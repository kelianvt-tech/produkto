"""Read-only citation browser. One normalized source URL per saved answer."""
import datetime as dt
import json
import re
from collections import defaultdict
from html import escape as E
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import config
import engines
import evidence
import period
import storetime


def clean_url(url):
    from dashboard import safe_url
    if not safe_url(url):
        return ''
    u = urlsplit(url)
    tracking = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content','navsrc','srsltid','gclid','fbclid'}
    query = urlencode(sorted((k,v) for k,v in parse_qsl(u.query) if k.lower() not in tracking and not k.lower().startswith('utm_')))
    return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path or '/',query,''))


def key(url):
    url = clean_url(url)
    if not url:
        return ''
    u = urlsplit(url)
    return u.netloc.removeprefix('www.') + u.path.rstrip('/') + ('?'+u.query if u.query else '')


def content_type(url, product_match=False):
    """A deliberately conservative URL hint, not a fetched-page classification."""
    path = urlsplit(url).path.lower()
    if product_match or re.search(r'/(products?|p|dp)/',path):
        return 'Product'
    if re.search(r'/(reviews?|reviewed)/',path):
        return 'Review'
    if re.search(r'/(news|press)/',path):
        return 'News'
    if re.search(r'/(blogs?|articles?|guides?)/',path):
        return 'Article'
    if re.search(r'/(collections?|categor(y|ies))/',path):
        return 'Collection'
    if not path.strip('/'):
        return 'Homepage'
    return 'Unclassified'


def records(ctx, p):
    answers, mentions = evidence.load(ctx['ids'],p)
    scans = {s['id']:s for s in ctx['scans']}
    catalog = {key(x['url']):x for x in p['_catalog'] if key(x['url']) and (x['id']==p['id'] if p['id'] is not None else x['id'] in p['_ps']['product_ids'])}
    by_answer = defaultdict(list)
    for m in mentions:
        by_answer[m['answer_id']].append(m)
    own_domain = p['store_domain'].lower().removeprefix('www.')
    # Your products as they appear on other sites: the product title in the
    # page title (e.g. "Helsinki Moisturiser – Myza") or the product handle in
    # the URL (e.g. goodhoodstore.com/products/clubhouse-skin-helsinki-moisturiser-75ml).
    norm = lambda t: re.sub(r'[^a-z0-9]+', ' ', (t or '').lower()).strip()
    own_titles = [norm(x['title']) for x in catalog.values() if len(norm(x['title'])) >= 8]
    own_handles = [urlsplit(x['url']).path.rstrip('/').rsplit('/', 1)[-1].lower() for x in catalog.values()]
    own_handles = [h for h in own_handles if len(h) >= 8]
    def names_product(url, title):
        t, path = norm(title), urlsplit(url).path.lower()
        return any(x in t for x in own_titles) or any(h in path for h in own_handles)
    if p['id'] is not None:
        # A product page counts only the answers about THIS product: ones that
        # mention it or link to its page. The catalog page keeps every answer
        # to the buyer questions (5 Oct 2026).
        def about_product(a):
            if any(evidence.own(m,p) for m in by_answer[a['id']]):
                return True
            cites = json.loads(a['citations'] or '[]')
            return any(isinstance(c,dict) and key(clean_url(c.get('url'))) in catalog for c in cites)
        answers = [a for a in answers if about_product(a)]
    out = []
    for a in answers:
        seen = set()
        for order,c in enumerate(json.loads(a['citations'] or '[]'),1):
            if not isinstance(c,dict):
                continue
            url = clean_url(c.get('url'))
            ident = key(url)
            if not ident or ident in seen:
                continue
            seen.add(ident)
            host = urlsplit(url).hostname.lower().removeprefix('www.')
            own_site = host==own_domain or host.endswith('.'+own_domain)
            matched = [m for m in by_answer[a['id']] if key(m['url'])==ident and m['product_name']]
            # A homepage is not a product listing even if extraction links a product to it.
            own_matches = [m for m in matched if evidence.own(m,p) and urlsplit(url).path.strip('/')]
            product = catalog.get(ident)
            relation = 'Your product page' if product else 'Other listing of your product' if own_matches else 'Other source'
            # Why this source matters to the merchant. We never fetch the page,
            # so "mentions you" means: the answer tied your product to this link,
            # or the link was cited in an answer that recommended you.
            names_you = any(evidence.own(m,p) for m in by_answer[a['id']])
            about = 'Links to your product' if own_matches or product or (not own_site and urlsplit(url).path.strip('/') and names_product(url, c.get('title'))) else 'Cited when you were recommended' if names_you else ''
            names = [product['title']] if product else sorted(set(m['product_name'] for m in matched))
            engine = a['engine'] or config.DEFAULT_ENGINE
            timestamp = a['created_at'] or scans[a['scan_id']]['run_at']
            bucket = period.bucket_start(storetime.date_of(scans[a['scan_id']]['run_at'],ctx.get('tz')),ctx['per']['group']).isoformat()
            out.append(dict(url=url,title=str(c.get('title') or host),domain=host,source='Your site' if own_site else 'External site',
                            content=content_type(url,bool(product or (matched and urlsplit(url).path.strip('/')))),relation=relation,
                            products=names,engine=engine,model=config.engine_label(engine),order=order,date=storetime.label(timestamp,ctx.get('tz'),'%d %b %Y'),
                            timestamp=timestamp,bucket=bucket,answer=a['id'],prompt=a['prompt'],own=own_site,about=about))
    return out, answers


