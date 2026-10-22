#!/usr/bin/env python3
"""Produkto LinkedIn agent.

Sends connection requests to founders from our Apollo lead lists, then two
follow-up messages after they accept. It works inside Kelian's own Chrome
(through AppleScript), so LinkedIn sees his normal browser and home internet.

Standard library only. Run `python3 linkedin_agent.py help` for commands.

Data lives in ~/Library/Application Support/ProduktoLinkedIn/ (outside Desktop,
so the scheduled job can read it without Full Disk Access).
"""
import csv
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

HOME = Path.home() / "Library" / "Application Support" / "ProduktoLinkedIn"
DB_PATH = HOME / "agent.db"
SETTINGS_PATH = HOME / "settings.json"
PAUSE_PATH = HOME / "PAUSED"
LOCK_PATH = HOME / "run.lock"
LOG_PATH = HOME / "agent.log"
PLIST_NAME = "com.produkto.linkedin"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_NAME}.plist"

DEFAULT_SETTINGS = {
    # Safety limits. LinkedIn allows roughly 100-200 requests a week per account.
    "daily_invites": 40,
    "weekly_invites": 200,
    "send_messages": False,       # connection requests only until Kelian turns this on
    "daily_messages": 30,
    "max_actions_per_run": 3,
    # Sends only inside these hours, on these days (0 = Monday ... 6 = Sunday).
    "timezone": "Europe/Madrid",
    "days": [0, 1, 2, 3, 4],
    "start_hour": 9,
    "end_hour": 17,
    "skip_chance": 0.15,          # sometimes do nothing, like a person
    "msg1_delay_hours": 2,        # wait after they accept before message 1
    "msg2_delay_days": 4,         # wait after message 1 before message 2
    "check_connections_every_hours": 3,
    # {first} {company} {niche} are filled in per lead.
    "msg1": (
        "Thanks for connecting, {first}. I run Produkto: we check which products "
        "AI assistants like ChatGPT recommend when shoppers ask about {niche}, "
        "and where {company} shows up.\n\n"
        "Want me to run a free check of {company} and send you the results? "
        "Just reply \"yes\"."
    ),
    "msg2": (
        "Hi {first}, bumping this in case it got buried. Happy to run that free "
        "check for {company} and send it over, no call needed. Just reply \"yes\"."
    ),
}

TITLE_RANK = [
    (r"founder|owner|ceo|chief executive|president", 0),
    (r"chief marketing|cmo|head of (e-?commerce|marketing|growth|digital)|vp", 1),
    (r"marketing|e-?commerce|growth|digital", 2),
    (r"coo|chief operating|general manager", 3),
]


# ---------------------------------------------------------------- basics

def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if s else None


def log(msg):
    HOME.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def notify(msg):
    subprocess.run(["osascript", "-e",
                    f'display notification {json.dumps(msg)} with title "Produkto LinkedIn agent"'],
                   capture_output=True)


def settings():
    HOME.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(json.dumps(DEFAULT_SETTINGS, indent=2))
    s = dict(DEFAULT_SETTINGS)
    s.update(json.loads(SETTINGS_PATH.read_text()))
    return s


