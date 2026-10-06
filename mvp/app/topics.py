"""Onboarding step 5: topics, the way Peec AI does it.

The model proposes a handful of buying topics from the catalog; the merchant
ticks, renames or adds their own. Step 6 then writes PROMPTS_PER_TOPIC buyer
questions under each chosen topic (plus the specific ones), so the merchant
steers what gets measured without writing questions themselves.

Topics are setup, not measurement: they only shape question generation, and
questions still freeze at the first scan.
"""
import json
from urllib.parse import quote

import catalog
import db
import llm
import onboarding
import questions

E = onboarding.E
SUGGESTED = 5       # topics proposed by default
MAX_TOPICS = 10
PROMPTS_PER_TOPIC = 4   # 5 topics x 4 = ~20 questions, ~$13/user/month (Kelian, 2026-09-25)

INSTRUCTIONS = """You propose the buying topics an online store should be tracked on in AI
shopping answers: the broad themes its likely buyers ask ChatGPT about. You
get the brand profile the merchant verified (description, industry, identity,
products & services, markets) and a compact catalog summary. Return exactly %d
topics.

Build the topics from the brand profile first: its Products & Services name
the categories, its Identity and Description give the character words, its
markets give the language. Use the catalog to confirm products exist.

- Write the topics in the main language of the shoppers in the brand's home
  market (e.g. Spanish for a store based in Spain, English for the UK/US).
- Each topic is short, 2-4 words: a product category plus ONE word or phrase
  for what characterises it in this brand's range and identity (design,
  craft, style, material, the need it serves). Examples of the right shape:
  "Sofás de diseño", "Mesas de comedor artesanales", "Decoración de
  interiores elegante", "Gentle Daily Cleansers".
- Broad enough that many shoppers ask about it; one topic may be a wider
  theme across categories (e.g. modern living-room furniture).
- No place names in topics (location belongs in the questions), no brand
  name, no dimensions or prices, no duplicates or near-duplicates.
- Every topic is backed by products in the catalog, and the main categories
  are covered. Sentence case as is natural in that language.""" % SUGGESTED

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["topics"],
          "properties": {"topics": {"type": "array", "items": {"type": "string"}}}}


def _table():
    db.write("CREATE TABLE IF NOT EXISTS topics (store_domain TEXT PRIMARY KEY, "
             "topics TEXT, chosen TEXT, stale INTEGER DEFAULT 0)")


def saved(domain):
    """(all topics shown, chosen topics, stale) or None."""
    _table()
    row = db.one("SELECT topics, chosen, stale FROM topics WHERE store_domain=?", (domain,))
    if not row:
        return None
    return json.loads(row["topics"]), json.loads(row["chosen"]), bool(row["stale"])


def chosen(domain):
    got = saved(domain)
    return got[1] if got else []


def _clean(names):
    out, seen = [], set()
    for n in names or []:
        n = " ".join(str(n).split())[:60]
        if n and n.casefold() not in seen:
            seen.add(n.casefold())
            out.append(n)
    return out


def suggest(domain):
    store = db.brand(domain) or {}
    money = dict(currency=store.get("currency") or "",
                 symbol=catalog.SYMBOLS.get(store.get("currency") or "", ""))
    ids = set(db.scope(domain)["product_ids"])
    products = [p for p in db.all_("SELECT * FROM products WHERE store_domain=?", (domain,))
                if p["id"] in ids]
    if not products:
        raise ValueError("Include some products in your catalog first.")
    profile = "Brand profile:\n" + "\n".join("%s: %s" % (label, value) for label, value in (
        ("Description", store.get("description")), ("Industry", store.get("industry")),
        ("Identity", ", ".join(store.get("identity") or [])),
        ("Products & services", ", ".join(store.get("services") or [])),
        ("Based in / markets", ", ".join(store.get("markets") or [])),
        ("Shopper country", store.get("country"))) if value)
    out = llm.json_call(INSTRUCTIONS, profile + "\n\n" + questions.catalog_brief(products, money),
                        "topics", SCHEMA, attempts=2)
    names = _clean(out.get("topics"))[:MAX_TOPICS]
    if not names:
        raise llm.LLMError("No topics came back. Try again or add your own.")
    return names


