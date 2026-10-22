"""Run one scan: ask ChatGPT every question several times, read each answer
into a ranked product list, and decide which mentions are the merchant's.

A scan runs in a background thread so the browser can show progress. Every
answer is stored the moment it arrives, so a crash half-way loses nothing
that was already paid for.

Matching ("is this mention their product?") is the risky part. ChatGPT names
products loosely - "the Sven sofa from Article" has to resolve to the
"Sven 3-Seater Sofa - Charme Tan" in the catalogue. The rule used here:

  * a link to the product's own page             -> theirs, certain
  * their brand named AND most of the product's  -> theirs
    title words present in the product name
  * their brand named, different product         -> counted as a brand
                                                    mention, not theirs

Every mention keeps its match score, so borderline calls can be checked by
hand later instead of being silently counted.
"""

import json
import re
import secrets
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import config
import apify_answers
import db
import llm
import scoring
from text import core_title, norm, words

EXTRACT_INSTRUCTIONS = """You read an AI assistant's answer to a shopping
question and list every product or brand it recommends, in the order they
first appear in the answer (1 = first).

- One entry per distinct recommendation. If the answer recommends a brand
  without naming a specific product, give the brand and leave product_name
  empty.
- product_name: the product's name as written, without the brand.
- brand: the brand or maker. Empty if the answer doesn't say.
- url: the product or brand link the answer gives for it, else empty.
- price: the price the answer states for this product, copied as written
  with its currency symbol or code ("€16.99", "$34", "£12.50"). If it gives
  a range, copy the range. Empty if the answer states no price for it.
  Never estimate or fill in a price the answer does not give.
- Ignore retailers mentioned only as places to buy (Amazon, IKEA's website
  as a shop, etc.) unless they are recommended as the brand of a product.
- Ignore generic advice that names neither a brand nor a specific product
  ("use a gentle, fragrance-free cleanser", "a vitamin C serum", "a plain
  moisturiser"). Only list things a shopper could actually go and buy.
- If nothing is recommended, return an empty list."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "product_name": {"type": "string"},
                    "brand": {"type": "string"},
                    "url": {"type": "string"},
                    "price": {"type": "string"},
                },
                "required": ["rank", "product_name", "brand", "url", "price"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def brand_aliases(domain, products):
    """Names a buyer (or ChatGPT) would use for this store's brand.

    The merchant's own answer wins: anything typed into the brand card on the
    product page is added here, which is what makes a mention count as theirs.
    """
    aliases = {norm(domain.split(".")[0])}
    store = db.brand(domain)
    names = list({p["vendor"] for p in products})
    if store:
        names += [store["brand_name"], store["brand"]] + list(store["aliases"])
    for v in names:
        n = norm(v)
        if len(n) >= 3:
            aliases.add(n)
    return {a for a in aliases if len(a) >= 3}


def _host(url):
    try:
        h = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def match(mention, product, aliases):
    """Return (is_theirs, is_their_brand, score)."""
    url = mention.get("url") or ""
    host = _host(url)
    domain = product["store_domain"]
    handle = product["handle"] or ""
    on_their_site = bool(host) and (host == domain or host.endswith("." + domain))
    if on_their_site and handle and ("/products/" + handle) in url:
        return True, True, 1.0

    b = norm(mention.get("brand"))
    their_brand = on_their_site or any(
        a and b and (a == b or a in b or b in a) for a in aliases)

    named = set(words(mention.get("product_name")))
    score = 0.0
    # try the full title and the core name (without colour/variant suffix)
    for t in (product["title"], core_title(product["title"])):
        tw = set(words(t))
        # brand words inside the title don't prove it's the same product
        tw = {w for w in tw if norm(w) not in aliases} or tw
        if tw:
            score = max(score, len(tw & named) / len(tw))
    theirs = their_brand and bool(named) and score >= config.TITLE_MATCH_THRESHOLD
    return theirs, their_brand, round(score, 2)


def prepare_catalog(products, aliases):
    return [(p, [{w for w in words(t) if norm(w) not in aliases} or set(words(t))
                 for t in (p['title'],core_title(p['title']))]) for p in products]


def match_catalog(mention, products, aliases, prepared=None):
    prepared = prepared if prepared is not None else prepare_catalog(products,aliases)
    if not products:
        return None,False,0.0
    url=mention.get('url') or ''
    host=_host(url)
    domain=products[0]['store_domain']
    on_site=bool(host) and (host==domain or host.endswith('.'+domain))
    b=norm(mention.get('brand'))
    brand=on_site or any(a and b and (a==b or a in b or b in a) for a in aliases)
    named=set(words(mention.get('product_name')))
    candidates=[]
    best_score=0.0
    path=urllib.parse.unquote(urllib.parse.urlparse(url).path).rstrip('/')
    for p, wordsets in prepared:
        # Exact handle segment, not a prefix (cleanser must not match cleanser-set).
        exact=on_site and bool(p['handle']) and path.endswith('/products/'+p['handle'])
        value=max((len(w & named)/len(w) for w in wordsets if w),default=0.0)
        best_score=max(best_score,value)
        if exact or (brand and named and value>=config.TITLE_MATCH_THRESHOLD):
            candidates.append((bool(exact),1.0 if exact else value,p['id']))
    if candidates:
        candidates.sort(key=lambda x:(-x[0],-x[1],x[2]))
        winner=candidates[0]
        return winner[2],bool(brand),round(winner[1],2)
    return None,bool(brand),round(best_score,2)


_start_lock=threading.Lock()


def _engines():
    """Engines this scan buys. The API path can only be ChatGPT."""
    if config.ANSWER_SOURCE!='apify':
        return [config.DEFAULT_ENGINE]
    return [e for e in config.SCAN_ENGINES if e in config.ENGINES] or [config.DEFAULT_ENGINE]


def start(store_domain):
    with _start_lock, db._lock, db.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        ps=db.decode_prompts(c.execute('SELECT * FROM prompt_sets WHERE store_domain=? ORDER BY id DESC LIMIT 1',(store_domain,)).fetchone())
        if not ps or not ps['prompts']:
            raise ValueError('Generate the buyer questions first.')
        running=c.execute("SELECT token FROM scans WHERE prompt_set_id=? AND status='running'",(ps['id'],)).fetchone()
        if running:
            return running['token']
        c.execute('UPDATE prompt_sets SET frozen_at=? WHERE id=? AND frozen_at IS NULL',(time.time(),ps['id']))
        token=secrets.token_urlsafe(12)
        total=len(ps['prompts'])*config.RUNS_PER_QUESTION*len(_engines())
        scan_id=c.execute('INSERT INTO scans(token,prompt_set_id,run_at,status,done,total) VALUES(?,?,?,?,?,?)',
                          (token,ps['id'],time.time(),'running',0,total)).lastrowid
    threading.Thread(target=_run,args=(scan_id,store_domain,ps['prompts']),daemon=True).start()
    return token


def completion_status(processed,total):
    return 'done' if processed==total and total else 'partial' if processed>total/2 else 'failed'


def engine_status(scan_id,engines,want):
    """Scan status judged only on engines that answer every time.

    AI Overview is excluded from the verdict because Google legitimately shows
    no overview for many searches. Counting its silences as missing answers
    would mark almost every scan 'partial' and bury a real finding under a
    false alarm. Returns (status, {engine: {collected, expected}}).
    """
    per_engine={r['engine']:r['n'] for r in db.all_(
        "SELECT a.engine AS engine,COUNT(*) AS n FROM answers a JOIN answer_processing p ON p.answer_id=a.id "
        "WHERE a.scan_id=? AND p.status='done' GROUP BY a.engine",(scan_id,))}
    coverage={e:dict(collected=per_engine.get(e,0),expected=want) for e in engines}
    strict=[e for e in engines if not config.ENGINES.get(e,{}).get('may_be_empty')]
    if not strict:
        return ('done' if sum(per_engine.values()) else 'failed'),coverage
    return completion_status(sum(per_engine.get(e,0) for e in strict),want*len(strict)),coverage


def _missing(engine,q):
    """Why a question came back with nothing.

    On AI Overview this is usually not a failure at all: Google shows no
    overview for plenty of searches, and the actor only bills for the ones it
    captures. Saying "no answer came back" about that would read as a bug and
    hide a real finding - the buyer sees no AI answer for that question.
    """
    if engine=='ai-overview':
        return 'AI Overview: Google showed no overview for: %s'%q
    return '%s: no answer came back for: %s'%(config.engine_label(engine),q)


def _quote_key(s):
    """Apify echoes the query back; curly quotes and stray spaces must not
    stop us finding the answer we paid for."""
    return re.sub(r"\s+", " ", (s or "")).strip().translate(
        str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}))


def _store_answer(scan_id,q,n,text,cites,model,engine=config.DEFAULT_ENGINE):
    """Write the raw answer before extraction. Never update or delete it."""
    answer_id=db.write('INSERT INTO answers(scan_id,prompt,model,engine,run_n,raw_text,citations,created_at) VALUES(?,?,?,?,?,?,?,?)',
                       (scan_id,q,model,engine,n,text,json.dumps(cites),time.time()))
    db.write("INSERT INTO answer_processing(answer_id,status) VALUES(?,'pending')",(answer_id,))
    return answer_id


def _extract(answer_id,q,text,products,aliases,prepared,usage):
    items=llm.json_call(EXTRACT_INSTRUCTIONS,'Shopping question: %s\n\nAnswer:\n%s'%(q,text),
                        'recommendations',EXTRACT_SCHEMA,usage).get('items') or []
    items.sort(key=lambda i:i.get('rank') or 999)
    with db._lock,db.conn() as c:
        for pos,it in enumerate(items,1):
            pid,brand,value=match_catalog(it,products,aliases,prepared)
            c.execute('INSERT INTO mentions(answer_id,product_name,brand,url,rank,is_theirs,is_their_brand,match_score,matched_product_id,price) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (answer_id,it.get('product_name',''),it.get('brand',''),it.get('url',''),pos,int(pid is not None),int(brand),value,pid,(it.get('price') or '').strip()[:40]))
        c.execute("UPDATE answer_processing SET status='done',error=NULL WHERE answer_id=?",(answer_id,))


def _context(store_domain, scan_id=None):
    ps=(db.decode_prompts(db.one('SELECT ps.* FROM prompt_sets ps JOIN scans s ON s.prompt_set_id=ps.id WHERE s.id=?',(scan_id,)))
        if scan_id is not None else db.get_prompt_set(store_domain))
    products=ps['catalog_snapshot']
    aliases=brand_aliases(store_domain,products)
    return ps,products,aliases,prepare_catalog(products,aliases)


def _run(scan_id, store_domain, prompts):
    ps=db.decode_prompts(db.one('SELECT ps.* FROM prompt_sets ps JOIN scans s ON s.prompt_set_id=ps.id WHERE s.id=?',(scan_id,)))
    products=ps['catalog_snapshot']
    aliases=brand_aliases(store_domain,products)
    prepared=prepare_catalog(products,aliases)
    store=db.brand(store_domain)
    country=config.BUYER_COUNTRY or (store['country'] if store else '')
    usage=llm.Usage()
    errors=[]
    progress=threading.Lock()

    def bump(k=1):
        """Move the progress bar. `done` counts answers collected."""
        with progress:
            db.write('UPDATE scans SET done=done+?,model_versions=?,cost_cents=? WHERE id=?',
                     (k,json.dumps(usage.as_dict()),usage.cost_cents(),scan_id))

    def store_answer(q,n,text,cites,model,engine=config.DEFAULT_ENGINE):
        return _store_answer(scan_id,q,n,text,cites,model,engine)

    def extract(answer_id,q,text):
        _extract(answer_id,q,text,products,aliases,prepared,usage)

    def fail(answer_id,e):
        with progress:
            errors.append(str(e))
        if answer_id:
            db.write("UPDATE answer_processing SET status='failed',error=? WHERE answer_id=?",(str(e),answer_id))

    def api_job(q,n):
        """One answer bought from the OpenAI API, then read."""
        answer_id=None
        try:
            text,cites,model=llm.ask_buyer_question(q,usage,country)
            answer_id=store_answer(q,n,text,cites,model)
            extract(answer_id,q,text)
        except Exception as e:
            fail(answer_id,e)
        finally:
            bump()

    def scrape_run(job):
        """One Apify run buys every question once, on one engine."""
        engine,n=job
        def remember(run_id,dataset_id):
            # Written BEFORE any answer exists, so a crash from here on costs
            # time rather than money - the dataset outlives this process.
            db.write('INSERT OR REPLACE INTO scan_batches(scan_id,run_n,engine,apify_run_id,dataset_id,collected,started_at) VALUES(?,?,?,?,?,0,?)',
                     (scan_id,n,engine,run_id,dataset_id,time.time()))
        try:
            got=apify_answers.ask_batch(prompts,usage,on_start=remember,engine=engine)
        except Exception as e:
            with progress:
                errors.append('%s: %s'%(config.engine_label(engine),e))
            return []
        loose={_quote_key(k):v for k,v in got.items()}
        out=[]
        for q in prompts:
            hit=got.get(q) or loose.get(_quote_key(q))
            if not hit:
                with progress:
                    errors.append(_missing(engine,q))
                continue
            text,cites,model=hit
            out.append((store_answer(q,n,text,cites,model,engine),q,text))
        db.write('UPDATE scan_batches SET collected=1 WHERE scan_id=? AND run_n=? AND engine=?',(scan_id,n,engine))
        bump(len(out))
        return out

    def extract_job(args):
        answer_id,q,text=args
        try:
            extract(answer_id,q,text)
        except Exception as e:
            fail(answer_id,e)

    engines=_engines()
    batches=[(e,n) for e in engines for n in range(1,config.RUNS_PER_QUESTION+1)]
    jobs=[(q,n) for q in prompts for n in range(1,config.RUNS_PER_QUESTION+1)]
    coverage={}
    try:
        if config.ANSWER_SOURCE=='apify':
            # Buy first - one actor run per engine per run number, all fired
            # together - then read the stored answers. Extraction is cheap and
            # local, so a failure there costs nothing already paid for.
            collected=[]
            with ThreadPoolExecutor(max_workers=max(1,len(batches))) as pool:
                for batch in pool.map(scrape_run,batches):
                    collected.extend(batch)
            with ThreadPoolExecutor(max_workers=config.PARALLEL_CALLS) as pool:
                list(pool.map(extract_job,collected))
        else:
            with ThreadPoolExecutor(max_workers=config.PARALLEL_CALLS) as pool:
                list(pool.map(lambda args:api_job(*args),jobs))
        want=len(prompts)*config.RUNS_PER_QUESTION
        status,coverage=engine_status(scan_id,engines,want)
        error=None if status=='done' else 'Some answers could not be collected or analysed. Saved answers are preserved.'
        if sum(c['collected'] for c in coverage.values()):
            scoring.score(scan_id)
    except Exception:
        status,error='failed','The results could not be prepared. Saved answers are preserved.'
    db.write('UPDATE scans SET status=?,error=?,finished_at=?,model_versions=?,cost_cents=? WHERE id=?',
             (status,error,time.time(),json.dumps(dict(usage.as_dict(),engine_coverage=coverage)),
              usage.cost_cents(),scan_id))
    _notify(store_domain,status)


_resume_locks={}
_resume_guard=threading.Lock()


def _resume_lock(scan_id):
    with _resume_guard:
        return _resume_locks.setdefault(scan_id,threading.Lock())


def resume(scan_id, store_domain=None):
    """Finish a scan that was interrupted after its answers were bought.

    A scraped batch is paid for the moment the Apify run starts, but the
    answers only land minutes later. `scan_batches` records the dataset id up
    front, so anything already bought is fetched again here rather than
    re-bought. Extraction then runs over whatever is still pending.

    One resume at a time per scan. Two of them racing would both read an
    empty answer list and store the same batch twice, which is exactly how
    scan 6 ended up with duplicates on 2026-09-20.
    """
    with _resume_lock(scan_id):
        return _resume(scan_id,store_domain)


def _resume(scan_id, store_domain=None):
    row=db.one("""SELECT s.id, ps.store_domain FROM scans s
                  JOIN prompt_sets ps ON ps.id=s.prompt_set_id WHERE s.id=?""",(scan_id,))
    if not row:
        return 'failed'
    store_domain=store_domain or row['store_domain']
    ps,products,aliases,prepared=_context(store_domain,scan_id)
    prompts=ps['prompts']
    usage=llm.Usage()

    for b in db.all_('SELECT * FROM scan_batches WHERE scan_id=? AND collected=0 ORDER BY engine,run_n',(scan_id,)):
        if not b['dataset_id']:
            continue
        engine=b['engine'] or config.DEFAULT_ENGINE
        try:
            status=apify_answers.wait(b['apify_run_id']) if b['apify_run_id'] else 'SUCCEEDED'
            got=apify_answers.collect(b['dataset_id'],status,b['apify_run_id'] or '',engine)
        except Exception:                                       # noqa: BLE001
            continue        # leave the batch open; a later resume can retry
        usage.add_scraped(len(got),engine)
        loose={_quote_key(k):v for k,v in got.items()}
        # Scoped to this engine: the same question at the same run number has
        # one answer PER ENGINE, so a stored ChatGPT answer must not block
        # storing the Perplexity one.
        already={r['prompt'] for r in db.all_(
            'SELECT prompt FROM answers WHERE scan_id=? AND run_n=? AND engine=?',
            (scan_id,b['run_n'],engine))}
        for q in prompts:
            if q in already:
                continue                    # never store the same answer twice
            hit=got.get(q) or loose.get(_quote_key(q))
            if hit:
                _store_answer(scan_id,q,b['run_n'],hit[0],hit[1],hit[2],engine)
        db.write('UPDATE scan_batches SET collected=1 WHERE scan_id=? AND run_n=? AND engine=?',(scan_id,b['run_n'],engine))

    pending=db.all_("""SELECT a.id, a.prompt, a.raw_text FROM answers a
                       JOIN answer_processing p ON p.answer_id=a.id
                       WHERE a.scan_id=? AND p.status='pending'""",(scan_id,))
    for a in pending:
        try:
            _extract(a['id'],a['prompt'],a['raw_text'],products,aliases,prepared,usage)
        except Exception as e:                                  # noqa: BLE001
            db.write("UPDATE answer_processing SET status='failed',error=? WHERE answer_id=?",(str(e),a['id']))

    engines=_engines()
    status,coverage=engine_status(scan_id,engines,len(prompts)*config.RUNS_PER_QUESTION)
    if sum(c['collected'] for c in coverage.values()):
        scoring.score(scan_id)
    stored=db.one('SELECT COUNT(*) AS n FROM answers WHERE scan_id=?',(scan_id,))['n']
    db.write('UPDATE scans SET status=?,error=?,finished_at=?,done=? WHERE id=?',
             (status,None if status=='done' else 'Recovered after the app stopped mid-scan. '
              'Answers already bought were kept.',time.time(),stored,scan_id))
    _notify(row['store_domain'],status)
    return status


def _notify(store_domain,status):
    """Email the store's owner when their first scan has results. Never lets
    an email problem touch the scan."""
    if status not in ('done','partial'):
        return
    try:
        import mailer
        b=db.brand(store_domain)
        mailer.first_results(store_domain,(b or {}).get('brand_name',''))
    except Exception:                                       # noqa: BLE001
        pass


def recover_interrupted():
    """A scan still 'running' at startup died with the previous server.

    Before the scraped path this was safe to write off: answers arrived one
    at a time, so almost nothing was lost. Now a whole batch is bought before
    the first answer is stored, so a scan with an open batch gets finished
    instead of failed - otherwise a restart throws away answers already paid
    for. Only scans with nothing recoverable are marked failed.
    """
    resumable=[]
    for s in db.all_("SELECT id FROM scans WHERE status='running'"):
        open_batch=db.one('SELECT COUNT(*) AS n FROM scan_batches WHERE scan_id=? AND collected=0',(s['id'],))['n']
        pending=db.one("""SELECT COUNT(*) AS n FROM answers a JOIN answer_processing p ON p.answer_id=a.id
                          WHERE a.scan_id=? AND p.status='pending'""",(s['id'],))['n']
        if open_batch or pending:
            resumable.append(s['id'])
        else:
            db.write("UPDATE scans SET status='failed', error='The app was stopped "
                     "while this scan was running.' WHERE id=?",(s['id'],))
    for scan_id in resumable:
        threading.Thread(target=resume,args=(scan_id,),daemon=True).start()
    return resumable
