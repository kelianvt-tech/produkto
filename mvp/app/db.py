"""SQLite storage - one file, produkto.db, created on first run.

Two rules are enforced here rather than in the screens:

* Questions freeze at the first scan. After that they can never change,
  because the trend chart only means something if every scan asked the
  same questions.
* `answers` is never edited or deleted. It is the only record of what
  the engine actually said, so answers can be re-read later without paying
  for another API call.

Every answer carries the `engine` it came from (chatgpt / ai-overview /
perplexity). It is part of the record, not a setting: the same question asked
on the same day gets different answers from each engine, and the dashboard
filter only means something because the engine is stored per answer.
"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS competitor_comparisons (
    store_domain TEXT PRIMARY KEY, selection TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS competitor_suggestions (
    store_domain TEXT PRIMARY KEY, scope TEXT NOT NULL, suggestions TEXT NOT NULL, usage TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY,
    store_domain TEXT NOT NULL,
    shopify_id   INTEGER,
    handle       TEXT,
    title        TEXT NOT NULL,
    url          TEXT,
    price        TEXT,
    image        TEXT,
    variants     INTEGER DEFAULT 0,
    vendor       TEXT,
    raw_json     TEXT,
    UNIQUE (store_domain, shopify_id)
);
CREATE TABLE IF NOT EXISTS stores (
    domain     TEXT PRIMARY KEY,
    brand      TEXT,
    products   INTEGER,
    variants   INTEGER,
    fetched_at REAL,
    currency   TEXT DEFAULT '',
    country    TEXT DEFAULT '',
    brand_name TEXT DEFAULT '',
    aliases    TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS prompt_sets (
    id         INTEGER PRIMARY KEY,
    store_domain TEXT,
    legacy_product_id INTEGER,
    clusters TEXT DEFAULT '[]',
    relevance TEXT DEFAULT '[]',
    product_ids TEXT DEFAULT '[]',
    excluded_types TEXT DEFAULT '[]',
    catalog_snapshot TEXT DEFAULT '[]',
    prompts    TEXT NOT NULL,
    tags       TEXT DEFAULT '',
    created_at REAL,
    frozen_at  REAL
);
CREATE TABLE IF NOT EXISTS scans (
    id             INTEGER PRIMARY KEY,
    token          TEXT UNIQUE,
    prompt_set_id  INTEGER NOT NULL,
    run_at         REAL,
    finished_at    REAL,
    status         TEXT,
    done           INTEGER DEFAULT 0,
    total          INTEGER DEFAULT 0,
    error          TEXT,
    cost_cents     REAL DEFAULT 0,
    model_versions TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    id        INTEGER PRIMARY KEY,
    scan_id   INTEGER NOT NULL,
    prompt    TEXT,
    model     TEXT,
    engine    TEXT NOT NULL DEFAULT 'chatgpt',
    run_n     INTEGER,
    raw_text  TEXT,
    citations TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS mentions (
    id           INTEGER PRIMARY KEY,
    answer_id    INTEGER NOT NULL,
    product_name TEXT,
    brand        TEXT,
    url          TEXT,
    rank         INTEGER,
    is_theirs    INTEGER DEFAULT 0,
    is_their_brand INTEGER DEFAULT 0,
    matched_product_id INTEGER,
    match_score  REAL
);
CREATE TABLE IF NOT EXISTS answer_processing (
    answer_id INTEGER PRIMARY KEY, status TEXT NOT NULL, error TEXT
);
-- One row per Apify run, written the moment the run starts and before any
-- answer comes back. A scraped batch is bought minutes before it is stored,
-- so without this a restart in that window loses answers already paid for.
-- `collected` flips to 1 once the answers are safely in `answers`.
-- One row per engine per run number: three engines x five runs is fifteen
-- batches, each recoverable on its own.
CREATE TABLE IF NOT EXISTS scan_batches (
    scan_id INTEGER NOT NULL, run_n INTEGER NOT NULL,
    engine TEXT NOT NULL DEFAULT 'chatgpt',
    apify_run_id TEXT, dataset_id TEXT,
    collected INTEGER NOT NULL DEFAULT 0, started_at REAL,
    PRIMARY KEY (scan_id, run_n, engine)
);
CREATE TABLE IF NOT EXISTS catalog_scope (
    store_domain TEXT PRIMARY KEY, product_ids TEXT NOT NULL, excluded_types TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_scores (
    scan_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
    visibility REAL, appearance_rate REAL, avg_rank REAL, sov_pct REAL, detail TEXT,
    PRIMARY KEY(scan_id,product_id)
);
CREATE TABLE IF NOT EXISTS scores (
    scan_id         INTEGER PRIMARY KEY,
    visibility      REAL,
    appearance_rate REAL,
    avg_rank        REAL,
    sov_pct         REAL,
    brand_rate      REAL,
    detail          TEXT
);
-- Third-party context (third_party.py, 22 Oct 2026): Google Shopping, Google web
-- results and Trustpilot for one store, pulled by hand by an admin. Each pull
-- is a run; rows keep their run_id so older pulls stay readable.
CREATE TABLE IF NOT EXISTS third_party_runs (
    id INTEGER PRIMARY KEY, store_domain TEXT NOT NULL, status TEXT NOT NULL,
    estimate_usd REAL, cost_usd REAL, detail TEXT, started_at REAL, finished_at REAL
);
CREATE TABLE IF NOT EXISTS third_party_shopping (
    id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, store_domain TEXT NOT NULL,
    question TEXT, position INTEGER, title TEXT, merchant TEXT, price TEXT,
    rating REAL, reviews INTEGER, is_brand INTEGER DEFAULT 0, is_own_store INTEGER DEFAULT 0,
    product_id INTEGER, fetched_at REAL
);
CREATE TABLE IF NOT EXISTS third_party_web (
    id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, store_domain TEXT NOT NULL,
    query TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT, kind TEXT,
    collision INTEGER DEFAULT 0, fetched_at REAL
);
CREATE TABLE IF NOT EXISTS third_party_reviews (
    id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, store_domain TEXT NOT NULL,
    review_id TEXT, rating INTEGER, title TEXT, text TEXT, published TEXT,
    company_score REAL, company_total INTEGER, fetched_at REAL
);
CREATE INDEX IF NOT EXISTS idx_tp_shopping ON third_party_shopping(store_domain, run_id);
CREATE INDEX IF NOT EXISTS idx_tp_web ON third_party_web(store_domain, run_id);
CREATE INDEX IF NOT EXISTS idx_tp_reviews ON third_party_reviews(store_domain, run_id);
"""

