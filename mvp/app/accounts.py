"""Accounts: who is signed in, and which stores they may see.

Invite-only. There is no public sign-up, because every store a customer adds
costs real money in daily scans. Kelian (the admin) creates an invite at
/admin, sends the one-time link, and the brand sets its own password there.

- An admin sees every store, including the Clubhouse Skin demo.
- A customer sees only the store(s) they added themselves, one by default.
- A customer's plan caps how many buyer questions a store can track.

Passwords are stored as salted PBKDF2 hashes (standard library only), never
as text. Sessions are random tokens in an HttpOnly cookie.

Paying on Stripe skips the manual invite (2026-10-13): the payment link sends
the buyer to /welcome?session_id=..., which asks Stripe whether that checkout
was paid and for which plan, then creates the invite itself. One invite per
checkout. Cancellations are still handled by hand: Disable in /admin.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from html import escape as E

import config
import db
import mailer

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    question_limit INTEGER,
    store_limit INTEGER DEFAULT 1,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS user_stores (
    user_id INTEGER NOT NULL,
    store_domain TEXT NOT NULL,
    PRIMARY KEY (user_id, store_domain)
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at REAL
);
CREATE TABLE IF NOT EXISTS password_resets (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL,
    used_at REAL
);
CREATE TABLE IF NOT EXISTS mcp_keys (
    key_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL,
    last_used REAL
);
CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    question_limit INTEGER,
    created_at REAL,
    used_at REAL
);
"""

COOKIE = "pk_session"
SESSION_DAYS = 30
ITERATIONS = 240_000
PLANS = {"starter": 25, "growth": 75}   # Custom: any number, typed at invite time

# Paths anyone may open without signing in.
PUBLIC = ("/login", "/logout", "/forgot", "/invite/", "/reset/", "/welcome", "/logo.png", "/favicon", "/icon", "/pimg",
          "/content/cal/",   # private calendar feed: the random link is the key (content_calendar.ical)
          "/content/media/")  # photos an owner uploaded for an article: the random link is the key (article_learning)

# Which plan a Stripe checkout bought, read from its price before discounts.
# Matches the live payment links in research/stripe-payment-links.md.
STRIPE_PLANS = {("usd", 9900): "starter", ("usd", 29700): "growth"}
SUPPORT_EMAIL = "kelian@getprodukto.com"

_local = threading.local()


# Columns added after the first release; init() adds them to older databases.
_ADDED = (("users", "disabled", "INTEGER DEFAULT 0"), ("users", "source", "TEXT DEFAULT ''"),
          ("users", "stripe_customer", "TEXT DEFAULT ''"), ("invites", "source", "TEXT DEFAULT ''"),
          ("invites", "stripe_session", "TEXT"), ("invites", "stripe_customer", "TEXT DEFAULT ''"))


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)
        for table, col, kind in _ADDED:
            if col not in {r[1] for r in c.execute("PRAGMA table_info(%s)" % table)}:
                c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, kind))
        # One invite per Stripe checkout, even if /welcome is opened twice at once.
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invites_stripe ON invites(stripe_session)"
                  " WHERE stripe_session IS NOT NULL")


# --- passwords and sessions -------------------------------------------------

def hash_pw(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return "pbkdf2$%d$%s$%s" % (ITERATIONS, salt, digest)


def check_pw(password, stored):
    try:
        _, n, salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(n)).hex()
    return hmac.compare_digest(test, digest)


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    db.write("INSERT INTO sessions(token,user_id,expires_at) VALUES (?,?,?)",
             (token, user_id, time.time() + SESSION_DAYS * 86400))
    return token


def user_for(token):
    if not token:
        return None
    row = db.one("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                 "WHERE s.token=? AND s.expires_at>? AND COALESCE(u.disabled,0)=0", (token, time.time()))
    return dict(row) if row else None


def cookie_header(token, clear=False):
    secure = "; Secure" if os.environ.get("PRODUKTO_SECURE_COOKIES") == "1" else ""
    if clear:
        return "%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax%s" % (COOKIE, secure)
    return "%s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (
        COOKIE, token, SESSION_DAYS * 86400, secure)


