"""The dialer page, rendered by the service.

Each test renders the real template from a canned queue and checks what the operator
sees, so a template edit that drops a control fails here rather than on a live call."""

from __future__ import annotations

import copy
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from parallel_dialer.api import PACKAGE_DIR, create_app
from parallel_dialer.auth import access_key
from parallel_dialer.config import Settings
from parallel_dialer.dialer import CloseDialer
from parallel_dialer.live_dialer import LiveDialer
from parallel_dialer.profile import Profile

ORIGIN = "https://dialer.example.com"
SECRET = "page-test-secret-0123456789abcdef"
ALICE = "alice@example.com"
BOB = "bob@example.com"
PROFILE = Profile(brand="Acme", brand_is_set=True)


def view(recordings=None, **live_overrides):
    recordings = recordings or {}
    live = {
        "ready": True,
        "blockers": [],
        "max_concurrency": 10,
        "max_session_contacts": 10000,
        "max_greeting_seconds": 2.5,
        "operator_configured": True,
        "voicemail": recordings.get("voicemail", {}),
        "recordings": recordings,
        "callback_routing": {},
    }
    live.update(live_overrides)
    return {
        "connected": True,
        "contacts": [],
        "smart_views": [],
        "selected_smart_view": None,
        "checkpoint": {},
        "fetched_at": None,
        "live": live,
    }


