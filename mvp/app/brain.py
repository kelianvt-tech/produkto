"""The agent's brain, step 1: a nightly collector that learns what works in AI search from OTHER people's data.

Built 22 Oct 2026 (plan: mvp/content-agent/agent-brain.html). Kelian: our own data (a few stores,
one-day scans) is too small to be conclusive, so the brain's general findings come from third-party
sources only. Our own scans stay store facts and never enter here (MEMORY.md, 2026-10-22).

Every night, on the server, with nobody feeding it:

  1. Collect only what is NEW since the last run (brain_seen dedupes by URL / post id / video id):
       blogs     competitor blogs and research pages, from their RSS feed or sitemap (free, plain fetch)
       search    Google results from the past week for new AEO/GEO/AI-shopping studies
                 (apify/google-search-scraper, $0.0025 a page)
       linkedin  posts from the experts in EXPERTS (harvestapi/linkedin-profile-posts, $0.002 a post), weekly
       youtube   new talks found through Google (site:youtube.com, past week), transcripts through
                 johnvc/YoutubeTranscripts ($0.0025 a video), weekly
       docs      engine help pages (OpenAI, Google, Perplexity, Microsoft, Shopify); a change in the
                 visible text is an item (free)
  2. A cheap model (config.HELPER_MODEL) reads each item and pulls out checkable claims, grades each
     one (Official / Measured with who ran it and how big / Opinion; vendor flagged), and compares it
     with what the brain already holds (agrees / contradicts / new). Competitor launches are kept
     apart as "what competitors shipped".
  3. Status, decided in code, not by the model:
       playbook   Official findings (only an engine's own page can be Official), and Measured findings
                  that a second, independent source agrees with. One vendor study alone never gets in.
       candidate  a Measured finding waiting for that second source
       test       Opinions. Stored only; nothing runs them yet.
     Contradictions are flagged on both findings and never remove anything on their own.
     The brain writes ONLY its own brain_* tables. It never changes drafts, writing rules, the copy
     skill or anything a merchant sees; findings about wording or tone can never reach the playbook.

Cost guard (guard()), same shape as third_party.py: off unless PRODUKTO_BRAIN=1; at most
PRODUKTO_BRAIN_CAP dollars a night (default $1), counted before every paid call; never runs while
the shared Apify account is within $10 of its monthly limit, because the daily scans need it.
Items the night's budget can't cover stay queued for the next night.

Monday digest to Kelian (mailer.py) only when PRODUKTO_BRAIN_DIGEST=1: playbook changes,
contradictions, what competitors shipped.

Run by hand: python3 brain.py run [--force]   |   python3 brain.py report   |   python3 brain.py digest
"""
import datetime as dt
import hashlib
import html
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import db

# --- Sources (Kelian's additions are one line each) ----------------------------

# Competitors: their claims are vendor evidence. `feed` is an RSS/Atom feed or a sitemap.xml;
# `paths` keeps only URLs under those paths (blog posts, research), so product pages never come in.
# Checked by hand 22 Oct 2026. CommercePepper: no website found yet (commercepepper.com/.ai/.io don't
# resolve); add its feed here when Kelian has the address. refibuy.com is a mortgage broker: ReFiBuy is .ai.
COMPETITORS = [
    dict(name='Sixthshop', feed='https://www.sixthshop.com/sitemap.xml', paths=('/blog/', '/research/')),
    dict(name='Azoma', feed='https://www.azoma.ai/sitemap.xml', paths=('/insights/',)),
    dict(name='AndromedAI', feed='https://www.andromed.ai/sitemap.xml', paths=('/blog/',)),
    dict(name='Searchable', feed='https://www.searchable.com/rss.xml', paths=('/blog/',)),
    dict(name='CatalogWise', feed='https://catalogwise.com/sitemap.xml', paths=('/guides/', '/blog/')),
    dict(name='CommercePepper', feed='', paths=()),
    dict(name='Pepper', feed='https://www.pepper.inc/sitemap.xml', paths=('/blog/',)),
    dict(name='Promptwatch', feed='https://promptwatch.com/sitemap.xml', paths=('/blog/',)),
    dict(name='Peec AI', feed='https://peec.ai/sitemap.xml', paths=('/blog/',)),
    dict(name='Profound', feed='https://www.tryprofound.com/sitemap.xml', paths=('/blog/', '/articles/', '/research/')),
    dict(name='Goodie', feed='https://higoodie.com/sitemap.xml', paths=('/blog/',)),
    dict(name='Glara', feed='https://glara.ai/sitemap.xml', paths=('/blog/',)),
    dict(name='ReFiBuy', feed='https://refibuy.ai/sitemap.xml', paths=('/articles/',)),
    dict(name='Alhena', feed='https://alhena.ai/blog/feed', paths=('/blog/',)),
]