_lock = threading.Lock()
_revision = 0


class _Conn(sqlite3.Connection):
    # sqlite3's own `with` only commits; it never closes. Closing here stops
    # each request leaking a file handle (the app hit 1024 and died, 5 Oct 2026).
    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def conn():
    c = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False, factory=_Conn)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, conn() as c:
        have = {r[1] for r in c.execute('PRAGMA table_info(prompt_sets)')}
        if 'product_id' in have:
            if c.execute("SELECT 1 FROM scans WHERE status='running'").fetchone():
                raise RuntimeError('Finish the running scan before migration.')
            backup = Path(str(config.DB_PATH) + '.pre-catalog-' + str(time.time_ns()) + '.bak')
            with sqlite3.connect(backup) as dest:
                c.backup(dest)
            # Preserve legacy baselines and every raw answer. They are not catalog scans.
            c.execute('ALTER TABLE prompt_sets RENAME TO legacy_prompt_sets')
            c.executescript(SCHEMA)
            c.execute("""INSERT INTO prompt_sets(id,legacy_product_id,prompts,tags,created_at,frozen_at)
                         SELECT id,product_id,prompts,tags,created_at,frozen_at FROM legacy_prompt_sets""")
            for row in c.execute('SELECT id,legacy_product_id,prompts FROM prompt_sets').fetchall():
                product = c.execute('SELECT * FROM products WHERE id=?',(row['legacy_product_id'],)).fetchone()
                ids = [row['legacy_product_id']]
                c.execute('UPDATE prompt_sets SET product_ids=?,relevance=?,catalog_snapshot=? WHERE id=?',
                          (json.dumps(ids),json.dumps([ids for _ in json.loads(row['prompts'])]),
                           json.dumps([dict(product)] if product else []),row['id']))
            c.execute('DROP TABLE legacy_prompt_sets')
        c.executescript(SCHEMA)
        # A new prompt version preserves the exact set used by older scans.
        sql = c.execute("SELECT sql FROM sqlite_master WHERE name='prompt_sets'").fetchone()[0]
        if 'store_domain TEXT UNIQUE' in sql:
            backup = Path(str(config.DB_PATH) + '.pre-prompt-versions-' + str(time.time_ns()) + '.bak')
            with sqlite3.connect(backup) as dest:
                c.backup(dest)
            c.execute('BEGIN IMMEDIATE')
            c.execute(sql.replace('prompt_sets', 'prompt_sets_versioned', 1).replace('store_domain TEXT UNIQUE', 'store_domain TEXT'))
            c.execute('INSERT INTO prompt_sets_versioned SELECT * FROM prompt_sets')
            c.execute('DROP TABLE prompt_sets')
            c.execute('ALTER TABLE prompt_sets_versioned RENAME TO prompt_sets')
            c.commit()
        c.execute('CREATE INDEX IF NOT EXISTS idx_prompt_store ON prompt_sets(store_domain,id)')
        c.execute('CREATE TABLE IF NOT EXISTS prompt_types (prompt_set_id INTEGER, prompt TEXT, type TEXT, PRIMARY KEY(prompt_set_id,prompt))')
        # Brand profile, 24 Sep 2026: the Peec-style step 2. `description`
        # and `identity` are shown and stored but do not reach question
        # generation - see MEMORY.md, 2026-09-24.
        for table, cols in (('stores', ('currency','country','brand_name','aliases',
                                        'description','industry','identity','services','markets')),
                            ('prompt_sets', ('tags',))):
            have = {r[1] for r in c.execute('PRAGMA table_info(%s)' % table)}
            for col in cols:
                if col not in have:
                    c.execute("ALTER TABLE %s ADD COLUMN %s TEXT DEFAULT ''" % (table,col))
        # Multi-engine, 21 Sep 2026. Everything stored before this ran was
        # bought from ChatGPT, so the backfill is a statement of fact.
        have = {r[1] for r in c.execute('PRAGMA table_info(answers)')}
        if 'engine' not in have:
            c.execute("ALTER TABLE answers ADD COLUMN engine TEXT NOT NULL DEFAULT 'chatgpt'")
            c.execute("UPDATE answers SET engine='chatgpt' WHERE COALESCE(engine,'')=''")
        # scan_batches gains `engine` INSIDE its primary key, so the table has
        # to be rebuilt rather than altered - one run number now holds one
        # batch per engine instead of one batch outright.
        have = {r[1] for r in c.execute('PRAGMA table_info(scan_batches)')}
        if have and 'engine' not in have:
            c.execute('ALTER TABLE scan_batches RENAME TO scan_batches_pre_engine')
            c.executescript(SCHEMA)
            c.execute("""INSERT INTO scan_batches
                             (scan_id,run_n,engine,apify_run_id,dataset_id,collected,started_at)
                         SELECT scan_id,run_n,'chatgpt',apify_run_id,dataset_id,collected,started_at
                         FROM scan_batches_pre_engine""")
            c.execute('DROP TABLE scan_batches_pre_engine')
        c.execute('CREATE INDEX IF NOT EXISTS idx_answers_engine ON answers(engine)')
        have = {r[1] for r in c.execute('PRAGMA table_info(mentions)')}
        if 'matched_product_id' not in have:
            c.execute('ALTER TABLE mentions ADD COLUMN matched_product_id INTEGER')
            c.execute("""UPDATE mentions SET matched_product_id=(SELECT ps.legacy_product_id
                FROM answers a JOIN scans s ON s.id=a.scan_id JOIN prompt_sets ps ON ps.id=s.prompt_set_id
                WHERE a.id=mentions.answer_id) WHERE is_theirs=1""")
        if 'price' not in have:
            # The price the answer quoted for this product, as written ("€16.99").
            # Empty when the answer gave none, and for answers extracted before
            # this column existed.
            c.execute("ALTER TABLE mentions ADD COLUMN price TEXT DEFAULT ''")
        c.execute('CREATE INDEX IF NOT EXISTS idx_mentions_product ON mentions(matched_product_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_mentions_answer ON mentions(answer_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_answers_scan ON answers(scan_id)')
        # Old extraction had no separate status; flag incomplete stored batches.
        c.execute("INSERT OR IGNORE INTO answer_processing(answer_id,status) SELECT id,'done' FROM answers")
        c.execute("""UPDATE scans SET status=CASE WHEN
            (SELECT COUNT(*) FROM answers WHERE scan_id=scans.id)>total/2.0 THEN 'partial' ELSE 'failed' END,
            error='Some answers were not collected in this legacy scan.'
            WHERE status='done' AND total>0 AND (SELECT COUNT(*) FROM answers WHERE scan_id=scans.id)<total""")
        import accounts
        c.executescript(accounts.SCHEMA)
        # The agent's brain (brain.py, 22 Oct 2026): what it learned from outside sources.
        import brain
        c.executescript(brain.SCHEMA)