def render(s, ctx, p):
    rows, answers = records(ctx,p)
    group = ctx['per']['group']
    scan_buckets = {period.bucket_start(storetime.date_of(x['run_at'],ctx.get('tz')),group).isoformat() for x in ctx['scans'] if any(a['scan_id']==x['id'] for a in answers)}
    buckets = [dict(id=d.isoformat(),label=period.short_label(d,group),long=period.long_label(d,group),measured=d.isoformat() in scan_buckets) for d in period.bucket_starts(ctx['a'],ctx['b'],group)]
    filled = [i for i,b in enumerate(buckets) if b['measured']]
    if len(filled)>1:
        buckets=buckets[filled[0]:]
    logos = {e:engines.logo(e) for e in config.ENGINE_ORDER}
    payload = json.dumps(dict(rows=rows,buckets=buckets,logos=logos,token=s['token']),ensure_ascii=False).replace('<','\\u003c')
    return '''<section class="cite-analysis">
<div class="cite-plot"><header><h2>Top cited domains</h2><div class="cite-view" role="group" aria-label="Domain chart view"><button type="button" data-cite-view="time" aria-pressed="true">Over time</button><button type="button" data-cite-view="top" aria-pressed="false">Top domains</button></div></header><p class="cite-caption">Citations per measured period · your site and leading cited domains</p><div id="cite-chart" tabindex="0" aria-label="Domain citation chart"></div><div id="cite-chart-tip" role="status" hidden></div><details class="cite-chart-data"><summary>View chart data</summary><div id="cite-chart-data"></div></details></div>
<aside class="cite-shares"><header><h2>Citation share</h2><div class="cite-count-control"><button type="button" id="cite-count-button" aria-label="Citation share options" aria-expanded="false" aria-controls="cite-count-menu">⋯</button><fieldset id="cite-count-menu" hidden><legend>Number of domains</legend><label><input type="radio" name="citation-domain-count" value="7" checked>7</label><label><input type="radio" name="citation-domain-count" value="14">14</label><label><input type="radio" name="citation-domain-count" value="21">21</label><label><input type="radio" name="citation-domain-count" value="28">28</label><label><input type="radio" name="citation-domain-count" value="100000">All</label></fieldset></div></header><p class="cite-caption">Share of all matching source citations</p><div id="cite-share-list"></div><p class="cite-scroll-status" id="cite-scroll-status" role="status"></p></aside></section>
<section class="cite-browser" aria-label="Citation sources"><div class="cite-view cite-mode" role="group" aria-label="Citation list"><button type="button" data-cite-mode="all" aria-pressed="true">All citations</button><button type="button" data-cite-mode="you" aria-pressed="false" title="Other sites the AI cited when it linked to your product or recommended you. Your own site is left out.">Sites behind your mentions <span id="cite-you-count"></span></button></div><div class="cite-tools"><input id="cite-search" type="search" aria-label="Search citation URLs, titles or products" placeholder="Search URL, title or product…"><label>Source<select id="cite-source"><option value="">All sources</option><option>Your site</option><option>External site</option></select></label><label>Content type<select id="cite-content"><option value="">All content types</option></select></label><label>Domain<select id="cite-domain"><option value="">All domains</option></select></label><label>Product link<select id="cite-relation"><option value="">All citations</option><option>Your product page</option><option>Other listing of your product</option><option>Other source</option></select></label><button type="button" id="cite-clear">Clear</button><button type="button" id="cite-export">↓ Export CSV</button></div>
<div id="cite-you-list" hidden></div><div id="cite-all-view"><p class="cite-table-note">One source URL per answer. Content types are inferred from URLs and saved product matches. Source order is the link’s order in the saved source list, not a product ranking.</p>
<div class="cite-table-scroll"><table class="cite-table"><thead><tr><th>URL / product</th><th>Source</th><th>Type <span title="Inferred from the URL and saved product matches; unclassified when unclear.">ⓘ</span></th><th>Model</th><th id="cite-order-head" aria-sort="none"><button type="button" data-cite-sort="order">Source order ↕</button></th><th id="cite-date-head" aria-sort="descending"><button type="button" data-cite-sort="date">Date ↕</button></th><th>Evidence</th></tr></thead><tbody id="cite-rows"></tbody></table></div><div class="cite-pagination"><span id="cite-count" role="status"></span><div><button type="button" id="cite-prev" aria-label="Previous citation page">←</button><span id="cite-page"></span><button type="button" id="cite-next" aria-label="Next citation page">→</button></div></div></div></section>
<script type="application/json" id="cite-config">%s</script>'''%payload+SCRIPT