# People who post about AI search, SEO and AI shopping (41). Every profile URL checked 22 Oct 2026: the
# first six from the 18 Oct creator scrape, the rest from Google `site:linkedin.com/in` results whose
# headline named the person and their company. Add or remove one per line.
EXPERTS = [
    'https://www.linkedin.com/in/donnellychris/',     # Chris Donnelly, Searchable
    'https://www.linkedin.com/in/lily-ray-44755615/', # Lily Ray, Amsive
    'https://www.linkedin.com/in/mariusmeiners/',     # Marius Meiners, Peec AI
    'https://www.linkedin.com/in/ethanls/',           # Ethan Smith, Graphite
    'https://www.linkedin.com/in/jamescadwallader/',  # James Cadwallader, Profound
    'https://www.linkedin.com/in/kevinindig/',        # Kevin Indig
    'https://www.linkedin.com/in/joshua-blyskal/',    # Josh Blyskal, Profound
    'https://www.linkedin.com/in/landwehr/',          # Malte Landwehr, Peec AI
    'https://www.linkedin.com/in/tomekrudzki/',       # Tomek Rudzki, Peec AI
    'https://www.linkedin.com/in/samuelhhogan/',      # Sam Hogan, Searchable
    'https://www.linkedin.com/in/aleyda/',            # Aleyda Solis
    'https://www.linkedin.com/in/randfishkin/',       # Rand Fishkin, SparkToro
    'https://www.linkedin.com/in/michaelkingphilly/', # Mike King, iPullRank
    'https://www.linkedin.com/in/glenngabe/',         # Glenn Gabe
    'https://www.linkedin.com/in/rustybrick/',        # Barry Schwartz, Search Engine Roundtable
    'https://www.linkedin.com/in/marie-haynes/',      # Marie Haynes
    'https://www.linkedin.com/in/cyrusshepard/',      # Cyrus Shepard, Zyppy
    'https://www.linkedin.com/in/schwartze/',         # Eli Schwartz
    'https://www.linkedin.com/in/wilreynolds/',       # Wil Reynolds, Seer
    'https://www.linkedin.com/in/crystal-carter-digital/',# Crystal Carter, Wix
    'https://www.linkedin.com/in/britneymuller/',     # Britney Muller
    'https://www.linkedin.com/in/jasonmbarnard/',     # Jason Barnard, Kalicube
    'https://www.linkedin.com/in/patrickstox/',       # Patrick Stox
    'https://www.linkedin.com/in/timsoulo/',          # Tim Soulo, Ahrefs
    'https://www.linkedin.com/in/thinkingslow/',      # Ryan Law, Ahrefs
    'https://www.linkedin.com/in/gianlucafiorelli/',  # Gianluca Fiorelli
    'https://www.linkedin.com/in/seoguy/',            # Dan Petrovic, Dejan
    'https://www.linkedin.com/in/markseo/',           # Mark Williams-Cook
    'https://www.linkedin.com/in/volpini/',           # Andrea Volpini, WordLift
    'https://www.linkedin.com/in/jes-scholz/',        # Jes Scholz
    'https://www.linkedin.com/in/willcritchlow/',     # Will Critchlow, SearchPilot (SEO tests)
    'https://www.linkedin.com/in/chris-long-marketing/',# Chris Long, Nectiv
    'https://www.linkedin.com/in/mordyoberstein/',    # Mordy Oberstein
    'https://www.linkedin.com/in/dforrester/',        # Duane Forrester
    'https://www.linkedin.com/in/olafkopp/',          # Olaf Kopp (GEO, agentic commerce)
    'https://www.linkedin.com/in/thcapper/',          # Tom Capper, STAT
    'https://www.linkedin.com/in/rosshudgens/',       # Ross Hudgens, Siege Media
    'https://www.linkedin.com/in/brodieclark/',       # Brodie Clark (e-commerce SERPs)
    'https://www.linkedin.com/in/lukecarthy/',        # Luke Carthy (e-commerce SEO)
    'https://www.linkedin.com/in/kiri-masters/',      # Kiri Masters (retail media, commerce)
    'https://www.linkedin.com/in/andrew-lipsman-10b2162/',# Andrew Lipsman (agentic commerce analyst)
]

# Google searches for new studies, past week only. Results from LinkedIn and YouTube are left to
# their own collectors.
STUDY_QUERIES = [
    'ChatGPT shopping study products',
    '"AI search" ecommerce study data',
    '"generative engine optimization" research',
    '"AI Overviews" citations study',
    '"AI visibility" brands study analysed',
    'LLM product recommendations study brands',
]
VIDEO_QUERIES = [
    'site:youtube.com AI search ecommerce products ChatGPT',
    'site:youtube.com GEO AEO "AI search" study',
]

# Engine pages whose wording we watch. A change is an Official item.
ENGINE_DOCS = [
    ('OpenAI', 'https://help.openai.com/en/articles/11128490-shopping-in-chatgpt'),
    ('OpenAI', 'https://developers.openai.com/commerce/specs/file-upload/products'),
    ('OpenAI', 'https://developers.openai.com/api/docs/bots'),
    ('Google', 'https://developers.google.com/search/docs/appearance/ai-features'),
    ('Google', 'https://developers.google.com/search/docs/appearance/structured-data/merchant-listing'),
    ('Google', 'https://developers.google.com/search/docs/appearance/structured-data/product'),
    ('Google', 'https://developers.google.com/merchant/ucp'),
    ('Google', 'https://support.google.com/merchants/answer/7052112'),
    ('Perplexity', 'https://www.perplexity.ai/hub/blog/shop-like-a-pro'),
    ('Perplexity', 'https://docs.perplexity.ai/guides/bots'),
    ('Microsoft', 'https://learn.microsoft.com/en-us/advertising/shopping-content/products-resource'),
    ('Shopify', 'https://shopify.dev/docs/agents'),
]

# --- Prices and limits (Bronze, checked 22 Oct 2026 in the Apify store) ---------

SEARCH_ACTOR = 'apify~google-search-scraper'
LINKEDIN_ACTOR = 'harvestapi~linkedin-profile-posts'
YOUTUBE_ACTOR = 'johnvc~YoutubeTranscripts'
SEARCH_PER_PAGE = 0.0025
LINKEDIN_PER_POST = 0.002
LINKEDIN_EMPTY = 0.001               # a profile with no posts in the window
LINKEDIN_MAX_POSTS = 5               # per expert per week
YOUTUBE_PER_VIDEO = 0.0025
YOUTUBE_MAX_VIDEOS = 8               # per week
RUN_START = 0.001
LLM_PER_ITEM = 0.004                 # budgeted per item read; real cost is usually ~$0.001
HEADROOM = 10.0                      # never run within this many dollars of the Apify monthly limit
DEFAULT_CAP = 1.0                    # dollars a night
PER_SOURCE_NIGHT = 5                 # new items kept per blog per night
BASELINE_KEEP = 2                    # first time a blog is seen: read its newest 2 (when dates exist)
TEXT_LIMIT = 14000                   # characters of an item the model reads
NIGHT_HOUR = 2                       # server local time
EVERY = dict(blogs=1, search=1, docs=1, linkedin=7, youtube=7)     # days between runs of a collector

TOPICS = ('feeds', 'structured_data', 'crawling', 'product_pages', 'reviews', 'offsite_citations',
          'articles', 'technical', 'measurement', 'engine_behaviour', 'agentic_checkout', 'wording', 'other')
COPY_TOPICS = ('wording',)           # never playbook: the brain doesn't touch writing rules

# Words that make a title, URL or post worth reading. "AI" alone isn't enough: Profound alone
# publishes several generic marketing articles a day.
ON_TOPIC = re.compile(r'chatgpt|openai|\bllms?\b|\baeo\b|\bgeo\b|generative|perplexity|gemini|copilot|ai[ -]search|'
                      r'ai[ -]overview|ai[ -]mode|agentic|shopping|e-?commerce|product|citation|schema|feed|'
                      r'merchant|visibility|\bucp\b|\bacp\b|study|research|analy[sz]|\bdata\b|report|answer engine|'
                      r'launch|introduc|announc|new feature', re.I)
