"""Instagram photos for AEO articles (20 Oct 2026).

Kelian: DTC stores often live on Instagram, so their best lifestyle photos are there, not on the product pages.
The owner clicks "Get photos from Instagram" (Settings > Look and lessons); we read the store's own
Instagram (the handle linked from its homepage, or the one the owner types), keep the photo posts, and copy each
photo into our own storage (content_media, the same table as the owner's uploads). Instagram's photo links expire
after a few days, so a copy is the only way an article can keep using one. From there they behave exactly like an
upload: they show in the article photo picker, and on publish they are copied into the store's Shopify Files
(shopify_connect.host_uploads), so the live article never depends on Instagram or on us.

Cost: Apify `apify/instagram-post-scraper`, $0.0015 a post on Bronze. MAX_POSTS = 30 -> about 5 cents a read.
Only when the owner clicks, and at most once every COOLDOWN days. Instagram refuses free scripted reads (401).

Only the store's OWN account: the owner picks which photos go into an article, so a reposted customer photo is
their call, the same as on their own feed.
"""
import json
import re
import threading
import time
import urllib.request

import db

ACTOR = 'apify~instagram-post-scraper'
MAX_POSTS = 30
MAX_PHOTOS = 40              # photos kept per read (a carousel post can hold several)
PRICE_PER_POST = 0.0015
COOLDOWN = 7 * 86400
MAX_BYTES = 4_000_000
_HANDLE = re.compile(r'instagram\.com/([A-Za-z0-9_.]{2,30})/?(?=["\'?#\s<]|$)', re.I)
_NOT_HANDLES = {'p', 'reel', 'reels', 'explore', 'accounts', 'stories', 'tv', 'about', 'developer', 'legal',
                'instagram', 'sharer', 'share', 'direct', 'web'}
_running = set()


def init():
    import article_learning
    article_learning._media_init()
    with db.conn() as c:
        cols = [r[1] for r in c.execute('PRAGMA table_info(content_media)')]
        if 'source' not in cols:
            c.execute('ALTER TABLE content_media ADD COLUMN source TEXT')
        if 'meta' not in cols:
            c.execute('ALTER TABLE content_media ADD COLUMN meta TEXT')


def clean_handle(text):
    """'@clubhouse.skin', 'instagram.com/clubhouse.skin/' or 'clubhouse.skin' -> 'clubhouse.skin'; '' if not a handle."""
    t = (text or '').strip()
    m = _HANDLE.search(t + ' ')
    t = m.group(1) if m else t.lstrip('@').strip('/')
    t = t.lower()
    return t if re.fullmatch(r'[a-z0-9_.]{2,30}', t) and t not in _NOT_HANDLES else ''


def find_handle(domain):
    """The Instagram account the store links to from its homepage (free). '' if none."""
    import brand_style
    try:
        html = brand_style._fetch('https://%s/' % domain)
    except Exception:                                                       # noqa: BLE001 - site unreachable
        return ''
    found = [h.lower() for h in _HANDLE.findall(html) if h.lower() not in _NOT_HANDLES]
    return max(set(found), key=found.count) if found else ''


def state(domain):
    import content_setup
    return content_setup.get(domain).get('instagram') or {}


def _put(domain, **kw):
    import content_setup
    s = content_setup.get(domain)
    ig = dict(s.get('instagram') or {})
    ig.update(kw)
    s['instagram'] = ig
    content_setup.put(domain, s)
    return ig


def handle(domain):
    """The owner's handle if they typed one, else the one linked from the homepage (looked up once)."""
    st = state(domain)
    if st.get('handle'):
        return st['handle']
    if 'found' not in st:
        st = _put(domain, found=find_handle(domain))
    return st.get('found') or ''


def set_handle(domain, text):
    h = clean_handle(text)
    if text.strip() and not h:
        raise ValueError('That doesn\'t look like an Instagram handle.')
    _put(domain, handle=h)
    return h


def photos(domain):
    """Media URLs of the store's Instagram photos, newest post first."""
    import article_learning
    try:
        init()
        rows = db.all_("SELECT token FROM content_media WHERE store_domain=? AND source='instagram' "
                       "ORDER BY created_at DESC LIMIT ?", (domain, MAX_PHOTOS))
    except Exception:                                                       # noqa: BLE001
        return []
    return [article_learning.media_url(r['token']) for r in rows]


def wait_left(domain):
    """Seconds until the owner may read Instagram again (0 = now)."""
    st = state(domain)
    if st.get('status') != 'done':
        return 0
    return max(0, int((st.get('at') or 0) + COOLDOWN - time.time()))


def running(domain):
    return domain in _running


