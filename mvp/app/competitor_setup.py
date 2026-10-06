"""Competitor onboarding; suggestions never enter measured evidence."""
import json
from urllib.parse import quote
import catalog_setup
import db
import llm
import apify_answers
import competitor_finder
import onboarding
import questions
import competitor_comparison as comparison
from html import escape as E


def scope(domain):
    ps = db.get_prompt_set(domain)
    ids = db.scope(domain)['product_ids']
    products = ps['catalog_snapshot'] if ps and ps['frozen_at'] else [dict(p) for p in db.all_('SELECT * FROM products WHERE store_domain=? ORDER BY title', (domain,))]
    return [p for p in products if p['id'] in ids]


def selection_context(domain):
    return dict(prompts=[], product_ids=[p['id'] for p in scope(domain)])


def ready(domain):
    selections = comparison.saved(domain)
    if not selections:
        return False
    try:
        context = selection_context(domain)
        for selection in selections:
            comparison.validate(context, selection)
    except (ValueError, TypeError):
        return False
    return True


def save(domain, selections):
    if not isinstance(selections, list) or not 1 <= len(selections) <= 5:
        raise ValueError('Choose between one and five competitors.')
    clean = [comparison.validate(selection_context(domain), s) for s in selections]
    own_brand = db.brand(domain)['brand_name']
    if len({comparison.norm(s['brand']) for s in clean}) != len(clean):
        raise ValueError('Each competitor must be different.')
    if any(comparison.norm(s['brand']) == comparison.norm(own_brand) for s in clean):
        raise ValueError('Choose a competitor other than your own brand.')
    if len({tuple(p['own_id'] for p in s['pairs']) for s in clean}) != 1:
        raise ValueError('Use the same six of your products for every competitor.')
    db.write('INSERT OR REPLACE INTO competitor_comparisons VALUES (?,?)', (domain, json.dumps(clean)))
    return clean


def suggest(domain, chosen):
    products = scope(domain)
    if not isinstance(chosen, list) or len(chosen) != 6 or len(set(chosen)) != 6 or not all(type(i) is int for i in chosen):
        raise ValueError('Choose six distinct products first.')
    lookup = {p['id']: p for p in products}
    if not set(chosen) <= set(lookup):
        raise ValueError('Choose products included in your catalog.')
    signature = json.dumps(chosen)
    cached = db.one('SELECT * FROM competitor_suggestions WHERE store_domain=? AND scope=?', (domain, signature))
    if cached:
        return json.loads(cached['suggestions'])
    brand = db.brand(domain)
    try:
        found, sources = competitor_finder.suggest(domain, brand, [lookup[i] for i in chosen])
    except apify_answers.ApifyError as error:
        raise ValueError(str(error))
    clean = []
    for candidate in found:
        try:
            clean.append(comparison.validate(selection_context(domain), candidate))
        except (ValueError, TypeError):
            continue
    result = dict(competitors=clean[:3], sources=sources)
    usage = {}
    if not clean:
        raise ValueError('We could not find complete six-product suggestions. Add a competitor manually, or try again.')
    db.write('INSERT OR REPLACE INTO competitor_suggestions VALUES (?,?,?,?)', (domain, signature, json.dumps(result), json.dumps(usage)))
    return result


def api(q, form):
    domain = q.get('d','')
    try:
        if not db.brand(domain):
            raise ValueError('Unknown store.')
        if q.get('suggest') == '1':
            out = suggest(domain, json.loads(form.get('products','[]')))
        else:
            save(domain, json.loads(form.get('selections','[]')))
            out = {'saved':True}
    except (ValueError, TypeError, llm.LLMError) as error:
        out = {'error':str(error)}
    return 200, ('json', json.dumps(out))