OFF_TOPIC = re.compile(r'alternatives?\b|-vs-|\bvs\.?\b|\bbest\b.*\btools?\b|best-[\w-]*tools?|pricing|careers?|'
                       r'webinar|podcast-episode|/tag/|/category/|'
                       r'/author/|/page/\d', re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_runs (
    id INTEGER PRIMARY KEY, day TEXT, status TEXT, cap_usd REAL, cost_usd REAL DEFAULT 0,
    detail TEXT, started_at REAL, finished_at REAL
);
CREATE TABLE IF NOT EXISTS brain_seen (
    source TEXT NOT NULL, key TEXT NOT NULL, first_seen REAL, PRIMARY KEY (source, key)
);
CREATE TABLE IF NOT EXISTS brain_items (
    id INTEGER PRIMARY KEY, run_id INTEGER, collector TEXT, source TEXT, url TEXT, title TEXT,
    author TEXT, published TEXT, vendor INTEGER DEFAULT 0, official INTEGER DEFAULT 0, text TEXT,
    status TEXT DEFAULT 'queued', note TEXT, cost_usd REAL, fetched_at REAL, read_at REAL
);
CREATE TABLE IF NOT EXISTS brain_findings (
    id INTEGER PRIMARY KEY, item_id INTEGER, claim TEXT NOT NULL, topic TEXT, engine TEXT,
    evidence TEXT, measured_by TEXT, sample_size TEXT, vendor INTEGER DEFAULT 0, source TEXT, url TEXT,
    published TEXT, verdict TEXT, related_id INTEGER, status TEXT, confirmed_by INTEGER,
    disputed INTEGER DEFAULT 0, created_at REAL
);
CREATE TABLE IF NOT EXISTS brain_changes (
    id INTEGER PRIMARY KEY, finding_id INTEGER, change TEXT, reason TEXT, at REAL
);
CREATE TABLE IF NOT EXISTS brain_shipped (
    id INTEGER PRIMARY KEY, item_id INTEGER, competitor TEXT, what TEXT, url TEXT, published TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS brain_docs (
    url TEXT PRIMARY KEY, engine TEXT, text_hash TEXT, text TEXT, status TEXT, checked_at REAL, changed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_brain_items_status ON brain_items(status);
CREATE INDEX IF NOT EXISTS idx_brain_findings_status ON brain_findings(status);
"""

_lock = threading.Lock()
_running = False


def init():
    with db.conn() as c:
        c.executescript(SCHEMA)


# --- Switch, cap, guard ---------------------------------------------------------

def enabled():
    return config.env('PRODUKTO_BRAIN') == '1'


def cap():
    try:
        return float(config.env('PRODUKTO_BRAIN_CAP') or DEFAULT_CAP)
    except ValueError:
        return DEFAULT_CAP


def account_usage():
    import third_party
    return third_party.account_usage()


def guard(usage=None, force=False):
    """(ok, reasons). `force` skips only the switch (a hand run); the money checks always apply."""
    reasons = []
    if not enabled() and not force:
        reasons.append('The brain is switched off (PRODUKTO_BRAIN=1 turns it on).')
    if _running:
        reasons.append('A brain run is already going.')
    try:
        used, limit = usage if usage is not None else account_usage()
        if limit and limit - used - cap() < HEADROOM:
            reasons.append('The Apify account has $%.2f left of its $%.0f monthly limit; the brain must leave $%.0f '
                           'for the daily scans.' % (max(0, limit - used), limit, HEADROOM))
    except Exception as e:                                          # noqa: BLE001 - unknown balance = don't spend
        reasons.append('Could not read the Apify balance (%s).' % e)
    return not reasons, reasons


class Budget:
    """The night's money. Every paid step asks before it spends and records what it really cost."""

    def __init__(self, limit):
        self.limit, self.spent, self.lines = limit, 0.0, []

    def allows(self, estimate):
        return self.spent + estimate <= self.limit + 1e-9

    def add(self, what, usd):
        self.spent += usd or 0
        self.lines.append((what, round(usd or 0, 5)))


# --- Plain fetching (free) ----------------------------------------------------------

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):     # Python < 3.11 refuses 308
        if code == 308:
            code = 301
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_Redirect)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
    with _opener.open(req, timeout=timeout) as r:
        return r.read(3_000_000).decode('utf-8', 'replace')


def plain(html_text):
    t = re.sub(r'(?is)<(script|style|noscript|svg|nav|header|footer|form)\b.*?</\1>', ' ', html_text or '')
    t = re.sub(r'(?i)<br\s*/?>|</(p|h[1-6]|li|tr|div)>', '\n', t)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', t))
    t = re.sub(r'[ \t\r\f\v]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t).strip()


def title_of(html_text):
    m = re.search(r'(?is)<title[^>]*>(.*?)</title>', html_text or '')
    return html.unescape(re.sub(r'\s+', ' ', m.group(1))).strip() if m else ''


def feed_entries(text, depth=0, get=None):
    """[(url, title, date)] from RSS, Atom or a sitemap (following a sitemap index one level down)."""
    get = get or fetch
    out = []
    if '<sitemapindex' in text and depth < 2:
        for loc in re.findall(r'(?is)<sitemap>.*?<loc>\s*(.*?)\s*</loc>', text):
            try:
                out += feed_entries(get(html.unescape(loc)), depth + 1, get)
            except Exception:                                       # noqa: BLE001 - one bad child sitemap
                pass
        return out
    for block in re.findall(r'(?is)<url>(.*?)</url>', text):
        loc = re.search(r'(?is)<loc>\s*(.*?)\s*</loc>', block)
        mod = re.search(r'(?is)<lastmod>\s*(.*?)\s*</lastmod>', block)
        if loc:
            out.append((html.unescape(loc.group(1)), '', mod.group(1)[:10] if mod else ''))
    for block in re.findall(r'(?is)<(?:item|entry)\b.*?</(?:item|entry)>', text):
        link = (re.search(r'(?is)<link>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</link>', block)
                or re.search(r'(?is)<link[^>]*href="([^"]+)"', block))
        title = re.search(r'(?is)<title[^>]*>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>', block)
        date = re.search(r'(?is)<(?:pubDate|published|updated|dc:date)>\s*(.*?)\s*</', block)
        if link:
            out.append((html.unescape(link.group(1).strip()), html.unescape(title.group(1).strip()) if title else '',
                        _iso(date.group(1)) if date else ''))
    return out


def _iso(s):
    s = (s or '').strip()
    for fmt in ('%a, %d %b %Y %H:%M:%S %Z', '%a, %d %b %Y %H:%M:%S %z'):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s[:10]


def _host(url):
    return urllib.parse.urlparse(url or '').netloc.lower().removeprefix('www.')


def _norm(url):
    p = urllib.parse.urlparse((url or '').strip())
    return urllib.parse.urlunparse((p.scheme or 'https', p.netloc.lower().removeprefix('www.'),
                                    p.path.rstrip('/') or '/', '', '', ''))


def on_topic(*texts):
    blob = ' '.join(t or '' for t in texts)
    return bool(ON_TOPIC.search(blob.replace('-', ' ')) or ON_TOPIC.search(blob))


# --- Dedupe and queue ------------------------------------------------------------------

def _seen(source, key):
    return bool(db.one('SELECT 1 FROM brain_seen WHERE source=? AND key=?', (source, key)))


def _mark(source, keys):
    now = time.time()
    with db.conn() as c:
        c.executemany('INSERT OR IGNORE INTO brain_seen (source, key, first_seen) VALUES (?,?,?)',
                      [(source, k, now) for k in keys])


def _queue(run_id, collector, source, url, title='', author='', published='', text='', vendor=0, official=0,
           status='queued', note=''):
    return db.write('INSERT INTO brain_items (run_id, collector, source, url, title, author, published, vendor, '
                    'official, text, status, note, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (run_id, collector, source, url, title, author, published, vendor, official,
                     (text or '')[:TEXT_LIMIT * 2], status, note, time.time()))


# --- Collectors -----------------------------------------------------------------------------
# Each returns a dict for the run's detail. Free ones take `get` (a fetch function) so tests never
# touch the network; paid ones take `actor` (items, usd) = actor(name, body) for the same reason.

def collect_blogs(run_id, get=fetch, sources=None):
    out = {}
    for src in sources if sources is not None else COMPETITORS:
        name = src['name']
        if not src.get('feed'):
            out[name] = 'no feed address'
            continue
        try:
            entries = feed_entries(get(src['feed']), get=get)
        except Exception as e:                                      # noqa: BLE001
            out[name] = 'feed failed: %s' % str(e)[:120]
            continue
        paths = src.get('paths') or ()
        entries = [(u, t, d) for u, t, d in entries if not paths or any(p in urllib.parse.urlparse(u).path for p in paths)]
        entries = [(u, t, d) for u, t, d in entries if urllib.parse.urlparse(u).path.rstrip('/') not in
                   {p.rstrip('/') for p in paths}]                  # the blog's index page itself
        key = 'blog:' + name
        first = not db.one('SELECT 1 FROM brain_seen WHERE source=?', (key,))
        new = [(u, t, d) for u, t, d in entries if not _seen(key, _norm(u))]
        _mark(key, [_norm(u) for u, _, _ in new])
        kept = [(u, t, d) for u, t, d in new if on_topic(u, t) and not OFF_TOPIC.search(u + ' ' + t)]
        if first:
            # First sight: everything already published is history, not news. Read the newest few,
            # only when the feed carries real dates; otherwise wait for the first new post.
            real_dates = len({d for _, _, d in new if d}) > 1 or len(new) <= 3   # one date on many URLs = regenerated
            kept = [e for e in kept if e[2]] if real_dates else []
            kept = sorted(kept, key=lambda e: e[2], reverse=True)[:BASELINE_KEEP]
        kept = sorted(kept, key=lambda e: e[2] or '', reverse=True)[:PER_SOURCE_NIGHT]
        for u, t, d in kept:
            _queue(run_id, 'blogs', name, u, title=t, published=d, vendor=1)
        out[name] = '%d new, %d queued%s' % (len(new), len(kept), ' (first run: history skipped)' if first else '')
    return out


def collect_docs(run_id, get=fetch, docs=None):
    """A doc page is an item only when its visible text changes. The first look stores it silently."""
    out = {}
    for engine, url in docs if docs is not None else ENGINE_DOCS:
        now = time.time()
        try:
            raw = get(url)
            text = plain(raw)
        except Exception as e:                                      # noqa: BLE001
            db.write('INSERT INTO brain_docs (url, engine, status, checked_at) VALUES (?,?,?,?) '
                     'ON CONFLICT(url) DO UPDATE SET status=excluded.status, checked_at=excluded.checked_at',
                     (url, engine, 'unreadable: %s' % str(e)[:80], now))
            out[url] = 'unreadable'
            continue
        h = hashlib.sha256(_stable(text).encode()).hexdigest()
        old = db.one('SELECT text_hash, text FROM brain_docs WHERE url=?', (url,))
        if old and old['text_hash'] == h:
            db.write('UPDATE brain_docs SET status=?, checked_at=? WHERE url=?', ('same', now, url))
            out[url] = 'same'
            continue
        added, removed = _diff(old['text'] if old else '', text)
        db.write('INSERT INTO brain_docs (url, engine, text_hash, text, status, checked_at, changed_at) '
                 'VALUES (?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET text_hash=excluded.text_hash, '
                 'text=excluded.text, status=excluded.status, checked_at=excluded.checked_at, '
                 'changed_at=excluded.changed_at', (url, engine, h, text, 'changed' if old else 'first look', now, now))
        if not old:
            out[url] = 'first look stored'
            continue
        if len(' '.join(added + removed)) < 40:                     # a date or a counter moved, nothing more
            out[url] = 'trivial change'
            continue
        body = 'ADDED:\n' + '\n'.join(added)[:TEXT_LIMIT // 2] + '\n\nREMOVED:\n' + '\n'.join(removed)[:TEXT_LIMIT // 2]
        _queue(run_id, 'docs', engine, url, title='Change to %s page: %s' % (engine, title_of(raw) or url),
               published=dt.date.today().isoformat(), text=body, official=1)
        out[url] = 'changed: queued'
    return out


def _stable(text):
    """Text without the bits that change on every load (dates, times, counters)."""
    return re.sub(r'\d', '0', text)


def _diff(old, new):
    a = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n', old) if len(s.strip()) > 3]
    b = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n', new) if len(s.strip()) > 3]
    sa, sb = {_stable(s) for s in a}, {_stable(s) for s in b}
    return [s for s in b if _stable(s) not in sa], [s for s in a if _stable(s) not in sb]


def _search(queries, actor, budget, label, date_range='w1'):
    est = len(queries) * SEARCH_PER_PAGE + RUN_START
    if not budget.allows(est):
        return None, 'skipped: over tonight\'s budget (needs $%.3f)' % est
    items, usd = actor(SEARCH_ACTOR, dict(queries='\n'.join(queries), maxPagesPerQuery=1, resultsPerPage=10,
                                          countryCode='us', languageCode='en', quickDateRange=date_range,
                                          mobileResults=False, saveHtml=False, saveHtmlToKeyValueStore=False,
                                          includeIcons=False))
    budget.add(label, usd if usd is not None else est)
    rows = []
    for it in items or []:
        for r in it.get('organicResults') or []:
            rows.append(dict(url=r.get('url') or '', title=r.get('title') or '', snippet=r.get('description') or '',
                             date=r.get('date') or ''))
    return rows, None


def collect_search(run_id, actor, budget, get=fetch):
    rows, why = _search(STUDY_QUERIES, actor, budget, 'search: studies')
    if rows is None:
        return dict(status=why)
    vendors = {_host(c['feed']) for c in COMPETITORS if c.get('feed')}
    queued = 0
    for r in rows:
        u, host = r['url'], _host(r['url'])
        if not u or any(h in host for h in ('linkedin.com', 'youtube.com', 'youtu.be', 'reddit.com', 'x.com',
                                             'twitter.com', 'facebook.com', 'instagram.com', 'tiktok.com')):
            continue
        if _seen('web', _norm(u)) or not on_topic(u, r['title'], r['snippet']):
            _mark('web', [_norm(u)])
            continue
        _mark('web', [_norm(u)])
        _queue(run_id, 'search', host, u, title=r['title'], published=r['date'][:10],
               vendor=1 if host in vendors else 0, note=r['snippet'][:300])
        queued += 1
    return dict(status='ok', results=len(rows), queued=queued)


def collect_linkedin(run_id, actor, budget, experts=None):
    experts = experts if experts is not None else EXPERTS
    if not experts:
        return dict(status='no experts listed')
    est = len(experts) * LINKEDIN_MAX_POSTS * LINKEDIN_PER_POST + RUN_START
    if not budget.allows(est):
        return dict(status='skipped: over tonight\'s budget (needs $%.2f)' % est)
    items, usd = actor(LINKEDIN_ACTOR, dict(targetUrls=experts, maxPosts=LINKEDIN_MAX_POSTS, postedLimit='week',
                                            includeReposts=False, includeQuotePosts=True, scrapeReactions=False,
                                            scrapeComments=False))
    budget.add('linkedin', usd if usd is not None else len(items or []) * LINKEDIN_PER_POST)
    queued = posts = 0
    for p in items or []:
        text = p.get('content') or p.get('text') or ''
        url = p.get('linkedinUrl') or p.get('url') or p.get('shareUrl') or ''
        key = str(p.get('id') or p.get('entityId') or url)
        if not text or not key:
            continue
        posts += 1
        if _seen('linkedin', key):
            continue
        _mark('linkedin', [key])
        if len(text) < 200 or not on_topic(text):
            continue
        a = p.get('author') or {}
        when = p.get('postedAt') or {}
        when = when.get('date') if isinstance(when, dict) else str(when)
        _queue(run_id, 'linkedin', a.get('name') or 'LinkedIn', url, title=text[:90], author=a.get('name') or '',
               published=(when or '')[:10], text=text)
        queued += 1
    return dict(status='ok', posts=posts, queued=queued)


def collect_youtube(run_id, actor, budget):
    rows, why = _search(VIDEO_QUERIES, actor, budget, 'search: videos')
    if rows is None:
        return dict(status=why)
    vids = []
    for r in rows:
        m = re.search(r'(?:v=|youtu\.be/|/shorts/)([\w-]{11})', r['url'])
        if not m or _seen('youtube', m.group(1)):
            continue
        _mark('youtube', [m.group(1)])
        if on_topic(r['title'], r['snippet']):
            vids.append((m.group(1), r))
    vids = vids[:YOUTUBE_MAX_VIDEOS]
    if not vids:
        return dict(status='ok', results=len(rows), queued=0)
    est = len(vids) * YOUTUBE_PER_VIDEO + RUN_START
    if not budget.allows(est):
        return dict(status='skipped transcripts: over tonight\'s budget', found=len(vids))
    items, usd = actor(YOUTUBE_ACTOR, dict(youtube_url=['https://www.youtube.com/watch?v=' + v for v, _ in vids],
                                           languages=['en'], include_metadata=True))
    budget.add('youtube transcripts', usd if usd is not None else len(items or []) * YOUTUBE_PER_VIDEO)
    by_id = {v: r for v, r in vids}
    queued = 0
    for it in items or []:
        vid = it.get('video_id') or (re.search(r'([\w-]{11})', it.get('url') or '') or [None, None])[1]
        text = it.get('non_timestamped') or it.get('text') or ''
        if isinstance(text, list):
            text = ' '.join(x.get('text', '') if isinstance(x, dict) else str(x) for x in text)
        if not vid or not text:
            continue
        r = by_id.get(vid, {})
        _queue(run_id, 'youtube', it.get('channel_name') or 'YouTube', 'https://www.youtube.com/watch?v=' + vid,
               title=it.get('title') or r.get('title', ''), author=it.get('channel_name') or '',
               published=(r.get('date') or '')[:10], text=text)
        queued += 1
    return dict(status='ok', results=len(rows), videos=len(vids), queued=queued)


# --- Reading: claims, grades, comparison ---------------------------------------------------------

EXTRACT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['relevant', 'kind', 'announcement', 'claims'],
    'properties': {
        'relevant': {'type': 'boolean'},
        'kind': {'type': 'string', 'enum': ['study', 'announcement', 'advice', 'news', 'doc_change', 'other']},
        'announcement': {'type': 'string'},
        'claims': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['claim', 'topic', 'engine', 'evidence', 'measured_by', 'measured_by_vendor', 'sample_size',
                         'verdict', 'related_id'],
            'properties': {
                'claim': {'type': 'string'},
                'topic': {'type': 'string', 'enum': list(TOPICS)},
                'engine': {'type': 'string'},
                'evidence': {'type': 'string', 'enum': ['official', 'measured', 'opinion']},
                'measured_by': {'type': 'string'},
                'measured_by_vendor': {'type': 'boolean'},
                'sample_size': {'type': 'string'},
                'verdict': {'type': 'string', 'enum': ['new', 'agrees', 'repeats', 'contradicts']},
                'related_id': {'type': 'integer'},
            }}},
    }}

