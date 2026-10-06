"""Produkto MVP - phases 1 and 2 of PLAN.md.

    paste a Shopify URL -> read the catalogue -> pick a product
                        -> five buyer questions -> freeze them

Run it:

    python3 mvp/server/app.py

then open http://localhost:8000

Standard library only - no pip install, no virtualenv. PLAN.md specifies
FastAPI; this uses http.server instead because the machine has Python 3.9 with
no FastAPI and installing it would mean setting up a virtualenv first. Routing
is kept in one dispatch table so moving to FastAPI later is a small change.
"""

import html
import json
import os
import re
import sys
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brand                                                    # noqa: E402
import catalog                                                  # noqa: E402
import questions                                                # noqa: E402
import render                                                   # noqa: E402
import store                                                    # noqa: E402

# Brand reads are cached per domain for the life of the process. Re-reading a
# homepage on every page view would be rude to the store and slow for us.
BRANDS = {}

PORT = int(os.environ.get("PORT", "8000"))

# Catalogue fetches run in a thread so the page can poll; PLAN.md phase 3
# reuses this for scans.
JOBS = {}
JOBS_LOCK = threading.Lock()


# --------------------------------------------------------------- rendering

def esc(s):
    return html.escape(str(s if s is not None else ""))


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s - Produkto</title>
<style>
 :root{--navy:#071B37;--mint:#5EE6B8;--mint-dk:#158760;--mint-soft:#E9FBF4;
   --mint-line:#B4F0DC;--bg:#F6F8FA;--surface:#fff;--surface-2:#F1F4F8;
   --border:#E1E7EE;--border-2:#C6D0DC;--ink:#071B37;--ink-2:#4C5F78;
   --ink-3:#8494A8;--danger:#C4443F;--r:10px;
   --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
   --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
 *{box-sizing:border-box}[hidden]{display:none!important}
 body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
   font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
 .shell{max-width:940px;margin:0 auto;padding:0 20px 80px}
 header{display:flex;align-items:center;gap:12px;padding:22px 0 0}
 .mark{width:26px;height:26px;border-radius:7px;background:var(--navy);
   color:#fff;display:grid;place-items:center;font-weight:700;font-size:15px}
 .wordmark{font-weight:700;letter-spacing:.14em;font-size:14px}
 .card{background:var(--surface);border:1px solid var(--border);
   border-radius:14px;margin-top:24px;padding:34px 36px 30px}
 @media(max-width:620px){.card{padding:24px 18px}}
 .tag{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;
   text-transform:uppercase;color:var(--mint-dk);font-weight:600}
 h1{font-size:clamp(25px,4vw,33px);line-height:1.12;letter-spacing:-.025em;
   margin:8px 0 0}
 .sub{margin:10px 0 0;color:var(--ink-2);max-width:60ch}
 label{font-weight:600;font-size:14.5px;display:block;margin-bottom:6px}
 .hint{font-size:13px;color:var(--ink-3)}
 input[type=text]{width:100%%;font:400 15px/1.4 var(--sans);color:var(--ink);
   background:var(--surface);border:1px solid var(--border-2);
   border-radius:var(--r);padding:12px 14px}
 input[type=text]:focus,button:focus-visible{outline:2px solid var(--mint-dk);
   outline-offset:1px}
 .row{display:flex;gap:10px;margin-top:26px}
 .row input{flex:1}
 .btn{font:700 14.5px/1 var(--sans);cursor:pointer;border:1.5px solid transparent;
   border-radius:var(--r);padding:13px 22px;white-space:nowrap}
 .btn.primary{background:var(--mint);color:var(--navy)}
 .btn.ghost{background:none;color:var(--ink-2);border-color:var(--border-2)}
 .btn:disabled{opacity:.55;cursor:default}
 .err{margin-top:18px;background:#FDF2F2;border:1px solid #F3C9C7;
   color:#8A2F2B;border-radius:var(--r);padding:12px 14px;font-size:14px}
 .ok{display:inline-flex;align-items:center;gap:7px;background:var(--mint-soft);
   border:1px solid var(--mint-line);border-radius:99px;padding:6px 13px;
   font-size:12.5px;font-weight:500;margin-top:22px}
 .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
   border:1px solid var(--border);border-radius:var(--r);overflow:hidden;
   margin-top:20px}
 .stats>div{padding:13px 15px;border-right:1px solid var(--border)}
 .stats>div:last-child{border-right:0}
 .stats dt{font-family:var(--mono);font-size:10px;letter-spacing:.1em;
   text-transform:uppercase;color:var(--ink-3);margin:0 0 4px}
 .stats dd{margin:0;font-family:var(--mono);font-size:16px;font-weight:500}
 .grid{display:grid;gap:12px;margin-top:18px;
   grid-template-columns:repeat(auto-fill,minmax(168px,1fr));
   max-height:460px;overflow-y:auto;padding:2px}
 .pcard{display:flex;flex-direction:column;text-align:left;font:inherit;
   color:inherit;cursor:pointer;background:var(--surface);
   border:1.5px solid var(--border);border-radius:var(--r);overflow:hidden;
   padding:0;text-decoration:none}
 .pcard:hover{border-color:var(--border-2)}
 .pthumb{aspect-ratio:4/3;background:var(--surface-2);display:block}
 .pthumb img{width:100%%;height:100%%;object-fit:cover;display:block}
 .pbody{padding:10px 12px 12px}
 .pbody .t{display:block;font-size:13.5px;font-weight:600;line-height:1.3}
 .pbody .p{display:block;font-family:var(--mono);font-size:12px;
   color:var(--ink-3);margin-top:3px}
 .qrow{display:grid;grid-template-columns:26px 1fr;gap:10px;align-items:center;
   margin-bottom:10px}
 .qn{font-family:var(--mono);font-size:12px;color:var(--ink-3);text-align:center}
 .qrow input{font-family:var(--mono);font-size:13.5px}
 .freeze{margin-top:18px;display:flex;gap:11px;background:var(--surface-2);
   border-radius:var(--r);padding:14px 16px;font-size:13.5px;color:var(--ink-2)}
 .freeze p{margin:0}
 .nav{display:flex;gap:12px;margin-top:28px;padding-top:20px;
   border-top:1px solid var(--border)}
 .nav .right{margin-left:auto;display:flex;gap:10px}
 a{color:var(--mint-dk)}
 table{width:100%%;border-collapse:collapse;margin-top:8px;font-size:14px}
 td,th{text-align:left;padding:7px 0;border-bottom:1px solid var(--border)}
 th{font-family:var(--mono);font-size:10px;letter-spacing:.1em;
   text-transform:uppercase;color:var(--ink-3);font-weight:600}
 .miss{color:var(--danger)}.has{color:var(--mint-dk)}
 .spin{width:18px;height:18px;border-radius:50%%;border:2.5px solid var(--surface-2);
   border-top-color:var(--mint);animation:s .7s linear infinite;display:inline-block;
   vertical-align:-4px;margin-right:9px}
 @keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
<div class="shell">
 <header><span class="mark">P</span><span class="wordmark">PRODUKTO</span></header>
 %(body)s
</div></body></html>"""


def page(title, body):
    return (PAGE % {"title": esc(title), "body": body}).encode("utf-8")


# ------------------------------------------------------------------ routes

def view_home(qs):
    err = qs.get("err", [None])[0]
    rows = ""
    for s in store.stores():
        rows += ('<tr><td><a href="/store?domain=%s">%s</a></td>'
                 '<td class="mono">%d products</td>'
                 '<td class="mono">%s variants</td></tr>'
                 % (urllib.parse.quote(s["store_domain"]), esc(s["store_domain"]),
                    s["n"], "{:,}".format(s["v"] or 0)))
    prev = ('<div class="card"><div class="tag">Already read</div>'
            '<table><tr><th>Store</th><th>Products</th><th>Variants</th></tr>'
            + rows + "</table></div>") if rows else ""
    return page("Read a store", """
 <div class="card">
  <div class="tag">Step 1 of 4</div>
  <h1>Read a Shopify catalogue</h1>
  <p class="sub">Paste any Shopify store. We read its public product feed,
   then you pick the product you want to track.</p>
  %s
  <form class="row" method="post" action="/fetch">
   <input type="text" name="domain" placeholder="yourstore.com"
          autofocus spellcheck="false" required>
   <button class="btn primary" type="submit">Read catalogue</button>
  </form>
  <p class="hint" style="margin-top:10px">Works on any store that publishes
   /products.json &mdash; which is the Shopify default.</p>
 </div>%s""" % (('<div class="err">%s</div>' % esc(err)) if err else "", prev))


def view_onboarding(qs):
    """The real 7-step onboarding UI, filled with this store's live data."""
    domain = (qs.get("domain", [""])[0] or "").strip()
    if not domain:
        return redirect("/")
    rows = store.list_products(domain)
    if not rows:
        return redirect("/?err=" + urllib.parse.quote(
            "No catalogue stored for %s. Read it first." % domain))
    b = BRANDS.get(domain)
    if not b:
        prods = [{"raw": json.loads(r["raw_json"] or "{}")} for r in rows]
        b = brand.read(domain, prods)
        BRANDS[domain] = b

    def qfor(row):
        return questions.generate(row["title"], row["price"],
                                  json.loads(row["raw_json"] or "{}"),
                                  currency=b.get("symbol") or "€",
                                  region=b.get("region"))

    return render.render(domain, b, rows, qfor)


def view_brand(qs):
    domain = (qs.get("domain", [""])[0] or "").strip()
    if not domain:
        return redirect("/")
    rows = store.list_products(domain)
    if not rows:
        return redirect("/?err=" + urllib.parse.quote(
            "No catalogue stored for %s. Read it first." % domain))
    b = BRANDS.get(domain)
    if not b:
        prods = [{"raw": json.loads(r["raw_json"] or "{}")} for r in rows]
        b = brand.read(domain, prods)
        BRANDS[domain] = b

    alias_rows = "".join(
        '<div class="qrow"><span class="qn">%d</span>'
        '<input type="text" value="%s"></div>' % (i + 1, esc(a))
        for i, a in enumerate(b["aliases"])) or \
        '<p class="hint">No brand name published on the homepage.</p>'

    def src(field):
        s = b["sources"].get(field, "")
        cls = "miss" if s == "not found" else "has"
        return '<span class="%s" style="font-size:12px">%s</span>' % (cls, esc(s))

    desc = b["description"] or ""
    desc_block = ('<textarea rows="4" style="width:100%%;font:400 14.5px/1.5 '
                  'var(--sans);border:1px solid var(--border-2);'
                  'border-radius:var(--r);padding:12px 14px">%s</textarea>'
                  % esc(desc)) if desc else (
        '<div class="err">This store publishes no meta description. '
        'We leave this blank rather than writing one for you &mdash; an '
        'invented description is worse than an empty field.</div>')

    variants = sum(r["variants"] for r in rows)
    warn = ""
    if len(rows) < 150:
        warn = ('<div class="err" style="margin-top:18px">Heads up: %d products '
                '/ %s variants is below the 150-SKU floor in the ICP. A '
                'catalogue this size can be hand-fixed in an afternoon, so '
                'there may be nothing here worth selling.</div>'
                % (len(rows), "{:,}".format(variants)))

    unreachable = "" if b["reachable"] else (
        '<div class="err">Couldn\'t load the homepage, so brand fields come '
        'from the product feed alone.</div>')

    return page("Brand Hub - " + domain, """
 <div class="card">
  <div class="tag">Step 2 of 4</div>
  <h1>Brand Hub</h1>
  <p class="sub">Read from %s just now. Check it and fix anything wrong &mdash;
   every field below says where it came from.</p>
  %s
  <div class="ok">&#10003; Read from %s</div>

  <div style="margin-top:26px">
   <label>Brand name %s</label>
   <input type="text" value="%s">
  </div>

  <div style="margin-top:22px">
   <label>Brand aliases %s</label>
   <p class="hint" style="margin-bottom:10px">Other names and spellings. This is
    what we search for in an AI answer, so a missing alias reads back as a
    lower score.</p>
   %s
  </div>

  <div style="margin-top:22px">
   <label>Short description %s</label>
   %s
  </div>

  <div style="margin-top:22px">
   <label>Industry %s</label>
   <input type="text" value="%s">
  </div>

  <div class="stats">
   <div><dt>Products</dt><dd>%d</dd></div>
   <div><dt>Variants (SKUs)</dt><dd>%s</dd></div>
  </div>
  %s

  <div class="nav">
   <a class="btn ghost" href="/">Back</a>
   <div class="right">
    <a class="btn primary" href="/store?domain=%s">Continue</a>
   </div>
  </div>
 </div>""" % (esc(domain), unreachable, esc(domain),
              src("name"), esc(b["name"]),
              src("name"), alias_rows,
              src("description"), desc_block,
              src("industry"), esc(b["industry"]),
              len(rows), "{:,}".format(variants), warn,
              urllib.parse.quote(domain)))


def view_store(qs):
    domain = (qs.get("domain", [""])[0] or "").strip()
    q = (qs.get("q", [""])[0] or "").strip()
    if not domain:
        return redirect("/")
    rows = store.list_products(domain, q or None)
    if not rows:
        if q:
            allrows = store.list_products(domain)
            if allrows:
                cards = '<p class="hint" style="margin-top:20px">No product matches &ldquo;%s&rdquo;.</p>' % esc(q)
                return _store_page(domain, allrows, q, cards)
        return redirect("/?err=" + urllib.parse.quote(
            "No catalogue stored for %s. Read it first." % domain))
    return _store_page(domain, rows, q, None)


def _store_page(domain, rows, q, override):
    total_v = sum(r["variants"] for r in rows)
    cards = override
    if cards is None:
        cards = '<div class="grid">'
        for r in rows:
            img = ('<span class="pthumb"><img src="%s" alt="" loading="lazy"></span>'
                   % esc(r["image"])) if r["image"] else '<span class="pthumb"></span>'
            price = ("&euro;" + esc(r["price"])) if r["price"] else "&mdash;"
            cards += ('<a class="pcard" href="/product?id=%d">%s'
                      '<span class="pbody"><span class="t">%s</span>'
                      '<span class="p">%s</span></span></a>'
                      % (r["id"], img, esc(r["title"]), price))
        cards += "</div>"
    return page(domain, """
 <div class="card">
  <div class="tag">Step 3 of 4</div>
  <h1>%s</h1>
  <p class="sub">Pick the product you want to track. Everything after this
   is generated from that product&rsquo;s own data.</p>
  <div class="stats">
   <div><dt>Products</dt><dd>%d</dd></div>
   <div><dt>Variants (SKUs)</dt><dd>%s</dd></div>
  </div>
  <form class="row" method="get" action="/store">
   <input type="hidden" name="domain" value="%s">
   <input type="text" name="q" placeholder="Search products" value="%s">
   <button class="btn ghost" type="submit">Search</button>
  </form>
  %s
  <div class="nav"><a class="btn ghost" href="/brand?domain=%s">Back to brand</a></div>
 </div>""" % (esc(domain), len(rows), "{:,}".format(total_v),
              esc(domain), esc(q), cards, urllib.parse.quote(domain)))


def view_product(qs):
    try:
        pid = int(qs.get("id", ["0"])[0])
    except ValueError:
        return redirect("/")
    p = store.get_product(pid)
    if not p:
        return redirect("/")

    raw = json.loads(p["raw_json"] or "{}")
    ps = store.get_prompt_set(pid)
    frozen = bool(ps and ps["frozen_at"])
    if ps:
        prompts = json.loads(ps["prompts"])
    else:
        _b = BRANDS.get(p["store_domain"]) or {}
        prompts = questions.generate(p["title"], p["price"], raw,
                                     currency=_b.get("symbol") or "€",
                                     region=_b.get("region"))
        store.save_prompt_set(pid, prompts)

    have, score = questions.confidence(raw)
    facts = "".join(
        '<tr><td>%s</td><td class="%s">%s</td></tr>'
        % (k.replace("_", " ").title(), "has" if v else "miss",
           "stated" if v else "not stated")
        for k, v in have.items())

    qrows = "".join(
        '<div class="qrow"><span class="qn">%d</span>'
        '<input type="text" name="q%d" value="%s"%s></div>'
        % (i + 1, i, esc(t), " readonly" if frozen else "")
        for i, t in enumerate(prompts))

    if frozen:
        action = ('<div class="ok">&#10003; Frozen &mdash; these five are locked '
                  'so week-to-week scores stay comparable</div>')
        btn = ""
    else:
        action = ""
        btn = ('<div class="right">'
               '<button class="btn primary" type="submit">Freeze these five</button>'
               '</div>')

    price = ("&euro;" + esc(p["price"])) if p["price"] else "&mdash;"
    return page(p["title"], """
 <div class="card">
  <div class="tag">Step 4 of 4</div>
  <h1>%s</h1>
  <p class="sub">The buyer questions this product should be a candidate for,
   built from its stated price, material and dimensions. Edit anything that
   doesn&rsquo;t sound like your customer.</p>
  %s
  <form method="post" action="/freeze">
   <input type="hidden" name="id" value="%d">
   <div style="margin-top:24px">%s</div>
   <div class="freeze"><p><b>These get locked once you freeze them.</b>
    A visibility score is only comparable week to week if the questions stay
    the same. Changing them later starts a fresh line on the chart.</p></div>
   <div class="nav">
    <a class="btn ghost" href="/store?domain=%s">Back to catalogue</a>%s
   </div>
  </form>
 </div>

 <div class="card">
  <div class="tag">What the page actually states</div>
  <p class="sub">%s &middot; %s &middot; <a href="%s" target="_blank"
   rel="noopener">view product page</a></p>
  <table><tr><th>Attribute</th><th>Status</th></tr>%s</table>
  <p class="hint" style="margin-top:14px">%d of 4 present. This is the same gap
   the audit scores: an assistant can only recommend on facts the page states.</p>
 </div>""" % (esc(p["title"]), action, pid, qrows,
              urllib.parse.quote(p["store_domain"]), btn,
              price, esc(p["store_domain"]), esc(p["url"]), facts, score))


# ------------------------------------------------------------------ actions

def act_fetch(form):
    raw = (form.get("domain", [""])[0] or "").strip()
    try:
        domain = catalog.normalise_domain(raw)
        products, meta = catalog.fetch(domain)
    except catalog.CatalogError as e:
        return redirect("/?err=" + urllib.parse.quote(str(e)))
    except Exception as e:                                      # noqa: BLE001
        traceback.print_exc()
        return redirect("/?err=" + urllib.parse.quote("Unexpected error: %s" % e))
    store.save_products(domain, products)
    try:
        BRANDS[domain] = brand.read(domain, products)
    except Exception:                                           # noqa: BLE001
        traceback.print_exc()          # a brand read failing must not block
    return redirect("/onboarding?domain=" + urllib.parse.quote(domain))


def act_freeze(form):
    try:
        pid = int(form.get("id", ["0"])[0])
    except ValueError:
        return redirect("/")
    prompts = [(form.get("q%d" % i, [""])[0] or "").strip() for i in range(5)]
    prompts = [p for p in prompts if p]
    if len(prompts) >= 1:
        store.freeze_prompt_set(pid, prompts)
    return redirect("/product?id=%d" % pid)


ROUTES_GET = {"/": view_home, "/brand": view_brand,
              "/onboarding": view_onboarding,
              "/store": view_store, "/product": view_product}
ROUTES_POST = {"/fetch": act_fetch, "/freeze": act_freeze}


def redirect(location):
    return ("redirect", location)


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    server_version = "Produkto/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, result):
        if isinstance(result, tuple) and result[0] == "redirect":
            self.send_response(303)
            self.send_header("Location", result[1])
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        fn = ROUTES_GET.get(u.path)
        if not fn:
            self.send_error(404)
            return
        try:
            self._send(fn(urllib.parse.parse_qs(u.query)))
        except Exception:                                       # noqa: BLE001
            traceback.print_exc()
            self.send_error(500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        fn = ROUTES_POST.get(u.path)
        if not fn:
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"))
        try:
            self._send(fn(form))
        except Exception:                                       # noqa: BLE001
            traceback.print_exc()
            self.send_error(500)


def main():
    store.init()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("\n  Produkto MVP  ->  http://localhost:%d\n" % PORT)
    print("  database: %s" % store.DB_PATH)
    print("  stop with Ctrl-C\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")


if __name__ == "__main__":
    main()
