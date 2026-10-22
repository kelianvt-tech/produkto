"""Admin hub (/admin): one page for Kelian with everything important, admin only.

Built 22 Oct 2026 (Kelian: "one central place to find all of this"). Groups, in plain words:
the live app and its accounts, every store (demo stores only he sees, customers' stores),
the agent brain, the internal tools, the marketing site getprodukto.com with a free live
check of its SEO/AEO basics, and the outside accounts (Stripe, Apify, Netlify, ...) as links.

Free to open: the live checks are plain HTTP fetches of our own site plus Apify's usage
endpoint (no charge), cached for ten minutes. Nothing here spends money, and no key is shown.
The accounts table that used to be /admin is now /admin/accounts (accounts.admin_page).
"""
import concurrent.futures
import re
import time
import urllib.parse
import urllib.request
from html import escape as E

import config
import db

APP_URL = "https://app.getprodukto.com"
SITE_URL = "https://getprodukto.com"
BRAIN_PLAN = "https://claude.ai/artifact/RHww22r74Zmn9LuJPj4L5q"
CACHE_SECONDS = 600
AI_BOTS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "ClaudeBot", "Google-Extended", "Bingbot")

# Outside accounts. Plain links only; logins stay in Kelian's browser, keys stay in .env.
EXTERNAL = [
    ("Money", [
        ("Stripe", "https://dashboard.stripe.com", "Payments, subscriptions, payment links"),
        ("Cost tracker", "https://docs.google.com/spreadsheets/d/1mcls2aG51pno6hZ7xqeIb3Rg8lDnXwWSoFe6WYkNQ34",
         "Every subscription and usage cost, monthly total and forecast"),
        ("Apify billing", "https://console.apify.com/billing", "Shared by daily scans, the brain and third-party pulls"),
        ("OpenAI usage", "https://platform.openai.com/usage", "Brand profile, buyer questions, extraction"),
    ]),
    ("Hosting", [
        ("Hetzner", "https://console.hetzner.cloud/", "The app server (CX23, Falkenstein) and its backups"),
        ("Netlify", "https://app.netlify.com/sites/dapper-cascaron-576cec", "Hosts getprodukto.com"),
        ("Namecheap DNS", "https://ap.www.namecheap.com/domains/list/", "Domain getprodukto.com and its DNS records"),
        ("GitHub", "https://github.com/kelianvt-tech/produkto", "The private code repository, shared with Gabe"),
    ]),
    ("Sales and email", [
        ("Instantly", "https://app.instantly.ai", "Cold email campaigns (Growth plan, 1,000 contacts a month)"),
        ("Close", "https://app.close.com", "CRM and calling, kelian@getprodukto.com"),
        ("Gmail", "https://mail.google.com", "kelian@getprodukto.com inbox"),
        ("Google Workspace", "https://admin.google.com", "Mailboxes and the app's sending address"),
    ]),
    ("Shopify", [
        ("Test store", "https://admin.shopify.com/store/produkto-test", "produkto-test, for publishing tests"),
        ("Partner dashboard", "https://partners.shopify.com", "The Produkto app and dev stores"),
    ]),
]

_cache = {}