INSTRUCTIONS = """You read one item (an article, post, video transcript, or the changed lines of an AI engine's
help page) for a team that helps online stores get their products recommended by AI assistants (ChatGPT,
Google AI Overviews and AI Mode, Perplexity, Copilot, Gemini, Claude).

relevant: true only if the item says something checkable about how AI engines find, read, cite, rank or
recommend products, brands or pages, or about how stores can affect that.

claims: at most 5 short sentences, each one checkable fact or measured result taken from the item, in plain
words, with the numbers it gives. No marketing language, no advice without a reason. Skip anything the item
doesn't actually support. Empty list if nothing qualifies.

evidence for each claim:
- official: ONLY when the item is the engine's own page or announcement saying how its product works.
- measured: someone counted it in real AI answers or real data. Fill measured_by (who ran it) and
  sample_size (how big, e.g. "43,000 products", "3,000 runs"). If either is unknown, it is an opinion.
- opinion: everything else, including advice and expert views.
measured_by_vendor: true if whoever measured it sells AI-visibility, SEO or AI-shopping tools or services.
engine: which engine the claim is about (ChatGPT, Google, Perplexity, Copilot, Gemini, Claude, Shopify, all).

Compare each claim with KNOWN FINDINGS. verdict:
- repeats: the SAME study, dataset or measurement as a known finding, reported again (by anyone, including a
  different article quoting it, or the same company restating its own number). Not a confirmation.
- agrees: a DIFFERENT study or source that finds the same thing.
- contradicts: says the opposite, or a clearly different number for the same thing. Two numbers measured on
  different things (different engines, samples or questions) are not a contradiction.
- new: nothing known is about the same thing.
related_id: the id of the known finding it repeats, agrees with or contradicts, else 0.

kind: what the item mostly is. announcement: if a company announces a product or feature it shipped, one
sentence "<Company> launched <what>", else empty."""