@pytest.fixture
def render(tmp_path, monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    settings = Settings(
        root=tmp_path, public_base_url=ORIGIN, allowed_emails=frozenset({ALICE, BOB}), profile=PROFILE
    )
    offline = httpx.MockTransport(lambda request: httpx.Response(404))
    close = CloseDialer(transport=offline)
    live = LiveDialer(settings, close, transport=offline)
    seen_operators = []
    app = create_app(settings, close_dialer_instance=close, live_dialer_instance=live, secret=SECRET)

    def _render(payload=None, email=ALICE) -> str:
        payload = payload if payload is not None else view()
        monkeypatch.setattr(close, "contacts", lambda *a, **k: {})

        def decorate(_contacts, operator_email=""):
            seen_operators.append(operator_email)
            return copy.deepcopy(payload)

        monkeypatch.setattr(live, "decorate_contacts", decorate)
        client = TestClient(app, base_url=ORIGIN)
        signed_in = client.post(
            "/login", data={"email": email, "key": access_key(SECRET, email)}, follow_redirects=False
        )
        assert signed_in.status_code == 303
        response = client.get("/dialer/")
        assert response.status_code == 200
        return response.text

    _render.seen_operators = seen_operators
    return _render


def test_the_page_is_the_dialer_and_nothing_else(render):
    body = render()
    assert 'id="dialer-app"' in body
    assert "Close CRM contacts" in body
    assert "Acme dialer" in body
    for section in ("User management", "Website analytics", "<aside"):
        assert section not in body, section
    assert "/assets/dialer.js?v=" in body


def test_nothing_in_the_page_belongs_to_another_company(render):
    body = render()
    script = (PACKAGE_DIR / "static" / "dialer.js").read_text(encoding="utf-8")
    for text in (body, script):
        for word in ("Senecta", "senecta", "Marcos", "Mauro", "Spain"):
            assert word not in text, word


def test_the_page_carries_the_deployments_own_wording(render):
    body = render()
    profile = json.loads(re.search(r'<script type="application/json" id="dialer-profile">(.*?)</script>', body, re.S).group(1))
    assert set(profile) == {"brand", "script", "screening_reply"}
    assert profile["brand"] == "Acme"
    # What is said to a receptionist is the operator's own name and the company's.
    assert profile["screening_reply"].startswith("Hi, this is Alice calling from Acme.")
    assert "with Acme" in profile["script"] and "{{Brand}}" not in profile["script"]


def test_the_page_has_nothing_that_schedules_or_sends_email(render):
    body = render()
    script = (PACKAGE_DIR / "static" / "dialer.js").read_text(encoding="utf-8")
    for text in (body, script):
        for word in (
            "Scheduling", "scheduling", "Radar", "Book Demo", "Send Info", "Sleep Guard", "sleep guard",
            "quick-book", "send-info", "check-avail", "calendar", "Google Meet", "invite", "Invite",
        ):
            assert word not in text, word
    # What is left of the settings dialog: the Close key, and the Twilio account.
    assert 'id="dialer-twilio-form"' in body


def test_offers_a_slot_for_each_thing_the_contact_hears(render):
    body = render()
    for slot in ("greeting", "screening", "dropped", "voicemail"):
        assert f'data-slot="{slot}"' in body
    assert body.count("Not set") == 4
    assert 'data-max-greeting="2.5"' in body
    # With no message recorded the rules row must say so rather than claim it is on.
    assert "machines are hung up on in silence" in body


def test_shows_a_saved_recording_with_its_length(render):
    body = render(
        view(
            {
                "greeting": {"configured": True, "filename": "hello.wav", "duration_seconds": 0.6},
                "voicemail": {"configured": True, "filename": "message.mp3"},
            }
        )
    )
    assert "hello.wav" in body and "0.6s" in body
    assert "the machine hears your recording" in body
    assert body.count("Not set") == 2


def test_has_no_simulation_or_demo_scaffolding(render):
    body = render()
    # The dialer places real calls to real people; nothing on it may suggest a
    # rehearsal, and no number on it may be invented.
    for ghost in (
        "Simulation", "simulation", "Demo mode", "Demo health", "Demo session", "Demo estimate",
        "demo queue", "simulator", "data-dialer-mode", "dialer-mode-chip", "dialer-health-score",
        "dialer-gauge-score",
    ):
        assert ghost not in body, ghost
    assert body.count('class="metric-card') == 4
    assert "Abandonment rate" in body
    assert "Live" in body


def test_offers_the_browser_as_the_place_to_take_the_call(render):
    body = render()
    assert 'data-operator-target="browser"' in body
    assert 'data-operator-target="phone"' in body
    assert "dialer-mic-meter-wrap" in body
    assert "dialer-mic-test-btn" in body
    assert "dialer-modal-mic-indicator" in body
    # The SDK is served from this origin; the CSP forbids a CDN.
    assert "/assets/twilio-voice-2.18.5.js" in body
    assert "cdn." not in body and "unpkg" not in body


def test_locked_chip_names_the_real_blockers(render):
    body = render(view(ready=False, blockers=["Add at least one consenting test number to the server allowlist."]))
    assert "Locked" in body
    assert "consenting test number" in body
    assert "Set the allowlist and operator number" not in body


def test_includes_the_profile_dialog_and_mic_meter(render):
    body = render()
    for element in (
        "dialer-profile-dialog", "dialer-modal-name", "dialer-modal-open-close", "dialer-auto-open-toggle",
        "dialer-modal-mic-wrap", "dialer-mic-meter-fill", "dialer-modal-notes-box", "dialer-notes-list",
    ):
        assert f'id="{element}"' in body, element


def test_the_operator_badge_is_whoever_signed_in(render):
    alice = render(email=ALICE)
    assert f'data-operator-email="{ALICE}"' in alice
    assert 'data-operator-name="Alice"' in alice
    bob = render(email=BOB)
    assert f'data-operator-email="{BOB}"' in bob
    assert 'data-operator-name="Bob"' in bob
    for body in (alice, bob):
        assert 'id="dialer-screening-reply"' not in body
        assert "AI screening reply" not in body
    # Each page loaded that operator's own queue.
    assert render.seen_operators == [ALICE, BOB]


def test_includes_the_talk_track_notepad(render):
    body = render()
    for element in (
        "dialer-script-panel", "dialer-script-pad", "dialer-script-status", "dialer-script-copy-btn",
        "dialer-script-reset-btn", "dialer-script-meta", "dialer-modal-script-drawer",
        "dialer-modal-script-toggle", "dialer-modal-script-pad", "dialer-modal-script-status",
        "dialer-modal-script-copy-btn",
    ):
        assert f'id="{element}"' in body, element


def test_offers_the_voicemail_drop(render):
    body = render()
    assert 'id="dialer-bridge-drop-vm"' in body
    assert 'id="dialer-modal-drop-voicemail"' in body
    assert "⚡ Drop Voicemail" in body
    assert "This is a voicemail" in body


def test_renders_timezone_waves_on_each_contact(render):
    payload = view()
    payload["contacts"] = [
        {
            "contact_id": "cont_prime_1",
            "lead_id": "lead_1",
            "name": "Sarah Connor",
            "lead_name": "Cyberdyne Care",
            "email": "sarah@cyberdyne.com",
            "phone": "+12125550111",
            "status": "Potential",
            "phone_type": "mobile",
            "close_url": "https://app.close.com/lead/lead_1",
            "live_allowed": True,
            "dialer_attempted": False,
            "timezone_info": {
                "tz_code": "ET",
                "local_time_str": "10:15 AM",
                "wave_status": "prime",
                "can_call": True,
                "notice": "Prime calling window (10:15 AM ET)",
            },
        }
    ]
    body = render(payload)
    for element in ("dialer-wave-sort-toggle", "dialer-safe-hours-toggle", "dialer-wave-summary", "dialer-wave-prime-count"):
        assert f'id="{element}"' in body, element
    assert 'data-tz-code="ET"' in body
    assert 'data-wave-status="prime"' in body
    assert 'data-can-call="true"' in body
    assert "tz-badge prime" in body
    assert "ET &bull; 10:15 AM" in body


def test_one_failed_poll_does_not_abandon_a_running_session():
    script = (PACKAGE_DIR / "static" / "dialer.js").read_text(encoding="utf-8")
    # A 502 from the proxy once froze the page on "did not start" while the session kept
    # dialing: a failed poll retries, and says so, before giving up.
    assert "pollFailures" in script and '"Reconnecting"' in script
    # Lines are numbered as they sit on screen, not by queue position ("Line 12" of 3).
    assert "Line ${index + 1}" in script
    assert "Line ${sib.queue_position" not in script


def test_the_call_popup_shows_the_script_to_read_from(render):
    body = render()
    # Its own column in the pop-up, open unless the operator closed it, rendered for
    # reading rather than a small edit box at the bottom.
    drawer = body.split('id="dialer-modal-script-drawer"', 1)[1].split("</section>", 1)[0]
    assert 'aria-expanded="true"' in drawer
    assert 'id="dialer-modal-script-view"' in drawer
    assert 'id="dialer-modal-script-edit-btn"' in drawer
    assert body.index('class="dialer-modal-main"') < body.index('id="dialer-modal-script-drawer"')
    # The renderer loads before the page script that uses it.
    assert body.index("/assets/call-script.js") < body.index("/assets/dialer.js")
    # And an empty "Previous call notes" box no longer sits above it on every call.
    assert ".dialer-modal-notes-box[hidden]" in (PACKAGE_DIR / "static" / "dialer.css").read_text(encoding="utf-8")
