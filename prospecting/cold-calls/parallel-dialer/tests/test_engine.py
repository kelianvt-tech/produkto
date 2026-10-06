"""Tests for the dialer engine: sessions, dialing, the screening classifier, recordings,
numbers, callbacks and the Close and Twilio clients, all against in-memory fakes of Twilio
and Close."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from collections.abc import Callable
from urllib.parse import parse_qs
from xml.etree import ElementTree

import httpx
import pytest

from parallel_dialer.auth import access_key
from parallel_dialer.config import Settings
from parallel_dialer.profile import Profile

# A deployment that has said what it is called: without a brand the dialer stays locked.
PROFILE = Profile(brand="Acme", brand_is_set=True)
ALLOWED = frozenset({"alice@example.com", "bob@example.com"})
# The signing secret the HTTP tests start the service with, and the access key it yields.
SIGNING_SECRET = "test-signing-secret-0123456789"
ACCESS_KEY = access_key(SIGNING_SECRET, "alice@example.com")
from parallel_dialer.dialer import CloseDialer, DialerError
from parallel_dialer.live_dialer import (
    DialAttempt,
    LiveDialer,
    LiveDialerError,
    audio_duration_seconds,
    is_toll_free_number,
    mask_phone,
    normalize_phone,
    validate_phone_number,
)


def _sid(prefix: str, number: int) -> str:
    return prefix + f"{number:032x}"


class ProviderHarness:
    def __init__(self) -> None:
        self.smart_views = [
            {
                "id": "save_" + "a" * 32,
                "name": "Alice Top 100 ICP v1",
                "type": "contact",
                "is_shared": True,
                "s_query": {
                    "query": {
                        "type": "field_condition",
                        "field": {
                            "field_name": "name",
                            "object_type": "contact",
                            "condition": {"type": "text", "mode": "full_words", "value": "Demo"},
                        },
                    },
                    "sort": [
                        {
                            "field": {"field_name": "name", "object_type": "contact"},
                            "direction": "asc",
                        }
                    ],
                },
            }
        ]
        self.contacts = [
            {
                "contact_id": "cont_1",
                "lead_id": "lead_1",
                "name": "Alex Demo",
                "lead_name": "Demo One",
                "phone": "+12025550148",
            },
            {
                "contact_id": "cont_2",
                "lead_id": "lead_2",
                "name": "Blair Demo",
                "lead_name": "Demo Two",
                "phone": "+12025550149",
            },
            {
                "contact_id": "cont_3",
                "lead_id": "lead_3",
                "name": "Casey Demo",
                "lead_name": "Demo Three",
                "phone": "+12025550150",
            },
        ]
        self.requests: list[httpx.Request] = []
        self.close_posts: list[dict] = []
        self.close_puts: list[dict] = []
        self.close_call_activities: list[dict] = []
        self.openrouter_payloads: list[dict] = []
        self.openrouter_result: dict = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"kind": "human", "reason": "greeting"})
                    }
                }
            ]
        }
        self.openai_payloads: list[dict] = []
        self.openai_result: dict = {
            "output_text": json.dumps(
                {"kind": "unknown", "reply": "Please say hello if you are there."}
            )
        }
        self.typesafe_payloads: list[dict] = []
        self.typesafe_result: dict = {
            "model": "jev-latest",
            "answers": {
                "kind": {
                    "type": "choice",
                    "choice": "human",
                    "confidence": 0.98,
                }
            },
        }
        self.cloudflare_payloads: list[dict] = []
        self.cloudflare_result: dict = {
            "result": {
                "model": "jev-latest",
                "answers": {
                    "kind": {
                        "type": "choice",
                        "choice": "human",
                        "confidence": 0.98,
                    }
                },
            },
            "success": True,
        }
        self.fail_create_numbers: set[str] = set()
        self.fail_updates = False
        self.call_statuses: dict[str, dict] = {}
        self.created_calls: list[dict[str, str]] = []
        self.number_updates: list[dict[str, str]] = []
        self.active_opportunities: list[dict] = []
        self.previously_contacted_leads: list[dict] = []

    def close_contact_rows(self) -> list[dict]:
        return [
            {
                "__object_type": "contact",
                "id": item["contact_id"],
                "lead_id": item["lead_id"],
                "name": item["name"],
                "title": "Director",
                "phones": [{"phone": item["phone"], "type": "mobile"}],
            }
            for item in self.contacts
        ]

    def close_lead_rows(self) -> list[dict]:
        return [
            {
                "__object_type": "lead",
                "id": item["lead_id"],
                "display_name": item["lead_name"],
                "status_label": "Qualified",
            }
            for item in self.contacts
        ]

    @staticmethod
    def _is_call_hydration(payload: dict) -> bool:
        query = payload.get("query") or {}
        return any(
            item.get("type") == "has_related" and item.get("related_object_type") == "activity.call"
            for item in query.get("queries") or []
            if isinstance(item, dict)
        )

    @staticmethod
    def _is_lead_hydration(payload: dict) -> bool:
        query = payload.get("query") or {}
        return any(
            item.get("type") == "object_type" and item.get("object_type") == "lead"
            for item in query.get("queries") or []
            if isinstance(item, dict)
        )

    @staticmethod
    def _is_opportunity_hydration(payload: dict) -> bool:
        query = payload.get("query") or {}
        return any(
            item.get("type") == "object_type" and item.get("object_type") == "opportunity"
            for item in query.get("queries") or []
            if isinstance(item, dict)
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "api.close.com" and request.method == "GET":
            if request.url.path.endswith("/saved_search/"):
                return httpx.Response(200, json={"data": self.smart_views, "has_more": False})
            if "/activity/call/" in request.url.path:
                cid = request.url.params.get("contact_id")
                lid = request.url.params.get("lead_id")
                filtered = [
                    c for c in self.close_call_activities
                    if (not cid or c.get("contact_id") == cid) and (not lid or c.get("lead_id") == lid)
                ]
                return httpx.Response(200, json={"data": filtered, "has_more": False})
            raise AssertionError(f"Unexpected Close GET: {request.url}")
        if request.url.host == "api.close.com" and request.method == "POST":
            payload = json.loads(request.content)
            if request.url.path.endswith("/data/search/"):
                if self._is_opportunity_hydration(payload):
                    return httpx.Response(200, json={"data": self.active_opportunities, "cursor": ""})
                if self._is_call_hydration(payload):
                    return httpx.Response(200, json={"data": self.previously_contacted_leads, "cursor": ""})
                rows = (
                    self.close_lead_rows()
                    if self._is_lead_hydration(payload)
                    else self.close_contact_rows()
                )
                limit = int(payload.get("_limit") or len(rows))
                return httpx.Response(200, json={"data": rows[:limit], "cursor": ""})
            if request.url.path.endswith("/activity/call/"):
                self.close_posts.append(payload)
                return httpx.Response(200, json={"id": _sid("acti_", len(self.close_posts))})
            raise AssertionError(f"Unexpected Close POST: {request.url}")
        if request.url.host == "api.close.com" and request.method == "PUT":
            payload = json.loads(request.content)
            if "/activity/call/" in request.url.path:
                self.close_puts.append(payload)
                call_id = request.url.path.strip("/").split("/")[-1]
                return httpx.Response(200, json={"id": call_id, **payload})
            if "/lead/" in request.url.path:
                self.close_puts.append(payload)
                lead_id = request.url.path.strip("/").split("/")[-1]
                return httpx.Response(200, json={"id": lead_id, **payload})
            raise AssertionError(f"Unexpected Close PUT: {request.url}")
        if request.url.host == "openrouter.ai":
            self.openrouter_payloads.append(json.loads(request.content))
            return httpx.Response(200, json=self.openrouter_result)
        if request.url.host == "api.openai.com":
            self.openai_payloads.append(json.loads(request.content))
            return httpx.Response(200, json=self.openai_result)
        if request.url.host == "api.typesafe.ai":
            self.typesafe_payloads.append(json.loads(request.content))
            return httpx.Response(200, json=self.typesafe_result)
        if request.url.host == "api.cloudflare.com":
            self.cloudflare_payloads.append(json.loads(request.content))
            return httpx.Response(200, json=self.cloudflare_result)
        if request.url.host != "api.twilio.com":
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        if request.method == "GET" and "/Recordings/" in request.url.path:
            return httpx.Response(
                200,
                content=b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x00fake-recording-data",
                headers={"Content-Type": "audio/mpeg"},
            )

        if request.method == "GET" and request.url.path.endswith("/IncomingPhoneNumbers.json"):
            return httpx.Response(
                200,
                json={
                    "incoming_phone_numbers": [
                        {
                            "sid": _sid("PN", 1),
                            "phone_number": "+12025550100",
                        }
                    ]
                },
            )
        if request.method == "GET" and "/AvailablePhoneNumbers/US/Local.json" in request.url.path:
            self.available_count = getattr(self, "available_count", 0) + 1
            num = f"+1816555019{self.available_count}"
            return httpx.Response(
                200,
                json={
                    "available_phone_numbers": [
                        {
                            "phone_number": num,
                            "friendly_name": f"(816) 555-019{self.available_count}",
                            "locality": "Kansas City",
                            "region": "MO",
                        }
                    ]
                },
            )

        if request.method == "POST" and request.url.path.endswith("/IncomingPhoneNumbers.json"):
            form = {key: values[0] for key, values in parse_qs(request.content.decode("utf-8")).items()}
            return httpx.Response(
                201,
                json={
                    "sid": _sid("PN_bought_", len(self.number_updates) + 1),
                    "phone_number": form.get("PhoneNumber", "+18165550199"),
                    "friendly_name": form.get("FriendlyName", "Acme Purchased Line"),
                    "locality": "Kansas City",
                    "region": "MO",
                },
            )

        if request.method == "DELETE" and "/IncomingPhoneNumbers/" in request.url.path:
            return httpx.Response(204)

        if request.method == "GET" and re.search(r"/Accounts/AC[a-zA-Z0-9]+\.json", request.url.path):
            return httpx.Response(200, json={"status": "active", "friendly_name": "Acme Twilio Account"})

        if request.method == "POST" and "/IncomingPhoneNumbers/PN" in request.url.path:
            form = {key: values[0] for key, values in parse_qs(request.content.decode("utf-8")).items()}
            self.number_updates.append(form)
            return httpx.Response(200, json={"sid": _sid("PN", 1), **form})

        if request.method == "POST" and request.url.path.endswith("/Calls.json"):
            form = parse_qs(request.content.decode("utf-8"))
            destination = form["To"][0]
            if destination in self.fail_create_numbers:
                return httpx.Response(400, json={"code": 21217, "message": "invalid"})
            call_sid = _sid("CA", len(self.created_calls) + 1)
            self.created_calls.append({"sid": call_sid, "to": destination})
            self.call_statuses[call_sid] = {"status": "queued", "duration": "0"}
            return httpx.Response(201, json={"sid": call_sid, "status": "queued"})
        call_sid = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        if request.method == "POST":
            if self.fail_updates:
                return httpx.Response(503, json={"message": "temporary failure"})
            self.call_statuses[call_sid] = {"status": "completed", "duration": "0"}
            return httpx.Response(200, json={"sid": call_sid, "status": "completed"})
        if request.method == "GET":
            payload = self.call_statuses.get(call_sid, {"status": "completed", "duration": "0"})
            return httpx.Response(200, json={"sid": call_sid, **payload})
        raise AssertionError(f"Unexpected Twilio request: {request.method} {request.url}")


def configure(
    monkeypatch,
    *,
    allowed: str = "+12025550148,+12025550149,+12025550150,+12025550199",
    operator: str = "+12025550199",
    callback: str = "",
    live_mode: str = "enabled",
) -> None:
    values = {
        "TWILIO_ACCOUNT_SID": "AC" + "a" * 32,
        "TWILIO_API_KEY_SID": "SK" + "b" * 32,
        "TWILIO_API_KEY_SECRET": "secret-value-for-tests-123456",
        "TWILIO_PHONE_NUMBER": "+12025550100",
        "OPENAI_API_KEY": "openai-test-key",
        "DIALER_WEBHOOK_TOKEN": "webhook-secret-for-tests-123456789",
        "DIALER_LIVE_MODE": live_mode,
        "DIALER_ALLOWED_TEST_NUMBERS": allowed,
        "DIALER_OPERATOR_NUMBER": operator,
        "DIALER_CALLBACK_NUMBER": callback,
        "TYPESAFE_API_KEY": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def make_dialer(tmp_path, monkeypatch, harness: ProviderHarness) -> LiveDialer:
    configure(monkeypatch)
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    dialer = LiveDialer(
        Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE),
        close,
        transport=httpx.MockTransport(harness.handler),
    )
    dialer.save_voicemail_recording(
        filename="test-voicemail.mp3",
        content_type="audio/mpeg",
        data_base64=base64.b64encode(b"ID3" + b"\0" * 2048).decode("ascii"),
    )
    return dialer


def start(
    dialer: LiveDialer,
    harness: ProviderHarness,
    count: int = 1,
    concurrency: int | None = None,
    reply: str = "Hi, this is Acme's AI-assisted demo calling about the approved test.",
    operator_target: str = "phone",
    operator_email: str = "",
) -> dict:
    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=count,
            concurrency=concurrency or count,
            screening_reply=reply,
            operator_target=operator_target,
            operator_email=operator_email,
        )
    )
    operator_sid = dialer.sessions[session["id"]].operator_call_sid
    asyncio.run(
        dialer.handle_session_operator_answer(
            session["id"], {"CallSid": operator_sid}
        )
    )
    return dialer.session(session["id"])


def attempt_for(dialer: LiveDialer, session: dict, index: int = 0):
    return dialer.attempts[session["attempts"][index]["id"]]


def lead_destinations(harness: ProviderHarness) -> list[str]:
    return [item["to"] for item in harness.created_calls if item["to"] != "+12025550199"]


def assert_raises_message(error: type[Exception], text: str, call: Callable[[], object]) -> None:
    with pytest.raises(error, match=text):
        call()


def test_close_smart_view_contacts_preserve_saved_order_and_cursor() -> None:
    smart_view_id = "save_" + "z" * 32
    search_pages = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal search_pages
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "has_more": False,
                    "data": [
                        {
                            "id": smart_view_id,
                            "name": "Pinned contacts",
                            "type": "contact",
                            "s_query": {"query": {"type": "and", "queries": []}},
                        }
                    ],
                },
            )
        payload = json.loads(request.content)
        if ProviderHarness._is_opportunity_hydration(payload):
            return httpx.Response(200, json={"data": []})
        if ProviderHarness._is_call_hydration(payload):
            return httpx.Response(200, json={"data": []})
        if ProviderHarness._is_lead_hydration(payload):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "__object_type": "lead",
                            "id": f"lead_{number}",
                            "display_name": f"Company {number}",
                            "status_label": "Qualified",
                        }
                        for number in range(2)
                    ]
                },
            )
        cursor = str(payload.get("cursor") or "")
        search_pages += 1
        number = 1 if cursor else 0
        return httpx.Response(
            200,
            json={
                "cursor": "next-page" if not cursor else "",
                "data": [
                    {
                        "__object_type": "contact",
                        "id": f"cont_{number}",
                        "lead_id": f"lead_{number}",
                        "name": f"Contact {number}",
                        "title": "Director",
                        "phones": [{"phone": f"+1202555014{number}", "type": "office"}],
                    }
                ],
            },
        )

    dialer = CloseDialer(transport=httpx.MockTransport(handler))
    dialer.api_key = "test-key"
    payload = dialer.contacts(limit=2, smart_view_id=smart_view_id)
    assert payload["connected"] is True
    assert payload["selected_smart_view"]["id"] == smart_view_id
    assert [item["name"] for item in payload["contacts"]] == ["Contact 0", "Contact 1"]
    assert len(payload["contacts"]) == 2
    assert search_pages == 2


def test_close_missing_credential_and_invalid_payload_are_safe() -> None:
    dialer = CloseDialer()
    dialer.api_key = ""
    assert dialer.contacts()["contacts"] == []

    broken = CloseDialer(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": {"unexpected": True}})
        )
    )
    broken.api_key = "test-key"
    with pytest.raises(DialerError, match="invalid"):
        broken.contacts()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+1 (202) 555-0148", "+12025550148"),
        ("0012025550148", "+12025550148"),
        ("202-555-0148", ""),
        ("+123", ""),
        ("+1234567890123456", ""),
    ],
)
def test_phone_normalization_and_masking(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected
    if expected:
        assert mask_phone(raw).endswith(expected[-4:])


def test_readiness_and_contact_decoration(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    configure(monkeypatch, allowed="", operator="", live_mode="disabled")
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    dialer = LiveDialer(
        Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE),
        close,
        transport=httpx.MockTransport(harness.handler),
    )
    assert dialer.ready is False
    # A missing voicemail message is deliberately not among them: it silences the drop
    # rather than stopping the dialer. Nor is a missing operator number, because the
    # browser can take that leg without one.
    assert len(dialer.blockers()) == 2

    configure(monkeypatch)
    ready = make_dialer(tmp_path / "ready", monkeypatch, harness)
    payload = ready.decorate_contacts({"contacts": harness.contacts.copy()})
    assert ready.ready is True
    assert all(item["live_allowed"] for item in payload["contacts"])


def test_start_call_contract_and_silent_first_listen(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    create_request = next(
        item
        for item in harness.requests
        if item.url.path.endswith("/Calls.json")
        and "MachineDetection" in parse_qs(item.content.decode("utf-8"))
    )
    form = parse_qs(create_request.content.decode("utf-8"))
    assert form["MachineDetection"] == ["DetectMessageEnd"]
    assert form["AsyncAmd"] == ["true"]
    assert form["StatusCallbackEvent"] == ["initiated", "ringing", "answered", "completed"]
    assert "#rc=2" in form["StatusCallback"][0]

    twiml = dialer.answer_twiml(attempt.id)
    root = ElementTree.fromstring(twiml)
    gather = root.find("Gather")
    assert gather is not None
    assert gather.attrib["timeout"] == "5"
    assert gather.find("Say") is None


def test_create_response_does_not_regress_an_early_status_callback(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    call_sid = attempt.twilio_call_sid
    attempt.status = "in-progress"
    attempt.twilio_status = "in-progress"

    async def delayed_create_response(*_args, **_kwargs):
        return {"sid": call_sid, "status": "queued"}

    monkeypatch.setattr(dialer, "_twilio_post", delayed_create_response)
    asyncio.run(dialer._create_call(attempt))

    assert attempt.status == "in-progress"
    assert attempt.twilio_status == "in-progress"


def test_screening_reply_is_escaped_and_loop_is_bounded(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    approved = "Acme & partners: this is an AI-assisted <product> demonstration."
    session = start(dialer, harness, reply=approved)
    attempt = attempt_for(dialer, session)
    dialer.answer_twiml(attempt.id)
    for number in range(1, 5):
        twiml = asyncio.run(
            dialer.handle_speech(
                attempt.id,
                {
                    "CallSid": attempt.twilio_call_sid,
                    "SpeechResult": "Please state the reason for your call",
                    "_IdempotencyToken": f"screen-{number}",
                },
            )
        )
    assert attempt.turns == 4
    assert attempt.outcome == "unclassified"
    assert ElementTree.fromstring(twiml).find("Hangup") is not None


def test_voicemail_is_discarded_without_operator_dial(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Please leave a message after the tone",
            },
        )
    )
    assert attempt.outcome == "voicemail"
    assert "<Dial" not in twiml
    assert "<Hangup" in twiml


def test_human_detection_cancels_competitors_and_builds_tracked_bridge(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3)
    winner = attempt_for(dialer, session)
    twiml = asyncio.run(
        dialer.handle_speech(
            winner.id,
            {
                "CallSid": winner.twilio_call_sid,
                "SpeechResult": "Hello, this is Alex speaking",
                "_IdempotencyToken": "human-one",
            },
        )
    )
    root = ElementTree.fromstring(twiml)
    dial = root.find("Dial")
    conference = dial.find("Conference") if dial is not None else None
    assert dial is not None and "/bridge?" in dial.attrib["action"]
    assert conference is not None and conference.text == dialer.sessions[session["id"]].conference_name
    assert root.find("Say") is None
    assert winner.outcome == "human-bridged"
    assert winner.status == "bridged"
    competitors = [attempt_for(dialer, session, index) for index in (1, 2)]
    assert all(item.outcome == "canceled-after-human" for item in competitors)
    assert len([item for item in harness.requests if item.method == "POST"]) >= 3

    duplicate = asyncio.run(
        dialer.handle_speech(
            winner.id,
            {
                "CallSid": winner.twilio_call_sid,
                "SpeechResult": "Hello, this is Alex speaking",
                "_IdempotencyToken": "human-one",
            },
        )
    )
    assert duplicate == twiml
    assert winner.turns == 1


def test_simultaneous_humans_elect_exactly_one_operator_handoff(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=2)
    attempts = [attempt_for(dialer, session, index) for index in (0, 1)]

    async def race() -> list[str]:
        return list(
            await asyncio.gather(
                *(
                    dialer.handle_speech(
                        attempt.id,
                        {
                            "CallSid": attempt.twilio_call_sid,
                            "SpeechResult": "Hello, this is the person speaking",
                            "_IdempotencyToken": f"race-{index}",
                        },
                    )
                    for index, attempt in enumerate(attempts)
                )
            )
        )

    twimls = asyncio.run(race())
    assert sum(ElementTree.fromstring(twiml).find("Dial/Conference") is not None for twiml in twimls) == 1
    assert sum(attempt.human_detected for attempt in attempts) == 1
    assert sum(attempt.outcome == "human-bridged" for attempt in attempts) == 1
    assert sum(attempt.outcome == "dropped-line" for attempt in attempts) == 1


def test_consecutive_humans_in_same_session_both_get_bridged(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=2, concurrency=1)
    attempt_one = attempt_for(dialer, session, 0)

    # First attempt answers human and connects
    twiml_one = asyncio.run(
        dialer.handle_speech(
            attempt_one.id,
            {
                "CallSid": attempt_one.twilio_call_sid,
                "SpeechResult": "Hello, this is the first human",
                "_IdempotencyToken": "human-first",
            },
        )
    )
    assert ElementTree.fromstring(twiml_one).find("Dial/Conference") is not None
    assert attempt_one.outcome == "human-bridged"
    assert attempt_one.status == "bridged"

    # Operator completes active call, advancing queue to next attempt
    updated_session = asyncio.run(dialer.complete_active_call(session["id"]))
    assert attempt_one.status == "completed"

    # Second attempt now dialed and answers human in the same session
    attempt_two = attempt_for(dialer, updated_session, 1)
    twiml_two = asyncio.run(
        dialer.handle_speech(
            attempt_two.id,
            {
                "CallSid": attempt_two.twilio_call_sid,
                "SpeechResult": "Hello, this is the second human",
                "_IdempotencyToken": "human-second",
            },
        )
    )
    root_two = ElementTree.fromstring(twiml_two)
    assert root_two.find("Dial/Conference") is not None
    assert attempt_two.outcome == "human-bridged"
    assert attempt_two.status == "bridged"

    # Verify complete_active_call is idempotent and completes session when queue finishes
    updated_session2 = asyncio.run(dialer.complete_active_call(session["id"]))
    assert updated_session2["status"] == "completed"
    # Even when human_attempt_id is empty and session is complete, it succeeds cleanly
    updated_session3 = asyncio.run(dialer.complete_active_call(session["id"]))
    assert updated_session3["status"] == "completed"



def test_concurrent_webhook_retry_reuses_one_speech_result(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    params = {
        "CallSid": attempt.twilio_call_sid,
        "SpeechResult": "Hello, this is the person speaking",
        "_IdempotencyToken": "same-delivery-token",
    }

    async def duplicate() -> list[str]:
        return list(
            await asyncio.gather(*(dialer.handle_speech(attempt.id, params) for _ in range(2)))
        )

    first, second = asyncio.run(duplicate())
    assert first == second
    assert "<Dial" in first
    assert attempt.turns == 1


def test_another_speech_callback_for_a_call_already_put_through_gets_an_empty_response(tmp_path, monkeypatch) -> None:
    # Twilio can deliver a further speech result for a call that is already bridged. It has to
    # be answered with "nothing to do", not with an error: a failed webhook makes Twilio say
    # "an application error has occurred" and hang up a conversation that is under way.
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    def speech(token: str, words: str) -> str:
        return asyncio.run(
            dialer.handle_speech(
                attempt.id,
                {"CallSid": attempt.twilio_call_sid, "SpeechResult": words, "_IdempotencyToken": token},
            )
        )

    assert "<Dial" in speech("delivery-1", "Hello, this is the person speaking")
    again = speech("delivery-2", "Hello? Are you still there?")
    root = ElementTree.fromstring(again)
    assert root.tag == "Response" and len(root) == 0
    # A retry of that same delivery is answered the same way.
    assert speech("delivery-2", "Hello? Are you still there?") == again


def test_operator_callbacks_distinguish_detection_from_bridge(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Hello"},
        )
    )
    child_sid = _sid("CA", 99)
    dialer.handle_operator_status(
        attempt.id,
        {
            "ParentCallSid": attempt.twilio_call_sid,
            "CallSid": child_sid,
            "CallStatus": "in-progress",
            "SequenceNumber": "2",
        },
    )
    assert attempt.status == "bridged"
    assert attempt.outcome == "human-bridged"
    assert dialer.session(session["id"])["status"] == "human-connected"

    dialer.handle_operator_status(
        attempt.id,
        {
            "ParentCallSid": attempt.twilio_call_sid,
            "CallSid": child_sid,
            "CallStatus": "ringing",
            "SequenceNumber": "1",
        },
    )
    assert attempt.status == "bridged"

    result = dialer.handle_bridge_result(
        attempt.id,
        {
            "CallSid": attempt.twilio_call_sid,
            "DialCallStatus": "completed",
            "DialCallDuration": "14",
        },
    )
    assert "<Hangup" in result
    assert attempt.bridge_duration == 14
    assert dialer.session(session["id"])["status"] == "completed"


def test_operator_no_answer_and_mismatched_parent_are_reported(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Hello"},
        )
    )
    with pytest.raises(LiveDialerError, match="parent"):
        dialer.handle_operator_status(
            attempt.id,
            {
                "ParentCallSid": _sid("CA", 999),
                "CallSid": _sid("CA", 100),
                "CallStatus": "no-answer",
            },
        )
    dialer.handle_operator_status(
        attempt.id,
        {
            "ParentCallSid": attempt.twilio_call_sid,
            "CallSid": _sid("CA", 100),
            "CallStatus": "no-answer",
        },
    )
    dialer.handle_bridge_result(
        attempt.id,
        {"CallSid": attempt.twilio_call_sid, "DialCallStatus": "no-answer"},
    )
    assert attempt.outcome == "operator-no-answer"


def test_ai_classifier_uses_structured_output_and_fails_closed(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    harness.openai_result = {
        "output_text": json.dumps(
            {
                "kind": "human",
                "reply": "This is AI-assisted; I will connect you with Marco.",
            }
        )
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(attempt, "I am available to discuss the test")
    )
    assert kind == "human"
    assert reply == ""
    payload = harness.openai_payloads[-1]
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True

    harness.openai_result = {"output_text": "not json"}
    kind, _ = asyncio.run(dialer._classify_transcript(attempt, "Ambiguous audio"))
    assert kind == "unknown"


def test_ai_classifier_fails_closed_on_http_error(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    # Force OpenAI endpoint to fail with 401 Unauthorized
    harness.openai_result = {}
    original_handler = harness.handler

    def handler_with_401(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openai.com":
            return httpx.Response(401, json={"error": {"message": "Invalid API key"}})
        return original_handler(request)

    harness.handler = handler_with_401
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(dialer._classify_transcript(attempt, "Ambiguous carrier audio"))
    assert kind == "unknown"
    assert reply == ""


def test_typesafe_jev_classification_success(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    harness.typesafe_result = {
        "model": "jev-latest",
        "answers": {
            "kind": {
                "type": "choice",
                "choice": "human",
                "confidence": 0.99,
            }
        },
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.typesafe_api_key = "test-typesafe-key"
    dialer.typesafe_model = "jev-latest"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(attempt, "I am available to discuss the test")
    )
    assert kind == "human"
    assert reply == ""
    # TypeSafe was called, OpenAI and Cloudflare were NOT called
    assert len(harness.typesafe_payloads) == 1
    assert len(harness.cloudflare_payloads) == 0
    assert len(harness.openai_payloads) == 0
    ts_payload = harness.typesafe_payloads[0]
    assert ts_payload["model"] == "jev-latest"
    assert "questions" in ts_payload
    assert ts_payload["questions"]["kind"]["type"] == "choice"


def test_typesafe_jev_screening_reply(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    harness.typesafe_result = {
        "model": "jev-latest",
        "answers": {
            "kind": {
                "type": "choice",
                "choice": "screening",
                "confidence": 0.95,
            }
        },
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.typesafe_api_key = "test-typesafe-key"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(
            attempt, "Could you clarify your organization and inquiry details before I connect you?"
        )
    )
    assert kind == "screening"
    assert reply == attempt.screening_reply
    assert len(harness.typesafe_payloads) == 1
    assert len(harness.openai_payloads) == 0


def test_typesafe_jev_falls_back_to_openai_on_error(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    original_handler = harness.handler

    def handler_with_ts_error(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.typesafe.ai":
            harness.typesafe_payloads.append(json.loads(request.content))
            return httpx.Response(500, json={"error": "TypeSafe internal server error"})
        return original_handler(request)

    harness.handler = handler_with_ts_error
    harness.openai_result = {
        "output_text": json.dumps({"kind": "voicemail"})
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.typesafe_api_key = "test-typesafe-key"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(
            attempt, "An automated archive system is recording this channel."
        )
    )
    assert kind == "voicemail"
    assert reply == ""
    assert len(harness.typesafe_payloads) == 1
    assert len(harness.openai_payloads) == 1


def test_cloudflare_jev_classification_success(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    harness.cloudflare_result = {
        "result": {
            "model": "jev-latest",
            "answers": {
                "kind": {
                    "type": "choice",
                    "choice": "human",
                    "confidence": 0.99,
                }
            },
        },
        "success": True,
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.cloudflare_account_id = "test-account-id"
    dialer.cloudflare_api_token = "test-api-token"
    dialer.cloudflare_ai_model = "typesafe/jev"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(attempt, "I am available to discuss the test")
    )
    assert kind == "human"
    assert reply == ""
    # Cloudflare was called, OpenAI was NOT called
    assert len(harness.cloudflare_payloads) == 1
    assert len(harness.openai_payloads) == 0
    cf_payload = harness.cloudflare_payloads[0]
    assert cf_payload["model"] == "typesafe/jev"
    assert "questions" in cf_payload["input"]
    assert cf_payload["input"]["questions"]["kind"]["type"] == "choice"


def test_cloudflare_jev_screening_reply(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    harness.cloudflare_result = {
        "result": {
            "model": "jev-latest",
            "answers": {
                "kind": {
                    "type": "choice",
                    "choice": "screening",
                    "confidence": 0.95,
                }
            },
        },
        "success": True,
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.cloudflare_account_id = "test-account-id"
    dialer.cloudflare_api_token = "test-api-token"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(
            attempt, "Could you clarify your organization and inquiry details before I connect you?"
        )
    )
    assert kind == "screening"
    assert reply == attempt.screening_reply
    assert len(harness.cloudflare_payloads) == 1
    assert len(harness.openai_payloads) == 0


def test_cloudflare_jev_falls_back_to_openai_on_error(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    original_handler = harness.handler

    def handler_with_cf_error(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.cloudflare.com":
            harness.cloudflare_payloads.append(json.loads(request.content))
            return httpx.Response(500, json={"error": "Cloudflare Workers AI internal error"})
        return original_handler(request)

    harness.handler = handler_with_cf_error
    harness.openai_result = {
        "output_text": json.dumps({"kind": "voicemail"})
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.cloudflare_account_id = "test-account-id"
    dialer.cloudflare_api_token = "test-api-token"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    kind, reply = asyncio.run(
        dialer._classify_transcript(
            attempt, "An automated archive system is recording this channel."
        )
    )
    # Failed closed from CF Jev to OpenAI, which returned voicemail
    assert kind == "voicemail"
    assert reply == ""
    assert len(harness.cloudflare_payloads) == 1
    assert len(harness.openai_payloads) == 1


def test_carrier_voicemail_heuristics_catch_unavailable_messages(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    test_phrases = [
        "This person is not available",
        "The person you have called is unavailable",
        "The subscriber is not available right now, please try again later",
        "Sorry, I cannot take your call at the moment, please call back",
        "Your call has been forwarded to an automated voice message system",
    ]
    for phrase in test_phrases:
        kind, _ = asyncio.run(dialer._classify_transcript(attempt, phrase))
        assert kind == "voicemail", f"Failed to classify '{phrase}' as voicemail"


def test_ivr_and_voicemail_heuristics_prevent_false_positives(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    ivr_phrases = [
        "Thank you for calling Strive for Independence LLC. If this is an emergency, please hang up and call 911.",
        "Hello, and thank you for calling Heaven at Home Senior Care. Please listen to the following options.",
        "Thank you for calling Platinum Care Group. Please listen closely as our menu options have changed.",
        "Thank you for calling Loving Hands Home Care. Please choose from the following options. Press 1",
        "Thank you for calling Live Well Home Care. Para Español o Prima Uno. Our office hours are Monday through Friday",
        "This call may be recorded for quality and training purposes.",
        "Excel home care and hospitals hand me a director call. Have a wonderful day.",
        "Thank you for calling Strive for Independence LLC.",
    ]
    for phrase in ivr_phrases:
        kind, _ = asyncio.run(dialer._classify_transcript(attempt, phrase))
        assert kind == "ivr", f"Expected 'ivr' for '{phrase}', got '{kind}'"

    voicemail_phrases = [
        "Hi, this is Dave. Please text me and I'll get back to you as quick as I can.",
        "Please text me at this number and I will get back to you as soon as possible.",
    ]
    for phrase in voicemail_phrases:
        kind, _ = asyncio.run(dialer._classify_transcript(attempt, phrase))
        assert kind == "voicemail", f"Expected 'voicemail' for '{phrase}', got '{kind}'"

    human_phrases = [
        "Hello?",
        "Speaking.",
        "Hello, this is John.",
        "Always Home Caregiving, this is Jamie. How may I help you?",
        "Wilson and Associates, good morning, how may I help you?",
    ]
    for phrase in human_phrases:
        kind, _ = asyncio.run(dialer._classify_transcript(attempt, phrase))
        assert kind == "human", f"Expected 'human' for '{phrase}', got '{kind}'"


def test_speech_respects_prior_machine_amd_result(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    attempt.answered_by = "machine_end_other"
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Hello, this is Rupert",
            },
        )
    )
    assert attempt.voicemail_detected is True
    assert attempt.outcome == "voicemail"
    assert "<Dial" not in twiml


def test_speech_on_completed_call_hangs_up_and_does_not_claim_winner(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    # Mock OpenAI returning human
    harness.openai_result = {
        "output_text": json.dumps({"kind": "human", "reply": ""})
    }
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3)
    attempt = attempt_for(dialer, session)
    
    # Twilio sends speech webhook with CallStatus=completed (callee hung up)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "CallStatus": "completed",
                "SpeechResult": "Thanks Mark.",
            },
        )
    )
    assert "<Dial" not in twiml
    assert "<Hangup" in twiml
    assert attempt.human_detected is False
    assert attempt.status == "completed"
    session_obj = dialer.sessions[session["id"]]
    assert session_obj.human_attempt_id == ""
    assert session_obj.status != "human-connected"


@pytest.mark.parametrize("field,value", [("phone", "+12025550177"), ("contact_id", "changed")])
def test_unapproved_or_invalid_smart_view_rows_never_reach_twilio(
    tmp_path, monkeypatch, field: str, value: str
) -> None:
    harness = ProviderHarness()
    harness.contacts = [harness.contacts[0]]
    harness.contacts[0][field] = value
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    with pytest.raises(LiveDialerError, match="approved for calling"):
        asyncio.run(
            dialer.start_session(
                smart_view_id=harness.smart_views[0]["id"],
                max_contacts=1,
                concurrency=1,
                screening_reply="A sufficiently long approved test reason.",
            )
        )
    assert harness.created_calls == []


def test_duplicate_numbers_are_deduplicated_and_invalid_parameters_are_rejected(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    harness.contacts[1]["phone"] = harness.contacts[0]["phone"]
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=2,
            concurrency=2,
            screening_reply="A sufficiently long approved test reason.",
        )
    )
    assert session["queue_total"] == 1
    assert len(harness.created_calls) == 1
    asyncio.run(dialer.stop_session(session["id"]))

    with pytest.raises(LiveDialerError, match="valid Close Smart View"):
        asyncio.run(
            dialer.start_session(
                smart_view_id="not-a-view",
                max_contacts=1,
                concurrency=1,
                screening_reply="A sufficiently long approved test reason.",
            )
        )
    with pytest.raises(LiveDialerError, match="15-240"):
        asyncio.run(
            dialer.start_session(
                smart_view_id=harness.smart_views[0]["id"],
                max_contacts=1,
                concurrency=1,
                screening_reply="short",
            )
        )


def test_only_one_live_batch_can_exist_globally(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    start(dialer, harness)
    with pytest.raises(LiveDialerError, match="Another live session"):
        start(dialer, harness)
    assert len(lead_destinations(harness)) == 1


def test_a_start_the_browser_abandoned_never_dials(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    async def gone() -> bool:
        return False

    with pytest.raises(LiveDialerError, match="abandoned"):
        asyncio.run(
            dialer.start_session(
                smart_view_id=harness.smart_views[0]["id"],
                max_contacts=1,
                concurrency=1,
                screening_reply="Hi, this is Acme's AI-assisted demo calling about the approved test.",
                operator_target="phone",
                still_wanted=gone,
            )
        )
    # Nobody was rung, not even the operator, and nothing blocks the next Start.
    assert harness.created_calls == []
    assert dialer.sessions == {}
    start(dialer, harness)
    assert len(lead_destinations(harness)) == 1


def test_partial_and_total_provider_failures_are_visible(tmp_path, monkeypatch) -> None:
    partial = ProviderHarness()
    partial.fail_create_numbers.add(partial.contacts[1]["phone"])
    dialer = make_dialer(tmp_path / "partial", monkeypatch, partial)
    session = start(dialer, partial, count=2)
    assert session["status"] == "running"
    assert [item["outcome"] for item in session["attempts"]] == ["", "provider-error"]

    total = ProviderHarness()
    total.fail_create_numbers.add(total.contacts[0]["phone"])
    failed = make_dialer(tmp_path / "total", monkeypatch, total)
    failed_session = start(failed, total)
    assert failed_session["status"] == "failed"
    assert next(iter(failed.sessions.values())).status == "failed"


def test_parent_status_ordering_and_close_logging_are_idempotent(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    final = {
        "CallSid": attempt.twilio_call_sid,
        "CallStatus": "completed",
        "CallDuration": "12",
        "SequenceNumber": "3",
    }
    asyncio.run(dialer.handle_status(attempt.id, final))
    asyncio.run(
        dialer.handle_status(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "CallStatus": "ringing",
                "SequenceNumber": "1",
            },
        )
    )
    asyncio.run(dialer.handle_status(attempt.id, final))
    assert attempt.status == "completed"
    assert attempt.sequence_number == 3
    assert attempt.duration == 12
    assert len(harness.close_posts) == 1


def test_power_mode_advances_one_contact_at_a_time_in_smart_view_order(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)

    assert session["mode"] == "power"
    assert session["queue_total"] == 3
    assert session["queue_started"] == 1
    assert session["queue_remaining"] == 2
    assert lead_destinations(harness) == [harness.contacts[0]["phone"]]

    first = attempt_for(dialer, session)
    completed = {
        "CallSid": first.twilio_call_sid,
        "CallStatus": "completed",
        "CallDuration": "4",
        "SequenceNumber": "3",
    }
    asyncio.run(dialer.handle_status(first.id, completed))
    after_first = dialer.session(session["id"])
    assert after_first["queue_started"] == 2
    assert after_first["queue_remaining"] == 1
    assert lead_destinations(harness) == [
        harness.contacts[0]["phone"],
        harness.contacts[1]["phone"],
    ]

    asyncio.run(dialer.handle_status(first.id, completed))
    assert len(lead_destinations(harness)) == 2

    second = dialer.attempts[after_first["attempts"][1]["id"]]
    asyncio.run(
        dialer.handle_status(
            second.id,
            {
                "CallSid": second.twilio_call_sid,
                "CallStatus": "no-answer",
                "SequenceNumber": "3",
            },
        )
    )
    after_second = dialer.session(session["id"])
    assert after_second["queue_started"] == 3
    assert lead_destinations(harness)[-1] == harness.contacts[2]["phone"]

    third = dialer.attempts[after_second["attempts"][2]["id"]]
    asyncio.run(
        dialer.handle_status(
            third.id,
            {
                "CallSid": third.twilio_call_sid,
                "CallStatus": "busy",
                "SequenceNumber": "3",
            },
        )
    )
    final = dialer.session(session["id"])
    assert final["status"] == "completed"
    assert final["queue_remaining"] == 0
    assert len(harness.close_posts) == 3


def test_parallel_mode_refills_only_the_open_line(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    assert session["mode"] == "parallel"
    assert len(lead_destinations(harness)) == 2

    first = attempt_for(dialer, session)
    asyncio.run(
        dialer.handle_status(
            first.id,
            {
                "CallSid": first.twilio_call_sid,
                "CallStatus": "completed",
                "SequenceNumber": "3",
            },
        )
    )
    current = dialer.session(session["id"])
    assert len(lead_destinations(harness)) == 3
    assert current["queue_remaining"] == 0
    assert (
        sum(
            item["status"] not in {"busy", "canceled", "completed", "failed", "no-answer"}
            for item in current["attempts"]
        )
        == 2
    )


def test_human_handoff_pauses_queue_until_parent_call_finishes(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    winner = attempt_for(dialer, session)
    asyncio.run(
        dialer.handle_speech(
            winner.id,
            {
                "CallSid": winner.twilio_call_sid,
                "SpeechResult": "Hello, this is Alex speaking",
            },
        )
    )
    assert len(lead_destinations(harness)) == 2
    assert dialer.sessions[session["id"]].human_attempt_id == winner.id
    live = dialer.session(session["id"])
    assert live["status"] == "human-connected"
    assert live["active_contact"]["close_url"].endswith("/lead_1/")

    asyncio.run(dialer.complete_active_call(session["id"]))
    assert len(lead_destinations(harness)) == 3
    assert lead_destinations(harness)[-1] == harness.contacts[2]["phone"]


def test_stopped_queue_never_refills_after_late_callback(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    first = attempt_for(dialer, session)
    asyncio.run(dialer.stop_session(session["id"]))
    asyncio.run(
        dialer.handle_status(
            first.id,
            {
                "CallSid": first.twilio_call_sid,
                "CallStatus": "completed",
                "SequenceNumber": "4",
            },
        )
    )
    assert len(lead_destinations(harness)) == 1
    assert dialer.session(session["id"])["status"] == "stopped"


def test_stopped_power_queue_resumes_at_the_next_unattempted_contact(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    first_session = start(dialer, harness, count=3, concurrency=1)
    asyncio.run(dialer.stop_session(first_session["id"]))

    resumed = start(dialer, harness, count=3, concurrency=1)
    assert resumed["mode"] == "power"
    assert resumed["queue_total"] == 3
    assert resumed["resumed_from"] == 1
    assert resumed["queue_started"] == 2
    assert lead_destinations(harness) == [
        harness.contacts[0]["phone"],
        harness.contacts[1]["phone"],
    ]


def test_checkpoint_survives_restart_without_recent_session_history(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    asyncio.run(dialer.stop_session(session["id"]))

    state = json.loads(dialer.state_path.read_text(encoding="utf-8"))
    state["sessions"] = []
    state["attempts"] = []
    dialer.state_path.write_text(json.dumps(state), encoding="utf-8")
    restored = make_dialer(tmp_path, monkeypatch, harness)
    resumed = start(restored, harness, count=3, concurrency=1)
    assert resumed["resumed_from"] == 1
    assert lead_destinations(harness)[-1] == harness.contacts[1]["phone"]


def test_checkpoint_decorates_queue_and_explicit_reset_allows_start_over(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=1, concurrency=1)
    first = attempt_for(dialer, session)
    asyncio.run(
        dialer.handle_status(
            first.id,
            {
                "CallSid": first.twilio_call_sid,
                "CallStatus": "completed",
                "SequenceNumber": "3",
            },
        )
    )
    payload = dialer.decorate_contacts(
        dialer.close_dialer.contacts(limit=1, smart_view_id=harness.smart_views[0]["id"])
    )
    assert payload["contacts"][0]["dialer_attempted"] is True
    assert payload["checkpoint"]["attempted_count"] == 1
    assert payload["checkpoint"]["remaining_count"] == 0
    assert payload["checkpoint"]["complete"] is True
    with pytest.raises(LiveDialerError, match="Everyone in this Smart View was dialed"):
        start(dialer, harness, count=1, concurrency=1)

    reset = asyncio.run(dialer.reset_checkpoint(harness.smart_views[0]["id"]))
    assert reset["reset"] is True
    restarted = start(dialer, harness, count=1, concurrency=1)
    assert restarted["resumed_from"] == 0
    assert len(lead_destinations(harness)) == 2


def test_active_session_is_discoverable_and_blocks_checkpoint_reset(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    active = dialer.status()["active_session"]
    assert active["id"] == session["id"]
    assert active["smart_view_id"] == harness.smart_views[0]["id"]
    with pytest.raises(LiveDialerError, match="Stop the active session"):
        asyncio.run(dialer.reset_checkpoint(harness.smart_views[0]["id"]))


def test_close_call_notes_are_html_escaped() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "acti_1"})

    dialer = CloseDialer(transport=httpx.MockTransport(handler))
    dialer.api_key = "test-key"
    dialer.log_call(
        lead_id="lead_1",
        contact_id="cont_1",
        phone="+12025550148",
        duration=3,
        note="Outcome <script>alert(1)</script>",
    )
    assert "<script>" not in captured["note_html"]
    assert "&lt;script&gt;" in captured["note_html"]


def test_stop_is_idempotent_and_failed_stop_remains_locked(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    stopped = asyncio.run(dialer.stop_session(session["id"]))
    assert stopped["status"] == "stopped"
    assert asyncio.run(dialer.stop_session(session["id"]))["status"] == "stopped"

    failing_harness = ProviderHarness()
    failing = make_dialer(tmp_path / "failed-stop", monkeypatch, failing_harness)
    active = start(failing, failing_harness)
    failing_harness.fail_updates = True
    result = asyncio.run(failing.stop_session(active["id"]))
    assert result["status"] == "stop-failed"
    with pytest.raises(LiveDialerError, match="Another live session"):
        start(failing, failing_harness)
    failing_harness.fail_updates = False
    assert asyncio.run(failing.stop_session(active["id"]))["status"] == "stopped"


def test_state_survives_restart_without_persisting_transcript(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    attempt.transcript.append("private spoken words")
    dialer._persist_state()

    restored = make_dialer(tmp_path, monkeypatch, harness)
    restored_attempt = restored.attempt(attempt.id)
    assert restored.session(session["id"])["status"] == "running"
    assert restored_attempt.twilio_call_sid == attempt.twilio_call_sid
    assert restored_attempt.transcript == []
    assert restored.verify_signature(attempt.id, restored._attempt_signature(attempt.id))


def test_reconcile_recovers_terminal_call_after_restart(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    harness.call_statuses[attempt.twilio_call_sid] = {"status": "completed", "duration": "9"}

    restored = make_dialer(tmp_path, monkeypatch, harness)
    asyncio.run(restored.reconcile())
    recovered = restored.attempt(attempt.id)
    assert recovered.status == "completed"
    assert recovered.duration == 9
    assert restored.session(session["id"])["status"] == "completed"
    assert len(harness.close_posts) == 1


def test_async_amd_discards_machine_but_not_human(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    machine_session = start(dialer, harness)
    machine = attempt_for(dialer, machine_session)

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr("parallel_dialer.live_dialer.asyncio.sleep", no_wait)
    asyncio.run(
        dialer.handle_amd(
            machine.id,
            {"CallSid": machine.twilio_call_sid, "AnsweredBy": "machine_end_beep"},
        )
    )
    assert machine.outcome == "voicemail"
    assert machine.voicemail_played is True
    update = next(
        item
        for item in reversed(harness.requests)
        if item.method == "POST" and item.url.path.endswith(f"/{machine.twilio_call_sid}.json")
    )
    assert "<Play>" in parse_qs(update.content.decode("utf-8"))["Twiml"][0]

    second = ProviderHarness()
    human_dialer = make_dialer(tmp_path / "human", monkeypatch, second)
    human_session = start(human_dialer, second)
    human = attempt_for(human_dialer, human_session)
    asyncio.run(
        human_dialer.handle_amd(
            human.id,
            {"CallSid": human.twilio_call_sid, "AnsweredBy": "human"},
        )
    )
    # AMD alone does not unilaterally bridge without speech verification
    assert human.answered_by == "human"
    assert human.status != "bridged"

    # Verified human speech confirms and bridges to operator
    twiml = asyncio.run(
        human_dialer.handle_speech(
            human.id,
            {"CallSid": human.twilio_call_sid, "SpeechResult": "Hello, this is Jane speaking."},
        )
    )
    assert human.outcome == "human-bridged"
    assert human.status == "bridged"
    assert "<Conference" in twiml


def test_carrier_transfer_prompt_does_not_bridge_and_continues_listening(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Twilio AMD fires "human" because of short transfer speech burst
    asyncio.run(
        dialer.handle_amd(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "AnsweredBy": "human"},
        )
    )
    assert attempt.status != "bridged"

    # Carrier transfer prompt (e.g. Jeanine Signorelli case: "Wait, while we are.")
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Wait, while we are."},
        )
    )
    # Must NOT bridge the operator into an automated transfer
    assert attempt.status != "bridged"
    assert attempt.outcome != "human-bridged"
    # Must continue gathering audio for the destination
    root = ElementTree.fromstring(twiml)
    assert root.find("Gather") is not None
    assert root.find("Dial/Conference") is None


def test_voicemail_starting_with_hello_classified_as_voicemail(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Greeting starts with "Hello" but is followed by "you've reached the voicemail box"
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Hello? Hello, you've reached the voicemail box of Brian. Please leave a message.",
            },
        )
    )
    assert attempt.outcome == "voicemail"
    assert attempt.status in {"completed", "voicemail-playing"}
    assert attempt.human_detected is False
    root = ElementTree.fromstring(twiml)
    assert root.find("Dial/Conference") is None


def test_operator_is_connected_before_any_prospect_is_dialed(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=2,
            concurrency=1,
            screening_reply="This is the approved reason for the test call.",
            operator_target="phone",
        )
    )
    assert session["status"] == "operator-connecting"
    assert session["attempts"] == []
    assert harness.created_calls == [
        {"sid": dialer.sessions[session["id"]].operator_call_sid, "to": "+12025550199"}
    ]

    operator_sid = dialer.sessions[session["id"]].operator_call_sid
    twiml = asyncio.run(
        dialer.handle_session_operator_answer(session["id"], {"CallSid": operator_sid})
    )
    root = ElementTree.fromstring(twiml)
    assert root.find("Dial/Conference") is not None
    assert root.find("Say") is None
    assert lead_destinations(harness) == [harness.contacts[0]["phone"]]
    assert dialer.session(session["id"])["operator"]["ready"] is True


def test_voicemail_upload_media_and_inbound_callback_configuration(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    with pytest.raises(LiveDialerError, match="MP3 or WAV"):
        dialer.save_voicemail_recording(
            filename="message.txt",
            content_type="text/plain",
            data_base64=base64.b64encode(b"x" * 2048).decode("ascii"),
        )
    audio, content_type = dialer.voicemail_audio()
    assert audio.startswith(b"ID3")
    assert content_type == "audio/mpeg"
    routing = asyncio.run(dialer.configure_inbound_routing())
    assert routing["configured"] is True
    assert harness.number_updates[-1]["VoiceMethod"] == "POST"
    assert "/twilio/dialer/inbound?sig=" in harness.number_updates[-1]["VoiceUrl"]
    inbound = ElementTree.fromstring(dialer.inbound_twiml())
    assert inbound.find("Dial/Number").text == "+12025550199"
    # With no caller on the request there is nothing to pass through.
    assert "callerId" not in inbound.find("Dial").attrib


def test_fastapi_auth_and_signed_webhook_flow_end_to_end(tmp_path, monkeypatch) -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    configure(monkeypatch)
    from parallel_dialer.api import create_app

    harness = ProviderHarness()
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    settings = Settings(root=tmp_path / "app", allowed_emails=ALLOWED, profile=PROFILE)
    live = LiveDialer(
        settings,
        close,
        transport=httpx.MockTransport(harness.handler),
    )
    client = TestClient(
        create_app(
            settings,
            close_dialer_instance=close,
            live_dialer_instance=live, secret=SIGNING_SECRET,
        )
    )
    assert client.get("/dialer/api/status").status_code == 401
    headers = {"Authorization": f"Bearer {ACCESS_KEY}"}
    assert client.get("/dialer/api/status", headers=headers).status_code == 200
    upload = client.put(
        "/dialer/api/voicemail",
        headers=headers,
        json={
            "filename": "marco-voicemail.mp3",
            "content_type": "audio/mpeg",
            "data_base64": base64.b64encode(b"ID3" + b"\0" * 2048).decode("ascii"),
        },
    )
    assert upload.status_code == 200
    assert upload.json()["voicemail"]["configured"] is True
    start_response = client.post(
        "/dialer/api/start",
        headers=headers,
        json={
            "smart_view_id": harness.smart_views[0]["id"],
            "max_contacts": 1,
            "concurrency": 1,
            "screening_reply": "This is Acme's approved AI-assisted product test.",
        },
    )
    assert start_response.status_code == 200
    session_id = start_response.json()["session"]["id"]
    assert start_response.json()["session"]["status"] == "operator-connecting"
    assert start_response.json()["session"]["attempts"] == []
    active_status = client.get("/dialer/api/status", headers=headers).json()
    assert active_status["active_session"]["id"] == session_id
    operator_sid = live.sessions[session_id].operator_call_sid
    session_signature = live._session_signature(session_id)
    forged_operator = client.post(
        "/twilio/dialer/operator-answer",
        params={"session_id": session_id, "sig": "0" * 64},
        data={"CallSid": operator_sid},
    )
    assert forged_operator.status_code == 403
    operator_answer = client.post(
        "/twilio/dialer/operator-answer",
        params={"session_id": session_id, "sig": session_signature},
        data={"CallSid": operator_sid},
    )
    assert operator_answer.status_code == 200
    assert ElementTree.fromstring(operator_answer.text).find("Dial/Conference") is not None
    attempt = attempt_for(live, live.session(session_id))
    signature = live._attempt_signature(attempt.id)
    query = {"attempt_id": attempt.id, "sig": signature}

    forged = client.post(
        "/twilio/dialer/answer",
        params={"attempt_id": attempt.id, "sig": "0" * 64},
        data={"CallSid": attempt.twilio_call_sid},
    )
    assert forged.status_code == 403
    wrong_call = client.post(
        "/twilio/dialer/answer",
        params=query,
        data={"CallSid": _sid("CA", 999)},
    )
    assert wrong_call.status_code == 403
    answer = client.post(
        "/twilio/dialer/answer",
        params=query,
        data={"CallSid": attempt.twilio_call_sid},
    )
    assert answer.status_code == 200
    assert ElementTree.fromstring(answer.text).find("Gather") is not None

    speech = client.post(
        "/twilio/dialer/speech",
        params=query,
        headers={"I-Twilio-Idempotency-Token": "speech-api-1"},
        data={"CallSid": attempt.twilio_call_sid, "SpeechResult": "Hello, speaking"},
    )
    assert speech.status_code == 200
    speech_root = ElementTree.fromstring(speech.text)
    assert speech_root.find("Dial/Conference") is not None
    assert speech_root.find("Say") is None
    connected = client.get(f"/dialer/api/session/{session_id}", headers=headers).json()["session"]
    assert connected["active_contact"]["contact_id"] == attempt.contact_id
    completed = client.post(
        f"/dialer/api/session/{session_id}/complete-active",
        headers=headers,
    )
    assert completed.status_code == 200
    assert completed.json()["session"]["status"] == "completed"

    media = client.get(
        "/twilio/dialer/voicemail-media",
        params={"sig": live._resource_signature("voicemail-media"), "op": "alice"},
    )
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("audio/mpeg")
    inbound = client.post(
        "/twilio/dialer/inbound",
        params={"sig": live._resource_signature("inbound-routing")},
        data={"From": "+12025550148"},
    )
    assert inbound.status_code == 200
    assert ElementTree.fromstring(inbound.text).find("Dial/Number").text == "+12025550199"

    rec_sig = live._attempt_signature(attempt.id)
    rec_res = client.post(
        "/twilio/dialer/recording",
        params={"attempt_id": attempt.id, "sig": rec_sig},
        data={
            "RecordingSid": "RE1234567890abcdef1234567890abcdef",
            "RecordingStatus": "completed",
            "RecordingDuration": "25",
        },
    )
    assert rec_res.status_code == 204

    stream_res = client.get("/twilio/dialer/call-recording/RE1234567890abcdef1234567890abcdef.mp3")
    assert stream_res.status_code == 200
    assert stream_res.headers["content-type"] == "audio/mpeg"

    reset = client.post(
        "/dialer/api/progress/reset",
        headers=headers,
        json={"smart_view_id": harness.smart_views[0]["id"]},
    )
    assert reset.status_code == 200
    assert reset.json()["checkpoint"]["reset"] is True


def _wav(seconds: float, rate: int = 8000) -> str:
    """A valid PCM WAV of silence, as the browser recorder produces it."""
    frames = int(rate * seconds)
    body = b"\x00\x00" * frames
    header = (
        b"RIFF" + (36 + len(body)).to_bytes(4, "little") + b"WAVE"
        + b"fmt " + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
        + rate.to_bytes(4, "little") + (rate * 2).to_bytes(4, "little")
        + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
        + b"data" + len(body).to_bytes(4, "little")
    )
    return base64.b64encode(header + body).decode("ascii")


def _save(dialer: LiveDialer, slot: str, seconds: float = 0.6) -> dict:
    return dialer.save_recording(
        slot,
        filename=f"{slot}.wav",
        content_type="audio/wav",
        data_base64=_wav(seconds),
    )


def test_wav_and_mp3_durations_are_read_or_declined() -> None:
    assert audio_duration_seconds(base64.b64decode(_wav(1.5)), "audio/wav") == pytest.approx(1.5)
    assert audio_duration_seconds(b"ID3" + b"\0" * 2048, "audio/mpeg") is None
    assert audio_duration_seconds(b"not audio", "audio/wav") is None


def test_hello_plays_on_answer_and_is_held_to_its_budget(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Nothing recorded: the leg still listens in silence, as it did before slots.
    gather = ElementTree.fromstring(dialer.answer_twiml(attempt.id)).find("Gather")
    assert gather.find("Play") is None and gather.find("Say") is None

    with pytest.raises(LiveDialerError, match="under 2.5 seconds"):
        _save(dialer, "greeting", seconds=4.0)
    assert dialer.recording_metadata("greeting")["configured"] is False

    saved = _save(dialer, "greeting", seconds=0.6)
    assert saved["duration_seconds"] == pytest.approx(0.6)

    # Slot prompt twiml renders the recording media url with cache-busting digest
    slot_twiml = dialer._gather_twiml(attempt, "", slot="greeting")
    play = ElementTree.fromstring(slot_twiml).find("Gather/Play")
    assert play is not None and "/recording-media/greeting?sig=" in play.text
    # The digest travels in the URL so a re-recorded hello is not served from cache.
    assert f"v={saved['sha256'][:16]}" in play.text

    # But answer_twiml deliberately listens in silence with zero audio playback,
    # preventing Twilio's speech recognizer from being deaf during the initial greeting.
    answer_gather = ElementTree.fromstring(dialer.answer_twiml(attempt.id)).find("Gather")
    assert answer_gather.find("Play") is None and answer_gather.find("Say") is None


def test_screening_reply_prefers_the_operator_voice_over_twilio_tts(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    params = {"CallSid": attempt.twilio_call_sid, "SpeechResult": "May I ask who is calling?"}

    spoken = ElementTree.fromstring(asyncio.run(dialer.handle_speech(attempt.id, params)))
    assert spoken.find("Gather/Say") is not None
    assert spoken.find("Gather/Play") is None

    _save(dialer, "screening", seconds=2.0)
    played = ElementTree.fromstring(asyncio.run(dialer.handle_speech(attempt.id, params)))
    assert played.find("Gather/Say") is None
    assert "/recording-media/screening?sig=" in played.find("Gather/Play").text


def test_machine_is_hung_up_on_in_silence_when_no_message_is_recorded(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    assert dialer.recording_metadata("voicemail")["configured"] is True

    dialer.delete_recording("voicemail")
    assert dialer.recording_metadata("voicemail")["configured"] is False
    # Removing the message must not lock the dialer; that was the old blocker.
    assert dialer.ready is True

    silent = ElementTree.fromstring(dialer._voicemail_twiml())
    assert silent.find("Play") is None
    assert silent.find("Hangup") is not None

    _save(dialer, "voicemail", seconds=2.0)
    restored = ElementTree.fromstring(dialer._voicemail_twiml())
    assert "/recording-media/voicemail?sig=" in restored.find("Play").text


def test_media_signatures_do_not_transfer_between_slots(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    _save(dialer, "greeting")
    voicemail_sig = dialer._resource_signature("voicemail-media")
    assert dialer.verify_media_signature(voicemail_sig, "voicemail") is True
    assert dialer.verify_media_signature(voicemail_sig, "greeting") is False
    with pytest.raises(LiveDialerError, match="Unknown recording slot"):
        dialer.verify_media_signature(voicemail_sig, "anything-else")


def test_recording_slots_round_trip_through_the_api(tmp_path, monkeypatch) -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    configure(monkeypatch)
    from parallel_dialer.api import create_app

    harness = ProviderHarness()
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    settings = Settings(root=tmp_path / "app", allowed_emails=ALLOWED, profile=PROFILE)
    live = LiveDialer(settings, close, transport=httpx.MockTransport(harness.handler))
    client = TestClient(
        create_app(settings, close_dialer_instance=close, live_dialer_instance=live, secret=SIGNING_SECRET)
    )
    headers = {"Authorization": f"Bearer {ACCESS_KEY}"}

    assert client.put("/dialer/api/recording/greeting", json={
        "filename": "hello.wav", "content_type": "audio/wav", "data_base64": _wav(0.5)}
    ).status_code == 401

    saved = client.put("/dialer/api/recording/greeting", headers=headers, json={
        "filename": "hello.wav", "content_type": "audio/wav", "data_base64": _wav(0.5)})
    assert saved.status_code == 200
    assert saved.json()["recordings"]["greeting"]["configured"] is True
    assert saved.json()["recordings"]["voicemail"]["configured"] is False

    too_long = client.put("/dialer/api/recording/greeting", headers=headers, json={
        "filename": "hello.wav", "content_type": "audio/wav", "data_base64": _wav(5.0)})
    assert too_long.status_code == 400
    assert "under 2.5 seconds" in too_long.json()["error"]

    unknown = client.put("/dialer/api/recording/nonsense", headers=headers, json={
        "filename": "x.wav", "content_type": "audio/wav", "data_base64": _wav(0.5)})
    assert unknown.status_code == 400

    media = client.get(
        "/twilio/dialer/recording-media/greeting",
        params={"sig": live._resource_signature("greeting-media"), "op": "alice"},
    )
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("audio/wav")
    crossed = client.get(
        "/twilio/dialer/recording-media/voicemail",
        params={"sig": live._resource_signature("greeting-media")},
    )
    assert crossed.status_code == 403

    removed = client.delete("/dialer/api/recording/greeting", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["recordings"]["greeting"]["configured"] is False
    assert client.get("/dialer/api/status", headers=headers).json()["recordings"]["greeting"][
        "configured"
    ] is False


def test_a_callback_reaches_close_as_the_lead_who_is_calling(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    configure(monkeypatch, callback="+16285550147")
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    dialer = LiveDialer(
        Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE),
        close,
        transport=httpx.MockTransport(harness.handler),
    )

    dial = ElementTree.fromstring(dialer.inbound_twiml("+15105550143")).find("Dial")
    # Close matches an inbound call on the caller's number, so the returning
    # lead's own number is what has to arrive -- not ours.
    assert dial.attrib["callerId"] == "+15105550143"
    assert dial.find("Number").text == "+16285550147"

    # A malformed or withheld caller must not become a forged caller ID.
    for junk in ("", "unknown", "+1", "anonymous"):
        assert "callerId" not in ElementTree.fromstring(dialer.inbound_twiml(junk)).find("Dial").attrib

    assert dialer.status()["callback_destination"] == "close"
    assert dialer.status()["callback_number_masked"].endswith("0147")


def test_without_a_close_number_callbacks_still_reach_the_operator(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dial = ElementTree.fromstring(dialer.inbound_twiml("+15105550143")).find("Dial")
    assert dial.find("Number").text == "+12025550199"
    assert dial.attrib["callerId"] == "+15105550143"
    assert dialer.status()["callback_destination"] == "operator"


def test_close_activity_note_does_not_call_a_real_call_a_demo(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    asyncio.run(dialer.handle_status(attempt.id, {"CallSid": attempt.twilio_call_sid,
                                                  "CallStatus": "completed", "CallDuration": "12"}))
    note = harness.close_posts[-1]["note_html"]
    assert "demo" not in note.lower(), note
    assert "Parallel dialer" in note


def test_the_operator_leg_can_ring_the_browser_instead_of_a_phone(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, operator_target="browser")

    # Twilio addresses a registered browser as client:<identity>; nothing else changes,
    # because the operator leg only ever had to answer and join the conference.
    assert harness.created_calls[0]["to"] == "client:dialer-operator"
    # start() already answers the leg for us, so the session is past connecting.
    assert session["status"] == "running"

    live = dialer.sessions[session["id"]]
    conference = ElementTree.fromstring(dialer._operator_conference_twiml(live)).find("Dial/Conference")
    assert conference.attrib["participantLabel"] == "operator"
    assert conference.attrib["endConferenceOnExit"] == "true"
    assert conference.attrib["waitUrl"] == ""



def test_no_operator_number_is_needed_when_the_browser_takes_the_call(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    configure(monkeypatch, operator="")
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    dialer = LiveDialer(
        Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE),
        close,
        transport=httpx.MockTransport(harness.handler),
    )
    assert dialer.ready is True
    assert not any("operator number" in b for b in dialer.blockers())

    assert asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=1,
            concurrency=1,
            screening_reply="This is the approved reason for the test call.",
        )
    )["status"] == "operator-connecting"

    # Asking for the phone without one configured is refused, not silently rerouted.
    for live in list(dialer.sessions.values()):
        live.status = "stopped"
    with pytest.raises(LiveDialerError, match="operator number"):
        asyncio.run(
            dialer.start_session(
                smart_view_id=harness.smart_views[0]["id"],
                max_contacts=1,
                concurrency=1,
                screening_reply="This is the approved reason for the test call.",
                operator_target="phone",
            )
        )


def test_the_browser_token_can_receive_a_call_and_place_none(tmp_path, monkeypatch) -> None:
    import jwt as jwt_lib

    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    issued = dialer.voice_access_token(ttl_seconds=900)

    decoded = jwt_lib.decode(issued["token"], "secret-value-for-tests-123456", algorithms=["HS256"])
    assert decoded["iss"] == "SK" + "b" * 32
    assert decoded["sub"] == "AC" + "a" * 32
    assert decoded["grants"]["identity"] == "dialer-operator"
    assert decoded["grants"]["voice"] == {"incoming": {"allow": True}}
    # A leaked token must not be able to dial anyone.
    assert "outgoing" not in decoded["grants"]["voice"]
    assert jwt_lib.get_unverified_header(issued["token"])["cty"] == "twilio-fpa;v=1"
    assert 800 < decoded["exp"] - decoded["nbf"] < 1000

    assert dialer.status()["browser_calling"] is True
    assert dialer.status()["voice_identity"] == "dialer-operator"


def test_unrestricted_mode_dials_queue_without_allowlist_and_respects_blocklist(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    configure(
        monkeypatch,
        allowed="none",
        operator="+12025550199",
    )
    monkeypatch.setenv("DIALER_UNRESTRICTED", "enabled")
    monkeypatch.setenv("DIALER_BLOCKED_NUMBERS", "+12025550150")

    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    dialer = LiveDialer(
        Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE),
        close,
        transport=httpx.MockTransport(harness.handler),
    )

    assert dialer.ready is True
    assert dialer.blockers() == []
    status = dialer.status()
    assert status["unrestricted"] is True
    assert status["allowlist_count"] == 0
    assert status["blocklist_count"] == 1

    contacts_payload = dialer.decorate_contacts(
        close.contacts(limit=10, smart_view_id=harness.smart_views[0]["id"])
    )
    by_phone = {c["phone"]: c["live_allowed"] for c in contacts_payload["contacts"]}
    # Blocked number is marked not allowed; others are allowed
    assert by_phone["+12025550150"] is False
    assert by_phone["+12025550148"] is True
    assert by_phone["+12025550149"] is True

    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=5,
            concurrency=2,
            screening_reply="This is an approved screening reason for testing.",
            operator_target="browser",
        )
    )
    assert session["status"] == "operator-connecting"
    assert dialer.sessions[session["id"]].operator_target == "browser"
    assert harness.created_calls[0]["to"] == "client:dialer-operator"
    dialed_phones = [c["phone"] for c in dialer.sessions[session["id"]].queue]
    assert "+12025550150" not in dialed_phones
    assert "+12025550148" in dialed_phones


def test_unrestricted_mode_raises_when_all_contacts_are_blocked(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    configure(
        monkeypatch,
        allowed="none",
    )
    monkeypatch.setenv("DIALER_UNRESTRICTED", "enabled")
    # Block all phones in the harness
    monkeypatch.setenv(
        "DIALER_BLOCKED_NUMBERS",
        "+12025550148,+12025550149,+12025550150",
    )

    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    dialer = LiveDialer(
        Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE),
        close,
        transport=httpx.MockTransport(harness.handler),
    )

    with pytest.raises(LiveDialerError, match="callable contacts"):
        asyncio.run(
            dialer.start_session(
                smart_view_id=harness.smart_views[0]["id"],
                max_contacts=5,
                concurrency=1,
                screening_reply="This is an approved screening reason for testing.",
            )
        )


def test_multi_operator_user_attribution_and_isolated_checkpoints(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    close = dialer.close_dialer

    # 1. A Close user id is only known once an operator's key has been verified
    assert close.user_id_for("alice@example.com") == ""
    close.custom_user_ids["bob@example.com"] = "user_bob_close_id"
    assert close.user_id_for("bob@example.com") == "user_bob_close_id"
    assert close.user_id_for("unknown@example.com") == ""

    # 2. Smart Views sorting prioritizes the operator's lists
    views = [
        {"id": "save_1", "name": "General Leads"},
        {"id": "save_2", "name": "Bob - Batch 1 Calls"},
        {"id": "save_3", "name": "Alice - Priority Accounts"},
    ]
    bob_sorted = close._sort_views(views, "bob@example.com")
    assert bob_sorted[0]["name"] == "Bob - Batch 1 Calls"

    alice_sorted = close._sort_views(views, "alice@example.com")
    assert alice_sorted[0]["name"] == "Alice - Priority Accounts"

    # 3. Softphone voice identities
    assert dialer.operator_voice_identity("") == "dialer-operator"
    assert dialer.operator_voice_identity("alice@example.com") == "dialer-operator-alice"
    assert dialer.operator_voice_identity("bob@example.com") == "dialer-operator-bob"

    # 4. Bob starting a session uses client:dialer-operator-bob
    bob_session = start(
        dialer,
        harness,
        count=1,
        concurrency=1,
        operator_target="browser",
        operator_email="bob@example.com",
    )
    assert bob_session["operator_email"] == "bob@example.com"
    assert harness.created_calls[0]["to"] == "client:dialer-operator-bob"

    # 5. Checkpoint isolation
    first_attempt = attempt_for(dialer, bob_session)
    asyncio.run(
        dialer.handle_status(
            first_attempt.id,
            {
                "CallSid": first_attempt.twilio_call_sid,
                "CallStatus": "completed",
                "SequenceNumber": "3",
            },
        )
    )

    # Bob's decoration reflects 1 attempted
    bob_contacts = dialer.decorate_contacts(
        close.contacts(limit=10, smart_view_id=harness.smart_views[0]["id"]),
        operator_email="bob@example.com",
    )
    assert bob_contacts["checkpoint"]["attempted_count"] == 1

    # Dial history is pooled across operators, even though checkpoints are separate.
    alice_contacts = dialer.decorate_contacts(
        close.contacts(limit=10, smart_view_id=harness.smart_views[0]["id"]),
        operator_email="alice@example.com",
    )
    assert alice_contacts["checkpoint"]["attempted_count"] == 1

    # 6. Close call logging passes operator user_id
    logged = close.log_call(
        lead_id="lead_123",
        contact_id="cont_123",
        phone="+12025550148",
        duration=45,
        note="Test call",
        operator_email="bob@example.com",
    )
    assert logged["id"].startswith("acti_")
    assert harness.close_posts[-1]["user_id"] == "user_bob_close_id"


def test_close_log_call_and_update_call_recording(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    configure(monkeypatch)
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"

    # 1. log_call with recording_url
    rec_url = "https://dialer.example.com/twilio/dialer/call-recording/RE1234567890abcdef1234567890abcdef.mp3"
    result = close.log_call(
        lead_id="lead_123",
        contact_id="cont_123",
        phone="+12025550148",
        duration=30,
        note="Call with recording",
        recording_url=rec_url,
    )
    assert result["id"].startswith("acti_")
    assert harness.close_posts[-1]["recording_url"] == rec_url
    assert harness.close_posts[-1]["duration"] == 30

    # 2. update_call_recording updates recording_url and duration
    new_rec_url = "https://dialer.example.com/twilio/dialer/call-recording/RE9999999999abcdef9999999999abcdef.mp3"
    updated = close.update_call_recording(
        result["id"],
        recording_url=new_rec_url,
        duration=55,
        operator_email="alice@example.com",
    )
    assert updated["id"] == result["id"]
    assert harness.close_puts[-1]["recording_url"] == new_rec_url
    assert harness.close_puts[-1]["duration"] == 55

    # 3. Invalid call activity ID raises DialerError
    with pytest.raises(DialerError, match="Invalid Close call activity identifier"):
        close.update_call_recording("invalid_id", recording_url=new_rec_url)


def test_outbound_call_and_conference_twiml_request_recordings(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    start(dialer, harness)

    # Verify Calls.json outbound call requested RecordingStatusCallback
    attempt_requests = [
        r for r in harness.requests
        if r.url.path.endswith("/Calls.json")
        and "answer?attempt_id=" in parse_qs(r.content.decode("utf-8")).get("Url", [""])[0]
    ]
    assert len(attempt_requests) >= 1
    call_form = parse_qs(attempt_requests[0].content.decode("utf-8"))
    assert call_form["Record"] == ["true"]
    assert "RecordingStatusCallback" in call_form
    assert "/recording?attempt_id=" in call_form["RecordingStatusCallback"][0]
    assert call_form["RecordingStatusCallbackEvent"] == ["completed"]

    # Verify conference TwiML includes conference recording
    attempt = next(iter(dialer.attempts.values()))
    conf_twiml = dialer._conference_twiml(attempt)
    assert 'record="record-from-start"' in conf_twiml
    assert "conference-recording?attempt_id=" in conf_twiml
    assert 'recordingStatusCallbackEvent="completed"' in conf_twiml


def test_handle_recording_status_and_audio_caching(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    start(dialer, harness)
    attempt = next(iter(dialer.attempts.values()))
    attempt.close_call_id = "acti_test_rec_123"

    sid_call = "RE11111111111111111111111111111111"
    asyncio.run(
        dialer.handle_recording_status(
            attempt.id,
            {
                "RecordingSid": sid_call,
                "RecordingStatus": "completed",
                "RecordingDuration": "28",
            },
        )
    )
    assert attempt.recording_sid == sid_call
    assert sid_call in attempt.recording_url
    assert attempt.duration == 28
    assert harness.close_puts[-1]["recording_url"] == attempt.recording_url
    assert harness.close_puts[-1]["duration"] == 28

    # Conference recording arrives and updates over call recording
    sid_conf = "RE22222222222222222222222222222222"
    asyncio.run(
        dialer.handle_recording_status(
            attempt.id,
            {
                "RecordingSid": sid_conf,
                "RecordingStatus": "completed",
                "RecordingDuration": "42",
            },
            is_conference=True,
        )
    )
    assert attempt.recording_sid == sid_conf
    assert sid_conf in attempt.recording_url
    assert attempt.duration == 42
    assert harness.close_puts[-1]["recording_url"] == attempt.recording_url
    assert harness.close_puts[-1]["duration"] == 42

    # A subsequent call recording does NOT overwrite conference recording
    asyncio.run(
        dialer.handle_recording_status(
            attempt.id,
            {
                "RecordingSid": sid_call,
                "RecordingStatus": "completed",
                "RecordingDuration": "28",
            },
            is_conference=False,
        )
    )
    assert attempt.recording_sid == sid_conf

    # Test call_recording_audio fetches from Twilio and caches to disk
    audio_bytes, content_type = asyncio.run(dialer.call_recording_audio(sid_conf))
    assert content_type == "audio/mpeg"
    assert b"fake-recording-data" in audio_bytes
    cache_file = dialer.settings.state_dir / "call_recordings" / f"{sid_conf}.mp3"
    assert cache_file.exists()

    # Second fetch reads from cache
    audio_cached, _ = asyncio.run(dialer.call_recording_audio(sid_conf))
    assert audio_cached == audio_bytes


def test_operator_recordings_are_strictly_isolated_and_streamable(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    # make_dialer saved one voicemail with no operator named. It belongs to nobody, so
    # neither operator inherits it.
    for who in ("alice@example.com", "bob@example.com"):
        meta = dialer.recordings_metadata(who)
        assert meta["voicemail"]["configured"] is False
        assert meta["greeting"]["configured"] is False
        with pytest.raises(LiveDialerError, match="unavailable"):
            dialer.recording_audio("voicemail", operator_email=who)

    def voicemail(tag: bytes) -> str:
        return base64.b64encode(b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x00" + tag + b"\0" * 2048).decode("ascii")

    for who, filename, tag in (
        ("alice@example.com", "alice-vm.mp3", b"alice-audio-bytes"),
        ("bob@example.com", "bob-vm.mp3", b"bob-audio-bytes"),
    ):
        dialer.save_recording(
            "voicemail",
            filename=filename,
            content_type="audio/mpeg",
            data_base64=voicemail(tag),
            operator_email=who,
        )
        meta = dialer.recordings_metadata(who)
        assert meta["voicemail"]["configured"] is True
        assert meta["voicemail"]["filename"] == filename

    # Each streams their own audio, and neither sees the other's
    bob_audio, content_type = dialer.recording_audio("voicemail", operator_email="bob@example.com")
    assert b"bob-audio-bytes" in bob_audio
    assert content_type == "audio/mpeg"
    alice_audio, _ = dialer.recording_audio("voicemail", operator_email="alice@example.com")
    assert b"alice-audio-bytes" in alice_audio
    assert b"bob-audio-bytes" not in alice_audio


def test_operator_close_api_key_lifecycle(tmp_path, monkeypatch) -> None:
    settings = Settings(root=tmp_path, allowed_emails=ALLOWED, profile=PROFILE)
    
    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        decoded = ""
        if auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth.removeprefix("Basic ").strip()).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                decoded = ""
        if "api_invalid" in decoded:
            return httpx.Response(401, json={"error": "Unauthorized"})
        if "api_bob_valid_key_12345" in decoded:
            return httpx.Response(
                200,
                json={
                    "id": "user_bob_close_id_999",
                    "email": "bob@example.com",
                    "first_name": "Bob",
                    "last_name": "Test",
                },
            )
        return httpx.Response(404)

    close = CloseDialer(
        transport=httpx.MockTransport(handler),
        settings=settings,
    )
    close.api_key = "default-system-key"

    # 1. Initial status for Bob: he has no key of his own, so the shared key is what he dials on
    initial_status = close.operator_api_key_status("bob@example.com")
    assert initial_status["configured"] is True
    assert initial_status["is_custom"] is False
    assert initial_status["key_masked"] == "api_******-key"
    assert close.api_key_for("bob@example.com") == "default-system-key"

    # 2. Reject invalid format
    with pytest.raises(DialerError, match="Invalid Close API key format"):
        close.save_operator_api_key("bob@example.com", "bad_key")

    # 3. Reject unauthorized key from Close API
    with pytest.raises(DialerError, match="rejected this API key"):
        close.save_operator_api_key("bob@example.com", "api_invalid_key_123456789")

    # 4. Save valid key
    saved = close.save_operator_api_key("bob@example.com", "api_bob_valid_key_12345")
    assert saved["configured"] is True
    assert saved["is_custom"] is True
    assert saved["user_id"] == "user_bob_close_id_999"
    assert saved["user_name"] == "Bob Test"
    assert saved["key_masked"] == "api_******2345"

    # 5. api_key_for and user_id_for now use Bob's custom key and ID
    assert close.api_key_for("bob@example.com") == "api_bob_valid_key_12345"
    assert close.user_id_for("bob@example.com") == "user_bob_close_id_999"

    # Alice still uses system key
    assert close.api_key_for("alice@example.com") == "default-system-key"

    # Status check confirms custom key
    status = close.operator_api_key_status("bob@example.com")
    assert status["configured"] is True
    assert status["is_custom"] is True
    assert status["user_name"] == "Bob Test"

    # 6. Deleting his key hands him back to the shared one
    deleted = close.delete_operator_api_key("bob@example.com")
    assert deleted["configured"] is True
    assert deleted["is_custom"] is False
    assert close.api_key_for("bob@example.com") == "default-system-key"


def test_operator_numbers_lifecycle_and_labeling(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    # 1. Default fallback number for an operator without dedicated file
    status = dialer.operator_numbers("bob@example.com")
    assert status["count"] == 1
    assert status["numbers"][0]["label"] == "Number 1"

    # 2. Populate a dedicated multi-number pool for Bob (e.g. 3 numbers)
    state_file = tmp_path / "state" / "dialer-numbers-bob.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({
            "operator_email": "bob@example.com",
            "numbers": [
                {"sid": "PN_1", "phone_number": "+18165550143", "label": "Number 1", "locality": "Kansas City", "region": "MO"},
                {"sid": "PN_2", "phone_number": "+18605550144", "label": "Number 2", "locality": "Clinton", "region": "CT"},
                {"sid": "PN_3", "phone_number": "+17015550145", "label": "Number 3", "locality": "Hillsboro", "region": "ND"},
            ]
        })
    )

    bob_numbers = dialer.operator_numbers("bob@example.com")
    assert bob_numbers["count"] == 3
    assert bob_numbers["numbers"][0]["formatted"] == "+1 (816) 555-0143"
    assert bob_numbers["numbers"][1]["phone_number"] == "+18605550144"

    # 3. Update label / nickname for a number
    updated = dialer.update_operator_number_label("bob@example.com", "PN_1", "Midwest Line")
    assert updated["numbers"][0]["label"] == "Midwest Line"


def test_parallel_lines_assign_distinct_caller_numbers_from_pool(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    # Setup 3 numbers for Bob
    state_file = tmp_path / "state" / "dialer-numbers-bob.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({
            "operator_email": "bob@example.com",
            "numbers": [
                {"sid": "PN_1", "phone_number": "+18165550143", "label": "Number 1"},
                {"sid": "PN_2", "phone_number": "+18605550144", "label": "Number 2"},
                {"sid": "PN_3", "phone_number": "+17015550145", "label": "Number 3"},
            ]
        })
    )

    # Start a 3-line session for Bob
    session = start(dialer, harness, count=3, concurrency=3, operator_email="bob@example.com")
    attempts = [attempt_for(dialer, session, i) for i in range(3)]

    # Verify each parallel line received a distinct Caller ID and label
    assert attempts[0].caller_number == "+18165550143"
    assert attempts[0].caller_label == "Number 1"

    assert attempts[1].caller_number == "+18605550144"
    assert attempts[1].caller_label == "Number 2"

    assert attempts[2].caller_number == "+17015550145"
    assert attempts[2].caller_label == "Number 3"

    # Verify Twilio call requests used distinct "From" numbers
    twilio_calls = [item for item in harness.requests if item.url.path.endswith("/Calls.json")]
    from_numbers = [
        parse_qs(item.content.decode("utf-8"))["From"][0]
        for item in twilio_calls
        if "MachineDetection" in parse_qs(item.content.decode("utf-8"))
    ]
    assert len(set(from_numbers)) == 3
    assert "+18165550143" in from_numbers
    assert "+18605550144" in from_numbers
    assert "+17015550145" in from_numbers


def test_inbound_twiml_routes_to_operator_who_owns_to_number(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    monkeypatch.setenv("DIALER_CALLBACK_NUMBER_BOB", "+12025550188")

    state_file = tmp_path / "state" / "dialer-numbers-bob.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({
            "operator_email": "bob@example.com",
            "numbers": [
                {"sid": "PN_bob", "phone_number": "+18165550143", "label": "Number 1"},
            ]
        })
    )

    # Inbound call returning to Bob's number routes to Bob's callback destination
    twiml = dialer.inbound_twiml(caller="+12025550180", to_number="+18165550143")
    root = ElementTree.fromstring(twiml)
    number = root.find("Dial/Number")
    assert number is not None
    assert number.text == "+12025550188"


def test_voicemail_speech_drops_recording_with_one_second_pause_and_marks_played(
    tmp_path, monkeypatch
) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Please record your message after the tone.",
            },
        )
    )
    assert attempt.outcome == "voicemail"
    assert attempt.status == "voicemail-playing"
    assert attempt.voicemail_played is True
    root = ElementTree.fromstring(twiml)
    pause = root.find("Pause")
    play = root.find("Play")
    hangup = root.find("Hangup")
    assert pause is not None and pause.attrib.get("length") == "1"
    assert play is not None and "voicemail" in (play.text or "")
    assert hangup is not None


def test_amd_ignores_if_voicemail_already_played(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Leave a message at the tone",
            },
        )
    )
    assert attempt.voicemail_played is True
    post_count_before = len([
        item for item in harness.requests
        if item.method == "POST" and item.url.path.endswith(f"/{attempt.twilio_call_sid}.json")
    ])

    # Async AMD arrives after speech already dropped voicemail
    asyncio.run(
        dialer.handle_amd(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "AnsweredBy": "machine_end_beep"},
        )
    )
    post_count_after = len([
        item for item in harness.requests
        if item.method == "POST" and item.url.path.endswith(f"/{attempt.twilio_call_sid}.json")
    ])
    assert post_count_after == post_count_before


def test_ivr_menu_detected_and_hangs_up(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Thank you for calling Acme Corp. Press 1 for sales, press 2 for support, or enter your party's extension.",
            },
        )
    )
    assert attempt.outcome == "ivr"
    assert attempt.status == "completed"
    assert attempt.voicemail_played is False
    root = ElementTree.fromstring(twiml)
    assert root.find("Hangup") is not None
    assert root.find("Play") is None


def test_create_call_includes_tuned_amd_parameters(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    start(dialer, harness, count=1)

    twilio_calls = [
        item for item in harness.requests
        if item.url.path.endswith("/Calls.json") and item.method == "POST"
    ]
    prospect_calls = [
        parse_qs(item.content.decode("utf-8"))
        for item in twilio_calls
        if "MachineDetection" in parse_qs(item.content.decode("utf-8"))
    ]
    assert len(prospect_calls) == 1
    form = prospect_calls[0]
    assert form.get("MachineDetection") == ["DetectMessageEnd"]
    assert form.get("AsyncAmd") == ["true"]
    assert form.get("MachineDetectionSilenceTimeout") == ["2000"]
    assert form.get("MachineDetectionSpeechEndThreshold") == ["1000"]
    assert form.get("MachineDetectionTimeout") == ["30"]


def test_gatekeeper_screening_not_overwritten_by_amd_machine_callback(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Gatekeeper asks who is calling
    _ = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Hello, may I ask who is calling and why?",
            },
        )
    )
    assert attempt.outcome == "screening"
    assert attempt.screening_detected is True
    assert attempt.status == "screening"

    post_count_before = len([
        item for item in harness.requests
        if item.method == "POST" and item.url.path.endswith(f"/{attempt.twilio_call_sid}.json")
    ])

    # Twilio AMD fires machine_end_other because the screener sounds robotic
    asyncio.run(
        dialer.handle_amd(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "AnsweredBy": "machine_end_other"},
        )
    )

    # Must NOT have redirected to voicemail or overwritten screening state
    post_count_after = len([
        item for item in harness.requests
        if item.method == "POST" and item.url.path.endswith(f"/{attempt.twilio_call_sid}.json")
    ])
    assert post_count_after == post_count_before
    assert attempt.outcome == "screening"
    assert attempt.voicemail_played is False


def test_mailbox_full_detected_and_hangs_up_cleanly(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "The mailbox is full and cannot accept messages at this time. Goodbye.",
            },
        )
    )
    assert attempt.outcome == "mailbox-full"
    assert attempt.status == "completed"
    assert attempt.voicemail_played is False
    root = ElementTree.fromstring(twiml)
    assert root.find("Hangup") is not None
    assert root.find("Play") is None


def test_ivr_menu_classified_even_if_amd_machine_fired(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # AMD callback arrives first reporting machine_start or machine_end_other
    asyncio.run(
        dialer.handle_amd(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "AnsweredBy": "machine_start"},
        )
    )
    assert attempt.voicemail_played is False

    # Then speech recognition delivers IVR menu transcript
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "Thank you for calling. Press 1 for sales, press 2 for appointments.",
            },
        )
    )
    assert attempt.outcome == "ivr"
    assert attempt.status == "completed"
    assert attempt.voicemail_played is False
    root = ElementTree.fromstring(twiml)
    assert root.find("Hangup") is not None
    assert root.find("Play") is None


def test_greeting_prompt_immediate_playback_without_pause(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    _save(dialer, "greeting", seconds=0.8)
    twiml = dialer._gather_twiml(attempt, "", slot="greeting")
    gather = ElementTree.fromstring(twiml).find("Gather")
    assert gather is not None
    pause = gather.find("Pause")
    play = gather.find("Play")
    assert pause is None
    assert play is not None and "greeting" in (play.text or "")

    # answer_twiml keeps gather free of audio to connect humans instantly
    answer_twiml = dialer.answer_twiml(attempt.id)
    answer_gather = ElementTree.fromstring(answer_twiml).find("Gather")
    assert answer_gather is not None
    assert answer_gather.find("Play") is None


def test_operator_twilio_settings_lifecycle(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    op = "bob@example.com"

    # 1. Default organization settings
    initial = dialer.operator_twilio_settings(op)
    assert initial["configured"] is True
    assert initial["is_custom"] is False
    assert "AC" in initial["account_sid_masked"]
    assert "SK" in initial["api_key_sid_masked"]

    # 2. Validation of bad inputs
    with pytest.raises(LiveDialerError, match="Account SID"):
        dialer.update_operator_twilio_settings(op, "bad_sid", "SK" + "a" * 32, "secret123456789012")

    # 3. Save custom credentials
    custom_ac = "AC" + "9" * 32
    custom_api = "SK" + "8" * 32
    saved = dialer.update_operator_twilio_settings(
        op, custom_ac, custom_api, "custom_secret_123456", phone_number="+18165550100"
    )
    assert saved["configured"] is True
    assert saved["is_custom"] is True
    assert saved["phone_number"] == "+18165550100"

    # 4. Verify credentials resolved for operator
    creds = dialer._twilio_credentials_for_operator(op)
    assert creds[0] == custom_ac
    assert creds[1] == custom_api

    # 5. Delete custom settings (reverts to default)
    reverted = dialer.delete_operator_twilio_settings(op)
    assert reverted["is_custom"] is False
    assert dialer._twilio_credentials_for_operator(op)[0] == dialer.account_sid


def test_operator_buy_and_delete_number(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    op = "bob@example.com"

    # Buy a number in area code 816
    result = asyncio.run(dialer.buy_operator_number(op, area_code="816"))
    assert result["ok"] is True
    num = result["number"]
    assert num["phone_number"] == "+18165550191"
    assert num["health"]["status"] == "fresh"
    assert num["health"]["badge"] == "Fresh"

    # Verify both the original primary number and the new number are in the pool
    pool = dialer.operator_numbers(op)["numbers"]
    assert len(pool) == 2
    assert pool[0]["label"] == "Number 1"
    assert pool[1]["label"] == "Number 2"
    assert pool[1]["phone_number"] == "+18165550191"

    # Buy another number and verify it does NOT substitute the existing ones
    result2 = asyncio.run(dialer.buy_operator_number(op, area_code="816"))
    assert result2["ok"] is True
    assert result2["number"]["label"] == "Number 3"
    assert result2["number"]["phone_number"] == "+18165550192"
    pool_after_second = dialer.operator_numbers(op)["numbers"]
    assert len(pool_after_second) == 3
    assert [n["label"] for n in pool_after_second] == ["Number 1", "Number 2", "Number 3"]

    # Delete the purchased number
    deleted = asyncio.run(dialer.delete_operator_number(op, num["sid"]))
    assert deleted["ok"] is True
    assert deleted["phone_number"] == "+18165550191"

    # Verify number is no longer in pool
    new_pool = dialer.operator_numbers(op)["numbers"]
    assert not any(item["phone_number"] == "+18165550191" for item in new_pool)
    assert len(new_pool) == 2


def test_the_main_line_can_be_switched_and_a_cooked_one_deleted(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    op = "alice@example.com"
    bought = asyncio.run(dialer.buy_operator_number(op, area_code="816"))["number"]
    pool = dialer.operator_numbers(op)["numbers"]
    main = next(item for item in pool if item["primary"])
    assert main["phone_number"] == "+12025550100"

    # Deleting the main line hands it to the other number first, then releases it.
    result = asyncio.run(dialer.delete_operator_number(op, main["sid"]))
    assert result["new_main_line"] == bought["phone_number"]
    assert dialer.caller_number == bought["phone_number"]
    webhook = [r for r in harness.requests if r.method == "POST" and f"/IncomingPhoneNumbers/{bought['sid']}" in r.url.path]
    assert webhook, "the new main line must take the callbacks"
    assert any(r.method == "DELETE" and main["sid"] in r.url.path for r in harness.requests)
    assert [(item["phone_number"], item["primary"]) for item in dialer.operator_numbers(op)["numbers"]] == [
        (bought["phone_number"], True)
    ]

    # Its last number cannot go: there would be no main line left.
    with pytest.raises(LiveDialerError, match="only number"):
        asyncio.run(dialer.delete_operator_number(op, bought["sid"]))

    # The switch survives a restart, and the softphone leg comes from the new line.
    restarted = LiveDialer(dialer.settings, dialer.close_dialer, transport=httpx.MockTransport(harness.handler))
    assert restarted.caller_number == bought["phone_number"]


def test_any_number_can_be_made_the_main_line(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    op = "alice@example.com"
    bought = asyncio.run(dialer.buy_operator_number(op, area_code="816"))["number"]
    numbers = asyncio.run(dialer.set_main_line(op, bought["sid"]))["numbers"]
    assert [item["primary"] for item in numbers] == [False, True]
    # The old main line stays one of the numbers, and nothing was released.
    assert not any(r.method == "DELETE" for r in harness.requests)
    with pytest.raises(LiveDialerError, match="not one of yours"):
        asyncio.run(dialer.set_main_line("bob@example.com", bought["sid"]))


def test_number_health_assessment_indicators(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    test_num = "+18165550777"

    # 1. Zero dials -> fresh
    health = dialer._calculate_number_health(test_num)
    assert health["status"] == "fresh"
    assert health["badge"] == "Fresh"
    assert health["total_calls"] == 0

    # 2. Add 10 calls: 3 human connects, 7 voicemails -> healthy (30% connect rate)
    for i in range(10):
        attempt_id = f"att_health_{i}"
        outcome = "human-bridged" if i < 3 else "voicemail"
        dialer.attempts[attempt_id] = DialAttempt(
            id=attempt_id,
            session_id="ds_test",
            contact_id=f"cont_{i}",
            lead_id=f"lead_{i}",
            name="Test Lead",
            company="Test Co",
            phone=f"+1555000{i:04d}",
            screening_reply="Hello from testing",
            caller_number=test_num,
            caller_label="Number 1",
            outcome=outcome,
            human_detected=i < 3,
            status="completed",
        )

    health_healthy = dialer._calculate_number_health(test_num)
    assert health_healthy["status"] == "healthy"
    assert health_healthy["connect_rate"] == 30.0

    # 3. Add 15 more calls: all busy or failed -> cooked (> 35% block rate)
    for i in range(10, 25):
        attempt_id = f"att_health_{i}"
        dialer.attempts[attempt_id] = DialAttempt(
            id=attempt_id,
            session_id="ds_test",
            contact_id=f"cont_{i}",
            lead_id=f"lead_{i}",
            name="Test Lead",
            company="Test Co",
            phone=f"+1555000{i:04d}",
            screening_reply="Hello from testing",
            caller_number=test_num,
            caller_label="Number 1",
            outcome="busy",
            status="busy",
        )

    health_cooked = dialer._calculate_number_health(test_num)
    assert health_cooked["status"] == "cooked"
    assert health_cooked["badge"] == "Cooked"
    assert "Carrier spam" in health_cooked["message"]


def test_abandonment_rate_and_session_stats(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=2)
    attempts = [attempt_for(dialer, session, index) for index in (0, 1)]

    async def race() -> list[str]:
        return list(
            await asyncio.gather(
                *(
                    dialer.handle_speech(
                        attempt.id,
                        {
                            "CallSid": attempt.twilio_call_sid,
                            "SpeechResult": "Hello, this is person speaking",
                            "_IdempotencyToken": f"token-{index}",
                        },
                    )
                    for index, attempt in enumerate(attempts)
                )
            )
        )

    _ = asyncio.run(race())
    bridged = [a for a in attempts if a.outcome == "human-bridged"]
    abandoned = [a for a in attempts if a.abandoned]
    assert len(bridged) == 1
    assert len(abandoned) == 1

    # Verify session stats
    session_data = dialer.session(session["id"])
    assert "stats" in session_data
    stats = session_data["stats"]
    assert stats["attempts"] == 2
    assert stats["human_connects"] == 2
    assert stats["human_answered"] == 1
    assert stats["human_missed"] == 1
    assert stats["abandonment_rate"] == 50.0
    assert stats["connect_rate"] == 50.0


def test_how_can_i_help_greeting_is_classified_as_human(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=2)
    attempt = attempt_for(dialer, session)

    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {
                "CallSid": attempt.twilio_call_sid,
                "SpeechResult": "How can I help?",
            },
        )
    )
    assert attempt.human_detected is True
    assert attempt.outcome == "human-bridged"
    assert attempt.status == "bridged"
    assert "Conference" in twiml
    assert "screening" not in twiml


def test_checkpoint_contact_history_tracks_terminal_outcomes_only(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=2, concurrency=2)
    attempts = [attempt_for(dialer, session, i) for i in (0, 1)]

    # Attempt 0 answers human and connects
    asyncio.run(
        dialer.handle_speech(
            attempts[0].id,
            {"CallSid": attempts[0].twilio_call_sid, "SpeechResult": "Hello, Alex speaking"},
        )
    )
    # Complete the active call so attempt 0 reaches terminal status
    asyncio.run(dialer.complete_active_call(session["id"]))

    checkpoint = dialer._get_checkpoint("alice@example.com", harness.smart_views[0]["id"])
    assert checkpoint is not None
    # Winner was connected and completed: recorded and retired
    assert attempts[0].contact_id in checkpoint.contact_history
    assert attempts[0].contact_id in checkpoint.attempted_contact_ids
    assert checkpoint.contact_history[attempts[0].contact_id].retired is True

    # Peer was canceled while ringing (canceled-after-human): must NOT be retired
    assert attempts[1].contact_id not in checkpoint.attempted_contact_ids
    assert (
        attempts[1].contact_id not in checkpoint.contact_history
        or not checkpoint.contact_history[attempts[1].contact_id].retired
    )


def _drop_blair_while_alex_wins(tmp_path, monkeypatch):
    """Two lines: Blair picks up, Alex says hello first and is put through, Blair is dropped."""
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    alex, blair = (attempt_for(dialer, session, i) for i in (0, 1))
    asyncio.run(
        dialer.handle_status(blair.id, {"CallSid": blair.twilio_call_sid, "CallStatus": "in-progress"})
    )
    asyncio.run(
        dialer.handle_speech(
            alex.id, {"CallSid": alex.twilio_call_sid, "SpeechResult": "Hello, this is Alex"}
        )
    )
    return harness, dialer, dialer.sessions[session["id"]], alex, blair


def _dialed_after(dialer, sess, *known):
    return [dialer.attempts[item] for item in sess.attempt_ids if item not in {a.id for a in known}]


def test_a_dropped_person_is_called_back_once_alone_after_the_first_call_hangs_up(
    tmp_path, monkeypatch
) -> None:
    _, dialer, sess, alex, blair = _drop_blair_while_alex_wins(tmp_path, monkeypatch)
    assert blair.outcome == "dropped-line" and blair.abandoned
    assert sess.queue[sess.next_index]["contact_id"] == blair.contact_id
    assert sess.queue[sess.next_index]["callback"] is True

    # Alex's call ends. Blair's first call is still playing "let me call you right back",
    # so nobody is dialed yet: on 2026-09-21 the call back rang over that message.
    asyncio.run(dialer.complete_active_call(sess.id))
    checkpoint = dialer._get_checkpoint("alice@example.com", sess.smart_view_id)
    assert checkpoint is not None
    assert blair.contact_id not in checkpoint.attempted_contact_ids  # a drop is not retired
    assert _dialed_after(dialer, sess, alex, blair) == []

    # Blair's first call hangs up: the call back goes out, and it goes out alone.
    asyncio.run(
        dialer.handle_status(blair.id, {"CallSid": blair.twilio_call_sid, "CallStatus": "completed"})
    )
    dialed = _dialed_after(dialer, sess, alex, blair)
    assert [(a.contact_id, a.callback) for a in dialed] == [(blair.contact_id, True)]

    # Nobody is called back twice in a session, whatever happens to the call back.
    callback = dialed[0]
    dialer._prioritize_dropped_contact(sess, callback)
    assert blair.contact_id not in [c["contact_id"] for c in sess.queue[sess.next_index :]]

    # Once the call back is over, the list carries on in parallel.
    asyncio.run(
        dialer.handle_status(callback.id, {"CallSid": callback.twilio_call_sid, "CallStatus": "no-answer"})
    )
    dialed = _dialed_after(dialer, sess, alex, blair, callback)
    assert [(a.name, a.callback) for a in dialed] == [("Casey Demo", False)]


def test_a_call_back_is_not_held_up_forever_by_a_lost_webhook(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    from parallel_dialer.live_dialer import CALLBACK_STALE_SECONDS

    _, dialer, sess, alex, blair = _drop_blair_while_alex_wins(tmp_path, monkeypatch)
    asyncio.run(dialer.complete_active_call(sess.id))
    assert _dialed_after(dialer, sess, alex, blair) == []
    # Twilio never reports Blair's first call as ended. Once it has been quiet long
    # enough, the call back goes anyway rather than stalling the whole list behind it.
    blair.updated_at = (datetime.now(UTC) - timedelta(seconds=CALLBACK_STALE_SECONDS + 1)).isoformat()
    asyncio.run(dialer._advance_session(sess.id))
    assert [(a.contact_id, a.callback) for a in _dialed_after(dialer, sess, alex, blair)] == [
        (blair.contact_id, True)
    ]


def test_an_answering_machine_keeps_its_voicemail_when_a_person_wins(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    alex, blair = (attempt_for(dialer, session, i) for i in (0, 1))
    asyncio.run(
        dialer.handle_amd(blair.id, {"CallSid": blair.twilio_call_sid, "AnsweredBy": "machine_end_beep"})
    )
    assert blair.voicemail_played
    asyncio.run(
        dialer.handle_speech(
            alex.id, {"CallSid": alex.twilio_call_sid, "SpeechResult": "Hello, this is Alex"}
        )
    )
    sess = dialer.sessions[session["id"]]
    assert sess.human_attempt_id == alex.id
    # The machine is left to take our message: not dropped, not counted, not dialed again.
    assert blair.outcome == "voicemail" and blair.status == "voicemail-playing"
    assert not blair.abandoned
    assert blair.contact_id not in [c["contact_id"] for c in sess.queue[sess.next_index :]]
    assert dialer.session(sess.id)["stats"]["human_missed"] == 0


def test_the_abandonment_rate_counts_people_not_machines(tmp_path, monkeypatch) -> None:
    _, dialer, sess, _, blair = _drop_blair_while_alex_wins(tmp_path, monkeypatch)
    stats = dialer.session(sess.id)["stats"]
    assert (stats["human_answered"], stats["human_missed"], stats["abandonment_rate"]) == (1, 1, 50.0)
    # What sessions before the fix recorded for a machine that was dropped mid-voicemail.
    blair.voicemail_played = True
    stats = dialer.session(sess.id)["stats"]
    assert (stats["human_missed"], stats["abandonment_rate"]) == (0, 0.0)


def test_stop_is_not_undone_by_the_calls_it_cancels(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    sess = dialer.sessions[session["id"]]
    first = attempt_for(dialer, session)
    sess.status = "stopping"  # Stop has begun and is hanging up the lines
    asyncio.run(
        dialer.handle_status(first.id, {"CallSid": first.twilio_call_sid, "CallStatus": "canceled"})
    )
    # The cancelled call reporting back neither revives the session nor dials anyone.
    assert sess.status == "stopping"
    assert [a for a in sess.attempt_ids if a != first.id] == []
    assert len(harness.created_calls) == 2  # the operator leg and the first contact only


def test_a_call_placed_while_stop_runs_is_hung_up(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    sess = dialer.sessions[session["id"]]
    late = DialAttempt(
        id="da_" + "f" * 32,
        session_id=sess.id,
        contact_id="cont_2",
        lead_id="lead_2",
        name="Blair Demo",
        company="Demo Two",
        phone="+12025550149",
        screening_reply=sess.screening_reply,
    )
    dialer.attempts[late.id] = late
    sess.attempt_ids.append(late.id)
    # Stop reached this attempt before Twilio answered the create, so it had no call id.
    asyncio.run(dialer.stop_session(sess.id))
    assert late.status == "completed" and not late.twilio_call_sid
    asyncio.run(dialer._create_call(late))
    # The call that was created anyway is hung up at once.
    assert harness.call_statuses[late.twilio_call_sid]["status"] == "completed"


def test_the_state_written_on_every_event_carries_no_queue(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    queue_file = dialer.queue_dir / f"{session['id']}.json"

    def saved_session() -> dict:
        state = json.loads(dialer.state_path.read_text(encoding="utf-8"))
        return next(item for item in state["sessions"] if item["id"] == session["id"])

    # On 2026-09-21 every Start's whole Smart View went into this file, written on every
    # call event: 10 MB, 533 ms a write, and Twilio gave up on 200 webhooks in an hour.
    assert saved_session()["queue"] == []
    assert len(json.loads(queue_file.read_text(encoding="utf-8"))) == 3
    # The queue file is rewritten only when the queue changes, not on every event.
    before = queue_file.stat().st_mtime_ns
    dialer._persist_state()
    assert queue_file.stat().st_mtime_ns == before
    # A finished session keeps no queue anywhere.
    asyncio.run(dialer.stop_session(session["id"]))
    assert not queue_file.exists()
    restarted = LiveDialer(dialer.settings, dialer.close_dialer, transport=httpx.MockTransport(harness.handler))
    assert restarted.sessions[session["id"]].status == "stopped"
    assert restarted.session(session["id"])["stats"]["attempts"] == 1


def test_a_running_session_carries_on_down_its_list_after_a_restart(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    first = attempt_for(dialer, session)
    restarted = LiveDialer(dialer.settings, dialer.close_dialer, transport=httpx.MockTransport(harness.handler))
    restored = restarted.sessions[session["id"]]
    assert [item["name"] for item in restored.queue] == ["Alex Demo", "Blair Demo", "Casey Demo"]
    assert restored.next_index == 1
    asyncio.run(
        restarted.handle_status(first.id, {"CallSid": first.twilio_call_sid, "CallStatus": "no-answer"})
    )
    assert [restarted.attempts[item].name for item in restored.attempt_ids] == ["Alex Demo", "Blair Demo"]


def test_an_older_state_file_with_queues_inside_still_resumes(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=1)
    # What the service wrote before 2026-09-21: the queue inside the state file itself.
    state = json.loads(dialer.state_path.read_text(encoding="utf-8"))
    for item in state["sessions"]:
        if item["id"] == session["id"]:
            item["queue"] = dialer.sessions[session["id"]].queue
    dialer.state_path.write_text(json.dumps(state), encoding="utf-8")
    dialer._queue_path(session["id"]).unlink()
    restarted = LiveDialer(dialer.settings, dialer.close_dialer, transport=httpx.MockTransport(harness.handler))
    assert len(restarted.sessions[session["id"]].queue) == 3
    restarted._persist_state()
    assert restarted._queue_path(session["id"]).exists()


def test_active_opportunity_leads_are_excluded_from_dialing(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    # lead_1 has an active deal
    harness.active_opportunities = [
        {"id": "oppo_1", "lead_id": "lead_1", "status_type": "active"}
    ]
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    contacts_payload = dialer.close_dialer.contacts(limit=10, smart_view_id=harness.smart_views[0]["id"])
    c1 = next(c for c in contacts_payload["contacts"] if c["lead_id"] == "lead_1")
    c2 = next(c for c in contacts_payload["contacts"] if c["lead_id"] == "lead_2")
    assert c1["has_active_deal"] is True
    assert "Active opportunity" in c1["deal_reason"]
    assert c2["has_active_deal"] is False

    decorated = dialer.decorate_contacts(contacts_payload)
    dec_c1 = next(c for c in decorated["contacts"] if c["lead_id"] == "lead_1")
    assert dec_c1["live_allowed"] is False
    assert dec_c1["dialer_blocked"] is True

    # When starting a session, lead_1 must not be in the queue
    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=10,
            concurrency=2,
            screening_reply="Test screening reply with enough words for dialer.",
            operator_target="browser",
        )
    )
    queued_lead_ids = [c["lead_id"] for c in dialer.sessions[session["id"]].queue]
    assert "lead_1" not in queued_lead_ids
    assert "lead_2" in queued_lead_ids


def test_previously_contacted_leads_excluded_from_queue(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    # lead_1 had a previous conversation (call duration >= 30s)
    harness.previously_contacted_leads = [{"id": "lead_1"}]
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    contacts_payload = dialer.close_dialer.contacts(limit=10, smart_view_id=harness.smart_views[0]["id"])
    c1 = next(c for c in contacts_payload["contacts"] if c["lead_id"] == "lead_1")
    c2 = next(c for c in contacts_payload["contacts"] if c["lead_id"] == "lead_2")
    assert c1["has_active_deal"] is True
    assert c1["already_contacted"] is True
    assert "Previously contacted" in c1["deal_reason"]
    assert ">= 30s" in c1["deal_reason"]
    assert c2["has_active_deal"] is False
    assert c2["already_contacted"] is False

    decorated = dialer.decorate_contacts(contacts_payload)
    dec_c1 = next(c for c in decorated["contacts"] if c["lead_id"] == "lead_1")
    assert dec_c1["live_allowed"] is False
    assert dec_c1["dialer_blocked"] is True

    # When starting a session, lead_1 must not be in the queue
    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=10,
            concurrency=2,
            screening_reply="Test screening reply with enough words for dialer.",
            operator_target="browser",
        )
    )
    queued_lead_ids = [c["lead_id"] for c in dialer.sessions[session["id"]].queue]
    assert "lead_1" not in queued_lead_ids
    assert "lead_2" in queued_lead_ids


def test_not_interested_leads_excluded_from_dialing_queue(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    orig_lead_rows = harness.close_lead_rows
    def custom_lead_rows():
        rows = orig_lead_rows()
        for r in rows:
            if r["id"] == "lead_1":
                r["status_label"] = "Not Interested"
        return rows
    harness.close_lead_rows = custom_lead_rows
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    contacts_payload = dialer.close_dialer.contacts(limit=10, smart_view_id=harness.smart_views[0]["id"])
    c1 = next(c for c in contacts_payload["contacts"] if c["lead_id"] == "lead_1")
    c2 = next(c for c in contacts_payload["contacts"] if c["lead_id"] == "lead_2")
    assert c1["has_active_deal"] is True
    assert "Not Interested" in c1["deal_reason"]
    assert c2["has_active_deal"] is False

    session = asyncio.run(
        dialer.start_session(
            smart_view_id=harness.smart_views[0]["id"],
            max_contacts=10,
            concurrency=2,
            screening_reply="Test screening reply with enough words for dialer.",
            operator_target="browser",
        )
    )
    queued_lead_ids = [c["lead_id"] for c in dialer.sessions[session["id"]].queue]
    assert "lead_1" not in queued_lead_ids
    assert "lead_2" in queued_lead_ids


def test_disqualify_active_call_updates_close_lead_status(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = dialer.attempts[session["attempts"][0]["id"]]

    # Connect operator and human
    attempt.twilio_call_sid = "CA_lead_dnc"
    attempt.status = "human-bridged"
    session_obj = dialer.sessions[session["id"]]
    session_obj.human_attempt_id = attempt.id
    session_obj.status = "human-connected"

    # Operator clicks Not Interested button
    asyncio.run(dialer.disqualify_active_call(session["id"], disposition="Not Interested"))
    assert attempt.status == "completed"
    assert attempt.outcome == "not-interested"
    assert attempt.operator_disqualified is True
    assert attempt.disposition == "Not Interested"

    # Close PUT /lead/ was executed
    lead_puts = [p for p in harness.close_puts if p.get("status_label") == "Not Interested"]
    assert len(lead_puts) == 1

    # Call activity logged with operator note
    assert attempt.close_logged is True
    logged_post = next(p for p in harness.close_posts if p.get("lead_id") == attempt.lead_id)
    assert "marked Not Interested by operator" in logged_post["note_html"]


def test_disqualify_active_api_endpoint(tmp_path, monkeypatch) -> None:
    from starlette.testclient import TestClient
    from parallel_dialer.api import create_app
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    app = create_app(
        settings=dialer.settings,
        close_dialer_instance=dialer.close_dialer,
        live_dialer_instance=dialer,
        secret=SIGNING_SECRET,
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {ACCESS_KEY}"}
    start_resp = client.post(
        "/dialer/api/start",
        headers=headers,
        json={
            "smart_view_id": harness.smart_views[0]["id"],
            "max_contacts": 1,
            "concurrency": 1,
            "screening_reply": "This is a test screening reply.",
        },
    )
    session_id = start_resp.json()["session"]["id"]
    operator_sid = dialer.sessions[session_id].operator_call_sid
    session_sig = dialer._session_signature(session_id)
    client.post(
        "/twilio/dialer/operator-answer",
        params={"session_id": session_id, "sig": session_sig},
        data={"CallSid": operator_sid},
    )
    attempt = attempt_for(dialer, dialer.session(session_id))
    dialer.sessions[session_id].human_attempt_id = attempt.id
    dialer.sessions[session_id].status = "human-connected"
    attempt.status = "human-bridged"

    disq_resp = client.post(
        f"/dialer/api/session/{session_id}/disqualify-active",
        headers=headers,
        json={"disposition": "Not Interested"},
    )
    assert disq_resp.status_code == 200
    assert attempt.status == "completed"
    assert attempt.outcome == "not-interested"
    assert attempt.operator_disqualified is True
    lead_puts = [p for p in harness.close_puts if p.get("status_label") == "Not Interested"]
    assert len(lead_puts) == 1


def test_local_presence_caller_id_matches_destination_area_code(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    pool = [
        {"phone_number": "+18165550100", "label": "Missouri (816)"},
        {"phone_number": "+12025550100", "label": "DC (202)"},
    ]

    # Matching area code 816
    num, label = dialer._select_caller_number("+18165550999", pool, "Default")
    assert num == "+18165550100"
    assert label == "Missouri (816)"

    # Matching area code 202
    num, label = dialer._select_caller_number("2025550888", pool, "Default")
    assert num == "+12025550100"
    assert label == "DC (202)"

    # Non-matching area code falls back to empty tuple for caller fallback
    num, label = dialer._select_caller_number("+14155550777", pool, "Default")
    assert num == ""
    assert label == ""


def test_real_call_transcripts_classification_matrix(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    cases = [
        # Carrier transfer announcements -> transfer
        ("Please hold while we transfer your call to the next available agent.", "transfer"),
        ("Your call is being forwarded, please wait.", "transfer"),
        ("Please wait while I connect you.", "transfer"),
        # Voicemails starting with hello -> voicemail
        ("Hello, you have reached the voicemail of Dr. Jones. Please leave a message after the tone.", "voicemail"),
        ("Hi, I am currently unavailable. Please leave your name and number.", "voicemail"),
        # Screening prompts -> screening
        ("Please state your name and the reason for your call.", "screening"),
        ("Google Call Screen: May I ask who is calling?", "screening"),
        # Fast-path human greetings -> human (no OpenAI call needed)
        ("Hello?", "human"),
        ("Speaking", "human"),
        ("Hi, this is Dr. Roberts", "human"),
        ("Good morning, Acme Healthcare", "human"),
        ("Yeah, who's this?", "human"),
        ("Yes, how can I help you?", "human"),
        # Mailbox full -> mailbox-full
        ("The mailbox is full and cannot accept messages at this time.", "mailbox-full"),
        # IVR -> ivr
        ("Press 1 for front desk, press 2 for appointments.", "ivr"),
    ]

    for transcript, expected_kind in cases:
        kind, reply = asyncio.run(dialer._classify_transcript(attempt, transcript))
        assert kind == expected_kind, f"Failed on transcript: {transcript!r} (expected {expected_kind}, got {kind})"
        if expected_kind == "screening":
            assert reply == attempt.screening_reply
        elif expected_kind in {"human", "transfer", "voicemail", "ivr", "mailbox-full"}:
            assert reply == ""

    # Verify that all fast-path classifications did NOT invoke OpenAI
    assert len(harness.openai_payloads) == 0


def test_stream_worker_answer_twiml_generates_media_stream(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.stream_worker_url = "https://stream-worker.example.workers.dev"

    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    twiml = dialer.answer_twiml(attempt.id)

    root = ElementTree.fromstring(twiml)
    assert root.tag == "Response"
    connect = root.find("Connect")
    assert connect is not None
    stream = connect.find("Stream")
    assert stream is not None
    assert "wss://stream-worker.example.workers.dev/stream" in stream.attrib["url"]
    assert f"attempt_id={attempt.id}" in stream.attrib["url"]


def test_stream_worker_callback_bridges_human(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    res = asyncio.run(
        dialer.handle_stream_callback(attempt.id, "human", "Hello this is Dr. Smith")
    )
    assert res["status"] == "bridged"
    assert attempt.transcript == ["Hello this is Dr. Smith"]
    # Twilio API was called to redirect the call to conference
    call_posts = [
        p for p in harness.requests
        if f"/Calls/{attempt.twilio_call_sid}.json" in p.url.path and p.method == "POST"
    ]
    assert len(call_posts) >= 1


def test_stream_worker_callback_handles_voicemail_and_ivr(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    start(dialer, harness, count=2, concurrency=2)
    attempts = list(dialer.attempts.values())

    vm_res = asyncio.run(
        dialer.handle_stream_callback(attempts[0].id, "voicemail", "Please leave a message")
    )
    assert vm_res["status"] == "voicemail"
    assert attempts[0].voicemail_detected is True

    ivr_res = asyncio.run(
        dialer.handle_stream_callback(attempts[1].id, "ivr", "Press 1 for receptionist")
    )
    assert ivr_res["status"] == "ivr"
    assert attempts[1].status == "completed"


def test_dropped_recording_save_and_duration_budget(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    # Under 6.0s succeeds
    meta = _save(dialer, "dropped", seconds=3.0)
    assert meta["configured"] is True
    assert dialer.recording_metadata("dropped")["configured"] is True

    # Over 6.0s is rejected
    with pytest.raises(LiveDialerError, match="must be under 6.0 seconds"):
        _save(dialer, "dropped", seconds=6.5)


def test_dropped_line_collision_plays_natural_speech_fallback(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    attempts = [attempt_for(dialer, session, i) for i in (0, 1)]

    # Both lines answer
    for att in attempts:
        asyncio.run(
            dialer.handle_status(
                att.id,
                {"CallSid": att.twilio_call_sid, "CallStatus": "in-progress"},
            )
        )

    # Attempt 0 answers speech first and wins operator bridge
    asyncio.run(
        dialer.handle_speech(
            attempts[0].id,
            {"CallSid": attempts[0].twilio_call_sid, "SpeechResult": "Hello, this is Dr. Alex"},
        )
    )
    assert attempts[0].outcome == "human-bridged"
    assert attempts[1].outcome == "dropped-line"
    sess = dialer.sessions[session["id"]]
    assert sess.queue[sess.next_index]["contact_id"] == attempts[1].contact_id

    # Competitor attempt 1 was redirected to play natural speech fallback
    redirect_posts = [
        p for p in harness.requests
        if f"/Calls/{attempts[1].twilio_call_sid}.json" in p.url.path and p.method == "POST"
    ]
    assert len(redirect_posts) >= 1
    twiml_sent = parse_qs(redirect_posts[0].content.decode("utf-8"))["Twiml"][0]
    assert "<Say>" in twiml_sent
    assert "cannot hear you, let me call you right back" in twiml_sent
    assert "<Hangup/>" in twiml_sent


def test_dropped_line_collision_plays_custom_recording_and_stream_callback(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    _save(dialer, "dropped", seconds=2.5)

    session = start(dialer, harness, count=3, concurrency=2)
    attempts = [attempt_for(dialer, session, i) for i in (0, 1)]

    # Attempt 0 is bridged with operator
    attempts[0].status = "bridged"
    attempts[0].human_detected = True
    session_obj = dialer.sessions[session["id"]]
    session_obj.human_attempt_id = attempts[0].id
    session_obj.status = "human-connected"

    # Attempt 1 is in-progress and detects human via stream callback
    attempts[1].status = "in-progress"
    res1 = asyncio.run(
        dialer.handle_stream_callback(attempts[1].id, "human", "Hello this is Blair")
    )
    assert res1["status"] == "dropped-line-played"
    assert attempts[1].outcome == "dropped-line"
    assert session_obj.queue[session_obj.next_index]["contact_id"] == attempts[1].contact_id

    # Twilio API was posted to redirect attempt 1 to play custom dropped recording
    redirect_posts = [
        p for p in harness.requests
        if f"/Calls/{attempts[1].twilio_call_sid}.json" in p.url.path and p.method == "POST"
    ]
    assert len(redirect_posts) >= 1
    twiml_sent = parse_qs(redirect_posts[0].content.decode("utf-8"))["Twiml"][0]
    assert "<Play>" in twiml_sent
    assert "recording-media/dropped" in twiml_sent
    assert "<Hangup/>" in twiml_sent


def test_dropped_line_collision_handle_speech_race_returns_twiml(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    _save(dialer, "dropped", seconds=2.5)

    session = start(dialer, harness, count=3, concurrency=2)
    attempts = [attempt_for(dialer, session, i) for i in (0, 1)]

    # Attempt 0 is bridged
    attempts[0].status = "bridged"
    attempts[0].human_detected = True
    session_obj = dialer.sessions[session["id"]]
    session_obj.human_attempt_id = attempts[0].id
    session_obj.status = "human-connected"

    # Attempt 1 calls handle_speech
    attempts[1].status = "in-progress"
    twiml = asyncio.run(
        dialer.handle_speech(
            attempts[1].id,
            {"CallSid": attempts[1].twilio_call_sid, "SpeechResult": "Hello this is Blair"},
        )
    )
    assert attempts[1].outcome == "dropped-line"
    assert "<Play>" in twiml
    assert "recording-media/dropped" in twiml
    assert "<Hangup/>" in twiml


def test_close_call_notes_when_called_before(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    configure(monkeypatch)
    harness.close_call_activities = [
        {
            "id": "acti_call_1",
            "contact_id": "cont_1",
            "lead_id": "lead_1",
            "duration": 45,
            "user_name": "Alice Example",
            "date_created": "2026-09-18T14:30:00+00:00",
            "direction": "outbound",
            "status": "completed",
            "note": "Spoke to office manager. Scheduled demo callback.",
        }
    ]
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"

    result = close.call_notes(contact_id="cont_1", lead_id="lead_1")
    assert result["ok"] is True
    assert result["has_called_before"] is True
    assert result["total_calls"] == 1
    notes = result["call_notes"]
    assert len(notes) == 1
    assert notes[0]["id"] == "acti_call_1"
    assert notes[0]["duration"] == 45
    assert notes[0]["duration_formatted"] == "45s"
    assert notes[0]["user_name"] == "Alice Example"
    assert "office manager" in notes[0]["note"]


def test_close_call_notes_when_never_called(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    configure(monkeypatch)
    harness.close_call_activities = []
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"

    result = close.call_notes(contact_id="cont_never_called", lead_id="lead_99")
    assert result["ok"] is True
    assert result["has_called_before"] is False
    assert result["total_calls"] == 0
    assert result["call_notes"] == []


def test_api_contact_call_notes_endpoint(tmp_path, monkeypatch) -> None:
    from starlette.testclient import TestClient

    from parallel_dialer.api import create_app
    from parallel_dialer.config import Settings

    harness = ProviderHarness()
    configure(monkeypatch)
    harness.close_call_activities = [
        {
            "id": "acti_call_2",
            "contact_id": "cont_test",
            "lead_id": "lead_test",
            "duration": 120,
            "user_name": "Bob",
            "date_created": "2026-09-19T10:00:00+00:00",
            "direction": "outbound",
            "status": "completed",
            "note_html": "<p>Requested one-pager email and pricing.</p>",
        }
    ]
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    settings = Settings(root=tmp_path / "app", allowed_emails=ALLOWED, profile=PROFILE)
    live = LiveDialer(settings, close, transport=httpx.MockTransport(harness.handler))
    app = create_app(settings, close_dialer_instance=close, live_dialer_instance=live, secret=SIGNING_SECRET)
    client = TestClient(app)
    res = client.get(
        "/dialer/api/contacts/cont_test/call-notes",
        params={"lead_id": "lead_test"},
        headers={"Authorization": f"Bearer {ACCESS_KEY}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["has_called_before"] is True
    assert data["total_calls"] == 1
    assert "one-pager email" in data["call_notes"][0]["note"]
    assert data["call_notes"][0]["duration_formatted"] == "2m"


def test_api_contact_call_notes_fallback_to_checkpoint(tmp_path, monkeypatch) -> None:
    from starlette.testclient import TestClient

    from parallel_dialer.api import create_app
    from parallel_dialer.config import Settings
    from parallel_dialer.live_dialer import ContactHistory, DialCheckpoint

    harness = ProviderHarness()
    configure(monkeypatch)
    harness.close_call_activities = []  # No Close records
    close = CloseDialer(transport=httpx.MockTransport(harness.handler))
    close.api_key = "close-test-key"
    settings = Settings(root=tmp_path / "app", allowed_emails=ALLOWED, profile=PROFILE)
    live = LiveDialer(settings, close, transport=httpx.MockTransport(harness.handler))
    # Inject contact history into checkpoint
    cp = DialCheckpoint(smart_view_id="save_123", smart_view_name="Test View")
    cp.contact_history["cont_fallback_1"] = ContactHistory(
        contact_id="cont_fallback_1",
        attempts=2,
        last_outcome="busy",
        last_attempted_at="2026-09-18T16:00:00+00:00",
    )
    live.checkpoints["alice@example.com:save_123"] = cp

    app = create_app(settings, close_dialer_instance=close, live_dialer_instance=live, secret=SIGNING_SECRET)
    client = TestClient(app)
    res = client.get(
        "/dialer/api/contacts/cont_fallback_1/call-notes",
        headers={"Authorization": f"Bearer {ACCESS_KEY}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["has_called_before"] is True
    assert data["total_calls"] == 2
    assert "busy" in data["call_notes"][0]["note"]
    assert data["call_notes"][0]["source"] == "dialer_checkpoint"


def test_speech_timeout_attribute_is_tightened(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)
    twiml = dialer.answer_twiml(attempt.id)
    gather = ElementTree.fromstring(twiml).find("Gather")
    assert gather is not None
    assert gather.attrib["speechTimeout"] == "1.0"


def test_openrouter_classification_human(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.openrouter_api_key = "openrouter-test-key"
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    harness.openrouter_result = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"kind": "human", "reason": "greeting"})
                }
            }
        ]
    }

    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Well you know we might be interested depending on the pricing structure"},
        )
    )
    assert len(harness.openrouter_payloads) == 1
    assert harness.openrouter_payloads[0]["model"] == "google/gemini-3.5-flash-lite"
    assert "<Conference" in twiml
    assert attempt.outcome == "human-bridged"


def test_openrouter_falls_back_to_openai_on_error(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.openrouter_api_key = "openrouter-test-key"
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Force openrouter.ai to fail
    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openrouter.ai":
            harness.openrouter_payloads.append(json.loads(request.content))
            return httpx.Response(500, json={"error": "server error"})
        return harness.handler(request)

    dialer.transport = httpx.MockTransport(failing_handler)
    harness.openai_result = {
        "output_text": json.dumps({"kind": "voicemail", "reply": ""})
    }

    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Nobody is available at this desk right now feel free to drop some information"},
        )
    )
    assert len(harness.openrouter_payloads) == 1
    # Fallback to OpenAI worked
    assert len(harness.openai_payloads) == 1
    assert attempt.outcome == "voicemail"


def test_speech_on_terminal_call_does_not_bridge_ghost_call(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Call completed/hung up on provider side
    attempt.status = "completed"
    attempt.twilio_status = "completed"

    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Hello, this is Jane speaking."},
        )
    )
    assert "<Hangup" in twiml
    assert attempt.outcome != "human-bridged"
    assert attempt.status == "completed"


def test_drop_active_voicemail_with_recording_flags_and_records_feedback(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    dial_session = dialer.sessions[session["id"]]
    dial_session.human_attempt_id = attempt.id
    attempt.twilio_call_sid = "CA" + "1" * 32
    attempt.status = "bridged"
    attempt.twilio_status = "in-progress"

    result = asyncio.run(dialer.drop_active_voicemail(session["id"]))
    assert attempt.operator_flagged_voicemail is True
    assert attempt.outcome == "voicemail"
    assert attempt.voicemail_played is True
    assert attempt.status == "voicemail-playing"
    assert dial_session.human_attempt_id == ""

    # Feedback jsonl file written
    feedback_file = dialer.settings.state_dir / "voicemail_feedback.jsonl"
    assert feedback_file.exists()
    feedback_lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(feedback_lines) >= 1
    record = json.loads(feedback_lines[-1])
    assert record["attempt_id"] == attempt.id
    assert record["operator_flag"] == "voicemail"
    assert record["detected_kind"] == "human"
    assert record["voicemail_dropped"] is True

    # Close note contains operator flag note
    assert len(harness.close_posts) >= 1
    assert "flagged by operator: false-positive human connect" in harness.close_posts[-1]["note_html"]


def test_drop_active_voicemail_without_recording_hangs_up_cleanly(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, operator_email="bob@example.com")
    attempt = attempt_for(dialer, session)

    dial_session = dialer.sessions[session["id"]]
    dial_session.human_attempt_id = attempt.id
    attempt.twilio_call_sid = "CA" + "2" * 32
    attempt.status = "bridged"
    attempt.twilio_status = "in-progress"

    # Must NOT raise LiveDialerError
    result = asyncio.run(dialer.drop_active_voicemail(session["id"]))
    assert attempt.operator_flagged_voicemail is True
    assert attempt.outcome == "voicemail"
    assert attempt.voicemail_played is False
    assert attempt.status == "completed"

    feedback_file = dialer.settings.state_dir / "voicemail_feedback.jsonl"
    assert feedback_file.exists()
    records = [json.loads(line) for line in feedback_file.read_text(encoding="utf-8").strip().splitlines()]
    bob_record = [r for r in records if r["operator_email"] == "bob@example.com"][-1]
    assert bob_record["operator_flag"] == "voicemail"
    assert bob_record["voicemail_dropped"] is False


def test_voicemail_playing_does_not_consume_parallel_concurrency(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    harness.contacts.extend([
        {
            "contact_id": f"cont_{i}",
            "lead_id": f"lead_{i}",
            "name": f"Contact {i}",
            "lead_name": f"Lead {i}",
            "phone": f"+1202555015{i-3}",
        }
        for i in range(4, 7)
    ])
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    dialer.unrestricted = True
    session = start(dialer, harness, count=6, concurrency=3)
    sess = dialer.sessions[session["id"]]
    assert len(sess.attempt_ids) == 3
    att0, att1, att2 = (dialer.attempts[aid] for aid in sess.attempt_ids)

    # Attempt 0 detects voicemail via speech
    asyncio.run(
        dialer.handle_speech(
            att0.id,
            {"CallSid": att0.twilio_call_sid, "SpeechResult": "Please leave a message after the tone"},
        )
    )
    assert att0.status == "voicemail-playing"
    assert att0.voicemail_played is True

    # Advance session: attempt 0 should NOT occupy concurrency, so line 4 is dialed immediately
    asyncio.run(dialer._advance_session(sess.id))
    assert len(sess.attempt_ids) == 4
    att3 = dialer.attempts[sess.attempt_ids[3]]
    assert att3.status in {"queued", "initiated"}

    # Attempt 1 detects machine via AMD
    asyncio.run(
        dialer.handle_amd(
            att1.id,
            {"CallSid": att1.twilio_call_sid, "AnsweredBy": "machine_end_beep"},
        )
    )
    assert att1.status == "voicemail-playing"
    assert att1.voicemail_played is True

    # Advance session: attempt 1 also does NOT occupy concurrency, line 5 is dialed immediately
    asyncio.run(dialer._advance_session(sess.id))
    assert len(sess.attempt_ids) == 5
    att4 = dialer.attempts[sess.attempt_ids[4]]
    assert att4.status in {"queued", "initiated"}

    # Verify active dialing lines calculation: att0 and att1 are non-active (background voicemails)
    active_lines = [
        dialer.attempts[aid]
        for aid in sess.attempt_ids
        if dialer._is_active_dialing_line(dialer.attempts[aid])
    ]
    # Active lines are att2, att3, att4 (exactly 3 = session.concurrency)
    assert [a.id for a in active_lines] == [att2.id, att3.id, att4.id]


def test_callback_is_not_blocked_by_unrelated_voicemail_drop(tmp_path, monkeypatch) -> None:
    _, dialer, sess, alex, blair = _drop_blair_while_alex_wins(tmp_path, monkeypatch)
    assert blair.outcome == "dropped-line" and blair.abandoned

    # Introduce an unrelated call playing voicemail in the background
    charlie_attempt = DialAttempt(
        id="da_charlie_vm",
        session_id=sess.id,
        contact_id="cont_charlie",
        lead_id="lead_charlie",
        name="Charlie Machine",
        company="Charlie Co",
        phone="+15555550099",
        screening_reply="Hello",
        status="voicemail-playing",
        twilio_status="in-progress",
        twilio_call_sid="CA" + "9" * 32,
        outcome="voicemail",
        voicemail_detected=True,
        voicemail_played=True,
    )
    dialer.attempts[charlie_attempt.id] = charlie_attempt
    sess.attempt_ids.append(charlie_attempt.id)

    # Alex's human call ends
    asyncio.run(dialer.complete_active_call(sess.id))

    # Blair's first call hangs up: Blair's callback should go out immediately
    # despite Charlie playing voicemail in the background
    asyncio.run(
        dialer.handle_status(blair.id, {"CallSid": blair.twilio_call_sid, "CallStatus": "completed"})
    )
    dialed = _dialed_after(dialer, sess, alex, blair, charlie_attempt)
    assert [(a.contact_id, a.callback) for a in dialed] == [(blair.contact_id, True)]


def test_callback_hitting_voicemail_does_not_stall_dialer(tmp_path, monkeypatch) -> None:
    _, dialer, sess, alex, blair = _drop_blair_while_alex_wins(tmp_path, monkeypatch)
    asyncio.run(dialer.complete_active_call(sess.id))
    asyncio.run(
        dialer.handle_status(blair.id, {"CallSid": blair.twilio_call_sid, "CallStatus": "completed"})
    )
    callback_attempt = _dialed_after(dialer, sess, alex, blair)[0]

    # Callback answers with voicemail
    asyncio.run(
        dialer.handle_speech(
            callback_attempt.id,
            {"CallSid": callback_attempt.twilio_call_sid, "SpeechResult": "Leave a message"},
        )
    )
    assert callback_attempt.status == "voicemail-playing"

    # Queue should immediately refill without waiting for Twilio callback completion
    asyncio.run(dialer._advance_session(sess.id))
    new_dialed = _dialed_after(dialer, sess, alex, blair, callback_attempt)
    # The next queued contact was dialed immediately!
    assert len(new_dialed) >= 1
    assert new_dialed[0].name == "Casey Demo"


def test_validate_phone_number_nanp_and_toll_free() -> None:
    # Invalid NANP numbers (area codes starting with 0 or 1, or N11)
    valid, reason = validate_phone_number("+11431226236")
    assert not valid
    assert "cannot start with 0 or 1" in reason

    valid, reason = validate_phone_number("+10123456789")
    assert not valid
    assert "cannot start with 0 or 1" in reason

    valid, reason = validate_phone_number("+19113456789")
    assert not valid
    assert "N11" in reason

    # Invalid exchange code
    valid, reason = validate_phone_number("+12020550148")
    assert not valid
    assert "cannot start with 0 or 1" in reason

    valid, reason = validate_phone_number("+12021550148")
    assert not valid
    assert "cannot start with 0 or 1" in reason

    # Valid numbers
    valid, reason = validate_phone_number("+12025550148")
    assert valid
    assert reason == "ok"

    valid, reason = validate_phone_number("+14125550148")
    assert valid
    assert reason == "ok"

    # Toll free checks
    assert is_toll_free_number("+18005550199")
    assert is_toll_free_number("+18885550199")
    assert is_toll_free_number("+18775550199")
    assert is_toll_free_number("+18665550199")
    assert is_toll_free_number("+18555550199")
    assert is_toll_free_number("+18445550146")
    assert is_toll_free_number("+18335550199")
    assert not is_toll_free_number("+12025550148")


def test_start_session_filters_invalid_and_toll_free_contacts(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    # Inject an invalid NANP number and a toll-free number alongside a valid number
    harness.contacts = [
        {
            "contact_id": "cont_bad_npa",
            "lead_id": "lead_1",
            "name": "Bad Area Code",
            "lead_name": "Demo 1",
            "phone": "+11431226236",
        },
        {
            "contact_id": "cont_toll_free",
            "lead_id": "lead_2",
            "name": "Toll Free",
            "lead_name": "Demo 2",
            "phone": "+18445550146",
        },
        {
            "contact_id": "cont_good",
            "lead_id": "lead_3",
            "name": "Good Contact",
            "lead_name": "Demo 3",
            "phone": "+12025550148",
        },
    ]
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session_data = start(dialer, harness, count=3)
    session = dialer.sessions[session_data["id"]]
    # The invalid NANP and toll-free contacts must have been excluded from the queue
    queued_phones = [c["phone"] for c in session.queue]
    assert queued_phones == ["+12025550148"]


def test_session_resilient_to_provider_call_creation_failure(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    call_creation_count = 0
    original_handler = harness.handler

    def custom_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_creation_count
        if request.url.host == "api.twilio.com" and request.url.path.endswith("/Calls.json") and request.method == "POST":
            form = parse_qs(request.content.decode("utf-8"))
            if form.get("MachineDetection"):
                call_creation_count += 1
                if call_creation_count == 1:
                    # First call fails with Twilio 21211 (invalid number)
                    return httpx.Response(
                        400,
                        json={
                            "code": 21211,
                            "message": "The 'To' number is not a valid phone number.",
                            "status": 400,
                        },
                    )
        return original_handler(request)

    harness.handler = custom_handler
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    # Start session with count=3, concurrency=1
    session_data = start(dialer, harness, count=3, concurrency=1)
    session_id = session_data["id"]
    session = dialer.sessions[session_id]

    # Session must NOT be failed; it must remain running / active
    assert session.status != "failed"

    # First attempt should be marked invalid with error code 21211
    first_attempt_id = session.attempt_ids[0]
    first_attempt = dialer.attempts[first_attempt_id]
    assert first_attempt.status == "failed"
    assert first_attempt.outcome == "provider-error"
    assert first_attempt.error_code == "21211"

    # Session advanced to the second contact in the queue!
    asyncio.run(dialer._advance_session(session_id))
    assert len(session.attempt_ids) >= 2


def test_handle_status_carrier_rejection_code_13224_and_sip_404(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session_data = start(dialer, harness, count=1)
    session_id = session_data["id"]
    session = dialer.sessions[session_id]
    attempt_id = session.attempt_ids[0]
    attempt = dialer.attempts[attempt_id]

    # Twilio sends status callback with failed, ErrorCode 13224, SipResponseCode 404
    asyncio.run(
        dialer.handle_status(
            attempt_id,
            {
                "CallSid": attempt.twilio_call_sid,
                "CallStatus": "failed",
                "ErrorCode": "13224",
                "ErrorMessage": "invalid phone number ",
                "SipResponseCode": "404",
            },
        )
    )

    assert attempt.outcome == "invalid"
    assert attempt.error_code == "13224"
    assert attempt.sip_response_code == "404"
    assert attempt.error_message == "invalid phone number"

    # Verify Close call activity note
    assert len(harness.close_posts) >= 1
    last_post = harness.close_posts[-1]
    assert "outcome: invalid" in last_post["note_html"]
    assert "number disconnected / out of service (SIP 404 / Twilio 13224)" in last_post["note_html"]


def test_answer_twiml_immediate_gather_zero_audio_delay(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness)
    attempt = attempt_for(dialer, session)

    # Save audio in all slots
    _save(dialer, "greeting", seconds=1.0)
    _save(dialer, "screening", seconds=1.5)
    _save(dialer, "dropped", seconds=2.0)
    _save(dialer, "voicemail", seconds=3.0)

    # answer_twiml MUST listen immediately with zero audio playback
    twiml = dialer.answer_twiml(attempt.id)
    root = ElementTree.fromstring(twiml)
    gather = root.find("Gather")
    assert gather is not None
    assert gather.attrib["speechTimeout"] == "1.0"
    assert gather.attrib["timeout"] == "5"
    assert gather.attrib["actionOnEmptyResult"] == "true"
    # Crucial: NO Play or Say tags that could delay Twilio's speech recognizer
    assert gather.find("Play") is None
    assert gather.find("Say") is None


def test_fast_speech_path_bridges_on_first_turn_hello(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session_data = start(dialer, harness)
    attempt = attempt_for(dialer, session_data)
    live_session = dialer.sessions[session_data["id"]]

    dialer.answer_twiml(attempt.id)
    assert attempt.status == "in-progress"

    # Prospect says "Hello"
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Hello?"},
        )
    )

    root = ElementTree.fromstring(twiml)
    dial = root.find("Dial")
    assert dial is not None
    conf = dial.find("Conference")
    assert conf is not None
    assert conf.text == live_session.conference_name

    assert attempt.status == "bridged"
    assert attempt.outcome == "human-bridged"
    assert attempt.human_detected is True
    assert live_session.status == "human-connected"
    assert live_session.human_attempt_id == attempt.id


def test_fast_speech_safeguard_carrier_transfer(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session_data = start(dialer, harness)
    attempt = attempt_for(dialer, session_data)

    dialer.answer_twiml(attempt.id)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Please hold while we transfer your call."},
        )
    )
    assert attempt.status != "bridged"
    assert attempt.outcome != "human-bridged"
    root = ElementTree.fromstring(twiml)
    assert root.find("Dial/Conference") is None
    assert root.find("Gather") is not None


def test_fast_speech_safeguard_voicemail_drop(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    _save(dialer, "voicemail", seconds=2.0)
    session_data = start(dialer, harness)
    attempt = attempt_for(dialer, session_data)

    dialer.answer_twiml(attempt.id)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Please leave a message after the tone."},
        )
    )
    assert attempt.status == "voicemail-playing"
    assert attempt.outcome == "voicemail"
    assert attempt.status != "bridged"
    root = ElementTree.fromstring(twiml)
    assert root.find("Dial/Conference") is None
    assert root.find("Play") is not None


def test_fast_speech_safeguard_screening_reply(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    _save(dialer, "screening", seconds=1.0)
    session_data = start(dialer, harness)
    attempt = attempt_for(dialer, session_data)

    dialer.answer_twiml(attempt.id)
    twiml = asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "May I ask who is calling?"},
        )
    )
    assert attempt.status == "screening"
    assert attempt.outcome == "screening"
    assert attempt.status != "bridged"
    root = ElementTree.fromstring(twiml)
    assert root.find("Dial/Conference") is None

def test_competitor_machine_is_not_treated_as_dropped_line(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    alex, blair = (attempt_for(dialer, session, i) for i in (0, 1))

    # Blair's line answered and AMD already reported machine
    asyncio.run(
        dialer.handle_status(blair.id, {"CallSid": blair.twilio_call_sid, "CallStatus": "in-progress"})
    )
    asyncio.run(
        dialer.handle_amd(blair.id, {"CallSid": blair.twilio_call_sid, "AnsweredBy": "machine_end_other"})
    )

    # Alex says hello and wins
    asyncio.run(
        dialer.handle_speech(
            alex.id, {"CallSid": alex.twilio_call_sid, "SpeechResult": "Hello, this is Alex"}
        )
    )

    sess = dialer.sessions[session["id"]]
    assert blair.outcome == "voicemail"
    assert not blair.abandoned
    # Blair must NOT be inserted into queue as high-priority callback
    assert not any(c.get("contact_id") == blair.contact_id and c.get("callback") for c in sess.queue)


def test_late_amd_machine_corrects_dropped_line_and_unprioritizes_queue(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=3, concurrency=2)
    alex, blair = (attempt_for(dialer, session, i) for i in (0, 1))

    # Blair answers (AMD not finished yet)
    asyncio.run(
        dialer.handle_status(blair.id, {"CallSid": blair.twilio_call_sid, "CallStatus": "in-progress"})
    )
    # Alex says hello and wins: Blair is initially marked dropped-line
    asyncio.run(
        dialer.handle_speech(
            alex.id, {"CallSid": alex.twilio_call_sid, "SpeechResult": "Hello, this is Alex"}
        )
    )
    sess = dialer.sessions[session["id"]]
    assert blair.outcome == "dropped-line"
    assert blair.abandoned
    assert sess.queue[sess.next_index]["contact_id"] == blair.contact_id
    assert sess.queue[sess.next_index]["callback"] is True

    # Late AMD callback arrives: Blair was actually an answering machine!
    asyncio.run(
        dialer.handle_amd(blair.id, {"CallSid": blair.twilio_call_sid, "AnsweredBy": "machine_end_other"})
    )
    assert blair.outcome == "voicemail"
    assert not blair.abandoned
    assert blair.voicemail_detected is True
    # Priority callback queue must have been unprioritized
    assert not any(c.get("contact_id") == blair.contact_id and c.get("callback") for c in sess.queue)


def test_bridge_duration_updated_from_status_and_conference_recording(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=1, concurrency=1)
    attempt = attempt_for(dialer, session)

    # Human connects
    asyncio.run(
        dialer.handle_speech(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "SpeechResult": "Hello, human here"},
        )
    )
    assert attempt.outcome == "human-bridged"
    assert attempt.bridge_duration == 0

    # Call completed status with duration=120
    asyncio.run(
        dialer.handle_status(
            attempt.id,
            {"CallSid": attempt.twilio_call_sid, "CallStatus": "completed", "CallDuration": "120"},
        )
    )
    assert attempt.duration == 120
    assert attempt.bridge_duration == 120

    # Conference recording completes with duration=125
    asyncio.run(
        dialer.handle_recording_status(
            attempt.id,
            {
                "RecordingSid": "RE" + "a" * 32,
                "RecordingStatus": "completed",
                "RecordingDuration": "125",
            },
            is_conference=True,
        )
    )
    assert attempt.duration == 125
    assert attempt.bridge_duration == 125


def test_bloated_conference_recording_duration_is_clamped(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=1, concurrency=1)
    attempt = attempt_for(dialer, session)

    # Lead bridged for 20s
    attempt.outcome = "human-bridged"
    attempt.bridge_duration = 20
    attempt.duration = 20

    # Twilio sends an inflated conference recording from multi-call bleed (e.g. 636s)
    asyncio.run(
        dialer.handle_recording_status(
            attempt.id,
            {
                "RecordingSid": "RE" + "b" * 32,
                "RecordingStatus": "completed",
                "RecordingDuration": "636",
            },
            is_conference=True,
        )
    )
    # Must remain clamped to bridge duration (20), not inflated to 636!
    assert attempt.duration == 20
    assert attempt.bridge_duration == 20


def test_sip_200_and_487_do_not_log_carrier_error_in_close(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)
    session = start(dialer, harness, count=1, concurrency=1)
    attempt = attempt_for(dialer, session)

    attempt.twilio_call_sid = "CA" + "1" * 32
    attempt.lead_id = "lead_test123"
    attempt.sip_response_code = "200"
    attempt.outcome = "answered"

    logged_notes = []
    monkeypatch.setattr(
        dialer.close_dialer,
        "log_call",
        lambda **kwargs: logged_notes.append(kwargs.get("note", "")) or {"id": "act_123"},
    )
    asyncio.run(dialer._log_close_once(attempt))
    assert len(logged_notes) == 1
    assert "carrier error" not in logged_notes[0]

    # Test SIP 487
    attempt.close_logged = False
    attempt.sip_response_code = "487"
    attempt.outcome = "canceled"
    logged_notes.clear()
    asyncio.run(dialer._log_close_once(attempt))
    assert len(logged_notes) == 1
    assert "carrier error" not in logged_notes[0]


def test_stop_conference_recordings_invoked_and_stops_recordings(tmp_path, monkeypatch) -> None:
    harness = ProviderHarness()
    dialer = make_dialer(tmp_path, monkeypatch, harness)

    stopped_urls = []
    async def mock_twilio_get(path, **kwargs):
        if "Conferences.json" in path:
            return {"conferences": [{"sid": "CF12345"}]}
        if "Recordings.json" in path:
            return {"recordings": [{"sid": "RE54321"}]}
        return {}

    async def mock_twilio_post(path, data, **kwargs):
        stopped_urls.append((path, data))
        return {}

    monkeypatch.setattr(dialer, "_twilio_get", mock_twilio_get)
    monkeypatch.setattr(dialer, "_twilio_post", mock_twilio_post)

    asyncio.run(dialer._stop_conference_recordings("conf_test_room"))
    assert any("Twilio.CURRENT.json" in url and data.get("Status") == "stopped" for url, data in stopped_urls)
    assert any("RE54321.json" in url and data.get("Status") == "stopped" for url, data in stopped_urls)