def known_findings(limit=180):
    rows = db.all_("SELECT id, claim, evidence, status FROM brain_findings WHERE status IN ('playbook','candidate','test') "
                   "ORDER BY CASE status WHEN 'playbook' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END, id DESC LIMIT ?",
                   (limit,))
    return [dict(r) for r in rows]


def _llm(instructions, text, usage):
    import llm
    return llm.json_call(instructions, text, 'brain_item', EXTRACT_SCHEMA, usage=usage, attempts=3)


def read_item(item, call=None):
    """Model output for one item: (data, cost in dollars)."""
    import llm
    usage = llm.Usage()
    known = known_findings()
    head = ('SOURCE: %s (%s)\nTYPE: %s%s\nURL: %s\nTITLE: %s\nDATE: %s\n\n' %
            (item['source'], item['collector'], 'engine help page change' if item['official'] else
             'competitor of ours (a vendor)' if item['vendor'] else 'third party', '', item['url'],
             item['title'], item['published']))
    body = item['text'] or ''
    listing = '\n'.join('[%d] (%s) %s' % (k['id'], k['evidence'], k['claim']) for k in known) or '(none yet)'
    text = head + 'ITEM TEXT:\n' + body[:TEXT_LIMIT] + '\n\nKNOWN FINDINGS:\n' + listing
    data = (call or _llm)(INSTRUCTIONS, text, usage)
    cents = usage.cost_cents()
    return data, (cents / 100.0 if cents is not None else LLM_PER_ITEM)


