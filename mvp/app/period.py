"""The dashboard period: a date range plus a grouping (day / week / month / quarter).

Every Overview panel is calculated from the scans inside this period. The
browser chart code in insight_panels.CHART_SCRIPT uses the same rules:
local time, weeks start on Monday, "Last N days" ends today.
Daily is the default because scans run once a day (scheduler.py): each day's
scan is its own point. Week, month and quarter pool those daily scans into
calmer points for anyone who wants them.
"""
import datetime as dt
import time

import config
import db
import storetime

RANGES = {'7': 'Last 7 days', '30': 'Last 30 days', '90': 'Last 90 days', '365': 'Last 365 days'}
GROUPS = {'day': 'Daily', 'week': 'Weekly', 'month': 'Monthly', 'quarter': 'Quarterly'}
DEFAULT_GROUP = 'day'
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
         'September', 'October', 'November', 'December']


def parse(query):
    """Read range/group/from/to from the page address, falling back to defaults."""
    q = query or {}
    rng, group = q.get('range') or '30', q.get('group') or DEFAULT_GROUP
    frm, to = q.get('from') or '', q.get('to') or ''
    if group not in GROUPS:
        group = DEFAULT_GROUP
    if rng == 'custom':
        try:
            dt.date.fromisoformat(frm)
            dt.date.fromisoformat(to)
        except ValueError:
            rng = '30'
    elif rng not in RANGES:
        rng = '30'
    return dict(range=rng, group=group, frm=frm, to=to)


def bounds(per, today=None, tz=None):
    """First day, last day, and the matching start/end timestamps.

    `tz` is the store's timezone (storetime.zone). "Last 30 days" has to mean
    the merchant's last 30 days, not the server's, or a brand in California
    loses or gains a day at each end of the range."""
    if per['range'] == 'custom':
        a, b = dt.date.fromisoformat(per['frm']), dt.date.fromisoformat(per['to'])
        if a > b:
            a, b = b, a
    else:
        b = today or storetime.today(tz)
        a = b - dt.timedelta(days=int(per['range']) - 1)
    start, _ = storetime.day_bounds(a, tz)
    # day_bounds already ends at 23:59:59.999999, so no fudge factor here:
    # adding one would push the window into the next day.
    _, end = storetime.day_bounds(b, tz)
    return a, b, start, end


def bucket_start(d, group):
    if group == 'day':
        return d
    if group == 'week':
        return d - dt.timedelta(days=d.weekday())
    if group == 'month':
        return d.replace(day=1)
    return d.replace(day=1, month=(d.month - 1) // 3 * 3 + 1)


def next_bucket(d, group):
    if group == 'day':
        return d + dt.timedelta(days=1)
    if group == 'week':
        return d + dt.timedelta(days=7)
    m = d.month - 1 + (1 if group == 'month' else 3)
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def bucket_starts(a, b, group):
    out, d = [], bucket_start(a, group)
    while d <= b:
        out.append(d)
        d = next_bucket(d, group)
    return out


def short_label(d, group):
    if group in ('day', 'week'):
        return '%d %s' % (d.day, MON[d.month - 1])
    if group == 'month':
        return '%s %d' % (MON[d.month - 1], d.year)
    return 'Q%d %d' % ((d.month - 1) // 3 + 1, d.year)


def long_label(d, group):
    if group == 'day':
        return '%d %s %d' % (d.day, MON[d.month - 1], d.year)
    if group == 'week':
        return 'Week of %d %s %d' % (d.day, MON[d.month - 1], d.year)
    if group == 'month':
        return '%s %d' % (MONTH[d.month - 1], d.year)
    return short_label(d, group)


def describe(a, b):
    return '%d %s %d – %d %s %d' % (a.day, MON[a.month - 1], a.year, b.day, MON[b.month - 1], b.year)


def done_scans(prompt_set_id, start=None, end=None):
    """Finished, scored scans for every question-set version of this store,
    oldest first. Editing questions after a scan saves a new version; pooling
    the versions keeps each unchanged question's history, while
    evidence.load() counts only questions in the set being viewed.

    Skips anything before the store's config.HISTORY_START date."""
    sql = ("SELECT s.* FROM scans s JOIN scores sc ON sc.scan_id = s.id "
           "JOIN prompt_sets ps ON ps.id = s.prompt_set_id "
           "WHERE s.prompt_set_id IN (SELECT id FROM prompt_sets WHERE store_domain = "
           "(SELECT store_domain FROM prompt_sets WHERE id = ?)) AND s.status IN ('done','partial')")
    args = [prompt_set_id]
    if start is not None:
        sql += " AND s.run_at BETWEEN ? AND ?"
        args += [start, end]
    for domain, day in config.HISTORY_START.items():
        sql += " AND NOT (ps.store_domain = ? AND s.run_at < ?)"
        args += [domain, dt.datetime.strptime(day, "%Y-%m-%d").replace(
            tzinfo=dt.timezone.utc).timestamp()]
    return db.all_(sql + " ORDER BY s.run_at", args)
