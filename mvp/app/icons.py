"""Brand logos for the rankings, fetched once and cached on disk.

Most brand sites don't serve a plain /favicon.ico, so this reads the site's
own <link rel="icon"> and stores whatever it points at under icons/. Nothing
goes to a third-party favicon service: the request is ours, the cache is ours.

A miss is cached too (as an empty file), so a brand without a usable logo
isn't re-fetched on every page load; the initials tile stays underneath.
"""
import os
import re
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# v2: icons are now picked largest-first (2026-09-23). The old folder holds
# whichever tiny favicon came first; it is left alone, just no longer read.
CACHE = os.path.join(HERE, "icons", "v2")
# A browser user-agent: several brand sites refuse anything else, and this
# request only ever fetches a public logo.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
TYPES = {".ico": "image/x-icon", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp",
         ".gif": "image/gif"}
MAX_BYTES = 300_000
RETRY_MISS_AFTER = 7 * 24 * 3600
_lock = threading.Lock()
_locks = {}


def _domain_lock(domain):
    """One download per domain at a time; different domains run in parallel.
    (A single shared lock used to queue every logo behind the slowest site.)"""
    with _lock:
        return _locks.setdefault(domain, threading.Lock())


# Background warming: page views never fetch from brand sites; they queue the
# fetch here and show the logo/initials now, the photo on a later view.
from concurrent.futures import ThreadPoolExecutor as _Pool
_pool = _Pool(max_workers=6)
_queued = set()


def warm(fn, *args):
    key = (fn.__name__,) + args
    with _lock:
        if key in _queued:
            return
        _queued.add(key)

    def run():
        try:
            fn(*args)
        except Exception:                                       # noqa: BLE001
            pass
        finally:
            with _lock:
                _queued.discard(key)
    _pool.submit(run)


def _safe(domain):
    d = (domain or "").strip().lower()
    return d if re.fullmatch(r"[a-z0-9.-]{3,80}", d or "") and "." in d else ""