def fetch(url, timeout=5):
    """(status, text). Status 0 = could not reach it. Patched in tests."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Produkto admin hub"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:                          # noqa: BLE001 - unreachable is a result, not a crash
        return 0, ""


def apify_usage():
    """(used, limit) dollars this month, or None. Patched in tests."""
    try:
        import apify_answers
        d = apify_answers._request("GET", "/users/me/limits")["data"]
        return float(d["current"].get("monthlyUsageUsd") or 0), float(d["limits"].get("maxMonthlyUsageUsd") or 0)
    except Exception:                          # noqa: BLE001 - no key or no network
        return None


def live():
    """Live checks only run on a real database (produkto.db, or a copy of it); tests never touch the network."""
    import os
    return os.path.basename(config.DB_PATH).startswith("produkto.db")


def _cached(key, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


# --- Live checks -------------------------------------------------------------

def robots_ai(text):
    """Which AI crawlers robots.txt shuts out of the whole site. [] = all allowed."""
    groups, agents, rules = [], [], False
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        if k.lower() == "user-agent":
            if rules:
                agents, rules = [], False
            if not agents:
                groups.append((agents, set()))
            agents.append(v.lower())
        elif k.lower() == "disallow" and groups:
            rules = True
            groups[-1][1].add(v)
        elif k.lower() == "allow":
            rules = True
    out = []
    for bot in AI_BOTS:
        own = [g for g in groups if bot.lower() in g[0]] or [g for g in groups if "*" in g[0]]
        if any("/" in g[1] for g in own):
            out.append(bot)
    return out


def sitemap_urls(text):
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text or "")


def site_status():
    """Free check of getprodukto.com: pages answer, robots/sitemap/llms.txt exist, AI crawlers allowed."""
    def run():
        paths = {"home": "/", "pricing": "/pricing", "guides": "/guides", "robots": "/robots.txt",
                 "sitemap": "/sitemap.xml", "llms": "/llms.txt", "app": None}
        urls = {k: (SITE_URL + p if p else APP_URL + "/login") for k, p in paths.items()}
        with concurrent.futures.ThreadPoolExecutor(len(urls)) as ex:
            res = dict(zip(urls, ex.map(fetch, urls.values())))
        home = res["home"][1]
        return dict(
            res={k: v[0] for k, v in res.items()},
            title=(re.search(r"<title>(.*?)</title>", home, re.S | re.I) or [None, ""])[1].strip(),
            description=(re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', home, re.I) or [None, ""])[1],
            schema="application/ld+json" in home,
            blocked=robots_ai(res["robots"][1]) if res["robots"][0] == 200 else None,
            pages=sitemap_urls(res["sitemap"][1]) if res["sitemap"][0] == 200 else [],
            checked=time.time())
    if not live():
        return dict(res={k: 0 for k in ("home", "pricing", "guides", "robots", "sitemap", "llms", "app")},
                    title="", description="", schema=False, blocked=None, pages=[], checked=time.time())
    return _cached("site", run)


# --- Pieces ----------------------------------------------------------------
# Look: the Produkto brand kit (produkto-site/brand-kit/index.html). Midnight navy, IBM Plex Mono
# for labels and numbers ("mono speaks"), Geist for explanations ("Geist explains"), signal green
# for live/OK, alert red only for problems, a faint dot grid. Light mode is the kit's "paper".

def _pill(ok, yes="OK", no="Problem", warn=False):
    cls = "ok" if ok else ("warn" if warn else "bad")
    return '<span class="st %s"><i></i>%s</span>' % (cls, E(yes if ok else no))


def _when(ts):
    return time.strftime("%d %b %Y", time.localtime(ts)) if ts else "never"


_ARROW = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 11 11 5M6 5h5v5"/></svg>'


def _link(label, href, sub="", ext=False):
    tgt = ' target="_blank" rel="noopener"' if ext else ""
    return ('<a class="tile" href="%s"%s><span class="tile-t">%s%s</span>%s</a>'
            % (E(href), tgt, E(label), _ARROW if ext else '<span class="go">→</span>',
               ('<span class="tile-d">%s</span>' % E(sub)) if sub else ""))


def _slot(label, sub):
    return '<div class="tile slot"><span class="tile-t">%s</span><span class="tile-d">%s</span></div>' % (E(label), E(sub))


def _card(n, title, desc, body, wide=False):
    return ('<section class="sec%s"><div class="sec-h"><span class="lbl"><b>%02d</b> · %s</span>'
            '<p>%s</p></div><div class="panel">%s</div></section>' % (" wide" if wide else "", n, E(title), desc, body))


def _app_card(n):
    import accounts
    users = db.all_("SELECT is_admin, disabled FROM users")
    customers = sum(1 for u in users if not u["is_admin"])
    paused = sum(1 for u in users if not u["is_admin"] and u["disabled"])
    waiting = db.one("SELECT COUNT(*) n FROM invites WHERE used_at IS NULL")["n"]
    here = accounts.base_url()
    links = [
        _link("Live app", APP_URL, "app.getprodukto.com. What customers sign in to.", ext=True),
        _link("Accounts and invites", "/admin/accounts",
              "%d customer%s%s · %d invite%s waiting" % (customers, "" if customers == 1 else "s",
                                                        " (%d paused)" % paused if paused else "",
                                                        waiting, "" if waiting == 1 else "s")),
        _link("Scan costs", "/costs", "What every scan cost."),
    ]
    note = ("" if here.rstrip("/") == APP_URL else
            '<p class="hint">Local copy (%s). Numbers come from this copy\'s database.</p>' % E(here))
    return _card(n, "The app", "Where customers sign in, and who has an account.",
                 '<div class="tiles">%s</div>%s' % ("".join(links), note))


def _stores():
    import scheduler
    try:
        daily = set(scheduler.scannable())
    except Exception:                          # noqa: BLE001
        daily = set()
    out = []
    for s in db.all_("SELECT domain, COALESCE(NULLIF(brand_name,''), brand, domain) name FROM stores ORDER BY domain"):
        d = s["domain"]
        owners = [r["email"] for r in db.all_(
            "SELECT u.email FROM user_stores o JOIN users u ON u.id=o.user_id WHERE o.store_domain=? AND u.is_admin=0", (d,))]
        last = db.one("SELECT MAX(s.run_at) t FROM scans s JOIN prompt_sets p ON p.id=s.prompt_set_id "
                      "WHERE p.store_domain=?", (d,))["t"]
        out.append(dict(domain=d, name=s["name"], owners=owners, last=last,
                        daily=d in daily and d not in config.DAILY_SCAN_EXCLUDE))
    return out


def _stores_card(n, stores):
    rows = []
    for s in stores:
        q = urllib.parse.quote(s["domain"])
        who = (E(", ".join(s["owners"])) if s["owners"] else '<span class="tag">Demo · only you</span>')
        tools = "".join('<a href="%s">%s</a>' % (E(h), E(l)) for l, h in (
            ("Dashboard", "/?d=" + q), ("Questions", "/buyer-questions?d=" + q),
            ("Opportunities", "/opportunities?d=" + q), ("Agent", "/content?d=" + q))
            + ((("Third-party", "/admin/third-party?d=" + q),) if _optional("third_party") else ()))
        rows.append('<tr><td><div class="store"><img src="/icon?d=%s" alt="" loading="lazy" '
                    'onerror="this.style.visibility=\'hidden\'"><span><b>%s</b><span class="m">%s</span></span></div></td>'
                    '<td>%s</td><td class="m">%s</td><td class="m">%s</td><td><div class="acts">%s</div></td></tr>'
                    % (E(q), E(s["name"]), E(s["domain"]), who, _pill(s["daily"], "Daily", "By hand", warn=True),
                       _when(s["last"]), tools))
    table = ('<div class="scroll"><table><thead><tr><th>Store</th><th>Who sees it</th>'
             '<th>Scans</th><th>Last scan</th><th>Open</th></tr></thead><tbody>%s</tbody></table></div>'
             % ("".join(rows) or '<tr><td colspan="5">No stores yet.</td></tr>'))
    return _card(n, "Stores", "Demo stores have no customer account, so only you see them. Stores that "
                 "don't pay get no daily scans.", table + '<p class="hint"><a href="/new">+ Add a store</a></p>', wide=True)


def _optional(name):
    """A module another session is still building may not be on this server yet."""
    try:
        return __import__(name)
    except ImportError:
        return None


def _brain():
    brain = _optional("brain")
    info = dict(on=bool(brain and brain.enabled()), page="/admin/brain" if brain and hasattr(brain, "admin_body") else "",
                run=None, counts={})
    try:
        info["run"] = db.one("SELECT * FROM brain_runs ORDER BY id DESC LIMIT 1")
        info["counts"] = {r["status"]: r["n"] for r in db.all_(
            "SELECT status, COUNT(*) n FROM brain_findings GROUP BY status")}
    except Exception:                          # noqa: BLE001 - tables not made on this database yet
        pass
    return info


def _brain_card(n, b):
    run, c = b["run"], b["counts"]
    stats = ('<div class="mini"><div><span class="lbl">Status</span>%s</div>'
             '<div><span class="lbl">Last run</span><b class="m">%s</b></div>'
             '<div><span class="lbl">Playbook</span><b class="m">%d</b></div>'
             '<div><span class="lbl">Waiting for 2nd source</span><b class="m">%d</b></div>'
             '<div><span class="lbl">Opinions to test</span><b class="m">%d</b></div></div>' % (
                 _pill(b["on"], "On nightly", "Off", warn=True),
                 (_when(run["started_at"]) + " · $%.2f" % (run["cost_usd"] or 0)) if run else "never",
                 c.get("playbook", 0), c.get("candidate", 0), c.get("test", 0)))
    parts = [_link("Brain plan", BRAIN_PLAN, "The diagram: what it collects and how findings get graded.", ext=True),
             _link("Brain in the app", b["page"], "Findings, sources, nightly runs.") if b["page"] else
             _slot("Brain in the app", "Being built in another session. Its page appears here when it ships.")]
    return _card(n, "Agent brain", "Learns what works in AI search from outside research, every night.",
                 stats + '<div class="tiles">%s</div>' % "".join(parts))


def _selfvis_card(n, runs, note=""):
    """Produkto's own AI visibility (self_visibility.py): are we named, or our competitors?"""
    import self_visibility as sv
    btn = ('<form method="post" action="/admin/self-visibility" class="inline">'
           '<button type="submit" class="btn">Run now · about $%.2f</button></form>' % sv.estimate())
    note = ('<p class="notice">%s</p>' % E(note)) if note else ""
    if not runs:
        return _card(n, "Produkto in AI answers", "Not measured on this database yet.", note + btn, wide=True)
    last, first = runs[0], runs[-1]
    day = lambda d: time.strftime("%d %b", time.strptime(d, "%Y-%m-%d"))  # noqa: E731
    trend = "".join('<div class="wk"><span class="m">%s</span><b class="m">%d<i>/%d</i></b></div>'
                    % (day(r["day"]), r["named"], r["answers"]) for r in reversed(runs[:8]))
    top = max([v for _, v in last["rivals"][:1]] + [last["named"], 1])
    bars = ['<li class="you"><span>Produkto</span><span class="bar"><i style="width:%d%%"></i></span><b class="m">%d</b></li>'
            % (100 * last["named"] / top, last["named"])]
    bars += ['<li><span>%s</span><span class="bar"><i style="width:%d%%"></i></span><b class="m">%d</b></li>'
             % (E(k), 100 * v / top, v) for k, v in last["rivals"][:10]]
    engines = " · ".join("%s %d/%d" % (config.ENGINES[e]["label"], v[1], v[0])
                         for e, v in last["by_engine"].items() if e in config.ENGINES)
    sites = "".join('<li><span class="m">%s</span><b class="m">%d</b></li>' % (E(d), c) for d, c in last["sites"][:10])

    def cell(e, q):
        if (e, q) not in last["questions"]:
            return '<span class="m dim">no answer</span>'
        return _pill(True, "Named") if last["questions"][(e, q)][0] else '<span class="m dim">—</span>'
    qrows = "".join('<tr><td>%s</td>%s</tr>' % (E(q), "".join('<td>%s</td>' % cell(e, q) for e in config.ENGINE_ORDER))
                    for q in sv.QUESTIONS)
    since = (" First reading %s: %d/%d." % (day(first["day"]), first["named"], first["answers"]) if len(runs) > 1 else
             " Baseline, taken before the site's AEO work went live.")
    body = ('<div class="sv-top"><div><span class="lbl">Named in AI answers · %s</span>'
            '<b class="sv-big m%s">%d<i> / %d</i></b><span class="hint0">Cited %d times. %s.%s</span></div>'
            '<div class="wks">%s</div><div class="sv-act">%s<span class="hint0">Runs by itself every Monday.</span></div></div>'
            '<div class="sv-grid"><div><span class="lbl">Who AI names instead · answers mentioning each</span>'
            '<ul class="bars">%s</ul></div><div><span class="lbl">Sites AI cites · where to get mentioned</span>'
            '<ul class="sites">%s</ul></div></div>'
            '<details><summary>Every question, every engine</summary><div class="scroll q"><table><thead><tr><th>Question</th>%s'
            '</tr></thead><tbody>%s</tbody></table></div></details>'
            % (day(last["day"]), " up" if last["named"] else " down", last["named"], last["answers"], last["cited"],
               engines, since, trend, btn, "".join(bars), sites,
               "".join("<th>%s</th>" % E(config.ENGINES[e]["label"]) for e in config.ENGINE_ORDER), qrows))
    return _card(n, "Produkto in AI answers", "Ten questions a Shopify brand asks AI when looking for a tool like "
                 "ours, on ChatGPT, Google AI Overview and Perplexity. Does AI name Produkto, or our competitors?",
                 note + body, wide=True)


