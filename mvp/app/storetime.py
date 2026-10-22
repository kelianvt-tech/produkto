"""What day it is *for the merchant*, not for the machine running Produkto.

Every date on the dashboard used to come from `dt.date.fromtimestamp()`, which
reads the server's clock. Run the server in Barcelona and sell to a brand in
California and the labels are wrong in a way the merchant can see: a scan taken
at 06:00 CEST is 21:00 the previous day in Los Angeles, and a merchant checking
in their evening can be shown a point dated tomorrow. A date in the future is
the fastest way to lose someone's trust in a number.

So dates are formed in the store's own timezone, taken from the country that
Shopify publishes in /meta.json and that `catalog.store_meta()` already saves.

One zone per country, chosen as the one that keeps a morning scan on the right
date across the whole country: for the US that is America/New_York, because a
06:00 Eastern scan is still the same calendar day in Hawaii. Countries that
genuinely straddle days are listed individually; anything unknown falls back to
UTC rather than to the server's clock, so the failure is neutral instead of
silently Spanish.
"""

import datetime as dt

try:
    from zoneinfo import ZoneInfo
except ImportError:                                             # pragma: no cover
    ZoneInfo = None

import db

# Representative zone per country. Populous/eastern-most-reasonable choice, so
# an early-morning scan lands on the correct date everywhere in that country.
ZONES = {
    'US': 'America/New_York', 'CA': 'America/Toronto', 'MX': 'America/Mexico_City',
    'BR': 'America/Sao_Paulo', 'AR': 'America/Argentina/Buenos_Aires',
    'GB': 'Europe/London', 'IE': 'Europe/Dublin', 'PT': 'Europe/Lisbon',
    'ES': 'Europe/Madrid', 'FR': 'Europe/Paris', 'DE': 'Europe/Berlin',
    'NL': 'Europe/Amsterdam', 'BE': 'Europe/Brussels', 'IT': 'Europe/Rome',
    'CH': 'Europe/Zurich', 'AT': 'Europe/Vienna', 'DK': 'Europe/Copenhagen',
    'SE': 'Europe/Stockholm', 'NO': 'Europe/Oslo', 'FI': 'Europe/Helsinki',
    'PL': 'Europe/Warsaw', 'CZ': 'Europe/Prague', 'GR': 'Europe/Athens',
    'AU': 'Australia/Sydney', 'NZ': 'Pacific/Auckland', 'JP': 'Asia/Tokyo',
    'SG': 'Asia/Singapore', 'HK': 'Asia/Hong_Kong', 'IN': 'Asia/Kolkata',
    'AE': 'Asia/Dubai', 'IL': 'Asia/Jerusalem', 'ZA': 'Africa/Johannesburg',
}
FALLBACK = 'UTC'

_cache = {}


def _chosen(domain):
    """A zone the merchant picked in the agent's setup (content_settings), if any. Country is the fallback."""
    try:
        import json
        row = db.one('SELECT data FROM content_settings WHERE store_domain=?', (domain,))
        return (json.loads(row['data']) if row and row['data'] else {}).get('timezone') or None
    except Exception:                                           # noqa: BLE001 - table not made yet
        return None


def zone_name(domain):
    """The IANA zone name for a store, e.g. 'America/New_York'."""
    if not domain:
        return FALLBACK
    if domain not in _cache:
        chosen = _chosen(domain)
        row = db.one('SELECT country FROM stores WHERE domain=?', (domain,))
        country = ((row['country'] if row else '') or '').strip().upper()
        _cache[domain] = chosen or ZONES.get(country, FALLBACK)
    return _cache[domain]


def forget(domain=None):
    """Drop the cached zone, for when a store's country is re-read."""
    _cache.pop(domain, None) if domain else _cache.clear()


def zone(domain):
    """The store's timezone, or None if this Python has no zone database.

    None is handled everywhere it is used: the caller falls back to the
    server's clock, which is what the dashboard did before."""
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(zone_name(domain))
    except Exception:                                           # noqa: BLE001
        try:
            return ZoneInfo(FALLBACK)
        except Exception:                                       # noqa: BLE001
            return None


def date_of(ts, tz):
    """The calendar date a timestamp falls on, in that store's zone."""
    if tz is None:
        return dt.date.fromtimestamp(ts)
    return dt.datetime.fromtimestamp(ts, tz).date()


def now(tz):
    """The store's local 'now'."""
    return dt.datetime.now(tz) if tz is not None else dt.datetime.now()


def today(tz):
    return now(tz).date()


def day_bounds(day, tz):
    """(start, end) unix timestamps for a calendar day in that store's zone."""
    if tz is None:
        start = dt.datetime.combine(day, dt.time.min).timestamp()
        end = dt.datetime.combine(day, dt.time.max).timestamp()
        return start, end
    start = dt.datetime.combine(day, dt.time.min, tz).timestamp()
    end = dt.datetime.combine(day, dt.time.max, tz).timestamp()
    return start, end


def label(ts, tz, fmt='%-d %b, %H:%M'):
    """A timestamp written the way the merchant's own clock shows it."""
    if tz is None:
        return dt.datetime.fromtimestamp(ts).strftime(fmt)
    return dt.datetime.fromtimestamp(ts, tz).strftime(fmt)


def abbrev(tz):
    """'EDT', 'CEST' - what to print next to a time so it is unambiguous."""
    if tz is None:
        import time as _t
        return _t.tzname[_t.localtime().tm_isdst > 0]
    return dt.datetime.now(tz).strftime('%Z')