_memo = {}
_memo_lock = threading.Lock()


def data_stamp():
    """Changes whenever scan results do: a new scan, a scan finishing, new
    answers or mentions, new questions or products. Cheap (primary keys)."""
    return tuple(one("SELECT (SELECT MAX(id) FROM scans), (SELECT COUNT(*) FROM scans WHERE status IN ('done','partial')),"
                     " (SELECT MAX(id) FROM answers), (SELECT MAX(id) FROM mentions), (SELECT MAX(id) FROM prompt_sets),"
                     " (SELECT COUNT(*) FROM products), (SELECT COUNT(*) FROM stores)"))


def memo(key, fn, stamp=None):
    """Reuse a slow, read-only result until the database changes.

    Keyed on the caller's key plus this process's write counter and the
    database file's timestamp, so any write (here or from another process)
    makes the next call recompute. Callers put anything else the result
    depends on - the signed-in user, today's date - into the key."""
    if stamp is None:
        try:
            stamp = (_revision, os.path.getmtime(config.DB_PATH))
        except OSError:
            return fn()
    full = (key, stamp)
    with _memo_lock:
        if full in _memo:
            return _memo[full]
    value = fn()
    with _memo_lock:
        if len(_memo) > 200:
            _memo.clear()
        _memo[full] = value
    return value