def save(domain, shown, picked):
    shown, picked = _clean(shown)[:MAX_TOPICS * 2], _clean(picked)
    if not picked:
        raise ValueError("Choose at least one topic.")
    if len(picked) > MAX_TOPICS:
        raise ValueError("Choose up to %d topics." % MAX_TOPICS)
    ps = db.get_prompt_set(domain)
    before = chosen(domain) or (_clean(ps["clusters"]) if ps else [])   # locked set: its groups
    # Changed topics mean the questions no longer match them, so step 6
    # writes them again. Locked questions are never edited: new ones are
    # saved as a new version and past scans keep theirs.
    stale = int(bool(ps and before != picked)) or int(bool(saved(domain) and saved(domain)[2]))
    db.write("INSERT OR REPLACE INTO topics VALUES (?,?,?,?)",
             (domain, json.dumps(shown), json.dumps(picked), stale))
    return picked


def clear_stale(domain):
    _table()
    db.write("UPDATE topics SET stale=0 WHERE store_domain=?", (domain,))


def api(q, form):
    domain = q.get("d", "")
    try:
        if not db.brand(domain):
            raise ValueError("Unknown store.")
        if "chosen" in form:
            picked = save(domain, json.loads(form.get("shown", "[]")), json.loads(form["chosen"]))
            return 200, ("json", json.dumps({"chosen": picked}))
        got = saved(domain)
        ps = db.get_prompt_set(domain)
        if got and not q.get("regen"):
            return 200, ("json", json.dumps({"shown": got[0], "chosen": got[1]}))
        names = suggest(domain)
        return 200, ("json", json.dumps({"shown": names, "chosen": names}))
    except (ValueError, TypeError, llm.LLMError) as e:
        return 200, ("json", json.dumps({"error": str(e)}))


