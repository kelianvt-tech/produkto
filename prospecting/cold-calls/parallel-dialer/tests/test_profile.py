"""What makes this deployment its own: the wording in dialer.toml, the settings, the sign-in
secret and the talk track kept for each operator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parallel_dialer import __main__ as cli
from parallel_dialer.auth import access_key, load_secret, match_access_key, read_session, sign_session
from parallel_dialer.config import ConfigError, Settings, clean_operator_identity, read_secret
from parallel_dialer.profile import Profile, ProfileError, fill, load_profile, parse_profile
from parallel_dialer.talk_track import load_talk_track, save_talk_track

ALICE = "alice@example.com"

TOML = """
[brand]
name = "Acme Robotics"

[call]
screening_reply = "Hi, this is {{Operator}} from {{Brand}}, do you have a second to help me?"
script_file = "script.md"

[operators."alice@example.com"]
name = "Alice Ng"
"""


@pytest.fixture
def toml_dir(tmp_path):
    (tmp_path / "script.md").write_text("# Track\n\nHello from {{Brand}}. [Name], meet [My Name].\n", encoding="utf-8")
    (tmp_path / "dialer.toml").write_text(TOML, encoding="utf-8")
    return tmp_path


# --- templates ---


def test_fill_replaces_known_tokens_and_leaves_the_rest():
    text = "Hi {{ Operator }}, {{operator}}, {{Nope}}"
    assert fill(text, {"Operator": "Ada"}) == "Hi Ada, Ada, {{Nope}}"


def test_defaults_are_neutral_and_locked_on_the_brand():
    profile = Profile()
    assert profile.brand_is_set is False
    for text in (profile.script, profile.screening_reply):
        for word in ("Senecta", "fall", "caregiver", "agency", "Spain", "calendar", "invite"):
            assert word not in text, word
    assert profile.operator_name("jane.doe@example.com") == "Jane Doe"
    assert profile.operator_name("") == "Operator"


# --- dialer.toml ---


def test_the_toml_becomes_a_profile(toml_dir):
    profile = load_profile(toml_dir / "dialer.toml")
    assert profile.brand == "Acme Robotics" and profile.brand_is_set is True
    assert "Hello from {{Brand}}" in profile.script  # read from script.md, filled per operator later
    assert profile.operator_name(ALICE) == "Alice Ng"
    # An operator with no entry is named from their address.
    assert profile.operator_name("bob@example.com") == "Bob"


def test_the_script_and_reply_are_filled_for_the_operator(toml_dir):
    profile = load_profile(toml_dir / "dialer.toml")
    page = profile.page_values(ALICE)
    # All the page is told: what is said, in whose name.
    assert set(page) == {"brand", "script", "screening_reply"}
    assert "Hello from Acme Robotics. [Name], meet [My Name]." in page["script"]  # [Name] is the page's to fill
    assert page["screening_reply"] == "Hi, this is Alice Ng from Acme Robotics, do you have a second to help me?"


def test_dialer_toml_is_found_in_the_working_directory(toml_dir, monkeypatch):
    monkeypatch.chdir(toml_dir)
    monkeypatch.delenv("DIALER_CONFIG", raising=False)
    assert load_profile().brand == "Acme Robotics"


def test_no_dialer_toml_means_defaults_but_a_named_missing_one_is_an_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DIALER_CONFIG", raising=False)
    assert load_profile().brand_is_set is False
    monkeypatch.setenv("DIALER_CONFIG", str(tmp_path / "typo.toml"))
    with pytest.raises(ProfileError, match="does not exist"):
        load_profile()


@pytest.mark.parametrize(
    "data, message",
    [
        ({"call": {"screening_reply": "Too short"}}, "screening_reply must be"),
        ({"call": {"screening_reply": "x" * 300}}, "screening_reply must be"),
        ({"call": {"script_file": "missing.md"}}, "Cannot read script_file"),
        ({"call": {"script": "a", "script_file": "b.md"}}, "both script and script_file"),
        ({"operators": {"not-an-email": {}}}, "named by the operator's email"),
        ({"brand": {"name": 5}}, "must be text"),
        ({"brand": "Acme"}, r"\[brand\] must be a table"),
        # A typo is caught rather than ignored
        ({"brand": {"nmae": "Acme"}}, r"\[brand\] nmae is not a setting"),
        ({"brand": {"name": "Acme", "website": "acme.example"}}, r"\[brand\] website is not a setting"),
        ({"operators": {"a@b.example": {"title": "CEO"}}}, "title is not a setting"),
        ({"extras": {}}, r"\[extras\] is not a setting"),
        # What used to be here and is not any more
        ({"calendar": {"invite_title": "x"}}, "does not schedule meetings or send email"),
        ({"email": {"subject": "x"}}, "does not schedule meetings or send email"),
    ],
)
def test_a_bad_dialer_toml_says_what_is_wrong(tmp_path, data, message):
    with pytest.raises(ProfileError, match=message):
        parse_profile(data, tmp_path)


def test_the_brand_placeholder_counts_as_unset(tmp_path):
    assert parse_profile({"brand": {"name": "Your Company"}}, tmp_path).brand_is_set is False
    assert parse_profile({}, tmp_path).brand_is_set is False


# --- each operator's own talk track ---


def test_a_talk_track_is_the_deployments_until_the_operator_saves_their_own(toml_dir):
    profile = load_profile(toml_dir / "dialer.toml")
    state = toml_dir / "state"
    assert load_talk_track(ALICE, state, profile) == profile.script_for(ALICE)
    assert "Hello from Acme Robotics" in load_talk_track(ALICE, state, profile)

    save_talk_track(ALICE, "my own words\nsecond line", state)
    assert load_talk_track(ALICE, state, profile) == "my own words\nsecond line"
    assert load_talk_track("ALICE@example.com ", state, profile) == "my own words\nsecond line"
    # Saved per operator: nobody else's changes.
    assert load_talk_track("bob@example.com", state, profile) == profile.script_for("bob@example.com")
    save_talk_track("bob@example.com", "", state)  # an empty track is a track, not "unset"
    assert load_talk_track("bob@example.com", state, profile) == ""
    assert load_talk_track(ALICE, state, profile) == "my own words\nsecond line"
    # Kept on disk as plain JSON, written whole.
    assert json.loads((state / "talk-tracks.json").read_text(encoding="utf-8"))[ALICE].startswith("my own words")
    assert [path.name for path in state.iterdir()] == ["talk-tracks.json"]


def test_an_unreadable_saved_file_falls_back_to_the_default(toml_dir):
    profile = load_profile(toml_dir / "dialer.toml")
    state = toml_dir / "state"
    state.mkdir()
    (state / "talk-tracks.json").write_text("{not json", encoding="utf-8")
    assert load_talk_track(ALICE, state, profile) == profile.script_for(ALICE)
    # and the next save replaces it with a good one
    save_talk_track(ALICE, "fresh", state)
    assert load_talk_track(ALICE, state, profile) == "fresh"


# --- settings ---


def test_settings_load_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIALER_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("DIALER_PUBLIC_URL", "https://dialer.example.com/")
    monkeypatch.setenv("DIALER_ALLOWED_EMAILS", " Alice@Example.com, bob@example.com  carol@example.com ")
    monkeypatch.setenv("DIALER_SESSION_DAYS", "3")
    settings = Settings.load()
    assert settings.public_base_url == "https://dialer.example.com"
    assert settings.allowed_emails == {ALICE, "bob@example.com", "carol@example.com"}
    assert settings.session_days == 3 and settings.secure_cookies is True
    assert (settings.state_dir.parent.name, settings.state_dir.name) == ("data", "state")
    assert settings.twilio_base_url == "https://dialer.example.com/twilio/dialer"


def test_two_operators_cannot_share_a_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIALER_ALLOWED_EMAILS", "alice@a.example,alice@b.example")
    with pytest.raises(ConfigError, match="share the name 'alice'"):
        Settings.load()


@pytest.mark.parametrize(
    "name, value, message",
    [
        ("DIALER_ALLOWED_EMAILS", "not-an-email", "is not an email address"),
        ("DIALER_PUBLIC_URL", "dialer.example.com", "must start with http"),
        ("DIALER_SESSION_DAYS", "soon", "whole number of days"),
    ],
)
def test_bad_settings_say_what_is_wrong(tmp_path, monkeypatch, name, value, message):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=message):
        Settings.load()


def test_operators_are_told_apart_by_the_part_before_the_at():
    assert clean_operator_identity("Alice.Smith@Example.com") == "alice_smith"
    assert clean_operator_identity("") == "operator"


def test_secrets_come_from_the_environment_a_credential_or_a_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv("CLOSE_API_KEY", raising=False)
    assert read_secret("dialer-close-api-key", "CLOSE_API_KEY") == ""
    (tmp_path / ".env").write_text('# comment\nCLOSE_API_KEY="api_from_dotenv"\n', encoding="utf-8")
    assert read_secret("dialer-close-api-key", "CLOSE_API_KEY") == "api_from_dotenv"
    credentials = tmp_path / "creds"
    credentials.mkdir()
    (credentials / "dialer-close-api-key").write_text("api_from_credential\n", encoding="utf-8")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))
    assert read_secret("dialer-close-api-key", "CLOSE_API_KEY") == "api_from_credential"
    monkeypatch.setenv("CLOSE_API_KEY", "api_from_env")
    assert read_secret("dialer-close-api-key", "CLOSE_API_KEY") == "api_from_env"


# --- the signing secret and sessions ---


def test_the_signing_secret_is_made_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DIALER_SECRET", raising=False)
    state = tmp_path / "state"
    first = load_secret(state)
    assert len(first) >= 48
    assert load_secret(state) == first
    assert (state / "secret.key").read_text(encoding="utf-8").strip() == first
    monkeypatch.setenv("DIALER_SECRET", "chosen-by-the-operator")
    assert load_secret(state) == "chosen-by-the-operator"


def test_sessions_carry_their_address_and_expire():
    secret = "s" * 40
    cookie = sign_session(secret, "Alice@Example.com", "1", 2_000_000_000)
    assert read_session(secret, cookie, "1", now=1_900_000_000) == ALICE
    assert read_session(secret, cookie, "1", now=2_000_000_001) == ""  # expired
    assert read_session(secret, cookie, "2", now=1_900_000_000) == ""  # the version was bumped
    assert read_session("t" * 40, cookie, "1", now=1_900_000_000) == ""
    assert read_session(secret, "", "1") == "" and read_session("", cookie, "1") == ""
    encoded, _, signature = cookie.partition(".")
    assert read_session(secret, f"{encoded}x.{signature}", "1", now=1_900_000_000) == ""


def test_an_access_key_matches_only_its_own_operator():
    secret = "s" * 40
    emails = frozenset({ALICE, "bob@example.com"})
    key = access_key(secret, ALICE)
    assert match_access_key(secret, key, emails) == ALICE
    assert match_access_key(secret, f"  {key}\n", emails) == ALICE
    assert match_access_key(secret, key, frozenset({"bob@example.com"})) == ""
    assert match_access_key(secret, "", emails) == ""
    assert match_access_key("", key, emails) == ""


# --- the command line ---


def test_the_access_key_command_prints_the_key_the_server_will_accept(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DIALER_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("DIALER_ALLOWED_EMAILS", ALICE)
    monkeypatch.delenv("DIALER_SECRET", raising=False)
    cli.main(["access-key", "Alice@Example.com"])
    printed = capsys.readouterr()
    key = printed.out.strip()
    assert printed.err == ""
    assert key == access_key(load_secret(tmp_path / "data" / "state"), ALICE)
    # An address that is not on the list still gets a key, with a warning that it will not work yet.
    cli.main(["access-key", "carol@example.com"])
    assert "not in DIALER_ALLOWED_EMAILS" in capsys.readouterr().err


def test_the_command_line_says_what_it_does_not_understand(capsys):
    with pytest.raises(SystemExit, match="usage: python -m parallel_dialer access-key EMAIL"):
        cli.main(["access-key"])
    with pytest.raises(SystemExit, match="unknown command 'serve'"):
        cli.main(["serve"])


def test_nothing_private_ships_in_the_package():
    root = Path(__file__).resolve().parents[1]
    forbidden = ("senecta", "marcos", "mauro", "junca", "bluestaff", "taleva", "company-brain")
    for path in [*root.glob("parallel_dialer/**/*"), *root.glob("tests/*.py"), *root.glob("*.md"), *root.glob("*.toml")]:
        if not path.is_file() or path.suffix in {".woff2", ".pyc"} or path.name == "twilio-voice-2.18.5.js":
            continue
        if path.name in {"test_profile.py", "test_page.py"}:
            continue  # these two name the words on purpose
        text = path.read_text(encoding="utf-8").lower()
        for word in forbidden:
            assert word not in text, f"{word!r} in {path.relative_to(root)}"


# --- the files a new user starts from ---


def test_the_example_config_is_valid_and_keeps_the_dialer_locked():
    root = Path(__file__).resolve().parents[1]
    profile = load_profile(root / "dialer.example.toml")
    # Copied unedited it must not go live under a placeholder name.
    assert profile.brand_is_set is False
    assert profile.operator_name("you@example.com") == "Your Name"
    assert "THE OPENER" in profile.script
    assert "{{" not in profile.script_for("you@example.com")


def test_every_setting_the_code_reads_is_in_the_env_example():
    import re

    root = Path(__file__).resolve().parents[1]
    documented = (root / ".env.example").read_text(encoding="utf-8")
    read = set()
    for path in (root / "parallel_dialer").rglob("*.py"):
        read |= set(re.findall(r'read_secret\(\s*"[^"]+",\s*"([A-Z][A-Z0-9_]+)"', path.read_text(encoding="utf-8")))
    # Advanced switches for other classifier providers and a streaming worker: in the code, not the guide.
    advanced = {
        "DIALER_MODE", "DIALER_VOICE_IDENTITY", "DIALER_STREAM_WORKER_URL",
        "TYPESAFE_API_KEY", "TYPESAFE_MODEL",
        "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_AI_MODEL",
        "FORWARDED_ALLOW_IPS",
    }
    missing = sorted(name for name in read - advanced if name not in documented)
    assert not missing, f"read by the code but not in .env.example: {missing}"
    assert {"DIALER_ALLOWED_EMAILS", "TWILIO_ACCOUNT_SID", "CLOSE_API_KEY", "OPENAI_API_KEY"} <= read