def write(sql, args=()):
    global _revision
    with _lock, conn() as c:
        cur = c.execute(sql, args)
        _revision += 1
        return cur.lastrowid


def one(sql, args=()):
    with conn() as c:
        return c.execute(sql, args).fetchone()


def all_(sql, args=()):
    with conn() as c:
        return c.execute(sql, args).fetchall()


# --- catalogue ---------------------------------------------------------------

def save_catalog(domain, rows, meta):
    with _lock, conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO stores (domain,brand,products,variants,"
            "fetched_at,currency,country) VALUES (?,?,?,?,?,?,?)",
            (domain, meta.get("vendor") or "", meta["products"], meta["variants"],
             time.time(), meta.get("currency") or "", meta.get("country") or ""))
        for r in rows:
            c.execute(
                """INSERT INTO products (store_domain, shopify_id, handle, title,
                       url, price, image, variants, vendor, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(store_domain, shopify_id) DO UPDATE SET
                       handle=excluded.handle, title=excluded.title,
                       url=excluded.url, price=excluded.price,
                       image=excluded.image, variants=excluded.variants,
                       vendor=excluded.vendor, raw_json=excluded.raw_json""",
                (domain, r["shopify_id"], r["handle"], r["title"], r["url"],
                 r["price"], r["image"], r["variants"], r["raw"]["vendor"],
                 json.dumps(r["raw"])))