def page(q):
    domain = q.get("d", "")
    brand = db.brand(domain)
    if not brand:
        return 303, "/new"
    ps = db.get_prompt_set(domain)
    frozen = bool(ps and ps["frozen_at"])
    body = '''<h1>Review topics</h1>
<p class="sub">We’ll write buyer questions for each topic you choose, and show how AI recommends your products in these areas. Rename any topic or add your own.</p>
%s<div class="topics-head"><span>Select topics</span><span id="tcount">0/%d</span></div>
<div id="tbox" aria-live="polite"><div class="loading"><span class="spin"></span>Finding the topics in your catalog…</div></div>
<button type="button" class="btn ghost small-btn" id="tregen">Suggest new topics</button>
<p class="small" id="tmsg" role="status"></p>
<script>
document.addEventListener('DOMContentLoaded',()=>{
const domain=%s,frozen=%s,MAX=%d,endpoint='/api/topics?d='+encodeURIComponent(domain);
const box=document.getElementById('tbox'),count=document.getElementById('tcount'),msg=document.getElementById('tmsg'),next=document.getElementById('topics-next');
let rows=[];
function picked(){return rows.filter(r=>r.on&&r.name.trim()).map(r=>r.name.trim());}
function sync(){const n=picked().length;count.textContent=n+'/'+MAX;next.disabled=!n||n>MAX;
 box.querySelectorAll('input[type=checkbox]').forEach((c,i)=>{c.disabled=!rows[i].on&&n>=MAX;});
 box.dispatchEvent(new CustomEvent('topicschange',{bubbles:true,detail:picked()}));}
function render(){box.replaceChildren();rows.forEach((r,i)=>{const row=document.createElement('label');row.className='topic-row';
 const c=document.createElement('input');c.type='checkbox';c.checked=r.on;c.onchange=()=>{r.on=c.checked;sync();};
 const t=document.createElement('input');t.type='text';t.value=r.name;t.placeholder='Name your topic';t.setAttribute('aria-label','Topic');
 t.oninput=()=>{r.name=t.value;sync();};row.append(c,t);box.append(row);});
 {const add=document.createElement('button');add.type='button';add.className='topic-add';add.textContent='+ Add custom';
  add.onclick=()=>{rows.push({name:'',on:true});render();box.querySelectorAll('.topic-row input[type=text]')[rows.length-1].focus();};box.append(add);}
 sync();}
function load(fresh){const regen=document.getElementById('tregen');regen.disabled=true;msg.textContent='';
 if(fresh)box.innerHTML='<div class="loading"><span class="spin"></span>Finding the topics in your catalog…</div>';
 fetch(endpoint+(fresh?'&regen=1':''),{method:'POST'}).then(r=>r.json()).then(j=>{if(j.error)throw Error(j.error);
 rows=j.shown.map(n=>({name:n,on:j.chosen.includes(n)}));j.chosen.filter(n=>!j.shown.includes(n)).forEach(n=>rows.push({name:n,on:true}));
 // More than the limit (older question sets): start with the first ones ticked.
 let k=0;rows.forEach(r=>{if(r.on&&++k>MAX)r.on=false;});render();})
 .catch(e=>{if(!rows.length)rows=[{name:'',on:true}];render();msg.textContent=e.message+' You can add your own topics.';})
 .finally(()=>{regen.disabled=false;});}
document.getElementById('tregen').onclick=()=>load(true);load(false);
next.onclick=async()=>{next.disabled=true;msg.textContent='Saving…';
 try{const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
  body:'shown='+encodeURIComponent(JSON.stringify(rows.map(r=>r.name.trim()).filter(Boolean)))+'&chosen='+encodeURIComponent(JSON.stringify(picked()))});
  const j=await r.json();if(j.error)throw Error(j.error);location.href='/questions?d='+encodeURIComponent(domain);}
 catch(e){msg.textContent=e.message;sync();}};
});</script>''' % ('<p class="small">You’ve already run scans with your current questions. Changing topics writes a new set of questions; past results stay saved.</p>' if frozen else '',
                   MAX_TOPICS, json.dumps(domain), json.dumps(frozen), MAX_TOPICS)
    # Ghost preview: the Prompts screen's topic sidebar, filling as topics change.
    body += '''<template id="ghost-tpl"><div class="cat-ghost" aria-hidden="true"><div class="gw">
<div class="gw-side"><div class="gw-brand"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><b>%s</b><span>&#8964;</span></div>
<span class="sk h"></span><span class="sk"></span><span class="sk s"></span><span class="sk l"></span><span class="sk s"></span>
<div class="gw-nav"><svg viewBox="0 0 16 16"><path d="M2 4h5l1.5 1.5H14V12H2z"/></svg>Topics</div></div>
<div class="gw-main"><h3>Topics</h3><p>Each topic gets its own buyer questions.</p>
<div class="gw-stats"><div><small>Topics</small><strong id="g-tn">0</strong></div>
<div><small>Questions</small><strong id="g-qn">0</strong></div></div>
<div class="gw-label">Your topics</div><div class="gw-qs" id="g-ts"></div></div></div></div></template>
<script>document.addEventListener('DOMContentLoaded',function(){
 var a=document.querySelector('aside'),t=document.getElementById('ghost-tpl');if(!a||!t)return;
 a.append(t.content.cloneNode(true));
 document.addEventListener('topicschange',function(e){var list=document.getElementById('g-ts');list.replaceChildren();
  document.getElementById('g-tn').textContent=e.detail.length;
  document.getElementById('g-qn').textContent=e.detail.length*%d+(e.detail.length?%d:0);
  e.detail.forEach(function(n,i){var row=document.createElement('div'),k=document.createElement('i'),s=document.createElement('span');
   k.textContent=i+1;s.textContent=n;row.append(k,s);list.append(row);});});
});</script>''' % (E(domain), E(brand["brand_name"]), PROMPTS_PER_TOPIC, questions.SPECIFIC_QUESTIONS)
    return 200, onboarding.page("Review topics", body, 4,
                                '<a class="btn ghost" href="/store?d=%s">← Back</a>'
                                '<button class="btn" id="topics-next" disabled>Continue →</button>' % E(quote(domain)))
