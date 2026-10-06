"""Accounts: who is signed in, and which stores they may see.

Invite-only. There is no public sign-up, because every store a customer adds
costs real money in daily scans. Kelian (the admin) creates an invite at
/admin, sends the one-time link, and the brand sets its own password there.

- An admin sees every store, including the Clubhouse Skin demo.
- A customer sees only the store(s) they added themselves, one by default.
- A customer's plan caps how many buyer questions a store can track.

Passwords are stored as salted PBKDF2 hashes (standard library only), never
as text. Sessions are random tokens in an HttpOnly cookie.
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from html import escape as E

import config
import db

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
PUBLIC = ("/login", "/logout", "/invite/", "/reset/", "/logo.png", "/favicon", "/icon", "/pimg")

_local = threading.local()


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)


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
                 "WHERE s.token=? AND s.expires_at>?", (token, time.time()))
    return dict(row) if row else None


def cookie_header(token, clear=False):
    secure = "; Secure" if os.environ.get("PRODUKTO_SECURE_COOKIES") == "1" else ""
    if clear:
        return "%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax%s" % (COOKIE, secure)
    return "%s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (
        COOKIE, token, SESSION_DAYS * 86400, secure)


def create_user(email, password, is_admin=False, question_limit=None):
    return db.write("INSERT INTO users(email,pw_hash,is_admin,question_limit,created_at) VALUES (?,?,?,?,?)",
                    (email.strip().lower(), hash_pw(password), 1 if is_admin else 0,
                     question_limit, time.time()))


# --- the signed-in user for this request --------------------------------------

def set_current(user):
    _local.user = user


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
<p class="small" style="margin-top:18px">Forgot your password? Email <a href="mailto:kelian@getprodukto.com">kelian@getprodukto.com</a> and we'll send you a reset link.</p></main>""" % (err, E(nxt), E(email)))


