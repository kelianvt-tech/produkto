"""Is a cited page still there? One plain request per URL, cached for 3 days.

Only "dead" (404/410) is shown to the merchant. Bot blocks, timeouts and
server errors come back "unknown": we can't tell, so we don't claim a broken page.
"""
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import db

TTL = 3 * 86400
MAX_URLS = 60
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'


def _public(url):
    """Refuse anything that resolves to a private or local address."""
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname:
        return False
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(u.hostname, None)}
    except OSError:
        return False
    return all(ipaddress.ip_address(a.split('%')[0]).is_global for a in addrs)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _public(newurl):
            raise urllib.error.URLError('redirect to non-public address')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def _probe(url):
    if not _public(url):
        return 'unknown'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html'})
    try:
        with _opener.open(req, timeout=8) as r:
            r.read(2048)
            return 'ok'
    except urllib.error.HTTPError as e:
        return 'dead' if e.code in (404, 410) else 'unknown'
    except Exception:
        return 'unknown'


def _table():
    db.write('CREATE TABLE IF NOT EXISTS link_checks (url TEXT PRIMARY KEY, status TEXT, checked_at REAL)')


def check(urls):
    _table()
    urls = [u for u in dict.fromkeys(urls) if u][:MAX_URLS]
    out, todo = {}, []
    for u in urls:
        row = db.one('SELECT status, checked_at FROM link_checks WHERE url=?', (u,))
        if row and row['checked_at'] > time.time() - TTL:
            out[u] = row['status']
        else:
            todo.append(u)
    with ThreadPoolExecutor(8) as pool:
        for u, status in zip(todo, pool.map(_probe, todo)):
            out[u] = status
            db.write('INSERT OR REPLACE INTO link_checks(url,status,checked_at) VALUES (?,?,?)', (u, status, time.time()))
    return out


def api(q, form):
    """POST /api/linkcheck  urls=<one URL per line>"""
    return 200, ('json', json.dumps(check(form.get('urls', '').splitlines())))