def db():
    HOME.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        slug TEXT PRIMARY KEY, url TEXT, first TEXT, last TEXT, company TEXT,
        title TEXT, email TEXT, niche TEXT, rank INTEGER, source TEXT,
        status TEXT DEFAULT 'new', note TEXT,
        added_at TEXT, invited_at TEXT, connected_at TEXT,
        msg1_at TEXT, msg2_at TEXT, replied_at TEXT
    );
    CREATE TABLE IF NOT EXISTS events (
        at TEXT, slug TEXT, kind TEXT, detail TEXT
    );
    CREATE TABLE IF NOT EXISTS state (k TEXT PRIMARY KEY, v TEXT);
    """)
    return con


def event(con, slug, kind, detail=""):
    con.execute("INSERT INTO events VALUES (?,?,?,?)", (iso(now()), slug, kind, detail))
    con.commit()


def get_state(con, k):
    r = con.execute("SELECT v FROM state WHERE k=?", (k,)).fetchone()
    return r["v"] if r else None


def set_state(con, k, v):
    con.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (k, v))
    con.commit()


def count_since(con, kind, since):
    return con.execute("SELECT COUNT(*) FROM events WHERE kind=? AND at>=?",
                       (kind, iso(since))).fetchone()[0]


def slug_of(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "", re.I)
    return urllib.parse.unquote(m.group(1)).strip().lower() if m else None


def pause(reason):
    HOME.mkdir(parents=True, exist_ok=True)
    PAUSE_PATH.write_text(f"{iso(now())} {reason}\n")
    log(f"PAUSED: {reason}")
    notify(f"Paused: {reason}. Run 'resume' when it's sorted.")


# ---------------------------------------------------------------- Chrome

class ChromeError(Exception):
    pass


class Chrome:
    """Drives one dedicated tab in Kelian's real Chrome through AppleScript."""

    def __init__(self, con):
        self.con = con
        self.tab_id = get_state(con, "tab_id")

    def _osa(self, script):
        try:
            r = subprocess.run(["osascript", "-"], input=script, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            # Usually the Mac's "python3 wants to control Google Chrome" prompt waiting for a click.
            notify("Waiting on Chrome. If a Mac prompt asks to let python3 control Google Chrome, click OK.")
            raise ChromeError("Chrome didn't answer within 90s (Mac permission prompt waiting?)")
        if r.returncode != 0:
            err = r.stderr.strip()
            if "Apple Events" in err or "turned off" in err:
                raise ChromeError("Chrome setting off: View > Developer > Allow JavaScript from Apple Events")
            raise ChromeError(err)
        return r.stdout.strip()

    def _find_tab(self):
        return f"""
        set found to missing value
        repeat with w in windows
            repeat with t in tabs of w
                if (id of t as text) is "{self.tab_id}" then set found to t
            end repeat
        end repeat
        """

    def ensure_tab(self):
        if self.tab_id:
            ok = self._osa(f'tell application "Google Chrome"\n{self._find_tab()}\n'
                           'if found is missing value then return "no"\nreturn "yes"\nend tell')
            if ok == "yes":
                return
        # Its own window, so it never takes over a tab Kelian is using.
        # Puts Kelian's own window back in front afterwards so he isn't pulled away.
        tid = self._osa('tell application "Google Chrome"\n'
                        'set prev to missing value\n'
                        'if (count of windows) > 0 then set prev to front window\n'
                        'set w to make new window\n'
                        'if prev is not missing value then set index of prev to 1\n'
                        'set URL of active tab of w to "https://www.linkedin.com/feed/"\n'
                        'return id of active tab of w as text\nend tell')
        self.tab_id = tid
        set_state(self.con, "tab_id", tid)
        time.sleep(6)

    def front_window(self):
        """Id of the Chrome window Kelian is looking at, or "" if none."""
        return self._osa('tell application "Google Chrome"\n'
                         'if (count of windows) = 0 then return ""\n'
                         'return id of front window as text\nend tell')

    def restore_front(self, win_id):
        """If the agent's window jumped in front of Kelian's, put his back on top."""
        if not win_id:
            return
        self._osa('tell application "Google Chrome"\n'
                  f'if (id of front window as text) is not "{win_id}" then\n'
                  'repeat with w in windows\n'
                  f'if (id of w as text) is "{win_id}" then set index of w to 1\n'
                  'end repeat\nend if\nend tell')

    def goto(self, url):
        self.ensure_tab()
        # Navigate from inside the page: AppleScript's "set URL" pulls the agent's
        # window in front of whatever Kelian is doing in Chrome; this doesn't.
        try:
            ok = self.js(f"location.href = {json.dumps(url)}; 'ok'") == "ok"
        except ChromeError:
            ok = False
        if not ok:  # e.g. the tab is on a chrome:// page where JS can't run
            prev = self.front_window()
            self._osa(f'tell application "Google Chrome"\n{self._find_tab()}\n'
                      f'set URL of found to {json.dumps(url)}\nend tell')
            self.restore_front(prev)
        time.sleep(3)
        for _ in range(30):
            if self.js("document.readyState") == "complete":
                break
            time.sleep(1)
        time.sleep(random.uniform(3, 6))
        self.guard()

    def js(self, code):
        """Runs JS in the tab and returns its result as text."""
        self.ensure_tab()
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(code)
            path = f.name
        try:
            return self._osa(f'tell application "Google Chrome"\n{self._find_tab()}\n'
                             f'return (execute found javascript (read POSIX file "{path}" as «class utf8»))\n'
                             'end tell')
        finally:
            os.unlink(path)

    def jsj(self, body):
        """Runs a JS function body and returns its result parsed from JSON."""
        out = self.js(f"JSON.stringify((function(){{ {body} }})())")
        try:
            return json.loads(out) if out else None
        except ValueError:
            return None

    def guard(self):
        """Stops everything if LinkedIn shows a login wall, a security check or a restriction."""
        info = self.jsj("return {u: location.href, t: (document.body ? document.body.innerText : '').slice(0, 3000)};") or {}
        u, t = info.get("u", ""), info.get("t", "")
        if re.search(r"/checkpoint/|/authwall|/login|/uas/|/challenge", u):
            pause(f"LinkedIn asked for a login or security check ({u.split('?')[0]})")
            raise ChromeError("stopped: security check")
        if re.search(r"unusual activity|account (has been )?restricted|temporarily restricted", t, re.I):
            pause("LinkedIn showed a restriction / unusual-activity warning")
            raise ChromeError("stopped: restriction warning")


# JS snippets (function bodies). LinkedIn's class names are hashed, so these
# match on links, labels and visible text instead.
JS_PROFILE = r"""
const main = document.querySelector('main') || document.body;
const t = main.innerText || '';
const top = t.split('\nAbout\n')[0].slice(0, 2500);
const deg = (top.match(/·\s*(1st|2nd|3rd\+?)/) || [])[1] || null;
const gone = /this page doesn.t exist|profile is not available|page not found/i.test(t.slice(0, 2000));
const pending = /\bPending\b/.test(top) || !!document.querySelector('[aria-label^="Pending"]');
return {deg, gone, pending, url: location.href};
"""


def js_click_connect(slug):
    return r"""
const want = %s;
const norm = s => { try { return decodeURIComponent(s).toLowerCase(); } catch (e) { return (s||'').toLowerCase(); } };
const a = [...document.querySelectorAll('a[href*="custom-invite"]')].find(x => {
    const m = (x.getAttribute('href') || '').match(/vanityName=([^&]+)/);
    return m && norm(m[1]) === want;
});
if (!a) {
    const more = [...(document.querySelector('main') || document).querySelectorAll('button[aria-label="More"]')]
        .find(b => b.offsetParent !== null);
    if (!more) return {ok: false, why: 'no More button'};
    more.click();
    return {ok: false, why: 'opened menu', retry: true};
}
a.click();
return {ok: true};
""" % json.dumps(slug)


JS_INVITE_DIALOG = r"""
const d = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')].find(x => x.getClientRects().length > 0 && (x.innerText || '').trim());
if (!d) return {dialog: false};
const txt = d.innerText || '';
if (/enter (their|the member.s) email|knows you/i.test(txt)) return {dialog: true, email: true};
const btns = [...d.querySelectorAll('button, a[role="button"]')];
const label = b => ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).trim();
const send = btns.find(b => /send without a note/i.test(label(b)))
          || btns.find(b => /^send( now| invitation)?$/i.test((b.innerText || '').trim()));
return {dialog: true, email: false, send: send ? label(send) : null, text: txt.slice(0, 300)};
"""

JS_INVITE_SEND = r"""
const d = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')].find(x => x.getClientRects().length > 0 && (x.innerText || '').trim());
if (!d) return {ok: false, why: 'no dialog'};
const btns = [...d.querySelectorAll('button, a[role="button"]')];
const label = b => ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).trim();
const send = btns.find(b => /send without a note/i.test(label(b)))
          || btns.find(b => /^send( now| invitation)?$/i.test((b.innerText || '').trim()));
if (!send) return {ok: false, why: 'no send button'};
send.click();
return {ok: true};
"""

JS_AFTER_INVITE = r"""
const t = document.body.innerText || '';
return {
  limit: /weekly invitation limit|reached the weekly limit|you.ve reached the (weekly )?limit|invitation limit/i.test(t),
  pending: /\bPending\b/.test(t.split('\nAbout\n')[0]),
  sent: /invitation sent/i.test(t)
};
"""

JS_CLOSE_DIALOG = r"""
const d = [...document.querySelectorAll('[role="dialog"]')].find(x => x.getClientRects().length > 0 && (x.innerText || '').trim());
if (d) { const c = [...d.querySelectorAll('button')].find(b => /dismiss|close|cancel/i.test(b.getAttribute('aria-label') || b.innerText)); if (c) c.click(); }
document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
return true;
"""

JS_OPEN_MESSAGE = r"""
const main = document.querySelector('main') || document;
const m = [...main.querySelectorAll('a, button')].find(e => (e.innerText || '').trim() === 'Message' && e.offsetParent !== null);
if (!m) return {ok: false};
m.click();
return {ok: true};
"""

JS_THREAD = r"""
const boxes = [...document.querySelectorAll('[contenteditable="true"][role="textbox"], div[contenteditable="true"]')].filter(b => b.offsetParent !== null);
const box = boxes[boxes.length - 1];
if (!box) return {box: false};
let c = box;
for (let i = 0; i < 12 && c.parentElement; i++) { c = c.parentElement; if ((c.innerText || '').length > 200 && c.querySelector('ul, ol')) break; }
const items = c.querySelectorAll('[class*="msg-s-event-listitem"], [data-event-urn], li[class*="message"]');
return {box: true, items: items.length, text: (c.innerText || '').slice(-4000)};
"""


def js_type(text):
    return r"""
const boxes = [...document.querySelectorAll('[contenteditable="true"][role="textbox"], div[contenteditable="true"]')].filter(b => b.offsetParent !== null);
const box = boxes[boxes.length - 1];
if (!box) return {ok: false, why: 'no message box'};
box.focus();
%s.split('\n').forEach((line, i) => {
  if (i > 0) document.execCommand('insertParagraph');
  if (line) document.execCommand('insertText', false, line);
});
return {ok: true, typed: (box.innerText || '').length};
""" % json.dumps(text)


JS_PRESS_SEND = r"""
const boxes = [...document.querySelectorAll('[contenteditable="true"][role="textbox"], div[contenteditable="true"]')].filter(b => b.offsetParent !== null);
let el = boxes[boxes.length - 1];
for (let i = 0; i < 10 && el; i++) {
  const s = el.querySelectorAll ? [...el.querySelectorAll('button')].find(b => /^send$/i.test((b.innerText || '').trim()) || b.type === 'submit') : null;
  if (s) { if (s.disabled) return {ok: false, why: 'send disabled'}; s.click(); return {ok: true}; }
  el = el.parentElement;
}
return {ok: false, why: 'no send button'};
"""

JS_BOX_EMPTY = r"""
const boxes = [...document.querySelectorAll('[contenteditable="true"][role="textbox"], div[contenteditable="true"]')].filter(b => b.offsetParent !== null);
const box = boxes[boxes.length - 1];
return {empty: !box || (box.innerText || '').trim().length === 0};
"""

JS_CLOSE_CHAT = r"""
[...document.querySelectorAll('button')].filter(b => /close your conversation|close conversation/i.test(b.getAttribute('aria-label') || '')).forEach(b => b.click());
return true;
"""

JS_CONNECTIONS = r"""
return [...new Set([...document.querySelectorAll('main a[href*="/in/"]')].map(a => (a.getAttribute('href') || '').split('?')[0]))];
"""


# ---------------------------------------------------------------- actions

def fill(template, lead):
    first = (lead["first"] or "").strip().split(" ")[0] or "there"
    return template.format(first=first, company=lead["company"] or "your brand",
                           niche=lead["niche"] or "your category")


def mark(con, slug, status, note, invited=False):
    if invited:
        con.execute("UPDATE leads SET status=?, note=?, invited_at=COALESCE(invited_at, ?) WHERE slug=?",
                    (status, note, iso(now()), slug))
    else:
        con.execute("UPDATE leads SET status=?, note=? WHERE slug=?", (status, note, slug))
    con.commit()
    log(f"  {slug}: {status}{' (' + note + ')' if note else ''}")


def hit_limit(con):
    set_state(con, "invites_blocked_until", iso(now() + timedelta(days=7)))
    log("LinkedIn says the weekly invitation limit is reached. Invites stop for 7 days; messages continue.")
    notify("Weekly LinkedIn invite limit reached. Invites paused for 7 days.")


def do_invite(chrome, con, lead, s, live):
    slug = lead["slug"]
    chrome.goto(f"https://www.linkedin.com/in/{urllib.parse.quote(slug)}/")
    p = chrome.jsj(JS_PROFILE) or {}
    if p.get("gone"):
        return mark(con, slug, "skipped", "profile not found")
    if p.get("deg") == "1st":
        con.execute("UPDATE leads SET status='connected', connected_at=? WHERE slug=?", (iso(now()), slug))
        con.commit()
        event(con, slug, "already_connected")
        return log(f"  {slug}: already connected")
    if p.get("pending"):
        return mark(con, slug, "invited", "already pending", invited=True)

    # A scripted click on "Connect" doesn't open the invite window, but its
    # link target does: the same page LinkedIn opens from the More menu.
    time.sleep(random.uniform(4, 10))  # "reads" the profile first
    chrome.goto(f"https://www.linkedin.com/preload/custom-invite/?vanityName={urllib.parse.quote(slug)}")
    time.sleep(random.uniform(1, 2))

    d = chrome.jsj(JS_INVITE_DIALOG) or {}
    if not d.get("dialog"):
        a = chrome.jsj(JS_AFTER_INVITE) or {}
        if a.get("limit"):
            return hit_limit(con)
        if a.get("pending") or a.get("sent"):  # some profiles send in one click
            event(con, slug, "invite", "one-click")
            return mark(con, slug, "invited", "one-click", invited=True)
        return mark(con, slug, "skipped", "no invite window (follow-only or restricted profile)")
    if d.get("email"):
        chrome.jsj(JS_CLOSE_DIALOG)
        return mark(con, slug, "skipped", "LinkedIn wants their email to connect")
    if not d.get("send"):
        chrome.jsj(JS_CLOSE_DIALOG)
        return mark(con, slug, "error", f"no send button in dialog: {d.get('text', '')[:120]}")

    if not live:
        log(f"  DRY RUN: found '{d['send']}' for {slug}. Closed without sending.")
        chrome.jsj(JS_CLOSE_DIALOG)
        return
    chrome.jsj(JS_INVITE_SEND)
    time.sleep(random.uniform(2.5, 4))
    a = chrome.jsj(JS_AFTER_INVITE) or {}
    if a.get("limit"):
        return hit_limit(con)
    event(con, slug, "invite")
    mark(con, slug, "invited", "", invited=True)


def check_connections(chrome, con):
    chrome.goto("https://www.linkedin.com/mynetwork/invite-connect/connections/")
    time.sleep(3)
    slugs = {slug_of(l) for l in (chrome.jsj(JS_CONNECTIONS) or [])} - {None}
    n = 0
    for sl in slugs:
        row = con.execute("SELECT status FROM leads WHERE slug=?", (sl,)).fetchone()
        if row and row["status"] in ("invited", "new", "skipped"):
            con.execute("UPDATE leads SET status='connected', connected_at=? WHERE slug=?", (iso(now()), sl))
            event(con, sl, "accepted")
            n += 1
    con.commit()
    set_state(con, "last_connections_check", iso(now()))
    log(f"  connections check: {len(slugs)} recent, {n} new accepts from our leads")


def thread_has_other_messages(thread, my_text):
    """True when the conversation holds anything besides our own message."""
    text = thread.get("text", "")
    if my_text:
        tail = my_text.strip()[-40:]
        i = text.rfind(tail)
        if i == -1:
            return True  # can't find our message: don't risk a double message
        after = re.sub(r"(Seen|Sent|Delivered|Write a message…?|Press Enter to send|\d{1,2}:\d{2}\s?[AP]M|Today|Yesterday|\s)+",
                       " ", text[i + len(tail):])
        return len(after.strip()) > 25
    return thread.get("items", 0) > 0


def do_message(chrome, con, lead, which, s, live):
    slug = lead["slug"]
    chrome.goto(f"https://www.linkedin.com/in/{urllib.parse.quote(slug)}/")
    p = chrome.jsj(JS_PROFILE) or {}
    if p.get("deg") != "1st":
        return log(f"  {slug}: not shown as connected yet, message waits")
    if not (chrome.jsj(JS_OPEN_MESSAGE) or {}).get("ok"):
        return mark(con, slug, "error", "no Message button")
    time.sleep(random.uniform(3, 5))
    thread = chrome.jsj(JS_THREAD) or {}
    if not thread.get("box"):
        chrome.jsj(JS_CLOSE_CHAT)
        return mark(con, slug, "error", "message box did not open")

    msg1 = fill(s["msg1"], lead)
    if which == 1 and thread_has_other_messages(thread, None):
        chrome.jsj(JS_CLOSE_CHAT)
        return mark(con, slug, "manual", "conversation already has messages: reply yourself")
    if which == 2 and thread_has_other_messages(thread, msg1):
        chrome.jsj(JS_CLOSE_CHAT)
        con.execute("UPDATE leads SET replied_at=? WHERE slug=?", (iso(now()), slug))
        event(con, slug, "replied")
        return mark(con, slug, "replied", "they replied: answer in LinkedIn")

    text = msg1 if which == 1 else fill(s["msg2"], lead)
    if not live:
        log(f"  DRY RUN: would send message {which} to {slug}:\n    " + text.replace("\n", "\n    "))
        chrome.jsj(JS_CLOSE_CHAT)
        return
    r = chrome.jsj(js_type(text)) or {}
    if not r.get("ok"):
        chrome.jsj(JS_CLOSE_CHAT)
        return mark(con, slug, "error", f"could not type: {r.get('why')}")
    time.sleep(random.uniform(1.5, 3))
    r = chrome.jsj(JS_PRESS_SEND) or {}
    time.sleep(2.5)
    if not r.get("ok") or not (chrome.jsj(JS_BOX_EMPTY) or {}).get("empty"):
        chrome.jsj(JS_CLOSE_CHAT)
        return mark(con, slug, "error",
                    f"message {which} may not have sent ({r.get('why', 'box not empty')}): check by hand")
    col = "msg1_at" if which == 1 else "msg2_at"
    con.execute(f"UPDATE leads SET status=?, {col}=? WHERE slug=?", (f"msg{which}", iso(now()), slug))
    con.commit()
    event(con, slug, f"msg{which}")
    log(f"  {slug}: message {which} sent")
    time.sleep(1)
    chrome.jsj(JS_CLOSE_CHAT)


# ---------------------------------------------------------------- the run

def in_window(s):
    tz = ZoneInfo(s["timezone"]) if ZoneInfo else timezone(timedelta(hours=-4))
    t = datetime.now(tz)
    return t.weekday() in s.get("days", [0, 1, 2, 3, 4]) and s["start_hour"] <= t.hour < s["end_hour"]


def next_action(con, s):
    n = now()
    last = parse(get_state(con, "last_connections_check"))
    if not last or n - last > timedelta(hours=s["check_connections_every_hours"]):
        return ("connections", None)

    day = n - timedelta(hours=24)
    if s["send_messages"] and count_since(con, "msg1", day) + count_since(con, "msg2", day) < s["daily_messages"]:
        due2 = con.execute("SELECT * FROM leads WHERE status='msg1' AND msg1_at<=? ORDER BY msg1_at LIMIT 1",
                           (iso(n - timedelta(days=s["msg2_delay_days"])),)).fetchone()
        if due2:
            return ("msg2", due2)
        due1 = con.execute("SELECT * FROM leads WHERE status='connected' AND connected_at<=? ORDER BY connected_at LIMIT 1",
                           (iso(n - timedelta(hours=s["msg1_delay_hours"])),)).fetchone()
        if due1:
            return ("msg1", due1)

    blocked = parse(get_state(con, "invites_blocked_until"))
    if blocked and blocked > n:
        return (None, None)
    if count_since(con, "invite", day) >= s["daily_invites"]:
        return (None, None)
    if count_since(con, "invite", n - timedelta(days=7)) >= s["weekly_invites"]:
        return (None, None)
    lead = con.execute("SELECT * FROM leads WHERE status='new' ORDER BY rank, added_at LIMIT 1").fetchone()
    return ("invite", lead) if lead else (None, None)


def run(live=True, force=False):
    s = settings()
    if PAUSE_PATH.exists():
        return print(f"Paused: {PAUSE_PATH.read_text().strip()}  (run 'resume' to continue)")
    if not force and not in_window(s):
        return
    if LOCK_PATH.exists() and time.time() - LOCK_PATH.stat().st_mtime < 1800:
        return  # another round is still going
    LOCK_PATH.write_text(str(os.getpid()))
    try:
        con = db()
        if not force:
            if random.random() < s["skip_chance"]:
                return
            time.sleep(random.uniform(0, 240))
        chrome = Chrome(con)
        for _ in range(s["max_actions_per_run"]):
            kind, lead = next_action(con, s)
            if not kind:
                break
            log(f"{'LIVE' if live else 'DRY'} {kind}{' ' + lead['slug'] if lead else ''}")
            try:
                if kind == "connections":
                    check_connections(chrome, con)
                elif kind == "invite":
                    do_invite(chrome, con, lead, s, live)
                elif kind in ("msg1", "msg2"):
                    do_message(chrome, con, lead, int(kind[-1]), s, live)
            except ChromeError as e:
                log(f"  stopped: {e}")
                if "Apple Events" in str(e):
                    notify(str(e))
                break
            if not live and kind != "connections":
                break  # a dry run changes nothing, so the same lead would come up again
            time.sleep(random.uniform(40, 150))
    finally:
        LOCK_PATH.unlink(missing_ok=True)


# ---------------------------------------------------------------- commands

def cmd_import(args):
    if not args:
        sys.exit('usage: import <apollo.csv> --niche "coffee and tea" [--only-emails-in cleaned.csv]')
    path = args[0]
    niche = args[args.index("--niche") + 1] if "--niche" in args else ""
    only = None
    if "--only-emails-in" in args:
        with open(args[args.index("--only-emails-in") + 1], newline="", encoding="utf-8-sig") as f:
            only = {(r.get("Email") or r.get("email") or "").strip().lower() for r in csv.DictReader(f)}
    con = db()
    added = dup = nourl = filtered = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            url = r.get("Person Linkedin Url") or r.get("linkedin_url") or r.get("LinkedIn") or ""
            sl = slug_of(url)
            if not sl:
                nourl += 1
                continue
            email = (r.get("Email") or r.get("email") or "").strip().lower()
            if only is not None and email not in only:
                filtered += 1
                continue
            title = r.get("Title") or r.get("title") or ""
            rank = next((v for pat, v in TITLE_RANK if re.search(pat, title, re.I)), 9)
            company = (r.get("Company Name for Emails") or r.get("Company Name") or r.get("company_name") or "").strip()
            cur = con.execute(
                "INSERT OR IGNORE INTO leads (slug,url,first,last,company,title,email,niche,rank,source,added_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sl, url, r.get("First Name") or r.get("first_name") or "", r.get("Last Name") or r.get("last_name") or "",
                 company, title, email, niche, rank, os.path.basename(path), iso(now())))
            if cur.rowcount:
                added += 1
            else:
                dup += 1
    con.commit()
    print(f"Added {added}. Already in the list: {dup}. No LinkedIn URL: {nourl}. Not in the cleaned file: {filtered}.")