def invite_page(token, error=""):
    inv = db.one("SELECT * FROM invites WHERE token=?", (token,))
    if not inv or inv["used_at"]:
        return 404, _frame("Link expired", '<main class="card"><img class="logo" src="/logo.png" alt="Produkto">'
                           '<h1>This link has already been used</h1><p class="sub">If you set up your account, '
                           '<a href="/login">sign in here</a>.</p></main>')
    err = '<div class="err" role="alert">%s</div>' % E(error) if error else ""
    return 200, _frame("Create your account", """<main class="card"><img class="logo" src="/logo.png" alt="Produkto">
<h1>Create your account</h1><p class="sub">%s Then we'll set up your store.</p>%s
<form method="post" action="/invite/%s">%s
<label for="p">Password</label><input id="p" type="password" name="password" minlength="10" autocomplete="new-password" required>
<p class="hint">At least 10 characters.</p>
<label for="p2">Confirm password</label><input id="p2" type="password" name="password2" minlength="10" autocomplete="new-password" required>
<button type="submit">Create account</button></form>
<p class="small" style="margin-top:18px">Already have an account? <a href="/login">Sign in</a></p></main>""" % (
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
    return 303, nxt, new_session(row["id"])


def base_url():
    return os.environ.get("PRODUKTO_BASE_URL", "http://localhost:%d" % config.PORT).rstrip("/")


def admin_page(q=None, created=""):
    created = created or (q or {}).get("created", "")
    reset = (q or {}).get("reset", "")
    reset_row = db.one("SELECT r.token, u.email FROM password_resets r JOIN users u ON u.id=r.user_id "
                       "WHERE r.token=? AND r.used_at IS NULL", (reset,)) if reset else None
    if created and not db.one("SELECT 1 FROM invites WHERE token=?", (created,)):
        created = ""
    note = ""
    if reset_row:
        note += ('<div class="ok"><b>Password reset link for %s</b> (works once, for %d hours):<br>%s/reset/%s</div>'
                 % (E(reset_row["email"]), RESET_HOURS, E(base_url()), E(reset_row["token"])))
    if created:
        note += '<div class="ok"><b>Invite link</b> (send this to the brand; it works once):<br>%s/invite/%s</div>' % (
            E(base_url()), E(created))
    users = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            E(u["email"]), "Admin" if u["is_admin"] else "Customer",
            "—" if u["is_admin"] else (u["question_limit"] or "No cap"),
            E(", ".join(sorted(owned(u["id"])))) or "—",
            '<form method="post" action="/admin/reset" style="margin:0"><input type="hidden" name="user" value="%d">'
            '<button type="submit" style="margin:0;height:32px;width:auto;padding:0 12px;font-size:.85rem">Reset link</button></form>' % u["id"])
        for u in db.all_("SELECT * FROM users ORDER BY created_at"))
    invites = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td class='small'>%s/invite/%s</td></tr>" % (
            E(i["email"]) or "Open link", i["question_limit"] or "No cap",
            "Used" if i["used_at"] else "Waiting", E(base_url()), E(i["token"]))
        for i in db.all_("SELECT * FROM invites ORDER BY created_at DESC LIMIT 30"))
    return 200, _frame("Accounts", """<main class="card wide"><img class="logo" src="/logo.png" alt="Produkto">
<h1>Accounts</h1><p class="sub">Invite a brand that has paid. They set a password, then add their own store.
<a href="/">Back to dashboard</a> · <a href="/logout">Sign out</a></p>%s
<h2>New invite</h2>
<form method="post" action="/admin/invite" class="row">
<div><label for="ie">Brand contact email <span class="small">(optional)</span></label><input id="ie" type="email" name="email" placeholder="Blank: they enter their own"></div>
<div><label for="ip">Plan</label><select id="ip" name="plan">
<option value="starter">Starter · 25 questions</option><option value="growth">Growth · 75 questions</option>
<option value="custom">Custom</option></select></div>
<div><label for="iq">Custom questions</label><input id="iq" type="number" name="questions" min="1" placeholder="e.g. 150"></div>
<button type="submit">Create invite</button></form>
<h2>Accounts</h2><table><thead><tr><th>Email</th><th>Role</th><th>Question limit</th><th>Store</th><th>Password</th></tr></thead>
<tbody>%s</tbody></table>
<h2>Invites</h2><table><thead><tr><th>Email</th><th>Questions</th><th>Status</th><th>Link</th></tr></thead>
<tbody>%s</tbody></table></main>""" % (note, users or '<tr><td colspan="5" class="small">None yet.</td></tr>',
                                       invites or '<tr><td colspan="4" class="small">None yet.</td></tr>'))


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
    return 303, "/admin?created=" + token


# --- password reset (admin-issued link; no email sending yet) ---------------------

RESET_HOURS = 24


def create_reset(form):
    try:
        uid = int(form.get("user") or 0)
    except ValueError:
        uid = 0
    if not db.one("SELECT 1 FROM users WHERE id=?", (uid,)):
        return 303, "/admin"
    token = secrets.token_urlsafe(24)
    db.write("INSERT INTO password_resets(token,user_id,created_at) VALUES (?,?,?)", (token, uid, time.time()))
    return 303, "/admin?reset=" + token


def _reset_row(token):
    return db.one("SELECT r.*, u.email FROM password_resets r JOIN users u ON u.id=r.user_id "
                  "WHERE r.token=? AND r.used_at IS NULL AND r.created_at>?",
                  (token, time.time() - RESET_HOURS * 3600))


def reset_page(token, error=""):
    row = _reset_row(token)
    if not row:
        return 404, _frame("Link expired", '<main class="card"><img class="logo" src="/logo.png" alt="Produkto">'
                           '<h1>This reset link has expired</h1><p class="sub">Links work once, for %d hours. '
                           'Email <a href="mailto:kelian@getprodukto.com">kelian@getprodukto.com</a> for a new one.</p></main>'
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
