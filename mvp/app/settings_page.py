"""Settings: account, plan and billing, daily scans, and cancelling.

Laid out the way most SaaS settings pages are (Linear, Vercel, Stripe): one
card per topic, the destructive action last and on its own, and a confirm
step that offers to keep the plan before it cancels anything.

The daily-scan table is read-only: the stores held back live in
config.DAILY_SCAN_EXCLUDE, and changing that is a code change, not a click.
Cancelling is handled in billing.py.
"""

import html
import time
import urllib.parse

import accounts
import billing
import config
import db
import scheduler
import storetime

E = html.escape
SUPPORT = accounts.SUPPORT_EMAIL
PRICING = "https://getprodukto.com/pricing"


def _ago(ts):
    """'2 hours ago' for a timestamp, or 'never'."""
    if not ts:
        return "never"
    gap = max(0, time.time() - ts)
    if gap < 3600:
        return "%d minutes ago" % (gap // 60)
    if gap < 86400:
        hours = int(gap // 3600)
        return "%d hour%s ago" % (hours, "" if hours == 1 else "s")
    days = int(gap // 86400)
    return "%d day%s ago" % (days, "" if days == 1 else "s")


def _date(ts):
    """'November 13, 2026' — American order, the customers are mostly American."""
    t = time.gmtime(ts)
    return "%s %d, %d" % (time.strftime("%B", t), t.tm_mday, t.tm_year)


def _row(domain, scheduled_now, due_now):
    last = scheduler.last_scan_at(domain)
    # The store's own clock, matching the dashboard's "Updated" line.
    tz = storetime.zone(domain)
    when = "%s %s" % (storetime.label(last, tz), storetime.abbrev(tz)) if last else "—"
    if not scheduled_now:
        state = '<span class="pill pill-off">Held back</span>'
        next_up = "manual scans only"
    elif due_now:
        state = '<span class="pill pill-on">Daily</span>'
        next_up = "due now"
    else:
        state = '<span class="pill pill-on">Daily</span>'
        next_up = "next at %02d:00" % scheduler.slot_hour(domain)
    return ("<tr><td><b>%s</b></td><td>%s</td><td>%s</td>"
            "<td>%s<br><span class=\"small\">%s</span></td></tr>"
            % (E(domain), state, E(next_up), E(when), E(_ago(last))))


def _scans_card():
    on = set(scheduler.scheduled())
    due = set(scheduler.due())
    # Held-back stores stay off this page: it is shown on demos, and a
    # test catalog must never appear there (5 Oct 2026).
    stores = [d for d in accounts.visible(scheduler.scannable()) if d in on]
    if stores:
        rows = "".join(_row(d, d in on, d in due) for d in stores)
        table = ('<table class="settings-table"><thead><tr><th>Store</th><th>Scan</th>'
                 '<th>Next</th><th>Last scan</th></tr></thead><tbody>%s</tbody></table>' % rows)
    else:
        table = '<p class="small">No store has finished onboarding yet.</p>'
    window = ("Scans start between %02d:00 and %02d:00 local time. Each store keeps its"
              " own slot inside that window, so today's reading and yesterday's are"
              " taken at the same hour."
              % (config.SCAN_WINDOW_START,
                 (config.SCAN_WINDOW_START + config.SCAN_WINDOW_HOURS) % 24))
    return _card("Daily scans", "Every store you finish setting up is scanned once a day, so your"
                 " dashboard already holds today's reading when you open it.",
                 '<div class="set-body">%s<p class="set-hint">%s</p></div>' % (table, E(window)))


def _card(title, desc, body, foot="", cls=""):
    return ('<section class="set-card %s"><header><h2>%s</h2><p>%s</p></header>%s%s</section>'
            % (cls, E(title), desc, body, ('<footer>%s</footer>' % foot) if foot else ""))


def _account_card(user, q):
    err = q.get("pw_error", "")
    saved = q.get("saved") == "password"
    form = """<form method="post" action="/settings/password" class="set-pw" id="pw-form"%s>
<label>Current password<input type="password" name="current" autocomplete="current-password" required></label>
<label>New password<input type="password" name="new" autocomplete="new-password" minlength="10" required>
<small>At least 10 characters.</small></label>
<label>Repeat new password<input type="password" name="new2" autocomplete="new-password" minlength="10" required></label>
%s<div class="set-actions"><button type="submit" class="btn">Save password</button>
<button type="button" class="btn ghost" data-close-pw>Cancel</button></div></form>""" % (
        "" if err else " hidden", ('<p class="set-error" role="alert">%s</p>' % E(err)) if err else "")
    body = """<dl class="set-rows">
<div><dt>Email</dt><dd>%s</dd></div>
<div><dt>Password</dt><dd>%s<button type="button" class="btn ghost btn-sm" data-open-pw%s>Change password</button></dd></div>
</dl>%s""" % (E(user["email"]),
              '<span class="set-ok">Password updated.</span>' if saved else '<span class="set-mask">••••••••••</span>',
              " hidden" if err else "", form)
    foot = '<span class="set-muted">Signed in on this browser.</span><a class="btn ghost btn-sm" href="/logout">Sign out</a>'
    return _card("Account", "Your sign-in details.", body, foot)


def _usage(used, cap):
    pct = 100 if not cap else min(100, round(100 * used / cap))
    return ('<div class="set-meter"><span style="width:%d%%"></span></div>' % pct)


def _plan_card(user, store, sub, req, preview):
    key, name, price = billing.plan_for(user)
    cap = user.get("question_limit")
    ps = db.get_prompt_set(store) if store else None
    used = len(ps["prompts"]) if ps else 0
    stores_used = len(accounts.owned(user["id"])) if not preview else 1
    store_cap = user.get("store_limit") or 1
    if req and req["status"] == "scheduled":
        state = '<span class="pill pill-warn">Cancels %s</span>' % E(_date(req["ends_at"])) if req["ends_at"] else \
            '<span class="pill pill-warn">Cancelling</span>'
    elif req:
        state = '<span class="pill pill-warn">Cancellation requested</span>'
    else:
        state = '<span class="pill pill-on">Active</span>'
    price_html = ('<b>$%d</b><span>/month</span>' % price) if price else '<b>Custom</b>'
    renew = ""
    if sub and sub.get("ends_at") and not (req or sub.get("cancelling")):
        renew = '<div><dt>Next payment</dt><dd>%s</dd></div>' % E(_date(sub["ends_at"]))
    elif req and req["status"] == "scheduled" and req["ends_at"]:
        renew = '<div><dt>Access until</dt><dd>%s</dd></div>' % E(_date(req["ends_at"]))
    body = """<div class="set-plan"><div><span class="set-plan-name">%s</span>%s</div><div class="set-price">%s</div></div>
<dl class="set-rows">
<div><dt>Buyer questions</dt><dd><span class="set-usage"><b>%d</b> of %s tracked</span>%s</dd></div>
<div><dt>Stores</dt><dd><span class="set-usage"><b>%d</b> of %d</span></dd></div>
<div><dt>Products</dt><dd>Unlimited</dd></div>%s
</dl>""" % (E(name), state, price_html, used, (str(cap) if cap else "unlimited"),
            _usage(used, cap) if cap else "", stores_used, store_cap, renew)
    foot = ('<span class="set-muted">Need more questions or another store?</span>'
            '<span class="set-foot-btns"><a class="btn ghost btn-sm" href="%s" target="_blank" rel="noopener">Compare plans</a>'
            '<a class="btn btn-sm" href="mailto:%s?subject=%s">Change plan</a></span>'
            % (PRICING, SUPPORT, "Change%20my%20Produkto%20plan"))
    return _card("Plan & billing", "What you pay for and how much of it you use.", body, foot)


def _cancel_card(user, req, preview):
    if req:
        if req["status"] == "scheduled":
            text = ("Your plan is set to end%s. You won't be charged again, and your dashboard and daily"
                    " scans keep working until then." % (" on <b>%s</b>" % E(_date(req["ends_at"])) if req["ends_at"] else ""))
        else:
            text = ("We received your cancellation on %s. We'll stop your plan before your next payment"
                    " and confirm by email." % E(_date(req["requested_at"])))
        body = '<div class="set-body"><p class="set-text">%s</p></div>' % text
        foot = ('<span class="set-muted">Changed your mind?</span>'
                '<form method="post" action="/settings/keep"><button type="submit" class="btn btn-sm">Keep my plan</button></form>')
        return _card("Cancellation", "", body, foot, "set-danger")
    reasons = "".join('<label class="set-radio"><input type="radio" name="reason" value="%s"%s><span>%s</span></label>'
                      % (E(r), " required" if i == 0 else "", E(r)) for i, r in enumerate(billing.REASONS))
    body = """<div class="set-body"><p class="set-text">Your plan stays active until the end of the period you've paid for.
After that, daily scans stop and you won't be charged again.</p></div>
<dialog id="cancel-dialog" class="set-dialog" aria-labelledby="cancel-title">
<form method="post" action="/settings/cancel">
<h3 id="cancel-title">Cancel your %s plan?</h3>
<p>Your dashboard and daily scans keep working until the end of your billing period. After that, scans stop and you won't be charged again.</p>
<fieldset><legend>What's the main reason you're leaving?</legend>%s</fieldset>
<label class="set-note"><span class="set-note-q">Anything we could have done better? <span>(optional)</span></span>
<textarea name="note" rows="3"></textarea></label>
%s<div class="set-actions"><button type="button" class="btn" data-close-cancel autofocus>Keep my plan</button>
<button type="submit" class="btn btn-danger"%s>Cancel plan</button></div>
</form></dialog>""" % (E(billing.plan_for(user)[1]), reasons,
                       '<p class="set-hint">Admin preview: this is what customers see. Admin accounts have no plan to cancel.</p>' if preview else "",
                       " disabled" if preview else "")
    foot = ('<span class="set-muted">You can keep using Produkto until your period ends.</span>'
            '<button type="button" class="btn btn-danger-ghost btn-sm" data-open-cancel>Cancel plan</button>')
    return _card("Cancel plan", "Stop your subscription.", body, foot, "set-danger")


SCRIPT = """<script>
(()=>{const $=s=>document.querySelector(s);
const pw=$('#pw-form'),open=$('[data-open-pw]');
open&&open.addEventListener('click',()=>{pw.hidden=false;open.hidden=true;pw.querySelector('input').focus();});
$('[data-close-pw]')&&$('[data-close-pw]').addEventListener('click',()=>{pw.hidden=true;open.hidden=false;});
const d=$('#cancel-dialog');
$('[data-open-cancel]')&&$('[data-open-cancel]').addEventListener('click',()=>d.showModal());
$('[data-close-cancel]')&&$('[data-close-cancel]').addEventListener('click',()=>d.close());
})();
</script>"""


_NEW_KEYS = {}     # user id -> key just made, shown once on the next page load


def _mcp_card(user):
    key = _NEW_KEYS.pop(user["id"], None)
    info = accounts.mcp_key_info(user["id"])
    url = accounts.base_url().rstrip("/") + "/mcp"
    if key:
        status = ('<p class="set-notice">Copy this key now. It won\'t be shown again.</p>'
                  '<pre class="set-key">%s</pre>' % E(key))
    elif info:
        status = '<p class="set-hint">Key made %s, last used %s.</p>' % (_ago(info["created_at"]), _ago(info["last_used"]))
    else:
        status = '<p class="set-hint">No key yet.</p>'
    setup = ("claude mcp add --transport http produkto %s --header \"Authorization: Bearer %s\""
             % (url, key or "YOUR_KEY"))
    import mcp_oauth
    apps = mcp_oauth.connections(user["id"])
    linked = "".join('<li>%s, connected %s <form method="post" action="/settings/mcp-key" style="display:inline">'
                     '<input type="hidden" name="client" value="%s"><button name="do" value="disconnect">Disconnect</button>'
                     '</form></li>' % (E(a["name"]), _ago(a["last"]), E(a["client_id"])) for a in apps)
    body = ('<div class="set-body"><p class="set-hint"><b>Claude, ChatGPT and other assistants:</b> add a custom connector '
            'with this address and sign in with your Produkto login.</p><pre class="set-key">%s</pre>%s'
            '<p class="set-hint" style="margin-top:20px"><b>Claude Code, Cursor and scripts</b> can use a key instead.</p>%s'
            '<pre class="set-key">%s</pre></div>'
            % (E(url), ('<p class="set-hint">Connected:</p><ul class="set-hint">%s</ul>' % linked) if linked else "",
               status, E(setup)))
    foot = ('<form method="post" action="/settings/mcp-key"><button name="do" value="new">%s</button>%s</form>'
            % ("Replace key" if info else "Create key",
               ' <button name="do" value="revoke">Turn off</button>' if info else ""))
    return _card("Connect your AI assistant", "Ask Claude or another AI assistant about your store's "
                 "visibility, products and opportunities. It can read your dashboard; it can't change anything.",
                 body, foot)


def act_mcp_key(_q, form):
    user = accounts.current()
    if form.get("do") == "revoke":
        accounts.revoke_mcp_key(user["id"])
    elif form.get("do") == "disconnect":
        import mcp_oauth
        mcp_oauth.revoke(user["id"], form.get("client"))
    else:
        _NEW_KEYS[user["id"]] = accounts.new_mcp_key(user["id"])
    return 303, "/settings#mcp"


def settings(q=None):
    q = q or {}
    user = accounts.current()
    if not user:
        return 200, '<div class="plain-page set-page"><h1>Settings</h1>%s</div>' % _scans_card()
    preview = bool(user["is_admin"])
    shown = dict(user)
    if preview:     # Kelian sees a customer's view, with nothing he can submit.
        shown.update(question_limit=accounts.PLANS["growth"], store_limit=1)
    stores = sorted(accounts.owned(user["id"]))
    store = q.get("d") or (stores[0] if stores else "")
    if preview and not store:
        visible = accounts.visible(scheduler.scheduled())
        store = visible[0] if visible else ""
    req = None if preview else billing.open_request(user["id"])
    sub = None if preview else billing.subscription(user)
    notice = ""
    if q.get("cancel") == "scheduled":
        notice = '<p class="set-notice">Your plan is cancelled. It stays active until the end of your billing period.</p>'
    elif q.get("cancel") == "requested":
        notice = '<p class="set-notice">We received your cancellation and will confirm by email.</p>'
    elif q.get("keep_error"):
        notice = ('<p class="set-notice set-notice-err">We couldn\'t undo the cancellation just now. Email '
                  '<a href="mailto:%s">%s</a> and we\'ll keep your plan running.</p>' % (SUPPORT, SUPPORT))
    elif q.get("kept"):
        notice = '<p class="set-notice">Your plan continues as before.</p>'
    body = """<div class="plain-page set-page"><h1>Settings</h1>
<p class="page-description">Your account, your plan, and your store's daily scans.</p>%s
%s%s%s%s%s</div>%s""" % (notice, _account_card(user, q), _plan_card(shown, store, sub, req, preview),
                       _scans_card(), _mcp_card(user), _cancel_card(shown, req, preview), SCRIPT)
    return 200, body


# --- form posts -----------------------------------------------------------------

def act_password(_q, form):
    user = accounts.current()
    err = billing.change_password(user, form.get("current"), form.get("new"), form.get("new2"))
    if err:
        return 303, "/settings?pw_error=" + urllib.parse.quote(err)
    return 303, "/settings?saved=password"


def act_cancel(_q, form):
    user = accounts.current()
    if user["is_admin"]:
        return 303, "/settings"
    if billing.open_request(user["id"]):
        return 303, "/settings"
    status = billing.cancel(user, form.get("reason", ""), form.get("note", ""))
    return 303, "/settings?cancel=" + status


def act_keep(_q, _form):
    user = accounts.current()
    if billing.undo(user):
        return 303, "/settings?kept=1"
    return 303, "/settings?keep_error=1"
