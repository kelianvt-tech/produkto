"""The parts the service adds around the engine: who may call it, the page, and the shape
of what it answers. The engine itself is covered by test_engine.py."""

from __future__ import annotations

import re
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from parallel_dialer.api import create_app
from parallel_dialer.auth import SESSION_COOKIE, access_key, sign_session
from parallel_dialer.config import Settings
from parallel_dialer.dialer import CloseDialer
from parallel_dialer.live_dialer import LiveDialer
from parallel_dialer.profile import Profile

SECRET = "service-test-signing-secret-0123456789"
ORIGIN = "https://dialer.example.com"
ALICE = "alice@example.com"
BOB = "bob@example.com"
PROFILE = Profile(brand="Acme", brand_is_set=True)


@pytest.fixture
def service(tmp_path, monkeypatch):
    for name in ("TWILIO_ACCOUNT_SID", "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "CLOSE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    settings = Settings(
        root=tmp_path, public_base_url=ORIGIN, allowed_emails=frozenset({ALICE, BOB}), profile=PROFILE
    )
    offline = httpx.MockTransport(lambda request: httpx.Response(404, json={"error": "offline"}))
    close = CloseDialer(transport=offline)
    live = LiveDialer(settings, close, transport=offline)
    app = create_app(settings, close_dialer_instance=close, live_dialer_instance=live, secret=SECRET)
    client = TestClient(app, base_url=ORIGIN)
    return client, close, live


def sign_in(client: TestClient, email: str = ALICE, key: str | None = None, **form) -> httpx.Response:
    return client.post(
        "/login",
        data={"email": email, "key": access_key(SECRET, email) if key is None else key, **form},
        headers={"Origin": ORIGIN},
        follow_redirects=False,
    )


def signed_in(client: TestClient, email: str = ALICE) -> TestClient:
    assert sign_in(client, email).status_code == 303
    return client


def bearer(email: str = ALICE) -> dict:
    return {"Authorization": f"Bearer {access_key(SECRET, email)}"}


# --- sign-in ---


def test_the_page_sends_a_stranger_to_the_sign_in_form(service):
    client, _, _ = service
    response = client.get("/dialer/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login?next=/dialer/"


def test_the_sign_in_form_renders(service):
    client, _, _ = service
    response = client.get("/login?next=/dialer/")
    assert response.status_code == 200
    assert "Acme dialer" in response.text
    assert 'name="email"' in response.text and 'name="key"' in response.text
    assert 'name="next" value="/dialer/"' in response.text
    assert response.headers["cache-control"] == "no-store"


def test_the_access_key_opens_the_page(service):
    client, _, _ = service
    response = sign_in(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/dialer/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    # Not readable by page script, never sent over http, not sent along with other sites' requests.
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie

    page = client.get("/")
    assert page.status_code == 200
    body = page.text
    assert "Acme dialer" in body and "Parallel dialer" in body
    assert 'id="dialer-app"' in body
    assert "/assets/dialer.js" in body and "/assets/twilio-voice-2.18.5.js" in body
    assert page.headers["cache-control"] == "no-store"


def test_signed_in_visitors_skip_the_form(service):
    client, _, _ = service
    signed_in(client)
    response = client.get("/login?next=/dialer/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/dialer/"


def test_a_wrong_key_and_an_unlisted_email_are_refused_alike(service):
    client, _, _ = service
    wrong_key = sign_in(client, key="not-the-key")
    stranger = sign_in(client, email="someone@example.com")  # a real key for them, but not on the list
    for response in (wrong_key, stranger):
        assert response.status_code == 401
        assert "do not match" in response.text
        assert "set-cookie" not in response.headers
    # The form is shown again with the email they typed, not the key.
    assert 'value="someone@example.com"' in stranger.text


def test_a_key_belongs_to_one_operator(service):
    client, _, _ = service
    assert sign_in(client, email=ALICE, key=access_key(SECRET, BOB)).status_code == 401
    assert sign_in(client, email=BOB, key=access_key(SECRET, BOB)).status_code == 303


def test_signing_in_cannot_send_anyone_off_site(service):
    client, _, _ = service
    for target in ("https://evil.example/", "//evil.example", "/somewhere-else"):
        response = sign_in(client, next=target)
        assert response.headers["location"] == "/dialer/", target
    assert sign_in(client, next="/dialer/?smart_view_id=save_abc").headers["location"] == "/dialer/"


def test_cross_origin_sign_in_is_blocked(service):
    client, _, _ = service
    response = client.post(
        "/login",
        data={"email": ALICE, "key": access_key(SECRET, ALICE)},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_signed_out_api_calls_say_sign_in(service):
    client, _, _ = service
    response = client.get("/dialer/api/status")
    assert response.status_code == 401
    assert response.json() == {"error": "Sign in to use the dialer."}


def test_a_forged_expired_or_revoked_session_is_no_session(service):
    client, _, _ = service
    week = 7 * 86400
    valid = sign_session(SECRET, ALICE, "1", int(time.time()) + week)
    cases = {
        "forged signature": valid[:-3] + "AAA",
        "garbage": "not-a-cookie",
        "expired": sign_session(SECRET, ALICE, "1", int(time.time()) - 5),
        "someone else's secret": sign_session("another-secret", ALICE, "1", int(time.time()) + week),
        "revoked version": sign_session(SECRET, ALICE, "2", int(time.time()) + week),
        "not on the list any more": sign_session(SECRET, "gone@example.com", "1", int(time.time()) + week),
    }
    for name, cookie in cases.items():
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, cookie)
        assert client.get("/dialer/api/status").status_code == 401, name
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, valid)
    assert client.get("/dialer/api/status").status_code == 200


def test_signing_out_clears_the_session(service):
    client, _, _ = service
    signed_in(client)
    response = client.post("/logout", headers={"Origin": ORIGIN}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/dialer/api/status").status_code == 401


def test_cross_origin_sign_out_is_blocked(service):
    client, _, _ = service
    signed_in(client)
    assert client.post("/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/dialer/api/status").status_code == 200


# --- the access key, as a phone presents it ---


def test_access_keys_are_read_with_a_cookie_and_used_as_a_bearer(service):
    client, _, _ = service
    issued = signed_in(client).get("/dialer/api/mobile-token")
    assert issued.status_code == 200
    assert issued.json()["operator_email"] == ALICE
    assert issued.json()["server_url"] == ORIGIN
    token = issued.json()["token"]
    assert token == access_key(SECRET, ALICE)

    phone = TestClient(client.app, base_url=ORIGIN)  # no cookie at all
    assert phone.get("/dialer/api/status", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # A key must not be able to read itself back.
    assert phone.get("/dialer/api/mobile-token", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_each_operator_gets_a_different_key():
    assert access_key(SECRET, ALICE) != access_key(SECRET, BOB)
    assert access_key(SECRET, ALICE) != access_key(SECRET, ALICE, version="2")
    assert access_key(SECRET, "ALICE@example.com ") == access_key(SECRET, ALICE)
    assert access_key("", ALICE) == ""


def test_a_wrong_bearer_never_falls_back_to_the_cookie(service):
    client, _, _ = service
    response = signed_in(client).get("/dialer/api/status", headers={"Authorization": "Bearer revoked"})
    assert response.status_code == 401


# --- writes ---


def test_browser_writes_must_come_from_the_dialer_page(service):
    client, _, _ = service
    signed_in(client)
    blocked = client.post("/dialer/api/progress/reset", json={"smart_view_id": "save_" + "a" * 20})
    assert blocked.status_code == 403
    forged = client.post(
        "/dialer/api/progress/reset",
        json={"smart_view_id": "save_" + "a" * 20},
        headers={"Origin": "https://evil.example"},
    )
    assert forged.status_code == 403
    allowed = client.post(
        "/dialer/api/progress/reset", json={"smart_view_id": "save_" + "a" * 20}, headers={"Origin": ORIGIN}
    )
    assert allowed.status_code == 200


def test_the_phone_writes_without_an_origin(service):
    client, _, _ = service
    response = client.post(
        "/dialer/api/progress/reset", json={"smart_view_id": "save_" + "a" * 20}, headers=bearer()
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_the_operator_is_always_the_signed_in_person(service, monkeypatch):
    client, close, _ = service
    saved = []
    monkeypatch.setattr(
        close,
        "save_operator_api_key",
        lambda email, key: saved.append(email) or {"saved": True, "operator_email": email},
    )
    response = signed_in(client).put(
        "/dialer/api/settings",
        json={"api_key": "api_" + "k" * 20, "operator_email": BOB},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    # The body named Bob; the key still lands on the person signed in.
    assert saved == [ALICE]


def test_validation_errors_are_sentences_not_python(service):
    client, _, _ = service
    response = client.post(
        "/dialer/api/start",
        json={"smart_view_id": "save_" + "a" * 20, "screening_reply": "too short", "concurrency": 3},
        headers=bearer(),
    )
    assert response.status_code == 400
    message = response.json()["error"]
    assert message.startswith("The dialer refused the request")
    assert "screening reply" in message
    assert "[{" not in message and "'loc'" not in message


def test_session_limits(service):
    client, _, live = service
    assert live.max_session_contacts == 10000
    assert live.max_concurrency == 10
    response = client.post(
        "/dialer/api/start",
        json={
            "smart_view_id": "save_" + "a" * 20,
            "screening_reply": "This is Alice from Acme calling.",
            "concurrency": 11,
            "max_contacts": 5000,
        },
        headers=bearer(),
    )
    # 5000 contacts is accepted; only the 11th line is refused.
    assert response.status_code == 400
    assert "concurrency" in response.json()["error"]
    assert "max contacts" not in response.json()["error"]


# --- shapes the page and the app rely on ---


def test_the_talk_track_is_the_deployments_until_an_operator_saves_their_own(service):
    client, _, _ = service
    first = client.get("/dialer/api/talk-track", headers=bearer())
    assert first.status_code == 200
    body = first.json()
    assert body["ok"] is True
    assert "THE OPENER" in body["script"] and "with Acme" in body["script"]

    saved = client.put("/dialer/api/talk-track", json={"script": "my own track"}, headers=bearer())
    assert saved.status_code == 200
    assert saved.json() == {"ok": True, "script": "my own track"}
    assert client.get("/dialer/api/talk-track", headers=bearer()).json()["script"] == "my own track"
    # Saved per operator: Bob still has the deployment's.
    assert "THE OPENER" in client.get("/dialer/api/talk-track", headers=bearer(BOB)).json()["script"]


def test_the_talk_track_needs_a_signed_in_operator_and_a_sane_body(service):
    client, _, _ = service
    assert client.get("/dialer/api/talk-track").status_code == 401
    assert client.put("/dialer/api/talk-track", json={"script": "x"}).status_code == 401
    # A browser's write must come from the page, like every other write.
    signed_in(client)
    assert client.put("/dialer/api/talk-track", json={"script": "x"}).status_code == 403
    assert client.put("/dialer/api/talk-track", json={"script": "x"}, headers={"Origin": ORIGIN}).status_code == 200
    too_long = client.put("/dialer/api/talk-track", json={"script": "x" * 50_001}, headers={"Origin": ORIGIN})
    assert too_long.status_code == 400
    assert client.put("/dialer/api/talk-track", json={}, headers={"Origin": ORIGIN}).status_code == 400


def test_there_is_no_way_to_schedule_a_meeting_or_send_email(service):
    client, _, _ = service
    signed_in(client)
    headers = {"Origin": ORIGIN}
    for method, path in (
        ("POST", "/dialer/api/calendar/book-demo"),
        ("POST", "/dialer/api/calendar/check-availability"),
        ("POST", "/dialer/api/email/send-info"),
        ("GET", "/dialer/api/scheduling-settings"),
        ("PUT", "/dialer/api/scheduling-settings"),
    ):
        response = client.request(method, path, json={}, headers=headers)
        assert response.status_code == 404, (method, path)
    # Nor any route named for it (as whole words: "voicemail" is not "email").
    for route in client.app.routes:
        words = set(re.split(r"[/_{}.-]+", route.path.lower()))
        assert not words & {"calendar", "email", "schedule", "scheduling", "book", "booking", "invite", "availability"}, route.path


def test_session_ids_are_checked_before_the_engine_sees_them(service):
    client, _, _ = service
    assert client.get("/dialer/api/session/not-a-session", headers=bearer()).status_code == 400
    assert client.get("/dialer/api/session/ds_" + "0" * 32, headers=bearer()).status_code == 404


def test_twilio_calls_back_to_this_service(service):
    _, _, live = service
    assert live.public_base_url == f"{ORIGIN}/twilio/dialer"


def test_health_and_assets(service):
    client, _, _ = service
    assert client.get("/health").json()["service"] == "parallel-dialer"
    for asset in (
        "dialer.js", "dialer.css", "login.css", "favicon.svg", "twilio-voice-2.18.5.js",
        "phone-engine.html", "phone-engine.js", "fonts/manrope-latin.woff2",
    ):
        response = client.get(f"/assets/{asset}")
        assert response.status_code == 200, asset
        assert len(response.content) > 0, asset


def test_assets_are_served_with_the_types_the_browser_needs(service):
    client, _, _ = service
    # With nosniff on every response, a script served as text/plain is not run.
    for asset, kind in (
        ("dialer.js", "text/javascript"),
        ("twilio-voice-2.18.5.js", "text/javascript"),
        ("dialer.css", "text/css"),
        ("favicon.svg", "image/svg+xml"),
        ("fonts/manrope-latin.woff2", "font/woff2"),
    ):
        assert client.get(f"/assets/{asset}").headers["content-type"].startswith(kind), asset


def test_every_response_carries_the_security_headers(service):
    client, _, _ = service
    for path in ("/health", "/login", "/assets/dialer.js", "/dialer/api/status"):
        headers = client.get(path).headers
        assert "script-src 'self'" in headers["content-security-policy"], path
        assert "frame-ancestors 'none'" in headers["content-security-policy"], path
        assert headers["x-content-type-options"] == "nosniff", path
        assert headers["x-frame-options"] == "DENY", path
        assert "microphone=(self)" in headers["permissions-policy"], path
        assert "max-age=" in headers["strict-transport-security"], path  # https deployment


def test_plain_http_deployments_get_no_hsts_and_no_secure_cookie(tmp_path):
    settings = Settings(
        root=tmp_path,
        public_base_url="http://127.0.0.1:8767",
        allowed_emails=frozenset({ALICE}),
        profile=PROFILE,
    )
    offline = httpx.MockTransport(lambda request: httpx.Response(404))
    close = CloseDialer(transport=offline)
    app = create_app(
        settings, close_dialer_instance=close, live_dialer_instance=LiveDialer(settings, close, transport=offline),
        secret=SECRET,
    )
    client = TestClient(app, base_url="http://127.0.0.1:8767")
    assert "strict-transport-security" not in client.get("/health").headers
    response = client.post(
        "/login",
        data={"email": ALICE, "key": access_key(SECRET, ALICE)},
        headers={"Origin": "http://127.0.0.1:8767"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Secure" not in response.headers["set-cookie"]
    assert client.get("/dialer/api/status").status_code == 200


def test_the_dialer_is_locked_until_it_has_a_brand(tmp_path, monkeypatch):
    for name, value in {
        "TWILIO_ACCOUNT_SID": "AC" + "a" * 32,
        "TWILIO_API_KEY_SID": "SK" + "b" * 32,
        "TWILIO_API_KEY_SECRET": "secret-value-for-tests-123456",
        "TWILIO_PHONE_NUMBER": "+12025550100",
        "OPENAI_API_KEY": "openai-test-key",
        "DIALER_WEBHOOK_TOKEN": "webhook-secret-for-tests-123456789",
        "DIALER_LIVE_MODE": "enabled",
        "DIALER_UNRESTRICTED": "enabled",
    }.items():
        monkeypatch.setenv(name, value)
    offline = httpx.MockTransport(lambda request: httpx.Response(404))
    close = CloseDialer(transport=offline)

    named = LiveDialer(Settings(root=tmp_path / "a", profile=PROFILE), close, transport=offline)
    assert named.ready is True
    assert named.blockers() == []

    unnamed = LiveDialer(Settings(root=tmp_path / "b"), close, transport=offline)
    assert unnamed.ready is False
    assert any("company name" in blocker for blocker in unnamed.blockers())


def test_close_throttling_waits_and_retries_instead_of_failing_the_queue():
    # Close answers a burst of searches with 429; the whole queue load used to fail as
    # "Close CRM is temporarily unavailable" and show an empty list.
    from parallel_dialer.dialer import CloseRateLimitTransport

    calls = []

    def close(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) <= 2:
            return httpx.Response(429, headers={"retry-after": "1.5"})
        return httpx.Response(200, json={"data": []})

    slept = []
    transport = CloseRateLimitTransport(httpx.MockTransport(close), sleep=slept.append)
    with httpx.Client(transport=transport) as client:
        response = client.post("https://api.close.com/api/v1/data/search/", json={"query": {}})
    assert response.status_code == 200
    assert len(calls) == 3
    assert slept == [1.5, 1.5]  # the wait Close asked for, not a guess


def test_close_throttling_gives_up_after_a_bounded_number_of_tries():
    from parallel_dialer.dialer import CloseRateLimitTransport

    transport = CloseRateLimitTransport(
        httpx.MockTransport(lambda request: httpx.Response(429, headers={"retry-after": "60"})),
        max_retries=3,
        sleep=lambda _seconds: None,
    )
    with httpx.Client(transport=transport) as client:
        response = client.get("https://api.close.com/api/v1/me/")
    assert response.status_code == 429
    # Capped: a minute-long Retry-After must not hold a page load for minutes.
    assert transport.waits == [10.0, 10.0, 10.0]


def _count_close_reads(close, monkeypatch):
    reads = []

    def fetch(limit, smart_view_id, operator_email):
        reads.append((operator_email, smart_view_id))
        return {"connected": True, "contacts": [{"contact_id": f"c{i}"} for i in range(3)],
                "smart_views": [], "selected_smart_view": None}

    monkeypatch.setattr(close, "_fetch_contacts", fetch)
    return reads


def test_reloading_the_page_does_not_search_close_again(service, monkeypatch):
    client, close, _ = service
    reads = _count_close_reads(close, monkeypatch)
    signed_in(client)
    for _ in range(3):
        assert client.get("/dialer/api/contacts").status_code == 200
    # One trip to Close for three loads: a big view costs about 50 s each time.
    assert reads == [(ALICE, "")]
    # Another operator, or another view, is its own list.
    client.get("/dialer/api/contacts", headers=bearer(BOB))
    client.get("/dialer/api/contacts?smart_view_id=save_" + "b" * 20)
    assert len(reads) == 3


def test_an_old_list_is_shown_at_once_and_refreshed_behind_it(service, monkeypatch):
    client, close, _ = service
    reads = _count_close_reads(close, monkeypatch)
    signed_in(client)
    client.get("/dialer/api/contacts")
    # Age the remembered list past the fresh window.
    key = (ALICE, "")
    fetched, limit, payload = close._recent[key]
    close._recent[key] = (fetched - 600, limit, payload)

    started = time.monotonic()
    response = client.get("/dialer/api/contacts")
    assert response.status_code == 200
    assert time.monotonic() - started < 1.0  # served from memory, not a minute of Close
    deadline = time.monotonic() + 5
    while len(reads) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(reads) == 2  # and read again in the background


def test_starting_a_session_dials_the_list_on_screen(service, monkeypatch):
    from parallel_dialer.api import QUEUE_STALE_SECONDS

    _, close, _ = service
    reads = _count_close_reads(close, monkeypatch)
    close.contacts(5000, smart_view_id="save_" + "a" * 20, operator_email=ALICE)
    # What start_session asks for: the page's own bound, fewer contacts than loaded.
    again = close.contacts(
        2, smart_view_id="save_" + "a" * 20, operator_email=ALICE, max_age=QUEUE_STALE_SECONDS
    )
    assert len(reads) == 1
    assert len(again["contacts"]) == 2
    # Asking for more than was loaded, or a fresh read, goes back to Close.
    close.contacts(6000, smart_view_id="save_" + "a" * 20, operator_email=ALICE, max_age=120)
    assert len(reads) == 2


def test_start_finds_the_list_the_page_showed_for_the_first_view(service, monkeypatch):
    # The page asks for "" (the operator's first view) and Start for that view by id.
    # Filed under "" alone, Start read all of Close again.
    _, close, _ = service
    first = "save_" + "a" * 20
    reads = []

    def fetch(limit, smart_view_id, operator_email):
        reads.append(smart_view_id)
        return {"connected": True, "contacts": [{"contact_id": f"c{i}"} for i in range(3)],
                "smart_views": [{"id": first}], "selected_smart_view": {"id": first}}

    monkeypatch.setattr(close, "_fetch_contacts", fetch)
    close.contacts(5000, operator_email=BOB, max_age=1800)
    again = close.contacts(3, smart_view_id=first, operator_email=BOB, max_age=1800)
    assert reads == [""]
    assert len(again["contacts"]) == 3


def test_overlapping_reads_of_one_list_go_to_close_once(service, monkeypatch):
    import threading

    _, close, _ = service
    reads = []

    def fetch(limit, smart_view_id, operator_email):
        reads.append(smart_view_id)
        time.sleep(0.3)  # a big view is ~50 s of throttled searches
        return {"connected": True, "contacts": [{"contact_id": "c1"}],
                "smart_views": [], "selected_smart_view": None}

    monkeypatch.setattr(close, "_fetch_contacts", fetch)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(close.contacts(5000, operator_email=BOB)))
        for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # A Start, a reload and a second Start shared one read rather than one rate limit.
    assert reads == [""]
    assert [len(result["contacts"]) for result in results] == [1, 1, 1]


def test_start_reuses_the_page_list_and_checks_the_browser_is_still_there(service, monkeypatch):
    from parallel_dialer.api import QUEUE_STALE_SECONDS

    client, _, live = service
    seen = {}

    async def fake_start(**kwargs):
        seen.update(kwargs)
        seen["wanted"] = await kwargs["still_wanted"]()
        return {"id": "ds_" + "0" * 32}

    monkeypatch.setattr(live, "start_session", fake_start)
    response = client.post(
        "/dialer/api/start",
        json={"smart_view_id": "save_" + "a" * 20, "screening_reply": "This is Alice from Acme calling."},
        headers=bearer(BOB),
    )
    assert response.status_code == 200
    assert seen["operator_email"] == BOB
    assert seen["list_max_age"] == QUEUE_STALE_SECONDS
    assert seen["wanted"] is True  # a browser still waiting for the answer


def test_changing_the_close_key_drops_the_remembered_list(service, monkeypatch):
    client, close, _ = service
    reads = _count_close_reads(close, monkeypatch)
    monkeypatch.setattr(close, "save_operator_api_key", lambda email, key: {"saved": True})
    signed_in(client)
    client.get("/dialer/api/contacts")
    client.put("/dialer/api/settings", json={"api_key": "api_" + "k" * 20}, headers={"Origin": ORIGIN})
    client.get("/dialer/api/contacts")
    # A different key is a different Close account; its list must be read anew.
    assert reads == [(ALICE, ""), (ALICE, "")]


def test_flag_voicemail_endpoint(service, monkeypatch):
    client, _, live = service
    signed_in(client)
    session_id = "ds_" + "f" * 32
    called = []

    async def fake_drop(sid):
        called.append(sid)
        return {"id": sid, "status": "running"}

    monkeypatch.setattr(live, "drop_active_voicemail", fake_drop)
    response = client.post(
        f"/dialer/api/session/{session_id}/flag-voicemail",
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert called == [session_id]


def test_contacts_organize_endpoint(service, monkeypatch):
    client, close, _ = service
    signed_in(client)
    invalidated = []
    monkeypatch.setattr(
        close,
        "invalidate",
        lambda smart_view_id="", operator_email="": invalidated.append((operator_email, smart_view_id)),
    )
    response = client.post(
        "/dialer/api/contacts/organize",
        json={"smart_view_id": "save_" + "a" * 20},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert invalidated == [(ALICE, "save_" + "a" * 20)]


# --- the process entry point ---


def test_uvicorn_outlives_a_proxys_idle_connections(monkeypatch, tmp_path):
    import uvicorn

    from parallel_dialer import api

    monkeypatch.chdir(tmp_path)  # no dialer.toml or .env here
    monkeypatch.setenv("DIALER_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("DIALER_ALLOWED_EMAILS", ALICE)
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: seen.update(kwargs))
    api.run()
    # Caddy keeps an idle upstream connection 2 minutes. Closing it sooner made the proxy
    # reuse dead connections and answer 502 to the page and to Twilio's webhooks.
    assert seen["timeout_keep_alive"] > 120
    assert seen["host"] == "127.0.0.1"


def test_the_server_refuses_to_start_when_nobody_may_sign_in(monkeypatch, tmp_path):
    import uvicorn

    from parallel_dialer import api

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIALER_ROOT", str(tmp_path / "data"))
    monkeypatch.delenv("DIALER_ALLOWED_EMAILS", raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: pytest.fail("the server must not start"))
    with pytest.raises(SystemExit, match="DIALER_ALLOWED_EMAILS"):
        api.run()