def _tools_card(n):
    import content_agent
    third_party = _optional("third_party")
    links = [
        _link("Opportunities", "/opportunities", "Ranked fixes per store." +
              ("" if config.SHOW_OPPORTUNITIES else " Switched off here.")),
        _link(content_agent.NAME, "/content", "Product page fixes and AEO articles." +
              (" Admins only." if config.CONTENT_AGENT_ADMIN_ONLY else "")),
        _link("Third-party context", "/admin/third-party", "Google Shopping, web results, Trustpilot. " +
              ("On." if third_party.enabled() else "Off.")) if third_party else
        _slot("Third-party context", "Built, not on this server yet."),
        _link("MCP keys", "/settings", "For Claude Code and Cursor. " + APP_URL.replace("https://", "") + "/mcp"),
        _link("Support page", "/support", "What customers see when they ask for help."),
        _link("How Produkto measures", "/docs", "The method page."),
    ]
    return _card(n, "Internal tools", "Parts of the app you use to run things.",
                 '<div class="tiles">%s</div>' % "".join(links), wide=True)


def _site_checks(st):
    r, blocked = st["res"], st["blocked"]
    return [
        ("Home page", r["home"] == 200, "Missing"), ("Pricing page", r["pricing"] == 200, "Missing"),
        ("Guides page", r["guides"] == 200, "Missing"), ("robots.txt", r["robots"] == 200, "Missing"),
        ("sitemap.xml", r["sitemap"] == 200, "Missing"), ("llms.txt", r["llms"] == 200, "Missing"),
        ("Structured data", st["schema"], "Missing"), ("Live app", r["app"] == 200, "Down"),
        ("AI crawlers allowed" + (": %s shut out" % ", ".join(blocked) if blocked else ""),
         blocked == [], "Unknown" if blocked is None else "Blocked"),
    ]