def start(domain):
    """Read the store's Instagram in the background. Raises ValueError with a plain reason if it can't start."""
    h = handle(domain)
    if not h:
        raise ValueError('Add your Instagram handle first.')
    if running(domain):
        return
    if wait_left(domain):
        raise ValueError('Instagram was read less than a week ago. You can read it again in %d days.'
                         % max(1, wait_left(domain) // 86400))
    _running.add(domain)
    _put(domain, status='running', started=time.time(), error='')

    def go():
        try:
            n, cost = fetch(domain, h)
            _put(domain, status='done', at=time.time(), count=n, cost=cost, read_handle=h)
        except Exception as e:                                              # noqa: BLE001 - shown to the owner
            _put(domain, status='failed', error=str(e)[:200])
        finally:
            _running.discard(domain)
    threading.Thread(target=go, daemon=True).start()


def _posts(h, limit):
    """Apify run -> its dataset items, and the run's cost in dollars (None if Apify didn't say)."""
    import apify_answers
    run = apify_answers._request('POST', '/acts/%s/runs?waitForFinish=240' % ACTOR, dict(
        username=[h], resultsLimit=limit, skipPinnedPosts=False, dataDetailLevel='basicData'), timeout=300)['data']
    for _ in range(30):
        if run.get('status') in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'):
            break
        time.sleep(10)
        run = apify_answers._request('GET', '/actor-runs/%s' % run['id'])['data']
    if run.get('status') != 'SUCCEEDED':
        raise RuntimeError('Reading Instagram didn\'t finish (%s). Try again later.' % (run.get('status') or 'no answer'))
    items = apify_answers._request('GET', '/datasets/%s/items?clean=true' % run['defaultDatasetId'], timeout=120)
    return items, run.get('usageTotalUsd')


def picks(items):
    """[(image url, post url, caption, post id)] from photo posts, newest first; videos and reels skipped."""
    out = []
    for it in items or []:
        if it.get('error') or (it.get('type') or '').lower() == 'video' or it.get('isVideo'):
            continue
        urls = [u for u in (it.get('images') or []) if isinstance(u, str)] or [it.get('displayUrl')]
        for k in it.get('childPosts') or []:
            if k.get('displayUrl') and (k.get('type') or '').lower() != 'video' and k['displayUrl'] not in urls:
                urls.append(k['displayUrl'])
        post = it.get('url') or ('https://www.instagram.com/p/%s/' % it['shortCode'] if it.get('shortCode') else '')
        pid = str(it.get('id') or it.get('shortCode') or post)
        for j, u in enumerate([u for u in urls if u][:4]):
            out.append((u, post, (it.get('caption') or '')[:200], '%s#%d' % (pid, j)))
    return out


def _download(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'image/*'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(MAX_BYTES + 1)
        mime = (r.headers.get_content_type() or '').lower()
    if len(raw) > MAX_BYTES:
        raise ValueError('too large')
    sig = raw[:12]
    if sig.startswith(b'\xff\xd8'):
        return 'image/jpeg', raw
    if sig.startswith(b'\x89PNG'):
        return 'image/png', raw
    if sig[:4] == b'RIFF' and sig[8:12] == b'WEBP':
        return 'image/webp', raw
    raise ValueError('not a photo (%s)' % mime)


def save(domain, found):
    """Copy new photos into content_media (skipping ones already kept). Returns how many were added."""
    import secrets
    init()
    have = set()
    for r in db.all_("SELECT meta FROM content_media WHERE store_domain=? AND source='instagram'", (domain,)):
        try:
            have.add(json.loads(r['meta'] or '{}').get('id'))
        except ValueError:
            pass
    added, now = 0, time.time()
    for n, (url, post, caption, pid) in enumerate(found[:MAX_PHOTOS]):
        if pid in have:
            continue
        try:
            mime, raw = _download(url)
        except Exception:                                                   # noqa: BLE001 - skip one bad photo
            continue
        db.write('INSERT INTO content_media (token, store_domain, mime, data, created_at, source, meta) '
                 'VALUES (?,?,?,?,?,?,?)', (secrets.token_urlsafe(18), domain, mime, raw, now - n, 'instagram',
                                            json.dumps(dict(id=pid, post=post, caption=caption))))
        added += 1
    return added


def fetch(domain, h, limit=MAX_POSTS):
    items, cost = _posts(h, limit)
    if not items or all(it.get('error') for it in items):
        raise RuntimeError('No posts came back for @%s. Check the handle, and that the account is public.' % h)
    n = save(domain, picks(items))
    return n, cost if cost is not None else round(len(items) * PRICE_PER_POST, 4)