SCRIPT = r'''<script>(()=>{
const cfg=JSON.parse(document.getElementById('cite-config').textContent),$=id=>document.getElementById(id),escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colors=['#20b6d2','#81868d','#f59e0b','#ef4565','#34b77e','#8476c9','#d65ab1'];let first=0,page=0,sort='date',direction=-1,view='time',filtered=[],groups=[],pinned=null;
let domainCount=7;try{const saved=Number(localStorage.getItem('produkto-citation-domains'));if([7,14,21,28,100000].includes(saved))domainCount=saved;}catch(e){}
const countButton=$('cite-count-button'),countMenu=$('cite-count-menu');
function closeCountMenu(){countMenu.hidden=true;countButton.setAttribute('aria-expanded','false');}
countButton.onclick=()=>{countMenu.hidden=!countMenu.hidden;countButton.setAttribute('aria-expanded',String(!countMenu.hidden));if(!countMenu.hidden)countMenu.querySelector('input:checked').focus();};
countMenu.querySelectorAll('input').forEach(input=>{input.checked=Number(input.value)===domainCount;input.onchange=()=>{domainCount=Number(input.value);try{localStorage.setItem('produkto-citation-domains',String(domainCount));}catch(e){}pinned=null;shareList();chart();closeCountMenu();countButton.focus();};});
document.addEventListener('click',e=>{if(!e.target.closest('.cite-count-control'))closeCountMenu();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!countMenu.hidden){closeCountMenu();countButton.focus();}});
for(const [id,field] of [['cite-domain','domain'],['cite-content','content']]){[...new Set(cfg.rows.map(r=>r[field]))].sort().forEach(v=>$(id).add(new Option(v,v)));}
function icon(domain){return `<span class="cite-site-icon"><span>${escape(domain[0].toUpperCase())}</span><img src="/icon?d=${encodeURIComponent(domain)}" alt="" loading="lazy" onerror="this.hidden=true"></span>`;}
function evidenceLink(r){const u=new URL('/r/'+cfg.token+'/answers',location.origin);for(const k of ['range','group','from','to','engines','product']){const v=new URL(location.href).searchParams.get(k);if(v)u.searchParams.set(k,v);}u.searchParams.set('answer',r.answer);u.hash='answer-'+r.answer;return u.pathname+u.search+u.hash;}
function summarize(){const map=new Map();filtered.forEach(r=>{if(!map.has(r.domain))map.set(r.domain,{domain:r.domain,count:0,buckets:{},own:r.own});const g=map.get(r.domain);g.count++;g.buckets[r.bucket]=(g.buckets[r.bucket]||0)+1;});groups=[...map.values()].sort((a,b)=>b.count-a.count||a.domain.localeCompare(b.domain));groups.forEach((g,i)=>g.color=g.own?'#0b1b35':colors[i%colors.length]);}
function focusDomain(domain){document.querySelectorAll('[data-domain-series]').forEach(el=>el.style.opacity=!domain||el.dataset.domainSeries===domain?'1':'.14');}
function cohort(){return [...groups.filter(g=>g.own),...groups.filter(g=>!g.own)].slice(0,domainCount);}
function shareList(){const measured=cfg.buckets.filter(b=>b.measured),last=measured.at(-1),prev=measured.at(-2),totals={};filtered.forEach(r=>totals[r.bucket]=(totals[r.bucket]||0)+1);$('cite-share-list').innerHTML=cohort().map(g=>{let change='';if(last&&prev&&totals[last.id]&&totals[prev.id]){const delta=100*(g.buckets[last.id]||0)/totals[last.id]-100*(g.buckets[prev.id]||0)/totals[prev.id];change=`<small class="cite-delta ${delta>0?'up':delta<0?'down':''}" title="Change in this share of citations since the previous measured period">${delta>0?'+':''}${delta.toFixed(1)}%</small>`;}return `<button type="button" class="cite-share-row" data-domain="${escape(g.domain)}" aria-pressed="${pinned===g.domain}"><i style="background:${g.color}"></i>${icon(g.domain)}<span class="cite-domain-name">${escape(g.domain)}${g.own?'<small>Your site</small>':''}</span><span class="cite-share-numbers">${change}<b>${(100*g.count/filtered.length).toFixed(1)}%</b><small>${g.count.toLocaleString()} citations</small></span></button>`;}).join('')||'<p class="cite-empty">No matching citations</p>';
syncWindow(true);$('cite-share-list').querySelectorAll('button').forEach(b=>{b.onmouseenter=()=>focusDomain(b.dataset.domain);b.onmouseleave=()=>focusDomain(pinned);b.onclick=()=>{pinned=pinned===b.dataset.domain?null:b.dataset.domain;shareList();focusDomain(pinned);};});}
function syncWindow(reset){const list=$('cite-share-list'),rows=[...list.querySelectorAll('.cite-share-row')];if(reset){list.scrollTop=0;first=0;}else{const i=rows.findIndex(r=>r.offsetTop+r.offsetHeight/2>=list.scrollTop);first=Math.max(0,Math.min(i<0?0:i,rows.length-7));}
$('cite-scroll-status').textContent=rows.length>7?'Chart shows '+(first+1)+'–'+Math.min(first+7,rows.length)+' of '+rows.length+' domains · scroll to compare':'';}
let scrollFrame;$('cite-share-list').addEventListener('scroll',()=>{cancelAnimationFrame(scrollFrame);scrollFrame=requestAnimationFrame(()=>{const was=first;syncWindow(false);if(first!==was)chart();});});
function chart(){const top=cohort().slice(first,first+7),buckets=cfg.buckets,W=Math.max(view==='top'?700:340,$('cite-chart').clientWidth-28),H=300,L=46,R=W-25,T=20,B=250;let svg='';const peak=Math.max(1,...top.flatMap(g=>view==='top'?[g.count]:buckets.filter(b=>b.measured).map(b=>g.buckets[b.id]||0))),step=Math.max(1,Math.ceil(peak/4)),max=step*4,x=i=>buckets.length===1?(L+R)/2:L+(R-L)*i/(buckets.length-1),y=n=>B-(B-T)*n/max;
for(let v=0;v<=max;v+=step)svg+=`<line x1="${L}" x2="${R}" y1="${y(v)}" y2="${y(v)}" stroke="#dde5ef" stroke-dasharray="3 4"/><text x="${L-10}" y="${y(v)+4}" text-anchor="end">${v}</text>`;
document.querySelector('.cite-plot .cite-caption').textContent=(view==='time'?'Citations per measured period':'Total citations in the selected period')+' · your site and leading cited domains';
if(!top.length)svg+=`<text x="${W/2}" y="135" text-anchor="middle">No citations match these filters</text>`;
if(view==='time'){top.forEach(g=>{let prev=null,marks='',points=buckets.filter(b=>b.measured).length;buckets.forEach((b,i)=>{if(!b.measured)return;const n=g.buckets[b.id]||0;if(prev!==null)marks+=`<line x1="${x(prev)}" y1="${y(g.buckets[buckets[prev].id]||0)}" x2="${x(i)}" y2="${y(n)}" stroke="${g.color}" stroke-width="2" ${i-prev>1?'stroke-dasharray="5 5"':''}/>`;marks+=`<circle cx="${x(i)}" cy="${y(n)}" r="${points===1?4:0}" fill="${g.color}"/>`;prev=i;});svg+=`<g data-domain-series="${escape(g.domain)}">${marks}</g>`;});const every=Math.max(1,Math.ceil(buckets.length/6));buckets.forEach((b,i)=>{if(i%every===0||i===buckets.length-1)svg+=`<text x="${x(i)}" y="277" text-anchor="middle">${escape(b.label)}</text>`;const slot=buckets.length===1?R-L:(R-L)/(buckets.length-1);svg+=`<rect data-bucket="${i}" x="${Math.max(L,x(i)-slot/2)}" y="${T}" width="${Math.min(R,x(i)+slot/2)-Math.max(L,x(i)-slot/2)}" height="${B-T}" fill="transparent" tabindex="0" role="button" aria-label="${escape(b.long)}${b.measured?' — show citation counts':' — no scan'}"/>`;});}
else{const slot=(R-L)/Math.max(1,top.length);top.forEach((g,i)=>{const cx=L+slot*(i+.5);svg+=`<g data-domain-series="${escape(g.domain)}"><rect x="${cx-slot*.3}" y="${y(g.count)}" width="${slot*.6}" height="${B-y(g.count)}" rx="3" fill="${g.color}"/><text x="${cx}" y="${y(g.count)-7}" text-anchor="middle">${g.count}</text><image href="/icon?d=${encodeURIComponent(g.domain)}" x="${cx-9}" y="259" width="18" height="18" preserveAspectRatio="xMidYMid meet" onerror="this.remove()"/><text x="${cx}" y="291" text-anchor="middle">${escape(g.domain.length>16?g.domain.slice(0,13)+'…':g.domain)}</text><rect data-top="${i}" x="${L+slot*i}" y="0" width="${slot}" height="300" fill="transparent" tabindex="0" role="button" aria-label="${escape(g.domain)}: ${g.count} citations"/></g>`;});}
if(view==='time')svg+='<g id="cite-hover" pointer-events="none"></g>';
$('cite-chart').innerHTML=`<svg style="min-width:${view==='top'?700:0}px" viewBox="0 0 ${W} ${H}" role="img" aria-label="${view==='time'?'Citation counts over time':'Top domains by citation count'}">${svg}</svg>`;
const tip=$('cite-chart-tip');function show(mark,event){const i=Number(mark.dataset.bucket??mark.dataset.top),b=buckets[i],data=view==='time'?top.map(g=>({g,n:b.measured?g.buckets[b.id]||0:null})):[{g:top[i],n:top[i].count}];if(view==='top'){const g=top[i];focusDomain(g.domain);document.querySelectorAll('.cite-share-row').forEach(r=>r.classList.toggle('hot',r.dataset.domain===g.domain));tip.innerHTML=`<b>${escape(g.domain)}${g.own?' · Your site':''}</b><span><i style="background:${g.color}"></i>Citations<strong>${g.count.toLocaleString()}</strong></span><span><i style="background:transparent"></i>Share of all citations<strong>${(100*g.count/filtered.length).toFixed(1)}%</strong></span><span><i style="background:transparent"></i>Rank<strong>#${groups.indexOf(g)+1}</strong></span>`;}else tip.innerHTML=`<b>${escape(b.long)}</b>`+data.map(({g,n})=>`<span><i style="background:${g.color}"></i>${escape(g.domain)}<strong>${n===null?'No scan':n}</strong></span>`).join('');const hov=$('cite-hover');if(hov)hov.innerHTML=view==='time'&&b.measured?`<line x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${B}" stroke="#9aa6b8" stroke-width="1" stroke-dasharray="3 3"/>`+top.map(g=>`<circle cx="${x(i)}" cy="${y(g.buckets[b.id]||0)}" r="4.5" fill="${g.color}" stroke="#fff" stroke-width="2"/>`).join(''):'';tip.hidden=false;const parent=$('cite-chart').getBoundingClientRect(),box=mark.getBoundingClientRect(),px=event?.clientX??box.x+box.width/2,py=event?.clientY??box.y+30;tip.style.left=Math.max(8,Math.min(parent.width-tip.offsetWidth-8,px-parent.left+16))+'px';tip.style.top=(view==='top'?Math.max(8,py-parent.top-tip.offsetHeight-14):Math.max(70,Math.min(240,py-parent.top+70)))+'px';}
$('cite-chart').querySelectorAll('[data-bucket],[data-top]').forEach(mark=>{mark.onpointermove=e=>show(mark,e);mark.onfocus=()=>show(mark);const off=()=>{tip.hidden=true;const h=$('cite-hover');if(h)h.innerHTML='';if(view==='top'){focusDomain(pinned);document.querySelectorAll('.cite-share-row.hot').forEach(r=>r.classList.remove('hot'));}};mark.onpointerleave=off;mark.onblur=off;mark.onclick=e=>show(mark,e);});
$('cite-chart-data').innerHTML='<table><thead><tr><th>Period</th>'+top.map(g=>'<th>'+escape(g.domain)+'</th>').join('')+'</tr></thead><tbody>'+buckets.map(b=>'<tr><td>'+escape(b.long)+'</td>'+top.map(g=>'<td>'+(b.measured?g.buckets[b.id]||0:'No scan')+'</td>').join('')+'</tr>').join('')+'</tbody></table>';focusDomain(pinned);}
function table(){const sorted=[...filtered].sort((a,b)=>direction*((sort==='date'?a.timestamp-b.timestamp:a.order-b.order)||a.answer-b.answer)||a.url.localeCompare(b.url));page=Math.max(0,Math.min(page,Math.ceil(sorted.length/25)-1));const start=page*25,slice=sorted.slice(start,start+25);$('cite-rows').innerHTML=slice.map(r=>`<tr><td><div class="cite-url-cell">${icon(r.domain)}<div><a class="cite-title" href="${escape(r.url)}" target="_blank" rel="noopener noreferrer">${escape(r.title)}</a><a class="cite-url" href="${escape(r.url)}" target="_blank" rel="noopener noreferrer">${escape(r.url)}</a>${r.products.length?'<span class="cite-products">'+escape(r.products.join(' · '))+'</span>':''}${r.relation!=='Other source'?'<span class="cite-relation">'+escape(r.relation)+'</span>':''}</div></div></td><td><span class="cite-pill ${r.own?'own':''}">${escape(r.source)}</span></td><td><span class="cite-pill type-${r.content.toLowerCase()}" title="Inferred from URL and saved product matches">${escape(r.content)}</span></td><td><span class="ans-engine cite-model">${cfg.logos[r.engine]||''}${escape(r.model)}</span></td><td class="cite-order">#${r.order}</td><td class="cite-date">${escape(r.date)}</td><td><a class="cite-answer" href="${escape(evidenceLink(r))}" title="${escape(r.prompt)}">View answer ↗</a></td></tr>`).join('')||'<tr><td colspan="7" class="cite-empty">No citations match these filters. Try another domain or clear the filters.</td></tr>';$('cite-count').textContent=sorted.length?`Showing ${start+1}–${Math.min(start+25,sorted.length)} of ${sorted.length.toLocaleString()} citations`:'0 citations';$('cite-page').textContent=`${page+1} / ${Math.max(1,Math.ceil(sorted.length/25))}`;$('cite-prev').disabled=page===0;$('cite-next').disabled=start+25>=sorted.length;$('cite-export').disabled=!sorted.length;}
function youList(){const map=new Map();filtered.filter(r=>r.about&&!r.own).forEach(r=>{if(!map.has(r.url))map.set(r.url,{r,n:0,links:false,answers:new Set()});const g=map.get(r.url);g.n++;g.answers.add(r.answer);if(r.about==='Links to your product')g.links=true;});const list=[...map.values()].sort((a,b)=>(b.links-a.links)||b.n-a.n);
$('cite-you-count').textContent=list.length?'('+list.length+')':'';const nLinks=list.filter(g=>g.links).length,nCites=list.reduce((t,g)=>t+g.n,0);$('cite-you-list').innerHTML=list.length?`<div class="you-stats"><div><b>${list.length}</b><span>sites behind your mentions</span></div><div class="links"><b>${nLinks}</b><span>link straight to your product</span></div><div><b>${list.length-nLinks}</b><span>backed an answer that recommended you</span></div><div><b>${nCites}</b><span>citations in total</span></div></div><p class="cite-table-note">Other sites the AI cited when it linked to your product or recommended you. Your own site is left out.</p>`+'<div class="cite-table-scroll"><table class="cite-table cite-you-table"><thead><tr><th>Site / URL</th><th>Why it counts</th><th>Times cited</th><th>Evidence</th></tr></thead><tbody>'+list.slice(0,youShown).map(({r,n,links})=>`<tr data-url="${escape(r.url)}"><td><div class="cite-url-cell">${icon(r.domain)}<div><a class="cite-title" href="${escape(r.url)}" target="_blank" rel="noopener noreferrer">${escape(r.title)}</a><span class="dead-slot"></span><a class="cite-url" href="${escape(r.url)}" target="_blank" rel="noopener noreferrer">${escape(r.url)}</a></div></div></td><td><span class="you-pill ${links?'links':'backed'}">${links?'↗ Links to your product':'✓ Cited when recommended'}</span></td><td><span class="you-count">${n}×</span></td><td><a class="cite-answer" href="${escape(evidenceLink(r))}" title="${escape(r.prompt)}">View answer ↗</a></td></tr>`).join('')+'</tbody></table></div>'+(list.length>youShown?`<button type="button" class="cite-you-more" id="cite-you-more">Show all ${list.length} sites</button>`:''):'<p class="cite-empty">No other site was cited alongside a recommendation of your product in this period.</p>';
const more=$('cite-you-more');if(more)more.onclick=()=>{youShown=1e9;youList();};markDead(list.slice(0,youShown).map(g=>g.r.url));}
const linkState={};
function paintDead(){document.querySelectorAll('#cite-you-list tr[data-url]').forEach(tr=>{const s=linkState[tr.dataset.url];tr.classList.toggle('is-dead',s==='dead');const slot=tr.querySelector('.dead-slot');if(slot)slot.innerHTML=s==='dead'?'<span class="dead-pill" title="This page returned \u201cpage not found\u201d when Produkto checked it. AI is sending buyers to a broken link.">⚠ Page not found</span>':'';});}
async function markDead(urls){const need=urls.filter(u=>!(u in linkState));paintDead();if(!need.length)return;need.forEach(u=>linkState[u]='pending');try{const r=await fetch('/api/linkcheck',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'urls='+encodeURIComponent(need.join('\n'))});const j=await r.json();Object.assign(linkState,j);}catch(e){need.forEach(u=>delete linkState[u]);}paintDead();}
let youShown=25;
document.querySelectorAll('[data-cite-mode]').forEach(b=>b.onclick=()=>{const you=b.dataset.citeMode==='you';document.querySelectorAll('[data-cite-mode]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));$('cite-you-list').hidden=!you;$('cite-all-view').hidden=you;});
function update(){const search=$('cite-search').value.trim().toLowerCase();filtered=cfg.rows.filter(r=>(!search||[r.url,r.title,...r.products].join(' ').toLowerCase().includes(search))&&[['cite-source','source'],['cite-content','content'],['cite-domain','domain'],['cite-relation','relation']].every(([id,k])=>!$(id).value||$(id).value===r[k]));page=0;pinned=null;summarize();shareList();chart();table();youList();}
['cite-source','cite-content','cite-domain','cite-relation'].forEach(id=>$(id).onchange=update);let timer;$('cite-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(update,120);};$('cite-clear').onclick=()=>{['cite-search','cite-source','cite-content','cite-domain','cite-relation'].forEach(id=>$(id).value='');update();};$('cite-prev').onclick=()=>{page--;table();};$('cite-next').onclick=()=>{page++;table();};document.querySelectorAll('[data-cite-sort]').forEach(b=>b.onclick=()=>{const field=b.dataset.citeSort;direction=sort===field?-direction:field==='date'?-1:1;sort=field;page=0;['date','order'].forEach(k=>$('cite-'+k+'-head').setAttribute('aria-sort',k===sort?direction===1?'ascending':'descending':'none'));table();});document.querySelectorAll('[data-cite-view]').forEach(b=>b.onclick=()=>{view=b.dataset.citeView;document.querySelectorAll('[data-cite-view]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));$('cite-chart-tip').hidden=true;chart();});
$('cite-export').onclick=()=>{const cell=v=>'"'+String(v??'').replace(/^[=+@\-\t\r]/,"'$&").replace(/"/g,'""')+'"';const header=['URL','Title','Domain','Source','Content type (inferred)','Product relationship','Products','Model','Source order','Date','Answer ID','Buyer question'];const lines=[header,...filtered.map(r=>[r.url,r.title,r.domain,r.source,r.content,r.relation,r.products.join('; '),r.model,r.order,r.date,r.answer,r.prompt])];const url=URL.createObjectURL(new Blob(['\ufeff'+lines.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='produkto-citations.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};update();
let resizing;window.addEventListener('resize',()=>{clearTimeout(resizing);resizing=setTimeout(chart,100);});
})();</script>'''
