"""The dialer service: page, JSON API and Twilio callbacks in one process.

The page and a phone app call /dialer/api/*, Twilio calls /twilio/dialer/*, and the engine
answers both directly. The operator is always the person signed in: a request body that
names some other operator_email is ignored.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import mimetypes
import re
import threading
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import (
    SESSION_COOKIE,
    Operator,
    access_key,
    load_secret,
    match_access_key,
    read_session,
    sign_session,
    token_version,
)
from .config import ConfigError, Settings, read_secret
from .dialer import CloseDialer, DialerError
from .live_dialer import RECORDING_SLOTS, LiveDialer, LiveDialerError
from .profile import ProfileError
from .talk_track import load_talk_track, save_talk_track

# The types the page's assets need. On Windows Python reads them from the registry, where a
# stray entry can call a .js file text/plain, and the nosniff header below would then make the
# browser refuse to run it. Stated here, they are the same everywhere.
for _extension, _content_type in (
    (".js", "text/javascript"),
    (".css", "text/css"),
    (".svg", "image/svg+xml"),
    (".woff2", "font/woff2"),
):
    mimetypes.add_type(_content_type, _extension)

PACKAGE_DIR = Path(__file__).resolve().parent
SESSION_ID = re.compile(r"ds_[a-f0-9]{32}")
SLOT = re.compile(r"[a-z]{4,16}")
SMART_VIEW = re.compile(r"save_[A-Za-z0-9]{20,80}")
QUEUE_LIMIT = 5000
# A cold read of a big Smart View is a minute of throttled Close searches (about 110
# searches for 1,800 contacts). The page shows the list the Close client last read and
# refreshes it in the background once it is older than QUEUE_FRESH_SECONDS; a list older
# than QUEUE_STALE_SECONDS is read again before the page renders. Starting a session
# reuses the same list under the same bound, so Start dials what the page shows.
QUEUE_FRESH_SECONDS = 120.0
QUEUE_STALE_SECONDS = 1800.0


# --- Request bodies ---


class DialerStartRequest(BaseModel):
    smart_view_id: str = Field(pattern=r"^save_[A-Za-z0-9]{20,80}$", max_length=85)
    max_contacts: int = Field(default=5000, ge=1, le=10000)
    concurrency: int = Field(default=1, ge=1, le=10)
    screening_reply: str = Field(min_length=15, max_length=240)
    operator_target: Literal["browser", "phone"] = "browser"
    operator_email: str = ""
    timezone_wave: bool = True
    safe_hours_only: bool = False


class DialerCheckpointResetRequest(BaseModel):
    smart_view_id: str = Field(pattern=r"^save_[A-Za-z0-9]{20,80}$", max_length=85)
    operator_email: str = ""


class DialerVoicemailUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content_type: str = Field(min_length=5, max_length=80)
    data_base64: str = Field(min_length=1000, max_length=8_000_000)
    operator_email: str = ""


class DialerApiKeyRequest(BaseModel):
    api_key: str = Field(min_length=15, max_length=120)
    operator_email: str = ""


class DialerNumberLabelRequest(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    operator_email: str = ""


class DialerTwilioKeyRequest(BaseModel):
    account_sid: str = Field(min_length=30, max_length=40)
    api_key_sid: str = Field(min_length=30, max_length=40)
    api_key_secret: str = Field(min_length=16, max_length=80)
    phone_number: str = ""
    operator_email: str = ""


class DialerBuyNumberRequest(BaseModel):
    area_code: str = ""
    label: str = ""
    operator_email: str = ""


class TalkTrackRequest(BaseModel):
    script: str = Field(max_length=50_000)
    name: str = Field(default="", max_length=200)


# --- Helpers ---


class ApiError(Exception):
    """An error the page or the app shows as {"error": message}."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def _ok(result: Any) -> dict:
    data = dict(result) if isinstance(result, dict) else {}
    data.setdefault("ok", True)
    return data


def _humanize_validation(exc: RequestValidationError) -> str:
    problems = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
        field = (location[-1] if location else "value").replace("_", " ")
        message = str(error.get("msg", "is not valid"))
        problems.append(f"{field}: {message}")
    return "The dialer refused the request — " + "; ".join(problems) if problems else "The request was not valid."