def _fill_text(item, get):
    if item['text']:
        return item['text']
    raw = get(item['url'])
    text = plain(raw)
    title = item['title'] or title_of(raw)
    db.write('UPDATE brain_items SET text=?, title=? WHERE id=?', (text[:TEXT_LIMIT * 2], title, item['id']))
    return text


ORG_NOISE = {'with', 'and', 'the', 'from', 'commissioned', 'researchers', 'research', 'colleagues', 'authors',
             'paper', 'study', 'team', 'analysis', 'using', 'data', 'university', 'institute', 'center', 'centre',
             'labs', 'inc', 'ltd', 'their', 'its', 'by', 'at', 'of', 'for', 'own', 'snapshots', 'report'}


def _org_words(f):
    """Who stands behind a finding: the measurer's name words, else the site it came from."""
    words = {w for w in re.findall(r'[a-z0-9]+', (f.get('measured_by') or '').lower()) if len(w) > 2} - ORG_NOISE
    return words or {_host(f.get('url') or '') or (f.get('source') or '').lower()}


def independent(a, b):
    """Two findings are independent sources only if they come from different items, different
    publishers, and no shared organisation name (so "ReFiBuy with Clickstream" and "Clickstream,
    commissioned by ReFiBuy" are the same study, and so are two blogs quoting one paper's authors)."""
    if a.get('item_id') and a.get('item_id') == b.get('item_id'):
        return False
    if (a.get('source') or '').lower() == (b.get('source') or '').lower():
        return False
    if _host(a.get('url')) and _host(a.get('url')) == _host(b.get('url')):
        return False
    return not (_org_words(a) & _org_words(b))


def _base_status(f):
    if f['topic'] in COPY_TOPICS:
        return 'test'
    return {'official': 'playbook', 'measured': 'candidate'}.get(f['evidence'], 'test')


def _change(fid, change, reason):
    db.write('INSERT INTO brain_changes (finding_id, change, reason, at) VALUES (?,?,?,?)', (fid, change, reason, time.time()))


def settle():
    """Work out every finding's status from scratch with today's rules, and log what moved.

    playbook   Official, or Measured and agreed with by an independent source (at least one of the
               pair Measured, neither an Opinion, neither about wording)
    candidate  Measured, waiting for that second source
    test       Opinion, and anything about wording
    Deterministic and free, so a rule change can be re-applied to everything already stored."""
    rows = {r['id']: dict(r) for r in db.all_('SELECT * FROM brain_findings')}
    want = {fid: _base_status(f) for fid, f in rows.items()}
    why = {fid: ('Official: %s.' % f['source']) for fid, f in rows.items() if want[fid] == 'playbook'}
    confirmed = {}
    for fid, f in rows.items():
        old = rows.get(f['related_id'])
        if f['verdict'] != 'agrees' or not old:
            continue
        pair = (f['evidence'], old['evidence'])
        if 'opinion' in pair or 'measured' not in pair or COPY_TOPICS[0] in (f['topic'], old['topic']):
            continue
        if not independent(f, old):
            continue
        for a, b in ((fid, old['id']), (old['id'], fid)):
            if want[a] != 'playbook':
                want[a], confirmed[a] = 'playbook', b
                why[a] = 'Confirmed by finding %d (%s), an independent source.' % (b, rows[b]['source'])
    disputed = {fid for fid, f in rows.items() if f['verdict'] == 'contradicts' and f['related_id'] in rows}
    disputed |= {rows[fid]['related_id'] for fid in disputed}
    moved = []
    with db.conn() as c:
        for fid, f in rows.items():
            dis = 1 if fid in disputed else 0
            if f['status'] != want[fid] or (f['confirmed_by'] or None) != confirmed.get(fid) or f['disputed'] != dis:
                c.execute('UPDATE brain_findings SET status=?, confirmed_by=?, disputed=? WHERE id=?',
                          (want[fid], confirmed.get(fid), dis, fid))
            if f['status'] != want[fid]:
                moved.append(fid)
                if want[fid] == 'playbook':
                    reason, change = why[fid], 'added'
                elif f['status'] == 'playbook':
                    reason, change = 'No longer meets the playbook rules.', 'removed'
                else:
                    continue
                c.execute('INSERT INTO brain_changes (finding_id, change, reason, at) VALUES (?,?,?,?)',
                          (fid, change, reason, time.time()))
            if dis and not f['disputed']:
                other = f['related_id'] if f['verdict'] == 'contradicts' else next(
                    (k for k, g in rows.items() if g['related_id'] == fid and g['verdict'] == 'contradicts'), None)
                c.execute('INSERT INTO brain_changes (finding_id, change, reason, at) VALUES (?,?,?,?)',
                          (fid, 'disputed', 'Finding %s says otherwise.' % other, time.time()))
    return moved