def _site_card(n, st):
    rows = "".join('<li>%s<span>%s</span></li>' % (_pill(ok, "OK", bad), E(k)) for k, ok, bad in _site_checks(st))
    pages = st["pages"]
    page_list = "".join('<li><a href="%s" target="_blank" rel="noopener">%s</a></li>' % (
        E(u), E(urllib.parse.urlparse(u).path or "/")) for u in pages)
    meta = ('<dl class="meta"><dt class="lbl">Title</dt><dd>%s</dd><dt class="lbl">Description</dt><dd>%s</dd></dl>'
            % (E(st["title"]) or "—", E(st["description"]) or "<i>none</i>"))
    links = "".join([
        _link("getprodukto.com", SITE_URL, "The marketing site.", ext=True),
        _link("Pricing", SITE_URL + "/pricing", "Plans and Stripe checkout.", ext=True),
        _link("Guides", SITE_URL + "/guides", "The AEO guides.", ext=True),
        _link("Search Console", "https://search.google.com/search-console?resource_id=sc-domain%3Agetprodukto.com",
              "Google: which pages are indexed and which searches show them.", ext=True),
        _link("Bing Webmaster", "https://www.bing.com/webmasters/home?siteUrl=https://getprodukto.com/",
              "Bing, ChatGPT search and Copilot. AI Performance tab.", ext=True),
    ])
    todo = ('<div class="todo"><span class="lbl"><b>Set up</b> · 22 Oct 2026</span><ol>'
            '<li><b>Google Search Console</b> and <b>Bing Webmaster Tools</b> (kelian@getprodukto.com). Sitemap '
            'submitted to both; indexing requested for the guides, guides index and press page. Bing feeds ChatGPT '
            'search and Copilot; its "AI Performance" tab shows Copilot citations.</li></ol>'
            '<p class="hint">Whether AI names Produkto is measured every week: section 01.</p></div>')
    return _card(n, "Website", "getprodukto.com. A free live check of its search and AI basics, every 10 minutes "
                 "(last <span class=\"m\">%s</span>)." % time.strftime("%H:%M", time.localtime(st["checked"])),
                 '<div class="tiles">%s</div><ul class="checks">%s</ul>%s'
                 '<details><summary>%d pages in the sitemap</summary><ul>%s</ul></details>%s'
                 % (links, rows, meta, len(pages), page_list, todo), wide=True)