def page(q):
    domain = q.get('d','')
    if not db.brand(domain):
        return 303, '/new'
    products = scope(domain)
    selections = comparison.saved(domain)
    def js(value):
        return json.dumps(value).replace('<', '\\u003c')
    body = '''<h1>Choose your competitors</h1><p class="sub">Your six products, side by side with theirs.</p>
<p class="small">We’ll suggest competitors and comparable products from your catalog. Review the suggestions, add your own, and choose who to track.</p>
<div id="own-products"></div><button class="btn ghost" id="suggest-competitors" type="button">Suggest competitors</button>
<p id="competitor-status" role="status" aria-live="polite"></p><div id="competitor-list"></div>
<button class="btn ghost" id="add-competitor" type="button">+ Add a competitor</button><p id="competitor-error" class="err" role="alert" hidden></p>
<p class="small">Suggestions are for your review, not measured results. Both sides will be checked against the same buyer answers. Generating suggestions costs about half a cent; viewing comparisons does not start another scan.</p>
<script>document.addEventListener('DOMContentLoaded',()=>{
const domain=DOMAIN,products=PRODUCTS;let rivals=SAVED.map(s=>({...s,selected:true}));
const box=document.getElementById('competitor-list'),ownBox=document.getElementById('own-products'),status=document.getElementById('competitor-status'),err=document.getElementById('competitor-error'),next=document.getElementById('competitor-next'),suggest=document.getElementById('suggest-competitors'),add=document.getElementById('add-competitor');let busy=false;
function field(label,element){const l=document.createElement('label');l.textContent=label;l.append(element);return l;}
function input(value,placeholder){const i=document.createElement('input');i.value=value||'';i.placeholder=placeholder;return i;}
const ownSelects=Array.from({length:6},(_,i)=>{const s=document.createElement('select');products.forEach(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.title;s.append(o);});s.value=rivals[0]?.pairs[i]?.own_id??products[i]?.id??'';ownBox.append(field('Your product '+(i+1),s));s.onchange=()=>{rivals.forEach(r=>{r.pairs[i].own_id=Number(s.value);});render();};return s;});
function ownIds(){return ownSelects.map(s=>Number(s.value));}
function sync(){const valid=products.length>=6&&new Set(ownIds()).size===6&&ownIds().every(Boolean);next.disabled=busy||!valid||!rivals.some(r=>r.selected);suggest.disabled=busy||!valid;add.disabled=busy||!valid||rivals.length>=5;ownSelects.forEach(s=>s.disabled=busy);}
function render(){box.replaceChildren();rivals.forEach((r,index)=>{const card=document.createElement('section');card.className='competitor-option';const chosen=document.createElement('input');chosen.type='checkbox';chosen.checked=r.selected;chosen.onchange=()=>{r.selected=chosen.checked;sync();};card.append(field('Include competitor',chosen));const brand=input(r.brand,'Competitor brand');brand.oninput=()=>r.brand=brand.value;card.append(field('Brand name',brand));
const details=document.createElement('details');details.open=!r.brand;const summary=document.createElement('summary');summary.textContent='Review six comparable products';details.append(summary);
r.pairs.forEach((pair,i)=>{const row=document.createElement('div');row.className='competitor-product';const h=document.createElement('p');h.textContent='Compare with '+(products.find(p=>p.id===pair.own_id)?.title||'your product '+(i+1));row.append(h);const name=input(pair.title,'Exact competitor product name');name.oninput=()=>pair.title=name.value;const url=input(pair.url,'https://…');url.type='url';url.oninput=()=>{pair.url=url.value;link.href=/^https?:\\/\\//.test(url.value)?url.value:'#';};row.append(field('Product name',name),field('Product URL (optional)',url));const link=document.createElement('a');link.textContent='Check product page ↗';link.target='_blank';link.rel='noopener noreferrer';link.href=/^https?:\\/\\//.test(pair.url)?pair.url:'#';row.append(link);details.append(row);});card.append(details);const remove=document.createElement('button');remove.type='button';remove.className='btn ghost small-btn';remove.textContent='Remove';remove.onclick=()=>{rivals.splice(index,1);render();};card.append(remove);box.append(card);});sync();}
async function request(extra,data){const response=await fetch('/api/competitors?d='+encodeURIComponent(domain)+extra,{method:'POST',body:new URLSearchParams(data)});const j=await response.json();if(j.error)throw Error(j.error);return j;}
function fail(e){err.textContent=e.message;err.hidden=false;}
suggest.onclick=async()=>{busy=true;err.hidden=true;const t0=Date.now(),tick=()=>{status.textContent='Finding competitors and matching products… '+Math.round((Date.now()-t0)/1000)+'s (usually 1–2 minutes)';};tick();const timer=setInterval(tick,1000);sync();try{const out=await request('&suggest=1',{products:JSON.stringify(ownIds())});out.competitors.forEach(r=>{if(rivals.length<5&&!rivals.some(x=>x.brand.toLowerCase()===r.brand.toLowerCase()))rivals.push({...r,selected:true});});status.textContent='Suggestions ready. Review the products and untick any you do not want.';render();}catch(e){status.textContent='';fail(e);}finally{clearInterval(timer);busy=false;sync();}};
add.onclick=()=>{rivals.push({brand:'',selected:true,pairs:ownIds().map(id=>({own_id:id,title:'',url:''}))});render();};
next.onclick=async()=>{busy=true;sync();err.hidden=true;try{await request('',{selections:JSON.stringify(rivals.filter(r=>r.selected).map(r=>({brand:r.brand,pairs:r.pairs})))});location.href='/topics?d='+encodeURIComponent(domain);}catch(e){fail(e);busy=false;sync();}};
render();if(products.length<6){status.textContent='Include six products in your catalog to set up this comparison.';}else if(!rivals.length){suggest.click();}
});</script>'''.replace('DOMAIN',js(domain)).replace('PRODUCTS',js([dict(id=p['id'],title=p['title']) for p in products])).replace('SAVED',js(selections))
    # Peec-style ghost preview, as on the catalog step: a faded Competitors
    # page that mirrors the form on the left as it changes.
    b = dict(db.brand(domain))
    name = b.get('brand_name') or b.get('brand') or domain
    images = {p['id']: catalog_setup._thumb(p.get('image') or '', 120) for p in products}
    body += ("""<template id="ghost-tpl"><div class="cat-ghost" aria-hidden="true"><div class="gw">
<div class="gw-side"><div class="gw-brand"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><b>%s</b><span>⌄</span></div>
<i class="sk h"></i><i class="sk"></i><i class="sk s"></i><i class="sk h"></i><i class="sk"></i><i class="sk l"></i><i class="sk s"></i><i class="sk h"></i><i class="sk"></i><i class="sk l"></i>
<div class="gw-nav"><svg viewBox="0 0 16 16"><circle cx="5.5" cy="6" r="2.5"/><circle cx="11" cy="6" r="2.5"/><path d="M1.5 13.5c.6-2.2 2.2-3.3 4-3.3s3.4 1.1 4 3.3M9.2 10.4c.5-.2 1.1-.3 1.8-.3 1.8 0 3.4 1.1 4 3.3"/></svg>Competitors</div></div>
<div class="gw-main"><h3>Competitors</h3><p>Your products, side by side with theirs.</p>
<div class="gw-stats"><div><small>Your products</small><strong id="g-own">0</strong></div><div><small>Competitors</small><strong id="g-riv">0</strong></div></div>
<div class="gw-label">Competitors</div><div class="gw-rivals" id="g-rivals"></div>
<div class="gw-label">Your products</div><div class="gw-list" id="g-list"></div></div></div></div></template>
<script>document.addEventListener('DOMContentLoaded',()=>{const a=document.querySelector('aside'),t=document.getElementById('ghost-tpl');if(!a||!t)return;a.append(t.content.cloneNode(true));
const img=IMAGES,esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function sync(){const own=[...document.querySelectorAll('#own-products select')].map(s=>({id:s.value,title:s.selectedOptions[0]?.textContent||''}));
const cards=[...document.querySelectorAll('#competitor-list .competitor-option')].map(c=>{const ins=c.querySelectorAll('input:not([type=checkbox]):not([type=url])');return{on:c.querySelector('input[type=checkbox]')?.checked,brand:(ins[0]?.value||'').trim(),pairs:[...ins].slice(1).map(i=>i.value.trim())};}).filter(r=>r.brand);
const lead=cards.find(r=>r.on)||cards[0];
document.getElementById('g-own').textContent=own.filter(o=>o.id).length;document.getElementById('g-riv').textContent=cards.filter(r=>r.on).length;
const busy=document.getElementById('competitor-status').textContent.startsWith('Finding');
document.getElementById('g-rivals').innerHTML=cards.length?cards.map(r=>'<span class="'+(r.on?'on':'')+'">'+esc(r.brand)+'</span>').join(''):'<i class="sk s"></i><i class="sk"></i><i class="sk s"></i>'.replace(/sk/g,busy?'sk shimmer':'sk');
document.getElementById('g-list').innerHTML=own.map((o,i)=>'<div><img src="'+esc(img[o.id]||'')+'" alt=""><b>'+esc(o.title)+'</b><small>'+(lead&&lead.pairs[i]?'vs '+esc(lead.pairs[i]):'')+'</small></div>').join('');}
const form=document.getElementById('main');form.addEventListener('input',sync);form.addEventListener('change',sync);
new MutationObserver(sync).observe(form,{childList:true,subtree:true,characterData:true});sync();});</script>""" % (E(domain), E(name))).replace('IMAGES', js({str(k): v for k, v in images.items()}))
    return 200,onboarding.page('Competitors',body,4,'<a class="btn ghost" href="/store?d=%s">← Back</a><button class="btn" id="competitor-next">Continue →</button>'%E(quote(domain)))
