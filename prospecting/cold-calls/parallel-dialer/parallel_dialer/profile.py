"""What a deployment says in its own voice.

The engine is generic. What the people being called hear, and what the operator reads on
screen, belongs to one company and lives here: the brand name, the talk track and the reply
given to a call screener. It is read from dialer.toml (or the path in DIALER_CONFIG). Every
value has a neutral default, so a fresh install runs before anything is written, but the
dialer stays locked until a brand name is set (see LiveDialer.blockers): the brand is spoken
to the people being called.

Templates use {{Token}} markers:

    {{Brand}}     the company name, from [brand] name
    {{Operator}}  the operator's display name

A marker with no value is left as written, so a typo shows up instead of silently
disappearing. [Name], [My Name] and [Company] in the talk track are not markers of this kind:
the page fills them in for the person on the line.

dialer.toml accepts only the settings below. Anything else is refused with a message, so a
typo is caught instead of ignored. This dialer does not schedule meetings or send email.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BRAND = "Your Company"
# The service refuses a start request whose screening reply is outside these bounds.
SCREENING_REPLY_MIN = 15
SCREENING_REPLY_MAX = 240

TOKEN = re.compile(r"\{\{\s*([A-Za-z_]+)\s*\}\}")

DEFAULT_SCRIPT = """# COLD CALL TALK TRACK

Write your own here. The text you type in this box saves per operator, and [Name],
[My Name] and [Company] are filled in for the person on the line.

## 1. THE OPENER (15 seconds)
"Hey [Name], this is [My Name] with {{Brand}}. I know I'm catching you in the middle of your day. Do you have 30 seconds for me to tell you why I called? If it's not relevant, you can hang up on me."
*Pause. Let them answer.*

## 2. THE HOOK (30 seconds)
"[One sentence on the problem your customers have.]
[One sentence on what you do about it.]
[One question that gets them talking about how they handle it today.]"

## 3. DISCOVERY & QUALIFYING
• "[A question that shows whether they have the problem.]"
• "[A question about how they solve it today.]"
• "[A question about what would make them change.]"

## 4. COMMON OBJECTIONS & REBUTTALS
### "Just send me an email"
👉 "Happy to. What's the best email for it? And do you have 15 minutes later this week to walk through it together?"

### "We're not interested"
👉 "Fair enough. Is that because it isn't a priority right now, or because you already have it covered?"

### "We already use something for that"
👉 "Good to hear. What do you like most about it, and what do you wish it did better?"