def _usage():
    return _cached("apify", apify_usage) if live() else None


def _external_card(n, usage):
    if usage:
        used, limit = usage
        pct = min(100, int(100 * used / limit)) if limit else 0
        apify = ('<div class="meter-row"><span class="lbl">Apify this month</span><b class="m">$%.2f <i>/ $%.0f</i></b></div>'
                 '<div class="meter%s"><span style="width:%d%%"></span></div>'
                 '<p class="hint">Daily scans stop at the limit. The brain and third-party pulls refuse to run '
                 'within $10 of it.</p>' % (used, limit, " hot" if pct >= 80 else "", pct))
    else:
        apify = '<p class="hint">Couldn\'t read Apify usage just now.</p>'
    groups = "".join('<h3 class="lbl grp">%s</h3><div class="tiles">%s</div>' % (
        E(g), "".join(_link(l, h, s, ext=True) for l, h, s in items)) for g, items in EXTERNAL)
    return _card(n, "Outside accounts", "Links only. Sign-ins stay in your browser. No key is ever shown here.",
                 apify + groups, wide=True)


def _kpis(stores, st, usage, brain, runs=()):
    customers = sum(1 for s in stores if s["owners"])
    checks = _site_checks(st)
    ok = sum(1 for _, good, _ in checks if good)
    cells = [
        ("Stores", "%d" % len(stores), "%d paying · %d demo" % (customers, len(stores) - customers)),
        ("Site checks", "%d/%d" % (ok, len(checks)), "all passing" if ok == len(checks) else "needs a look",
         ok == len(checks)),
        ("Apify", ("$%.2f" % usage[0]) if usage else "—",
         ("of $%.0f this month" % usage[1]) if usage else "not readable", not usage or usage[0] < .8 * usage[1]),
        ("Brain", "%d" % brain["counts"].get("playbook", 0), "playbook findings · " + ("on" if brain["on"] else "off")),
    ]
    if runs:
        cells.insert(0, ("Produkto in AI", "%d/%d" % (runs[0]["named"], runs[0]["answers"]),
                         "answers naming us · " + time.strftime("%d %b", time.strptime(runs[0]["day"], "%Y-%m-%d")),
                         runs[0]["named"] > 0))
    out = []
    for c in cells:
        good = c[3] if len(c) > 3 else None
        out.append('<div class="kpi"><span class="lbl">%s</span><b class="m%s">%s</b><span>%s</span></div>' % (
            E(c[0]), "" if good is None else (" up" if good else " down"), E(c[1]), E(c[2])))
    return '<div class="kpis" style="grid-template-columns:repeat(%d,1fr)">%s</div>' % (len(out), "".join(out))


def _self_runs():
    try:
        import self_visibility
        return self_visibility.report()
    except Exception:                          # noqa: BLE001 - never let this break the admin page
        return []


def page(_q=None):
    q = _q or {}
    stores, st, usage, brain, runs = _stores(), site_status(), _usage(), _brain(), _self_runs()
    body = ('<div class="hero"><span class="lbl"><b>●</b> Internal · only you</span>'
            '<h1>Everything in one place.<span class="cur"></span></h1>'
            '<p>The app, every store, the agent brain, the website and the accounts behind them. '
            'Not part of the product.</p></div>%s<div class="secs">%s%s%s%s%s%s%s</div>'
            % (_kpis(stores, st, usage, brain, runs), _selfvis_card(1, runs, q.get("sv", "")), _app_card(2),
               _brain_card(3, brain), _stores_card(4, stores), _tools_card(5), _site_card(6, st), _external_card(7, usage)))
    return 200, body


