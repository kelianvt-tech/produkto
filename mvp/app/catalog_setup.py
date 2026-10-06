"""Catalog confirmation and editable, coverage-aware buyer questions."""
import html
import json
from urllib.parse import quote
import db
import onboarding

E=html.escape


def js(value):
    return json.dumps(value).replace('<','\\u003c')


def _thumb(url, width=480):
    """Shopify CDN images at tile size, not the multi-megabyte original."""
    if not url or 'cdn.shopify.com' not in url or 'width=' in url:
        return url or ''
    return url+('&' if '?' in url else '?')+'width=%d'%width


def catalog(domain):
    b=db.brand(domain)
    if not b:
        return 303,'/new'
    ps=db.get_prompt_set(domain)
    frozen=bool(ps and ps['frozen_at'])
    products=ps['catalog_snapshot'] if frozen else [dict(p) for p in db.all_('SELECT * FROM products WHERE store_domain=? ORDER BY title',(domain,))]
    scope=db.scope(domain)
    types=sorted({db.product_type(p) for p in products})
    checks=''.join('<label><input type="checkbox" value="%s" %s %s> %s</label>'%(E(t),'checked' if t not in scope['excluded_types'] else '', 'disabled' if frozen else '',E(t)) for t in types)
    tiles=''.join('<article class="tile catalog-tile" data-type="%s" data-t="%s"><div class="im"><img src="%s" alt="" loading="lazy" style="width:100%%;height:100%%;object-fit:contain"></div><div class="t">%s</div><div class="p">%s</div><div class="p inclusion"></div></article>'%(E(db.product_type(p)),E(p['title'].lower()),E(_thumb(p['image'])),E(p['title']),E(p['price'] or '')) for p in products)
    body='''<h1>Confirm your catalog</h1><p class="sub">Choose the product categories you want to track.</p>
<p class="small">%s · %d products</p>%s
<div class="catalog-types" id="types">%s</div><label class="search-label" for="catalog-search">Find a product</label>
<input type="search" id="catalog-search" placeholder="Search products"><div class="grid" id="catalog-grid">%s</div>
<p id="catalog-empty" class="small" hidden>No products match your search.</p><p class="small" id="catalog-count"></p><p class="err" id="catalog-error" hidden></p>
<script>
document.addEventListener('DOMContentLoaded',()=>{
const domain=%s,frozen=%s,button=document.getElementById('catalog-next');
function update(){let term=document.getElementById('catalog-search').value.toLowerCase();const included=Array.from(document.querySelectorAll('#types input:checked')).map(x=>x.value);let n=0,shown=0;
document.querySelectorAll('.catalog-tile').forEach(t=>{let on=included.includes(t.dataset.type);n+=on?1:0;t.style.opacity=on?'1':'.5';t.querySelector('.inclusion').textContent=on?'Included':'Excluded';t.hidden=!t.dataset.t.includes(term);shown+=t.hidden?0:1;});document.getElementById('catalog-count').textContent=n+' products included';document.getElementById('catalog-empty').hidden=!!shown;button.disabled=!n;}
document.getElementById('types').addEventListener('change',update);document.getElementById('catalog-search').oninput=update;update();
button.onclick=async()=>{button.disabled=true;try{if(!frozen){const excluded=Array.from(document.querySelectorAll('#types input:not(:checked)')).map(x=>x.value);const r=await fetch('/api/catalog?d='+encodeURIComponent(domain),{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'excluded='+encodeURIComponent(JSON.stringify(excluded))});const j=await r.json();if(j.error)throw Error(j.error);}location.href='/topics?d='+encodeURIComponent(domain);}catch(e){const err=document.getElementById('catalog-error');err.hidden=false;err.textContent=e.message;update();}};
});</script>'''%(E(domain),len(products),'<p class="small">Catalog coverage is locked to your first scan. New products do not change this baseline.</p>' if frozen else '',checks,tiles,js(domain),js(frozen))

    name=dict(b).get('brand_name') or dict(b).get('brand') or domain
    # Peec-style ghost preview in the side panel: a faded app window whose
    # Catalog page mirrors the choices made on the left, live.
    body+='''<template id="ghost-tpl"><div class="cat-ghost" aria-hidden="true"><div class="gw">
<div class="gw-side"><div class="gw-brand"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><b>%s</b><span>⌄</span></div>
<i class="sk h"></i><i class="sk"></i><i class="sk s"></i><i class="sk h"></i><i class="sk"></i><i class="sk l"></i><i class="sk s"></i><i class="sk h"></i><i class="sk"></i><i class="sk l"></i>
<div class="gw-nav"><svg viewBox="0 0 16 16"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>Catalog</div></div>
<div class="gw-main"><h3>Catalog</h3><p>The products you track across AI answers.</p>
<div class="gw-store"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><div><b>%s</b><small>%s</small></div></div>
<div class="gw-stats"><div><small>Tracked products</small><strong id="g-n">0</strong></div><div><small>Categories</small><strong id="g-t">0</strong></div></div>
<div class="gw-label">Categories</div><div class="gw-chips" id="g-chips"></div>
<div class="gw-label">Products</div><div class="gw-list" id="g-list"></div></div></div></div></template>
<script>document.addEventListener('DOMContentLoaded',()=>{const a=document.querySelector('aside'),t=document.getElementById('ghost-tpl');if(!a||!t)return;a.append(t.content.cloneNode(true));
const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function sync(){const on=[...document.querySelectorAll('#types input:checked')].map(x=>x.value),all=[...document.querySelectorAll('#types input')].map(x=>x.value),term=document.getElementById('catalog-search').value.toLowerCase();
const tiles=[...document.querySelectorAll('.catalog-tile')].filter(x=>on.includes(x.dataset.type));
document.getElementById('g-n').textContent=tiles.length;document.getElementById('g-t').textContent=on.length;
document.getElementById('g-chips').innerHTML=all.map(v=>'<span class="'+(on.includes(v)?'':'off')+'">'+esc(v)+'</span>').join('');
document.getElementById('g-list').innerHTML=tiles.filter(x=>x.dataset.t.includes(term)).slice(0,6).map(x=>'<div><img src="'+esc(x.querySelector('img').src)+'" alt=""><b>'+esc(x.querySelector('.t').textContent)+'</b><small>'+esc(x.querySelector('.p').textContent)+'</small></div>').join('');}
document.getElementById('types').addEventListener('change',sync);document.getElementById('catalog-search').addEventListener('input',sync);sync();});</script>'''%(E(domain),E(name),E(domain),E(name),E(domain))
    return 200,onboarding.page('Confirm your catalog',body,3,'<a class="btn ghost" href="/brand?d=%s">← Back</a><button class="btn" id="catalog-next">Continue →</button>'%E(quote(domain)))


