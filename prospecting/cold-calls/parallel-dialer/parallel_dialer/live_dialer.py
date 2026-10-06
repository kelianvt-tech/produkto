from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote
from uuid import uuid4
from xml.sax.saxutils import escape, quoteattr

import httpx
import jwt

from .config import Settings, read_secret
from .dialer import CloseDialer, DialerError, clean_operator_identity
from .timezones import get_contact_local_time, sort_queue_by_timezone_wave

TERMINAL_CALL_STATUSES = {"busy", "canceled", "completed", "failed", "no-answer"}
# A session in one of these places no new calls, and nothing but stop_session moves it on.
HALTED_SESSION_STATUSES = {"failed", "stopped", "stopping", "stop-failed"}
ACTIVE_SESSION_STATUSES = {
    "starting",
    "running",
    "operator-connecting",
    "human-connected",
    "stopping",
    "stop-failed",
}
# A line that has sent no webhook for this long is taken as over by a waiting call back.
CALLBACK_STALE_SECONDS = 90.0
MACHINE_RESULTS = {
    "fax",
    "machine_end_beep",
    "machine_end_other",
    "machine_end_silence",
    "machine_start",
}
RECORDING_FILE_STEMS = {
    "greeting": "dialer-greeting-message",
    "screening": "dialer-screening-message",
    "dropped": "dialer-dropped-message",
    # Kept at the original name so a message uploaded before slots existed still plays.
    "voicemail": "dialer-voicemail-message",
}
RECORDING_SLOTS = tuple(RECORDING_FILE_STEMS)
# A prompt inside <Gather> is time the speech recogniser is deaf, so the hello is
# capped rather than trusted: long enough to cover the detection gap, short enough
# that the contact's first words still reach the classifier.
MAX_GREETING_SECONDS = 2.5
logger = logging.getLogger("parallel_dialer.dialer")


class LiveDialerError(RuntimeError):
    """Raised when a live dialing request is unsafe or cannot be completed."""


