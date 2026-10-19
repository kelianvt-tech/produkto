"""Produkto MCP server: lets Claude read a store's AI-visibility data.

Speaks the Model Context Protocol over stdin/stdout (JSON-RPC, one message
per line), standard library only. Read-only: it never starts a scan and
never writes to the database. Every number comes from the same loaders the
dashboard uses (evidence.load, insight_panels, opportunities), so answers
here match what the merchant sees.

Which database it reads is PRODUKTO_DB, same as the app. Point it at
produkto.db.server-copy on the laptop; the laptop's produkto.db is stale.
"""
import inspect
import json
import re
import sys
import time

import accounts
import db
import evidence
import insight_panels
import opportunities
import period

PROTOCOL = "2025-06-18"


def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).replace("&ldquo;", "“").replace("&rdquo;", "”").replace("&amp;", "&").strip()


def _store(domain):
    """The store to read: the one asked for if this user may see it, else their only store."""
    mine = accounts.visible([r["domain"] for r in db.all_("SELECT domain FROM stores")])
    if not domain:
        if len(mine) == 1:
            return mine[0]
        raise ValueError("Say which store: " + ", ".join(mine) if mine else "No store on this account yet.")
    if domain not in mine:
        raise ValueError("Unknown store %s. Use list_stores to see yours." % domain)
    return domain


def _scans(domain, days):
    domain = _store(domain)
    ps = db.get_prompt_set(domain)
    if not ps:
        raise ValueError("No buyer questions saved for %s. Use list_stores to see stores." % domain)
    end = time.time()
    scans = period.done_scans(ps["id"], end - days * 86400, end)
    if not scans:
        raise ValueError("No finished scans for %s in the last %d days." % (domain, days))
    return ps, tuple(s["id"] for s in scans), scans


def _num(v, digits=1):
    return None if v is None else round(v, digits)


def list_stores():
    rows = db.all_("SELECT s.domain, s.brand_name, s.brand, s.products, "
                   "(SELECT MAX(sc.run_at) FROM scans sc JOIN prompt_sets ps ON ps.id=sc.prompt_set_id "
                   " WHERE ps.store_domain=s.domain AND sc.status IN ('done','partial')) AS last_scan "
                   "FROM stores s ORDER BY last_scan DESC")
    mine = set(accounts.visible([r["domain"] for r in rows]))
    return [dict(domain=r["domain"], brand=r["brand_name"] or r["brand"], products=r["products"],
                 last_scan=time.strftime("%Y-%m-%d", time.gmtime(r["last_scan"])) if r["last_scan"] else None)
            for r in rows if r["domain"] in mine]


def visibility(domain="", days=30, competitors=10):
    ps, ids, scans = _scans(domain, days)
    domain = ps["store_domain"]
    p = evidence.product_context(ps)
    rows = insight_panels.market_rows(ids, p)
    own, rivals = rows[0], rows[1:]
    return dict(
        store=domain, days=days, scans=len(scans),
        first_scan=time.strftime("%Y-%m-%d", time.gmtime(scans[0]["run_at"])),
        last_scan=time.strftime("%Y-%m-%d", time.gmtime(scans[-1]["run_at"])),
        answers=own.get("answers"),
        visibility_pct=_num(own["rate"]), average_position=_num(own["avg"]), share_of_voice_pct=_num(own["share"]),
        competing_brands=len(rivals),
        top_competitors=[dict(brand=r["name"], visibility_pct=_num(r["rate"]), average_position=_num(r["avg"]),
                              share_of_voice_pct=_num(r["share"])) for r in rivals[:competitors]])


def products(domain="", days=30, limit=25):
    ps, ids, _ = _scans(domain, days)
    out = []
    for pid in ps["product_ids"]:
        p = evidence.product_context(ps, pid)
        if p is None or not evidence.relevant_questions(p):
            continue
        own = next(r for r in insight_panels.products(ids, p) if r["own"])
        out.append(dict(product=p["title"], url=p.get("url") or "", answers=own["answers"],
                        visibility_pct=_num(own["rate"]), average_position=_num(own["avg"])))
    out.sort(key=lambda r: (-(r["visibility_pct"] or 0), r["product"]))
    return out[:limit]


