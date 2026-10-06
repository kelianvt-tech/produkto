"""Configuration for the parallel dialer.

Settings come from environment variables, a .env file or a systemd credential (see
read_secret). The wording a prospect reads and hears lives in dialer.toml (profile.py).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .profile import Profile, load_profile

DEFAULT_ROOT = "./data"
DEFAULT_PUBLIC_BASE = "http://127.0.0.1:8767"


class ConfigError(RuntimeError):
    """The environment cannot start a dialer."""


def clean_operator_identity(operator_email: str) -> str:
    """The short name an operator's files, keys and softphone go by: the address before the @.

    Two operators must not share one (alice@example.com and alice@example.org would share keys and
    recordings), which Settings.load refuses.
    """
    clean = (operator_email or "").strip().lower()
    if "@" in clean:
        clean = clean.split("@")[0]
    return re.sub(r"[^a-zA-Z0-9_-]", "_", clean) or "operator"


def read_secret(name: str, env_name: str | None = None) -> str:
    """Read a setting from an env var, a systemd credential or a .env file without logging it.

    Looked for in this order: the env var `env_name`; a systemd credential called `name`
    (LoadCredential=); the env var DIALER_CREDENTIAL_<NAME>; a line `env_name=...` in a
    .env file beside the code or in the working directory. An empty string means unset.
    """
    if env_name and env_name in os.environ:
        return os.environ[env_name].strip()
    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if credentials_dir:
        path = Path(credentials_dir) / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    direct = os.environ.get(f"DIALER_CREDENTIAL_{name.upper().replace('-', '_')}")
    if direct:
        return direct.strip()
    if env_name:
        for candidate in (
            Path(__file__).resolve().parents[1] / ".env",
            Path.cwd() / ".env",
        ):
            if candidate.is_file():
                try:
                    for raw in candidate.read_text(encoding="utf-8").splitlines():
                        line = raw.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        if key.strip() == env_name:
                            return value.strip().strip('"').strip("'")
                except OSError:
                    continue
    return ""


def _emails(raw: str) -> frozenset[str]:
    return frozenset(item.strip().lower() for item in re.split(r"[,\s]+", raw) if item.strip())


def check_operator_emails(emails: frozenset[str]) -> None:
    """Refuse two addresses that would be the same operator to the engine."""
    seen: dict[str, str] = {}
    for email in sorted(emails):
        if "@" not in email:
            raise ConfigError(f"'{email}' in DIALER_ALLOWED_EMAILS is not an email address.")
        identity = clean_operator_identity(email)
        if identity in seen:
            raise ConfigError(
                f"{seen[identity]} and {email} would share the name '{identity}', and so their "
                "keys, recordings and softphone. Give each operator a different part before the @."
            )
        seen[identity] = email


@dataclass(frozen=True)
class Settings:
    root: Path
    llm_model: str = "gpt-5-mini"
    # Where Twilio and the browser reach this service. Twilio needs a public https address
    # to call back; the exact spelling matters, because writes from the page are only
    # accepted when their Origin header is this.
    public_base_url: str = DEFAULT_PUBLIC_BASE
    # The people who may sign in, by address. Nobody can sign in while it is empty.
    allowed_emails: frozenset[str] = frozenset()
    # How long a browser stays signed in.
    session_days: int = 14
    profile: Profile = field(default_factory=Profile)

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def twilio_base_url(self) -> str:
        return self.public_base_url.rstrip("/") + "/twilio/dialer"

    @property
    def secure_cookies(self) -> bool:
        return self.public_base_url.startswith("https://")

    @classmethod
    def load(cls) -> Settings:
        emails = _emails(read_secret("dialer-allowed-emails", "DIALER_ALLOWED_EMAILS"))
        check_operator_emails(emails)
        public = (read_secret("dialer-public-url", "DIALER_PUBLIC_URL") or DEFAULT_PUBLIC_BASE).rstrip("/")
        if not public.startswith(("http://", "https://")):
            raise ConfigError("DIALER_PUBLIC_URL must start with http:// or https://.")
        try:
            days = int(read_secret("dialer-session-days", "DIALER_SESSION_DAYS") or 14)
        except ValueError as exc:
            raise ConfigError("DIALER_SESSION_DAYS must be a whole number of days.") from exc
        return cls(
            root=Path(read_secret("dialer-root", "DIALER_ROOT") or DEFAULT_ROOT).expanduser().resolve(),
            llm_model=read_secret("dialer-llm-model", "DIALER_LLM_MODEL") or "gpt-5-mini",
            public_base_url=public,
            allowed_emails=emails,
            session_days=max(1, days),
            profile=load_profile(),
        )
