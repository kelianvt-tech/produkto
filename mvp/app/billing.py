"""Plan and cancellation for the signed-in customer (Settings page).

Cancelling goes to Stripe when it can: the customer's subscription is set to
end at the close of the period they already paid for, so nobody loses days
they paid for and nobody is charged again. That needs STRIPE_KEY to have
Subscriptions read + write. If it doesn't (the key started out read-only for
Checkout Sessions), or the account was invited by hand rather than bought on
Stripe, the request is recorded instead and shows up on /admin for Kelian to
cancel by hand. The customer is told which of the two happened; the page
never claims Stripe stopped a payment unless Stripe said so.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import accounts
import config
import db

SCHEMA = """CREATE TABLE IF NOT EXISTS cancellations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    email TEXT,
    plan TEXT,
    reason TEXT,
    note TEXT,
    requested_at REAL,
    status TEXT,                 -- scheduled (Stripe confirmed) | requested (by hand) | undone
    subscription TEXT,
    ends_at REAL
);"""

PRICES = {"starter": 99, "growth": 297}
REASONS = ("Too expensive", "Not using it enough", "Missing a feature I need",
           "Switching to another tool", "Something else")


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)


def plan_for(user):
    """(plan key, display name, monthly price or None) from the question limit."""
    limit = user.get("question_limit")
    for key, n in accounts.PLANS.items():
        if limit == n:
            return key, key.title(), PRICES[key]
    return "custom", "Custom", None


# --- Stripe -----------------------------------------------------------------

def _stripe(method, path, data=None):
    key = config.env("STRIPE_KEY")
    if not key:
        raise accounts.StripeError("STRIPE_KEY is not set")
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request("https://api.stripe.com/v1/" + path, data=body, method=method,
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, ValueError) as e:
        raise accounts.StripeError(str(e)) from e


def _period_end(sub):
    # Newer Stripe API versions keep the period on the subscription item.
    end = sub.get("current_period_end")
    if not end:
        items = (sub.get("items") or {}).get("data") or []
        end = items[0].get("current_period_end") if items else None
    return end


def subscription(user):
    """The customer's live Stripe subscription as {id, cancelling, ends_at}, or None."""
    customer = user.get("stripe_customer")
    if not customer:
        return None
    try:
        subs = _stripe("GET", "subscriptions?" + urllib.parse.urlencode(
            {"customer": customer, "status": "all", "limit": 5}))
    except accounts.StripeError:
        return None
    for s in subs.get("data") or []:
        if s.get("status") in ("active", "trialing", "past_due"):
            return {"id": s["id"], "cancelling": bool(s.get("cancel_at_period_end") or s.get("cancel_at")),
                    "ends_at": s.get("cancel_at") or _period_end(s)}
    return None


# --- cancel and undo -----------------------------------------------------------

def open_request(user_id):
    return db.one("SELECT * FROM cancellations WHERE user_id=? AND status IN ('scheduled','requested') "
                  "ORDER BY id DESC LIMIT 1", (user_id,))


def cancel(user, reason, note, sub=None):
    """Cancel at period end on Stripe if possible, else record it for Kelian."""
    status, sub_id, ends = "requested", None, None
    sub = sub if sub is not None else subscription(user)
    if sub:
        try:
            s = _stripe("POST", "subscriptions/" + sub["id"], {"cancel_at_period_end": "true"})
            status, sub_id, ends = "scheduled", s["id"], s.get("cancel_at") or _period_end(s)
        except accounts.StripeError:
            pass
    db.write("INSERT INTO cancellations(user_id,email,plan,reason,note,requested_at,status,subscription,ends_at) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             (user["id"], user["email"], plan_for(user)[1], reason if reason in REASONS else "",
              (note or "").strip()[:2000], time.time(), status, sub_id, ends))
    return status


def undo(user):
    """Keep the plan: lift a scheduled Stripe cancellation, or withdraw the request."""
    row = open_request(user["id"])
    if not row:
        return False
    if row["status"] == "scheduled" and row["subscription"]:
        try:
            _stripe("POST", "subscriptions/" + row["subscription"], {"cancel_at_period_end": "false"})
        except accounts.StripeError:
            return False
    db.write("UPDATE cancellations SET status='undone' WHERE id=?", (row["id"],))
    return True


def admin_rows():
    """Open cancellations for /admin, newest first."""
    return db.all_("SELECT * FROM cancellations WHERE status IN ('scheduled','requested') ORDER BY id DESC")


# --- password -------------------------------------------------------------------

def change_password(user, current, new, new2):
    """Returns an error message, or '' when the password was changed."""
    row = db.one("SELECT pw_hash FROM users WHERE id=?", (user["id"],))
    if not row or not accounts.check_pw(current or "", row["pw_hash"]):
        return "Your current password isn't right."
    if len(new or "") < 10:
        return "Use at least 10 characters."
    if new != new2:
        return "The two new passwords don't match."
    db.write("UPDATE users SET pw_hash=? WHERE id=?", (accounts.hash_pw(new), user["id"]))
    return ""


# --- switching access off when the paid month ends ---------------------------

def end_due(now=None, fetch=None):
    """Disable customers whose cancelled subscription has now ended.

    Runs on every scheduler tick. Stripe is the judge: access goes off only once
    Stripe reports the subscription as canceled, so a customer is never cut off
    early because of a clock or a date we worked out ourselves. If the plan was
    turned back on in Stripe, the request is closed instead. Returns the emails
    switched off."""
    now = now or time.time()
    fetch = fetch or (lambda sid: _stripe("GET", "subscriptions/" + sid))
    ended = []
    for row in db.all_("SELECT * FROM cancellations WHERE status='scheduled' AND subscription IS NOT NULL "
                       "AND COALESCE(ends_at,0) <= ?", (now,)):
        try:
            s = fetch(row["subscription"])
        except accounts.StripeError:
            continue                                  # try again next tick
        if s.get("status") in ("canceled", "incomplete_expired", "unpaid"):
            db.write("UPDATE users SET disabled=1 WHERE id=? AND is_admin=0", (row["user_id"],))
            db.write("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
            db.write("UPDATE cancellations SET status='ended' WHERE id=?", (row["id"],))
            ended.append(row["email"])
        elif not (s.get("cancel_at_period_end") or s.get("cancel_at")):
            db.write("UPDATE cancellations SET status='undone' WHERE id=?", (row["id"],))
    return ended
