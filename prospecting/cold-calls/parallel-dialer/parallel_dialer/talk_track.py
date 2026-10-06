"""Each operator's own copy of the talk track.

The deployment's default is in dialer.toml (profile.py). An operator edits their copy on the
page and it is kept here, one entry per operator, so it is on the server as well as in their
browser.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .profile import Profile

LOGGER = logging.getLogger("parallel_dialer.talk_track")


def _path(state_dir: str | Path) -> Path:
    return Path(state_dir) / "talk-tracks.json"


def _read_all(state_dir: str | Path) -> dict[str, str]:
    try:
        data = json.loads(_path(state_dir).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        LOGGER.warning("Could not read the saved talk tracks from %s: %s", _path(state_dir), exc)
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, str)} if isinstance(data, dict) else {}


def load_talk_track(operator_email: str, state_dir: str | Path, profile: Profile) -> str:
    """The operator's saved talk track, or the deployment's own when they have not saved one."""
    saved = _read_all(state_dir).get(operator_email.strip().lower())
    return saved if saved is not None else profile.script_for(operator_email)


def save_talk_track(operator_email: str, script: str, state_dir: str | Path) -> None:
    """Keep the operator's talk track. Written whole and moved into place, so a crash cannot leave half of it."""
    everything = _read_all(state_dir)
    everything[operator_email.strip().lower()] = script
    path = _path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        json.dump(everything, temporary, ensure_ascii=False, indent=2)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(path)