# --- questions ---------------------------------------------------------------

def decode_prompts(row):
    if not row:
        return None
    d = dict(row)
    for key in ('prompts','tags','clusters','relevance','product_ids','excluded_types','catalog_snapshot'):
        d[key] = json.loads(d.get(key) or '[]')
    return d


def get_prompt_set(store_domain):
    return decode_prompts(one('SELECT * FROM prompt_sets WHERE store_domain=? ORDER BY id DESC LIMIT 1',(store_domain,)))


def _tidy(label):
    label=' '.join(label.split())
    return label[:1].upper()+label[1:].lower() if label.isupper() or label.islower() else label


def product_type(product):
    """What kind of product this is: the store's own collection first, then
    Shopify's product_type, then a word-like tag (not a SKU code)."""
    raw=json.loads(product['raw_json'] or '{}')
    for label in (raw.get('category'),raw.get('product_type')):
        if (label or '').strip():
            return _tidy(label.strip())
    for tag in raw.get('tags') or []:
        if tag and not any(ch.isdigit() for ch in tag) and not tag.isupper():
            return _tidy(tag.strip())
    return 'Uncategorized'


def scope(domain):
    ps = get_prompt_set(domain)
    if ps and ps['frozen_at']:
        return ps
    row = one('SELECT * FROM catalog_scope WHERE store_domain=?',(domain,))
    if row:
        return dict(product_ids=json.loads(row['product_ids']),excluded_types=json.loads(row['excluded_types']))
    return dict(product_ids=[p['id'] for p in all_('SELECT id FROM products WHERE store_domain=?',(domain,))],excluded_types=[])


def save_scope(domain, excluded):
    with _lock, conn() as c:
        c.execute('BEGIN IMMEDIATE')
        ps = c.execute('SELECT * FROM prompt_sets WHERE store_domain=? ORDER BY id DESC LIMIT 1',(domain,)).fetchone()
        if ps and ps['frozen_at']:
            return decode_prompts(ps)
        products = c.execute('SELECT * FROM products WHERE store_domain=?',(domain,)).fetchall()
        excluded = sorted(set(excluded) & {product_type(p) for p in products})
        ids = [p['id'] for p in products if product_type(p) not in excluded]
        if not ids:
            raise ValueError('Include at least one product type.')
        old = c.execute('SELECT product_ids FROM catalog_scope WHERE store_domain=?',(domain,)).fetchone()
        if ps and (not old or json.loads(old[0]) != ids):
            c.execute('DELETE FROM prompt_sets WHERE id=? AND frozen_at IS NULL',(ps['id'],))
        c.execute('INSERT OR REPLACE INTO catalog_scope VALUES (?,?,?)',(domain,json.dumps(ids),json.dumps(excluded)))
    return dict(product_ids=ids,excluded_types=excluded)


