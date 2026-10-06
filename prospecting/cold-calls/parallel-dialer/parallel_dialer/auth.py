"""Who is calling the dialer.

Every operator has an access key: an HMAC of this service's secret with their address.
Nothing is stored. The key is worked out again to check it, so changing the secret or
DIALER_TOKEN_VERSION revokes every key and every signed-in browser at once.

* A browser signs in on /login with its email and access key and is given a signed,
  expiring session cookie. `python -m parallel_dialer access-key EMAIL` prints the key, and a
  signed-in browser can read its own from /dialer/api/mobile-token to pair a phone.
* An app presents the same key as `Authorization: Bearer <key>`.

To use another identity provider (Google, Okta, a reverse proxy that sets a header),
replace `resolve_operator` in api.py. Nothing else in the service knows how someone signed in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from .config import read_secret

SESSION_COOKIE = "dialer_session"


@dataclass(frozen=True)
class Operator:
    email: str
    name: str
    # "session" for a browser signed in on /login, "bearer" for an app with the key.
    via: str = "session"


def _digest(secret: str, message: str) -> str:
    raw = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def access_key(secret: str, email: str, version: str = "1") -> str:
    """The operator's access key. Empty when there is no secret to derive it from."""
    if not secret:
        return ""
    return _digest(secret, f"dialer-key:{version}:{email.strip().lower()}")


def match_access_key(secret: str, supplied: str, emails: frozenset[str], version: str = "1") -> str:
    """The operator an access key belongs to, or "" when it matches nobody."""
    supplied = supplied.strip()
    if not secret or not supplied:
        return ""
    for email in sorted(emails):
        if hmac.compare_digest(access_key(secret, email, version), supplied):
            return email
    return ""


def sign_session(secret: str, email: str, version: str, expires_at: int) -> str:
    """A session cookie value: the address and expiry, and a signature over both."""
    payload = f"{expires_at}:{email.strip().lower()}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode("ascii").rstrip("=")
    return f"{encoded}.{_digest(secret, f'dialer-session:{version}:{payload}')}"


def read_session(secret: str, cookie: str, version: str, now: float | None = None) -> str:
    """The address a session cookie was issued to, or "" when it is forged, expired or empty."""
    if not secret or "." not in cookie:
        return ""
    encoded, _, signature = cookie.partition(".")
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        expires, _, email = payload.partition(":")
        expires_at = int(expires)
    except (ValueError, UnicodeDecodeError):
        return ""
    if not hmac.compare_digest(_digest(secret, f"dialer-session:{version}:{payload}"), signature):
        return ""
    return email if expires_at > (time.time() if now is None else now) else ""


def load_secret(state_dir: Path) -> str:
    """The signing secret: DIALER_SECRET, else one made on first run and kept in the state folder."""
    configured = read_secret("dialer-secret", "DIALER_SECRET")
    if configured:
        return configured
    path = state_dir / "secret.key"
    for _ in range(2):
        try:
            existing = path.read_text(encoding="utf-8").strip()
        except OSError:
            existing = ""
        if existing:
            return existing
        state_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue  # another process made it a moment ago; read theirs
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_urlsafe(48))
    raise RuntimeError(f"Could not read or create the signing secret at {path}.")


def token_version() -> str:
    return read_secret("dialer-token-version", "DIALER_TOKEN_VERSION") or "1"