def questions(domain="", days=30):
    ps, ids, _ = _scans(domain, days)
    p = evidence.product_context(ps)
    groups = insight_panels.products(ids, p)
    own = next(g for g in groups if g["own"])
    out = []
    for q in ps["prompts"]:
        if q not in own["q_n"]:
            continue
        rivals = sorted((g for g in groups if not g["own"] and g["questions"].get(q)),
                        key=lambda g: -g["questions"][q])[:3]
        out.append(dict(question=q, answers=own["q_n"][q], your_visibility_pct=_num(own["questions"].get(q, 0)),
                        your_average_position=_num(own["q_rank"].get(q)),
                        top_competitor_products=["%s (%s) %d%%" % (g["name"], g["brand"] or "?", round(g["questions"][q]))
                                                 for g in rivals]))
    return out


# --- everything else in the app ---------------------------------------------
# Writes go through the same handlers the app's own buttons post to, so every
# check (plan caps, allowances, gaps, Shopify connection) applies here too.

def _route(result):
    """An app handler's (code, payload) as data, or a ValueError with its message."""
    code, out = result[0], result[1]
    if isinstance(out, tuple):
        data = json.loads(out[1])
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(data["error"])
        return data
    if code in (200, 303):
        return {"ok": True}
    raise ValueError(_clean(re.sub(r"</h1>\s*", ". ", out or "")) or "That didn't work.")


def _confirm(confirm, what):
    if confirm is not True:
        raise ValueError("This %s. Ask the user to confirm, then call again with confirm=true." % what)


def _ts(t):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t)) if t else None


def store_details(domain=""):
    import content_plan
    import scheduler
    domain = _store(domain)
    b = db.brand(domain) or {}
    ps = db.get_prompt_set(domain)
    keep = ("brand_name", "aliases", "country", "currency", "description", "industry", "identity", "services", "markets")
    return dict(domain=domain, products=b.get("products"), **{k: b.get(k) for k in keep},
                buyer_questions=len(ps["prompts"]) if ps else 0, question_limit=accounts.question_limit(domain),
                last_scan=_ts(scheduler.last_scan_at(domain)), daily_scans=domain in scheduler.scheduled(),
                content_allowance=content_plan.summary(domain) or None)


def trend(domain="", days=30):
    """Catalog visibility for each scan in the period, oldest first."""
    ps, ids, scans = _scans(domain, days)
    p = evidence.product_context(ps)
    out = []
    for s in scans:
        own = next(r for r in insight_panels.products((s["id"],), p) if r["own"])
        out.append(dict(date=_ts(s["run_at"]), answers=own["answers"], visibility_pct=_num(own["rate"]),
                        average_position=_num(own["avg"]), share_of_voice_pct=_num(own["share"])))
    return out


def answers(domain="", days=7, question="", engine="", limit=20):
    """Recent AI answers with the products they named, newest first."""
    ps, ids, _ = _scans(domain, days)
    p = evidence.product_context(ps)
    rows, mentions = evidence.load(ids, p)
    by = {}
    for m in mentions:
        by.setdefault(m["answer_id"], []).append(m)
    out = []
    for a in sorted(rows, key=lambda a: -a["id"]):
        if question and question.lower() not in a["prompt"].lower():
            continue
        if engine and (a["engine"] or "chatgpt") != engine:
            continue
        ms = by.get(a["id"], [])
        out.append(dict(id=a["id"], date=_ts(a["created_at"]), engine=a["engine"], question=a["prompt"],
                        yours=[m["product_name"] for m in ms if evidence.own(m, p) or m["is_theirs"]],
                        products_named=["%d. %s (%s)" % (m["rank"] or 0, m["product_name"], m["brand"] or "?") for m in ms],
                        cited=[c.get("url") for c in json.loads(a["citations"] or "[]")][:10]))
        if len(out) >= limit:
            break
    return out