def _initials(name: str) -> str:
    parts = [part for part in re.split(r"[\s._@-]+", name or "") if part]
    return "".join(part[0].upper() for part in parts[:2]) or "?"


class SecurityHeaders:
    """Adds response headers that are not already set. Plain ASGI on purpose: a
    BaseHTTPMiddleware wraps `receive`, and Start relies on request.is_disconnected()."""

    def __init__(self, app: Any, headers: dict[str, str]) -> None:
        self.app = app
        self.headers = [(name.lower().encode(), value.encode()) for name, value in headers.items()]

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                present = {name for name, _ in message.get("headers", [])}
                message = {
                    **message,
                    "headers": [*message.get("headers", []), *(h for h in self.headers if h[0] not in present)],
                }
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --- The app ---


def create_app(
    settings: Settings | None = None,
    *,
    close_dialer_instance: CloseDialer | None = None,
    live_dialer_instance: LiveDialer | None = None,
    secret: str | None = None,
    key_version: str | None = None,
) -> FastAPI:
    settings = settings or Settings.load()
    profile = settings.profile
    close_dialer = close_dialer_instance or CloseDialer(settings=settings)
    live_dialer = live_dialer_instance or LiveDialer(settings, close_dialer)
    secret = secret if secret is not None else load_secret(settings.state_dir)
    key_version = key_version or token_version()
    templates = Environment(
        loader=FileSystemLoader(str(PACKAGE_DIR / "templates")),
        autoescape=select_autoescape(["html"]),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        # Settle any call the last process left open.
        await live_dialer.reconcile()
        yield

    app = FastAPI(title="Parallel dialer", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(
        SecurityHeaders,
        headers={
            "Content-Security-Policy": (
                "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                "connect-src 'self' https://*.twilio.com wss://*.twilio.com; "
                "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            # The softphone is the only thing on the page that needs a device.
            "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
            **({"Strict-Transport-Security": "max-age=31536000; includeSubDomains"} if settings.secure_cookies else {}),
        },
    )
    app.state.live_dialer = live_dialer
    app.state.close_dialer = close_dialer

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        if request.url.path.startswith("/dialer/api/"):
            # The page and the app show `error` verbatim; pydantic's list used to
            # reach the operator's screen as raw Python.
            return JSONResponse({"error": _humanize_validation(exc)}, status_code=400)
        return JSONResponse({"detail": exc.errors()}, status_code=422)

    # --- Who is asking ---

    async def resolve_operator(request: Request) -> Operator | None:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            email = match_access_key(secret, header[7:], settings.allowed_emails, key_version)
            # A wrong key is not a fallback to the cookie: an app that holds a revoked
            # key must hear "pair again", not be let in some other way.
            return Operator(email=email, name=profile.operator_name(email), via="bearer") if email else None
        email = read_session(secret, request.cookies.get(SESSION_COOKIE, ""), key_version)
        if not email or email not in settings.allowed_emails:
            return None
        return Operator(email=email, name=profile.operator_name(email), via="session")

    async def api_operator(request: Request) -> Operator:
        operator = await resolve_operator(request)
        if operator is None:
            raise ApiError("Sign in to use the dialer.", 401)
        # A signed-in browser is the one caller a forged cross-site request can ride
        # on; the pairing token never travels by itself, so it needs no such check.
        if operator.via == "session" and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin", "").rstrip("/")
            if origin != settings.public_base_url:
                raise ApiError("Cross-origin dialer requests are blocked.", 403)
        return operator

    def login_redirect(request: Request) -> RedirectResponse:
        target = request.url.path if request.url.path.startswith("/dialer") else "/dialer/"
        return RedirectResponse(f"/login?next={quote(target)}", status_code=302)

    def safe_next(value: str) -> str:
        """Where to go after signing in: a page of this service, never another site."""
        return value if re.fullmatch(r"/dialer/?[A-Za-z0-9_./-]*", value or "") else "/dialer/"

    def login_html(error: str = "", email: str = "", next_path: str = "/dialer/", status: int = 200) -> HTMLResponse:
        html = templates.get_template("login.html").render(
            brand=profile.brand, error=error, email=email, next=next_path
        )
        return HTMLResponse(html, status_code=status, headers={"Cache-Control": "no-store"})

    # --- Queue, shared by the page and /dialer/api/contacts ---

    refreshing: set[tuple[str, str]] = set()
    refreshing_lock = threading.Lock()

    def refresh_in_background(smart_view_id: str, operator_email: str) -> None:
        key = (operator_email, smart_view_id)
        with refreshing_lock:
            if key in refreshing:
                return
            refreshing.add(key)

        def run() -> None:
            try:
                close_dialer.contacts(QUEUE_LIMIT, smart_view_id=smart_view_id, operator_email=operator_email)
            except DialerError:
                pass  # the list on screen stays; the next load tries again
            finally:
                with refreshing_lock:
                    refreshing.discard(key)

        threading.Thread(target=run, name=f"queue-refresh:{operator_email}", daemon=True).start()

    app.state.refresh_in_background = refresh_in_background

    def load_view(smart_view_id: str, operator_email: str) -> dict:
        if smart_view_id and not SMART_VIEW.fullmatch(smart_view_id):
            smart_view_id = ""
        try:
            contacts = close_dialer.contacts(
                QUEUE_LIMIT,
                smart_view_id=smart_view_id,
                operator_email=operator_email,
                max_age=QUEUE_STALE_SECONDS,
            )
            age = close_dialer.list_age(smart_view_id, operator_email)
            if age is not None and age > QUEUE_FRESH_SECONDS:
                refresh_in_background(smart_view_id, operator_email)
            # Attempted marks are never cached: decorate_contacts reads live progress.
            payload = live_dialer.decorate_contacts(contacts, operator_email=operator_email)
        except DialerError as exc:
            return {
                "connected": False,
                "contacts": [],
                "smart_views": [],
                "selected_smart_view": None,
                "checkpoint": {},
                "fetched_at": None,
                "live": {**live_dialer.status(operator_email=operator_email), "blockers": [str(exc)]},
            }
        return {
            "connected": bool(payload.get("connected")),
            "contacts": payload.get("contacts") if isinstance(payload.get("contacts"), list) else [],
            "smart_views": payload.get("smart_views") if isinstance(payload.get("smart_views"), list) else [],
            "selected_smart_view": payload.get("selected_smart_view")
            if isinstance(payload.get("selected_smart_view"), dict)
            else None,
            "checkpoint": payload.get("checkpoint") if isinstance(payload.get("checkpoint"), dict) else {},
            "fetched_at": payload.get("fetched_at"),
            "live": payload.get("live") if isinstance(payload.get("live"), dict) else {},
        }

    # --- Health and the page ---

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "ready": bool(live_dialer.ready), "service": "parallel-dialer"}

    @app.get("/", response_class=HTMLResponse)
    @app.get("/dialer", response_class=HTMLResponse)
    @app.get("/dialer/", response_class=HTMLResponse)
    async def page(request: Request, smart_view_id: str = Query(default="", max_length=85)):
        operator = await resolve_operator(request)
        if operator is None or operator.via != "session":
            return login_redirect(request)
        view = await asyncio.to_thread(load_view, smart_view_id, operator.email)
        user = {"email": operator.email, "display_name": operator.name}
        content = templates.get_template("dialer.html").render(
            dialer=view,
            user=user,
            initials_for=_initials,
            csrf="",
            profile=profile.page_values(operator.email),
        )
        html = templates.get_template("shell.html").render(
            title="Parallel dialer",
            brand=profile.brand,
            content=Markup(content),
            user=user,
            role_label="Operator",
            initials=_initials(operator.name),
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, next_path: str = Query(default="", alias="next", max_length=200)) -> Response:
        destination = safe_next(next_path)
        if await resolve_operator(request) is not None:
            return RedirectResponse(destination, status_code=302)
        return login_html(next_path=destination)

    @app.post("/login")
    async def login_submit(request: Request) -> Response:
        origin = request.headers.get("origin", "").rstrip("/")
        if origin and origin != settings.public_base_url:
            raise ApiError("Cross-origin sign-in is blocked.", 403)
        form = await request.form()
        email = str(form.get("email") or "").strip().lower()
        destination = safe_next(str(form.get("next") or ""))
        allowed = frozenset({email}) & settings.allowed_emails
        if not match_access_key(secret, str(form.get("key") or ""), allowed, key_version):
            return login_html("That email and access key do not match.", email, destination, 401)
        lifetime = settings.session_days * 86400
        response = RedirectResponse(destination, status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            sign_session(secret, email, key_version, int(time.time()) + lifetime),
            max_age=lifetime,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/logout")
    async def logout(request: Request) -> Response:
        origin = request.headers.get("origin", "").rstrip("/")
        if origin and origin != settings.public_base_url:
            raise ApiError("Cross-origin sign-out is blocked.", 403)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.secure_cookies, httponly=True)
        return response

    # --- /dialer/api: the page and a phone app ---

    @app.get("/dialer/api/mobile-token")
    async def api_mobile_token(request: Request) -> dict:
        operator = await resolve_operator(request)
        # Cookie only: a key must not be able to read itself back, or a stolen one
        # could be used to enumerate the others.
        if operator is None or operator.via != "session":
            raise ApiError("Sign in on the web to get a pairing token.", 401)
        token = access_key(secret, operator.email, key_version)
        if not token:
            raise ApiError("The dialer has no signing secret configured.", 503)
        return {"ok": True, "operator_email": operator.email, "server_url": settings.public_base_url, "token": token}

    @app.get("/dialer/api/contacts")
    async def api_contacts(
        smart_view_id: str = Query(default="", max_length=85), operator: Operator = Depends(api_operator)
    ) -> dict:
        return {"ok": True, **await asyncio.to_thread(load_view, smart_view_id, operator.email)}

    @app.get("/dialer/api/status")
    def api_status(operator: Operator = Depends(api_operator)) -> dict:
        return {"ok": True, **live_dialer.status(operator_email=operator.email)}

    @app.get("/dialer/api/voice-token")
    def api_voice_token(operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {"ok": True, **live_dialer.voice_access_token(operator_email=operator.email)}
        except LiveDialerError as exc:
            raise ApiError(str(exc), 503) from exc

    # Close key (per operator)

    @app.get("/dialer/api/settings")
    def api_settings_get(operator: Operator = Depends(api_operator)) -> dict:
        return _ok(close_dialer.operator_api_key_status(operator.email))

    @app.put("/dialer/api/settings")
    def api_settings_put(body: DialerApiKeyRequest, operator: Operator = Depends(api_operator)) -> dict:
        try:
            saved = _ok(close_dialer.save_operator_api_key(operator.email, body.api_key))
        except DialerError as exc:
            raise ApiError(str(exc), 400) from exc
        close_dialer.forget_lists(operator.email)
        return saved

    @app.delete("/dialer/api/settings")
    def api_settings_delete(operator: Operator = Depends(api_operator)) -> dict:
        close_dialer.forget_lists(operator.email)
        return _ok(close_dialer.delete_operator_api_key(operator.email))

    # Twilio account (per operator)

    @app.get("/dialer/api/twilio-settings")
    def api_twilio_get(operator: Operator = Depends(api_operator)) -> dict:
        return _ok(live_dialer.operator_twilio_settings(operator.email))

    @app.put("/dialer/api/twilio-settings")
    def api_twilio_put(body: DialerTwilioKeyRequest, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return _ok(
                live_dialer.update_operator_twilio_settings(
                    operator.email, body.account_sid, body.api_key_sid, body.api_key_secret, body.phone_number or ""
                )
            )
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.delete("/dialer/api/twilio-settings")
    def api_twilio_delete(operator: Operator = Depends(api_operator)) -> dict:
        return _ok(live_dialer.delete_operator_twilio_settings(operator.email))

    # Caller-ID numbers (per operator)

    @app.get("/dialer/api/numbers")
    def api_numbers(operator: Operator = Depends(api_operator)) -> dict:
        return _ok(live_dialer.operator_numbers(operator.email))

    @app.post("/dialer/api/numbers/buy")
    async def api_numbers_buy(body: DialerBuyNumberRequest, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return _ok(
                await live_dialer.buy_operator_number(
                    operator.email, area_code=body.area_code or "", label=body.label or ""
                )
            )
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.patch("/dialer/api/numbers/{phone_sid}")
    def api_numbers_label(
        phone_sid: str, body: DialerNumberLabelRequest, operator: Operator = Depends(api_operator)
    ) -> dict:
        try:
            return _ok(live_dialer.update_operator_number_label(operator.email, phone_sid, body.label))
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.post("/dialer/api/numbers/{phone_sid}/main")
    async def api_numbers_main(phone_sid: str, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return _ok(await live_dialer.set_main_line(operator.email, phone_sid))
        except (LiveDialerError, httpx.HTTPError) as exc:
            raise ApiError(str(exc) if isinstance(exc, LiveDialerError) else "Twilio did not accept the change.", 400) from exc

    @app.delete("/dialer/api/numbers/{phone_sid}")
    async def api_numbers_delete(phone_sid: str, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return _ok(await live_dialer.delete_operator_number(operator.email, phone_sid))
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    # Recordings the contact hears

    @app.put("/dialer/api/voicemail")
    def api_voicemail(body: DialerVoicemailUploadRequest, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {
                "ok": True,
                "voicemail": live_dialer.save_voicemail_recording(
                    filename=body.filename,
                    content_type=body.content_type,
                    data_base64=body.data_base64,
                    operator_email=operator.email,
                ),
            }
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.get("/dialer/api/recording/{slot}")
    def api_recording_get(slot: str, operator: Operator = Depends(api_operator)) -> Response:
        if not SLOT.fullmatch(slot):
            raise ApiError("Unknown recording slot.", 400)
        try:
            audio, content_type = live_dialer.recording_audio(slot, operator_email=operator.email)
        except LiveDialerError as exc:
            raise ApiError(str(exc), 404) from exc
        return Response(audio, media_type=content_type, headers={"Cache-Control": "private, no-cache"})

    @app.put("/dialer/api/recording/{slot}")
    def api_recording_put(
        slot: str, body: DialerVoicemailUploadRequest, operator: Operator = Depends(api_operator)
    ) -> dict:
        if not SLOT.fullmatch(slot):
            raise ApiError("Unknown recording slot.", 400)
        try:
            return {
                "ok": True,
                "slot": slot,
                "recording": live_dialer.save_recording(
                    slot,
                    filename=body.filename,
                    content_type=body.content_type,
                    data_base64=body.data_base64,
                    operator_email=operator.email,
                ),
                "recordings": live_dialer.recordings_metadata(operator_email=operator.email),
            }
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.delete("/dialer/api/recording/{slot}")
    def api_recording_delete(slot: str, operator: Operator = Depends(api_operator)) -> dict:
        if not SLOT.fullmatch(slot):
            raise ApiError("Unknown recording slot.", 400)
        try:
            return {
                "ok": True,
                "slot": slot,
                "recording": live_dialer.delete_recording(slot, operator_email=operator.email),
                "recordings": live_dialer.recordings_metadata(operator_email=operator.email),
            }
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.post("/dialer/api/callbacks/configure")
    async def api_callbacks(operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {"ok": True, "callback_routing": await live_dialer.configure_inbound_routing()}
        except (LiveDialerError, OSError) as exc:
            raise ApiError(str(exc), 400) from exc

    # Sessions

    @app.post("/dialer/api/start")
    async def api_start(
        request: Request, body: DialerStartRequest, operator: Operator = Depends(api_operator)
    ) -> dict:
        async def still_wanted() -> bool:
            # Caddy closes our side when the browser drops the request.
            return not await request.is_disconnected()

        try:
            session = await live_dialer.start_session(
                smart_view_id=body.smart_view_id,
                max_contacts=body.max_contacts,
                concurrency=body.concurrency,
                screening_reply=body.screening_reply,
                operator_target=body.operator_target,
                operator_email=operator.email,
                timezone_wave=body.timezone_wave,
                safe_hours_only=body.safe_hours_only,
                list_max_age=QUEUE_STALE_SECONDS,
                still_wanted=still_wanted,
            )
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc
        return {"ok": True, "session": session}

    @app.post("/dialer/api/progress/reset")
    async def api_progress_reset(body: DialerCheckpointResetRequest, operator: Operator = Depends(api_operator)) -> dict:
        try:
            result = await live_dialer.reset_checkpoint(body.smart_view_id, operator_email=operator.email)
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc
        return {"ok": True, "checkpoint": result}

    @app.post("/dialer/api/contacts/organize")
    async def api_contacts_organize(
        body: DialerCheckpointResetRequest, operator: Operator = Depends(api_operator)
    ) -> dict:
        try:
            close_dialer.invalidate(body.smart_view_id, operator.email)
            view = await asyncio.to_thread(load_view, body.smart_view_id, operator.email)
            return {"ok": True, "dialer": view}
        except DialerError as exc:
            raise ApiError(str(exc), 400) from exc

    def _session_id(session_id: str) -> str:
        if not SESSION_ID.fullmatch(session_id):
            raise ApiError("Invalid dialer session.", 400)
        return session_id

    @app.get("/dialer/api/session/{session_id}")
    def api_session(session_id: str, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {"ok": True, "session": live_dialer.session(_session_id(session_id))}
        except LiveDialerError as exc:
            raise ApiError(str(exc), 404) from exc

    @app.post("/dialer/api/session/{session_id}/stop")
    async def api_session_stop(session_id: str, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {"ok": True, "session": await live_dialer.stop_session(_session_id(session_id))}
        except LiveDialerError as exc:
            raise ApiError(str(exc), 404) from exc

    @app.post("/dialer/api/session/{session_id}/complete-active")
    async def api_session_complete(session_id: str, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {"ok": True, "session": await live_dialer.complete_active_call(_session_id(session_id))}
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.post("/dialer/api/session/{session_id}/disqualify-active")
    async def api_session_disqualify(
        session_id: str,
        request: Request,
        operator: Operator = Depends(api_operator),
    ) -> dict:
        disposition = "Not Interested"
        try:
            data = await request.json()
            if isinstance(data, dict) and data.get("disposition"):
                disposition = str(data["disposition"])
        except Exception:
            pass
        try:
            return {
                "ok": True,
                "session": await live_dialer.disqualify_active_call(
                    _session_id(session_id), disposition=disposition
                ),
            }
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    @app.post("/dialer/api/session/{session_id}/flag-voicemail")
    @app.post("/dialer/api/session/{session_id}/drop-voicemail")
    async def api_session_voicemail(session_id: str, operator: Operator = Depends(api_operator)) -> dict:
        try:
            return {"ok": True, "session": await live_dialer.drop_active_voicemail(_session_id(session_id))}
        except LiveDialerError as exc:
            raise ApiError(str(exc), 400) from exc

    # Talk track

    @app.get("/dialer/api/talk-track")
    def api_talk_track_get(name: str = "", operator: Operator = Depends(api_operator)) -> dict:
        name = name if name in profile.script_names() else ""
        return {"ok": True, "name": name, "script": load_talk_track(operator.email, settings.state_dir, profile, name)}

    @app.put("/dialer/api/talk-track")
    def api_talk_track_put(body: TalkTrackRequest, operator: Operator = Depends(api_operator)) -> dict:
        name = body.name if body.name in profile.script_names() else ""
        save_talk_track(operator.email, body.script, settings.state_dir, name)
        return {"ok": True, "name": name, "script": body.script}

    @app.get("/dialer/api/contacts/{contact_id}/call-notes")
    async def api_call_notes(
        contact_id: str,
        lead_id: str = Query(default=""),
        phone: str = Query(default=""),
        limit: int = Query(default=5, ge=1, le=20),
        operator: Operator = Depends(api_operator),
    ) -> dict:
        op = operator.email
        try:
            result = await asyncio.to_thread(
                close_dialer.call_notes,
                contact_id=contact_id,
                lead_id=lead_id,
                phone=phone,
                limit=limit,
                operator_email=op,
            )
        except DialerError:
            result = {"ok": False, "has_called_before": False, "total_calls": 0, "call_notes": []}
        if not result.get("has_called_before"):
            # The dialer's own memory of an attempt, for contacts Close has no call on yet.
            with contextlib.suppress(AttributeError, KeyError, TypeError, ValueError):
                cid = contact_id.strip()
                found = None
                for checkpoint in live_dialer.checkpoints.values():
                    history = getattr(checkpoint, "contact_history", None)
                    if history and cid in history and history[cid].attempts > 0:
                        found = history[cid]
                        break
                if found:
                    outcome = found.last_outcome or "attempted"
                    last_at = found.last_attempted_at or ""
                    result = {
                        "ok": True,
                        "has_called_before": True,
                        "total_calls": found.attempts,
                        "call_notes": [
                            {
                                "id": f"checkpoint_{cid}",
                                "date": last_at,
                                "date_formatted": last_at[:16].replace("T", " ") if last_at else "",
                                "relative_date": "Previous attempt",
                                "duration": 0,
                                "duration_formatted": "",
                                "user_name": profile.operator_name(op),
                                "direction": "outbound",
                                "status": outcome,
                                "note": f"Previous dialer attempt — outcome: {outcome}",
                                "source": "dialer_checkpoint",
                            }
                        ],
                    }
        return result

    # --- /twilio/dialer: Twilio's callbacks ---

    def require_twilio_attempt(attempt_id: str, signature: str) -> None:
        if not live_dialer.verify_signature(attempt_id, signature):
            raise StarletteHTTPException(status_code=403, detail="Invalid dialer callback signature")

    def require_twilio_session(session_id: str, signature: str) -> None:
        if not live_dialer.verify_session_signature(session_id, signature):
            raise StarletteHTTPException(status_code=403, detail="Invalid dialer session signature")

    async def twilio_form(request: Request) -> dict[str, str]:
        form = await request.form()
        return {str(key): str(value) for key, value in form.multi_items()}

    def forbidden(exc: Exception) -> StarletteHTTPException:
        return StarletteHTTPException(status_code=403, detail=str(exc))

    @app.post("/twilio/dialer/operator-answer", include_in_schema=False)
    async def twilio_operator_answer(
        request: Request,
        session_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_session(session_id, sig)
        try:
            twiml = await live_dialer.handle_session_operator_answer(session_id, await twilio_form(request))
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(twiml, media_type="application/xml")

    @app.post("/twilio/dialer/operator-status", include_in_schema=False, status_code=204)
    async def twilio_operator_status(
        request: Request,
        session_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_session(session_id, sig)
        try:
            await live_dialer.handle_session_operator_status(session_id, await twilio_form(request))
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(status_code=204)

    def media_response(slot: str, sig: str, op: str = "") -> Response:
        if not live_dialer.verify_media_signature(sig, slot):
            raise StarletteHTTPException(status_code=403, detail="Invalid media signature")
        try:
            audio, content_type = live_dialer.recording_audio(slot, operator_email=op)
        except LiveDialerError as exc:
            raise StarletteHTTPException(status_code=404, detail=str(exc)) from exc
        return Response(audio, media_type=content_type, headers={"Cache-Control": "public, max-age=3600, immutable"})

    @app.get("/twilio/dialer/recording-media/{slot}", include_in_schema=False)
    def twilio_recording_media(
        slot: str, sig: str = Query(min_length=64, max_length=64), op: str = Query(default="")
    ) -> Response:
        if slot not in RECORDING_SLOTS:
            raise StarletteHTTPException(status_code=404, detail="Unknown recording slot")
        return media_response(slot, sig, op=op)

    @app.get("/twilio/dialer/voicemail-media", include_in_schema=False)
    def twilio_voicemail_media(sig: str = Query(min_length=64, max_length=64), op: str = Query(default="")) -> Response:
        # Kept so a call already holding a pre-slots URL still plays its message.
        return media_response("voicemail", sig, op=op)

    @app.post("/twilio/dialer/inbound", include_in_schema=False)
    async def twilio_inbound(request: Request, sig: str = Query(min_length=64, max_length=64)) -> Response:
        if not live_dialer.verify_inbound_signature(sig):
            raise StarletteHTTPException(status_code=403, detail="Invalid inbound routing signature")
        form = await twilio_form(request)
        # The caller is who Close matches the callback to, so it has to survive the forward.
        return Response(
            live_dialer.inbound_twiml(str(form.get("From") or ""), str(form.get("To") or "")),
            media_type="application/xml",
        )

    @app.post("/twilio/dialer/answer", include_in_schema=False)
    async def twilio_answer(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        params = await twilio_form(request)
        attempt = live_dialer.attempt(attempt_id)
        if not live_dialer._validate_call_sid(attempt, params.get("CallSid", "")):
            raise StarletteHTTPException(status_code=403, detail="Call identifier mismatch")
        return Response(live_dialer.answer_twiml(attempt_id), media_type="application/xml")

    @app.post("/twilio/dialer/speech", include_in_schema=False)
    async def twilio_speech(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        try:
            params = await twilio_form(request)
            params["_IdempotencyToken"] = request.headers.get("I-Twilio-Idempotency-Token", "")
            twiml = await live_dialer.handle_speech(attempt_id, params)
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(twiml, media_type="application/xml")

    @app.post("/twilio/dialer/status", include_in_schema=False, status_code=204)
    async def twilio_status(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        try:
            await live_dialer.handle_status(attempt_id, await twilio_form(request))
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(status_code=204)

    @app.post("/twilio/dialer/operator", include_in_schema=False, status_code=204)
    async def twilio_operator(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        try:
            live_dialer.handle_operator_status(attempt_id, await twilio_form(request))
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(status_code=204)

    @app.post("/twilio/dialer/bridge", include_in_schema=False)
    async def twilio_bridge(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        try:
            twiml = live_dialer.handle_bridge_result(attempt_id, await twilio_form(request))
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(twiml, media_type="application/xml")

    @app.post("/twilio/dialer/stream-callback", include_in_schema=False)
    async def twilio_stream_callback(request: Request) -> Response:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        # Only the dialer's webhook secret is valid here.
        expected = live_dialer.webhook_secret
        if not expected or token != expected:
            raise StarletteHTTPException(status_code=401, detail="Unauthorized stream callback")
        try:
            body = await request.json()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise StarletteHTTPException(status_code=400, detail="Invalid JSON") from exc
        attempt_id = str(body.get("attempt_id") or "").strip()
        if not attempt_id:
            raise StarletteHTTPException(status_code=400, detail="Missing attempt_id")
        try:
            result = await live_dialer.handle_stream_callback(
                attempt_id, str(body.get("kind") or "unknown").strip(), str(body.get("transcript") or "").strip()
            )
        except LiveDialerError as exc:
            raise StarletteHTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/twilio/dialer/amd", include_in_schema=False, status_code=204)
    async def twilio_amd(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        params = await twilio_form(request)

        async def process_amd() -> None:
            with contextlib.suppress(LiveDialerError):
                await live_dialer.handle_amd(attempt_id, params)

        asyncio.create_task(process_amd())
        return Response(status_code=204)

    @app.post("/twilio/dialer/recording", include_in_schema=False, status_code=204)
    async def twilio_recording(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        try:
            await live_dialer.handle_recording_status(attempt_id, await twilio_form(request))
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(status_code=204)

    @app.post("/twilio/dialer/conference-recording", include_in_schema=False, status_code=204)
    async def twilio_conference_recording(
        request: Request,
        attempt_id: str = Query(min_length=8, max_length=80),
        sig: str = Query(min_length=64, max_length=64),
    ) -> Response:
        require_twilio_attempt(attempt_id, sig)
        try:
            await live_dialer.handle_recording_status(attempt_id, await twilio_form(request), is_conference=True)
        except LiveDialerError as exc:
            raise forbidden(exc) from exc
        return Response(status_code=204)

    @app.get("/twilio/dialer/call-recording/{recording_ref}", include_in_schema=False)
    async def twilio_call_recording(recording_ref: str) -> Response:
        try:
            audio, content_type = await live_dialer.call_recording_audio(recording_ref.removesuffix(".mp3"))
        except LiveDialerError as exc:
            raise StarletteHTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            audio,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400, immutable", "Accept-Ranges": "bytes"},
        )

    app.mount("/assets", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="assets")
    return app


def run() -> None:  # pragma: no cover - the process entry point
    import sys

    import uvicorn

    try:
        settings = Settings.load()
        if not settings.allowed_emails:
            raise ConfigError(
                "Set DIALER_ALLOWED_EMAILS to the address that may sign in (comma-separate several)."
            )
    except (ConfigError, ProfileError) as exc:
        sys.exit(f"parallel-dialer: {exc}")
    if not settings.profile.brand_is_set:
        print(
            "parallel-dialer: no brand name is set ([brand] name in dialer.toml), so the dialer stays "
            "locked: the brand is spoken to the people you call.",
            file=sys.stderr,
        )
    uvicorn.run(
        "parallel_dialer.api:create_app",
        factory=True,
        host=read_secret("dialer-host", "DIALER_HOST") or "127.0.0.1",
        port=int(read_secret("dialer-port", "DIALER_PORT") or 8767),
        proxy_headers=True,
        forwarded_allow_ips=read_secret("dialer-forwarded-allow-ips", "FORWARDED_ALLOW_IPS") or "127.0.0.1",
        # Longer than a reverse proxy keeps an idle upstream connection (Caddy: 2 minutes).
        # With uvicorn's default of 5 s the proxy reuses connections uvicorn has just closed
        # and answers 502 ("connection reset by peer"), which loses a webhook or a poll.
        timeout_keep_alive=150,
    )
