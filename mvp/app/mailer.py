"""Emails the app sends on its own: payment confirmed, first results ready,
password reset, and a note to Kelian when someone pays.

Sent through the getprodukto.com Google Workspace mailbox over SMTP (standard
library only, free). Settings in .env, read with config.env:

    SMTP_USER=kelian@getprodukto.com
    SMTP_PASSWORD=<a Google app password for that mailbox>

Without SMTP_PASSWORD nothing is sent: the email is logged in the `emails`
table as 'not sent' and the page carries on, so a missing setting never breaks
a payment or a scan. Sending happens on a background thread.

Each email has a `kind` and a `key` (e.g. first_results + the store domain).
`once=True` skips it if that kind+key was already sent, so a re-opened page or
a second scan never emails twice.
"""

import os
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape as E

import config
import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT DEFAULT '',
    to_addr TEXT NOT NULL,
    subject TEXT,
    status TEXT,            -- queued | sent | not sent | failed
    error TEXT,
    created_at REAL,
    sent_at REAL
);
CREATE INDEX IF NOT EXISTS idx_emails_kind_key ON emails(kind, key);
"""

FROM_NAME = "Produkto"
SUPPORT = "kelian@getprodukto.com"

def _init():
    with db.conn() as c:
        c.executescript(SCHEMA)


def configured():
    return bool(config.env("SMTP_PASSWORD"))


def already_sent(kind, key):
    _init()
    return bool(db.one("SELECT 1 FROM emails WHERE kind=? AND key=? AND status IN ('queued','sent')", (kind, key)))


def send(to, subject, paragraphs, button=None, kind="other", key="", once=False, wait=False):
    """Queue one email. `paragraphs` is a list of plain-text paragraphs;
    `button` an optional (label, url). Returns the emails row id, or None if
    skipped because it was already sent."""
    _init()
    to = (to or "").strip()
    if "@" not in to:
        return None
    if once and already_sent(kind, key):
        return None
    eid = db.write("INSERT INTO emails(kind,key,to_addr,subject,status,created_at) VALUES (?,?,?,?,?,?)",
                   (kind, key, to, subject, "queued", time.time()))
    msg = _message(to, subject, paragraphs, button)
    t = threading.Thread(target=_deliver, args=(eid, msg), daemon=True)
    t.start()
    if wait:
        t.join(30)
    return eid


def _message(to, subject, paragraphs, button):
    user = config.env("SMTP_USER") or SUPPORT
    msg = EmailMessage()
    msg["From"] = formataddr((FROM_NAME, user))
    msg["To"] = to
    msg["Reply-To"] = SUPPORT
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="getprodukto.com")
    text = "\n\n".join(paragraphs)
    if button:
        text += "\n\n%s: %s" % button
    text += "\n\n- Produkto\nQuestions? Reply to this email."
    msg.set_content(text)
    msg.add_alternative(_html(paragraphs, button), subtype="html")
    return msg


def _html(paragraphs, button):
    body = "".join('<p style="margin:0 0 16px;font-size:15px;line-height:1.55;color:#1f2a3d">%s</p>' % E(p)
                   for p in paragraphs)
    if button:
        body += ('<p style="margin:24px 0"><a href="%s" style="display:inline-block;background:#0b1b35;'
                 'color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 20px;'
                 'border-radius:8px">%s</a></p>' % (E(button[1]), E(button[0])))
    base = base_url()
    return ('<!doctype html><html><body style="margin:0;background:#f4f6fa;padding:24px 12px;'
            'font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
            '<div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;padding:28px">'
            '<img src="%s/logo.png" alt="Produkto" width="168" height="30" style="display:block;margin-bottom:22px">'
            '%s<p style="margin:24px 0 0;font-size:13px;color:#6b7486">Questions? Reply to this email.</p>'
            '</div></body></html>' % (E(base), body))


def _deliver(eid, msg):
    password = config.env("SMTP_PASSWORD")
    if not password:
        db.write("UPDATE emails SET status='not sent', error=? WHERE id=?", ("SMTP_PASSWORD is not set", eid))
        return
    if os.path.basename(config.DB_PATH) != "produkto.db":   # tests and the laptop's server copy never email anyone
        db.write("UPDATE emails SET status='not sent', error=? WHERE id=?", ("not the real database", eid))
        return
    host = config.env("SMTP_HOST") or "smtp.gmail.com"
    port = int(config.env("SMTP_PORT") or 587)
    user = config.env("SMTP_USER") or SUPPORT
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, password)
            s.send_message(msg)
        db.write("UPDATE emails SET status='sent', sent_at=?, error=NULL WHERE id=?", (time.time(), eid))
    except Exception as e:                                   # noqa: BLE001
        db.write("UPDATE emails SET status='failed', error=? WHERE id=?", (str(e)[:300], eid))


def base_url():
    return (config.env("PRODUKTO_BASE_URL") or "https://app.getprodukto.com").rstrip("/")


# --- The emails ---------------------------------------------------------------

PLAN_NAMES = {25: "Starter", 75: "Growth"}


def payment_confirmed(email, invite_token, question_limit, session_id):
    """Right after a Stripe payment: the link to create the account, in case
    they close the tab. Plus a note to Kelian."""
    plan = PLAN_NAMES.get(question_limit, "Produkto")
    send(email, "Your Produkto %s plan is active" % plan, [
        "Thanks for subscribing to Produkto %s. Your payment went through." % plan,
        "If you haven't created your account yet, use the button below. It takes a minute: "
        "choose a password, add your store, and we start measuring how AI recommends your catalog.",
        "Already set it up? Sign in at %s/login." % base_url(),
        "Stripe sends your receipt separately.",
    ], button=("Create your account", "%s/invite/%s" % (base_url(), invite_token)),
        kind="payment_confirmed", key=session_id, once=True)
    send(SUPPORT, "New customer: %s (%s)" % (email or "no email", plan), [
        "%s just paid for %s on Stripe." % (email or "Someone", plan),
        "They were sent the create-your-account email. Nothing for you to do.",
    ], button=("Open admin", base_url() + "/admin/accounts"), kind="admin_new_customer", key=session_id, once=True)


def first_results(store_domain, brand=""):
    """When a customer's first scan finishes. Once per store."""
    try:
        owners = db.all_("SELECT u.email FROM user_stores us JOIN users u ON u.id=us.user_id "
                         "WHERE us.store_domain=? AND COALESCE(u.is_admin,0)=0 AND COALESCE(u.disabled,0)=0",
                         (store_domain,))
    except Exception:                                        # noqa: BLE001  (no account tables in some tests)
        return
    name = brand or store_domain
    for o in owners:
        send(o["email"], "Your first AI visibility results for %s are ready" % name, [
            "Your first scan of %s has finished." % name,
            "Your dashboard now shows how often AI names your products, where they appear in the answer, "
            "and which competitors it recommends instead.",
            "From now on we scan every day, so your trend builds over the coming weeks.",
        ], button=("See your results", "%s/?d=%s" % (base_url(), store_domain)),
            kind="first_results", key="%s|%s" % (store_domain, o["email"]), once=True)


def password_reset(email, token, hours):
    send(email, "Reset your Produkto password", [
        "Someone asked to reset the password for your Produkto account.",
        "The link works once, for %d hours. If you didn't ask for this, ignore this email; "
        "your password stays the same." % hours,
    ], button=("Choose a new password", "%s/reset/%s" % (base_url(), token)), kind="password_reset", key=token)


def alert(topic, subject, paragraphs):
    """Something broke that a customer would notice. Emails Kelian at most once
    an hour per topic."""
    send(SUPPORT, "[Produkto alert] " + subject, paragraphs, kind="alert",
         key="%s|%d" % (topic, int(time.time() // 3600)), once=True)