def _get(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise ValueError(r.status)
        return r.read(MAX_BYTES + 1), (r.headers.get("Content-Type") or "").split(";")[0].strip()


def _candidates(domain):
    """The site's declared icon first, then the conventional path."""
    out = []
    try:
        html, _ = _get("https://%s/" % domain, timeout=7)
        head = html[:200_000].decode("utf-8", "ignore")
        found = []
        for m in re.finditer(r'<link[^>]+rel=["\']?[^"\'>]*icon[^"\'>]*["\']?[^>]*>', head, re.I):
            tag = m.group(0)
            href = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
            if not href:
                continue
            # Sharpest first: apple-touch-icon (180px), then the largest
            # declared size, then SVG. A 16px favicon is the last resort.
            size = max([int(x) for x in re.findall(r'(\d+)x\d+', tag)] or [0])
            score = (2000 if 'apple-touch' in tag.lower() else 0) + size + (500 if href.group(1).lower().split('?')[0].endswith('.svg') else 0)
            found.append((score, urllib.parse.urljoin("https://%s/" % domain, href.group(1))))
        ranked = sorted(found, key=lambda x: -x[0])
        # The conventional apple-touch-icon path beats any declared icon
        # under 64px, which renders blurry at the size we show logos.
        out += [u for sc, u in ranked if sc >= 64]
        out.append("https://%s/apple-touch-icon.png" % domain)
        out += [u for sc, u in ranked if sc < 64]
    except Exception:                                           # noqa: BLE001
        pass
    out.append("https://%s/favicon.ico" % domain)
    # Last resort: Google's favicon service, which knows logos for sites that
    # block us or hide theirs. It answers 404 for unknown domains, so a wrong
    # guess still ends in the initials rather than a generic globe.
    return out[:5] + ["https://www.google.com/s2/favicons?domain=%s&sz=128" % domain]


def _ext_for(url, ctype):
    ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower()
    if ext in TYPES:
        return ext
    for e, t in TYPES.items():
        if t == ctype:
            return e
    return ""


def fetch(domain, cached_only=False):
    """Return (path, content_type) for a cached icon, or (None, None).

    `cached_only=True` never touches the network: a logo not fetched yet is
    queued for the background and (None, None) comes back at once. Page
    views use this, so no image request waits on a slow brand site."""
    domain = _safe(domain)
    if not domain:
        return None, None
    os.makedirs(CACHE, exist_ok=True)
    for name in os.listdir(CACHE):
        if name.rsplit(".", 1)[0] == domain.replace("/", ""):
            path = os.path.join(CACHE, name)
            if os.path.getsize(path) == 0:
                if time.time() - os.path.getmtime(path) < RETRY_MISS_AFTER:
                    return None, None
                os.remove(path)
                break
            return path, TYPES.get(os.path.splitext(name)[1], "image/x-icon")
    if cached_only:
        warm(fetch, domain)
        return None, None
    with _domain_lock(domain):
        for url in _candidates(domain):
            try:
                data, ctype = _get(url)
            except Exception:                                   # noqa: BLE001
                continue
            ext = _ext_for(url, ctype)
            if not data or len(data) > MAX_BYTES or not ext:
                continue
            path = os.path.join(CACHE, domain + ext)
            with open(path, "wb") as f:
                f.write(data)
            return path, TYPES[ext]
        open(os.path.join(CACHE, domain + ".miss"), "wb").close()   # remember the failure
    return None, None


# --- product photos -----------------------------------------------------------
# A rival product's own photo, read from the page an AI answer linked to
# (its og:image). Cached as url -> image url in one JSON file; misses too.
import json as _json
import ipaddress as _ip

_PHOTOS = os.path.join(HERE, "icons", "product-photos.json")
_photo_lock = threading.Lock()


def _public_https(url):
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or "." not in host or host == "localhost":
        return False
    try:
        _ip.ip_address(host)
        return False          # never fetch bare IP addresses
    except ValueError:
        return True


def product_photo(url, cached_only=False):
    """The og:image of a product page, or '' when there is none. With
    `cached_only`, None means "not looked up yet" (queued for background)."""
    if not _public_https(url):
        return ""
    with _photo_lock:
        try:
            with open(_PHOTOS) as f:
                cache = _json.load(f)
        except (OSError, ValueError):
            cache = {}
    hit = cache.get(url)
    if hit is not None and (hit or time.time() - cache.get("_t:" + url, 0) < RETRY_MISS_AFTER):
        return hit
    if cached_only:
        warm(product_photo, url)
        return None
    photo = ""
    try:
        html, _ = _get(url, timeout=6)
        head = html[:300_000].decode("utf-8", "ignore")
        m = (re.search(r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)', head, re.I)
             or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', head, re.I))
        if m:
            cand = urllib.parse.urljoin(url, m.group(1).replace("&amp;", "&"))
            if cand.startswith("http://"):
                cand = "https://" + cand[7:]
            photo = cand if _public_https(cand) else ""
    except Exception:                                           # noqa: BLE001
        photo = ""
    with _photo_lock:
        try:
            with open(_PHOTOS) as f:
                cache = _json.load(f)
        except (OSError, ValueError):
            cache = {}
        cache[url] = photo
        cache["_t:" + url] = time.time()
        os.makedirs(os.path.dirname(_PHOTOS), exist_ok=True)
        with open(_PHOTOS, "w") as f:
            _json.dump(cache, f)
    return photo


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def shop_photo(domain, name, cached_only=False):
    """A product photo from the brand's own Shopify search, or ''.

    Only a close title match counts (half the words shared), so a search
    that surfaces a different product never puts the wrong photo up."""
    domain = _safe(domain)
    want = _words(name)
    if not domain or not want:
        return ""
    key = "shop:%s|%s" % (domain, " ".join(sorted(want)))
    with _photo_lock:
        try:
            with open(_PHOTOS) as f:
                cache = _json.load(f)
        except (OSError, ValueError):
            cache = {}
    if key in cache and (cache[key] or time.time() - cache.get("_t:" + key, 0) < RETRY_MISS_AFTER):
        return cache[key]
    if cached_only:
        warm(shop_photo, domain, name)
        return None
    photo = ""
    items = []
    q = urllib.parse.urlencode({"q": name, "resources[type]": "product", "resources[limit]": 3})
    # The domain is often a guess (brand name + .com); many DTC brands use .co.
    for host in [domain] + ([domain[:-4] + ".co"] if domain.endswith(".com") else []):
        try:
            body, _ = _get("https://%s/search/suggest.json?%s" % (host, q), timeout=6)
            items = _json.loads(body.decode("utf-8", "ignore"))["resources"]["results"]["products"]
            break
        except Exception:                                       # noqa: BLE001
            continue
    try:
        for it in items:
            got = _words(it.get("title"))
            if got and len(want & got) / len(want | got) >= 0.5:
                img = it.get("image") or (it.get("featured_image") or {}).get("url") or ""
                img = ("https:" + img) if img.startswith("//") else img
                if _public_https(img):
                    photo = img
                    break
    except Exception:                                           # noqa: BLE001
        photo = ""
    with _photo_lock:
        try:
            with open(_PHOTOS) as f:
                cache = _json.load(f)
        except (OSError, ValueError):
            cache = {}
        cache[key] = photo
        cache["_t:" + key] = time.time()
        with open(_PHOTOS, "w") as f:
            _json.dump(cache, f)
    return photo


# --- product photos by image search -------------------------------------------
# For brands that are not on Shopify and give no product link (IKEA, BoConcept,
# Kave Home...): a Google Images search for "<brand> <product>" through Apify,
# ~$0.009 per product, cached forever. A result only counts when its title
# shares the product's name words, because the top hit is often a different
# product from the same brand (a vase for "BoConcept Zurich", 2026-09-25).
IMAGE_ACTOR = "hooli~google-images-scraper"
_img_queue = {}                 # key -> (brand, name)
_img_cv = threading.Condition()
_img_worker = None


def _img_key(brand, name):
    return "img:%s|%s" % (" ".join(sorted(_words(brand))), " ".join(sorted(_words(name))))


def _plain(text):
    import unicodedata
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def _pick(results, brand, name):
    want = _words(_plain(name)) - _words(_plain(brand))
    if not want:
        return ""
    ok = []
    for r in results:
        url = r.get("thumbnailUrl") or r.get("imageUrl") or ""
        origin = (r.get("origin") or "").lower()
        if not _public_https(url) or "instagram" in origin or "pinterest" in origin:
            continue
        got = _words(_plain(r.get("title")))
        if len(want & got) / len(want) >= 0.5:
            on_brand = any(w in origin.replace(".", " ").replace("-", "") for w in _words(_plain(brand)))
            ok.append((0 if on_brand else 1, url))
    return min(ok)[1] if ok else ""


def _img_run(batch):
    import apify_answers
    queries = ["%s %s" % (b, n) for b, n in batch.values()]
    run = apify_answers._request("POST", "/acts/%s/runs" % IMAGE_ACTOR,
                                 {"queries": queries, "maxResultsPerQuery": 3})["data"]
    status = apify_answers.wait(run["id"], poll=5, timeout=600)
    items = apify_answers._request("GET", "/datasets/%s/items?clean=true" % run["defaultDatasetId"])
    by_q = {}
    for it in items if isinstance(items, list) else []:
        by_q.setdefault(it.get("query") or "", []).append(it)
    with _photo_lock:
        try:
            with open(_PHOTOS) as f:
                cache = _json.load(f)
        except (OSError, ValueError):
            cache = {}
        for key, (b, n) in batch.items():
            got = by_q.get("%s %s" % (b, n))
            if got is None and status != "SUCCEEDED":
                continue              # run failed: leave it unknown, retry later
            cache[key] = _pick(got or [], b, n)
            cache["_t:" + key] = time.time()
        with open(_PHOTOS, "w") as f:
            _json.dump(cache, f)


def _img_loop():
    while True:
        with _img_cv:
            while not _img_queue:
                _img_cv.wait()
        time.sleep(4)                 # let a page's requests pile up into one run
        with _img_cv:
            batch = dict(list(_img_queue.items())[:100])
        try:
            _img_run(batch)
        except Exception:             # noqa: BLE001 - Apify down: try again later
            time.sleep(60)
        with _img_cv:
            for k in batch:
                _img_queue.pop(k, None)


def search_photo(brand, name, cached_only=True):
    """A product photo found by image search, '' when none matched, or None
    while the search is still queued. Never blocks a page view."""
    if not _words(name) or not _words(brand):
        return ""
    key = _img_key(brand, name)
    with _photo_lock:
        try:
            with open(_PHOTOS) as f:
                cache = _json.load(f)
        except (OSError, ValueError):
            cache = {}
    if key in cache and (cache[key] or time.time() - cache.get("_t:" + key, 0) < RETRY_MISS_AFTER):
        return cache[key]
    global _img_worker
    with _img_cv:
        _img_queue.setdefault(key, (brand, name))
        if _img_worker is None:
            _img_worker = threading.Thread(target=_img_loop, daemon=True)
            _img_worker.start()
        _img_cv.notify()
    return None


def is_image_url(url):
    """A direct image link rather than a product page."""
    if not _public_https(url):
        return False
    u = urllib.parse.urlsplit(url)
    return (u.hostname or "").endswith("images.openai.com") or \
        u.path.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp", "avif", "gif")