def has_size(sample):
    """A sample size needs a real count: "68,879 searches" yes; "a few hundred sites", "one query" and
    "September 2025 vs 2026" (only years) no."""
    nums = re.findall(r'\d[\d,.]*', sample or '')
    return any(not re.fullmatch(r'(19|20)\d\d', n.rstrip('.,')) for n in nums)


def store(item, data):
    """Turn the model's reading into findings. The grade is checked in code: only an engine page can
    be Official, and Measured needs who ran it and a sample with a number in it. Status is left to settle()."""
    saved = []
    if data.get('announcement') and item['vendor']:
        db.write('INSERT INTO brain_shipped (item_id, competitor, what, url, published, created_at) VALUES (?,?,?,?,?,?)',
                 (item['id'], item['source'], data['announcement'][:400], item['url'], item['published'], time.time()))
    if not data.get('relevant'):
        return saved
    valid_ids = {r['id'] for r in db.all_('SELECT id FROM brain_findings')}
    for c in (data.get('claims') or [])[:5]:
        claim = (c.get('claim') or '').strip()
        if not claim:
            continue
        ev = c.get('evidence')
        if ev == 'official' and not item['official']:
            ev = 'opinion'                    # a blog repeating an engine's docs is second-hand
        if item['official']:
            ev = 'official'
        if ev == 'measured' and not ((c.get('measured_by') or '').strip() and has_size(c.get('sample_size'))):
            ev = 'opinion'                    # "a few hundred sites", "one query": no real size
        vendor = 1 if (item['vendor'] or (ev == 'measured' and c.get('measured_by_vendor'))) else 0
        topic = c.get('topic') if c.get('topic') in TOPICS else 'other'
        related = c.get('related_id') if c.get('related_id') in valid_ids else None
        verdict = c.get('verdict') if related else 'new'
        fid = db.write('INSERT INTO brain_findings (item_id, claim, topic, engine, evidence, measured_by, sample_size, '
                       'vendor, source, url, published, verdict, related_id, status, created_at) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (item['id'], claim, topic, (c.get('engine') or '')[:40], ev,
                        (c.get('measured_by') or '')[:120] if ev == 'measured' else '',
                        (c.get('sample_size') or '')[:80] if ev == 'measured' else '', vendor,
                        item['source'], item['url'], item['published'], verdict, related, 'new', time.time()))
        saved.append(fid)
    settle()
    return saved


def read_queue(budget, get=fetch, call=None, limit=200):
    """Read queued items oldest first until the night's money runs out. Unread items wait for tomorrow."""
    done = failed = 0
    for row in db.all_("SELECT * FROM brain_items WHERE status='queued' ORDER BY official DESC, id LIMIT ?", (limit,)):
        if not budget.allows(LLM_PER_ITEM):
            break
        item = dict(row)
        try:
            item['text'] = _fill_text(item, get)
            if len(item['text']) < 300:
                db.write("UPDATE brain_items SET status='unreadable', read_at=? WHERE id=?", (time.time(), item['id']))
                continue
            data, usd = read_item(item, call)
            budget.add('read item %d' % item['id'], usd)
            ids = store(item, data)
            db.write("UPDATE brain_items SET status=?, cost_usd=?, note=?, read_at=? WHERE id=?",
                     ('read' if data.get('relevant') else 'not relevant', round(usd, 5),
                      '%d findings' % len(ids), time.time(), item['id']))
            done += 1
        except Exception as e:                                      # noqa: BLE001 - one bad item keeps the rest
            db.write("UPDATE brain_items SET status='failed', note=?, read_at=? WHERE id=?",
                     (str(e)[:300], time.time(), item['id']))
            failed += 1
    return dict(read=done, failed=failed,
                waiting=db.one("SELECT COUNT(*) n FROM brain_items WHERE status='queued'")['n'])


# --- The night ------------------------------------------------------------------------------------

def _last(collector):
    rows = db.all_("SELECT detail, started_at FROM brain_runs WHERE status IN ('done','partial') ORDER BY id DESC LIMIT 30")
    for r in rows:
        if collector in (json.loads(r['detail'] or '{}').get('ran') or []):
            return r['started_at']
    return None


def due_collectors(now=None, force=False):
    now = now or time.time()
    return [c for c, days in EVERY.items()
            if force or (_last(c) is None or now - _last(c) >= days * 86400 - 3 * 3600)]


def _apify_actor(name, body):
    import third_party
    return third_party._run_actor(name, body, wait=900)


def run(usage=None, force=False, actor=None, get=fetch, call=None, only=None):
    """One night. `force` = a hand run (ignores the switch and the per-collector cadence, never the money
    checks). `actor`, `get` and `call` replace Apify, the web and the model in tests."""
    global _running
    init()
    ok, reasons = guard(usage, force)
    if not ok:
        raise ValueError(' '.join(reasons))
    with _lock:
        if _running:
            raise ValueError('A brain run is already going.')
        _running = True
    budget = Budget(cap())
    run_id = db.write('INSERT INTO brain_runs (day, status, cap_usd, started_at) VALUES (?,?,?,?)',
                      (dt.date.today().isoformat(), 'running', budget.limit, time.time()))
    detail, ran = {}, []
    try:
        actor = actor or _apify_actor
        steps = dict(docs=lambda: collect_docs(run_id, get),
                     blogs=lambda: collect_blogs(run_id, get),
                     search=lambda: collect_search(run_id, actor, budget, get),
                     linkedin=lambda: collect_linkedin(run_id, actor, budget),
                     youtube=lambda: collect_youtube(run_id, actor, budget))
        for name in only or due_collectors(force=force):
            try:
                detail[name] = steps[name]()
                ran.append(name)
            except Exception as e:                                  # noqa: BLE001 - one collector failing keeps the rest
                detail[name] = dict(status='failed', error=str(e)[:300])
        detail['reading'] = read_queue(budget, get, call)
        status = 'partial' if any(isinstance(v, dict) and v.get('status') == 'failed' for v in detail.values()) else 'done'
    except Exception as e:                                          # noqa: BLE001
        detail['error'], status = str(e)[:300], 'failed'
    finally:
        with _lock:
            _running = False
    detail['ran'], detail['spend'] = ran, budget.lines
    db.write('UPDATE brain_runs SET status=?, cost_usd=?, detail=?, finished_at=? WHERE id=?',
             (status, round(budget.spent, 4), json.dumps(detail), time.time(), run_id))
    return dict(run_id=run_id, status=status, cost_usd=round(budget.spent, 4), detail=detail)