def answer(answer_id):
    """One AI answer in full."""
    a = db.one("SELECT a.*, ps.store_domain FROM answers a JOIN scans s ON s.id=a.scan_id "
               "JOIN prompt_sets ps ON ps.id=s.prompt_set_id WHERE a.id=?", (int(answer_id),))
    if not a:
        raise ValueError("Unknown answer.")
    _store(a["store_domain"])
    return dict(id=a["id"], date=_ts(a["created_at"]), engine=a["engine"], question=a["prompt"], text=a["raw_text"],
                citations=json.loads(a["citations"] or "[]"))


def citations(domain="", days=30, limit=25):
    """Sites AI cites in answers to the store's buyer questions, most cited first."""
    from collections import Counter
    ps, ids, _ = _scans(domain, days)
    rows, _m = evidence.load(ids, evidence.product_context(ps))
    sites, pages = Counter(), Counter()
    for a in rows:
        seen = set()
        for c in json.loads(a["citations"] or "[]"):
            url = (c.get("url") or "").split("?")[0]
            site = re.sub(r"^www\.", "", url.split("/")[2]) if url.count("/") >= 2 else ""
            if site and site not in seen:
                seen.add(site)
                sites[site] += 1
            if url:
                pages[url] += 1
    own = domain or ps["store_domain"]
    return dict(answers=len(rows), your_site_cited_in=sites.get(own.replace("www.", ""), 0),
                top_sites=[dict(site=k, answers=v) for k, v in sites.most_common(limit)],
                top_pages=[dict(url=k, citations=v) for k, v in pages.most_common(limit)])


def opportunity_list(domain="", limit=20, include_closed=False):
    domain = _store(domain)
    statuses = {(r["kind"], r["key"]): r["status"] for r in db.all_(
        "SELECT kind,key,status FROM opportunity_status WHERE store_domain=?", (domain,))}
    out = []
    for r in opportunities.find(domain):
        status = statuses.get((r["type"], r["key"]), "open")
        if status != "open" and not include_closed:
            continue
        out.append(dict(kind=r["type"], key=r["key"], status=status, impact=r.get("impact"),
                        title=_clean(r["title"]), detail=_clean(r.get("text"))))
    return out[:limit]


def set_opportunity(kind, key, status, domain=""):
    domain = _store(domain)
    return _route(opportunities.act({}, dict(d=domain, kind=kind, key=key,
                                             status={"open": ""}.get(status, status))))


def list_questions(domain=""):
    domain = _store(domain)
    ps = db.get_prompt_set(domain)
    if not ps:
        return []
    names = {p["id"]: p["title"] for p in ps["catalog_snapshot"]}
    return [dict(question=q, topic=ps["clusters"][i] if i < len(ps["clusters"]) else "",
                 products=[names.get(x, x) for x in (ps["relevance"][i] if i < len(ps["relevance"]) else [])])
            for i, q in enumerate(ps["prompts"])]


def catalog(domain="", search=""):
    domain = _store(domain)
    scope = set(db.scope(domain)["product_ids"])
    rows = db.all_("SELECT id,title,price,url,vendor FROM products WHERE store_domain=? ORDER BY title", (domain,))
    return [dict(id=r["id"], title=r["title"], price=r["price"], url=r["url"], tracked=r["id"] in scope)
            for r in rows if search.lower() in r["title"].lower()]


def question_suggestion_list(domain=""):
    """Open Buyer questions > Suggestions: swaps for weak questions and new ones worth tracking."""
    import question_suggestions
    domain = _store(domain)
    return [dict(id=r["id"], kind=r["kind"], replaces=r["old_q"], question=r["new_q"], reason=r["reason"],
                 evidence=r["evidence"], source=r["source"]) for r in question_suggestions.open_rows(domain)]


def decide_question_suggestion(id, action, text="", domain=""):
    """Swap, add or dismiss one suggestion. Swap and add change the tracked questions."""
    import question_suggestions
    domain = _store(domain)
    err = question_suggestions.decide(domain, int(id), action, text)
    if err:
        raise ValueError(err)
    return list_questions(domain)