def cmd_status(args):
    con = db()
    s = settings()
    n = now()
    print("Paused:", PAUSE_PATH.read_text().strip() if PAUSE_PATH.exists() else "no")
    print("Inside sending hours now:", "yes" if in_window(s) else "no")
    print("Scheduled job installed:", "yes" if PLIST_PATH.exists() else "no")
    print("Follow-up messages:", "on" if s["send_messages"] else "off (connection requests only)")
    print()
    for row in con.execute("SELECT status, COUNT(*) c FROM leads GROUP BY status ORDER BY c DESC"):
        print(f"  {row['status']:<10} {row['c']}")
    sent = con.execute("SELECT COUNT(*) FROM leads WHERE invited_at IS NOT NULL").fetchone()[0]
    acc = con.execute("SELECT COUNT(*) FROM leads WHERE invited_at IS NOT NULL AND connected_at IS NOT NULL").fetchone()[0]
    rep = con.execute("SELECT COUNT(*) FROM leads WHERE replied_at IS NOT NULL").fetchone()[0]
    print()
    print(f"Invites last 24h: {count_since(con, 'invite', n - timedelta(hours=24))}/{s['daily_invites']}"
          f"   last 7 days: {count_since(con, 'invite', n - timedelta(days=7))}/{s['weekly_invites']}")
    print(f"Accepted: {acc}/{sent} ({(100 * acc / sent) if sent else 0:.0f}%)   Replied: {rep}")
    todo = con.execute("SELECT first,last,company,slug,note FROM leads WHERE status IN ('replied','manual','error')").fetchall()
    if todo:
        print("\nNeeds you (answer in LinkedIn, or check the error):")
        for m in todo:
            print(f"  {m['first']} {m['last']} ({m['company']})  linkedin.com/in/{m['slug']}  {m['note'] or ''}")