# Same key as the app's own switch, so the choice carries over. Dark is the default, like the app.
THEME_HEAD = ("<script>try{if(localStorage.getItem('produkto-theme')!=='light')"
              "document.documentElement.classList.add('dark')}catch(e){document.documentElement.classList.add('dark')}</script>")
THEME_JS = ("var d=document.documentElement.classList.toggle('dark');"
            "try{localStorage.setItem('produkto-theme',d?'dark':'light')}catch(e){}")

CSS = """
:root{--bg:#f2f1ee;--panel:#fff;--panel-2:#f7f6f3;--line:#e2dfd8;--line-2:#d3cfc6;--ink:#0b1b35;--text:#24324a;
 --mute:#5d6b80;--haze:#3f5f95;--green:#1f9d5b;--green-bg:#e3f4ea;--red:#c8363b;--red-bg:#fbe7e7;--amber:#8a5a00;
 --amber-bg:#f8eedb;--dot:#d9d5cc;--btn:#0b1b35;--btn-t:#fff}
html.dark{--bg:#07101f;--panel:#0a1529;--panel-2:#0d1a31;--line:#1c2b45;--line-2:#263958;--ink:#fff;--text:#c7d2e4;
 --mute:#8a96a8;--haze:#9fb3d6;--green:#2fbf71;--green-bg:#0f2a1f;--red:#e5484d;--red-bg:#2a1418;--amber:#e8b45a;
 --amber-bg:#241d10;--dot:#14223b;--btn:#fff;--btn-t:#0b1b35}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:400 14px/1.5 Geist,system-ui,sans-serif;-webkit-font-smoothing:antialiased;
 background-image:radial-gradient(var(--dot) 1px,transparent 1.4px);background-size:14px 14px;background-attachment:fixed}
a{color:inherit}
.m,.lbl,h1,.kpi b,table th{font-family:"IBM Plex Mono",ui-monospace,monospace}
.lbl{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--mute);font-weight:500}
.lbl b{color:var(--green);font-weight:500}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px 80px}
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 86%,transparent);backdrop-filter:blur(10px);
 border-bottom:1px solid var(--line)}
.top-in{max-width:1120px;margin:0 auto;padding:12px 24px;display:flex;align-items:center;gap:14px}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.brand img{width:28px;height:28px;border-radius:7px;display:block}
.brand .lbl{color:var(--ink);letter-spacing:.22em}
.top-r{margin-left:auto;display:flex;align-items:center;gap:8px}
.live{display:flex;align-items:center;gap:8px;font:500 12px "IBM Plex Mono",monospace;color:var(--mute);margin-right:8px}
.btn{font:500 12px "IBM Plex Mono",monospace;letter-spacing:.04em;text-decoration:none;padding:8px 12px;border-radius:8px;
 border:1px solid var(--line-2);background:transparent;color:var(--ink);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.btn:hover{border-color:var(--ink)}
.btn.solid{background:var(--btn);color:var(--btn-t);border-color:var(--btn)}
.btn svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.6}
.ico-sun{display:none}html.dark .ico-sun{display:block}html.dark .ico-moon{display:none}
.hero{padding:56px 0 28px}
.hero h1{color:var(--ink);font-weight:700;font-size:clamp(30px,4.6vw,52px);letter-spacing:-.02em;line-height:1.05;margin:18px 0 14px}
.hero p{font-size:16px;color:var(--mute);max-width:620px;margin:0}
.cur{display:inline-block;width:.5em;height:.82em;background:var(--ink);margin-left:.12em;vertical-align:-.06em;animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
@media(prefers-reduced-motion:reduce){.cur{animation:none}}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:14px;background:var(--panel);overflow:hidden;margin-bottom:40px}
.kpi{padding:18px 20px;border-left:1px solid var(--line);display:flex;flex-direction:column;gap:6px;min-width:0}
.kpi:first-child{border-left:0}
.kpi b{font-size:28px;font-weight:500;color:var(--ink);letter-spacing:-.02em;line-height:1.1}
.kpi b.up{color:var(--green)}.kpi b.down{color:var(--red)}
.kpi>span:last-child{font-size:12px;color:var(--mute)}
.secs{display:grid;grid-template-columns:1fr 1fr;gap:40px 28px}
.sec{min-width:0}.sec.wide{grid-column:1/-1}
.sec-h{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.sec-h p{margin:0;font-size:13px;color:var(--mute);max-width:70ch}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.tile{position:relative;display:flex;flex-direction:column;gap:4px;padding:14px 38px 14px 14px;border:1px solid var(--line);border-radius:10px;
 background:var(--panel-2);text-decoration:none;transition:border-color .15s,transform .15s}
a.tile:hover{border-color:var(--haze);transform:translateY(-1px)}
.tile-t{font-weight:600;font-size:13.5px;color:var(--ink)}
.tile-d{font-size:12px;color:var(--mute);line-height:1.45}
.tile svg,.tile .go{position:absolute;top:14px;right:12px;width:15px;height:15px;fill:none;stroke:var(--mute);stroke-width:1.6;
 color:var(--mute);font-size:14px;line-height:15px}
a.tile:hover svg{stroke:var(--ink)}a.tile:hover .go{color:var(--ink)}
.slot{border-style:dashed;background:transparent}
.st{display:inline-flex;align-items:center;gap:6px;font:500 11px "IBM Plex Mono",monospace;letter-spacing:.06em;text-transform:uppercase;
 padding:3px 8px;border-radius:6px;white-space:nowrap}
.st i{width:6px;height:6px;border-radius:50%;background:currentColor}
.st.ok{color:var(--green);background:var(--green-bg)}.st.bad{color:var(--red);background:var(--red-bg)}
.st.warn{color:var(--amber);background:var(--amber-bg)}
.tag{font:500 11px "IBM Plex Mono",monospace;letter-spacing:.04em;color:var(--haze);border:1px solid var(--line-2);padding:3px 8px;border-radius:6px;white-space:nowrap}
.mini{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:14px;padding-bottom:16px;margin-bottom:16px;border-bottom:1px solid var(--line)}
.mini>div{display:flex;flex-direction:column;gap:6px;align-items:flex-start}
.mini b{font-size:18px;font-weight:500;color:var(--ink)}
.hint{font-size:12px;color:var(--mute);margin:14px 0 0}.hint a{color:var(--ink)}
.scroll{overflow-x:auto;margin:-18px -18px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10.5px;font-weight:500;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);padding:14px 18px;border-bottom:1px solid var(--line)}
td{padding:14px 18px;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:hover{background:var(--panel-2)}
.m{font-size:12px}
td.m{color:var(--mute);white-space:nowrap}
.store{display:flex;align-items:center;gap:12px}
.store img{width:30px;height:30px;border-radius:8px;border:1px solid var(--line);background:#fff;object-fit:contain}
.store b{display:block;color:var(--ink);font-weight:600}.store .m{color:var(--mute)}
.acts{display:flex;flex-wrap:wrap;gap:6px}
.acts a{font:500 11.5px "IBM Plex Mono",monospace;text-decoration:none;color:var(--ink);padding:4px 9px;border:1px solid var(--line-2);border-radius:6px;white-space:nowrap}
.acts a:hover{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.checks{list-style:none;padding:0;margin:18px 0 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px 18px}
.checks li{display:flex;align-items:center;gap:10px;font-size:13px}
.checks .st{min-width:62px;justify-content:center}
.meta{display:grid;grid-template-columns:110px 1fr;gap:8px 16px;margin:20px 0 0;padding-top:18px;border-top:1px solid var(--line)}
.meta dd{margin:0;font-size:13px;color:var(--text)}
details{margin-top:16px;font-size:13px}
summary{cursor:pointer;font:500 12px "IBM Plex Mono",monospace;color:var(--ink)}
details ul{columns:3;margin:10px 0 0;padding-left:18px;color:var(--mute)}details li{break-inside:avoid;margin:2px 0}
.todo{margin-top:18px;padding:16px 18px;border:1px dashed var(--line-2);border-radius:10px;font-size:13px;line-height:1.6}
.todo ol{margin:10px 0 0;padding-left:18px}.todo b{color:var(--ink)}.todo .lbl b{color:var(--green)}
.meter-row{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}
.meter-row b{font-size:20px;color:var(--ink);font-weight:500}.meter-row i{font-style:normal;color:var(--mute);font-size:13px}
.meter{height:6px;border-radius:6px;background:var(--line);overflow:hidden}
.meter span{display:block;height:100%;background:var(--green);border-radius:6px}.meter.hot span{background:var(--red)}
.grp{margin:26px 0 10px}
.sv-top{display:grid;grid-template-columns:auto 1fr auto;gap:28px;align-items:end;padding-bottom:18px;border-bottom:1px solid var(--line)}
.sv-top>div:first-child{display:flex;flex-direction:column;gap:6px}
.sv-big{font-size:44px!important;font-weight:500;color:var(--ink);line-height:1}.sv-big.down{color:var(--red)}.sv-big.up{color:var(--green)}
.sv-big i{font-style:normal;font-size:20px;color:var(--mute)}
.hint0{font-size:12px;color:var(--mute)}
.wks{display:flex;gap:18px;justify-content:center}.wk{display:flex;flex-direction:column;gap:2px;align-items:center}
.wk span{color:var(--mute);font-size:11px}.wk b{font-size:16px;color:var(--ink)}.wk i{font-style:normal;color:var(--mute);font-size:12px}
.sv-act{display:flex;flex-direction:column;gap:8px;align-items:flex-end}
.sv-grid{display:grid;grid-template-columns:1.3fr 1fr;gap:28px;margin-top:18px}
.bars,.sites{list-style:none;padding:0;margin:12px 0 0;display:flex;flex-direction:column;gap:7px}
.bars li{display:grid;grid-template-columns:130px 1fr 28px;gap:12px;align-items:center;font-size:13px}
.bars .bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden}.bars .bar i{display:block;height:100%;background:var(--haze);border-radius:4px}
.bars li.you{color:var(--ink);font-weight:600}.bars li.you .bar i{background:var(--green)}
.bars b,.sites b{text-align:right;font-weight:500;color:var(--ink)}
.sites li{display:flex;justify-content:space-between;gap:12px;padding:3px 0;border-bottom:1px dashed var(--line)}
.sites .m{color:var(--text)}
.dim{color:var(--mute)}
.scroll.q{margin:12px 0 0}.scroll.q td{padding:9px 12px}.scroll.q th{padding:10px 12px}
@media(max-width:900px){.sv-top{grid-template-columns:1fr}.sv-act{align-items:flex-start}.wks{justify-content:flex-start}.sv-grid{grid-template-columns:1fr}}
.tabs{display:flex;gap:4px;margin-left:18px}
.tabs a{font:500 12px "IBM Plex Mono",monospace;text-decoration:none;color:var(--mute);padding:7px 10px;border-radius:7px}
.tabs a:hover{color:var(--ink)}.tabs a[aria-current]{color:var(--ink);background:var(--panel)}
.form{display:grid;grid-template-columns:1.4fr 1fr .8fr auto;gap:14px;align-items:end}
.form label{display:flex;flex-direction:column;gap:7px}
.form input,.form select{font:400 13px Geist,system-ui,sans-serif;color:var(--ink);background:var(--panel-2);border:1px solid var(--line-2);
 border-radius:8px;padding:10px 12px;min-width:0;width:100%}
.form input:focus,.form select:focus{outline:2px solid var(--haze);outline-offset:1px}
.form .btn,.row-btn{height:40px;justify-content:center}
.row-btn{height:30px;font-size:11px;padding:0 10px}
.inline{display:inline;margin:0}
.cells{display:flex;gap:6px;flex-wrap:wrap}
.notice{border:1px solid var(--green);background:var(--green-bg);border-radius:12px;padding:16px 18px;margin-bottom:28px;color:var(--text)}
.notice b{color:var(--ink)}.notice code{display:block;margin-top:8px;font:500 12.5px "IBM Plex Mono",monospace;color:var(--ink);word-break:break-all;user-select:all}
td.link{font:400 11.5px "IBM Plex Mono",monospace;color:var(--mute);word-break:break-all;user-select:all}
@media(max-width:760px){.form{grid-template-columns:1fr}.tabs{margin-left:6px}}
@media(max-width:900px){.secs{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}.kpi:nth-child(3){border-left:0}
 .kpi:nth-child(n+3){border-top:1px solid var(--line)}details ul{columns:2}}
@media(max-width:560px){.wrap,.top-in{padding-left:16px;padding-right:16px}.live,.top-r .hide-s{display:none}
 .meta{grid-template-columns:1fr}details ul{columns:1}.hero{padding-top:36px}}
"""