def agent_results(lane="fixes", domain=""):
    """The latest monthly self-review of one agent: live pages, before/after, verdicts, lessons, re-fixes."""
    import agent_review
    domain = _store(domain)
    agent_review.init()
    row = db.one("SELECT * FROM agent_reviews WHERE store_domain=? AND lane=? ORDER BY month DESC LIMIT 1",
                 (domain, lane))
    if not row:
        return {"month": None, "note": "No review yet. The first runs on the 1st of the month."}
    return dict(month=row["month"], pages=json.loads(row["rows"] or "[]"), lessons=json.loads(row["lessons"] or "[]"),
                refix_drafts=json.loads(row["refixes"] or "[]"))


def _app():
    import app
    return app


def edit_questions(add=None, remove=None, domain=""):
    """Add or remove buyer questions. Kept questions keep their history; new ones start their own trend."""
    import catalog_setup
    domain = _store(domain)
    ps = db.get_prompt_set(domain)
    if not ps:
        raise ValueError("This store has no buyer questions yet. Finish onboarding in the app first.")
    items = [x for x in catalog_setup.items_out(ps) if x["q"] not in set(remove or [])]
    titles = {p["title"].lower(): p["id"] for p in ps["catalog_snapshot"]}
    for it in add or []:
        ids = [titles[t.lower()] if isinstance(t, str) and t.lower() in titles else t for t in it.get("products") or []]
        if not ids or not all(type(i) is int for i in ids):
            raise ValueError("Give each new question the products it fits (ids or exact titles from get_catalog).")
        items.append(dict(q=it["question"], tag="", cluster=it.get("topic") or "Buyer questions", products=ids))
    accounts.check_question_limit(domain, len(items))
    _route(_app().api_questions(dict(d=domain), dict(questions=json.dumps(items))))
    return list_questions(domain)


def suggest_questions(products, kind="organic", keywords="", domain=""):
    """AI-written question ideas for some products. Nothing is saved; add the ones you like with edit_questions."""
    import prompt_creation
    domain = _store(domain)
    ps = db.get_prompt_set(domain)
    scan = db.one("SELECT token FROM scans WHERE prompt_set_id IN (SELECT id FROM prompt_sets WHERE store_domain=?) "
                  "ORDER BY id DESC LIMIT 1", (domain,))
    if not ps or not scan:
        raise ValueError("Run a first scan before adding questions this way.")
    out = _route(prompt_creation.api(dict(token=scan["token"]), dict(
        action="keywords" if keywords else "ai", products=json.dumps(products), type=kind, keywords=keywords)))
    return out.get("items", [])


def run_scan(domain="", confirm=False):
    _confirm(confirm, "buys a fresh scan of every buyer question (paid)")
    domain = _store(domain)
    return dict(_route(_app().api_scan_start(dict(d=domain), {})), note="Takes 3-5 minutes. Check with get_scan_status.")


def scan_status(token):
    s = db.one("SELECT ps.store_domain FROM scans s JOIN prompt_sets ps ON ps.id=s.prompt_set_id WHERE s.token=?", (token,))
    if not s:
        raise ValueError("Unknown scan.")
    _store(s["store_domain"])
    return _route(_app().api_scan_status(dict(t=token)))


def list_content(domain="", status=""):
    import content_plan
    domain = _store(domain)
    rows = db.all_("SELECT * FROM content_drafts WHERE store_domain=? ORDER BY COALESCE(planned_at,created_at) DESC", (domain,))
    return dict(allowance=content_plan.summary(domain) or None,
                drafts=[dict(id=r["id"], type=r["draft_type"], title=r["title"], status=r["status"],
                             scheduled_for=_ts(r["planned_at"]), live_url=r["live_url"], updated=_ts(r["updated_at"]))
                        for r in rows if not status or r["status"] == status])


def content_draft(draft_id, domain=""):
    import content_agent
    domain = _store(domain)
    r = db.one("SELECT * FROM content_drafts WHERE id=? AND store_domain=?", (int(draft_id), domain))
    if not r:
        raise ValueError("Unknown draft.")
    body, open_facts = content_agent._latest(r["id"])
    return dict(id=r["id"], type=r["draft_type"], title=r["title"], status=r["status"], live_url=r["live_url"],
                gaps_left=content_agent.placeholders(body), open_questions=open_facts, body=body)


def _content(form):
    import content_agent
    return _route(content_agent.act({}, form))


