"""Start one scan per store per day, without anyone clicking anything.

The dashboard plots a point per day, so a day needs a scan. This wakes every
few minutes, asks "which stores have not been scanned today?", and starts one
for each. That is the whole idea; the care is all in not scanning twice.

Three things keep a store from being scanned twice in a day:

  * `due()` only returns a store whose last scan STARTED before today's slot;
  * `scan.start` refuses while that store already has a running scan, and
    hands back the running token instead;
  * a store is only due once its slot time has passed, and the slot is fixed
    per store, so a restart at any hour of the day changes nothing.

Stores are spread across a window (config.SCAN_WINDOW_*) by hashing the
domain, so twenty stores do not all hit Apify in the same minute. The spread
is deterministic: a store keeps its slot from one day to the next, which is
what makes "yesterday's point" and "today's point" a fair comparison.

A failed scan is NOT retried today. A retry would buy a second set of answers
for the same date and put two points on one day; the honest thing is a gap in
the line, which is what the chart shows.
"""

import datetime as dt
import threading
import time
import zlib

import config
import db
import scan
import storetime

_stop = threading.Event()
_thread = None


def slot_hour(domain):
    """The hour this store's daily scan may start, fixed for that store."""
    if config.SCAN_WINDOW_HOURS <= 1:
        return config.SCAN_WINDOW_START % 24
    spread = zlib.crc32(domain.encode()) % config.SCAN_WINDOW_HOURS
    return (config.SCAN_WINDOW_START + spread) % 24


def slot_today(domain, now=None):
    """Unix time of this store's slot on the store's own current day.

    The store's clock, not the server's. A brand in California wants its scan
    finished before its own morning; timing it off a Barcelona server puts the
    reading most of a day out and labels it with the wrong date."""
    now = time.time() if now is None else now
    tz = storetime.zone(domain)
    day = storetime.date_of(now, tz)
    if tz is None:
        t = time.localtime(now)
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday,
                            slot_hour(domain), 0, 0, 0, 0, -1))
    return dt.datetime.combine(day, dt.time(slot_hour(domain)), tz).timestamp()


def scannable():
    """Stores that could be scanned: they have buyer questions saved.

    The domain check is not decoration. Prompt sets from before catalog-wide
    scanning were tied to a single product and carry no store_domain, and a
    null domain reaches scan.start as a store that does not exist."""
    return [r["store_domain"] for r in db.all_(
        "SELECT DISTINCT store_domain FROM prompt_sets"
        " WHERE store_domain IS NOT NULL AND TRIM(store_domain) <> ''"
        " AND prompts IS NOT NULL AND prompts <> '' AND prompts <> '[]'"
        " ORDER BY store_domain")]


def scheduled():
    """Stores that receive automatic daily scans.

    Every store that finished onboarding is in, because the point of the daily
    scan is that a dashboard already holds today's reading when it is opened.
    config.DAILY_SCAN_EXCLUDE holds the few stores kept out of it, and a store
    whose customer has been disabled (cancelled subscription) is out too."""
    import accounts
    held = set(config.DAILY_SCAN_EXCLUDE) | accounts.paused_stores()
    return [domain for domain in scannable() if domain not in held]


def last_scan_at(domain):
    """When this store's most recent scan STARTED, or None. Start, not finish:
    a scan that began today has used today's slot even if it is still running
    or ended badly."""
    row = db.one("SELECT MAX(s.run_at) AS t FROM scans s JOIN prompt_sets p"
                 " ON p.id = s.prompt_set_id WHERE p.store_domain = ?", (domain,))
    return row["t"] if row and row["t"] else None


def due(now=None):
    """Stores whose slot has passed today and that have not been scanned since."""
    now = time.time() if now is None else now
    out = []
    for domain in scheduled():
        slot = slot_today(domain, now)
        if now < slot:
            continue                       # today's slot is still ahead
        last = last_scan_at(domain)
        if last is not None and last >= slot:
            continue                       # already used today's slot
        out.append(domain)
    return out


def run_due(now=None):
    """Start a scan for every store that is due. Returns the domains started."""
    started = []
    for domain in due(now):
        try:
            scan.start(domain)
            started.append(domain)
        except Exception as e:
            # A store with no questions, a locked database, Apify down. Log it
            # and carry on: one broken store must not stop the other stores.
            print("scheduler: %s could not be scanned today (%s)" % (domain, e))
    return started


def _loop():
    while not _stop.is_set():
        try:
            for domain in run_due():
                print("scheduler: started today's scan for %s" % domain)
        except Exception as e:
            print("scheduler: tick failed (%s)" % e)
        try:
            import billing
            for email in billing.end_due():
                print("scheduler: %s's plan ended, account switched off" % email)
        except Exception as e:
            print("scheduler: plan end check failed (%s)" % e)
        if config.SHOW_CONTENT_AGENT or config.CONTENT_AGENT_ADMIN_ONLY:
            try:
                import shopify_connect
                done, failed = shopify_connect.publish_due()
                for did in done:
                    print("scheduler: published content draft %d on its calendar date" % did)
                for did, why in failed:
                    print("scheduler: content draft %d could not be published (%s)" % (did, why))
            except Exception as e:
                print("scheduler: calendar publishing failed (%s)" % e)
            try:
                import agent_review
                for domain in agent_review.run_due():
                    print("scheduler: monthly self-review for %s" % domain)
            except Exception as e:
                print("scheduler: monthly self-review failed (%s)" % e)
            try:
                import monthly_articles
                for domain in monthly_articles.run_due():
                    print("scheduler: writing this month's articles for %s" % domain)
            except Exception as e:
                print("scheduler: monthly articles failed (%s)" % e)
        _stop.wait(config.SCHEDULER_TICK_SECONDS)


def start():
    """Begin the daily loop. Does nothing unless config.DAILY_SCANS is on."""
    global _thread
    if not config.DAILY_SCANS or (_thread and _thread.is_alive()):
        return None
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="scheduler")
    _thread.start()
    return _thread


def stop():
    _stop.set()