def document(q=None):
    """The whole admin page: its own document, not the product's frame (Kelian, 22 Oct 2026)."""
    return frame("Produkto Admin", page(q)[1])


def frame(title, inner, here="/admin"):
    """Admin chrome (top bar, theme, brand-kit CSS) around any admin page: the hub and /admin/accounts."""
    st = site_status()
    up = st["res"].get("app") == 200 or not live()
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title>
<link rel="icon" type="image/png" href="/favicon.png?v=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;700&display=swap" rel="stylesheet">
%s<style>%s</style></head><body>
<header class="top"><div class="top-in">
<a class="brand" href="/admin"><img src="/favicon.png?v=1" alt="Produkto"><span class="lbl">Admin</span></a>
<nav class="tabs">%s</nav>
<div class="top-r"><span class="live">%s</span>
<button type="button" class="btn" onclick="%s" aria-label="Switch light or dark mode" title="Light or dark">
<svg class="ico-moon" viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>
<svg class="ico-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/></svg></button>
<a class="btn solid" href="/">Open the app</a><a class="btn hide-s" href="/logout">Sign out</a></div></div></header>
<main class="wrap">%s</main></body></html>""" % (
        E(title), THEME_HEAD, CSS, "".join('<a href="%s"%s>%s</a>' % (h, ' aria-current="page"' if h == here else "", l)
                                         for h, l in (("/admin", "Overview"), ("/admin/accounts", "Accounts"))),
        _pill(up, "app.getprodukto.com", "app down"), THEME_JS, inner)