class LiveDialerProviderError(LiveDialerError):
    """Raised when the telephony provider rejects a call request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        code: str = "",
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.detail = detail



def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("00"):
        raw = f"+{raw[2:]}"
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+") or not 8 <= len(digits) <= 15:
        return ""
    return f"+{digits}"


def validate_phone_number(phone: str) -> tuple[bool, str]:
    """Validate normalized E.164 phone number. Returns (is_valid, reason)."""
    if not phone or not phone.startswith("+"):
        return False, "Missing '+' or empty phone number"
    digits = phone[1:]
    if not digits.isdigit():
        return False, "Non-digit characters in phone number"
    if not 8 <= len(digits) <= 15:
        return False, f"Invalid length ({len(digits)} digits, must be 8-15)"

    # North American Numbering Plan (NANP: +1 US, Canada, etc.) validation
    if digits.startswith("1"):
        if len(digits) != 11:
            return False, f"NANP number must be exactly 11 digits including country code 1 (got {len(digits)})"
        npa = digits[1:4]
        nxx = digits[4:7]
        # Area code (NPA) cannot start with 0 or 1
        if npa[0] in "01":
            return False, f"Invalid area code '{npa}': NANP area codes cannot start with 0 or 1"
        # Area codes cannot end in 11 (N11 service codes like 911, 411, 211)
        if npa[1:] == "11":
            return False, f"Invalid area code '{npa}': N11 codes are reserved"
        # Central office exchange code (NXX) cannot start with 0 or 1
        if nxx[0] in "01":
            return False, f"Invalid exchange code '{nxx}': cannot start with 0 or 1"
        # Exchange codes cannot end in 11
        if nxx[1:] == "11":
            return False, f"Invalid exchange code '{nxx}': N11 codes are reserved"
    return True, "ok"


def is_toll_free_number(phone: str) -> bool:
    """Return whether the phone number is a US/Canada toll-free number (800/888/877/866/855/844/833)."""
    if phone.startswith("+1") and len(phone) == 12:
        return phone[2:5] in {"800", "888", "877", "866", "855", "844", "833"}
    return False


def mask_phone(value: str) -> str:
    normalized = normalize_phone(value)
    if len(normalized) < 6:
        return "Unavailable"
    return f"{normalized[:2]}•••{normalized[-4:]}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


# MPEG-1/2/2.5 Layer III bitrates, indexed by the 4-bit field in the frame header.
_MP3_BITRATES_V1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MP3_BITRATES_V2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)


def audio_duration_seconds(audio: bytes, content_type: str) -> float | None:
    """Length of a WAV or constant-bitrate MP3, or None when it cannot be read.

    Only used to hold the hello to its budget, so an unreadable file is not an
    error: an unknown duration simply skips the check rather than blocking a
    recording the operator can hear is fine.
    """
    try:
        if content_type == "audio/wav":
            if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
                return None
            offset, byte_rate = 12, 0
            while offset + 8 <= len(audio):
                chunk = audio[offset : offset + 4]
                size = int.from_bytes(audio[offset + 4 : offset + 8], "little")
                body = offset + 8
                if chunk == b"fmt " and body + 16 <= len(audio):
                    byte_rate = int.from_bytes(audio[body + 8 : body + 12], "little")
                elif chunk == b"data":
                    actual = min(size, len(audio) - body)
                    return actual / byte_rate if byte_rate > 0 else None
                offset = body + size + (size & 1)
            return None

        start = 0
        if audio[:3] == b"ID3" and len(audio) >= 10:
            tag = audio[6:10]
            start = 10 + ((tag[0] & 0x7F) << 21 | (tag[1] & 0x7F) << 14
                          | (tag[2] & 0x7F) << 7 | (tag[3] & 0x7F))
        while start + 4 <= len(audio) and not (
            audio[start] == 0xFF and audio[start + 1] & 0xE0 == 0xE0
        ):
            start += 1
        if start + 4 > len(audio):
            return None
        header = audio[start : start + 4]
        version_bits = (header[1] >> 3) & 0x03
        bitrate_index = (header[2] >> 4) & 0x0F
        table = _MP3_BITRATES_V1 if version_bits == 0x03 else _MP3_BITRATES_V2
        kbps = table[bitrate_index]
        if kbps <= 0:
            return None
        return (len(audio) - start) * 8 / (kbps * 1000)
    except (IndexError, ValueError, ZeroDivisionError):
        return None


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(str(value or default)))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class DialAttempt:
    id: str
    session_id: str
    contact_id: str
    lead_id: str
    name: str
    company: str
    phone: str
    screening_reply: str
    email: str = ""
    close_url: str = ""
    linkedin_url: str = ""
    title: str = ""
    lead_status: str = ""
    queue_position: int = 0
    caller_number: str = ""
    caller_label: str = ""
    status: str = "queued"
    twilio_status: str = "queued"
    outcome: str = ""
    twilio_call_sid: str = ""
    operator_call_sid: str = ""
    operator_status: str = ""
    answered_by: str = ""
    duration: int = 0
    bridge_duration: int = 0
    sequence_number: int = -1
    operator_sequence_number: int = -1
    turns: int = 0
    screening_detected: bool = False
    human_detected: bool = False
    abandoned: bool = False
    voicemail_detected: bool = False
    voicemail_played: bool = False
    operator_flagged_voicemail: bool = False
    operator_disqualified: bool = False
    disposition: str = ""
    close_logged: bool = False
    close_call_id: str = ""
    recording_url: str = ""
    recording_sid: str = ""
    checkpoint_recorded: bool = False
    # A call back to someone a busy line dropped: it is dialed alone (see _advance_session).
    callback: bool = False
    transcript: list[str] = field(default_factory=list)
    speech_responses: dict[str, str] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    sip_response_code: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "lead_id": self.lead_id,
            "name": self.name,
            "company": self.company,
            "email": self.email,
            "close_url": self.close_url,
            "linkedin_url": self.linkedin_url,
            "title": self.title,
            "lead_status": self.lead_status,
            "phone_masked": mask_phone(self.phone),
            "caller_number": self.caller_number,
            "caller_number_masked": mask_phone(self.caller_number),
            "caller_label": self.caller_label or "Number 1",
            "queue_position": self.queue_position,
            "status": self.status,
            "twilio_status": self.twilio_status,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "sip_response_code": self.sip_response_code,
            "operator_status": self.operator_status,
            "answered_by": self.answered_by,
            "twilio_call_sid": self.twilio_call_sid,
            "human_detected": self.human_detected,
            "abandoned": self.abandoned,
            "voicemail_detected": self.voicemail_detected,
            "operator_flagged_voicemail": self.operator_flagged_voicemail,
            "operator_disqualified": self.operator_disqualified,
            "disposition": self.disposition,
            "duration": self.duration,
            "recording_url": self.recording_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class DialSession:
    id: str
    attempt_ids: list[str]
    smart_view_id: str = ""
    smart_view_name: str = ""
    concurrency: int = 1
    screening_reply: str = ""
    queue: list[dict[str, Any]] = field(default_factory=list)
    next_index: int = 0
    source_total: int = 0
    resume_skipped: int = 0
    human_attempt_id: str = ""
    operator_call_sid: str = ""
    operator_status: str = ""
    operator_sequence_number: int = -1
    # "browser" takes the leg in the page over WebRTC; "phone" rings a handset.
    operator_target: str = "browser"
    conference_name: str = ""
    operator_email: str = ""
    status: str = "starting"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class ContactHistory:
    contact_id: str
    attempts: int = 0
    last_outcome: str = ""
    last_attempted_at: str = ""
    hours_tried: list[int] = field(default_factory=list)
    ever_answered: bool = False
    retired: bool = False


@dataclass(slots=True)
class DialCheckpoint:
    smart_view_id: str
    smart_view_name: str
    attempted_contact_ids: list[str] = field(default_factory=list)
    contact_history: dict[str, ContactHistory] = field(default_factory=dict)
    source_total: int = 0
    last_session_id: str = ""
    operator_email: str = ""
    updated_at: str = field(default_factory=utc_now)


class LiveDialer:
    """Demo-safe Twilio dialer with explicit allowlists and low concurrency."""

    twilio_api_base = "https://api.twilio.com/2010-04-01"
    openai_responses_url = "https://api.openai.com/v1/responses"
    typesafe_system_one_url = "https://api.typesafe.ai/v1/systemone"
    cloudflare_ai_run_url = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
    # Where Twilio calls back. Read from the settings in __init__; this is only the
    # local-development default.
    public_base_url = "http://127.0.0.1:8767/twilio/dialer"
    max_concurrency = 10
    max_session_contacts = 10000
    # A contact who has not reached a person comes back this long after their last
    # dial, up to this many dials in total. The history is pooled across every
    # operator and Smart View, so a duplicate copy of a view or another operator's
    # queue cannot ring someone early. Anyone a person answered for stays retired.
    redial_after = timedelta(days=7)
    max_dials_per_contact = 4

    def __init__(
        self,
        settings: Settings,
        close_dialer: CloseDialer,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        configured_base = getattr(settings, "twilio_base_url", "")
        if configured_base:
            self.public_base_url = configured_base
        self.close_dialer = close_dialer
        if self.close_dialer and not getattr(self.close_dialer, "settings", None):
            self.close_dialer.settings = settings
        self.transport = transport
        self.account_sid = read_secret("dialer-twilio-account-sid", "TWILIO_ACCOUNT_SID")
        self.api_key_sid = read_secret("dialer-twilio-api-key-sid", "TWILIO_API_KEY_SID")
        self.api_key_secret = read_secret(
            "dialer-twilio-api-key-secret", "TWILIO_API_KEY_SECRET"
        )
        self.caller_number = normalize_phone(
            read_secret("dialer-twilio-phone-number", "TWILIO_PHONE_NUMBER")
        )
        # The secret names the first main line. Switching it in the Numbers panel (or
        # deleting it) is recorded here, so a cooked main line can be retired.
        self.main_line_path = self.settings.state_dir / "dialer-main-line.json"
        try:
            switched = json.loads(self.main_line_path.read_text(encoding="utf-8"))
            if isinstance(switched, dict) and normalize_phone(switched.get("phone_number", "")):
                self.caller_number = normalize_phone(switched["phone_number"])
        except (OSError, ValueError):
            pass
        self.openai_api_key = read_secret("dialer-openai-api-key", "OPENAI_API_KEY")
        self.openrouter_api_key = (
            getattr(settings, "openrouter_api_key", "")
            or read_secret("dialer-openrouter-api-key", "OPENROUTER_API_KEY")
        )
        self.openrouter_model = (
            getattr(settings, "openrouter_model", "")
            or read_secret("dialer-openrouter-model", "OPENROUTER_MODEL")
            or "google/gemini-3.5-flash-lite"
        )
        self.typesafe_api_key = (
            getattr(settings, "typesafe_api_key", "")
            or read_secret("dialer-typesafe-api-key", "TYPESAFE_API_KEY")
        )
        self.typesafe_model = (
            getattr(settings, "typesafe_model", "")
            or read_secret("dialer-typesafe-model", "TYPESAFE_MODEL")
            or "jev-latest"
        )
        self.cloudflare_account_id = (
            getattr(settings, "cloudflare_account_id", "")
            or read_secret("dialer-cloudflare-account-id", "CLOUDFLARE_ACCOUNT_ID")
        )
        self.cloudflare_api_token = (
            getattr(settings, "cloudflare_api_token", "")
            or read_secret("dialer-cloudflare-api-token", "CLOUDFLARE_API_TOKEN")
        )
        self.cloudflare_ai_model = (
            getattr(settings, "cloudflare_ai_model", "")
            or read_secret("dialer-cloudflare-ai-model", "CLOUDFLARE_AI_MODEL")
            or "typesafe/jev"
        )
        self.stream_worker_url = (
            getattr(settings, "stream_worker_url", "")
            or read_secret("dialer-stream-worker-url", "DIALER_STREAM_WORKER_URL")
        ).strip().rstrip("/")
        self.webhook_secret = read_secret(
            "dialer-webhook-token", "DIALER_WEBHOOK_TOKEN"
        )
        self.live_mode = (
            read_secret("dialer-live-mode", "DIALER_LIVE_MODE").lower() == "enabled"
        )
        allowed = read_secret(
            "dialer-allowed-test-numbers", "DIALER_ALLOWED_TEST_NUMBERS"
        )
        self.unrestricted = (
            read_secret("dialer-unrestricted", "DIALER_UNRESTRICTED").lower()
            in {"enabled", "true", "1", "yes"}
            or read_secret("dialer-mode", "DIALER_MODE").lower() == "production"
            or allowed.strip().lower() in {"*", "all", "production", "unrestricted"}
        )
        self.allowed_numbers = {
            normalized
            for item in re.split(r"[,\s]+", allowed)
            if (normalized := normalize_phone(item))
        }
        blocked = read_secret(
            "dialer-blocked-numbers", "DIALER_BLOCKED_NUMBERS"
        )
        self.blocked_numbers = {
            normalized
            for item in re.split(r"[,\s]+", blocked)
            if (normalized := normalize_phone(item))
        }
        self.operator_number = normalize_phone(
            read_secret("dialer-operator-number", "DIALER_OPERATOR_NUMBER")
        )
        # Where a callback is sent. A Close Voice number puts the returning call in
        # front of the lead it belongs to, with Close doing the matching, logging
        # and recording; without one, callbacks go to the operator as before.
        self.callback_number = normalize_phone(
            read_secret("dialer-callback-number", "DIALER_CALLBACK_NUMBER")
        )
        # The operator leg only has to answer and join the conference, so it can be
        # a browser rather than a phone. Twilio addresses one as client:<identity>.
        self.voice_identity = (
            read_secret("dialer-voice-identity", "DIALER_VOICE_IDENTITY")
            or "dialer-operator"
        )
        # Three things get said on a live call, and every one of them used to be a
        # machine: the hello that covers the detection gap, the reply to a gatekeeper
        # (a <Say> until now, so a receptionist heard Twilio's voice speaking for the
        # operator) and the message left on an answering machine. Each is a slot the
        # operator records in their own voice; the legacy voicemail filename is kept so
        # an already-uploaded message survives this change.
        self.recording_paths = {
            slot: (
                self.settings.state_dir / stem,
                self.settings.state_dir / f"{stem}.json",
            )
            for slot, stem in RECORDING_FILE_STEMS.items()
        }
        self.voicemail_path, self.voicemail_meta_path = self.recording_paths["voicemail"]
        self.inbound_meta_path = self.settings.state_dir / "dialer-inbound-routing.json"
        self.sessions: dict[str, DialSession] = {}
        self.attempts: dict[str, DialAttempt] = {}
        self.checkpoints: dict[str, DialCheckpoint] = {}
        self.call_index: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._speech_locks: dict[str, asyncio.Lock] = {}
        self._end_locks: dict[str, asyncio.Lock] = {}
        self._advance_locks: dict[str, asyncio.Lock] = {}
        self._advance_timers: dict[str, asyncio.TimerHandle] = {}
        self.state_path = self.settings.state_dir / "live-dialer.json"
        # A running session's queue lives in queues/<session id>.json (see _persist_queues).
        self.queue_dir = self.settings.state_dir / "queues"
        self._saved_queues: dict[str, tuple[int, int]] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Restore recent attempts so restarts do not invalidate active callbacks."""
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        session_fields = {item.name for item in fields(DialSession)}
        attempt_fields = {item.name for item in fields(DialAttempt)}
        checkpoint_fields = {item.name for item in fields(DialCheckpoint)}
        restored_sessions: dict[str, DialSession] = {}
        restored_attempts: dict[str, DialAttempt] = {}
        restored_checkpoints: dict[str, DialCheckpoint] = {}
        for item in list(payload.get("checkpoints") or [])[-500:]:
            if not isinstance(item, dict):
                continue
            try:
                checkpoint = DialCheckpoint(
                    **{key: item[key] for key in checkpoint_fields if key in item and key != "contact_history"}
                )
            except (KeyError, TypeError, ValueError):
                continue
            if not CloseDialer._valid_smart_view_id(checkpoint.smart_view_id):
                continue
            history_map: dict[str, ContactHistory] = {}
            raw_history = item.get("contact_history")
            if isinstance(raw_history, dict):
                for cid, cdata in raw_history.items():
                    if isinstance(cdata, dict) and str(cid).startswith("cont_"):
                        history_map[str(cid)] = ContactHistory(
                            contact_id=str(cdata.get("contact_id") or cid),
                            attempts=int(cdata.get("attempts") or 0),
                            last_outcome=str(cdata.get("last_outcome") or ""),
                            last_attempted_at=str(cdata.get("last_attempted_at") or ""),
                            hours_tried=[int(h) for h in cdata.get("hours_tried") or []],
                            ever_answered=bool(cdata.get("ever_answered", False)),
                            retired=bool(cdata.get("retired", False)),
                        )
            elif isinstance(raw_history, list):
                for cdata in raw_history:
                    if isinstance(cdata, dict) and str(cdata.get("contact_id") or "").startswith("cont_"):
                        cid = str(cdata["contact_id"])
                        history_map[cid] = ContactHistory(
                            contact_id=cid,
                            attempts=int(cdata.get("attempts") or 0),
                            last_outcome=str(cdata.get("last_outcome") or ""),
                            last_attempted_at=str(cdata.get("last_attempted_at") or ""),
                            hours_tried=[int(h) for h in cdata.get("hours_tried") or []],
                            ever_answered=bool(cdata.get("ever_answered", False)),
                            retired=bool(cdata.get("retired", False)),
                        )
            raw_attempted = list(
                dict.fromkeys(
                    str(contact_id)
                    for contact_id in (item.get("attempted_contact_ids") or [])
                    if str(contact_id).startswith("cont_")
                )
            )
            for cid in raw_attempted:
                if cid not in history_map:
                    history_map[cid] = ContactHistory(
                        contact_id=cid,
                        attempts=1,
                        last_outcome="completed",
                        retired=True,
                    )
            checkpoint.contact_history = history_map
            checkpoint.attempted_contact_ids = list(
                dict.fromkeys(
                    cid
                    for cid, h in history_map.items()
                    if h.retired or h.attempts > 0
                )
            )[:1000]
            op_email = getattr(checkpoint, "operator_email", "") or ""
            key = self._checkpoint_key(op_email, checkpoint.smart_view_id)
            restored_checkpoints[key] = checkpoint
        for item in list(payload.get("sessions") or [])[-200:]:
            if not isinstance(item, dict):
                continue
            try:
                updated = datetime.fromisoformat(str(item.get("updated_at") or ""))
                session = DialSession(**{key: item[key] for key in session_fields if key in item})
            except (KeyError, TypeError, ValueError):
                continue
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if updated >= cutoff and re.fullmatch(r"ds_[a-f0-9]{32}", session.id):
                restored_sessions[session.id] = session
        for item in list(payload.get("attempts") or [])[-600:]:
            if not isinstance(item, dict):
                continue
            data = {key: item[key] for key in attempt_fields if key in item}
            data["transcript"] = []
            try:
                attempt = DialAttempt(**data)
            except (TypeError, ValueError):
                continue
            if (
                attempt.session_id in restored_sessions
                and re.fullmatch(r"da_[a-f0-9]{32}", attempt.id)
                and normalize_phone(attempt.phone)
            ):
                restored_attempts[attempt.id] = attempt
                if attempt.twilio_call_sid.startswith("CA"):
                    self.call_index[attempt.twilio_call_sid] = attempt.id
        for session in restored_sessions.values():
            session.attempt_ids = [
                attempt_id for attempt_id in session.attempt_ids if attempt_id in restored_attempts
            ]
            if not session.queue and session.status in ACTIVE_SESSION_STATUSES:
                try:
                    queue = json.loads(self._queue_path(session.id).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    queue = []
                if isinstance(queue, list):
                    session.queue = [item for item in queue if isinstance(item, dict)]
                    self._saved_queues[session.id] = (id(session.queue), len(session.queue))
        self.sessions = {
            key: value
            for key, value in restored_sessions.items()
            if value.attempt_ids or value.queue
        }
        self.attempts = restored_attempts
        self.checkpoints = restored_checkpoints
        # Version-one state did not have durable Smart View checkpoints. Migrate
        # any recent attempt history so an upgrade cannot redial known contacts.
        for session in sorted(self.sessions.values(), key=lambda item: item.updated_at):
            if not CloseDialer._valid_smart_view_id(session.smart_view_id):
                continue
            attempted_ids = [
                self.attempts[attempt_id].contact_id
                for attempt_id in session.attempt_ids
                if attempt_id in self.attempts
            ]
            if attempted_ids:
                self._update_checkpoint(session, attempted_ids)

    @staticmethod
    def _session_record(session: DialSession) -> dict[str, Any]:
        # This file is rewritten on every call event, on the event loop. Every Start put a
        # whole Smart View into its session, so the file grew to 10 MB, 99% of it the
        # queues of finished sessions. Each write stalled the loop long enough that Twilio
        # gave up on status webhooks and pages waited 10-25 s for an answer. A finished
        # session never dials again, so its queue is not kept. Built shallowly because
        # asdict deep-copies every contact, and json.dump reads it straight away.
        record = {item.name: getattr(session, item.name) for item in fields(DialSession)}
        # A running session's queue is in its own file, written when it changes; a
        # finished session's is not kept at all. Re-encoding one 1,700-contact queue
        # on every event still cost 86 ms a write.
        record["queue"] = []
        return record

    @staticmethod
    def _attempt_record(attempt: DialAttempt) -> dict[str, Any]:
        record = {item.name: getattr(attempt, item.name) for item in fields(DialAttempt)}
        record["transcript"] = []
        return record

    def _queue_path(self, session_id: str) -> Path:
        return self.queue_dir / f"{session_id}.json"

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(path)

    def _persist_queues(self) -> None:
        """Write a running session's queue only when it changed. A queue changes at Start
        and when a dropped person is queued for a call back, and always grows when it
        does, so its list and length say whether the file is current. Written before the
        state file, so after a crash the queue is never older than the progress through it."""
        running = {
            session_id: session
            for session_id, session in self.sessions.items()
            if session.status in ACTIVE_SESSION_STATUSES
        }
        for session_id, session in running.items():
            signature = (id(session.queue), len(session.queue))
            if self._saved_queues.get(session_id) != signature:
                self._write_json(self._queue_path(session_id), session.queue)
                self._saved_queues[session_id] = signature
        for session_id in [item for item in self._saved_queues if item not in running]:
            self._saved_queues.pop(session_id, None)
            with contextlib.suppress(OSError):
                self._queue_path(session_id).unlink()

    def _persist_state(self) -> None:
        payload = {
            "version": 3,
            "saved_at": utc_now(),
            "sessions": [self._session_record(item) for item in list(self.sessions.values())[-200:]],
            "attempts": [self._attempt_record(item) for item in list(self.attempts.values())[-600:]],
            "checkpoints": [asdict(item) for item in list(self.checkpoints.values())[-500:]],
        }
        try:
            self._persist_queues()
            self._write_json(self.state_path, payload)
        except OSError as exc:
            raise LiveDialerError("The dialer could not safely persist its state.") from exc

    def _refresh_session_state(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        # "stopping" included: the calls a Stop cancels report back while it runs, and
        # recomputing turned it into "running", so the next refill dialed a fresh batch.
        # Six people were once called after Stop was pressed.
        if session is None or session.status in HALTED_SESSION_STATUSES:
            return
        attempts = [self.attempts[item] for item in session.attempt_ids if item in self.attempts]
        active = [item for item in attempts if item.status not in TERMINAL_CALL_STATUSES]
        if session.operator_status not in {"answered", "in-progress"} and not session.attempt_ids:
            next_status = "operator-connecting"
        elif session.human_attempt_id:
            winner = self.attempts.get(session.human_attempt_id)
            if winner is not None and (
                winner.status == "bridged"
                or (winner.outcome == "human-bridged" and winner.status not in TERMINAL_CALL_STATUSES)
            ):
                next_status = "human-connected"
            else:
                session.human_attempt_id = ""
                if not active and session.next_index < len(session.queue):
                    next_status = "running"
                elif not active:
                    next_status = (
                        "failed"
                        if attempts and all(item.outcome == "provider-error" for item in attempts)
                        else "completed"
                    )
                elif any(item.status == "bridged" for item in active):
                    next_status = "human-connected"
                elif any(item.status in {"human-detected", "operator-connecting"} for item in active):
                    next_status = "operator-connecting"
                else:
                    next_status = "running"
        elif not active and session.next_index < len(session.queue):
            next_status = "running"
        elif not active:
            next_status = (
                "failed"
                if attempts and all(item.outcome == "provider-error" for item in attempts)
                else "completed"
            )
        elif any(item.status == "bridged" for item in active):
            next_status = "human-connected"
        elif any(item.status in {"human-detected", "operator-connecting"} for item in active):
            next_status = "operator-connecting"
        else:
            next_status = "running"
        if next_status != session.status:
            session.status = next_status
            session.updated_at = utc_now()

    @property
    def configured(self) -> bool:
        return all(
            (
                self.account_sid.startswith("AC"),
                self.api_key_sid.startswith("SK"),
                self.api_key_secret,
                self.caller_number,
                self.openai_api_key,
                len(self.webhook_secret) >= 24,
            )
        )

    @property
    def ready(self) -> bool:
        operator_ok = self.browser_calling_available or (
            self.operator_number
            and (self.unrestricted or self.operator_number in self.allowed_numbers)
        )
        has_targets = self.unrestricted or bool(self.allowed_numbers)
        return bool(
            self.configured
            and self.settings.profile.brand_is_set
            and self.live_mode
            and has_targets
            and operator_ok
        )

    def operator_voice_identity(self, operator_email: str = "") -> str:
        if not operator_email:
            return self.voice_identity
        clean = clean_operator_identity(operator_email)
        if not clean:
            return self.voice_identity
        return f"{self.voice_identity}-{clean}"

    def _checkpoint_key(self, operator_email: str, smart_view_id: str) -> str:
        clean = clean_operator_identity(operator_email) if operator_email else ""
        if not clean:
            return smart_view_id
        return f"{clean}:{smart_view_id}"

    def _get_checkpoint(self, operator_email: str, smart_view_id: str) -> DialCheckpoint | None:
        key = self._checkpoint_key(operator_email, smart_view_id)
        if key in self.checkpoints:
            return self.checkpoints[key]
        clean = clean_operator_identity(operator_email) if operator_email else ""
        if clean and f"{clean}:{smart_view_id}" in self.checkpoints:
            return self.checkpoints[f"{clean}:{smart_view_id}"]
        if smart_view_id in self.checkpoints:
            return self.checkpoints[smart_view_id]
        return None

    def _recording_paths(self, slot: str, operator_email: str = "") -> tuple[Path, Path]:
        slot = self._slot(slot)
        clean = clean_operator_identity(operator_email) if operator_email else ""
        stem = RECORDING_FILE_STEMS[slot]
        if clean:
            op_audio = self.settings.state_dir / f"{stem}-{clean}"
            op_meta = self.settings.state_dir / f"{stem}-{clean}.json"
            return op_audio, op_meta
        return self.settings.state_dir / stem, self.settings.state_dir / f"{stem}.json"

    @property
    def voicemail_configured(self) -> bool:
        return bool(self.recording_metadata("voicemail").get("configured"))

    def voicemail_metadata(self, operator_email: str = "") -> dict[str, Any]:
        return self.recording_metadata("voicemail", operator_email=operator_email)

    @staticmethod
    def _slot(slot: str) -> str:
        normalized = str(slot or "").strip().lower()
        if normalized not in RECORDING_FILE_STEMS:
            raise LiveDialerError("Unknown recording slot.")
        return normalized

    def recording_metadata(self, slot: str, operator_email: str = "") -> dict[str, Any]:
        slot = self._slot(slot)
        clean = clean_operator_identity(operator_email) if operator_email else ""
        audio_path, meta_path = self._recording_paths(slot, operator_email)
        if not clean and not (audio_path.exists() and meta_path.exists()):
            stem = RECORDING_FILE_STEMS[slot]
            fallback_audio = self.settings.state_dir / stem
            fallback_meta = self.settings.state_dir / f"{stem}.json"
            if fallback_audio.exists() and fallback_meta.exists():
                audio_path, meta_path = fallback_audio, fallback_meta
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            size = audio_path.stat().st_size
        except (OSError, json.JSONDecodeError, TypeError):
            return {"configured": False}
        if not isinstance(metadata, dict) or not 1024 <= size <= 5_000_000:
            return {"configured": False}
        content_type = str(metadata.get("content_type") or "")
        if content_type not in {"audio/mpeg", "audio/wav"}:
            return {"configured": False}
        return {
            "configured": True,
            "filename": str(metadata.get("filename") or "Recording"),
            "content_type": content_type,
            "size": size,
            "sha256": str(metadata.get("sha256") or ""),
            "updated_at": str(metadata.get("updated_at") or ""),
            "duration_seconds": metadata.get("duration_seconds"),
        }

    def recordings_metadata(self, operator_email: str = "") -> dict[str, dict[str, Any]]:
        return {
            slot: self.recording_metadata(slot, operator_email=operator_email)
            for slot in RECORDING_SLOTS
        }

    def save_voicemail_recording(
        self, *, filename: str, content_type: str, data_base64: str, operator_email: str = ""
    ) -> dict[str, Any]:
        return self.save_recording(
            "voicemail",
            filename=filename,
            content_type=content_type,
            data_base64=data_base64,
            operator_email=operator_email,
        )

    def delete_recording(self, slot: str, operator_email: str = "") -> dict[str, Any]:
        audio_path, meta_path = self._recording_paths(slot, operator_email)
        for path in (audio_path, meta_path):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise LiveDialerError("The recording could not be removed.") from exc
        return self.recording_metadata(slot, operator_email=operator_email)

    def save_recording(
        self,
        slot: str,
        *,
        filename: str,
        content_type: str,
        data_base64: str,
        operator_email: str = "",
    ) -> dict[str, Any]:
        slot = self._slot(slot)
        audio_path, meta_path = self._recording_paths(slot, operator_email)
        safe_name = Path(str(filename or "")).name[:160]
        normalized_type = str(content_type or "").lower().split(";", 1)[0].strip()
        if normalized_type in {"audio/mp3", "audio/mpeg3", "audio/x-mpeg-3"}:
            normalized_type = "audio/mpeg"
        if normalized_type in {"audio/wave", "audio/x-wav"}:
            normalized_type = "audio/wav"
        if normalized_type not in {"audio/mpeg", "audio/wav"}:
            raise LiveDialerError("Upload an MP3 or WAV recording.")
        try:
            audio = base64.b64decode(str(data_base64 or ""), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise LiveDialerError("The recording was not valid base64 audio.") from exc
        if not 1024 <= len(audio) <= 5_000_000:
            raise LiveDialerError("The recording must be between 1 KB and 5 MB.")
        is_wav = len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"
        is_mp3 = audio[:3] == b"ID3" or (
            len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0
        )
        if (normalized_type == "audio/wav" and not is_wav) or (
            normalized_type == "audio/mpeg" and not is_mp3
        ):
            raise LiveDialerError("The uploaded file contents did not match its audio type.")
        duration = audio_duration_seconds(audio, normalized_type)
        if slot == "greeting" and duration is not None and duration > MAX_GREETING_SECONDS:
            raise LiveDialerError(
                f"The hello must be under {MAX_GREETING_SECONDS:g} seconds so the contact's "
                f"first words still reach the classifier. This one is {duration:.1f} seconds."
            )
        if slot == "dropped" and duration is not None and duration > 6.0:
            raise LiveDialerError(
                f"The connection glitch message must be under 6.0 seconds. This one is {duration:.1f} seconds."
            )
        digest = hashlib.sha256(audio).hexdigest()
        metadata = {
            "filename": safe_name or (f"{slot}.mp3" if is_mp3 else f"{slot}.wav"),
            "content_type": normalized_type,
            "sha256": digest,
            "updated_at": utc_now(),
            "duration_seconds": round(duration, 2) if duration is not None else None,
        }
        try:
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile("wb", dir=audio_path.parent, delete=False) as temporary:
                temporary.write(audio)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_audio = Path(temporary.name)
            os.chmod(temporary_audio, 0o600)
            temporary_audio.replace(audio_path)
            with NamedTemporaryFile(
                "w", encoding="utf-8", dir=meta_path.parent, delete=False
            ) as temporary:
                json.dump(metadata, temporary, ensure_ascii=False, separators=(",", ":"))
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_meta = Path(temporary.name)
            os.chmod(temporary_meta, 0o600)
            temporary_meta.replace(meta_path)
        except OSError as exc:
            raise LiveDialerError("The recording could not be stored safely.") from exc
        return self.recording_metadata(slot, operator_email=operator_email)

    @property
    def browser_calling_available(self) -> bool:
        """The browser can take the operator leg whenever Twilio can mint it a token."""
        return bool(self.account_sid and self.api_key_sid and self.api_key_secret)

    def voice_access_token(
        self, *, ttl_seconds: int = 3600, operator_email: str = ""
    ) -> dict[str, Any]:
        """A Twilio access token letting one browser receive the operator leg."""
        if not self.browser_calling_available:
            raise LiveDialerError("Twilio credentials are incomplete.")
        identity = self.operator_voice_identity(operator_email)
        now = int(datetime.now(UTC).timestamp())
        payload = {
            "jti": f"{self.api_key_sid}-{now}",
            "iss": self.api_key_sid,
            "sub": self.account_sid,
            "nbf": now - 5,
            "exp": now + max(300, min(int(ttl_seconds), 86400)),
            "grants": {
                "identity": identity,
                "voice": {"incoming": {"allow": True}},
            },
        }
        token = jwt.encode(
            payload,
            self.api_key_secret,
            algorithm="HS256",
            headers={"cty": "twilio-fpa;v=1"},
        )
        return {
            "token": token,
            "identity": identity,
            "expires_at": datetime.fromtimestamp(payload["exp"], UTC).isoformat(),
        }

    def blockers(self) -> list[str]:
        blockers: list[str] = []
        if not self.settings.profile.brand_is_set:
            blockers.append(
                "Set your company name in dialer.toml ([brand] name): it is spoken to the people you call."
            )
        if not self.configured:
            blockers.append("Twilio, OpenAI, or webhook credentials are incomplete.")
        if not self.live_mode:
            blockers.append("The server-side live-mode switch is disabled.")
        if not self.unrestricted and not self.allowed_numbers:
            blockers.append("No numbers are approved for calling yet, so the dialer will not call anyone.")
        # An operator phone number is only required when the operator is a phone.
        # With the browser taking the leg there is nothing to configure, so this
        # stopped being a reason the dialer cannot run at all.
        if not self.browser_calling_available and not self.operator_number:
            blockers.append("Add the phone number that should ring, or take the call in the browser.")
        elif self.operator_number and not self.unrestricted and self.operator_number not in self.allowed_numbers:
            blockers.append("The phone that rings must itself be approved for calling.")
        # A missing voicemail message is a choice, not a fault: an answering machine is
        # hung up on in silence instead. It stopped being a blocker because refusing to
        # dial at all is not the same thing as declining to leave a message.
        return blockers

    def status(self, operator_email: str = "") -> dict[str, Any]:
        clean_op = clean_operator_identity(operator_email) if operator_email else ""
        active = sorted(
            (
                session
                for session in self.sessions.values()
                if session.status in ACTIVE_SESSION_STATUSES
                and (not clean_op or clean_operator_identity(session.operator_email) == clean_op)
            ),
            key=lambda session: session.updated_at,
            reverse=True,
        )
        identity = self.operator_voice_identity(operator_email) if operator_email else self.voice_identity
        return {
            "configured": self.configured,
            "live_enabled": self.live_mode,
            "ready": self.ready,
            "blockers": self.blockers(),
            "caller_number_masked": mask_phone(self.caller_number),
            "operator_configured": bool(self.operator_number),
            "browser_calling": self.browser_calling_available,
            "voice_identity": identity,
            "callback_number_masked": mask_phone(self.callback_number),
            "callback_destination": "close" if self.callback_number else "operator",
            "recordings": self.recordings_metadata(operator_email=operator_email),
            "max_greeting_seconds": MAX_GREETING_SECONDS,
            "voicemail": self.voicemail_metadata(operator_email=operator_email),
            "callback_routing": self.inbound_metadata(),
            "unrestricted": self.unrestricted,
            "allowlist_count": len(self.allowed_numbers),
            "blocklist_count": len(self.blocked_numbers),
            "max_concurrency": self.max_concurrency,
            "max_session_contacts": self.max_session_contacts,
            "active_sessions": len(active),
            "active_session": (
                {
                    "id": active[0].id,
                    "status": active[0].status,
                    "smart_view_id": active[0].smart_view_id,
                    "smart_view_name": active[0].smart_view_name,
                }
                if active
                else None
            ),
            "ai_mode": "Human-first screening classifier",
            "provider": "Twilio Programmable Voice",
            "operator_numbers": self.operator_numbers(operator_email),
            "numbers_count": self.operator_numbers(operator_email)["count"],
        }

    def _dial_index(self) -> dict[str, dict[str, Any]]:
        """Every contact's pooled dial history: dials, last dial, ever answered."""
        index: dict[str, dict[str, Any]] = {}
        for checkpoint in list(self.checkpoints.values()):
            history = checkpoint.contact_history or {}
            # Contacts dialed before per-contact history existed carry no date of
            # their own; the checkpoint's last update is the latest they can be.
            fallback = checkpoint.updated_at or ""
            for cid in set(checkpoint.attempted_contact_ids) | set(history):
                item = history.get(cid)
                entry = index.setdefault(cid, {"attempts": 0, "last": "", "answered": False})
                entry["attempts"] += max(1, item.attempts) if item else 1
                last = (item.last_attempted_at if item else "") or fallback
                if last > entry["last"]:
                    entry["last"] = last
                entry["answered"] = entry["answered"] or bool(item and item.ever_answered)
        return index

    def _dial_block(
        self, contact_id: str, index: dict[str, dict[str, Any]], now: datetime | None = None
    ) -> tuple[str, str]:
        """Why a contact cannot be dialed now ('' when it can), and when it returns."""
        entry = index.get(contact_id)
        if not entry:
            return "", ""
        if entry["answered"]:
            return "Reached a person before", ""
        if entry["attempts"] >= self.max_dials_per_contact:
            return f"No answer after {entry['attempts']} dials", ""
        try:
            last = datetime.fromisoformat(entry["last"].replace("Z", "+00:00"))
        except ValueError:
            return "Dialed before; date unknown", ""
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        # Back from the start of that day (UTC), so a morning session picks up everyone
        # dialed on the same weekday a week earlier, whatever hour they were rung.
        due = datetime.combine((last + self.redial_after).date(), datetime.min.time(), UTC)
        if (now or datetime.now(UTC)) < due:
            return f"No answer; back {due.strftime('%a %d %b')}", due.isoformat()
        return "", ""

    def decorate_contacts(
        self, payload: dict[str, Any], operator_email: str = ""
    ) -> dict[str, Any]:
        contacts = payload.get("contacts")
        if not isinstance(contacts, list):
            return payload
        selected_view = payload.get("selected_smart_view")
        smart_view_id = (
            str(selected_view.get("id") or "") if isinstance(selected_view, dict) else ""
        )
        checkpoint = self._get_checkpoint(operator_email, smart_view_id)
        dial_index = self._dial_index()
        waiting_ids: set[str] = set()
        current_ids: set[str] = set()
        for contact in contacts:
            if isinstance(contact, dict):
                contact_id = str(contact.get("contact_id") or "")
                if contact_id:
                    current_ids.add(contact_id)
                reason, due = self._dial_block(contact_id, dial_index)
                contact["dialer_attempted"] = bool(reason)
                contact["redial_reason"] = reason
                contact["redial_at"] = due
                if reason and contact_id:
                    waiting_ids.add(contact_id)
                phone = normalize_phone(contact.get("phone", ""))
                contact["timezone_info"] = get_contact_local_time(phone or str(contact.get("phone") or ""))
                if self.unrestricted:
                    allowed = bool(phone) and phone not in self.blocked_numbers
                else:
                    allowed = phone in self.allowed_numbers
                if contact.get("has_active_deal"):
                    contact["live_allowed"] = False
                    contact["dialer_blocked"] = True
                    contact["blocked_reason"] = contact.get("deal_reason") or "Active deal in Close"
                else:
                    contact["live_allowed"] = allowed
        attempted_current = len(current_ids.intersection(waiting_ids))
        payload["checkpoint"] = {
            "smart_view_id": smart_view_id,
            "attempted_count": attempted_current,
            "remaining_count": max(0, len(current_ids) - attempted_current),
            "source_total": len(current_ids),
            "updated_at": checkpoint.updated_at if checkpoint else "",
            "last_session_id": checkpoint.last_session_id if checkpoint else "",
            "complete": bool(current_ids) and attempted_current == len(current_ids),
        }
        payload["live"] = self.status(operator_email=operator_email)
        return payload

    def _update_checkpoint(self, session: DialSession, contact_ids: list[str]) -> DialCheckpoint:
        checkpoint = self._get_checkpoint(session.operator_email, session.smart_view_id)
        if checkpoint is None:
            checkpoint = DialCheckpoint(
                smart_view_id=session.smart_view_id,
                smart_view_name=session.smart_view_name,
                operator_email=session.operator_email,
            )
            key = self._checkpoint_key(session.operator_email, session.smart_view_id)
            self.checkpoints[key] = checkpoint
        checkpoint.smart_view_name = session.smart_view_name
        checkpoint.source_total = max(checkpoint.source_total, session.source_total)
        checkpoint.last_session_id = session.id
        checkpoint.attempted_contact_ids = list(
            dict.fromkeys([*checkpoint.attempted_contact_ids, *contact_ids])
        )[-1000:]
        now_str = utc_now()
        for cid in contact_ids:
            if cid and cid.startswith("cont_") and cid not in checkpoint.contact_history:
                checkpoint.contact_history[cid] = ContactHistory(
                    contact_id=cid,
                    attempts=1,
                    last_outcome="completed",
                    last_attempted_at=now_str,
                    retired=True,
                )
        checkpoint.updated_at = now_str
        return checkpoint

    def _record_attempt_outcome(self, session: DialSession, attempt: DialAttempt) -> None:
        cid = attempt.contact_id
        if not cid or not cid.startswith("cont_"):
            return
        if attempt.checkpoint_recorded:
            return
        # Dropped lines and unreached competitor lines are not retired from checkpoint
        if attempt.outcome in {"dropped-line", "canceled-after-human"}:
            return
        checkpoint = self._get_checkpoint(session.operator_email, session.smart_view_id)
        if checkpoint is None:
            checkpoint = DialCheckpoint(
                smart_view_id=session.smart_view_id,
                smart_view_name=session.smart_view_name,
                operator_email=session.operator_email,
            )
            key = self._checkpoint_key(session.operator_email, session.smart_view_id)
            self.checkpoints[key] = checkpoint

        now_str = utc_now()
        now_dt = datetime.now(UTC)
        history = checkpoint.contact_history.get(cid)
        if history is None:
            history = ContactHistory(contact_id=cid)
            checkpoint.contact_history[cid] = history
        history.attempts += 1
        history.last_outcome = attempt.outcome or attempt.status or "completed"
        history.last_attempted_at = now_str
        if now_dt.hour not in history.hours_tried:
            history.hours_tried.append(now_dt.hour)
        if (
            attempt.human_detected
            or attempt.outcome == "human-bridged"
            or attempt.answered_by == "human"
            or attempt.status == "bridged"
        ):
            history.ever_answered = True

        history.retired = True
        checkpoint.smart_view_name = session.smart_view_name
        checkpoint.source_total = max(checkpoint.source_total, session.source_total)
        checkpoint.last_session_id = session.id
        checkpoint.attempted_contact_ids = list(
            dict.fromkeys([*checkpoint.attempted_contact_ids, cid])
        )[-1000:]
        checkpoint.updated_at = now_str
        attempt.checkpoint_recorded = True

    async def reset_checkpoint(
        self, smart_view_id: str, operator_email: str = ""
    ) -> dict[str, Any]:
        if not CloseDialer._valid_smart_view_id(smart_view_id):
            raise LiveDialerError("Choose a valid Close Smart View.")
        clean = clean_operator_identity(operator_email) if operator_email else ""
        async with self._lock:
            if any(
                session.smart_view_id == smart_view_id
                and session.status in ACTIVE_SESSION_STATUSES
                and (not clean or clean_operator_identity(session.operator_email) == clean)
                for session in self.sessions.values()
            ):
                raise LiveDialerError("Stop the active session before resetting this Smart View.")
            key = self._checkpoint_key(operator_email, smart_view_id)
            removed = self.checkpoints.pop(key, None)
            if removed is None and not clean:
                removed = self.checkpoints.pop(smart_view_id, None)
            self._persist_state()
        return {
            "smart_view_id": smart_view_id,
            "reset": removed is not None,
            "attempted_count": 0,
        }

    def _resource_signature(self, value: str) -> str:
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _attempt_signature(self, attempt_id: str) -> str:
        return self._resource_signature(f"attempt:{attempt_id}")

    def verify_signature(self, attempt_id: str, signature: str) -> bool:
        if not self.webhook_secret or attempt_id not in self.attempts:
            return False
        return hmac.compare_digest(self._attempt_signature(attempt_id), signature)

    def _session_signature(self, session_id: str) -> str:
        return self._resource_signature(f"session:{session_id}")

    def verify_session_signature(self, session_id: str, signature: str) -> bool:
        if not self.webhook_secret or session_id not in self.sessions or len(signature) != 64:
            return False
        return hmac.compare_digest(self._session_signature(session_id), signature)

    def verify_inbound_signature(self, signature: str) -> bool:
        expected = self._resource_signature("inbound-routing")
        return bool(signature) and hmac.compare_digest(expected, signature)

    def verify_media_signature(self, signature: str, slot: str = "voicemail") -> bool:
        # The slot is inside the signed string, so a URL minted for the hello cannot
        # be replayed to fetch the voicemail message.
        expected = self._resource_signature(f"{self._slot(slot)}-media")
        return bool(signature) and hmac.compare_digest(expected, signature)

    def _callback_url(self, endpoint: str, attempt_id: str) -> str:
        return (
            f"{self.public_base_url}/{endpoint}?attempt_id={attempt_id}"
            f"&sig={self._attempt_signature(attempt_id)}"
            "#rc=2&ct=1000&rt=6000&rp=ct,rt,5xx"
        )

    def _session_callback_url(self, endpoint: str, session_id: str) -> str:
        return (
            f"{self.public_base_url}/{endpoint}?session_id={session_id}"
            f"&sig={self._session_signature(session_id)}"
            "#rc=2&ct=1000&rt=6000&rp=ct,rt,5xx"
        )

    def voicemail_media_url(self, operator_email: str = "") -> str:
        return self.recording_media_url("voicemail", operator_email=operator_email)

    def recording_media_url(self, slot: str, operator_email: str = "") -> str:
        slot = self._slot(slot)
        version = str(self.recording_metadata(slot, operator_email=operator_email).get("sha256") or "")[:16]
        clean = clean_operator_identity(operator_email) if operator_email else ""
        op_param = f"&op={clean}" if clean else ""
        # Twilio caches media by URL, so the digest in the query is what makes a
        # re-recorded file take effect on the very next call instead of the next hour.
        return (
            f"{self.public_base_url}/recording-media/{slot}"
            f"?sig={self._resource_signature(f'{slot}-media')}&v={version}{op_param}"
        )

    def inbound_voice_url(self) -> str:
        return (
            f"{self.public_base_url}/inbound"
            f"?sig={self._resource_signature('inbound-routing')}"
        )

    def voicemail_audio(self, operator_email: str = "") -> tuple[bytes, str]:
        return self.recording_audio("voicemail", operator_email=operator_email)

    def recording_audio(self, slot: str, operator_email: str = "") -> tuple[bytes, str]:
        slot = self._slot(slot)
        metadata = self.recording_metadata(slot, operator_email=operator_email)
        if not metadata.get("configured"):
            raise LiveDialerError("The recording is unavailable.")
        clean = clean_operator_identity(operator_email) if operator_email else ""
        audio_path, _ = self._recording_paths(slot, operator_email)
        if not clean and not audio_path.exists():
            stem = RECORDING_FILE_STEMS[slot]
            fallback_audio = self.settings.state_dir / stem
            if fallback_audio.exists():
                audio_path = fallback_audio
        try:
            return audio_path.read_bytes(), str(metadata["content_type"])
        except OSError as exc:
            raise LiveDialerError("The recording is unavailable.") from exc

    async def call_recording_audio(self, recording_sid: str) -> tuple[bytes, str]:
        clean_sid = str(recording_sid or "").strip()
        if not re.match(r"^RE[0-9a-fA-F]{32}$", clean_sid):
            raise LiveDialerError("Invalid recording identifier.")
        cache_dir = self.settings.state_dir / "call_recordings"
        cache_file = cache_dir / f"{clean_sid}.mp3"
        if cache_file.exists():
            try:
                return cache_file.read_bytes(), "audio/mpeg"
            except OSError:
                pass
        try:
            async with httpx.AsyncClient(
                auth=httpx.BasicAuth(self.api_key_sid, self.api_key_secret),
                timeout=30,
                follow_redirects=True,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.twilio_api_base}/Accounts/{self.account_sid}/Recordings/{clean_sid}.mp3"
                )
                response.raise_for_status()
                audio_bytes = response.content
        except (httpx.HTTPError, OSError) as exc:
            raise LiveDialerError("The call recording is unavailable.") from exc
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(audio_bytes)
        except OSError:
            pass
        return audio_bytes, "audio/mpeg"

    def _twilio_key_path(self, operator_email: str) -> Path | None:
        if not self.settings or not getattr(self.settings, "state_dir", None):
            return None
        clean = clean_operator_identity((operator_email or "").strip().lower())
        return self.settings.state_dir / f"dialer-twilio-key-{clean}.json"

    def _twilio_credentials_for_operator(
        self, operator_email: str = ""
    ) -> tuple[str, str, str, str]:
        path = self._twilio_key_path(operator_email)
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                ac = data.get("account_sid")
                api_sid = data.get("api_key_sid")
                sec = data.get("api_key_secret")
                phone = data.get("phone_number") or self.caller_number
                if ac and api_sid and sec:
                    return (ac, api_sid, sec, phone)
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass
        return (self.account_sid, self.api_key_sid, self.api_key_secret, self.caller_number)

    async def _twilio_post(
        self, path: str, data: Any, *, timeout: float = 20, operator_email: str = ""
    ) -> dict[str, Any]:
        _, api_sid, api_sec, _ = self._twilio_credentials_for_operator(operator_email)
        async with httpx.AsyncClient(
            auth=httpx.BasicAuth(api_sid, api_sec),
            timeout=timeout,
            transport=self.transport,
        ) as client:
            encoded = str(httpx.QueryParams(data)).encode("utf-8")
            response = await client.post(
                f"{self.twilio_api_base}{path}",
                content=encoded,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.is_error:
                error_detail = ""
                error_code = ""
                try:
                    err_json = response.json()
                    error_detail = str(err_json.get("message") or "")
                    error_code = str(err_json.get("code") or "")
                except Exception:
                    pass
                msg = f"Twilio API error {response.status_code}"
                if error_code:
                    msg += f" (code {error_code})"
                if error_detail:
                    msg += f": {error_detail}"
                raise LiveDialerProviderError(
                    msg,
                    status_code=response.status_code,
                    code=error_code,
                    detail=error_detail,
                )
            payload = response.json()
        if not isinstance(payload, dict):
            raise LiveDialerError("Twilio returned an invalid response.")
        return payload

    async def _twilio_get(
        self, path: str, *, timeout: float = 10, operator_email: str = ""
    ) -> dict[str, Any]:
        _, api_sid, api_sec, _ = self._twilio_credentials_for_operator(operator_email)
        async with httpx.AsyncClient(
            auth=httpx.BasicAuth(api_sid, api_sec),
            timeout=timeout,
            transport=self.transport,
        ) as client:
            response = await client.get(f"{self.twilio_api_base}{path}")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise LiveDialerError("Twilio returned an invalid response.")
        return payload

    async def _twilio_delete(
        self, path: str, *, timeout: float = 15, operator_email: str = ""
    ) -> None:
        _, api_sid, api_sec, _ = self._twilio_credentials_for_operator(operator_email)
        async with httpx.AsyncClient(
            auth=httpx.BasicAuth(api_sid, api_sec),
            timeout=timeout,
            transport=self.transport,
        ) as client:
            response = await client.delete(f"{self.twilio_api_base}{path}")
            if response.status_code not in (200, 204, 404):
                response.raise_for_status()

    def inbound_metadata(self) -> dict[str, Any]:
        try:
            metadata = json.loads(self.inbound_meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return {"configured": False}
        if not isinstance(metadata, dict):
            return {"configured": False}
        return {
            "configured": bool(metadata.get("configured")),
            "updated_at": str(metadata.get("updated_at") or ""),
            "phone_sid_masked": (
                f"PN...{str(metadata.get('phone_sid') or '')[-4:]}"
                if str(metadata.get("phone_sid") or "").startswith("PN")
                else ""
            ),
        }

    async def configure_inbound_routing(self) -> dict[str, Any]:
        # Either destination will do: a Close number puts the callback on the lead,
        # the operator's phone is the fallback. Requiring an operator here predates
        # the Close route and would block the better of the two.
        if not self.configured or not (self.callback_number or self.operator_number):
            raise LiveDialerError("Configure Twilio and a callback destination first.")
        query = str(httpx.QueryParams({"PhoneNumber": self.caller_number, "PageSize": "20"}))
        payload = await self._twilio_get(
            f"/Accounts/{self.account_sid}/IncomingPhoneNumbers.json?{query}"
        )
        numbers = payload.get("incoming_phone_numbers") or []
        phone_sid = next(
            (
                str(item.get("sid") or "")
                for item in numbers
                if isinstance(item, dict)
                and normalize_phone(item.get("phone_number", "")) == self.caller_number
            ),
            "",
        )
        if not phone_sid.startswith("PN"):
            raise LiveDialerError("The configured Twilio caller number was not found in inventory.")
        await self._twilio_post(
            f"/Accounts/{self.account_sid}/IncomingPhoneNumbers/{phone_sid}.json",
            {"VoiceUrl": self.inbound_voice_url(), "VoiceMethod": "POST"},
        )
        metadata = {"configured": True, "phone_sid": phone_sid, "updated_at": utc_now()}
        try:
            self.inbound_meta_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.inbound_meta_path.parent, delete=False
            ) as temporary:
                json.dump(metadata, temporary, ensure_ascii=False, separators=(",", ":"))
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o600)
            temporary_path.replace(self.inbound_meta_path)
        except OSError as exc:
            raise LiveDialerError("Callback routing was set but its local status was not saved.") from exc
        return self.inbound_metadata()

    def _numbers_path_for_operator(self, operator_email: str) -> Path:
        clean = clean_operator_identity(operator_email) if operator_email else ""
        stem = f"dialer-numbers-{clean}.json" if clean else "dialer-numbers.json"
        return self.settings.state_dir / stem

    def operator_number_pool(self, operator_email: str = "") -> list[dict[str, Any]]:
        """Get the list of active numbers for line allocation."""
        numbers_dict = self.operator_numbers(operator_email)
        return numbers_dict.get("numbers", [])

    def operator_numbers(self, operator_email: str = "") -> dict[str, Any]:
        """List phone numbers assigned to an operator with status and labels."""
        email = (operator_email or "").strip().lower()
        path = self._numbers_path_for_operator(email)
        raw_numbers = []
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                raw_numbers = data.get("numbers", [])
            except (OSError, json.JSONDecodeError):
                raw_numbers = []

        if not raw_numbers and self.caller_number:
            raw_numbers = [
                {
                    "sid": "PN_default",
                    "phone_number": self.caller_number,
                    "friendly_name": f"{self.settings.profile.brand} primary line",
                    "label": "Number 1",
                    "locality": "",
                    "region": "",
                    "configured": True,
                }
            ]

        main_line = normalize_phone(self.caller_number)
        formatted = []
        for i, item in enumerate(raw_numbers, start=1):
            num = normalize_phone(item.get("phone_number", ""))
            formatted.append(
                {
                    "sid": str(item.get("sid") or f"num_{i}"),
                    "phone_number": num,
                    # The main line: never released, only taken out of a rotation.
                    "primary": num == main_line,
                    "formatted": self._format_us_phone(num),
                    "label": str(item.get("label") or f"Number {i}"),
                    "locality": str(item.get("locality") or ""),
                    "region": str(item.get("region") or ""),
                    "configured": bool(item.get("configured", True)),
                    "health": self._calculate_number_health(num),
                }
            )
        return {
            "operator_email": email,
            "count": len(formatted),
            "numbers": formatted,
        }

    def _calculate_number_health(self, phone_number: str) -> dict[str, Any]:
        """Assess carrier reputation and spam flag status from recent dialing outcomes."""
        norm = normalize_phone(phone_number)
        matching = [
            a
            for a in self.attempts.values()
            if normalize_phone(getattr(a, "caller_number", "") or "") == norm
        ]
        total_calls = len(matching)
        connected_calls = len(
            [
                a
                for a in matching
                if a.outcome in {"human-bridged", "human", "bridged"} or a.human_detected
            ]
        )
        blocked_calls = len(
            [
                a
                for a in matching
                if a.outcome in {"busy", "failed", "invalid", "provider-error"}
                or a.status in {"failed", "busy"}
            ]
        )
        voicemail_calls = len(
            [
                a
                for a in matching
                if a.voicemail_detected or "voicemail" in (a.outcome or "")
            ]
        )

        connect_rate = round((connected_calls / total_calls) * 100, 1) if total_calls > 0 else 0.0
        block_rate = round((blocked_calls / total_calls) * 100, 1) if total_calls > 0 else 0.0

        if total_calls < 8:
            status = "fresh"
            badge = "Fresh"
            message = "Pristine reputation · Ready to dial"
        elif (total_calls >= 15 and connect_rate < 4.0) or block_rate >= 35.0:
            status = "cooked"
            badge = "Cooked"
            message = f"Carrier spam flagged ({block_rate}% blocked); recommend replacing"
        elif connect_rate < 8.0 or block_rate >= 20.0:
            status = "warning"
            badge = "Cooling Down"
            message = f"Answer rate dipping ({connect_rate}% connect); rest recommended"
        else:
            status = "healthy"
            badge = "Healthy"
            message = f"Strong answer rate ({connect_rate}%) · Clean reputation"

        return {
            "status": status,
            "badge": badge,
            "message": message,
            "total_calls": total_calls,
            "connected_calls": connected_calls,
            "blocked_calls": blocked_calls,
            "voicemail_calls": voicemail_calls,
            "connect_rate": connect_rate,
            "block_rate": block_rate,
        }

    def update_operator_number_label(
        self, operator_email: str, phone_sid: str, label: str
    ) -> dict[str, Any]:
        """Update the custom label/nickname for an operator's phone number."""
        email = (operator_email or "").strip().lower()
        clean_label = (label or "").strip()
        if not clean_label:
            raise LiveDialerError("Label cannot be empty.")
        path = self._numbers_path_for_operator(email)
        if not path.exists():
            pool = self.operator_numbers(email)["numbers"]
            data = {
                "operator_email": email,
                "updated_at": utc_now(),
                "numbers": pool,
            }
        else:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise LiveDialerError("Could not read operator numbers.") from exc

        numbers = data.get("numbers", [])
        found = False
        for num in numbers:
            if num.get("sid") == phone_sid or num.get("phone_number") == phone_sid:
                num["label"] = clean_label
                found = True
                break
        if not found:
            raise LiveDialerError("Phone number identifier not found.")

        data["updated_at"] = utc_now()
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)
        return self.operator_numbers(email)

    def operator_twilio_settings(self, operator_email: str = "") -> dict[str, Any]:
        """Return the Twilio configuration status for an operator."""
        email = (operator_email or "").strip().lower()
        path = self._twilio_key_path(email)
        is_custom = False
        ac_sid = self.account_sid
        api_sid = self.api_key_sid
        phone = self.caller_number
        sec = self.api_key_secret
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("account_sid") and data.get("api_key_sid"):
                    is_custom = True
                    ac_sid = data.get("account_sid")
                    api_sid = data.get("api_key_sid")
                    if data.get("api_key_secret"):
                        sec = data.get("api_key_secret")
                    if data.get("phone_number"):
                        phone = data.get("phone_number")
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass

        ac_masked = f"{ac_sid[:2]}••••{ac_sid[-4:]}" if len(ac_sid) >= 6 else "Not configured"
        api_masked = f"{api_sid[:2]}••••{api_sid[-4:]}" if len(api_sid) >= 6 else "Not configured"
        phone_fmt = self._format_us_phone(phone) if phone else "Not configured"
        return {
            "configured": bool(ac_sid and api_sid),
            "is_custom": is_custom,
            "account_sid": ac_sid,
            "api_key_sid": api_sid,
            "api_key_secret": sec,
            "account_sid_masked": ac_masked,
            "api_key_sid_masked": api_masked,
            "phone_number": phone,
            "phone_number_formatted": phone_fmt,
        }

    def update_operator_twilio_settings(
        self,
        operator_email: str,
        account_sid: str,
        api_key_sid: str,
        api_key_secret: str,
        phone_number: str = "",
    ) -> dict[str, Any]:
        """Save custom Twilio API credentials for an operator."""
        clean_email = (operator_email or "").strip().lower()
        clean_ac = (account_sid or "").strip()
        clean_api = (api_key_sid or "").strip()
        clean_sec = (api_key_secret or "").strip()
        clean_phone = normalize_phone(phone_number.strip()) if phone_number else ""

        if not clean_ac.startswith("AC") or len(clean_ac) != 34:
            raise LiveDialerError("Twilio Account SID must start with 'AC' and be 34 characters long.")
        if not clean_api.startswith(("SK", "AC")) or len(clean_api) != 34:
            raise LiveDialerError("Twilio API Key SID must be 34 characters long.")
        if len(clean_sec) < 16:
            raise LiveDialerError("Twilio API Key Secret is too short.")

        path = self._twilio_key_path(clean_email)
        if not path:
            raise LiveDialerError("State directory is not configured.")

        payload = {
            "account_sid": clean_ac,
            "api_key_sid": clean_api,
            "api_key_secret": clean_sec,
            "phone_number": clean_phone,
            "updated_at": utc_now(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            json.dump(payload, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)
        return self.operator_twilio_settings(clean_email)

    def delete_operator_twilio_settings(self, operator_email: str) -> dict[str, Any]:
        """Remove custom Twilio credentials, reverting to organization defaults."""
        path = self._twilio_key_path(operator_email)
        if path and path.exists():
            path.unlink(missing_ok=True)
        return self.operator_twilio_settings(operator_email)

    async def buy_operator_number(
        self, operator_email: str, area_code: str = "", label: str = ""
    ) -> dict[str, Any]:
        """Search available clean US local numbers on Twilio, purchase, configure, and add to operator pool."""
        email = (operator_email or "").strip().lower()
        ac_sid, api_sid, api_sec, _ = self._twilio_credentials_for_operator(email)
        if not ac_sid or not api_sid or not api_sec:
            raise LiveDialerError("Twilio credentials are not configured.")

        params = {"PageSize": "5"}
        clean_area = re.sub(r"\D", "", area_code.strip())
        if clean_area and len(clean_area) == 3:
            params["AreaCode"] = clean_area

        query = str(httpx.QueryParams(params))
        payload = await self._twilio_get(
            f"/Accounts/{ac_sid}/AvailablePhoneNumbers/US/Local.json?{query}",
            operator_email=email,
        )
        avail = payload.get("available_phone_numbers") or []
        if not avail:
            if clean_area:
                hint = ""
                if clean_area == "415":
                    hint = " Area code 415 is exhausted on Twilio; try 628 (SF overlay) or 650 (SF Peninsula)."
                elif clean_area == "212":
                    hint = " Area code 212 is exhausted on Twilio; try 646, 332, or 917 for NYC."
                raise LiveDialerError(
                    f"No phone numbers currently available on Twilio for area code {clean_area}.{hint}"
                )
            raise LiveDialerError("No available phone numbers found on Twilio.")

        chosen = avail[0]
        chosen_number = chosen.get("phone_number")
        if not chosen_number:
            raise LiveDialerError("No valid phone number candidate received from Twilio.")

        clean_op = clean_operator_identity(email)
        existing_pool = self.operator_numbers(email)["numbers"]
        assigned_label = (label or "").strip() or f"Number {len(existing_pool) + 1}"
        friendly_name = f"{self.settings.profile.brand} dialer - {clean_op.title()} ({assigned_label})"

        purchase_data = {
            "PhoneNumber": chosen_number,
            "VoiceUrl": self.inbound_voice_url(),
            "VoiceMethod": "POST",
            "FriendlyName": friendly_name,
        }
        purchase_result = await self._twilio_post(
            f"/Accounts/{ac_sid}/IncomingPhoneNumbers.json",
            purchase_data,
            operator_email=email,
        )

        sid = str(purchase_result.get("sid") or "")
        if not sid.startswith("PN"):
            raise LiveDialerError("Twilio failed to purchase incoming phone number.")

        path = self._numbers_path_for_operator(email)
        existing_data = {"operator_email": email, "updated_at": utc_now(), "numbers": []}
        if path.exists():
            try:
                existing_data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass
        numbers_list = existing_data.get("numbers") or []
        if not numbers_list and existing_pool:
            for item in existing_pool:
                raw_sid = str(item.get("sid") or "PN_default")
                if raw_sid == "PN_default" or raw_sid.startswith("num_"):
                    resolved_sid = await self._resolve_twilio_sid_for_number(
                        item["phone_number"], email
                    )
                else:
                    resolved_sid = raw_sid
                numbers_list.append(
                    {
                        "sid": resolved_sid,
                        "phone_number": item["phone_number"],
                        "friendly_name": item.get("friendly_name")
                        or f"{self.settings.profile.brand} line ({item.get('label')})",
                        "label": item.get("label") or f"Number {len(numbers_list) + 1}",
                        "locality": item.get("locality", ""),
                        "region": item.get("region", ""),
                        "configured": bool(item.get("configured", True)),
                        "purchased_at": utc_now(),
                    }
                )

        if not (label or "").strip():
            used_indices = []
            for item in numbers_list:
                lbl = str(item.get("label") or "")
                m = re.match(r"^Number\s+(\d+)$", lbl.strip(), re.IGNORECASE)
                if m:
                    used_indices.append(int(m.group(1)))
            next_idx = max(used_indices) + 1 if used_indices else len(numbers_list) + 1
            assigned_label = f"Number {next_idx}"
        else:
            assigned_label = label.strip()

        new_entry = {
            "sid": sid,
            "phone_number": chosen_number,
            "friendly_name": friendly_name,
            "label": assigned_label,
            "locality": purchase_result.get("locality") or chosen.get("locality") or "",
            "region": purchase_result.get("region") or chosen.get("region") or "",
            "configured": True,
            "purchased_at": utc_now(),
        }
        numbers_list.append(new_entry)
        existing_data["numbers"] = numbers_list
        existing_data["updated_at"] = utc_now()

        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            json.dump(existing_data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)

        return {
            "ok": True,
            "number": {
                "sid": sid,
                "phone_number": chosen_number,
                "formatted": self._format_us_phone(chosen_number),
                "label": assigned_label,
                "locality": new_entry["locality"],
                "region": new_entry["region"],
                "health": self._calculate_number_health(chosen_number),
            },
            "pool": self.operator_numbers(email),
        }

    async def _resolve_twilio_sid_for_number(
        self, phone_number: str, operator_email: str = ""
    ) -> str:
        """Attempt to find the real Twilio IncomingPhoneNumber SID for a known phone number."""
        email = (operator_email or "").strip().lower()
        ac_sid, api_sid, api_sec, _ = self._twilio_credentials_for_operator(email)
        if not ac_sid or not api_sid or not api_sec:
            return "PN_default"
        norm = normalize_phone(phone_number)
        try:
            query = str(httpx.QueryParams({"PhoneNumber": norm, "PageSize": "5"}))
            payload = await self._twilio_get(
                f"/Accounts/{ac_sid}/IncomingPhoneNumbers.json?{query}",
                operator_email=email,
            )
            for item in payload.get("incoming_phone_numbers") or []:
                if isinstance(item, dict) and normalize_phone(item.get("phone_number", "")) == norm:
                    sid = str(item.get("sid") or "")
                    if sid.startswith("PN"):
                        return sid
        except (httpx.HTTPError, LiveDialerError, KeyError, TypeError):
            pass
        return "PN_default"

    async def delete_operator_number(
        self, operator_email: str, phone_sid: str
    ) -> dict[str, Any]:
        """Release/churn a phone number from Twilio and remove it from operator pool."""
        email = (operator_email or "").strip().lower()
        ac_sid, api_sid, _, _ = self._twilio_credentials_for_operator(email)
        path = self._numbers_path_for_operator(email)
        if not path.exists():
            raise LiveDialerError("No phone numbers found for operator.")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise LiveDialerError("Could not read operator numbers.") from exc

        numbers_list = data.get("numbers") or []
        target = None
        target_idx = -1
        for idx, item in enumerate(numbers_list):
            if item.get("sid") == phone_sid or item.get("phone_number") == phone_sid:
                target = item
                target_idx = idx
                break
        if target is None or target_idx < 0:
            raise LiveDialerError("Phone number not found in operator pool.")

        # The main line is the default caller ID, the number the operator's softphone
        # leg comes from, and where callbacks ring. Deleting it (a cooked one, say)
        # first hands the job to the healthiest other number, so there is always one.
        primary_number = normalize_phone(self.caller_number)
        target_number = normalize_phone(target.get("phone_number") or "")
        new_main_line = ""
        if target_number == primary_number:
            successor = self._main_line_successor(numbers_list, primary_number)
            if successor is None:
                raise LiveDialerError(
                    "This is your only number, so it has to stay the main line. Buy another number first."
                )
            await self.set_main_line(email, str(successor.get("sid") or ""))
            new_main_line = normalize_phone(successor.get("phone_number") or "")

        sid = str(target.get("sid") or "")
        if sid.startswith("PN") and ac_sid and api_sid:
            try:
                await self._twilio_delete(
                    f"/Accounts/{ac_sid}/IncomingPhoneNumbers/{sid}.json",
                    operator_email=email,
                )
            except Exception as exc:
                if "404" not in str(exc) and "not found" not in str(exc).lower():
                    raise LiveDialerError(f"Failed to release number on Twilio: {exc}") from exc

        numbers_list.pop(target_idx)
        data["numbers"] = numbers_list
        data["updated_at"] = utc_now()

        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)

        return {
            "ok": True,
            "released_sid": sid,
            "new_main_line": new_main_line,
            "phone_number": target.get("phone_number"),
            "pool": self.operator_numbers(email),
        }

    _HEALTH_ORDER = {"healthy": 0, "fresh": 1, "warning": 2, "cooked": 3}

    def _main_line_successor(
        self, numbers_list: list[dict[str, Any]], main_line: str
    ) -> dict[str, Any] | None:
        candidates = [
            item
            for item in numbers_list
            if normalize_phone(item.get("phone_number") or "") != main_line
            and str(item.get("sid") or "").startswith("PN")
        ]
        return min(
            candidates,
            key=lambda item: self._HEALTH_ORDER.get(
                self._calculate_number_health(item.get("phone_number") or "")["status"], 4
            ),
            default=None,
        )

    async def set_main_line(self, operator_email: str, phone_sid: str) -> dict[str, Any]:
        """Make one of this operator's numbers the main line: the default caller ID, the
        number the softphone leg comes from, and a callback line routed like the old one."""
        email = (operator_email or "").strip().lower()
        pool = self.operator_number_pool(email)
        target = next(
            (item for item in pool if item.get("sid") == phone_sid or item.get("phone_number") == phone_sid),
            None,
        )
        sid = str((target or {}).get("sid") or "")
        number = normalize_phone((target or {}).get("phone_number") or "")
        if not target or not sid.startswith("PN") or not number:
            raise LiveDialerError("That number is not one of yours.")
        if number == self.caller_number:
            return self.operator_numbers(email)
        # Callbacks to the main line go where they always went (Close, else the
        # operator), so its webhook is set before anything is switched.
        await self._twilio_post(
            f"/Accounts/{self.account_sid}/IncomingPhoneNumbers/{sid}.json",
            {"VoiceUrl": self.inbound_voice_url(), "VoiceMethod": "POST"},
        )
        previous = self.caller_number
        self._write_json(
            self.main_line_path,
            {"phone_number": number, "sid": sid, "previous": previous, "set_by": email, "updated_at": utc_now()},
        )
        self.caller_number = number
        with contextlib.suppress(OSError):
            self._write_json(
                self.inbound_meta_path, {"configured": True, "phone_sid": sid, "updated_at": utc_now()}
            )
        logger.info("Main line switched from %s to %s by %s", mask_phone(previous), mask_phone(number), email)
        return self.operator_numbers(email)

    @staticmethod
    def _format_us_phone(number: str) -> str:
        clean = re.sub(r"[^\d+]", "", number)
        if clean.startswith("+1") and len(clean) == 12:
            return f"+1 ({clean[2:5]}) {clean[5:8]}-{clean[8:]}"
        if len(clean) == 10:
            return f"({clean[:3]}) {clean[3:6]}-{clean[6:]}"
        return number

    async def reconcile(self) -> None:
        """Refresh active calls after an API restart without opening any new calls."""
        if not self.configured:
            return
        pending = [
            attempt
            for attempt in self.attempts.values()
            if attempt.twilio_call_sid.startswith("CA")
            and attempt.status not in TERMINAL_CALL_STATUSES
        ]
        for attempt in pending:
            try:
                payload = await self._twilio_get(
                    f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json"
                )
                await self.handle_status(
                    attempt.id,
                    {
                        "CallSid": attempt.twilio_call_sid,
                        "CallStatus": str(payload.get("status") or ""),
                        "CallDuration": str(payload.get("duration") or "0"),
                    },
                )
            except (httpx.HTTPError, LiveDialerError):
                continue
        for session_id in self.sessions:
            self._refresh_session_state(session_id)
        self._persist_state()

    def operator_destination(self, session: DialSession) -> str:
        """Where the operator leg rings: a registered browser, or a phone."""
        if session.operator_target == "browser":
            if not self.browser_calling_available:
                raise LiveDialerError("Twilio cannot reach the browser softphone.")
            return f"client:{self.operator_voice_identity(session.operator_email)}"
        if not self.operator_number:
            raise LiveDialerError("Add the operator number, or take the call in the browser.")
        return self.operator_number

    async def _create_operator_call(self, session: DialSession) -> None:
        form = [
            ("To", self.operator_destination(session)),
            ("From", self.caller_number),
            ("Url", self._session_callback_url("operator-answer", session.id)),
            ("Method", "POST"),
            ("StatusCallback", self._session_callback_url("operator-status", session.id)),
            ("StatusCallbackMethod", "POST"),
            ("StatusCallbackEvent", "initiated"),
            ("StatusCallbackEvent", "ringing"),
            ("StatusCallbackEvent", "answered"),
            ("StatusCallbackEvent", "completed"),
            ("Timeout", "30"),
        ]
        payload = await self._twilio_post(
            f"/Accounts/{self.account_sid}/Calls.json",
            form,
        )
        call_sid = str(payload.get("sid") or "")
        if not call_sid.startswith("CA"):
            raise LiveDialerError("Twilio did not return an operator call identifier.")
        async with self._lock:
            if session.operator_call_sid and not hmac.compare_digest(
                session.operator_call_sid, call_sid
            ):
                raise LiveDialerError("Twilio returned a mismatched operator call identifier.")
            session.operator_call_sid = call_sid
            provider_status = str(payload.get("status") or "queued").lower()
            if session.operator_status not in {"answered", "in-progress"}:
                session.operator_status = provider_status
            session.status = (
                "running"
                if session.operator_status in {"answered", "in-progress"}
                else "operator-connecting"
            )
            session.updated_at = utc_now()
            self._persist_state()

    def _validate_operator_call_sid(self, session: DialSession, call_sid: str) -> bool:
        if not call_sid.startswith("CA"):
            return False
        if session.operator_call_sid and not hmac.compare_digest(
            session.operator_call_sid, call_sid
        ):
            return False
        if not session.operator_call_sid:
            session.operator_call_sid = call_sid
        return True

    async def handle_session_operator_answer(
        self, session_id: str, params: dict[str, str]
    ) -> str:
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        call_sid = str(params.get("CallSid") or "")
        if not self._validate_operator_call_sid(session, call_sid):
            raise LiveDialerError("The operator call identifier did not match this session.")
        session.operator_status = "in-progress"
        session.status = "running"
        session.updated_at = utc_now()
        self._persist_state()
        await self._advance_session(session_id)
        return self._operator_conference_twiml(session)

    async def handle_session_operator_status(
        self, session_id: str, params: dict[str, str]
    ) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        call_sid = str(params.get("CallSid") or "")
        if not self._validate_operator_call_sid(session, call_sid):
            raise LiveDialerError("The operator call identifier did not match this session.")
        sequence_raw = str(params.get("SequenceNumber") or "")
        if sequence_raw:
            try:
                sequence = int(sequence_raw)
            except ValueError:
                sequence = -1
            if sequence >= 0 and sequence < session.operator_sequence_number:
                return
            if sequence >= 0:
                session.operator_sequence_number = sequence
        status = str(params.get("CallStatus") or "").lower()
        if status:
            session.operator_status = status
        session.updated_at = utc_now()
        self._persist_state()
        if status in TERMINAL_CALL_STATUSES and session.status not in {
            "completed",
            "failed",
            "stopped",
            "stopping",
        }:
            await self.stop_session(session_id, operator_ended=True)

    async def _create_call(self, attempt: DialAttempt) -> None:
        form = [
            ("To", attempt.phone),
            ("From", attempt.caller_number or self.caller_number),
            ("Url", self._callback_url("answer", attempt.id)),
            ("Method", "POST"),
            ("StatusCallback", self._callback_url("status", attempt.id)),
            ("StatusCallbackMethod", "POST"),
            ("StatusCallbackEvent", "initiated"),
            ("StatusCallbackEvent", "ringing"),
            ("StatusCallbackEvent", "answered"),
            ("StatusCallbackEvent", "completed"),
            ("MachineDetection", "DetectMessageEnd"),
            ("AsyncAmd", "true"),
            ("AsyncAmdStatusCallback", self._callback_url("amd", attempt.id)),
            ("AsyncAmdStatusCallbackMethod", "POST"),
            ("MachineDetectionSilenceTimeout", "2000"),
            ("MachineDetectionSpeechEndThreshold", "1000"),
            ("MachineDetectionTimeout", "30"),
            ("Timeout", "25"),
            ("Record", "true"),
            ("RecordingStatusCallback", self._callback_url("recording", attempt.id)),
            ("RecordingStatusCallbackMethod", "POST"),
            ("RecordingStatusCallbackEvent", "completed"),
        ]
        payload = await self._twilio_post(
            f"/Accounts/{self.account_sid}/Calls.json",
            form,
        )
        call_sid = str(payload.get("sid") or "")
        if not call_sid.startswith("CA"):
            raise LiveDialerError("Twilio did not return a call identifier.")
        async with self._lock:
            if attempt.twilio_call_sid and not hmac.compare_digest(
                attempt.twilio_call_sid, call_sid
            ):
                raise LiveDialerError("Twilio returned a mismatched call identifier.")
            attempt.twilio_call_sid = call_sid
            provider_status = str(payload.get("status") or "queued").lower()
            # Twilio may deliver the answer/status webhook before its REST create
            # response reaches us. Never regress an already-advanced callback state.
            if attempt.status == "queued":
                attempt.status = provider_status
            if attempt.twilio_status == "queued":
                attempt.twilio_status = provider_status
            attempt.updated_at = utc_now()
            self.call_index[call_sid] = attempt.id
            self._persist_state()
            session = self.sessions.get(attempt.session_id)
            stopped_meanwhile = attempt.status in TERMINAL_CALL_STATUSES or (
                session is not None and session.status in HALTED_SESSION_STATUSES
            )
        if stopped_meanwhile:
            # Stop ran while Twilio was still creating this call, so it had no call id to
            # hang up and the phone rang on with nobody behind it. Hang up now.
            logger.info("Hanging up %s for attempt %s: its session stopped while it was placed", call_sid, attempt.id)
            with contextlib.suppress(httpx.HTTPError, LiveDialerError):
                await self._twilio_post(
                    f"/Accounts/{self.account_sid}/Calls/{call_sid}.json",
                    {"Status": "completed"},
                    timeout=5,
                )

    async def start_session(
        self,
        *,
        smart_view_id: str,
        max_contacts: int,
        concurrency: int,
        screening_reply: str,
        operator_target: str = "browser",
        operator_email: str = "",
        timezone_wave: bool = True,
        safe_hours_only: bool = False,
        list_max_age: float = 1800.0,
        still_wanted: Callable[[], Awaitable[bool]] | None = None,
    ) -> dict[str, Any]:
        if not self.ready:
            raise LiveDialerError("Live dialing is locked: " + " ".join(self.blockers()))
        clean_op = clean_operator_identity(operator_email)
        if any(
            item.status in ACTIVE_SESSION_STATUSES
            and clean_operator_identity(item.operator_email) == clean_op
            for item in self.sessions.values()
        ):
            raise LiveDialerError(
                "Another live session is active for your account. Stop or finish it before starting a new queue."
            )
        if not 1 <= concurrency <= self.max_concurrency:
            raise LiveDialerError(f"Concurrency must be between 1 and {self.max_concurrency}.")
        if not CloseDialer._valid_smart_view_id(smart_view_id):
            raise LiveDialerError("Choose a valid Close Smart View.")
        if not 1 <= max_contacts <= self.max_session_contacts:
            raise LiveDialerError(
                f"The queue limit must be between 1 and {self.max_session_contacts}."
            )
        reply = " ".join(str(screening_reply or "").split())
        if not 15 <= len(reply) <= 240:
            raise LiveDialerError("The approved screening reply must be 15-240 characters.")
        target = str(operator_target or "browser").strip().lower()
        if target not in {"browser", "phone"}:
            raise LiveDialerError("The operator takes the call in the browser or on a phone.")
        if target == "browser" and not self.browser_calling_available:
            raise LiveDialerError("Twilio cannot reach the browser softphone.")
        if target == "phone" and not self.operator_number:
            raise LiveDialerError("Add the operator number, or take the call in the browser.")

        try:
            # The list the page is showing is reused (list_max_age is the page's own
            # bound), so Start dials exactly what is on the operator's screen and starts
            # at once. Re-reading it is up to a minute and a half of throttled Close
            # searches for a big view: long enough that operators reloaded and pressed
            # Start again. In a worker thread, because a read run on the event
            # loop froze every live call's Twilio callbacks with it.
            payload = await asyncio.to_thread(
                self.close_dialer.contacts,
                limit=max_contacts,
                smart_view_id=smart_view_id,
                operator_email=operator_email,
                max_age=list_max_age,
            )
        except DialerError as exc:
            raise LiveDialerError("The Close queue could not be validated.") from exc
        selected_view = payload.get("selected_smart_view")
        if not isinstance(selected_view, dict) or selected_view.get("id") != smart_view_id:
            raise LiveDialerError("The selected Close Smart View could not be validated.")

        all_queue: list[dict[str, Any]] = []
        seen_numbers: set[str] = set()
        for contact in payload.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            phone = normalize_phone(contact.get("phone", ""))
            contact_id = str(contact.get("contact_id") or "")
            lead_id = str(contact.get("lead_id") or "")
            is_disallowed = (
                (not phone or phone in self.blocked_numbers)
                if self.unrestricted
                else (phone not in self.allowed_numbers)
            )
            if (
                is_disallowed
                or contact.get("has_active_deal")
                or contact.get("already_contacted")
                or phone in seen_numbers
                or not contact_id.startswith("cont_")
                or not lead_id.startswith("lead_")
            ):
                if contact.get("already_contacted") or "Previously contacted" in str(contact.get("deal_reason") or ""):
                    logger.info(
                        "Skipping contact %s (%s) from lead %s (%s): previously contacted with call >= 30s",
                        contact_id,
                        contact.get("name"),
                        lead_id,
                        contact.get("lead_name"),
                    )
                continue
            is_valid, reason = validate_phone_number(phone)
            if not is_valid:
                logger.warning(
                    "Skipping contact %s (%s) with invalid phone '%s': %s",
                    contact_id,
                    contact.get("name"),
                    phone,
                    reason,
                )
                continue
            if is_toll_free_number(phone):
                logger.info(
                    "Skipping contact %s (%s) with toll-free phone '%s'",
                    contact_id,
                    contact.get("name"),
                    phone,
                )
                continue
            seen_numbers.add(phone)
            all_queue.append(
                {
                    "contact_id": contact_id,
                    "lead_id": lead_id,
                    "name": str(contact.get("name") or "Close contact"),
                    "lead_name": str(contact.get("lead_name") or "Close CRM"),
                    "phone": phone,
                    "title": str(contact.get("title") or ""),
                    "lead_status": str(contact.get("status") or ""),
                    "close_url": str(contact.get("close_url") or ""),
                    "linkedin_url": str(contact.get("linkedin_url") or ""),
                }
            )
        if not all_queue:
            if self.unrestricted:
                raise LiveDialerError(
                    "The selected Smart View has no callable contacts with valid phone numbers."
                )
            raise LiveDialerError(
                "Nobody in this list is approved for calling yet."
            )
        checkpoint = self._get_checkpoint(operator_email, smart_view_id)
        dial_index = self._dial_index()
        queue = [
            contact
            for contact in all_queue
            if not self._dial_block(str(contact.get("contact_id") or ""), dial_index)[0]
        ]
        if timezone_wave:
            queue = sort_queue_by_timezone_wave(queue, safe_hours_only=safe_hours_only)
        resume_skipped = len(all_queue) - len(queue)
        if not queue:
            if safe_hours_only:
                raise LiveDialerError(
                    "All callable contacts in this Smart View are currently outside safe hours (8:00 AM - 6:00 PM local)."
                )
            raise LiveDialerError(
                "Everyone in this Smart View was dialed in the last 7 days, reached a person, "
                "or has had 4 dials. No-answers come back 7 days after their last dial."
            )

        # A Start the browser gave up on (a reload, a closed tab) must not dial. One once
        # did, 88 s after the operator reloaded: the reloaded page's softphone took the
        # operator leg, and people were put through to a screen that did not know a
        # session was running.
        if still_wanted is not None and not await still_wanted():
            raise LiveDialerError("The start was abandoned before dialing began.")

        session_id = f"ds_{uuid4().hex}"
        session = DialSession(
            id=session_id,
            attempt_ids=[],
            smart_view_id=smart_view_id,
            smart_view_name=str(selected_view.get("name") or "Close Smart View"),
            concurrency=concurrency,
            screening_reply=reply,
            queue=queue,
            operator_target=target,
            source_total=len(all_queue),
            resume_skipped=resume_skipped,
            conference_name=f"dialer-{uuid4().hex[:24]}",
            operator_email=operator_email or "",
        )
        async with self._lock:
            if any(
                item.status in ACTIVE_SESSION_STATUSES
                and clean_operator_identity(item.operator_email) == clean_op
                for item in self.sessions.values()
            ):
                raise LiveDialerError(
                    "Another live session is active for your account. Stop or finish it before starting a new queue."
                )
            self.sessions[session_id] = session
            try:
                self._persist_state()
            except LiveDialerError:
                self.sessions.pop(session_id, None)
                raise
        try:
            await self._create_operator_call(session)
        except (httpx.HTTPError, LiveDialerError) as exc:
            session.status = "failed"
            session.operator_status = "failed"
            session.updated_at = utc_now()
            self._persist_state()
            raise LiveDialerError("Twilio could not connect the operator phone.") from exc
        return self.session(session_id)

    def _select_caller_number(
        self, destination_phone: str, pool: list[dict[str, Any]], default_label: str
    ) -> tuple[str, str]:
        """Select caller ID matching destination area code if available in operator pool."""
        if not pool:
            return (self.caller_number, default_label)
        clean_dest = re.sub(r"\D", "", destination_phone)
        dest_npa = ""
        if len(clean_dest) == 11 and clean_dest.startswith("1"):
            dest_npa = clean_dest[1:4]
        elif len(clean_dest) == 10:
            dest_npa = clean_dest[:3]
        if dest_npa:
            for item in pool:
                p_clean = re.sub(r"\D", "", item.get("phone_number") or "")
                p_npa = p_clean[1:4] if len(p_clean) == 11 and p_clean.startswith("1") else p_clean[:3]
                if p_npa == dest_npa:
                    return (str(item.get("phone_number") or ""), str(item.get("label") or default_label))
        return ("", "")

    def _is_active_dialing_line(self, attempt: DialAttempt) -> bool:
        """Return whether an attempt represents an active outbound line occupying
        the operator's parallel concurrency. Voicemail playback, canceled competitor
        lines, and completed attempts are non-active and do not hold a line slot."""
        if attempt.status in TERMINAL_CALL_STATUSES:
            return False
        if attempt.status in {"voicemail-playing", "canceling"}:
            return False
        if attempt.voicemail_played or attempt.voicemail_detected:
            return False
        if attempt.outcome in {
            "voicemail",
            "ivr",
            "mailbox-full",
            "dropped-line",
            "canceled-after-human",
            "completed",
            "busy",
            "no-answer",
            "failed",
            "canceled",
        }:
            return False
        return True

    def _trigger_advance(self, session_id: str) -> None:
        """Schedule _advance_session on the running event loop if available."""
        if not session_id:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._advance_session(session_id))

    def _callback_must_wait(
        self, session: DialSession, active: list[DialAttempt], contact_id: str
    ) -> bool:
        """Whether a call back has to wait: another line is up, or the call that was
        dropped is still playing its message. A line quiet for CALLBACK_STALE_SECONDS
        is taken as over, because a lost status webhook must not stall the queue."""
        now = datetime.now(UTC)

        def live(attempt: DialAttempt) -> bool:
            try:
                updated = datetime.fromisoformat(attempt.updated_at)
            except ValueError:
                return False
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            return (now - updated).total_seconds() < CALLBACK_STALE_SECONDS

        if any(live(attempt) for attempt in active):
            return True
        return any(
            attempt.contact_id == contact_id
            and attempt.twilio_status not in TERMINAL_CALL_STATUSES
            and live(attempt)
            for attempt in (self.attempts[item] for item in session.attempt_ids if item in self.attempts)
        )

    def _advance_later(self, session_id: str, delay: float = 3.0) -> None:
        """Look again shortly: a call back waiting on a quiet line has no webhook to wake it."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        previous = self._advance_timers.pop(session_id, None)
        if previous is not None:
            previous.cancel()
        self._advance_timers[session_id] = loop.call_later(
            delay, lambda: loop.create_task(self._advance_session(session_id))
        )

    async def _advance_session(self, session_id: str) -> int:
        """Fill open lines from the immutable Smart View snapshot, in order."""
        lock = self._advance_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            started = 0
            while True:
                session = self.sessions.get(session_id)
                if session is None or session.status in {
                    "failed",
                    "stopped",
                    "stopping",
                    "stop-failed",
                }:
                    return started
                if session.operator_status not in {"answered", "in-progress"}:
                    session.status = "operator-connecting"
                    session.updated_at = utc_now()
                    self._persist_state()
                    return started
                if session.human_attempt_id:
                    return started
                active = [
                    self.attempts[item]
                    for item in session.attempt_ids
                    if item in self.attempts
                    and self._is_active_dialing_line(self.attempts[item])
                ]
                capacity = session.concurrency - len(active)
                upcoming = (
                    session.queue[session.next_index]
                    if session.next_index < len(session.queue)
                    else None
                )
                # A call back to someone a busy line dropped goes out on its own, once the
                # first call to them has hung up and no other line is up, so no other
                # pickup can drop them a second time. Other lines wait while it rings.
                if any(item.callback for item in active):
                    capacity = 0
                elif isinstance(upcoming, dict) and upcoming.get("callback"):
                    if self._callback_must_wait(session, active, str(upcoming.get("contact_id") or "")):
                        self._advance_later(session_id)
                        capacity = 0
                    else:
                        capacity = 1
                if capacity <= 0:
                    self._refresh_session_state(session_id)
                    self._persist_state()
                    return started
                if session.next_index >= len(session.queue):
                    self._refresh_session_state(session_id)
                    self._persist_state()
                    if session.status in {"completed", "failed"}:
                        await self._end_operator_call(session)
                    return started

                contacts = session.queue[
                    session.next_index : min(len(session.queue), session.next_index + capacity)
                ]
                attempts: list[DialAttempt] = []
                pool = self.operator_number_pool(session.operator_email)
                for offset, contact in enumerate(contacts, start=session.next_index + 1):
                    default_item = pool[len(attempts) % len(pool)] if pool else None
                    default_num = (
                        default_item.get("phone_number")
                        if default_item and default_item.get("phone_number")
                        else self.caller_number
                    )
                    default_label = (
                        default_item.get("label")
                        if default_item and default_item.get("label")
                        else f"Number {len(attempts) + 1}"
                    )
                    assigned_num, assigned_label = self._select_caller_number(
                        str(contact.get("phone") or ""), pool, default_label
                    )
                    if not assigned_num:
                        assigned_num, assigned_label = default_num, default_label
                    attempt = DialAttempt(
                        id=f"da_{uuid4().hex}",
                        session_id=session_id,
                        contact_id=str(contact.get("contact_id") or ""),
                        lead_id=str(contact.get("lead_id") or ""),
                        name=str(contact.get("name") or "Close contact"),
                        company=str(contact.get("lead_name") or "Close CRM"),
                        phone=normalize_phone(contact.get("phone", "")),
                        screening_reply=session.screening_reply,
                        email=str(contact.get("email") or ""),
                        close_url=str(contact.get("close_url") or ""),
                        linkedin_url=str(contact.get("linkedin_url") or ""),
                        title=str(contact.get("title") or ""),
                        lead_status=str(contact.get("lead_status") or ""),
                        queue_position=offset,
                        caller_number=assigned_num,
                        caller_label=assigned_label,
                        callback=bool(contact.get("callback")),
                    )
                    attempts.append(attempt)
                async with self._lock:
                    # Waiting for the lock can span a Stop, and "running" below would undo it.
                    if session.status in HALTED_SESSION_STATUSES:
                        return started
                    session.next_index += len(attempts)
                    session.attempt_ids.extend(attempt.id for attempt in attempts)
                    self.attempts.update({attempt.id: attempt for attempt in attempts})
                    session.status = "running"
                    session.updated_at = utc_now()
                    self._persist_state()

                results = await asyncio.gather(
                    *(self._create_call(attempt) for attempt in attempts),
                    return_exceptions=True,
                )
                fatal_error = False
                for attempt, result in zip(attempts, results, strict=True):
                    if isinstance(result, Exception):
                        attempt.status = "failed"
                        attempt.twilio_status = "failed"
                        code = getattr(result, "code", "")
                        detail = getattr(result, "detail", "")
                        status_code = getattr(result, "status_code", 0)
                        if code:
                            attempt.error_code = str(code)
                        if detail:
                            attempt.error_message = str(detail)
                        if status_code in (401, 403) or code in ("20003",):
                            fatal_error = True
                        attempt.outcome = "provider-error"
                        attempt.updated_at = utc_now()
                        logger.error("Failed to create call for attempt %s (%s): %s", attempt.id, attempt.phone, result)
                        self._record_attempt_outcome(session, attempt)
                        with contextlib.suppress(Exception):
                            asyncio.create_task(self._log_close_once(attempt))
                    else:
                        started += 1
                if started == 0 and attempts:
                    has_more_queue = session.next_index < len(session.queue)
                    if fatal_error or not has_more_queue:
                        logger.error(
                            "Provider rejected all %d call creation requests in batch. Halting session %s (fatal=%s, remaining=%d).",
                            len(attempts),
                            session_id,
                            fatal_error,
                            len(session.queue) - session.next_index,
                        )
                        session.status = "failed"
                        session.updated_at = utc_now()
                        await self._end_operator_call(session)
                        self._refresh_session_state(session_id)
                        self._persist_state()
                        return started
                    else:
                        logger.warning(
                            "Batch of %d calls rejected by provider, but %d contacts remain in queue. Continuing session %s.",
                            len(attempts),
                            len(session.queue) - session.next_index,
                            session_id,
                        )
                        self._refresh_session_state(session_id)
                        self._persist_state()
                        self._trigger_advance(session.id)
                        return started
                self._refresh_session_state(session_id)
                self._persist_state()

    def session(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        original_status = session.status
        self._refresh_session_state(session_id)
        attempts = [self.attempts[item] for item in session.attempt_ids if item in self.attempts]
        active_attempt = self.attempts.get(session.human_attempt_id)
        if session.status != original_status:
            self._persist_state()

        total_attempts = len(attempts)
        human_answered = len(
            [a for a in attempts if a.outcome == "human-bridged" or a.status == "bridged"]
        )
        human_missed = len(
            [
                a
                for a in attempts
                # A machine that was taking our voicemail is not a person we failed to
                # answer; counting three of them once put a session at 57%.
                if not a.voicemail_played
                and (
                    getattr(a, "abandoned", False)
                    or (
                        (
                            a.human_detected
                            or a.outcome in {"abandoned", "operator-unavailable", "operator-no-answer", "operator-busy", "operator-failed"}
                        )
                        and a.outcome != "human-bridged"
                        and a.status != "bridged"
                    )
                )
            ]
        )
        total_human = human_answered + human_missed
        abandonment_rate = round((human_missed / total_human) * 100, 1) if total_human > 0 else 0.0
        connect_rate = round((human_answered / total_attempts) * 100, 1) if total_attempts > 0 else 0.0

        return {
            "id": session.id,
            "status": session.status,
            "mode": "power" if session.concurrency == 1 else "parallel",
            "concurrency": session.concurrency,
            "operator": {
                "status": session.operator_status or "queued",
                "ready": session.operator_status in {"answered", "in-progress"},
                "email": session.operator_email,
            },
            "operator_email": session.operator_email,
            "active_contact": active_attempt.public() if active_attempt else None,
            "smart_view": {
                "id": session.smart_view_id,
                "name": session.smart_view_name,
            },
            "queue_total": session.source_total or len(session.queue),
            "queue_started": session.resume_skipped + session.next_index,
            "queue_remaining": max(0, len(session.queue) - session.next_index),
            "resumed_from": session.resume_skipped,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "stats": {
                "attempts": total_attempts,
                "human_connects": total_human,
                "human_answered": human_answered,
                "human_missed": human_missed,
                "abandonment_rate": abandonment_rate,
                "connect_rate": connect_rate,
            },
            "attempts": [attempt.public() for attempt in attempts],
        }

    async def _end_call(self, attempt: DialAttempt, outcome: str) -> bool:
        lock = self._end_locks.setdefault(attempt.id, asyncio.Lock())
        async with lock:
            return await self._end_call_locked(attempt, outcome)

    async def _end_call_locked(self, attempt: DialAttempt, outcome: str) -> bool:
        if attempt.status in TERMINAL_CALL_STATUSES:
            return True
        if attempt.twilio_call_sid and attempt.twilio_status not in TERMINAL_CALL_STATUSES:
            try:
                await self._twilio_post(
                    f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                    {"Status": "completed"},
                    timeout=5,
                )
            except (httpx.HTTPError, LiveDialerError):
                logger.warning(
                    "Twilio call %s for attempt %s could not be ended via API (likely already completed)",
                    attempt.twilio_call_sid,
                    attempt.id,
                )
        attempt.status = "completed"
        attempt.outcome = outcome or attempt.outcome or "completed"
        attempt.updated_at = utc_now()
        session = self.sessions.get(attempt.session_id)
        if session is not None:
            self._record_attempt_outcome(session, attempt)
        self._persist_state()
        self._trigger_advance(attempt.session_id)
        return True

    async def _end_operator_call(self, session: DialSession) -> bool:
        if not session.operator_call_sid or session.operator_status in TERMINAL_CALL_STATUSES:
            return True
        try:
            await self._twilio_post(
                f"/Accounts/{self.account_sid}/Calls/{session.operator_call_sid}.json",
                {"Status": "completed"},
                timeout=5,
            )
        except (httpx.HTTPError, LiveDialerError):
            return False
        session.operator_status = "completed"
        session.updated_at = utc_now()
        self._persist_state()
        return True

    async def stop_session(
        self, session_id: str, *, operator_ended: bool = False
    ) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        if session.status == "stopped":
            return self.session(session_id)
        session.status = "stopping"
        session.updated_at = utc_now()
        self._persist_state()
        timer = self._advance_timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()
        attempts = [self.attempts[item] for item in session.attempt_ids if item in self.attempts]
        results = await asyncio.gather(
            *(
                self._end_call(attempt, "canceled")
                for attempt in attempts
                if attempt.status not in TERMINAL_CALL_STATUSES
            )
        )
        operator_stopped = True if operator_ended else await self._end_operator_call(session)
        if operator_ended:
            session.operator_status = session.operator_status or "completed"
        session.human_attempt_id = ""
        session.status = "stopped" if all(results) and operator_stopped else "stop-failed"
        session.updated_at = utc_now()
        if session.conference_name:
            with contextlib.suppress(RuntimeError):
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._stop_conference_recordings(
                        session.conference_name,
                        operator_email=session.operator_email,
                    )
                )
        self._persist_state()
        return self.session(session_id)

    async def complete_active_call(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        if session.status in {"completed", "failed", "stopped"}:
            return self.session(session_id)

        attempt = self.attempts.get(session.human_attempt_id)
        if attempt is not None and attempt.status not in TERMINAL_CALL_STATUSES:
            await self._end_call(attempt, "human-bridged")

        session.human_attempt_id = ""
        if session.status not in {"stopping", "stopped", "failed", "completed"}:
            session.status = "running"
        session.updated_at = utc_now()
        if attempt is not None:
            await self._log_close_once(attempt)
        self._persist_state()
        await self._advance_session(session_id)
        return self.session(session_id)

    async def disqualify_active_call(
        self, session_id: str, disposition: str = "Not Interested"
    ) -> dict[str, Any]:
        """Hang up the active bridged contact call, update the lead status in Close CRM to the disposition,
        log the call outcome, and advance to the next contact in queue."""
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        if session.status in {"completed", "failed", "stopped"}:
            return self.session(session_id)

        clean_disp = str(disposition or "Not Interested").strip() or "Not Interested"
        attempt = self.attempts.get(session.human_attempt_id)
        if attempt is not None and attempt.status not in TERMINAL_CALL_STATUSES:
            attempt.disposition = clean_disp
            attempt.operator_disqualified = True
            await self._end_call(attempt, "not-interested")

        session.human_attempt_id = ""
        if session.status not in {"stopping", "stopped", "failed", "completed"}:
            session.status = "running"
        session.updated_at = utc_now()
        if attempt is not None:
            op_email = session.operator_email if session else ""
            if attempt.lead_id:
                try:
                    await asyncio.to_thread(
                        self.close_dialer.update_lead_status,
                        attempt.lead_id,
                        clean_disp,
                        operator_email=op_email,
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not update lead %s status to '%s' in Close: %s",
                        attempt.lead_id,
                        clean_disp,
                        exc,
                    )
            await self._log_close_once(attempt)
        self._persist_state()
        await self._advance_session(session_id)
        return self.session(session_id)

    async def drop_active_voicemail(self, session_id: str) -> dict[str, Any]:
        """Redirect the active bridged contact call to play the voicemail message in background,
        or hang up cleanly if no voicemail recording is configured, flagging as voicemail."""
        session = self.sessions.get(session_id)
        if session is None:
            raise LiveDialerError("Dialer session not found.")
        if session.status in {"completed", "failed", "stopped"}:
            return self.session(session_id)

        attempt = self.attempts.get(session.human_attempt_id)
        if attempt is None or not attempt.twilio_call_sid:
            raise LiveDialerError("No active call connected to drop voicemail on.")

        op_email = session.operator_email or ""
        has_recording = bool(self.recording_metadata("voicemail", operator_email=op_email).get("configured"))

        if has_recording:
            # Redirect the contact leg to play the voicemail recording in the background
            twiml = self._voicemail_drop_twiml(operator_email=op_email, pause_seconds=1)
            try:
                await self._twilio_post(
                    f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                    {"Twiml": twiml},
                    timeout=5,
                )
            except (httpx.HTTPError, LiveDialerError) as exc:
                logger.warning("Could not redirect call %s to voicemail drop: %s", attempt.twilio_call_sid, exc)
            attempt.voicemail_played = True
            attempt.status = "voicemail-playing"
        else:
            # Cleanly end the contact leg if no voicemail recording was configured
            await self._end_call(attempt, "voicemail")
            attempt.voicemail_played = False
            attempt.status = "completed"

        attempt.voicemail_detected = True
        attempt.operator_flagged_voicemail = True
        attempt.outcome = "voicemail"
        attempt.updated_at = utc_now()

        # Record operator feedback for dataset collection & AI detection accuracy improvements
        self._record_voicemail_feedback(
            attempt,
            session_id=session_id,
            operator_email=op_email,
            has_recording=has_recording,
        )

        # Release the operator leg from the bridged state so they can take the next human call
        session.human_attempt_id = ""
        if session.status not in {"stopping", "stopped", "failed", "completed"}:
            session.status = "running"
        session.updated_at = utc_now()

        if session.conference_name:
            with contextlib.suppress(RuntimeError):
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._stop_conference_recordings(
                        session.conference_name,
                        operator_email=op_email,
                    )
                )

        await self._log_close_once(attempt)
        self._persist_state()
        await self._advance_session(session_id)
        return self.session(session_id)

    def _record_voicemail_feedback(
        self,
        attempt: DialAttempt,
        *,
        session_id: str,
        operator_email: str,
        has_recording: bool,
    ) -> None:
        try:
            feedback_entry = {
                "timestamp": utc_now(),
                "attempt_id": attempt.id,
                "session_id": session_id,
                "twilio_call_sid": attempt.twilio_call_sid,
                "contact_id": attempt.contact_id,
                "lead_id": attempt.lead_id,
                "name": attempt.name,
                "company": attempt.company,
                "phone": attempt.phone,
                "operator_email": operator_email,
                "detected_kind": "human",
                "operator_flag": "voicemail",
                "voicemail_dropped": has_recording,
                "transcript": attempt.transcript,
                "speech_responses": attempt.speech_responses,
                "recording_url": attempt.recording_url,
            }
            log_dir = (
                self.settings.state_dir
                if self.settings and getattr(self.settings, "state_dir", None)
                else Path(".")
            )
            feedback_file = log_dir / "voicemail_feedback.jsonl"
            with open(feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(feedback_entry) + "\n")
            logger.info(
                "Operator %s flagged attempt %s as voicemail (contact: %s, call_sid: %s)",
                operator_email,
                attempt.id,
                attempt.name,
                attempt.twilio_call_sid,
            )
        except Exception as exc:
            logger.warning("Failed to record voicemail feedback entry: %s", exc)

    def attempt(self, attempt_id: str) -> DialAttempt:
        attempt = self.attempts.get(attempt_id)
        if attempt is None:
            raise LiveDialerError("Dial attempt not found.")
        return attempt

    def _validate_call_sid(self, attempt: DialAttempt, call_sid: str) -> bool:
        if not call_sid.startswith("CA"):
            return False
        if attempt.twilio_call_sid and not hmac.compare_digest(attempt.twilio_call_sid, call_sid):
            return False
        if not attempt.twilio_call_sid:
            attempt.twilio_call_sid = call_sid
            self.call_index[call_sid] = attempt.id
        return True

    async def handle_status(self, attempt_id: str, params: dict[str, str]) -> None:
        attempt = self.attempt(attempt_id)
        call_sid = str(params.get("CallSid") or "")
        if not self._validate_call_sid(attempt, call_sid):
            raise LiveDialerError("The Twilio call identifier did not match this attempt.")
        sequence_raw = str(params.get("SequenceNumber") or "")
        if sequence_raw:
            try:
                sequence = int(sequence_raw)
            except ValueError:
                sequence = -1
            if sequence >= 0 and sequence < attempt.sequence_number:
                return
            if sequence >= 0:
                attempt.sequence_number = sequence
        status = str(params.get("CallStatus") or "").lower()
        if status:
            attempt.twilio_status = status
            if status in TERMINAL_CALL_STATUSES or attempt.status in {
                "queued",
                "initiated",
                "ringing",
                "in-progress",
                "canceling",
            }:
                attempt.status = status
        duration = safe_int(params.get("CallDuration"), 0)
        if duration > 0:
            attempt.duration = duration
            if attempt.outcome == "human-bridged" or attempt.status == "bridged":
                attempt.bridge_duration = max(attempt.bridge_duration, duration)

        error_code = str(params.get("ErrorCode") or "").strip()
        error_msg = str(params.get("ErrorMessage") or "").strip()
        sip_code = str(params.get("SipResponseCode") or "").strip()
        if error_code:
            attempt.error_code = error_code
        if error_msg:
            attempt.error_message = error_msg
        if sip_code:
            attempt.sip_response_code = sip_code

        if status in {"busy", "no-answer", "failed", "canceled"} and not attempt.outcome:
            if status == "failed":
                if (
                    error_code == "13224"
                    or sip_code == "404"
                    or error_code in {"21211", "21214", "21217", "21614"}
                ):
                    attempt.outcome = "invalid"
                elif sip_code in {"486", "600"}:
                    attempt.outcome = "busy"
                else:
                    attempt.outcome = "failed"
            else:
                attempt.outcome = status
        elif status == "completed" and not attempt.outcome:
            attempt.outcome = "completed"
        attempt.updated_at = utc_now()
        session = self.sessions.get(attempt.session_id)
        if (
            status in TERMINAL_CALL_STATUSES
            and session is not None
            and session.human_attempt_id == attempt.id
        ):
            session.human_attempt_id = ""
            if session.status not in {"stopping", "stopped", "failed"}:
                session.status = "running"
            session.updated_at = utc_now()
        self._refresh_session_state(attempt.session_id)
        self._persist_state()
        if status in TERMINAL_CALL_STATUSES:
            if session is not None:
                self._record_attempt_outcome(session, attempt)
            await self._log_close_once(attempt)
            self._persist_state()
            await self._advance_session(attempt.session_id)

    async def handle_recording_status(
        self, attempt_id: str, params: dict[str, str], is_conference: bool = False
    ) -> None:
        attempt = self.attempt(attempt_id)
        recording_sid = str(params.get("RecordingSid") or "").strip()
        if not re.match(r"^RE[0-9a-fA-F]{32}$", recording_sid):
            raise LiveDialerError("Invalid recording identifier.")
        rec_status = str(params.get("RecordingStatus") or "").lower()
        if rec_status and rec_status != "completed":
            return

        # If a conference recording is already recorded, do not let single-leg overwrite it
        if not is_conference and attempt.recording_sid and attempt.recording_sid != recording_sid:
            return

        rec_duration = safe_int(params.get("RecordingDuration"), 0)
        attempt.recording_sid = recording_sid
        attempt.recording_url = f"{self.public_base_url}/call-recording/{recording_sid}.mp3"
        if rec_duration > 0:
            if is_conference and attempt.bridge_duration > 0 and (rec_duration - attempt.bridge_duration > 15):
                # An inflated conference recording from operator wait time or multi-call bleed
                # must not overwrite the real call duration.
                attempt.duration = attempt.bridge_duration
            else:
                attempt.duration = max(attempt.duration, rec_duration)
                if attempt.outcome == "human-bridged" or attempt.status == "bridged":
                    attempt.bridge_duration = max(attempt.bridge_duration, attempt.duration)
        attempt.updated_at = utc_now()
        self._persist_state()

        if attempt.close_call_id:
            session = self.sessions.get(attempt.session_id)
            op_email = session.operator_email if session else ""
            try:
                await asyncio.to_thread(
                    self.close_dialer.update_call_recording,
                    attempt.close_call_id,
                    recording_url=attempt.recording_url,
                    duration=attempt.duration,
                    operator_email=op_email,
                )
            except DialerError:
                pass

    async def handle_amd(self, attempt_id: str, params: dict[str, str]) -> None:
        attempt = self.attempt(attempt_id)
        call_sid = str(params.get("CallSid") or "")
        if not self._validate_call_sid(attempt, call_sid):
            raise LiveDialerError("The Twilio call identifier did not match this attempt.")
        attempt.answered_by = str(params.get("AnsweredBy") or "").lower()
        attempt.updated_at = utc_now()
        self._persist_state()
        if attempt.answered_by in MACHINE_RESULTS and attempt.outcome == "dropped-line":
            attempt.outcome = "voicemail"
            attempt.abandoned = False
            attempt.voicemail_detected = True
            self._unprioritize_dropped_contact(attempt.session_id, attempt.contact_id)
            self._refresh_session_state(attempt.session_id)
            self._persist_state()
            logger.info("Attempt %s was dropped-line but late AMD confirmed %s: corrected to voicemail", attempt.id, attempt.answered_by)
            return
        if attempt.status in TERMINAL_CALL_STATUSES:
            return
        if attempt.answered_by == "human":
            logger.info("Attempt %s Twilio AMD reported human; awaiting speech verification before bridging", attempt.id)
            return
        if attempt.answered_by == "fax":
            await self._end_call(attempt, "fax")
            return
        if attempt.answered_by not in MACHINE_RESULTS:
            return
        if attempt.human_detected:
            return
        if (
            attempt.screening_detected
            or attempt.outcome in {"screening", "screening-passed", "human-bridged", "human"}
        ):
            logger.info("Attempt %s already in screening or bridged (%s), ignoring machine AMD callback", attempt.id, attempt.outcome)
            return
        if attempt.voicemail_played:
            logger.info("Attempt %s already played voicemail, ignoring AMD callback", attempt.id)
            return
        if attempt.answered_by == "machine_start":
            attempt.voicemail_detected = True
            logger.info("Attempt %s machine_start detected, waiting for message end or speech", attempt.id)
            return
        attempt.voicemail_detected = True
        attempt.voicemail_played = True
        attempt.status = "voicemail-playing"
        attempt.outcome = "voicemail"
        attempt.updated_at = utc_now()
        self._refresh_session_state(attempt.session_id)
        self._persist_state()
        self._trigger_advance(attempt.session_id)
        session = self.sessions.get(attempt.session_id)
        op_email = session.operator_email if session else ""
        try:
            await self._twilio_post(
                f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                {"Twiml": self._voicemail_drop_twiml(operator_email=op_email, pause_seconds=1)},
                timeout=5,
            )
        except (httpx.HTTPError, LiveDialerError):
            await self._end_call(attempt, "voicemail-playback-failed")

    async def _classify_transcript(self, attempt: DialAttempt, transcript: str) -> tuple[str, str]:
        normalized = " ".join(transcript.lower().split())
        voicemail_terms = (
            "after the tone",
            "at the tone",
            "after the beep",
            "at the beep",
            "call back later",
            "call has been forwarded",
            "cannot take your call",
            "can't take your call",
            "currently unavailable",
            "forwarded to",
            "leave a message",
            "leave me a message",
            "leave your message",
            "leave your name",
            "mailbox",
            "no longer in service",
            "not available",
            "not taking calls",
            "number you have dialed",
            "number you have dialled",
            "out of service",
            "party you are trying to reach",
            "person you are trying to reach",
            "person you have called",
            "please call back",
            "please leave a message",
            "record the message",
            "record your message",
            "subscriber is not available",
            "temporarily unavailable",
            "try again later",
            "try calling again",
            "try your call again",
            "unable to take your call",
            "unable to take the call",
            "unavailable",
            "voice mail",
            "voice message",
            "voicemail",
            "you have reached",
            "you've reached",
            "you have reached the",
            "you've reached the",
            "reached the voice",
            "voice mailbox",
            "record a message",
            "leave a detailed message",
            "leave a brief message",
            "leave your name and number",
            "at the sound of the beep",
            "at the sound of the tone",
            "when you have finished recording",
            "when you finish recording",
            "press pound to end",
            "press pound when finished",
            "is not in service",
            "wireless customer",
            "please text me",
            "text me",
            "text me at",
            "get back to you",
            "i'll get back to you",
            "will get back to you",
            "as soon as i can",
            "as quick as i can",
            "as soon as possible",
            "reach me by text",
            "leave your number",
            "at your earliest convenience",
        )
        transfer_terms = (
            "please wait while",
            "wait while",
            "wait while we",
            "wait while i",
            "please wait",
            "please hold",
            "hold on while",
            "hold on please",
            "one moment please",
            "just a moment",
            "transferring your call",
            "transferring you to",
            "transfer you to",
            "call is being transferred",
            "call is being forwarded",
            "call will be forwarded",
            "call has been forwarded",
            "forwarding your call",
            "forwarding to",
            "connecting your call",
            "connecting you to",
        )
        screening_terms = (
            "may i ask who is calling",
            "please state your name",
            "reason for the call",
            "reason for your call",
            "record your name",
            "record your name and reason",
            "see if this person is available",
            "what is this regarding",
            "who is calling",
            "who is this calling",
            "who may i say is calling",
            "who's calling",
            "why are you calling",
        )
        human_words = {"hello", "hey", "hi", "yeah", "yes", "speaking"}
        human_phrases = (
            "this is",
            "who is this",
            "who's this",
            "how can i help",
            "how can i help you",
            "can i help you",
            "can i help",
            "good morning",
            "good afternoon",
            "good evening",
            "how are you",
            "how are you doing",
            "what can i do",
            "what can i do for you",
            "this is he",
            "this is she",
            "go ahead",
        )
        ivr_terms = (
            "press 0",
            "press zero",
            "press 1",
            "press one",
            "press 2",
            "press two",
            "press 3",
            "press three",
            "press 4",
            "press four",
            "press 5",
            "press five",
            "press 8",
            "press 9",
            "press nine",
            "press pound",
            "press star",
            "for sales",
            "for billing",
            "for customer service",
            "for support",
            "for accounting",
            "enter your party",
            "enter an extension",
            "dial an extension",
            "enter the extension",
            "main menu",
            "phone menu",
            "automated menu",
            "to speak with",
            "to speak to",
            "if you know your party",
            "for all other inquiries",
            "transfer you to",
            "please listen",
            "listen closely",
            "listen to the following",
            "following options",
            "menu options",
            "options have changed",
            "choose from the following",
            "please choose",
            "to make a new",
            "to learn more",
            "for learning more",
            "for current employees",
            "employment opportunities",
            "if you receive services",
            "all other calls",
            "cannot be transferred",
            "if you are looking for",
            "if you are a current",
            "current client",
            "current caregiver",
            "thank you for calling",
            "thanks for calling",
            "welcome to",
            "our office hours",
            "office hours are",
            "director call",
            "automated system",
            "automated attendant",
            "automated service",
            "virtual assistant",
            "virtual receptionist",
            "para espanol",
            "para español",
            "oprima",
            "o prima",
            "call may be monitored",
            "call may be recorded",
            "recorded for quality",
            "monitored or recorded",
            "recorded for training",
            "quality assurance",
            "if this is an emergency",
            "if you have an emergency",
            "hang up and call 911",
            "call 911 immediately",
        )
        mailbox_full_terms = (
            "mailbox is full",
            "mailbox full",
            "box is full",
            "cannot accept messages",
            "cannot accept more messages",
            "not accepting messages",
            "not accepting new messages",
            "memory is full",
            "inbox is full",
            "reached its limit",
            "has reached its maximum",
            "cannot receive messages",
            "mailbox has reached",
            "voicemail is full",
        )
        if any(term in normalized for term in ivr_terms):
            return "ivr", ""
        if any(term in normalized for term in mailbox_full_terms):
            return "mailbox-full", ""
        if any(term in normalized for term in voicemail_terms):
            return "voicemail", ""
        if any(term in normalized for term in transfer_terms):
            return "transfer", ""
        if any(term in normalized for term in screening_terms):
            return "screening", attempt.screening_reply
        words = set(re.findall(r"\b[a-z0-9']+\b", normalized))
        corporate_automated_markers = (
            "thank you for calling",
            "thanks for calling",
            "welcome to",
            "office hours",
            "call may be",
            "recorded for",
            "monitored for",
            "please listen",
            "press",
            "options",
            "emergency",
            "director call",
        )
        has_automated_marker = any(m in normalized for m in corporate_automated_markers)
        if (
            not has_automated_marker
            and (words & human_words or any(phrase in normalized for phrase in human_phrases))
            and len(normalized) <= 120
        ):
            return "human", ""
        if not normalized:
            return "unknown", ""

        if self.openrouter_api_key:
            or_result = await self._classify_with_openrouter(attempt, transcript)
            if or_result is not None:
                return or_result

        if self.typesafe_api_key:
            ts_result = await self._classify_with_typesafe_jev(attempt, transcript)
            if ts_result is not None:
                return ts_result
        elif self.cloudflare_account_id and self.cloudflare_api_token:
            cf_result = await self._classify_with_cloudflare_jev(attempt, transcript)
            if cf_result is not None:
                return cf_result
        return await self._classify_with_openai(attempt, transcript)

    async def _classify_with_openrouter(
        self, attempt: DialAttempt, transcript: str
    ) -> tuple[str, str] | None:
        if not self.openrouter_api_key:
            return None
        payload = {
            "model": self.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a real-time call classifier for an automated phone dialer. "
                        "Classify what was said into EXACTLY one category:\n"
                        "- \"human\": A live person answered conversationally (e.g. \"Hello?\", \"Good morning, Jane speaking\", \"Who's this?\").\n"
                        "- \"voicemail\": An answering machine, personal voicemail (e.g. \"Please text me\"), or beep prompt.\n"
                        "- \"ivr\": An automated phone tree, IVR menu, auto-attendant (e.g. \"Thank you for calling [Company]\", \"If you are looking for services press 1\"), or recording disclosure.\n"
                        "- \"screening\": An automated call screening assistant (e.g. \"Please record your name and reason for calling\").\n"
                        "- \"mailbox-full\": Mailbox is full and cannot accept messages.\n\n"
                        "Respond with JSON ONLY:\n"
                        "{\"kind\": \"human\" | \"voicemail\" | \"ivr\" | \"screening\" | \"mailbox-full\", \"reason\": \"<brief explanation>\"}"
                    ),
                },
                {"role": "user", "content": f"Opening call speech transcript: {transcript[:1000]!r}"},
            ],
            "temperature": 0.0,
            "max_tokens": 40,
        }
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.public_base_url,
            "X-Title": f"{self.settings.profile.brand} dialer",
        }
        client_cls = httpx.AsyncClient
        kwargs = {}
        if self.transport:
            kwargs["transport"] = self.transport
        try:
            async with client_cls(**kwargs) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=3.0,
                )
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        kind = str(parsed.get("kind", "")).lower().strip()
                        if kind in {"human", "voicemail", "ivr", "screening", "mailbox-full"}:
                            reply = attempt.screening_reply if kind == "screening" else ""
                            return kind, reply
                    content_lower = content.lower()
                    for k in ["human", "voicemail", "ivr", "screening", "mailbox-full"]:
                        if f'"{k}"' in content_lower or f"'{k}'" in content_lower:
                            reply = attempt.screening_reply if k == "screening" else ""
                            return k, reply
        except Exception as exc:
            logger.warning("OpenRouter classification failed (%s), falling back", exc)
        return None

    async def _classify_with_typesafe_jev(
        self, attempt: DialAttempt, transcript: str
    ) -> tuple[str, str] | None:
        if not self.typesafe_api_key:
            return None
        url = self.typesafe_system_one_url
        payload = {
            "model": self.typesafe_model,
            "state": transcript[:1000],
            "questions": {
                "kind": {
                    "type": "choice",
                    "instructions": (
                        "Classify outbound call speaker: "
                        "human, voicemail, screening, ivr, mailbox-full, transfer, or unknown."
                    ),
                    "criteria": {
                        "human": "Live person answering conversationally (e.g. Hello?, Speaking, Who is this?). Not automated company greetings.",
                        "voicemail": "Answering machine, personal voicemail (e.g. Please text me), or beep prompt",
                        "screening": "Google Call Screen or assistant asking to state name",
                        "ivr": "Automated IVR phone tree menu, automated company greeting (e.g. Thank you for calling), or recording disclosure",
                        "mailbox-full": "Mailbox memory full",
                        "transfer": "Hold music or transfer announcement",
                        "unknown": "Ambiguous or unclassifiable audio",
                    },
                }
            },
        }
        try:
            async with httpx.AsyncClient(timeout=1.5, transport=self.transport) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.typesafe_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            data = result.get("result", result)
            answers = data.get("answers") or {}
            kind_data = answers.get("kind") or {}
            choice = str(kind_data.get("choice") or "").strip().lower().replace("_", "-")
            if choice in {"screening", "human", "voicemail", "ivr", "mailbox-full", "transfer", "unknown"}:
                reply = attempt.screening_reply if choice == "screening" else ""
                return choice, reply
            return None
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("TypeSafe Jev classification failed (%s), falling back to OpenAI", exc)
            return None

    async def _classify_with_cloudflare_jev(
        self, attempt: DialAttempt, transcript: str
    ) -> tuple[str, str] | None:
        if not (self.cloudflare_account_id and self.cloudflare_api_token):
            return None
        url = self.cloudflare_ai_run_url.format(account_id=self.cloudflare_account_id)
        payload = {
            "model": self.cloudflare_ai_model,
            "input": {
                "state": transcript[:1000],
                "questions": {
                    "kind": {
                        "type": "choice",
                        "instructions": (
                            "Classify outbound call speaker: "
                            "human, voicemail, screening, ivr, mailbox-full, transfer, or unknown."
                        ),
                        "criteria": {
                            "human": "Live person answering conversationally (e.g. Hello?, Speaking, Who is this?). Not automated company greetings.",
                            "voicemail": "Answering machine, personal voicemail (e.g. Please text me), or beep prompt",
                            "screening": "Google Call Screen or assistant asking to state name",
                            "ivr": "Automated IVR phone tree menu, automated company greeting (e.g. Thank you for calling), or recording disclosure",
                            "mailbox-full": "Mailbox memory full",
                            "transfer": "Hold music or transfer announcement",
                            "unknown": "Ambiguous or unclassifiable audio",
                        },
                    }
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=1.5, transport=self.transport) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.cloudflare_api_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            data = result.get("result", result)
            answers = data.get("answers") or {}
            kind_data = answers.get("kind") or {}
            choice = str(kind_data.get("choice") or "").strip().lower().replace("_", "-")
            if choice in {"screening", "human", "voicemail", "ivr", "mailbox-full", "transfer", "unknown"}:
                reply = attempt.screening_reply if choice == "screening" else ""
                return choice, reply
            return None
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Cloudflare Jev classification failed (%s), falling back to OpenAI", exc)
            return None

    async def _classify_with_openai(
        self, attempt: DialAttempt, transcript: str
    ) -> tuple[str, str]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["human", "voicemail", "screening", "ivr", "mailbox-full", "transfer", "unknown"],
                },
            },
            "required": ["kind"],
        }
        payload = {
            "model": self.settings.llm_model,
            "instructions": (
                "You are an expert audio classifier for an outbound sales dialer. "
                "Classify the speaker from the opening transcript of an answered phone call into one of:\n"
                "- 'ivr': Automated phone tree, interactive voice response menu, automated company greeting (e.g. 'Thank you for calling [Company]', 'Welcome to...'), call recording disclosure ('this call may be recorded/monitored'), office hours announcements, or press-number prompts.\n"
                "- 'voicemail': Answering machine, personal voicemail greeting (e.g. 'Please text me or leave a message', 'I am unable to take your call'), or tone/beep prompts.\n"
                "- 'screening': Google Call Screen or automated assistant asking who is calling or reason for call.\n"
                "- 'transfer': Hold music or automated transfer announcement asking to hold or wait while transferring.\n"
                "- 'mailbox-full': Announcement that mailbox memory is full.\n"
                "- 'human': A real live person answering conversationally (e.g. 'Hello?', 'Speaking', 'Good morning, how can I help you?'). IMPORTANT: If the speech is an automated company greeting or announcement, it is IVR, NOT human.\n"
                "- 'unknown': Completely empty or unintelligible noise."
            ),
            "input": transcript[:1000],
            "max_output_tokens": 64,
            "store": False,
            "reasoning": {"effort": "minimal"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "dialer_classification",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        try:
            async with httpx.AsyncClient(timeout=2.0, transport=self.transport) as client:
                response = await client.post(
                    self.openai_responses_url,
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            text = str(result.get("output_text") or "")
            if not text:
                for item in result.get("output") or []:
                    for content in item.get("content") or []:
                        if content.get("type") == "output_text" and content.get("text"):
                            text = str(content["text"])
                            break
                    if text:
                        break
            parsed = json.loads(text)
            kind = str(parsed.get("kind") or "unknown")
            reply = attempt.screening_reply if kind == "screening" else ""
            if kind not in {"screening", "human", "voicemail", "ivr", "mailbox-full", "transfer", "unknown"}:
                return "unknown", ""
            return kind, reply
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            return "unknown", ""

    async def handle_speech(self, attempt_id: str, params: dict[str, str]) -> str:
        lock = self._speech_locks.setdefault(attempt_id, asyncio.Lock())
        async with lock:
            return await self._handle_speech_locked(attempt_id, params)

    async def _handle_speech_locked(self, attempt_id: str, params: dict[str, str]) -> str:
        attempt = self.attempt(attempt_id)
        call_sid = str(params.get("CallSid") or params.get("call_sid") or "")
        if not self._validate_call_sid(attempt, call_sid):
            raise LiveDialerError("The Twilio call identifier did not match this attempt.")
        idempotency_token = str(params.get("_IdempotencyToken") or "")[:200]
        if idempotency_token and idempotency_token in attempt.speech_responses:
            return attempt.speech_responses[idempotency_token]

        def remember(twiml: str) -> str:
            if idempotency_token:
                attempt.speech_responses[idempotency_token] = twiml
                attempt.speech_responses = dict(list(attempt.speech_responses.items())[-8:])
            self._persist_state()
            return twiml

        call_status = str(params.get("CallStatus") or params.get("call_status") or "").lower()
        if call_status in TERMINAL_CALL_STATUSES:
            attempt.status = call_status
            attempt.twilio_status = call_status
            if not attempt.outcome:
                attempt.outcome = call_status
            attempt.updated_at = utc_now()
            self._refresh_session_state(attempt.session_id)
            self._persist_state()
            logger.info("Attempt %s received speech on terminated call (%s), hanging up", attempt.id, call_status)
            return self._hangup_twiml()
        if attempt.status in TERMINAL_CALL_STATUSES or attempt.twilio_status in TERMINAL_CALL_STATUSES:
            logger.info("Attempt %s is already terminal (%s/%s), hanging up", attempt.id, attempt.status, attempt.twilio_status)
            return self._hangup_twiml()
        if attempt.status == "bridged" or attempt.outcome == "human-bridged":
            logger.info("Attempt %s is already bridged; ignoring extra speech callback", attempt.id)
            return remember('<?xml version="1.0" encoding="UTF-8"?><Response/>')

        transcript =" ".join(str(params.get("SpeechResult") or "").split())[:1000]
        attempt.turns += 1
        if transcript:
            attempt.transcript.append(transcript)
            attempt.transcript = attempt.transcript[-6:]

        if not transcript and (attempt.answered_by in MACHINE_RESULTS or attempt.voicemail_detected):
                if (
                    attempt.screening_detected
                    or attempt.human_detected
                    or attempt.outcome in {"screening", "screening-passed", "human-bridged", "human"}
                ):
                    return remember(self._hangup_twiml())
                attempt.voicemail_detected = True
                attempt.outcome = "voicemail"
                session = self.sessions.get(attempt.session_id)
                op_email = session.operator_email if session else ""
                if attempt.voicemail_played or not self.recording_metadata("voicemail", operator_email=op_email).get("configured"):
                    attempt.status = "completed"
                    self._refresh_session_state(attempt.session_id)
                    self._trigger_advance(attempt.session_id)
                    return remember(self._hangup_twiml())
                attempt.voicemail_played = True
                attempt.status = "voicemail-playing"
                self._refresh_session_state(attempt.session_id)
                self._trigger_advance(attempt.session_id)
                logger.info("Attempt %s answered_by is machine (%s) and silent, playing voicemail immediately", attempt.id, attempt.answered_by)
                return remember(self._voicemail_drop_twiml(operator_email=op_email, pause_seconds=1))

        kind, reply = await self._classify_transcript(attempt, transcript)
        logger.info(
            "Attempt %s (%s) turn %s speech %r -> kind=%s reply=%r (status=%s)",
            attempt.id,
            attempt.name,
            attempt.turns,
            transcript,
            kind,
            reply,
            attempt.status,
        )
        attempt.updated_at = utc_now()

        if kind == "ivr":
            attempt.outcome = "ivr"
            attempt.status = "completed"
            self._refresh_session_state(attempt.session_id)
            self._trigger_advance(attempt.session_id)
            logger.info("Attempt %s detected IVR menu, hanging up", attempt.id)
            return remember(self._hangup_twiml())
        if kind == "mailbox-full":
            attempt.outcome = "mailbox-full"
            attempt.status = "completed"
            self._refresh_session_state(attempt.session_id)
            self._trigger_advance(attempt.session_id)
            logger.info("Attempt %s detected full mailbox, hanging up without leaving voicemail", attempt.id)
            return remember(self._hangup_twiml())
        if kind == "screening":
            if attempt.turns >= 4:
                attempt.outcome = "unclassified"
                attempt.status = "completed"
                self._refresh_session_state(attempt.session_id)
                self._trigger_advance(attempt.session_id)
                return remember(self._hangup_twiml())
            attempt.screening_detected = True
            attempt.outcome = "screening"
            attempt.status = "screening"
            self._refresh_session_state(attempt.session_id)
            return remember(
                self._gather_twiml(
                    attempt, reply or attempt.screening_reply, slot="screening"
                )
            )
        if kind == "transfer":
            logger.info(
                "Attempt %s (%s) detected automated transfer prompt %r; continuing to listen for destination",
                attempt.id,
                attempt.name,
                transcript,
            )
            if attempt.turns >= 4:
                attempt.outcome = "unclassified"
                attempt.status = "completed"
                self._refresh_session_state(attempt.session_id)
                self._trigger_advance(attempt.session_id)
                return remember(self._hangup_twiml())
            return remember(self._gather_twiml(attempt, "", timeout=6))
        if attempt.answered_by in MACHINE_RESULTS or attempt.voicemail_detected or kind == "voicemail":
            attempt.voicemail_detected = True
            attempt.outcome = "voicemail"
            session = self.sessions.get(attempt.session_id)
            op_email = session.operator_email if session else ""
            if not self.recording_metadata("voicemail", operator_email=op_email).get("configured"):
                attempt.status = "completed"
                self._refresh_session_state(attempt.session_id)
                self._trigger_advance(attempt.session_id)
                return remember(self._hangup_twiml())
            attempt.voicemail_played = True
            attempt.status = "voicemail-playing"
            self._refresh_session_state(attempt.session_id)
            self._trigger_advance(attempt.session_id)
            logger.info("Attempt %s detected voicemail in speech or AMD, dropping voicemail immediately", attempt.id)
            return remember(self._voicemail_drop_twiml(operator_email=op_email, pause_seconds=1))
        if kind == "human":
            if attempt.status in TERMINAL_CALL_STATUSES or attempt.twilio_status in TERMINAL_CALL_STATUSES:
                logger.info("Attempt %s classified as human but call is already terminal (%s/%s), hanging up", attempt.id, attempt.status, attempt.twilio_status)
                return remember(self._hangup_twiml())
            if not await self._claim_human_winner(attempt):
                attempt.abandoned = True
                self._persist_state()
                session = self.sessions.get(attempt.session_id)
                op_email = session.operator_email if session else ""
                return remember(self._dropped_line_twiml(operator_email=op_email))
            return remember(self._conference_twiml(attempt))
        if attempt.turns >= 3:
            attempt.outcome = "unclassified"
            attempt.status = "completed"
            self._refresh_session_state(attempt.session_id)
            self._trigger_advance(attempt.session_id)
            return remember(self._hangup_twiml())
        return remember(
            self._gather_twiml(
                attempt,
                reply,
            )
        )

    async def _claim_human_winner(self, winner: DialAttempt) -> bool:
        async with self._lock:
            session = self.sessions.get(winner.session_id)
            if session is None:
                winner.status = "completed"
                winner.outcome = "unclassified"
                self._persist_state()
                return False
            if (
                winner.status in TERMINAL_CALL_STATUSES
                or winner.twilio_status in TERMINAL_CALL_STATUSES
                or winner.voicemail_played
                or (winner.answered_by in MACHINE_RESULTS and not winner.human_detected)
            ):
                logger.info(
                    "Cannot claim %s as winner because call is terminal (%s/%s) or machine (%s)",
                    winner.id,
                    winner.status,
                    winner.twilio_status,
                    winner.answered_by,
                )
                return False
            if session.operator_status not in {"answered", "in-progress"}:
                winner.abandoned = True
                winner.status = "completed"
                winner.outcome = "operator-unavailable"
                self._persist_state()
                return False
            existing_winner = next(
                (
                    self.attempts[item]
                    for item in session.attempt_ids
                    if item != winner.id
                    and item in self.attempts
                    and self.attempts[item].status not in TERMINAL_CALL_STATUSES
                    and (
                        self.attempts[item].human_detected
                        or self.attempts[item].status
                        in {"human-detected", "operator-connecting", "bridged"}
                    )
                ),
                None,
            )
            if existing_winner is not None:
                winner.abandoned = True
                winner.status = "completed"
                winner.outcome = "dropped-line"
                self._prioritize_dropped_contact(session, winner)
                winner.updated_at = utc_now()
                self._refresh_session_state(winner.session_id)
                self._persist_state()
                return False
            winner.human_detected = True
            winner.outcome = "human-bridged"
            winner.status = "bridged"
            session.human_attempt_id = winner.id
            session.status = "human-connected"
            session.updated_at = utc_now()
            logger.info("Elected human winner %s (%s) for session %s", winner.id, winner.name, session.id)
            # An answering machine is left to take its voicemail. Ending it as a
            # competitor played "let me call you right back" over our own message,
            # counted it as an abandoned person and dialed the machine again: three of
            # the eight "abandoned" calls in one session.
            competitors = [
                self.attempts[item]
                for item in session.attempt_ids
                if item != winner.id
                and item in self.attempts
                and self.attempts[item].status not in TERMINAL_CALL_STATUSES
                and not self.attempts[item].voicemail_detected
                and not self.attempts[item].voicemail_played
                and self.attempts[item].answered_by not in MACHINE_RESULTS
            ]
            for attempt in competitors:
                attempt.status = "canceling"
                attempt.updated_at = utc_now()
            self._persist_state()
        await asyncio.gather(
            *(self._end_competitor_call(session, attempt) for attempt in competitors)
        )
        self._persist_state()
        return True

    def _prioritize_dropped_contact(self, session: DialSession, attempt: DialAttempt) -> None:
        """Queue one call back to a person whose line was dropped, next in line.

        "Let me call you right back" only holds if the call back cannot be dropped too.
        It used to go out at once beside two fresh lines, sometimes while the first
        call was still playing that message, and one person was called three times in
        ninety seconds and dropped twice. The call back is now dialed alone
        (see _advance_session), and nobody is called back twice in one session.
        """
        cid = attempt.contact_id
        if not cid:
            return
        if attempt.callback or any(
            self.attempts[item].callback and self.attempts[item].contact_id == cid
            for item in session.attempt_ids
            if item in self.attempts
        ):
            return
        contact = next((c for c in session.queue if str(c.get("contact_id")) == cid), None)
        if contact is not None:
            contact = dict(contact)
        else:
            contact = {
                "contact_id": cid,
                "lead_id": attempt.lead_id,
                "name": attempt.name,
                "lead_name": attempt.company,
                "phone": attempt.phone,
                "close_url": attempt.close_url,
                "linkedin_url": attempt.linkedin_url,
                "title": attempt.title,
                "lead_status": attempt.lead_status,
            }
        already_queued = any(
            str(c.get("contact_id")) == cid
            for c in session.queue[session.next_index :]
        )
        if not already_queued:
            contact["callback"] = True
            session.queue.insert(session.next_index, contact)
            logger.info(
                "Prioritized dropped contact %s (%s) at queue position %d",
                cid,
                attempt.name,
                session.next_index + 1,
            )

    def _unprioritize_dropped_contact(self, session_id: str, contact_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session or not contact_id:
            return
        for i in range(session.next_index, len(session.queue)):
            if str(session.queue[i].get("contact_id")) == contact_id and session.queue[i].get("callback"):
                session.queue.pop(i)
                logger.info("Removed falsely dropped contact %s from callback queue", contact_id)
                break

    async def _end_competitor_call(self, session: DialSession, attempt: DialAttempt) -> bool:
        is_machine = (
            attempt.answered_by in MACHINE_RESULTS
            or attempt.voicemail_detected
            or attempt.voicemail_played
        )
        was_answered = (
            not is_machine
            and (
                attempt.status in {"in-progress", "answered", "screening", "human-detected"}
                or attempt.twilio_status in {"in-progress", "answered"}
                or (bool(attempt.answered_by) and attempt.answered_by not in MACHINE_RESULTS)
                or attempt.turns > 0
            )
        )
        if was_answered:
            attempt.outcome = "dropped-line"
            attempt.abandoned = True
            self._prioritize_dropped_contact(session, attempt)
            op_email = session.operator_email if session else ""
            twiml = self._dropped_line_twiml(operator_email=op_email)
            if attempt.twilio_call_sid and attempt.twilio_status not in TERMINAL_CALL_STATUSES:
                try:
                    await self._twilio_post(
                        f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                        {"Twiml": twiml},
                        timeout=5,
                    )
                except (httpx.HTTPError, LiveDialerError):
                    await self._end_call(attempt, "dropped-line")
            attempt.status = "completed"
            attempt.updated_at = utc_now()
            self._persist_state()
            return True
        elif is_machine:
            return await self._end_call(attempt, "voicemail")
        return await self._end_call(attempt, "canceled-after-human")

    def _validate_operator_parent(self, attempt: DialAttempt, params: dict[str, str]) -> bool:
        parent_sid = str(
            params.get("ParentCallSid")
            or params.get("ParentCallSID")
            or params.get("CallSid")
            or ""
        )
        return bool(
            parent_sid.startswith("CA")
            and attempt.twilio_call_sid
            and hmac.compare_digest(attempt.twilio_call_sid, parent_sid)
        )

    def handle_operator_status(self, attempt_id: str, params: dict[str, str]) -> None:
        attempt = self.attempt(attempt_id)
        if not self._validate_operator_parent(attempt, params):
            raise LiveDialerError("The operator callback did not match the parent call.")
        child_sid = str(params.get("CallSid") or "")
        parent_sid = str(params.get("ParentCallSid") or params.get("ParentCallSID") or "")
        if not parent_sid or not child_sid.startswith("CA"):
            raise LiveDialerError("The operator callback did not include a child call identifier.")
        if attempt.operator_call_sid and not hmac.compare_digest(
            attempt.operator_call_sid, child_sid
        ):
            raise LiveDialerError("The operator call identifier changed unexpectedly.")
        attempt.operator_call_sid = child_sid

        sequence_raw = str(params.get("SequenceNumber") or "")
        if sequence_raw:
            try:
                sequence = int(sequence_raw)
            except ValueError:
                sequence = -1
            if sequence >= 0 and sequence < attempt.operator_sequence_number:
                return
            if sequence >= 0:
                attempt.operator_sequence_number = sequence

        status = str(params.get("CallStatus") or "").lower()
        if status:
            attempt.operator_status = status
        attempt.bridge_duration = safe_int(params.get("CallDuration"), attempt.bridge_duration)
        session = self.sessions.get(attempt.session_id)
        if status in {"in-progress", "answered"}:
            attempt.status = "bridged"
            attempt.outcome = "human-bridged"
            if session is not None:
                session.status = "human-connected"
                session.updated_at = utc_now()
        elif status == "ringing":
            attempt.status = "operator-connecting"
        elif status in TERMINAL_CALL_STATUSES and attempt.outcome != "human-bridged":
            attempt.status = "operator-unavailable"
            attempt.outcome = f"operator-{status}"
            if session is not None:
                session.status = "operator-connecting"
                session.updated_at = utc_now()
        attempt.updated_at = utc_now()
        self._persist_state()

    def handle_bridge_result(self, attempt_id: str, params: dict[str, str]) -> str:
        attempt = self.attempt(attempt_id)
        if not self._validate_operator_parent(attempt, params):
            raise LiveDialerError("The bridge result did not match the parent call.")
        dial_status = str(params.get("DialCallStatus") or "").lower()
        attempt.bridge_duration = safe_int(params.get("DialCallDuration"), attempt.bridge_duration)
        if attempt.bridge_duration > 0:
            attempt.duration = attempt.bridge_duration
        if dial_status in {"completed", "answered"}:
            attempt.outcome = "human-bridged"
        elif dial_status:
            attempt.abandoned = True
            attempt.outcome = f"operator-{dial_status}"
        else:
            attempt.abandoned = True
            attempt.outcome = "operator-unknown"
        attempt.operator_status = dial_status or attempt.operator_status
        attempt.status = "completed"
        attempt.updated_at = utc_now()
        session = self.sessions.get(attempt.session_id)
        if session is not None:
            if session.conference_name:
                with contextlib.suppress(RuntimeError):
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._stop_conference_recordings(
                            session.conference_name,
                            operator_email=session.operator_email,
                        )
                    )
            if dial_status in {"completed", "answered"}:
                session.human_attempt_id = ""
                session.status = "running"
                with contextlib.suppress(RuntimeError):
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._log_close_once(attempt))
                    loop.create_task(self._advance_session(session.id))
            else:
                session.status = "failed"
            session.updated_at = utc_now()
        if attempt.close_call_id and attempt.duration > 0:
            op_email = session.operator_email if session else ""
            with contextlib.suppress(RuntimeError):
                loop = asyncio.get_running_loop()
                loop.create_task(
                    asyncio.to_thread(
                        self.close_dialer.update_call_recording,
                        attempt.close_call_id,
                        recording_url=attempt.recording_url,
                        duration=attempt.duration,
                        operator_email=op_email,
                    )
                )
        self._refresh_session_state(attempt.session_id)
        self._persist_state()
        return self._hangup_twiml()

    async def _log_close_once(self, attempt: DialAttempt) -> None:
        if attempt.close_logged or not attempt.lead_id:
            return
        if not attempt.twilio_call_sid and attempt.outcome not in {"invalid", "provider-error", "failed"}:
            return
        attempt.close_logged = True
        # This lands on a real lead's timeline, so it says what happened rather
        # than what the tool used to be called.
        flag_suffix = (
            " (flagged by operator: false-positive human connect)"
            if getattr(attempt, "operator_flagged_voicemail", False)
            else (
                f" (marked {getattr(attempt, 'disposition', 'Not Interested')} by operator)"
                if getattr(attempt, "operator_disqualified", False)
                else ""
            )
        )
        carrier_info: list[str] = []
        if attempt.outcome == "invalid":
            if attempt.error_code == "13224" or attempt.sip_response_code == "404":
                carrier_info.append("number disconnected / out of service (SIP 404 / Twilio 13224)")
            elif attempt.error_code:
                carrier_info.append(
                    f"invalid number (Twilio {attempt.error_code}: {attempt.error_message or 'invalid format'})"
                )
            else:
                carrier_info.append("invalid phone number")
        elif attempt.error_code or (
            attempt.sip_response_code and str(attempt.sip_response_code).strip() not in {"200", "487"}
        ):
            detail = attempt.error_message or (f"SIP {attempt.sip_response_code}" if attempt.sip_response_code else "")
            carrier_info.append(f"carrier error: {attempt.error_code or attempt.sip_response_code} ({detail})")

        carrier_suffix = f"; {'; '.join(carrier_info)}" if carrier_info else ""
        transcript_suffix = (
            f"; transcript: {' // '.join(attempt.transcript[-4:])}"
            if attempt.transcript
            else ""
        )
        note = (
            f"Parallel dialer — outcome: {attempt.outcome or attempt.status}{flag_suffix}{carrier_suffix}; "
            f"Twilio status: {attempt.twilio_status}; "
            f"operator: {attempt.operator_status or 'not dialed'}; "
            f"answered by: {attempt.answered_by or 'not returned'}{transcript_suffix}."
        )
        session = self.sessions.get(attempt.session_id)
        op_email = session.operator_email if session else ""
        try:
            result = await asyncio.to_thread(
                self.close_dialer.log_call,
                lead_id=attempt.lead_id,
                contact_id=attempt.contact_id,
                phone=attempt.phone,
                duration=attempt.duration,
                note=note,
                operator_email=op_email,
                recording_url=attempt.recording_url,
            )
            if isinstance(result, dict) and result.get("id"):
                attempt.close_call_id = str(result["id"])
        except DialerError:
            attempt.close_logged = False
        self._persist_state()

    def _answer_action(self, attempt: DialAttempt) -> str:
        return self._callback_url("speech", attempt.id)

    def _prompt_twiml(self, prompt: str, slot: str = "", operator_email: str = "") -> str:
        """A recording if the operator made one, their words read aloud otherwise."""
        if slot and self.recording_metadata(slot, operator_email=operator_email).get("configured"):
            media = escape(self.recording_media_url(slot, operator_email=operator_email))
            return f"<Play>{media}</Play>"
        safe_prompt = escape(" ".join(prompt.split())[:300])
        return f"<Say>{safe_prompt}</Say>" if safe_prompt else ""

    def _gather_twiml(
        self, attempt: DialAttempt, prompt: str, *, timeout: int = 8, slot: str = ""
    ) -> str:
        session = self.sessions.get(attempt.session_id)
        op_email = session.operator_email if session else ""
        action = quoteattr(self._answer_action(attempt))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Gather input="speech" action={action} method="POST" '
            f'speechTimeout="1.0" timeout="{timeout}" actionOnEmptyResult="true">'
            f"{self._prompt_twiml(prompt, slot, operator_email=op_email)}"
            "</Gather><Hangup/></Response>"
        )

    def _stream_twiml(self, attempt: DialAttempt) -> str:
        ws_url = self.stream_worker_url.replace("https://", "wss://").replace("http://", "ws://")
        stream_target = f"{ws_url}/stream?attempt_id={escape(attempt.id)}"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Connect>"
            f'<Stream url={quoteattr(stream_target)}>'
            f'<Parameter name="attempt_id" value={quoteattr(attempt.id)} />'
            "</Stream>"
            "</Connect>"
            '<Pause length="30"/>'
            "</Response>"
        )

    def answer_twiml(self, attempt_id: str) -> str:
        attempt = self.attempt(attempt_id)
        if attempt.status in TERMINAL_CALL_STATUSES:
            return self._hangup_twiml()
        attempt.status = "in-progress"
        attempt.twilio_status = "in-progress"
        attempt.updated_at = utc_now()
        self._persist_state()
        if self.stream_worker_url:
            return self._stream_twiml(attempt)
        # Immediate listen with zero audio playback delay.
        # Playing greeting audio inside <Gather> makes Twilio's speech recognizer deaf
        # during playback and adds 2.5-5.5s delay to pickup-to-connect latency.
        # Listening immediately allows prospect "Hello" + 1.0s speech timeout to bridge in ~1.5s.
        return self._gather_twiml(attempt, "", timeout=5, slot="")

    async def handle_stream_callback(
        self, attempt_id: str, kind: str, transcript: str = ""
    ) -> dict[str, str]:
        attempt = self.attempt(attempt_id)
        if attempt.status in TERMINAL_CALL_STATUSES:
            return {"status": "ignored", "reason": "terminal"}

        if transcript:
            attempt.transcript.append(transcript[:1000])
            attempt.transcript = attempt.transcript[-6:]

        logger.info(
            "Attempt %s (%s) received stream callback kind=%s transcript=%r",
            attempt.id,
            attempt.name,
            kind,
            transcript,
        )

        if kind == "human":
            if not await self._claim_human_winner(attempt):
                attempt.abandoned = True
                self._persist_state()
                session = self.sessions.get(attempt.session_id)
                op_email = session.operator_email if session else ""
                twiml = self._dropped_line_twiml(operator_email=op_email)
                try:
                    await self._twilio_post(
                        f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                        {"Twiml": twiml},
                        timeout=5,
                    )
                except (httpx.HTTPError, LiveDialerError):
                    await self._end_call(attempt, "dropped-line")
                return {"status": "dropped-line-played"}
            twiml = self._conference_twiml(attempt)
            try:
                await self._twilio_post(
                    f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                    {"Twiml": twiml},
                    timeout=5,
                )
            except (httpx.HTTPError, LiveDialerError) as exc:
                logger.error(
                    "Failed to redirect Twilio call to conference for %s: %s",
                    attempt.id,
                    exc,
                )
                return {"status": "error", "error": str(exc)}
            return {"status": "bridged"}

        if kind in {"voicemail", "mailbox-full"}:
            attempt.voicemail_detected = True
            attempt.outcome = kind
            session = self.sessions.get(attempt.session_id)
            op_email = session.operator_email if session else ""
            if (
                kind == "voicemail"
                and not attempt.voicemail_played
                and self.recording_metadata("voicemail", operator_email=op_email).get("configured")
            ):
                attempt.voicemail_played = True
                attempt.status = "voicemail-playing"
                self._persist_state()
                try:
                    await self._twilio_post(
                        f"/Accounts/{self.account_sid}/Calls/{attempt.twilio_call_sid}.json",
                        {"Twiml": self._voicemail_drop_twiml(operator_email=op_email, pause_seconds=1)},
                        timeout=5,
                    )
                except (httpx.HTTPError, LiveDialerError):
                    await self._end_call(attempt, "voicemail-playback-failed")
            else:
                await self._end_call(attempt, kind)
            return {"status": kind}

        if kind in {"ivr", "screening"}:
            await self._end_call(attempt, kind)
            return {"status": kind}

        return {"status": "unknown"}

    def _bridge_twiml(self, attempt: DialAttempt, prompt: str) -> str:
        return self._conference_twiml(attempt)

    def _operator_conference_twiml(self, session: DialSession) -> str:
        conference = escape(session.conference_name)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            '<Dial answerOnBridge="true">'
            '<Conference beep="false" startConferenceOnEnter="true" '
            'endConferenceOnExit="true" jitterBufferSize="large" '
            'waitUrl="" '
            f'participantLabel="operator">{conference}</Conference>'
            "</Dial></Response>"
        )

    def _conference_twiml(self, attempt: DialAttempt) -> str:
        session = self.sessions.get(attempt.session_id)
        if session is None or not session.conference_name:
            return self._hangup_twiml()
        conference = escape(session.conference_name)
        action = quoteattr(self._callback_url("bridge", attempt.id))
        participant = escape(f"lead-{attempt.id}")
        rec_callback = quoteattr(self._callback_url("conference-recording", attempt.id))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Dial answerOnBridge="true" action={action} method="POST">'
            '<Conference beep="false" startConferenceOnEnter="true" '
            'endConferenceOnExit="false" jitterBufferSize="large" '
            'waitUrl="" '
            'record="record-from-start" '
            f'recordingStatusCallback={rec_callback} '
            'recordingStatusCallbackEvent="completed" '
            f'participantLabel="{participant}">{conference}</Conference>'
            "</Dial><Hangup/></Response>"
        )

    async def _stop_conference_recordings(
        self, conference_name: str, operator_email: str = ""
    ) -> None:
        """Stop in-progress conference recordings when a lead disconnects so the recording is
        not kept running with operator background audio or concatenated into the next lead's call."""
        if not conference_name:
            return
        account_sid, _, _, _ = self._twilio_credentials_for_operator(operator_email)
        encoded_name = quote(conference_name)
        try:
            conf_data = await self._twilio_get(
                f"/Accounts/{account_sid}/Conferences.json?FriendlyName={encoded_name}&Status=in-progress",
                operator_email=operator_email,
            )
            conferences = conf_data.get("conferences") or []
            for conf in conferences:
                conf_sid = conf.get("sid")
                if not conf_sid:
                    continue
                # 1. Try stopping Twilio.CURRENT directly
                try:
                    await self._twilio_post(
                        f"/Accounts/{account_sid}/Conferences/{conf_sid}/Recordings/Twilio.CURRENT.json",
                        {"Status": "stopped"},
                        operator_email=operator_email,
                    )
                    logger.info("Stopped active conference recording Twilio.CURRENT for conference %s", conf_sid)
                except Exception:
                    pass

                # 2. Also stop any specific in-progress recordings on that conference
                try:
                    rec_data = await self._twilio_get(
                        f"/Accounts/{account_sid}/Conferences/{conf_sid}/Recordings.json?Status=in-progress",
                        operator_email=operator_email,
                    )
                    recordings = rec_data.get("recordings") or []
                    for rec in recordings:
                        rec_sid = rec.get("sid")
                        if not rec_sid:
                            continue
                        try:
                            await self._twilio_post(
                                f"/Accounts/{account_sid}/Conferences/{conf_sid}/Recordings/{rec_sid}.json",
                                {"Status": "stopped"},
                                operator_email=operator_email,
                            )
                            logger.info("Stopped in-progress conference recording %s for conference %s", rec_sid, conf_sid)
                        except Exception as exc:
                            logger.debug("Could not stop recording %s on %s: %s", rec_sid, conf_sid, exc)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("Error querying active conference recordings for %s: %s", conference_name, exc)

    def _voicemail_twiml(self, operator_email: str = "") -> str:
        # No message recorded means the machine is hung up on in silence rather than
        # played an empty file: nothing is left behind on anyone's phone.
        if not self.recording_metadata("voicemail", operator_email=operator_email).get("configured"):
            return self._hangup_twiml()
        media = escape(self.recording_media_url("voicemail", operator_email=operator_email))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Pause length=\"1\"/><Play>{media}</Play><Hangup/></Response>"
        )

    def _voicemail_drop_twiml(self, operator_email: str = "", *, pause_seconds: int = 1) -> str:
        """Play the recorded voicemail after a brief pause so the tone finishes sounding."""
        if not self.recording_metadata("voicemail", operator_email=operator_email).get("configured"):
            return self._hangup_twiml()
        media = escape(self.recording_media_url("voicemail", operator_email=operator_email))
        pause = f'<Pause length="{pause_seconds}"/>' if pause_seconds > 0 else ""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response>{pause}<Play>{media}</Play><Hangup/></Response>"
        )

    @staticmethod
    def _voicemail_wait_twiml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response><Pause length="30"/><Hangup/></Response>'
        )

    def inbound_twiml(self, caller: str = "", to_number: str = "") -> str:
        """Route a callback to Close, as the lead who is calling.

        The returning caller's own number is passed through as the caller ID,
        because that is the only thing Close has to match against its contacts.
        Forwarding under our own number would make every callback in the queue
        look like one anonymous repeat caller, which is the whole feature lost
        for the sake of one attribute. Twilio permits it for an inbound call's
        own `From`, and for nothing else.
        """
        destination = self.callback_number or self.operator_number
        if to_number:
            norm_to = normalize_phone(to_number)
            for state_file in self.settings.state_dir.glob("dialer-numbers-*.json"):
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    nums = [
                        normalize_phone(n.get("phone_number", ""))
                        for n in data.get("numbers", [])
                    ]
                    if norm_to in nums:
                        op_email = str(data.get("operator_email") or "").strip().lower()
                        clean_op = clean_operator_identity(op_email)
                        op_dest = normalize_phone(
                            read_secret(
                                f"dialer-callback-number-{clean_op}",
                                f"DIALER_CALLBACK_NUMBER_{clean_op.upper()}",
                            )
                        )
                        if not op_dest:
                            op_dest = normalize_phone(
                                read_secret(
                                f"dialer-operator-number-{clean_op}",
                                f"DIALER_OPERATOR_NUMBER_{clean_op.upper()}",
                            )
                        )
                        if op_dest:
                            destination = op_dest
                        break
                except (KeyError, ValueError, OSError):
                    pass

        if not destination:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response><Say>The person you are calling is unavailable.</Say><Hangup/></Response>"
            )
        forwarded = normalize_phone(caller)
        caller_id = f' callerId="{escape(forwarded)}"' if forwarded else ""
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Dial answerOnBridge="true" timeout="25"{caller_id}>'
            f"<Number>{escape(destination)}</Number>"
            "</Dial><Hangup/></Response>"
        )

    @staticmethod
    def _hangup_twiml() -> str:
        return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'

    def _dropped_line_twiml(self, operator_email: str = "") -> str:
        if self.recording_metadata("dropped", operator_email=operator_email).get("configured"):
            url = escape(self.recording_media_url("dropped", operator_email=operator_email))
            return f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{url}</Play><Hangup/></Response>'
        return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Hello? Yeah, cannot hear you, let me call you right back.</Say><Hangup/></Response>'