def question_page(domain):
    brand=db.brand(domain)
    if not brand:
        return 303,'/new'
    ps=db.get_prompt_set(domain)
    import topics
    if not ps and not topics.chosen(domain):
        return 303, '/topics?d=' + quote(domain)
    stale=bool((topics.saved(domain) or ([],[],False))[2])
    # New topics after the lock: this page writes a new version of the questions.
    frozen=bool(ps and ps['frozen_at']) and not stale
    products=ps['catalog_snapshot'] if frozen else [dict(p) for p in db.all_('SELECT * FROM products WHERE store_domain=? ORDER BY title',(domain,))]
    included=set(db.scope(domain)['product_ids'])
    products=[dict(id=p['id'],title=p['title']) for p in products if p['id'] in included]
    items=items_out(ps) if ps and not stale else None
    history=''.join('<p class="small"><a href="/r/%s">Saved scan · %s</a></p>'%(E(s['token']),E(s['status'])) for s in db.all_('SELECT token,status FROM scans WHERE prompt_set_id=? ORDER BY run_at DESC',(ps['id'],))) if ps else ''
    body='''<h1>Buyer questions</h1><p class="sub">Review the questions your buyers ask ChatGPT, grouped around your catalog.</p>
<p class="small">%s</p><div id="qbox" aria-live="polite"></div><button class="btn ghost small-btn" id="regen" %s>Write new questions</button><p class="small" id="msg" role="status"></p>%s
<script>
document.addEventListener('DOMContentLoaded',()=>{
const domain=%s,frozen=%s,products=%s;let items=%s;
const box=document.getElementById('qbox'),run=document.getElementById('run'),regen=document.getElementById('regen'),msg=document.getElementById('msg');
const endpoint='/api/questions?d='+encodeURIComponent(domain);let busy=false;
function esc(s){let d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function sync(){run.disabled=busy||!items||!items.length||items.some(x=>!x.q.trim()||!x.products.length);}
function render(){box.replaceChildren();let last='';items.forEach((it,i)=>{if(it.cluster!==last){const h=document.createElement('h2');h.className='section-label';h.textContent=it.cluster||'Buyer questions';box.append(h);last=it.cluster;}
const list=document.createElement('ol');list.className='qs';const li=document.createElement('li');list.append(li);
if(frozen){const text=document.createElement('span');text.className='qtext';text.textContent=it.q;li.append(text);}else{const text=document.createElement('textarea');text.rows=2;text.value=it.q;text.setAttribute('aria-label','Buyer question');text.oninput=()=>{it.q=text.value;sync();};li.append(text);const del=document.createElement('button');del.className='qdel';del.textContent='×';del.setAttribute('aria-label','Remove question');del.onclick=()=>{items.splice(i,1);render();};li.append(del);}
const tag=document.createElement('span');tag.className='tag';tag.textContent=it.tag;li.append(tag);const coverage=document.createElement('details');coverage.style.width='100%%';const summary=document.createElement('summary');summary.textContent='Relevant products';coverage.append(summary);
products.forEach(p=>{if(frozen&&!it.products.includes(p.id))return;const label=document.createElement('label');label.style.display='block';label.style.padding='5px 0';const input=document.createElement('input');input.type='checkbox';input.style.width='auto';input.style.minHeight='auto';input.checked=it.products.includes(p.id);input.disabled=frozen;input.onchange=()=>{it.products=input.checked?[...it.products,p.id]:it.products.filter(id=>id!==p.id);sync();};label.append(input,document.createTextNode(' '+p.title));coverage.append(label);});li.append(coverage);box.append(list);});
if(!frozen){const add=document.createElement('button');add.className='btn ghost small-btn';add.textContent='+ Add a question';add.onclick=()=>{items.push({q:'',tag:'',cluster:'Buyer questions',products:[]});render();};box.append(add);}sync();}
async function request(body,url=endpoint){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body});const j=await r.json();if(j.error)throw Error(j.error);return j;}
async function load(fresh){busy=true;regen.disabled=true;sync();box.innerHTML='<div class="loading"><span class="spin"></span>Preparing buyer questions from your catalog…</div>';try{const j=await request('',endpoint+(fresh?'&regen=1':''));items=j.questions;render();}catch(e){items=null;box.innerHTML='<div class="err">'+esc(e.message)+'</div>';}finally{busy=false;regen.disabled=false;sync();}}
regen.onclick=()=>load(true);run.onclick=async()=>{busy=true;regen.disabled=true;sync();msg.textContent='Saving…';try{if(!frozen)await request('questions='+encodeURIComponent(JSON.stringify(items)));msg.textContent='Starting…';const j=await request('','/api/scan?d='+encodeURIComponent(domain));location.href='/r/'+j.token;}catch(e){msg.textContent=e.message;busy=false;regen.disabled=false;sync();}};
if(items)render();else load(false);
});</script>'''%('These are locked now, so every scan stays comparable.' if frozen else 'Edit the questions and check their relevant products. These questions stay fixed after your first scan so future results can be compared.', 'hidden' if frozen else '',history,js(domain),js(frozen),js(products),js(items))
    # Ghost preview of the Prompts screen. The question list is rendered by
    # the page's own closure, so mirror it with an observer rather than
    # reaching into that code.
    body += """<template id="ghost-tpl"><div class="cat-ghost" aria-hidden="true"><div class="gw">
<div class="gw-side"><div class="gw-brand"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><b>%s</b><span>&#8964;</span></div>
<span class="sk h"></span><span class="sk"></span><span class="sk s"></span><span class="sk l"></span><span class="sk s"></span>
<div class="gw-nav"><svg viewBox="0 0 16 16"><path d="M3 3h10v7H8.5L5.5 13v-3H3z"/></svg>Prompts</div></div>
<div class="gw-main"><h3>Prompts</h3><p>The buyer questions we ask AI models about your catalog.</p>
<div class="gw-stats"><div><small>Questions</small><strong id="g-qn">0</strong></div>
<div><small>Products covered</small><strong id="g-pn">%d</strong></div></div>
<div class="gw-label">Buyer questions</div><div class="gw-qs" id="g-qs"></div></div></div></div></template>
<script>document.addEventListener('DOMContentLoaded',function(){
 var a=document.querySelector('aside'),t=document.getElementById('ghost-tpl'),box=document.getElementById('qbox');
 if(!a||!t||!box)return;
 a.append(t.content.cloneNode(true));
 var list=document.getElementById('g-qs'),count=document.getElementById('g-qn');
 function sync(){
  var qs=Array.prototype.map.call(box.querySelectorAll('.qs li'),function(li){
   var f=li.querySelector('textarea,.qtext');return f?(f.value!==undefined?f.value:f.textContent).trim():'';
  }).filter(Boolean);
  count.textContent=qs.length;
  list.replaceChildren();
  if(!qs.length){var e=document.createElement('p');e.className='gw-empty';
   e.textContent='Writing your buyer questions\u2026';list.append(e);return;}
  qs.slice(0,6).forEach(function(q,i){
   var row=document.createElement('div');var n=document.createElement('i');n.textContent=i+1;
   var s=document.createElement('span');s.textContent=q;row.append(n,s);list.append(row);});
  if(qs.length>6){var more=document.createElement('p');more.className='gw-empty';
   more.textContent='+ '+(qs.length-6)+' more';list.append(more);}
 }
 new MutationObserver(sync).observe(box,{childList:true,subtree:true,characterData:true});
 box.addEventListener('input',sync);
 sync();
});</script>""" % (E(domain), E(brand['brand_name']), len(products))

    return 200,onboarding.page('Buyer questions',body,5,'<a class="btn ghost" href="/topics?d=%s">← Back</a><button class="btn" id="run" disabled>Get insights →</button>'%E(quote(domain)))


def items_out(ps):
    return [dict(q=q,tag=ps['tags'][i] if i<len(ps['tags']) else '',cluster=ps['clusters'][i] if i<len(ps['clusters']) else '',products=ps['relevance'][i] if i<len(ps['relevance']) else []) for i,q in enumerate(ps['prompts'])]