# A second, harmless cookie that tells getprodukto.com this browser is signed in,
# so the website can show "Go to dashboard" instead of Log in / Sign up. It
# holds no session and opens nothing: the real sign-in stays in the HttpOnly
# cookie above, which only app.getprodukto.com can read. Set only when
# PRODUKTO_COOKIE_DOMAIN names the shared domain (the server), never locally.
SITE_COOKIE = "pk_signed_in"


def site_cookie_header(clear=False):
    domain = config.env("PRODUKTO_COOKIE_DOMAIN")
    if not domain:
        return None
    secure = "; Secure" if os.environ.get("PRODUKTO_SECURE_COOKIES") == "1" else ""
    if clear:
        return "%s=; Domain=%s; Path=/; Max-Age=0; SameSite=Lax%s" % (SITE_COOKIE, domain, secure)
    return "%s=1; Domain=%s; Path=/; Max-Age=%d; SameSite=Lax%s" % (
        SITE_COOKIE, domain, SESSION_DAYS * 86400, secure)


def create_user(email, password, is_admin=False, question_limit=None):
    return db.write("INSERT INTO users(email,pw_hash,is_admin,question_limit,created_at) VALUES (?,?,?,?,?)",
                    (email.strip().lower(), hash_pw(password), 1 if is_admin else 0,
                     question_limit, time.time()))


# --- the signed-in user for this request --------------------------------------

def set_current(user):
    _local.user = user


# --- MCP keys ---------------------------------------------------------------
# A merchant's AI assistant (Claude, Cursor...) reads their dashboard through
# /mcp with one of these as a Bearer token. Only a hash is stored, so a key is
# shown once, when it is made. One key per user: making a new one replaces it.

def _key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_mcp_key(user_id):
    key = "pk_" + secrets.token_urlsafe(32)
    db.write("DELETE FROM mcp_keys WHERE user_id=?", (user_id,))
    db.write("INSERT INTO mcp_keys(key_hash,user_id,created_at) VALUES (?,?,?)",
             (_key_hash(key), user_id, time.time()))
    return key


def revoke_mcp_key(user_id):
    db.write("DELETE FROM mcp_keys WHERE user_id=?", (user_id,))


def mcp_key_info(user_id):
    row = db.one("SELECT created_at,last_used FROM mcp_keys WHERE user_id=?", (user_id,))
    return dict(row) if row else None


def user_for_mcp_key(key):
    if not key:
        return None
    h = _key_hash(key)
    row = db.one("SELECT u.* FROM mcp_keys k JOIN users u ON u.id=k.user_id "
                 "WHERE k.key_hash=? AND COALESCE(u.disabled,0)=0", (h,))
    if row:
        db.write("UPDATE mcp_keys SET last_used=? WHERE key_hash=?", (time.time(), h))
    return dict(row) if row else None


def current():
    return getattr(_local, "user", None)


def is_admin():
    u = current()
    return bool(u and u["is_admin"])


def owned(user_id):
    return {r["store_domain"] for r in db.all_(
        "SELECT store_domain FROM user_stores WHERE user_id=?", (user_id,))}


def can_see(domain):
    """True if the signed-in user may open this store. No user = background job."""
    u = current()
    if u is None or u["is_admin"]:
        return True
    return bool(domain) and domain in owned(u["id"])


def visible(domains):
    """Filter a store list down to what the signed-in user may see."""
    u = current()
    if u is None or u["is_admin"]:
        return list(domains)
    mine = owned(u["id"])
    return [d for d in domains if d in mine]


