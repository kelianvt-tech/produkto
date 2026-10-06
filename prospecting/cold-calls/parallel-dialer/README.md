# Parallel dialer

A power dialer for outbound sales calls. It works a **Close CRM Smart View**: it rings several
contacts at once through **Twilio**, works out who picked up a person and who picked up a
machine, and puts the first person through to you. Anyone else who also picked up is told you
will call right back, and is called back. You take the call in your browser. Voicemail drops,
call-backs and a talk track on screen are built in.

**It does not schedule meetings or send email.** There is no calendar or mailbox connection in it,
and nothing runs on its own: it places calls only while an operator has a session running.

```
Close Smart View ──► parallel_dialer ──► Twilio ──► up to 10 contacts ring at once
                          ▲                              │ the first person to answer
   your browser  ◄────────┴──────────── "This computer" ◄┘ is put through to you
   (softphone, talk track, notes)
```

It is built around US and Canadian numbers: calling windows and the time-zone wave come from the
area code.

## What you need

| | for | |
|---|---|---|
| **Twilio** account, API key and a voice number | placing the calls; the browser softphone | required |
| **Close CRM** account and API key | the contacts (Smart Views) and logging calls | required |
| **OpenAI** API key | the last-resort call classifier (phrase rules answer most calls first) | required |
| A public **https** address | Twilio calls back to it, and browsers only allow the microphone on https | required to make calls |

Python 3.12 or newer.

## Quick start

```bash
git clone <this repo> parallel-dialer && cd parallel-dialer
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # on Windows: .venv\Scripts\pip

cp .env.example .env                        # fill in what you have; see the comments in it
cp dialer.example.toml dialer.toml          # set your company name, at least
```

Put your address in `DIALER_ALLOWED_EMAILS` in `.env`, then:

```bash
.venv/bin/python -m parallel_dialer access-key you@example.com     # prints your access key
.venv/bin/python -m parallel_dialer                                # starts the server
```

Open <http://127.0.0.1:8767>, sign in with your email and that key, and you are on the dialer.
The header chip says **Locked** and lists what is still missing until everything below is set.

To get further than looking at the page, Twilio has to reach the dialer. While you try it out, a
tunnel does that (`cloudflared tunnel --url http://localhost:8767`, or ngrok). Put the tunnel's
https address in `DIALER_PUBLIC_URL`, restart, and open the dialer at that address: the address
you browse to must be exactly `DIALER_PUBLIC_URL`, or the page's writes are refused.

## Going live

The dialer places real calls to real people, so it does nothing until each of these is set:

1. **Twilio, Close and OpenAI keys** and `DIALER_WEBHOOK_TOKEN` (24+ characters; the command to
   make one is in `.env.example`).
2. **Your company name** in `dialer.toml`. It is spoken to the people you call.
3. **`DIALER_LIVE_MODE=enabled`**, the master switch.
4. **Who it may call**, either of:
   - `DIALER_ALLOWED_TEST_NUMBERS`, a list. Start here with your own mobile and a colleague's,
     put those numbers in a Close Smart View, and run a session to hear how it behaves.
   - `DIALER_UNRESTRICTED=enabled` to call whatever is in the Smart View you pick.
5. **A way to take the call**: "This computer" needs nothing more (it is a Twilio softphone in the
   page; allow the microphone). "My phone" needs `DIALER_OPERATOR_NUMBER`.

Then, on the page: pick a Smart View, record your hello, screening reply and voicemail message
(each is a slot on the page; without a recording the reply is read out by text-to-speech and an
answering machine is hung up on in silence), choose how many lines to run, and press
**Start power session**. `DIALER_BLOCKED_NUMBERS` are never dialed.

**Callbacks.** Give the number people ring back a place to go: `DIALER_CALLBACK_NUMBER` (a Close
Voice number puts the returning call on the lead) or `DIALER_OPERATOR_NUMBER`, then use the
page's *Callback forwarding* button once, which points your Twilio number at
`/twilio/dialer/inbound`.

**Redialing.** When a session starts, a contact who did not reach a person on an earlier session is
left out until 7 days after their last dial, and up to 4 dials in all. Anyone a person answered for
is retired. The history is pooled across operators and Smart Views, so nobody is rung twice by two
people. Nothing is dialed until an operator presses Start.

## Making it yours

Everything a prospect hears that belongs to a company is in **`dialer.toml`**
(`dialer.example.toml` documents every field): the company name, the talk track on the operator's
screen, the reply given to a call screener, and how each operator is named. Operators can also edit
their own talk track on the page; that is saved per operator and wins over `dialer.toml` until they
press **Reset**. A setting the file does not know is refused with a message, so a typo is caught
instead of ignored.

Sign-in, keys and the rest are environment variables (`.env.example`). The page is plain HTML,
CSS and JavaScript in `parallel_dialer/static` and `templates`, with no build step.