def cmd_export(args):
    out = args[0] if args else "linkedin-log.csv"
    rows = db().execute("SELECT * FROM leads ORDER BY added_at").fetchall()
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        if rows:
            w.writerow(rows[0].keys())
        for r in rows:
            w.writerow(list(r))
    print(f"Wrote {len(rows)} rows to {out}")


def cmd_test(args):
    """Dry run on one lead: opens the profile and the invite window, then closes it without sending."""
    con = db()
    s = settings()
    if args:
        sl = slug_of(args[0]) or args[0].lower()
        lead = con.execute("SELECT * FROM leads WHERE slug=?", (sl,)).fetchone()
        if not lead:
            sys.exit("That lead isn't in the list. Import it first.")
    else:
        lead = con.execute("SELECT * FROM leads WHERE status='new' ORDER BY rank LIMIT 1").fetchone()
        if not lead:
            sys.exit("No new leads. Import some first.")
    print(f"Testing on {lead['first']} {lead['last']} ({lead['company']})")
    try:
        do_invite(Chrome(con), con, lead, s, live=False)
    except ChromeError as e:
        print(f"Stopped: {e}")


def cmd_send_one(args):
    """Sends ONE real connection request now, so the first live send happens with you watching."""
    con = db()
    s = settings()
    lead = con.execute("SELECT * FROM leads WHERE status='new' ORDER BY rank LIMIT 1").fetchone()
    if not lead:
        sys.exit("No new leads.")
    print(f"Sending a real connection request to {lead['first']} {lead['last']} ({lead['company']})")
    try:
        do_invite(Chrome(con), con, lead, s, live=True)
    except ChromeError as e:
        print(f"Stopped: {e}")


