from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx

from .config import Settings, clean_operator_identity, read_secret


class DialerError(RuntimeError):
    """Raised when the CRM-backed demo queue cannot be loaded."""


NON_COLD_STATUSES = {
    "customer",
    "active customer",
    "closed won",
    "proposal sent",
    "in negotiation",
    "negotiating",
    "trial",
    "pilot",
    "bad fit",
    "do not call",
    "dnc",
    "not interested",
    "interested",
    "canceled",
}


class CloseRateLimitTransport(httpx.BaseTransport):
    """Waits and retries when Close answers 429, instead of failing the whole call.

    One queue load searches Close about eighteen times in a burst: the Smart View in
    pages of 100, then lead details and open opportunities in chunks of 40. Close
    throttles search per API key. A single 429 used to surface as "Close CRM is
    temporarily unavailable" and an empty queue.

    A 429 means Close did not process the request, so retrying a write is as safe as
    retrying a search. The wait is the one Close asks for, capped, a few times over.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport | None = None,
        *,
        max_retries: int = 5,
        max_wait: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._owns_inner = inner is None
        self.inner = inner or httpx.HTTPTransport()
        self.max_retries = max_retries
        self.max_wait = max_wait
        self.sleep = sleep
        self.waits: list[float] = []

    def _wait_seconds(self, response: httpx.Response, attempt: int) -> float:
        for header in ("retry-after", "ratelimit-reset"):
            value = response.headers.get(header)
            if value:
                try:
                    return min(self.max_wait, max(0.2, float(value)))
                except ValueError:
                    continue
        return min(self.max_wait, 0.5 * (2**attempt))

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()  # buffer the body so the same request can be sent again
        attempt = 0
        while True:
            response = self.inner.handle_request(request)
            if response.status_code != 429 or attempt >= self.max_retries:
                return response
            wait = self._wait_seconds(response, attempt)
            response.read()
            response.close()
            self.waits.append(wait)
            self.sleep(wait)
            attempt += 1

    def close(self) -> None:
        # Only close what this wrapper opened: a transport handed in (a test's mock,
        # or one shared by the caller) is not ours to shut.
        if self._owns_inner:
            self.inner.close()


class CloseDialer:
    base_url = "https://api.close.com/api/v1"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings
        self.api_key = read_secret("dialer-close-api-key", "CLOSE_API_KEY")
        self.transport = transport
        self.custom_user_ids: dict[str, str] = {}
        # (operator, smart view) -> (fetched at, limit asked for, what Close returned).
        # A big view costs Close ~110 throttled searches (1,800 contacts take about
        # 50 s), and the page, a reload and the Start button all want the same list
        # within seconds of each other. See contacts(max_age=...).
        self._recent: dict[tuple[str, str], tuple[float, int, dict[str, Any]]] = {}
        self._recent_lock = threading.Lock()
        # One Close read per list at a time; the rest wait for it. See contacts().
        self._reading: dict[tuple[str, str], threading.Lock] = {}

    def _http_transport(self) -> CloseRateLimitTransport:
        return CloseRateLimitTransport(self.transport)

    def _key_path(self, clean_operator: str) -> Path | None:
        if not clean_operator or not self.settings:
            return None
        return self.settings.state_dir / f"dialer-close-key-{clean_operator}.json"

    def api_key_for(self, operator_email: str = "") -> str:
        clean = (operator_email or "").strip().lower()
        clean_op = clean_operator_identity(clean) if clean else ""

        # 1. Custom per-operator key file saved from dialer UI
        if clean_op:
            path = self._key_path(clean_op)
            if path and path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    key = str(data.get("api_key") or "").strip()
                    if key:
                        return key
                except (OSError, json.JSONDecodeError, TypeError):
                    pass

        # 2. Per-operator credential from systemd / env
        if clean_op:
            custom_key = read_secret(
                f"dialer-close-api-key-{clean_op}",
                f"CLOSE_API_KEY_{clean_op.upper()}",
            )
            if custom_key:
                return custom_key

        # 3. Fall back to shared / default key (used in tests and single-operator mode)
        return self.api_key

    def user_id_for(self, operator_email: str = "") -> str:
        clean = (operator_email or "").strip().lower()
        clean_op = clean_operator_identity(clean) if clean else ""
        if clean in self.custom_user_ids:
            return self.custom_user_ids[clean]
        if clean_op in self.custom_user_ids:
            return self.custom_user_ids[clean_op]
        # Check saved key file
        if clean_op:
            path = self._key_path(clean_op)
            if path and path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    uid = str(data.get("user_id") or "").strip()
                    if uid:
                        return uid
                except (OSError, json.JSONDecodeError, TypeError):
                    pass
        return ""

    def operator_api_key_status(self, operator_email: str = "") -> dict[str, Any]:
        clean = (operator_email or "").strip().lower()
        clean_op = clean_operator_identity(clean) if clean else ""
        if clean_op:
            path = self._key_path(clean_op)
            if path and path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    key = str(data.get("api_key") or "").strip()
                    return {
                        "configured": True,
                        "is_custom": True,
                        "user_id": str(data.get("user_id") or ""),
                        "user_name": str(data.get("user_name") or ""),
                        "user_email": str(data.get("user_email") or operator_email),
                        "key_masked": f"api_******{key[-4:]}" if len(key) >= 4 else "api_****",
                        "updated_at": str(data.get("updated_at") or ""),
                    }
                except (OSError, json.JSONDecodeError, TypeError):
                    pass
            sys_key = read_secret(
                f"dialer-close-api-key-{clean_op}",
                f"CLOSE_API_KEY_{clean_op.upper()}",
            )
            if sys_key:
                return {
                    "configured": True,
                    "is_custom": False,
                    "user_id": self.user_id_for(operator_email),
                    "user_name": clean_op.capitalize(),
                    "user_email": operator_email,
                    "key_masked": f"api_******{sys_key[-4:]}",
                    "updated_at": "",
                }
        if self.api_key:
            # The shared key from the environment: what every operator without a key of
            # their own dials on, so it is what the page should say is in use.
            return {
                "configured": True,
                "is_custom": False,
                "user_id": self.user_id_for(operator_email),
                "user_name": clean_op.replace("_", " ").title() if clean_op else "",
                "user_email": operator_email,
                "key_masked": f"api_******{self.api_key[-4:]}",
                "updated_at": "",
            }
        return {
            "configured": False,
            "is_custom": False,
            "user_id": "",
            "user_name": "",
            "user_email": operator_email,
            "key_masked": "",
            "updated_at": "",
        }

    def save_operator_api_key(
        self, operator_email: str, api_key: str
    ) -> dict[str, Any]:
        clean_key = str(api_key or "").strip()
        if not clean_key.startswith("api_") or len(clean_key) < 15:
            raise DialerError("Invalid Close API key format. Close keys start with 'api_'.")
        clean = (operator_email or "").strip().lower()
        clean_op = clean_operator_identity(clean) if clean else ""
        if not clean_op:
            raise DialerError("Unknown operator identity.")

        # Validate against Close API
        try:
            with httpx.Client(
                auth=httpx.BasicAuth(clean_key, ""),
                timeout=15,
                transport=self._http_transport(),
                headers={"Accept": "application/json"},
            ) as client:
                res = client.get(f"{self.base_url}/me/")
                if res.status_code == 401:
                    raise DialerError("Close CRM rejected this API key (Unauthorized). Please check the key.")
                res.raise_for_status()
                user_data = res.json()
        except DialerError:
            raise
        except Exception as exc:
            raise DialerError(f"Could not verify API key with Close CRM: {exc}") from exc

        user_id = str(user_data.get("id") or "")
        first = str(user_data.get("first_name") or "")
        last = str(user_data.get("last_name") or "")
        display_name = f"{first} {last}".strip() or str(user_data.get("email") or clean_op)
        user_email = str(user_data.get("email") or operator_email)

        path = self._key_path(clean_op)
        if not path:
            raise DialerError("State directory is not configured for storing credentials.")

        payload = {
            "api_key": clean_key,
            "user_id": user_id,
            "user_name": display_name,
            "user_email": user_email,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)

        if user_id:
            self.custom_user_ids[clean] = user_id
            self.custom_user_ids[clean_op] = user_id

        return {
            "configured": True,
            "is_custom": True,
            "user_id": user_id,
            "user_name": display_name,
            "user_email": user_email,
            "key_masked": f"api_******{clean_key[-4:]}",
            "updated_at": payload["updated_at"],
        }

    def delete_operator_api_key(self, operator_email: str) -> dict[str, Any]:
        clean = (operator_email or "").strip().lower()
        clean_op = clean_operator_identity(clean) if clean else ""
        if clean_op:
            path = self._key_path(clean_op)
            if path and path.exists():
                path.unlink(missing_ok=True)
            self.custom_user_ids.pop(clean, None)
            self.custom_user_ids.pop(clean_op, None)
        return self.operator_api_key_status(operator_email)

    @property
    def connected(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _phone_items(contact: dict[str, Any]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for item in contact.get("phones") or []:
            if not isinstance(item, dict):
                continue
            phone = str(item.get("phone") or "").strip()
            if not phone:
                continue
            result.append(
                {
                    "phone": phone,
                    "type": str(item.get("type") or "phone").strip() or "phone",
                }
            )
        return result

    @staticmethod
    def _public_smart_view(view: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(view.get("id") or ""),
            "name": str(view.get("name") or "Unnamed Smart View"),
            "type": str(view.get("type") or "lead"),
            "is_shared": bool(view.get("is_shared")),
        }

    @staticmethod
    def _valid_smart_view_id(value: str) -> bool:
        return bool(re.fullmatch(r"save_[A-Za-z0-9]{20,80}", str(value or "")))

    def _smart_views(self, client: httpx.Client) -> list[dict[str, Any]]:
        views: list[dict[str, Any]] = []
        skip = 0
        while skip < 500:
            response = client.get(
                f"{self.base_url}/saved_search/",
                params={"_limit": 100, "_skip": skip, "type__in": "lead,contact"},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise DialerError("Close CRM returned an invalid Smart View list.")
            views.extend(
                item
                for item in rows
                if isinstance(item, dict)
                and self._valid_smart_view_id(str(item.get("id") or ""))
                and item.get("type") in {"lead", "contact"}
            )
            if not payload.get("has_more") or not rows:
                break
            skip += len(rows)
        return views

    def _sort_views(
        self, views: list[dict[str, Any]], operator_email: str = ""
    ) -> list[dict[str, Any]]:
        clean = (operator_email or "").strip().lower()
        if not clean:
            return views

        first = re.split(r"[._+-]", clean.split("@")[0])[0]

        def priority(v: dict[str, Any]) -> tuple[int, str]:
            name = str(v.get("name") or "").lower()
            # A view named after the operator ("Alice's leads") comes first.
            if first and re.search(rf"\b{re.escape(first)}\b", name):
                return (0, name)
            return (1, name)

        return sorted(views, key=priority)

    def smart_views(self, operator_email: str = "") -> dict[str, Any]:
        api_key = self.api_key_for(operator_email)
        if not api_key:
            return {
                "connected": False,
                "source": "close",
                "smart_views": [],
                "fetched_at": datetime.now(UTC).isoformat(),
            }
        try:
            with httpx.Client(
                auth=httpx.BasicAuth(api_key, ""),
                timeout=20,
                transport=self._http_transport(),
                headers={"Accept": "application/json"},
            ) as client:
                views = self._sort_views(self._smart_views(client), operator_email)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DialerError("Close CRM Smart Views are temporarily unavailable.") from exc
        return {
            "connected": True,
            "source": "close",
            "smart_views": [self._public_smart_view(view) for view in views],
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def _search_smart_view(
        self, client: httpx.Client, view: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        saved_query = view.get("s_query")
        if not isinstance(saved_query, dict) or not isinstance(saved_query.get("query"), dict):
            raise DialerError("The selected Close Smart View has no usable saved filter.")
        rows: list[dict[str, Any]] = []
        cursor = ""
        while len(rows) < limit:
            payload = copy.deepcopy(saved_query)
            payload["_limit"] = min(100, limit - len(rows))
            payload["_fields"] = {
                "lead": ["id", "display_name", "name", "status_label", "contacts", "url", "urls", "custom"],
                "contact": ["id", "lead_id", "name", "title", "phones", "urls"],
            }
            if cursor:
                payload["cursor"] = cursor
            response = client.post(f"{self.base_url}/data/search/", json=payload)
            response.raise_for_status()
            result = response.json()
            page = result.get("data") or []
            if not isinstance(page, list):
                raise DialerError("Close CRM returned invalid Smart View results.")
            rows.extend(item for item in page if isinstance(item, dict))
            cursor = str(result.get("cursor") or "")
            if not cursor or not page:
                break
        return rows[:limit]

    def _lead_details(self, client: httpx.Client, lead_ids: list[str]) -> dict[str, dict[str, Any]]:
        details: dict[str, dict[str, Any]] = {}
        unique_ids = list(dict.fromkeys(item for item in lead_ids if item.startswith("lead_")))
        for offset in range(0, len(unique_ids), 40):
            chunk = unique_ids[offset : offset + 40]
            id_queries = [{"type": "id", "value": item} for item in chunk]
            response = client.post(
                f"{self.base_url}/data/search/",
                json={
                    "query": {
                        "type": "and",
                        "queries": [
                            {"type": "object_type", "object_type": "lead"},
                            {"type": "or", "queries": id_queries},
                        ],
                    },
                    "_limit": len(chunk),
                    "_fields": {"lead": ["id", "display_name", "name", "status_label", "url", "urls", "custom"]},
                },
            )
            response.raise_for_status()
            payload = response.json()
            for item in payload.get("data") or []:
                if isinstance(item, dict) and str(item.get("id") or "").startswith("lead_"):
                    details[str(item["id"])] = item
        return details

    def _active_opportunity_lead_ids(
        self, client: httpx.Client, lead_ids: list[str]
    ) -> set[str]:
        """Find leads that have active opportunities."""
        active_leads: set[str] = set()
        unique_ids = list(dict.fromkeys(item for item in lead_ids if item.startswith("lead_")))
        for offset in range(0, len(unique_ids), 40):
            chunk = unique_ids[offset : offset + 40]
            id_queries = [{"type": "lead_id", "value": item} for item in chunk]
            try:
                response = client.post(
                    f"{self.base_url}/data/search/",
                    json={
                        "query": {
                            "type": "and",
                            "queries": [
                                {"type": "object_type", "object_type": "opportunity"},
                                {
                                    "type": "field_condition",
                                    "field": {
                                        "object_type": "opportunity",
                                        "field_name": "status_type",
                                    },
                                    "condition": {"type": "term", "value": "active"},
                                },
                                {"type": "or", "queries": id_queries},
                            ],
                        },
                        "_limit": len(chunk),
                        "_fields": {"opportunity": ["id", "lead_id", "status_type"]},
                    },
                )
                if response.is_success:
                    payload = response.json()
                    for item in payload.get("data") or []:
                        lid = str(item.get("lead_id") or "")
                        if lid:
                            active_leads.add(lid)
            except (httpx.HTTPError, ValueError, TypeError):
                pass
        return active_leads

    def _previously_contacted_lead_ids(
        self, client: httpx.Client, lead_ids: list[str], min_duration_seconds: int = 30
    ) -> set[str]:
        """Find leads that have previous connected calls in Close with duration >= min_duration_seconds."""
        contacted_leads: set[str] = set()
        unique_ids = list(dict.fromkeys(item for item in lead_ids if item.startswith("lead_")))
        for offset in range(0, len(unique_ids), 40):
            chunk = unique_ids[offset : offset + 40]
            id_queries = [{"type": "id", "value": item} for item in chunk]
            try:
                response = client.post(
                    f"{self.base_url}/data/search/",
                    json={
                        "query": {
                            "type": "and",
                            "queries": [
                                {"type": "object_type", "object_type": "lead"},
                                {"type": "or", "queries": id_queries},
                                {
                                    "type": "has_related",
                                    "related_object_type": "activity.call",
                                    "this_object_type": "lead",
                                    "related_query": {
                                        "type": "and",
                                        "queries": [
                                            {
                                                "type": "field_condition",
                                                "field": {
                                                    "type": "regular_field",
                                                    "object_type": "activity.call",
                                                    "field_name": "duration",
                                                },
                                                "condition": {
                                                    "type": "number_range",
                                                    "gte": min_duration_seconds,
                                                },
                                            }
                                        ],
                                    },
                                },
                            ],
                        },
                        "_limit": len(chunk),
                        "_fields": {"lead": ["id"]},
                    },
                )
                if response.is_success:
                    payload = response.json()
                    for item in payload.get("data") or []:
                        lid = str(item.get("id") or "")
                        if lid:
                            contacted_leads.add(lid)
            except (httpx.HTTPError, ValueError, TypeError):
                pass
        return contacted_leads

    def _contact_target(
        self,
        contact: dict[str, Any],
        lead: dict[str, Any],
        active_opportunity_leads: set[str] | None = None,
        previously_contacted_leads: set[str] | None = None,
    ) -> dict[str, Any] | None:
        phone_items = self._phone_items(contact)
        if not phone_items:
            return None
        lead_id = str(contact.get("lead_id") or lead.get("id") or "").strip()
        contact_id = str(contact.get("id") or "").strip()
        if not lead_id.startswith("lead_") or not contact_id.startswith("cont_"):
            return None
        lead_name = str(lead.get("display_name") or lead.get("name") or "Close lead").strip()
        contact_name = str(contact.get("name") or lead_name).strip()
        primary_phone = phone_items[0]

        linkedin_url = ""
        for item in contact.get("urls") or []:
            if isinstance(item, dict):
                u = str(item.get("url") or "").strip()
                if "linkedin.com" in u.lower():
                    linkedin_url = u
                    break
        if not linkedin_url:
            for item in lead.get("urls") or []:
                if isinstance(item, dict):
                    u = str(item.get("url") or "").strip()
                    if "linkedin.com" in u.lower():
                        linkedin_url = u
                        break
        if not linkedin_url and contact.get("url"):
            u = str(contact.get("url") or "").strip()
            if "linkedin.com" in u.lower():
                linkedin_url = u
        if not linkedin_url and lead.get("url"):
            u = str(lead.get("url") or "").strip()
            if "linkedin.com" in u.lower():
                linkedin_url = u

        status_label = str(lead.get("status_label") or "Lead").strip()
        status_clean = status_label.lower()
        has_active_deal = False
        deal_reason = ""
        if active_opportunity_leads and lead_id in active_opportunity_leads:
            has_active_deal = True
            deal_reason = "Active opportunity in Close"
        elif previously_contacted_leads and lead_id in previously_contacted_leads:
            has_active_deal = True
            deal_reason = "Previously contacted (call duration >= 30s in Close)"
        elif any(pattern == status_clean or f" {pattern}" in f" {status_clean} " for pattern in NON_COLD_STATUSES):
            has_active_deal = True
            deal_reason = f"Non-cold status ({status_label})"

        email = ""
        for item in contact.get("emails") or []:
            if isinstance(item, dict) and item.get("email"):
                email = str(item.get("email")).strip()
                break
        if not email and contact.get("email"):
            email = str(contact.get("email")).strip()

        return {
            "contact_id": contact_id,
            "lead_id": lead_id,
            "lead_name": lead_name,
            "name": contact_name,
            "email": email,
            "title": str(contact.get("title") or "").strip(),
            "phone": primary_phone["phone"],
            "phone_type": primary_phone["type"],
            "status": status_label,
            "has_active_deal": has_active_deal,
            "deal_reason": deal_reason,
            "already_contacted": bool(previously_contacted_leads and lead_id in previously_contacted_leads),
            "close_url": f"https://app.close.com/lead/{lead_id}/",
            "linkedin_url": linkedin_url,
            "script_fields": _script_fields(lead),
        }

    def list_age(self, smart_view_id: str = "", operator_email: str = "") -> float | None:
        """Seconds since this operator's list for this view was read from Close."""
        with self._recent_lock:
            entry = self._recent.get((operator_email.strip().lower(), smart_view_id))
        return None if entry is None else time.monotonic() - entry[0]

    def forget_lists(self, operator_email: str = "") -> None:
        """Drop remembered lists: a new Close key means a different Close account."""
        clean = operator_email.strip().lower()
        with self._recent_lock:
            for key in [key for key in self._recent if not clean or key[0] == clean]:
                self._recent.pop(key, None)

    def contacts(
        self,
        limit: int = 5000,
        smart_view_id: str = "",
        operator_email: str = "",
        *,
        max_age: float = 0.0,
    ) -> dict[str, Any]:
        """The contacts in a Smart View, as Close has them.

        max_age > 0 accepts the list this operator last read for this view if it is at
        most that many seconds old and was read with at least this limit. Starting a
        session passes the page's own bound, so it dials exactly the list on the
        operator's screen rather than re-reading Close for another minute.
        """
        safe_limit = max(1, min(int(limit), 10000))
        key = (operator_email.strip().lower(), smart_view_id)
        asked_at = time.monotonic()
        if max_age > 0:
            remembered = self._remembered(key, safe_limit, newer_than=asked_at - max_age)
            if remembered is not None:
                return remembered
        # One read of a list at a time. Overlapping reads split one Close rate limit
        # between them: a Start, the reload after it and a second Start reading the same
        # 1,800 contacts at once took 88 s and 112 s where one read takes 50.
        with self._recent_lock:
            reading = self._reading.setdefault(key, threading.Lock())
        with reading:
            # A read that finished while this one waited is as fresh as a new one.
            remembered = self._remembered(key, safe_limit, newer_than=asked_at)
            if remembered is not None:
                return remembered
            fresh = self._fetch_contacts(safe_limit, smart_view_id, operator_email)
            if fresh.get("connected"):
                self._remember(key, safe_limit, fresh)
        return fresh

    def _remembered(
        self, key: tuple[str, str], safe_limit: int, *, newer_than: float
    ) -> dict[str, Any] | None:
        with self._recent_lock:
            entry = self._recent.get(key)
        if not entry or entry[1] < safe_limit or entry[0] < newer_than:
            return None
        remembered = copy.deepcopy(entry[2])
        remembered["contacts"] = list(remembered.get("contacts") or [])[:safe_limit]
        return remembered

    def _remember(self, key: tuple[str, str], safe_limit: int, fresh: dict[str, Any]) -> None:
        keys = {key}
        # The page asks for "" (the operator's first view) and Start for that view by
        # its id. Filed under "" alone, Start never found the list on screen and read
        # all of Close again, which made Start take 88 s instead of starting at once.
        selected = fresh.get("selected_smart_view")
        if isinstance(selected, dict) and selected.get("id"):
            keys.add((key[0], str(selected["id"])))
        entry = (time.monotonic(), safe_limit, copy.deepcopy(fresh))
        with self._recent_lock:
            for each in keys:
                self._recent[each] = entry

    def invalidate(self, smart_view_id: str = "", operator_email: str = "") -> None:
        """Evict cached contacts so the next read fetches fresh data from Close CRM."""
        clean_op = operator_email.strip().lower()
        with self._recent_lock:
            if clean_op and smart_view_id:
                self._recent.pop((clean_op, smart_view_id), None)
                self._recent.pop((clean_op, ""), None)
            elif clean_op:
                self._recent = {k: v for k, v in self._recent.items() if k[0] != clean_op}
            else:
                self._recent.clear()

    def _fetch_contacts(self, safe_limit: int, smart_view_id: str, operator_email: str) -> dict[str, Any]:
        api_key = self.api_key_for(operator_email)
        if not api_key:
            return {
                "connected": False,
                "source": "close",
                "smart_views": [],
                "selected_smart_view": None,
                "contacts": [],
                "fetched_at": datetime.now(UTC).isoformat(),
            }

        try:
            with httpx.Client(
                auth=httpx.BasicAuth(api_key, ""),
                timeout=20,
                transport=self._http_transport(),
                headers={"Accept": "application/json"},
            ) as client:
                views = self._sort_views(self._smart_views(client), operator_email)
                selected = next(
                    (view for view in views if view.get("id") == smart_view_id),
                    views[0] if views and not smart_view_id else None,
                )
                if selected is None:
                    if smart_view_id:
                        raise DialerError("The selected Close Smart View is unavailable.")
                    contacts: list[dict[str, Any]] = []
                else:
                    rows = self._search_smart_view(client, selected, safe_limit)
                    contact_rows = [item for item in rows if item.get("__object_type") == "contact"]
                    lead_ids = [str(item.get("lead_id") or "") for item in contact_rows]
                    lead_rows = [str(item.get("id") or "") for item in rows if item.get("__object_type") == "lead"]
                    all_lead_ids = list(dict.fromkeys(lead_ids + lead_rows))
                    lead_map = self._lead_details(client, all_lead_ids)
                    active_opp_leads = self._active_opportunity_lead_ids(client, all_lead_ids)
                    contacted_leads = self._previously_contacted_lead_ids(client, all_lead_ids, min_duration_seconds=30)
                    contacts = []
                    for row in rows:
                        if row.get("__object_type") == "contact":
                            lead = lead_map.get(str(row.get("lead_id") or ""), {})
                            target = self._contact_target(row, lead, active_opp_leads, contacted_leads)
                            if target:
                                contacts.append(target)
                        elif row.get("__object_type") == "lead":
                            for contact in row.get("contacts") or []:
                                if not isinstance(contact, dict):
                                    continue
                                contact["lead_id"] = row.get("id")
                                target = self._contact_target(contact, row, active_opp_leads, contacted_leads)
                                if target:
                                    contacts.append(target)
                                if len(contacts) >= safe_limit:
                                    break
                        if len(contacts) >= safe_limit:
                            break
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DialerError("Close CRM is temporarily unavailable.") from exc

        return {
            "connected": True,
            "source": "close",
            "smart_views": [self._public_smart_view(view) for view in views],
            "selected_smart_view": self._public_smart_view(selected) if selected else None,
            "contacts": contacts,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def log_call(
        self,
        *,
        lead_id: str,
        contact_id: str,
        phone: str,
        duration: int,
        note: str,
        user_id: str | None = None,
        operator_email: str = "",
        recording_url: str = "",
    ) -> dict[str, Any]:
        """Log one terminal external-call outcome in Close."""
        api_key = self.api_key_for(operator_email)
        if not api_key:
            raise DialerError("Close CRM is not configured.")
        target_user_id = user_id or self.user_id_for(operator_email)
        payload: dict[str, Any] = {
            "lead_id": lead_id or None,
            "contact_id": contact_id or None,
            "direction": "outbound",
            "duration": max(0, int(duration)),
            "phone": phone,
            "status": "completed",
            "note_html": f"<body><p>{escape(note)}</p></body>",
        }
        if target_user_id:
            payload["user_id"] = target_user_id
        if recording_url:
            payload["recording_url"] = recording_url
        try:
            with httpx.Client(
                auth=httpx.BasicAuth(api_key, ""),
                timeout=15,
                transport=self._http_transport(),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            ) as client:
                response = client.post(f"{self.base_url}/activity/call/", json=payload)
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DialerError("Close CRM could not log the call outcome.") from exc
        if not isinstance(result, dict):
            raise DialerError("Close CRM returned an invalid call activity.")
        return result

    def update_call_recording(
        self,
        call_id: str,
        *,
        recording_url: str,
        duration: int = 0,
        operator_email: str = "",
    ) -> dict[str, Any]:
        """Attach or update audio recording URL and duration on an existing Close call activity."""
        clean_call_id = str(call_id or "").strip()
        if not clean_call_id.startswith("acti_"):
            raise DialerError("Invalid Close call activity identifier.")
        api_key = self.api_key_for(operator_email)
        if not api_key:
            raise DialerError("Close CRM is not configured.")
        payload: dict[str, Any] = {}
        if recording_url:
            payload["recording_url"] = recording_url
        if duration > 0:
            payload["duration"] = int(duration)
        if not payload:
            return {}
        try:
            with httpx.Client(
                auth=httpx.BasicAuth(api_key, ""),
                timeout=15,
                transport=self._http_transport(),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            ) as client:
                response = client.put(f"{self.base_url}/activity/call/{clean_call_id}/", json=payload)
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DialerError("Close CRM could not update the call recording.") from exc
        if not isinstance(result, dict):
            raise DialerError("Close CRM returned an invalid call activity.")
        return result

    def update_lead_status(
        self,
        lead_id: str,
        status_label: str,
        operator_email: str = "",
    ) -> dict[str, Any]:
        """Update lead status in Close CRM (e.g. 'Not Interested')."""
        clean_lead_id = str(lead_id or "").strip()
        if not clean_lead_id.startswith("lead_"):
            raise DialerError("Invalid Close lead identifier.")
        api_key = self.api_key_for(operator_email)
        if not api_key:
            raise DialerError("Close CRM is not configured.")
        payload = {"status_label": str(status_label or "").strip()}
        try:
            with httpx.Client(
                auth=httpx.BasicAuth(api_key, ""),
                timeout=15,
                transport=self._http_transport(),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            ) as client:
                response = client.put(f"{self.base_url}/lead/{clean_lead_id}/", json=payload)
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DialerError(f"Close CRM could not update lead status: {exc}") from exc
        if not isinstance(result, dict):
            raise DialerError("Close CRM returned invalid lead response.")
        return result

    def call_notes(
        self,
        *,
        contact_id: str = "",
        lead_id: str = "",
        phone: str = "",
        limit: int = 5,
        operator_email: str = "",
    ) -> dict[str, Any]:
        """Fetch previous call activities and notes for a contact or lead from Close."""
        clean_cid = str(contact_id or "").strip()
        clean_lid = str(lead_id or "").strip()
        clean_phone = str(phone or "").strip()
        api_key = self.api_key_for(operator_email)
        if not api_key:
            return {
                "ok": True,
                "has_called_before": False,
                "total_calls": 0,
                "call_notes": [],
            }

        safe_limit = max(1, min(int(limit), 20))
        raw_calls: list[dict[str, Any]] = []

        try:
            with httpx.Client(
                auth=httpx.BasicAuth(api_key, ""),
                timeout=15,
                transport=self._http_transport(),
                headers={"Accept": "application/json"},
            ) as client:
                # 1. Query by contact_id if valid
                if clean_cid.startswith("cont_"):
                    response = client.get(
                        f"{self.base_url}/activity/call/",
                        params={"contact_id": clean_cid, "_limit": safe_limit},
                    )
                    if response.is_success:
                        payload = response.json()
                        rows = payload.get("data") if isinstance(payload, dict) else []
                        if isinstance(rows, list):
                            raw_calls.extend(item for item in rows if isinstance(item, dict))

                # 2. If no calls found for contact_id, try by lead_id
                if not raw_calls and clean_lid.startswith("lead_"):
                    response = client.get(
                        f"{self.base_url}/activity/call/",
                        params={"lead_id": clean_lid, "_limit": safe_limit},
                    )
                    if response.is_success:
                        payload = response.json()
                        rows = payload.get("data") if isinstance(payload, dict) else []
                        if isinstance(rows, list):
                            matching = []
                            for item in rows:
                                if not isinstance(item, dict):
                                    continue
                                c_id = str(item.get("contact_id") or "")
                                c_phone = str(item.get("phone") or "")
                                if (clean_cid and c_id == clean_cid) or (clean_phone and clean_phone in c_phone):
                                    matching.append(item)
                            raw_calls.extend(matching if matching else [it for it in rows if isinstance(it, dict)])

        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DialerError("Could not retrieve previous call notes from Close CRM.") from exc

        formatted_notes: list[dict[str, Any]] = []
        for call in raw_calls[:safe_limit]:
            note_text = str(call.get("note") or "").strip()
            if not note_text and call.get("note_html"):
                note_text = re.sub(r"<[^>]+>", " ", str(call["note_html"])).strip()
                note_text = " ".join(note_text.split())

            duration_secs = int(call.get("duration") or 0)
            mins = duration_secs // 60
            secs = duration_secs % 60
            if mins > 0:
                duration_str = f"{mins}m {secs}s" if secs > 0 else f"{mins}m"
            elif duration_secs > 0:
                duration_str = f"{secs}s"
            else:
                duration_str = ""

            created_iso = str(call.get("date_created") or call.get("activity_at") or "")
            formatted_date = ""
            relative_date = ""
            if created_iso:
                try:
                    dt = datetime.fromisoformat(created_iso)
                    formatted_date = dt.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")
                    now = datetime.now(UTC)
                    diff_days = (now.date() - dt.date()).days
                    if diff_days == 0:
                        relative_date = "Today"
                    elif diff_days == 1:
                        relative_date = "Yesterday"
                    elif diff_days < 7:
                        relative_date = f"{diff_days} days ago"
                    else:
                        relative_date = dt.strftime("%b %d")
                except (ValueError, TypeError):
                    formatted_date = created_iso[:16]

            formatted_notes.append({
                "id": str(call.get("id") or ""),
                "date": created_iso,
                "date_formatted": formatted_date,
                "relative_date": relative_date,
                "duration": duration_secs,
                "duration_formatted": duration_str,
                "user_name": str(call.get("user_name") or call.get("created_by_name") or ""),
                "direction": str(call.get("direction") or "outbound"),
                "status": str(call.get("status") or ""),
                "note": note_text or "Call completed (no notes recorded)",
                "source": "close",
            })

        return {
            "ok": True,
            "has_called_before": len(formatted_notes) > 0,
            "total_calls": len(formatted_notes),
            "call_notes": formatted_notes,
        }




# Close lead custom fields shown in the talk track, by Close field name -> slot key.
SCRIPT_FIELDS = {
    "their product": "their_product",
    "product type": "product_type",
    "competitor product": "competitor_product",
    "competitor brand": "competitor_brand",
    "call flag": "flag",
    "opener": "opener",
}


def _script_fields(lead: dict[str, Any]) -> dict[str, str]:
    custom = lead.get("custom") if isinstance(lead, dict) else None
    if not isinstance(custom, dict):
        return {}
    out: dict[str, str] = {}
    for name, value in custom.items():
        key = SCRIPT_FIELDS.get(str(name).strip().lower())
        if key and value not in (None, ""):
            out[key] = str(value).strip()[:400]
    return out
