"""SQLite storage.

One file, mvp.db, created on first run. The schema is the full one from
PLAN.md even though phases 1-2 only write `products` and `prompt_sets` -
creating the scan tables now costs nothing and means phase 3 doesn't need a
migration.
"""

import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "mvp.db")

SCHEMA = """
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
    raw_json     TEXT,
    UNIQUE (store_domain, shopify_id)
);

CREATE TABLE IF NOT EXISTS prompt_sets (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    prompts    TEXT NOT NULL,          -- JSON array of 5 strings
    frozen_at  REAL,                   -- NULL until the user confirms them
    created_at REAL NOT NULL
);

-- Not used until phase 3. Here so adding it later is not a migration.
CREATE TABLE IF NOT EXISTS scans (
    id             INTEGER PRIMARY KEY,
    prompt_set_id  INTEGER NOT NULL REFERENCES prompt_sets(id),
    run_at         REAL,
    status         TEXT,
    cost_cents     INTEGER,
    model_versions TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    id       INTEGER PRIMARY KEY,
    scan_id  INTEGER NOT NULL REFERENCES scans(id),
    prompt   TEXT,
    model    TEXT,
    run_n    INTEGER,
    raw_text TEXT
);
CREATE TABLE IF NOT EXISTS mentions (
    id           INTEGER PRIMARY KEY,
    answer_id    INTEGER NOT NULL REFERENCES answers(id),
    product_name TEXT,
    brand        TEXT,
    rank         INTEGER,
    is_theirs    INTEGER
);
CREATE TABLE IF NOT EXISTS scores (
    id              INTEGER PRIMARY KEY,
    scan_id         INTEGER NOT NULL REFERENCES scans(id),
    visibility      REAL,
    appearance_rate REAL,
    avg_rank        REAL,
    sov_pct         REAL
);

CREATE INDEX IF NOT EXISTS idx_products_domain ON products(store_domain);
CREATE INDEX IF NOT EXISTS idx_prompts_product ON prompt_sets(product_id);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------- products

def save_products(domain, products):
    """Upsert a fetched catalogue. Returns how many rows are now stored."""
    with connect() as conn:
        for p in products:
            conn.execute(
                """INSERT INTO products
                     (store_domain, shopify_id, handle, title, url, price,
                      image, variants, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT (store_domain, shopify_id) DO UPDATE SET
                     title=excluded.title, price=excluded.price,
                     image=excluded.image, variants=excluded.variants,
                     raw_json=excluded.raw_json""",
                (domain, p["shopify_id"], p["handle"], p["title"], p["url"],
                 p["price"], p["image"], p["variants"], json.dumps(p["raw"])),
            )
        return conn.execute(
            "SELECT COUNT(*) c FROM products WHERE store_domain=?", (domain,)
        ).fetchone()["c"]


def list_products(domain, q=None):
    sql = "SELECT * FROM products WHERE store_domain=?"
    args = [domain]
    if q:
        sql += " AND lower(title) LIKE ?"
        args.append("%" + q.lower() + "%")
    sql += " ORDER BY id"
    with connect() as conn:
        return conn.execute(sql, args).fetchall()


def get_product(pid):
    with connect() as conn:
        return conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()


def stores():
    with connect() as conn:
        return conn.execute(
            """SELECT store_domain, COUNT(*) n, SUM(variants) v
               FROM products GROUP BY store_domain ORDER BY store_domain"""
        ).fetchall()


# ------------------------------------------------------------ prompt sets

def get_prompt_set(product_id):
    with connect() as conn:
        return conn.execute(
            """SELECT * FROM prompt_sets WHERE product_id=?
               ORDER BY id DESC LIMIT 1""", (product_id,)
        ).fetchone()


def save_prompt_set(product_id, prompts):
    """Write a draft set. Refuses to overwrite a frozen one - the whole point
    of freezing is that the trend chart compares like with like."""
    existing = get_prompt_set(product_id)
    if existing and existing["frozen_at"]:
        return existing
    with connect() as conn:
        if existing:
            conn.execute("UPDATE prompt_sets SET prompts=? WHERE id=?",
                         (json.dumps(prompts), existing["id"]))
        else:
            conn.execute(
                """INSERT INTO prompt_sets (product_id, prompts, created_at)
                   VALUES (?,?,?)""",
                (product_id, json.dumps(prompts), time.time()),
            )
    return get_prompt_set(product_id)


def freeze_prompt_set(product_id, prompts):
    save_prompt_set(product_id, prompts)
    ps = get_prompt_set(product_id)
    if ps and not ps["frozen_at"]:
        with connect() as conn:
            conn.execute(
                "UPDATE prompt_sets SET prompts=?, frozen_at=? WHERE id=?",
                (json.dumps(prompts), time.time(), ps["id"]),
            )
    return get_prompt_set(product_id)