**Sign-in.** Each person on `DIALER_ALLOWED_EMAILS` has an access key: an HMAC of the signing
secret with their address. `python -m parallel_dialer access-key EMAIL` prints it and the browser
trades it for a signed, expiring session cookie. Nothing is stored, so rotating `DIALER_SECRET`
or bumping `DIALER_TOKEN_VERSION` signs everyone out and voids every key. The same key works as
`Authorization: Bearer <key>` for an app. To use Google, Okta or a proxy that sets a header
instead, replace `resolve_operator` in `parallel_dialer/api.py`: nothing else knows how anyone
signed in.

**Several operators.** Each signs in as themselves and gets their own Close key (gear icon, or
`CLOSE_API_KEY_<NAME>`), Twilio numbers, recordings, progress and softphone. Without a key of
their own they dial on the shared `CLOSE_API_KEY`, and Close attributes their calls to whoever
owns it. Each address needs a different part before the `@`.

## Deploying

**Docker Compose** (the dialer, and Caddy in front of it for https):

```bash
cp .env.example .env                        # DIALER_PUBLIC_URL=https://dialer.example.com
                                            # DIALER_DOMAIN=dialer.example.com
cp dialer.example.toml config/dialer.toml   # dialer.toml and the files it names live in ./config
docker compose up -d --build
docker compose exec dialer python -m parallel_dialer access-key you@example.com
```

Point the domain's DNS at the machine first; ports 80 and 443 must be open to the internet.

**Linux server, no Docker:** `deploy/parallel-dialer.service` is a hardened systemd unit with the
install steps in its header; `deploy/Caddyfile` is the matching reverse proxy (change the upstream
to `127.0.0.1:8767`).

Either way, **do not restart while a session is running**: it drops the calls in flight. Ask
`GET /dialer/api/status` first and look for `active_session`:

```bash
curl -s -H "Authorization: Bearer $(python -m parallel_dialer access-key you@example.com)" \
  https://dialer.example.com/dialer/api/status
```

## Running it

- **State** is in `DIALER_ROOT` (`./data` by default, a volume in Docker): recordings, dial
  progress, each operator's saved Close and Twilio keys (mode 0600), the signing secret, and a
  `voicemail_feedback.jsonl` of the calls operators flagged as voicemail (names, numbers,
  transcripts). Back it up, and keep it private.
- **Health:** `GET /health` answers `{"status": "ok", "ready": …}` without signing in. `ready` is
  false while any switch above is missing.
- **Behind a proxy** the dialer trusts `X-Forwarded-*` only from `FORWARDED_ALLOW_IPS` (default
  `127.0.0.1`), and keeps idle connections open for 150 s so Caddy and nginx never reuse a dead one.
- **Security headers** (a strict Content-Security-Policy, `X-Frame-Options: DENY`, HSTS on https)
  are set by the dialer itself, so it is safe without a proxy adding them.
- **Logs** go to stdout. Every Twilio callback is signed by the engine (not by Twilio's
  signature), so it is verified whatever hostname the proxy presents.
- **Recordings.** The dialer logs each call to Close with a link to its recording, and serves that
  audio from `/twilio/dialer/call-recording/<recording id>` so Close can play it. That route is
  not behind sign-in: it relies on Twilio's recording id (`RE…`, 32 hex characters) being
  unguessable. Copies you play are cached under `DIALER_ROOT/state/call_recordings`.

## Before you call anyone

Calling strangers is regulated, and that is yours to get right: consent and do-not-call rules
(in the US the TCPA and the national and state registries), calling-hour limits, and who must
agree to a recording. **Every call is recorded through Twilio**, so know what your jurisdictions
require before the first real call. The *Safe hours* toggle on the page (on by default) holds
calls to roughly 8:30 a.m. to 5:30 p.m. in each contact's local time, and the allowlist, block
list and live-mode switch exist so you can test on yourself first.

## Tests

```bash
.venv/bin/python -m pytest -q                                          # no network needed
node --test tests/call_script.test.cjs tests/phone_engine.test.cjs     # the page's scripts
```

The engine's tests run against in-memory fakes of Twilio and Close, so they exercise dialing,
call classification, redial rules, recordings and callbacks without placing a call.

## What is where

| | |
|---|---|
| `parallel_dialer/live_dialer.py` | the engine: sessions, dialing, screening, the operator leg, callbacks |
| `parallel_dialer/dialer.py` | the Close CRM client: Smart Views, contacts, call logging |
| `parallel_dialer/api.py` | the page, the JSON API (`/dialer/api/*`) and Twilio's callbacks (`/twilio/dialer/*`) |
| `parallel_dialer/auth.py`, `config.py`, `profile.py`, `talk_track.py` | sign-in, settings, `dialer.toml`, and each operator's saved talk track |
| `parallel_dialer/timezones.py` | a contact's local time, calling windows and the time-zone wave |
| `parallel_dialer/templates`, `static` | the page, its script, the Twilio softphone SDK, and `phone-engine.*`, a softphone page for a phone app's web view |

Third-party components and their licences: `THIRD_PARTY.md`.