def cmd_install(args):
    HOME.mkdir(parents=True, exist_ok=True)
    target = HOME / "linkedin_agent.py"
    target.write_text(Path(__file__).read_text())
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{PLIST_NAME}</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string><string>{target}</string><string>run</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>StandardOutPath</key><string>{HOME}/launchd.out</string>
  <key>StandardErrorPath</key><string>{HOME}/launchd.err</string>
</dict></plist>
""")
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    print("Installed. It checks every 15 minutes and only acts inside the hours and days in settings.json.")
    print("After editing this script, run 'install' again so the scheduled copy updates.")


def cmd_uninstall(args):
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink(missing_ok=True)
    print("Scheduled job removed. Your lead list and history are kept.")


def cmd_pause(args):
    pause(" ".join(args) or "paused by hand")


def cmd_resume(args):
    PAUSE_PATH.unlink(missing_ok=True)
    print("Resumed.")


COMMANDS = {
    "import": (cmd_import, 'import <apollo.csv> --niche "coffee and tea" [--only-emails-in cleaned.csv]'),
    "test": (cmd_test, "test [profile-url]   dry run on one lead: opens the invite, sends nothing"),
    "send-one": (cmd_send_one, "send-one             send ONE real connection request now, while you watch"),
    "run": (lambda a: run(live="--dry" not in a, force="--now" in a),
            "run [--now] [--dry]  one round (the scheduler calls this)"),
    "status": (cmd_status, "status               counts, limits, and who needs you"),
    "export": (cmd_export, "export [file.csv]    every lead and what happened"),
    "install": (cmd_install, "install              start the 15-minute schedule"),
    "uninstall": (cmd_uninstall, "uninstall            stop the schedule"),
    "pause": (cmd_pause, "pause [reason]       stop all sending"),
    "resume": (cmd_resume, "resume               start again"),
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd not in COMMANDS:
        print("Commands:")
        for _, (_, h) in COMMANDS.items():
            print("  " + h)
        sys.exit(0)
    COMMANDS[cmd][0](sys.argv[2:])