def save_prompts(store_domain, prompts, tags=None, clusters=None, relevance=None, expected_ids=None,
                 new_version=False):
    """Atomically save the questions AND coverage; neither can change after freeze.

    `new_version=True` (the merchant changed topics after the lock) saves the
    questions as a new, unfrozen prompt set instead; the frozen one and every
    scan made with it stay exactly as they are."""
    with _lock, conn() as c:
        c.execute('BEGIN IMMEDIATE')
        existing = c.execute('SELECT * FROM prompt_sets WHERE store_domain=? ORDER BY id DESC LIMIT 1',(store_domain,)).fetchone()
        if existing and existing['frozen_at'] and not new_version:
            return decode_prompts(existing)
        selected = scope(store_domain)
        ids = selected['product_ids']
        if expected_ids is not None and set(ids) != set(expected_ids):
            raise ValueError('Catalog selection changed. Generate questions again.')
        if not prompts or len(prompts)>max(config.QUESTION_CLUSTERS_MAX,60) or len(set(q.casefold() for q in prompts))!=len(prompts):
            raise ValueError('Keep distinct, non-empty buyer questions within the configured limit.')
        import accounts
        accounts.check_question_limit(store_domain, len(prompts))
        if not relevance or len(relevance)!=len(prompts):
            raise ValueError('Choose relevant products for every question.')
        allowed=set(ids)
        if any(not group or not set(group)<=allowed for group in relevance):
            raise ValueError('Questions must refer to included catalog products.')
        def pad(values):
            return list(values or [])[:len(prompts)] + ['']*max(0,len(prompts)-len(values or []))
        snapshot=[dict(p) for p in c.execute('SELECT * FROM products WHERE store_domain=?',(store_domain,))]
        values=(json.dumps(prompts),json.dumps(pad(tags)),json.dumps(pad(clusters)),json.dumps(relevance),
                json.dumps(ids),json.dumps(selected['excluded_types']),json.dumps(snapshot),time.time())
        if existing and not existing['frozen_at']:
            c.execute('UPDATE prompt_sets SET prompts=?,tags=?,clusters=?,relevance=?,product_ids=?,excluded_types=?,catalog_snapshot=?,created_at=? WHERE id=?',values+(existing['id'],))
        else:
            c.execute('INSERT INTO prompt_sets(prompts,tags,clusters,relevance,product_ids,excluded_types,catalog_snapshot,created_at,store_domain) VALUES (?,?,?,?,?,?,?,?,?)',values+(store_domain,))
    return get_prompt_set(store_domain)


# --- brand identity ----------------------------------------------------------

def brand(domain):
    """What this store is called, for spotting its products in AI answers."""
    row = one("SELECT * FROM stores WHERE domain=?", (domain,))
    if not row:
        return None
    d = dict(row)
    for key in ("aliases", "identity", "services", "markets"):
        d[key] = [v for v in json.loads(d.get(key) or "[]") if v]
    if not d.get("brand_name"):
        vendor = one("SELECT vendor FROM products WHERE store_domain=? AND vendor != '' "
                     "LIMIT 1", (domain,))
        d["brand_name"] = (vendor["vendor"] if vendor else "") or d["brand"] or domain.split(".")[0].title()
    return d


def _tags(values, limit=14):
    """Trimmed, de-duplicated, order-preserving chip list."""
    out = []
    for v in values or []:
        v = " ".join(str(v).split())[:60]
        if v and v.lower() not in {o.lower() for o in out}:
            out.append(v)
    return out[:limit]


def save_brand(domain, name, aliases, country, currency, profile=None):
    """Persist identity. `profile` carries the step 2 brand-profile fields."""
    p = profile or {}
    sets = ["brand_name=?", "aliases=?", "country=?", "currency=?"]
    args = [name.strip(), json.dumps(_tags(aliases)),
            (country or "").strip().upper()[:2], (currency or "").strip().upper()[:3]]
    if "description" in p:
        sets.append("description=?")
        args.append(" ".join((p.get("description") or "").split())[:600])
    if "industry" in p:
        sets.append("industry=?")
        args.append(" ".join((p.get("industry") or "").split())[:80])
    for key in ("identity", "services", "markets"):
        if key in p:
            sets.append("%s=?" % key)
            args.append(json.dumps(_tags(p.get(key))))
    write("UPDATE stores SET %s WHERE domain=?" % ", ".join(sets), tuple(args) + (domain,))
    return brand(domain)


def freeze(prompt_set_id):
    write("UPDATE prompt_sets SET frozen_at=? WHERE id=? AND frozen_at IS NULL",
          (time.time(), prompt_set_id))