def run_due(now=None):
    """Scheduler: once a night, from NIGHT_HOUR server time, in the background. Returns True if started."""
    if not enabled() or _running:
        return False
    init()
    t = time.localtime(now or time.time())
    if t.tm_hour < NIGHT_HOUR:
        return False
    if db.one('SELECT 1 FROM brain_runs WHERE day=?', (time.strftime('%Y-%m-%d', t),)):
        return False

    def go():
        try:
            out = run()
            print('brain: night run %s, $%.3f' % (out['status'], out['cost_usd']))
            send_digest()
        except Exception as e:                                      # noqa: BLE001
            print('brain: night run refused or failed (%s)' % e)
            db.write('INSERT INTO brain_runs (day, status, detail, started_at, finished_at) VALUES (?,?,?,?,?)',
                     (time.strftime('%Y-%m-%d', t), 'refused', json.dumps(dict(error=str(e)[:300])), time.time(), time.time()))
    threading.Thread(target=go, daemon=True, name='brain').start()
    return True


# --- What it knows, and the Monday digest ----------------------------------------------------------

def playbook():
    return [dict(r) for r in db.all_("SELECT * FROM brain_findings WHERE status='playbook' ORDER BY topic, id")]


def week(since=None):
    since = since or time.time() - 7 * 86400
    return dict(
        added=[dict(r) for r in db.all_("SELECT f.*, c.reason FROM brain_changes c JOIN brain_findings f ON f.id=c.finding_id "
                                        "WHERE c.change='added' AND c.at>=? ORDER BY c.at", (since,))],
        disputed=[dict(r) for r in db.all_("SELECT f.*, c.reason FROM brain_changes c JOIN brain_findings f ON f.id=c.finding_id "
                                           "WHERE c.change='disputed' AND c.at>=? ORDER BY c.at", (since,))],
        shipped=[dict(r) for r in db.all_('SELECT * FROM brain_shipped WHERE created_at>=? ORDER BY competitor', (since,))],
        tests=db.one("SELECT COUNT(*) n FROM brain_findings WHERE status='test' AND created_at>=?", (since,))['n'],
        cost=db.one("SELECT COALESCE(SUM(cost_usd),0) s FROM brain_runs WHERE started_at>=?", (since,))['s'])


def _label(f):
    ev = {'official': 'Official', 'measured': 'Measured', 'opinion': 'Opinion'}.get(f['evidence'], f['evidence'])
    who = ', %s, %s' % (f['measured_by'], f['sample_size']) if f['evidence'] == 'measured' else ''
    return '%s (%s%s%s; %s)' % (f['claim'], ev, who, ', vendor' if f['vendor'] else '', f['url'])


def digest_paragraphs(w=None):
    w = w or week()
    out = ['What the agent\'s brain learned this week from outside sources. Nothing here changed a draft or a '
           'writing rule; reply if a playbook change looks wrong and it can be undone.']
    out.append('New in the playbook (%d): ' % len(w['added']) + (' | '.join(_label(f) for f in w['added']) or 'nothing.'))
    out.append('Contradictions (%d): ' % len(w['disputed']) + (' | '.join('%s. %s' % (_label(f), f['reason'])
                                                                    for f in w['disputed']) or 'none.'))
    out.append('What competitors shipped (%d): ' % len(w['shipped']) +
               (' | '.join('%s: %s (%s)' % (s['competitor'], s['what'], s['url']) for s in w['shipped']) or 'nothing found.'))
    out.append('%d opinions stored as tests to run. Cost this week: $%.2f.' % (w['tests'], w['cost']))
    return out


def send_digest(now=None):
    """Mondays only, once a week, only with PRODUKTO_BRAIN_DIGEST=1."""
    if config.env('PRODUKTO_BRAIN_DIGEST') != '1':
        return None
    t = time.localtime(now or time.time())
    if t.tm_wday != 0:
        return None
    import mailer
    mailer._init()
    key = time.strftime('%G-W%V', t)
    if db.one("SELECT 1 FROM emails WHERE kind='brain_digest' AND key=?", (key,)):
        return None                                      # once a week, whether or not SMTP is set up
    return mailer.send(mailer.SUPPORT, 'Agent brain: this week', digest_paragraphs(), kind='brain_digest',
                       key=key, once=True)


def report(run_id=None):
    init()
    r = db.one('SELECT * FROM brain_runs WHERE id=?', (run_id,)) if run_id else \
        db.one("SELECT * FROM brain_runs ORDER BY id DESC LIMIT 1")
    lines = []
    if r:
        lines.append('Run %d (%s): %s, $%.4f of $%.2f' % (r['id'], r['day'], r['status'], r['cost_usd'] or 0, r['cap_usd'] or 0))
        d = json.loads(r['detail'] or '{}')
        spend = d.pop('spend', [])
        reads = [u for w, u in spend if w.startswith('read item')]
        lines.append('Spend: ' + ', '.join('%s $%.4f' % (w, u) for w, u in spend if not w.startswith('read item')) +
                     ', reading %d items $%.4f' % (len(reads), sum(reads)))
        lines.append(json.dumps(d, indent=1)[:6000])
    for status in ('playbook', 'candidate', 'test'):
        rows = db.all_('SELECT * FROM brain_findings WHERE status=? ORDER BY id', (status,))
        lines.append('\n== %s (%d)' % (status, len(rows)))
        lines += ['- [%d]%s %s' % (f['id'], ' DISPUTED' if f['disputed'] else '', _label(dict(f))) for f in rows]
    rows = db.all_('SELECT * FROM brain_shipped ORDER BY id')
    lines.append('\n== competitors shipped (%d)' % len(rows))
    lines += ['- %s: %s' % (s['competitor'], s['what']) for s in rows]
    return '\n'.join(lines)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'report'
    if cmd == 'run':
        only = [a for a in sys.argv[2:] if not a.startswith('--')] or None
        out = run(force='--force' in sys.argv, only=only)
        print(report(out['run_id']))
    elif cmd == 'digest':
        print('\n\n'.join(digest_paragraphs()))
    else:
        print(report())