def draft_content(kind, key, domain=""):
    """Have the Catalog Optimization Agent draft a fix for one opportunity (kind and key from get_opportunities)."""
    domain = _store(domain)
    before = {r["id"] for r in db.all_("SELECT id FROM content_drafts WHERE store_domain=?", (domain,))}
    _content(dict(d=domain, action="draft", kind=kind, key=key))
    new = db.one("SELECT id FROM content_drafts WHERE store_domain=? ORDER BY updated_at DESC, id DESC LIMIT 1", (domain,))
    return dict(ok=True, draft_id=new["id"] if new else None, new=bool(new and new["id"] not in before))


def answer_draft_gaps(draft_id, answers, domain=""):
    """Fill a draft's open questions: answers maps each open question to its answer ("" skips it)."""
    domain = _store(domain)
    form = dict(d=domain, id=str(draft_id), action="fill")
    for i, (q, a) in enumerate(answers.items()):
        form["q.%d" % i] = q
        if a:
            form["a.%d" % i] = a
        else:
            form["skip.%d" % i] = "1"
    _content(form)
    return content_draft(draft_id, domain)


def set_draft_status(draft_id, status, domain=""):
    """approved, rejected, or draft (back to review)."""
    domain = _store(domain)
    return _content(dict(d=domain, id=str(draft_id), status=status))


def schedule_draft(draft_id, day, domain=""):
    domain = _store(domain)
    return _content(dict(d=domain, id=str(draft_id), action="move", day=day))


def publish_draft(draft_id, live=True, domain="", confirm=False):
    _confirm(confirm, "changes the merchant's live Shopify store" if live else "takes a page down from the live Shopify store")
    domain = _store(domain)
    return _content(dict(d=domain, id=str(draft_id), action="golive" if live else "unlive"))


def topics_tool(domain="", choose=None):
    """The store's question topics; pass choose to set which ones questions are written for."""
    import topics
    domain = _store(domain)
    got = topics.saved(domain)
    if choose is not None:
        if not got:
            raise ValueError("No topics yet. Open Topics in the app first.")
        topics.save(domain, got[0], choose)
        got = topics.saved(domain)
    return dict(shown=got[0], chosen=got[1]) if got else dict(shown=[], chosen=[])


def support(message, topic="other", domain=""):
    import support as s
    domain = _store(domain)
    user = accounts.current() or {}
    return _route(s.api({}, dict(email=user.get("email", ""), topic=topic, message=message, store=domain, ua="mcp")))


DOMAIN = {"type": "string", "description": "Store domain, e.g. clubhouseskin.com (see list_stores). "
                                          "Optional when the account has one store."}
DAYS = {"type": "integer", "description": "How many days back to pool scans over. Default 30."}
INT = {"type": "integer"}
STR = {"type": "string"}
CONFIRM = {"type": "boolean", "description": "Must be true, and only after the user has said yes."}
R = {"readOnlyHint": True}
W = {"readOnlyHint": False, "destructiveHint": False}
D = {"readOnlyHint": False, "destructiveHint": True}


def _tool(name, fn, description, props=None, required=(), hints=R):
    return dict(name=name, fn=fn, description=description, annotations=hints,
                inputSchema={"type": "object", "properties": props or {}, **({"required": list(required)} if required else {})})