## 5. THE CLOSE
"Let's do this: I can show you in 15 minutes. Tuesday at 2 PM or Wednesday at 10 AM. Which works better for you?"
"""

DEFAULT_SCREENING_REPLY = (
    "Hi, this is {{Operator}} calling from {{Brand}}. "
    "Could you point me to the right person to speak with? It will only take a minute."
)

# What dialer.toml may say: table -> the keys it accepts. [operators] is a table of tables,
# one per operator, named by their address.
SETTINGS: dict[str, tuple[str, ...]] = {
    "brand": ("name",),
    "call": ("screening_reply", "script", "script_file"),
}
OPERATOR_SETTINGS = ("name",)


class ProfileError(ValueError):
    """dialer.toml is present but cannot be used."""


def fill(template: str, values: dict[str, str]) -> str:
    """Replace {{Token}} markers with values; markers without a value stay as written."""
    lowered = {key.lower(): value for key, value in values.items()}

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return lowered[key] if key in lowered else match.group(0)

    return TOKEN.sub(replace, template)


def _display_name(email: str) -> str:
    return email.split("@")[0].replace(".", " ").replace("_", " ").title() or "Operator"


@dataclass(frozen=True)
class Profile:
    brand: str = DEFAULT_BRAND
    # False until [brand] name is set: LiveDialer.blockers() keeps the dialer locked.
    brand_is_set: bool = False
    screening_reply: str = DEFAULT_SCREENING_REPLY
    script: str = DEFAULT_SCRIPT
    # Display names by address, for those whose name is not just their address made readable.
    operators: dict[str, str] = field(default_factory=dict)

    def operator_name(self, email: str) -> str:
        """How the operator is named to the people they call."""
        clean = (email or "").strip().lower()
        return self.operators.get(clean) or _display_name(clean)

    def values(self, operator_email: str = "") -> dict[str, str]:
        """Every {{Token}} this profile can fill, for one operator."""
        return {"Brand": self.brand, "Operator": self.operator_name(operator_email)}

    def render(self, template: str, operator_email: str = "") -> str:
        return fill(template, self.values(operator_email))

    def script_for(self, operator_email: str = "") -> str:
        """The talk track for one operator. [Name] and [Company] are left for the page."""
        return self.render(self.script, operator_email)

    def page_values(self, operator_email: str) -> dict[str, Any]:
        """What the dialer page needs to know, as plain data for its script."""
        return {
            "brand": self.brand,
            "script": self.script_for(operator_email),
            "screening_reply": self.render(self.screening_reply, operator_email),
        }


def _text(table: dict[str, Any], key: str) -> str:
    value = table.get(key, "")
    if not isinstance(value, str):
        raise ProfileError(f"{key} must be text.")
    return value.strip()


def _table(data: dict[str, Any], name: str, allowed: tuple[str, ...]) -> dict[str, Any]:
    table = data.get(name) or {}
    if not isinstance(table, dict):
        raise ProfileError(f"[{name}] must be a table.")
    for key in table:
        if key not in allowed:
            raise ProfileError(
                f"[{name}] {key} is not a setting of this dialer. [{name}] accepts: {', '.join(allowed)}."
            )
    return table


def _read_text_file(base: Path, name: str, what: str) -> str:
    path = (base / name).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"Cannot read {what} {path}: {exc.strerror or exc}") from exc


def parse_profile(data: dict[str, Any], base: Path) -> Profile:
    """Build a Profile from parsed TOML. `base` is where relative file names are found."""
    for name in data:
        if name in {"calendar", "email"}:
            raise ProfileError(
                f"[{name}] is not supported: this dialer does not schedule meetings or send email."
            )
        if name not in {*SETTINGS, "operators"}:
            raise ProfileError(
                f"[{name}] is not a setting of this dialer. dialer.toml has [brand], [call] and [operators]."
            )

    brand_table = _table(data, "brand", SETTINGS["brand"])
    call = _table(data, "call", SETTINGS["call"])
    raw_operators = data.get("operators") or {}
    if not isinstance(raw_operators, dict):
        raise ProfileError("[operators] must be a table of tables, one per operator email.")

    brand = _text(brand_table, "name")
    fields: dict[str, Any] = {
        "brand": brand or DEFAULT_BRAND,
        "brand_is_set": bool(brand) and brand != DEFAULT_BRAND,
    }
    if "screening_reply" in call:
        fields["screening_reply"] = _text(call, "screening_reply")
    if "script" in call and "script_file" in call:
        raise ProfileError("[call] has both script and script_file: use one.")
    if "script_file" in call:
        fields["script"] = _read_text_file(base, _text(call, "script_file"), "script_file")
    elif "script" in call:
        fields["script"] = _text(call, "script")

    operators: dict[str, str] = {}
    for raw_email, table in raw_operators.items():
        if not isinstance(table, dict):
            raise ProfileError(f"[operators.\"{raw_email}\"] must be a table.")
        clean = str(raw_email).strip().lower()
        if "@" not in clean:
            raise ProfileError(f"[operators.\"{raw_email}\"] must be named by the operator's email address.")
        for key in table:
            if key not in OPERATOR_SETTINGS:
                raise ProfileError(
                    f"[operators.\"{raw_email}\"] {key} is not a setting of this dialer. "
                    f"It accepts: {', '.join(OPERATOR_SETTINGS)}."
                )
        operators[clean] = _text(table, "name") or _display_name(clean)
    fields["operators"] = operators

    profile = Profile(**fields)
    for who in operators or {"": ""}:
        reply = profile.render(profile.screening_reply, who)
        if not SCREENING_REPLY_MIN <= len(reply) <= SCREENING_REPLY_MAX:
            raise ProfileError(
                f"[call] screening_reply must be {SCREENING_REPLY_MIN} to {SCREENING_REPLY_MAX} characters "
                f"once filled in (it is {len(reply)}{' for ' + who if who else ''})."
            )
    return profile


def load_profile(path: str | Path | None = None) -> Profile:
    """Read dialer.toml. With no file anywhere, the neutral defaults are returned.

    Looked for, in order: the path given, DIALER_CONFIG, ./dialer.toml. A file that is
    named but missing is an error; only the unnamed ./dialer.toml may be absent.
    """
    named = path or os.environ.get("DIALER_CONFIG", "").strip() or None
    location = Path(named).expanduser() if named else Path("dialer.toml")
    if not location.is_file():
        if named:
            raise ProfileError(f"The config file {location} does not exist.")
        return Profile()
    try:
        data = tomllib.loads(location.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProfileError(f"Cannot read {location}: {exc}") from exc
    return parse_profile(data, location.resolve().parent)
