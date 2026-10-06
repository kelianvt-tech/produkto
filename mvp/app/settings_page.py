"""Settings: the one setting Produkto has.

It answers one question — is this store being scanned every day, and
when did it last happen? That is the only setting Produkto has, so the page
shows it plainly rather than pretending to a preferences screen. It is
read-only: the stores held back live in config.DAILY_SCAN_EXCLUDE, and
changing that is a code change, not a click.
"""

import html
import time

import config
import accounts
import scheduler
import storetime

E = html.escape


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


def settings(_q=None):
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
    body = """<div class="plain-page"><h1>Settings</h1>
<p class="page-description">Every store you finish setting up is scanned once a day, so a dashboard already holds today's reading when you open it.</p>
<section><h2>Daily scans</h2>%s<p class="small">%s</p></section>
</div>""" % (table, E(window))
    return 200, body
