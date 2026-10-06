"""This dialer does not schedule meetings or send email, and does nothing on its own. These
tests are what keeps it that way: a change that brings a calendar or a mailbox back in fails
here, however it is spelled."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "parallel_dialer"


def test_the_modules_that_did_it_are_gone():
    for name in ("calendar_service", "email_service", "scheduling", "connectors"):
        assert importlib.util.find_spec(f"parallel_dialer.{name}") is None, name


def test_no_dependency_reaches_a_calendar_or_a_mailbox():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for word in ("google", "gmail", "sendgrid", "mailgun", "smtp", "msal", "exchangelib"):
        assert word not in pyproject, word
    # Nothing imports a mail or calendar library either.
    imports = set()
    for path in PACKAGE.rglob("*.py"):
        imports |= set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z0-9_]+)", path.read_text(encoding="utf-8"), re.M))
    assert not imports & {"smtplib", "imaplib", "poplib", "google", "googleapiclient", "requests", "sendgrid"}, imports


def test_no_file_in_the_package_talks_to_one():
    # Google's Calendar and Gmail APIs, mail servers and mail services, and what the old
    # endpoints and controls were called. The Twilio SDK is a vendored third-party bundle.
    forbidden = (
        "googleapis.com", "calendar/v3", "gmail", "freebusy", "smtp", "sendgrid", "mailgun", "postmark",
        "book-demo", "book_demo", "send-info", "send_info", "check-availability", "scheduling-settings",
        "sleep_guard", "google_workspace", "service_account", "google meet", "hangoutsmeet",
        "extract_scheduling_intent", "parse_spoken_time",
    )
    for path in PACKAGE.rglob("*"):
        if not path.is_file() or path.suffix in {".woff2", ".pyc"} or path.name == "twilio-voice-2.18.5.js":
            continue
        text = path.read_text(encoding="utf-8").lower()
        for word in forbidden:
            assert word not in text, f"{word!r} in {path.relative_to(ROOT)}"


def test_the_guides_do_not_promise_it_either():
    for name in ("README.md", ".env.example", "dialer.example.toml"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        for word in ("book demo", "send info email", "calendar booking", "google_service_account_file", "[calendar]", "[email]"):
            assert word not in text, f"{word!r} in {name}"
    # and the README says so plainly
    assert "does not schedule meetings or send email" in (ROOT / "README.md").read_text(encoding="utf-8")