TOOLS = [
    _tool("list_stores", list_stores, "Stores you can see, with brand, catalog size and last scan date."),
    _tool("get_store", store_details, "Brand profile, plan limits, daily-scan status and content allowance.", {"domain": DOMAIN}),
    _tool("get_visibility", visibility, "Headline catalog visibility: % of AI answers naming the store's products, "
          "average position, share of voice, top competitor brands.", {"domain": DOMAIN, "days": DAYS, "competitors": INT}),
    _tool("get_visibility_trend", trend, "Visibility, position and share of voice for each scan, oldest first.",
          {"domain": DOMAIN, "days": DAYS}),
    _tool("get_products", products, "Visibility per product, best first.", {"domain": DOMAIN, "days": DAYS, "limit": INT}),
    _tool("get_questions", questions, "Results per buyer question, with the competitor products AI names instead.",
          {"domain": DOMAIN, "days": DAYS}),
    _tool("list_answers", answers, "Recent AI answers: question, engine, products named in order, sites cited. "
          "Filter by words in the question or by engine (chatgpt, aio, perplexity).",
          {"domain": DOMAIN, "days": DAYS, "question": STR, "engine": STR, "limit": INT}),
    _tool("get_answer", answer, "One AI answer's full text and citations.", {"answer_id": INT}, ["answer_id"]),
    _tool("get_citations", citations, "Sites and pages AI cites when answering the store's buyer questions.",
          {"domain": DOMAIN, "days": DAYS, "limit": INT}),
    _tool("get_opportunities", opportunity_list, "Ranked fixes (Opportunities): lost questions, competitors to catch, "
          "missing product details, sites to get cited on. kind+key identify each one.",
          {"domain": DOMAIN, "limit": INT, "include_closed": {"type": "boolean"}}),
    _tool("set_opportunity_status", set_opportunity, "Mark an opportunity done, declined, or open again.",
          {"domain": DOMAIN, "kind": STR, "key": STR, "status": {"type": "string", "enum": ["done", "declined", "open"]}},
          ["kind", "key", "status"], W),
    _tool("get_catalog", catalog, "Products in the store with ids, and whether each is tracked.", {"domain": DOMAIN, "search": STR}),
    _tool("get_agent_results", agent_results, "The monthly self-review of an agent (lane fixes = Product page fixes, "
          "articles = AEO articles): what went live, how often AI named the product before vs since, the verdict, "
          "lessons for next month and re-fix drafts queued. Shows what changed, not why.",
          {"domain": DOMAIN, "lane": {"type": "string", "enum": ["fixes", "articles"]}}),
    _tool("list_question_suggestions", question_suggestion_list, "Suggested changes to the tracked buyer questions: "
          "swaps for questions that make a poor test, and new questions worth tracking, each with its reason.",
          {"domain": DOMAIN}),
    _tool("decide_question_suggestion", decide_question_suggestion, "Act on one suggestion: swap or add (changes "
          "the tracked questions; a new question starts its own trend), or dismiss. text optionally edits it first.",
          {"domain": DOMAIN, "id": INT, "action": {"type": "string", "enum": ["swap", "add", "dismiss"]}, "text": STR},
          ["id", "action"], W),
    _tool("list_buyer_questions", list_questions, "The buyer questions being tracked, with topic and matching products.",
          {"domain": DOMAIN}),
    _tool("edit_buyer_questions", edit_questions, "Add and/or remove buyer questions. Kept questions keep their history. "
          "Plan question limits apply. Takes effect from the next scan.",
          {"domain": DOMAIN, "remove": {"type": "array", "items": STR, "description": "Exact question texts to remove."},
           "add": {"type": "array", "items": {"type": "object", "required": ["question", "products"], "properties": {
               "question": STR, "topic": STR,
               "products": {"type": "array", "items": {}, "description": "Product ids or exact titles."}}}}}, (), W),
    _tool("suggest_buyer_questions", suggest_questions, "AI-written question ideas for given product ids. Saves nothing.",
          {"domain": DOMAIN, "products": {"type": "array", "items": INT},
           "kind": {"type": "string", "enum": ["organic", "specific", "competitor"]}, "keywords": STR}, ["products"]),
    _tool("topics", topics_tool, "The store's question topics; pass choose (list of topic names) to change which are used.",
          {"domain": DOMAIN, "choose": {"type": "array", "items": STR}}, (), W),
    _tool("run_scan", run_scan, "Start a fresh scan now (paid; daily scans already run automatically).",
          {"domain": DOMAIN, "confirm": CONFIRM}, ["confirm"], {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}),
    _tool("get_scan_status", scan_status, "Progress of a scan started with run_scan.", {"token": STR}, ["token"]),
    _tool("list_content", list_content, "Catalog Optimization Agent drafts (product page fixes, FAQs, comparisons, guides) "
          "and this month's allowance.", {"domain": DOMAIN, "status": STR}),
    _tool("get_content_draft", content_draft, "One draft in full, with any open questions it needs answered.",
          {"domain": DOMAIN, "draft_id": INT}, ["draft_id"]),
    _tool("draft_content", draft_content, "Ask the agent to draft a fix for an opportunity (kind and key from get_opportunities).",
          {"domain": DOMAIN, "kind": STR, "key": STR}, ["kind", "key"], W),
    _tool("answer_draft_gaps", answer_draft_gaps, "Answer a draft's open questions. answers maps question text to answer; "
          "an empty answer skips it. Only facts the user gave you, never invented ones.",
          {"domain": DOMAIN, "draft_id": INT, "answers": {"type": "object"}}, ["draft_id", "answers"], W),
    _tool("set_draft_status", set_draft_status, "Approve (uses allowance), reject, or send a draft back to review.",
          {"domain": DOMAIN, "draft_id": INT, "status": {"type": "string", "enum": ["approved", "rejected", "draft"]}},
          ["draft_id", "status"], W),
    _tool("schedule_draft", schedule_draft, "Move a comparison or guide to a calendar day (YYYY-MM-DD, today or later).",
          {"domain": DOMAIN, "draft_id": INT, "day": STR}, ["draft_id", "day"], W),
    _tool("publish_draft", publish_draft, "Put a draft live on the Shopify store (live=true) or take it down (live=false).",
          {"domain": DOMAIN, "draft_id": INT, "live": {"type": "boolean"}, "confirm": CONFIRM}, ["draft_id", "confirm"], D),
    _tool("contact_support", support, "Send a message to Produkto support.", {"domain": DOMAIN, "message": STR, "topic": STR},
          ["message"], W),
]
BY_NAME = {t["name"]: t for t in TOOLS}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = dict(protocolVersion=msg.get("params", {}).get("protocolVersion", PROTOCOL),
                      capabilities={"tools": {}}, serverInfo={"name": "produkto", "version": "0.1.0"},
                      instructions="Read-only access to Produkto's AI-visibility scans. Start with list_stores.")
    elif method == "tools/list":
        result = {"tools": [{k: v for k, v in t.items() if k != "fn"} for t in TOOLS]}
    elif method == "tools/call":
        params = msg.get("params", {})
        tool = BY_NAME.get(params.get("name"))
        if tool is None:
            return dict(jsonrpc="2.0", id=mid, error=dict(code=-32602, message="Unknown tool"))
        try:
            # Ignore arguments a tool doesn't take rather than failing on them.
            known = inspect.signature(tool["fn"]).parameters
            data = tool["fn"](**{k: v for k, v in (params.get("arguments") or {}).items() if k in known})
            result = dict(content=[dict(type="text", text=json.dumps(data, ensure_ascii=False, indent=1))])
        except Exception as e:
            result = dict(content=[dict(type="text", text="Error: %s" % e)], isError=True)
    elif method == "ping":
        result = {}
    elif mid is None:
        return None          # notifications (e.g. notifications/initialized) need no reply
    else:
        return dict(jsonrpc="2.0", id=mid, error=dict(code=-32601, message="Method not found"))
    return dict(jsonrpc="2.0", id=mid, result=result)


def http(body, authorization):
    """POST /mcp on the hosted app (MCP "streamable HTTP", plain JSON replies).
    Returns (status, reply text). The Bearer key decides whose stores are visible."""
    key = (authorization or "")[7:].strip() if (authorization or "").lower().startswith("bearer ") else ""
    import mcp_oauth
    user = mcp_oauth.user_for_token(key) or accounts.user_for_mcp_key(key)
    if not user:
        return 401, json.dumps(dict(jsonrpc="2.0", id=None, error=dict(
            code=-32001, message="Sign in to Produkto to connect, or use a key from Settings.")))
    accounts.set_current(user)
    try:
        msg = json.loads(body or "")
    except ValueError:
        return 400, json.dumps(dict(jsonrpc="2.0", id=None, error=dict(code=-32700, message="Bad JSON")))
    replies = [r for r in (handle(m) for m in (msg if isinstance(msg, list) else [msg])) if r is not None]
    if not replies:
        return 202, ""
    return 200, json.dumps(replies if isinstance(msg, list) else replies[0])


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as e:
            reply = dict(jsonrpc="2.0", id=None, error=dict(code=-32700, message=str(e)))
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
