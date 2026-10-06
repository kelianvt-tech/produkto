"""`python -m parallel_dialer` runs the service.

    python -m parallel_dialer                    start the server
    python -m parallel_dialer access-key EMAIL   print the access key EMAIL signs in with
"""

from __future__ import annotations

import sys


def print_access_key(email: str) -> None:
    from .auth import access_key, load_secret, token_version
    from .config import ConfigError, Settings
    from .profile import ProfileError

    try:
        settings = Settings.load()
    except (ConfigError, ProfileError) as exc:
        sys.exit(f"parallel-dialer: {exc}")
    email = email.strip().lower()
    if email not in settings.allowed_emails:
        print(
            f"parallel-dialer: {email} is not in DIALER_ALLOWED_EMAILS yet, so this key will not "
            "sign in until it is.",
            file=sys.stderr,
        )
    print(access_key(load_secret(settings.state_dir), email, token_version()))


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["access-key"]:
        if len(argv) != 2:
            sys.exit("usage: python -m parallel_dialer access-key EMAIL")
        print_access_key(argv[1])
        return
    if argv:
        sys.exit(f"parallel-dialer: unknown command '{argv[0]}'. Run it with no arguments to start the server.")
    from .api import run

    run()


if __name__ == "__main__":
    main()