def claim(domain):
    """Attach a newly added store to the signed-in customer, or refuse it.

    Raises PermissionError with a message fit to show the merchant."""
    u = current()
    if u is None or u["is_admin"]:
        return
    mine = owned(u["id"])
    if domain in mine:
        return
    taken = db.one("SELECT 1 FROM user_stores WHERE store_domain=?", (domain,))
    if taken:
        raise PermissionError("This store is already set up in another account. "
                              "Book a demo if you think that's a mistake.")
    if len(mine) >= (u["store_limit"] or 1):
        raise PermissionError("Your plan covers %d store. Book a demo to add another."
                              % (u["store_limit"] or 1))
    # A store we set up for a demo starts from nothing for the paying brand: no demo scans, questions, topics,
    # brand profile or agent drafts (Kelian, 2026-10-21; before that, real demo scans were kept).
    import demo_history
    if db.one("SELECT 1 FROM stores WHERE domain=?", (domain,)):
        demo_history.fresh_start(domain)
    db.write("INSERT INTO user_stores(user_id,store_domain) VALUES (?,?)", (u["id"], domain))


def question_limit(domain):
    """The most buyer questions this store may track, or None for no cap.

    The cap follows the customer who owns the store, so the daily scheduler
    (no signed-in user) still respects it."""
    row = db.one("SELECT MIN(u.question_limit) n FROM user_stores us JOIN users u ON u.id=us.user_id "
                 "WHERE us.store_domain=? AND u.is_admin=0 AND u.question_limit IS NOT NULL", (domain,))
    return row["n"] if row and row["n"] else None


def check_question_limit(domain, count):
    cap = question_limit(domain)
    if cap and count > cap:
        raise ValueError("Your plan tracks up to %d buyer questions. Remove %d to save."
                         % (cap, count - cap))


# --- pages ----------------------------------------------------------------------

def _frame(title, body):
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>%s · Produkto</title>
<link rel="icon" type="image/png" href="/favicon.png?v=1"><link rel="apple-touch-icon" href="/favicon.png?v=1">
<style>
:root{--ink:#0b1b35;--muted:#586579;--line:#dfe3ea;--bg:#f4f6fa}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px 16px;
background:var(--bg);color:var(--ink);font:16px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.card{width:100%%;max-width:420px;background:#fff;border:1px solid var(--line);border-radius:18px;padding:32px 28px;
box-shadow:0 12px 32px -12px rgba(11,27,53,.18)}
.card.wide{max-width:880px}
.logo{height:34px;margin-bottom:22px}h1{font-size:1.65rem;margin:0 0 6px;font-weight:750;letter-spacing:-.02em}
.sub{color:#3d4a5e;margin:0 0 22px}label{display:block;font-weight:650;font-size:.95rem;margin:14px 0 6px}
input,select{width:100%%;height:44px;border:1px solid var(--line);border-radius:10px;padding:0 12px;font:inherit;color:inherit}
input:focus,select:focus{outline:2px solid var(--ink);outline-offset:1px}
button{margin-top:22px;width:100%%;height:46px;border:0;border-radius:11px;background:var(--ink);color:#fff;font-family:inherit;font-size:1rem;font-weight:650;cursor:pointer}
.err{background:#fff2ea;border:1px solid #f8cdb5;color:#8a2c07;border-radius:10px;padding:10px 12px;margin-bottom:6px}
.ok{background:#eef6ef;border:1px solid #bfdcc3;border-radius:10px;padding:12px;margin:14px 0;word-break:break-all}
table{width:100%%;border-collapse:collapse;margin-top:10px;font-size:.92rem}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600}.small{color:#3d4a5e;font-size:.88rem}.hint{color:#3d4a5e;font-size:.85rem;margin:6px 0 0}h2{font-size:1.1rem;margin:28px 0 4px}
.row{display:grid;grid-template-columns:2fr 1fr auto;gap:10px;align-items:end}.row button{margin:0;width:auto;padding:0 18px}
@media(max-width:640px){.row{grid-template-columns:1fr}.row button{width:100%%}}
a{color:var(--ink)}
</style></head><body>%s</body></html>""" % (E(title), body)


def login_page(error="", email="", nxt="/"):
    err = '<div class="err" role="alert">%s</div>' % E(error) if error else ""
    return _frame("Sign in", """<main class="card"><img class="logo" src="/logo.png" alt="Produkto">
<h1>Sign in</h1><p class="sub">Welcome back.</p>%s
<form method="post" action="/login"><input type="hidden" name="next" value="%s">
<label for="e">Email</label><input id="e" type="email" name="email" value="%s" autocomplete="email" required>
<label for="p">Password</label><input id="p" type="password" name="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form>
<p class="small" style="margin-top:18px"><a href="/forgot">Forgot your password?</a></p></main>""" % (err, E(nxt), E(email)))


def forgot_page(sent=False, email=""):
    if sent:
        return 200, _frame("Check your email", '<main class="card"><img class="logo" src="/logo.png" alt="Produkto">'
                           '<h1>Check your email</h1><p class="sub">If <b>%s</b> has a Produkto account, a reset link '
                           'is on its way. It works once, for %d hours.</p><p class="small"><a href="/login">Back to sign in</a>'
                           '</p></main>' % (E(email), RESET_HOURS))
    return 200, _frame("Reset your password", """<main class="card"><img class="logo" src="/logo.png" alt="Produkto">
<h1>Reset your password</h1><p class="sub">Enter your account email and we'll send you a link.</p>
<form method="post" action="/forgot">
<label for="e">Email</label><input id="e" type="email" name="email" value="%s" autocomplete="email" required>
<button type="submit">Send reset link</button></form>
<p class="small" style="margin-top:18px"><a href="/login">Back to sign in</a></p></main>""" % E(email))


def request_reset(form):
    """Self-serve reset. Always shows the same reply, so it never reveals which
    emails have accounts. At most one email per account every 2 minutes."""
    email = form.get("email", "").strip().lower()
    row = db.one("SELECT * FROM users WHERE email=?", (email,)) if "@" in email else None
    if row and not row["disabled"] and not db.one(
            "SELECT 1 FROM password_resets WHERE user_id=? AND created_at>?", (row["id"], time.time() - 120)):
        token = secrets.token_urlsafe(24)
        db.write("INSERT INTO password_resets(token,user_id,created_at) VALUES (?,?,?)", (token, row["id"], time.time()))
        mailer.password_reset(email, token, RESET_HOURS)
    return forgot_page(sent=True, email=email)


def invite_page(token, error=""):
    """The set-a-password page. After a Stripe payment it opens with a thank-you."""
    inv = db.one("SELECT * FROM invites WHERE token=?", (token,))
    if not inv or inv["used_at"]:
        return 404, _frame("Link expired", '<main class="card"><img class="logo" src="/logo.png" alt="Produkto">'
                           '<h1>This link has already been used</h1><p class="sub">If you set up your account, '
                           '<a href="/login">sign in here</a>.</p></main>')
    err = '<div class="err" role="alert">%s</div>' % E(error) if error else ""
    return 200, _frame("Create your account", """<main class="card"><img class="logo" src="/logo.png" alt="Produkto">
<h1>Create your account</h1><p class="sub">%s%s Then we'll set up your store.</p>%s
<form method="post" action="/invite/%s">%s
<label for="p">Password</label><input id="p" type="password" name="password" minlength="10" autocomplete="new-password" required>
<p class="hint">At least 10 characters.</p>
<label for="p2">Confirm password</label><input id="p2" type="password" name="password2" minlength="10" autocomplete="new-password" required>
<button type="submit">Create account</button></form>
<p class="small" style="margin-top:18px">Already have an account? <a href="/login">Sign in</a></p></main>""" % (
        "Thanks, your payment went through. " if inv["source"] == "stripe" else "",
        "Set a password for <b>%s</b>." % E(inv["email"]) if inv["email"] else "Enter your email and choose a password.",
        err, E(token),
        "" if inv["email"] else '<label for="e">Email</label><input id="e" type="email" name="email" autocomplete="email" required>'))


def accept_invite(token, form):
    """Returns (code, payload, session_token_or_None)."""
    inv = db.one("SELECT * FROM invites WHERE token=?", (token,))
    if not inv or inv["used_at"]:
        code, body = invite_page(token)
        return code, body, None
    email = inv["email"] or form.get("email", "").strip().lower()
    if "@" not in email:
        return 200, invite_page(token, "Enter a valid email address.")[1], None
    pw, pw2 = form.get("password", ""), form.get("password2", "")
    if len(pw) < 10:
        return 200, invite_page(token, "Use at least 10 characters.")[1], None
    if pw != pw2:
        return 200, invite_page(token, "The two passwords don't match.")[1], None
    if db.one("SELECT 1 FROM users WHERE email=?", (email,)):
        return 200, invite_page(token, "An account with this email already exists. Sign in instead.")[1], None
    uid = create_user(email, pw, question_limit=inv["question_limit"])
    db.write("UPDATE users SET source=?, stripe_customer=? WHERE id=?",
             (inv["source"] or "invite", inv["stripe_customer"] or "", uid))
    db.write("UPDATE invites SET used_at=? WHERE token=?", (time.time(), token))
    return 303, "/new", new_session(uid)


def do_login(form):
    """Returns (code, payload, session_token_or_None)."""
    email = form.get("email", "").strip().lower()
    nxt = form.get("next") or "/"
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    row = db.one("SELECT * FROM users WHERE email=?", (email,))
    if not row or not check_pw(form.get("password", ""), row["pw_hash"]):
        time.sleep(0.5)
        return 200, login_page("That email and password don't match.", email, nxt), None
    if row["disabled"]:
        return 200, login_page("This account is paused. Email %s to reactivate it." % SUPPORT_EMAIL, email, nxt), None
    return 303, nxt, new_session(row["id"])


def base_url():
    return (config.env("PRODUKTO_BASE_URL") or "http://localhost:%d" % config.PORT).rstrip("/")


def admin_page(q=None, created=""):
    """Accounts and invites, inside the admin page's own frame and brand-kit look (hub.frame)."""
    import billing     # late: billing imports this module
    import hub
    created = created or (q or {}).get("created", "")
    reset = (q or {}).get("reset", "")
    reset_row = db.one("SELECT r.token, u.email FROM password_resets r JOIN users u ON u.id=r.user_id "
                       "WHERE r.token=? AND r.used_at IS NULL", (reset,)) if reset else None
    if created and not db.one("SELECT 1 FROM invites WHERE token=?", (created,)):
        created = ""
    note = ""
    if reset_row:
        note += ('<div class="notice"><b>Password reset link for %s</b> · works once, for %d hours<code>%s/reset/%s</code></div>'
                 % (E(reset_row["email"]), RESET_HOURS, E(base_url()), E(reset_row["token"])))
    if created:
        note += ('<div class="notice"><b>Invite link</b> · send this to the brand; it works once<code>%s/invite/%s</code></div>'
                 % (E(base_url()), E(created)))

    def btn(action, user, label, extra=""):
        return ('<form method="post" action="%s" class="inline"><input type="hidden" name="user" value="%d">%s'
                '<button type="submit" class="btn row-btn">%s</button></form>' % (action, user, extra, label))

    users = "".join(
        '<tr><td><b>%s</b></td><td>%s</td><td class="m">%s</td><td class="m">%s</td><td><div class="cells">%s%s</div></td></tr>' % (
            E(u["email"]),
            '<span class="tag">Admin</span>' if u["is_admin"] else (
                '<span class="tag">Customer%s</span>' % (" · Stripe" if u["source"] == "stripe" else "")
                + (' <span class="st bad"><i></i>Paused</span>' if u["disabled"] else "")),
            "—" if u["is_admin"] else (u["question_limit"] or "No cap"),
            E(", ".join(sorted(owned(u["id"])))) or "—",
            btn("/admin/reset", u["id"], "Reset link"),
            "" if u["is_admin"] else btn("/admin/disable", u["id"], "Enable" if u["disabled"] else "Disable",
                                         '<input type="hidden" name="disabled" value="%d">' % (0 if u["disabled"] else 1)))
        for u in db.all_("SELECT * FROM users ORDER BY created_at"))
    invites = "".join(
        '<tr><td>%s</td><td class="m">%s</td><td>%s</td><td class="link">%s/invite/%s</td></tr>' % (
            (E(i["email"]) or "Open link") + (" · Stripe" if i["source"] == "stripe" else ""), i["question_limit"] or "No cap",
            hub._pill(bool(i["used_at"]), "Used", "Waiting", warn=True), E(base_url()), E(i["token"]))
        for i in db.all_("SELECT * FROM invites ORDER BY created_at DESC LIMIT 30"))
    cancels = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            E(c["email"] or ""), E(c["plan"] or ""),
            "Switches off by itself" + (" on " + time.strftime("%d %b %Y", time.gmtime(c["ends_at"])) if c["ends_at"] else "")
            if c["status"] == "scheduled" else "<b>Cancel by hand in Stripe, then Disable</b>",
            E(c["reason"] or "—"), E(c["note"] or ""))
        for c in billing.admin_rows())

    def table(head, rows, cols, empty="None yet."):
        return ('<div class="panel"><div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></div>'
                % ("".join("<th>%s</th>" % c for c in head), rows or '<tr><td colspan="%d" class="m">%s</td></tr>' % (cols, empty)))

    def sec(n, title, desc, body):
        return ('<section class="sec wide"><div class="sec-h"><span class="lbl"><b>%02d</b> · %s</span><p>%s</p></div>%s</section>'
                % (n, title, desc, body))

    form = """<div class="panel"><form method="post" action="/admin/invite" class="form">
<label><span class="lbl">Brand contact email · optional</span><input type="email" name="email" placeholder="Blank: they enter their own"></label>
<label><span class="lbl">Plan</span><select name="plan"><option value="starter">Starter · 25 questions</option>
<option value="growth">Growth · 75 questions</option><option value="custom">Custom</option></select></label>
<label><span class="lbl">Custom questions</span><input type="number" name="questions" min="1" placeholder="e.g. 150"></label>
<button type="submit" class="btn solid">Create invite</button></form></div>"""
    n = 1
    parts = [sec(n, "New invite", "For Custom plans and demos. Brands that pay on Stripe get their account by themselves.", form)]
    if cancels:
        n += 1
        parts.append(sec(n, "Cancellations", "Waiting for you.", table(
            ("Email", "Plan", "To do", "Reason", "Note"), cancels, 5)))
    n += 1
    parts.append(sec(n, "Accounts", "Disable an account when its subscription ends: sign-in and daily scans stop.", table(
        ("Email", "Role", "Questions", "Store", "Access"), users, 5)))
    n += 1
    parts.append(sec(n, "Invites", "The last 30. Each link works once.", table(
        ("Email", "Questions", "Status", "Link"), invites, 4)))
    body = ('<div class="hero"><span class="lbl"><b>●</b> Internal · only you</span>'
            '<h1>Accounts.<span class="cur"></span></h1><p>Who can sign in, what they can track, and the links you send.</p>'
            '</div>%s<div class="secs">%s</div>' % (note, "".join(parts)))
    return 200, hub.frame("Accounts · Produkto Admin", body, here="/admin/accounts")


def create_invite(form):
    # Blank email = an open link (e.g. a friend testing): whoever opens it
    # types their own email. Still works once.
    email = form.get("email", "").strip().lower()
    if email and "@" not in email:
        return admin_page()
    plan = form.get("plan", "starter")
    if plan == "custom":
        try:
            limit = max(1, int(form.get("questions") or 0))
        except ValueError:
            limit = 0
        if limit <= 1:
            limit = 150   # Custom starts at 150; never leave a customer uncapped by accident
    else:
        limit = PLANS.get(plan, PLANS["starter"])
    token = secrets.token_urlsafe(24)
    db.write("INSERT INTO invites(token,email,question_limit,created_at) VALUES (?,?,?,?)",
             (token, email, limit, time.time()))
    # Redirect after the POST, so refreshing the page can't create a second invite.
    return 303, "/admin/accounts?created=" + token


# --- password reset (admin-issued link; no email sending yet) ---------------------

RESET_HOURS = 24


def create_reset(form):
    try:
        uid = int(form.get("user") or 0)
    except ValueError:
        uid = 0
    if not db.one("SELECT 1 FROM users WHERE id=?", (uid,)):
        return 303, "/admin/accounts"
    token = secrets.token_urlsafe(24)
    db.write("INSERT INTO password_resets(token,user_id,created_at) VALUES (?,?,?)", (token, uid, time.time()))
    return 303, "/admin/accounts?reset=" + token


def _reset_row(token):
    return db.one("SELECT r.*, u.email FROM password_resets r JOIN users u ON u.id=r.user_id "
                  "WHERE r.token=? AND r.used_at IS NULL AND r.created_at>?",
                  (token, time.time() - RESET_HOURS * 3600))


def reset_page(token, error=""):
    row = _reset_row(token)
    if not row:
        return 404, _frame("Link expired", '<main class="card"><img class="logo" src="/logo.png" alt="Produkto">'
                           '<h1>This reset link has expired</h1><p class="sub">Links work once, for %d hours. '
                           '<a href="/forgot">Send a new link</a>.</p></main>'
                           % RESET_HOURS)
    err = '<div class="err" role="alert">%s</div>' % E(error) if error else ""
    return 200, _frame("Choose a new password", """<main class="card"><img class="logo" src="/logo.png" alt="Produkto">
<h1>Choose a new password</h1><p class="sub">For <b>%s</b>.</p>%s
<form method="post" action="/reset/%s">
<label for="p">New password</label><input id="p" type="password" name="password" minlength="10" autocomplete="new-password" required>
<p class="hint">At least 10 characters.</p>
<label for="p2">Confirm password</label><input id="p2" type="password" name="password2" minlength="10" autocomplete="new-password" required>
<button type="submit">Save password</button></form></main>""" % (E(row["email"]), err, E(token)))


def accept_reset(token, form):
    """Returns (code, payload, session_token_or_None)."""
    row = _reset_row(token)
    if not row:
        code, body = reset_page(token)
        return code, body, None
    pw, pw2 = form.get("password", ""), form.get("password2", "")
    if len(pw) < 10:
        return 200, reset_page(token, "Use at least 10 characters.")[1], None
    if pw != pw2:
        return 200, reset_page(token, "The two passwords don't match.")[1], None
    db.write("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(pw), row["user_id"]))
    db.write("UPDATE password_resets SET used_at=? WHERE token=?", (time.time(), token))
    db.write("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))   # sign out everywhere else
    return 303, "/", new_session(row["user_id"])


def set_disabled(form):
    """Pause or restore a customer. Pausing signs them out and stops their daily scans."""
    try:
        uid = int(form.get("user", ""))
    except ValueError:
        return 303, "/admin/accounts"
    row = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if row and not row["is_admin"]:
        off = 1 if form.get("disabled") == "1" else 0
        db.write("UPDATE users SET disabled=? WHERE id=?", (off, uid))
        if off:
            db.write("DELETE FROM sessions WHERE user_id=?", (uid,))
    return 303, "/admin/accounts"


def customer_stores():
    """Stores owned by an active (not disabled) customer."""
    try:
        return {r["store_domain"] for r in db.all_(
            "SELECT us.store_domain FROM user_stores us JOIN users u ON u.id=us.user_id "
            "WHERE COALESCE(u.is_admin,0)=0 AND COALESCE(u.disabled,0)=0")}
    except sqlite3.OperationalError:   # no account tables yet (some tests)
        return set()


def paused_stores():
    """Stores whose every owner is disabled: no daily scans for them."""
    try:
        return {r["store_domain"] for r in db.all_(
            "SELECT us.store_domain FROM user_stores us JOIN users u ON u.id=us.user_id "
            "GROUP BY us.store_domain HAVING MIN(COALESCE(u.disabled,0))=1")}
    except sqlite3.OperationalError:   # no account tables yet (some tests)
        return set()


# --- Stripe: from a paid checkout straight to "create your account" -------------

class StripeError(Exception):
    pass


def stripe_session(session_id):
    """Read one Checkout Session from Stripe. Needs STRIPE_KEY in .env: a
    restricted key with read access to Checkout Sessions only."""
    key = config.env("STRIPE_KEY")
    if not key:
        raise StripeError("STRIPE_KEY is not set")
    req = urllib.request.Request("https://api.stripe.com/v1/checkout/sessions/" + session_id,
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, ValueError) as e:
        raise StripeError(str(e)) from e


def _welcome_problem(title, text):
    return 200, _frame(title, '<main class="card"><img class="logo" src="/logo.png" alt="Produkto">'
                       '<h1>%s</h1><p class="sub">%s</p></main>' % (E(title), text))


def welcome_page(q, fetch=None):
    """Where Stripe sends a buyer after paying. Checks the payment with Stripe,
    then shows the set-a-password page. Safe to open more than once."""
    sid = (q or {}).get("session_id", "")
    contact = 'Email <a href="mailto:%s">%s</a> and we&rsquo;ll set you up by hand.' % (SUPPORT_EMAIL, SUPPORT_EMAIL)
    if not re.fullmatch(r"cs_(live|test)_[A-Za-z0-9]{10,200}", sid):
        return _welcome_problem("We couldn't find your payment", "This link is missing its payment reference. " + contact)
    inv = db.one("SELECT * FROM invites WHERE stripe_session=?", (sid,))
    if inv:
        return invite_page(inv["token"])
    try:
        s = (fetch or stripe_session)(sid)
    except StripeError:
        return _welcome_problem("We couldn't confirm your payment yet",
                                "Refresh this page in a minute. If it still doesn't work, " + contact[0].lower() + contact[1:])
    if s.get("status") != "complete" or s.get("payment_status") not in ("paid", "no_payment_required"):
        return _welcome_problem("Your payment isn't complete",
                                'Stripe hasn&rsquo;t confirmed this payment. <a href="https://getprodukto.com/pricing">Back to pricing</a>, or ' + contact[0].lower() + contact[1:])
    plan = STRIPE_PLANS.get(((s.get("currency") or "").lower(), s.get("amount_subtotal")), "starter")
    email = ((s.get("customer_details") or {}).get("email") or s.get("customer_email") or "").strip().lower()
    token = secrets.token_urlsafe(24)
    try:
        db.write("INSERT INTO invites(token,email,question_limit,created_at,source,stripe_session,stripe_customer) "
                 "VALUES (?,?,?,?,?,?,?)", (token, email, PLANS[plan], time.time(), "stripe", sid, s.get("customer") or ""))
    except sqlite3.IntegrityError:     # the same checkout opened twice at once
        token = db.one("SELECT token FROM invites WHERE stripe_session=?", (sid,))["token"]
    else:
        mailer.payment_confirmed(email, token, PLANS[plan], sid)
    return invite_page(token)
