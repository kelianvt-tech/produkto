"""Read-only presentation of saved scans. No model calls or database writes."""
import html
import json
import math
import re
import time
from collections import defaultdict
from urllib.parse import urlsplit

import config
import db
import engines
import evidence
import scheduler
import storetime
import waitlist
from urllib.parse import parse_qsl, urlencode
from text import norm

E = html.escape


def safe_url(value):
    try:
        u = urlsplit(value or '')
        return value if u.scheme in ('http', 'https') and u.netloc else ''
    except ValueError:
        return ''


def inline(text):
    # Escape first; only our own tags and validated links may become HTML.
    parts = re.split(r'(\[[^\]\n]+\]\(https?://[^\s]+?\))', text)
    out = []
    for part in parts:
        m = re.fullmatch(r'\[([^\]\n]+)\]\((https?://[^\s]+)\)', part)
        if m and safe_url(m[2]):
            out.append('<a href="%s" target="_blank" rel="noopener noreferrer">%s ↗</a>' % (E(m[2]), E(m[1])))
        else:
            s = E(part)
            s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
            s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
            # Drop the backslashes markdown uses to escape punctuation, or the
            # citation markers ChatGPT writes come out as "\[1\]" on screen.
            # Last, so an escaped \*\* is not read as bold on the way past.
            s = re.sub(r'\\([\\`*_{}\[\]()#+\-.!])', r'\1', s)
            out.append(s)
    return ''.join(out)


def readable(text):
    out, para, list_kind = [], [], None
    def flush():
        if para:
            out.append('<p>' + inline(' '.join(para)) + '</p>')
            para.clear()
    for line in text.splitlines():
        line = line.strip()
        bullet = re.match(r'^(?:[-*]|\d+\.)\s+(.+)', line)
        heading = re.match(r'^#{1,6}\s+(.+)', line)
        if not bullet and list_kind:
            out.append('</%s>' % list_kind)
            list_kind = None
        if bullet:
            flush()
            kind = 'ol' if line[0].isdigit() else 'ul'
            if kind != list_kind:
                if list_kind:
                    out.append('</%s>' % list_kind)
                out.append('<%s>' % kind)
                list_kind = kind
            out.append('<li>' + inline(bullet[1]) + '</li>')
        elif heading:
            flush()
            out.append('<h3>' + inline(heading[1]) + '</h3>')
        elif not line:
            flush()
        else:
            para.append(line)
    flush()
    if list_kind:
        out.append('</%s>' % list_kind)
    return ''.join(out)


_AIO_JUNK = re.compile(r'Go to product viewer dialog for this item\.?|Show more|Show less')
# A shopping-card fragment glued into the scraped text:
# "CeraVe Hydrating Cream-to-Foam Cleanser$15.49SkinTypeSolutions.com& more4.7(16.1K)"
_AIO_CARD = re.compile(r'[^.?!]{0,160}?[$£€]\d[\d.,]*(?:[$£€]\d[\d.,]*)?.{0,90}?\d\.\d\([\d.,]+K?\)')


def overview_text(text):
    """Google's AI Overview comes back from the scraper with its shopping cards
    flattened into the prose. The cards are shown as real cards above, so drop
    them here, re-space the sentences, drop the repeat after "Show more", and
    break the rest into short paragraphs."""
    t = _AIO_CARD.sub('. ', _AIO_JUNK.sub(' ', text or ''))
    t = re.sub(r'([A-Za-z0-9)\]%])([.?!:])(?=[A-Z](?:[a-z]|\s))', r'\1\2 ', t)
    sentences, seen = [], set()
    for sent in re.split(r'(?<=[.?!])\s+', t):
        sent = sent.strip(' .')
        key = re.sub(r'\W+', '', sent.lower())
        if len(key) < 12 or key in seen:
            continue
        seen.add(key)
        sentences.append(sent + ('' if sent[-1:] in '?!:' else '.'))
    paras = [' '.join(sentences[i:i + 3]) for i in range(0, len(sentences), 3)]
    return '\n\n'.join(paras)


def _card_thumb(html_):
    """/pimg falls back to the brand's logo when no product photo is known yet.
    A logo is small (a favicon, 256px or less): show it small and centred rather
    than stretched across the card."""
    return html_.replace('onerror="this.hidden=true"',
        'onload="if(this.naturalWidth&&this.naturalWidth<=256)this.classList.add(\'brand-mark\')" '
        'onerror="this.hidden=true"')


def product_cards(ms, p, panels, cls='prod-cards'):
    """The products an answer recommended, as cards with a photo, the way the
    engine shows them to a buyer. Own products are marked; order is position."""
    cards, seen = [], set()
    for m in sorted(ms, key=lambda m: m['rank'] or 999):
        if not ((m['brand'] or '').strip() or (m['url'] or '').strip() or m['matched_product_id'] is not None):
            continue
        product = next((c for c in p['_catalog'] if c['id'] == m['matched_product_id']), None)
        name = product['title'] if product else (m['product_name'] or m['brand'] or '')
        brand = product['vendor'] if product else (m['brand'] or '')
        key = ('c', product['id']) if product else (norm(brand), norm(name))
        if key in seen:
            continue
        seen.add(key)
        mine = evidence.own(m, p)
        row = dict(name=name, brand=brand, url=m['url'] or '', own=mine,
                   image=product.get('image', '') if product else '')
        price = (m['price'] if 'price' in m.keys() else '') or ''
        link = safe_url(m['url'])
        tag = 'a' if link else 'div'
        href = ' href="%s" target="_blank" rel="noopener noreferrer"' % E(link) if link else ''
        cards.append(
            '<%s class="prod-card%s"%s><span class="prod-img">%s</span>'
            '<span class="prod-rank">#%s</span>%s'
            '<b class="prod-name">%s</b><span class="prod-brand">%s</span>%s</%s>'
            % (tag, ' mine' if mine else '', href, _card_thumb(panels.thumb(row, p)), m['rank'] or '–',
               '<span class="prod-own">Your product</span>' if mine
               else '<span class="prod-own brand">Your brand</span>' if m['is_their_brand'] else '',
               E(name), E(brand or 'Brand unavailable'),
               '<span class="prod-price">%s</span>' % E(price) if price else '', tag))
    return '<div class="%s">%s</div>' % (cls, ''.join(cards)) if cards else ''


def date(ts):
    return time.strftime('%d %b %Y, %H:%M', time.localtime(ts or 0))


def context(token, query=None):
    s=db.one('SELECT * FROM scans WHERE token=?',(token,))
    if not s:
        return None
    ps=db.one('SELECT * FROM prompt_sets WHERE id=?',(s['prompt_set_id'],))
    if not ps:
        return None
    selected=(query or {}).get('product')
    if selected and not selected.isdigit():
        return None
    selected=int(selected) if selected else ps['legacy_product_id']
    p=evidence.product_context(ps,selected)
    return (s,ps,p) if p else None


def scope_links(body, query, p):
    keep={k:v for k,v in (query or {}).items() if k in ('range','group','from','to','engines')}
    def link(match):
        u=urlsplit(html.unescape(match[1]))
        params=dict(parse_qsl(u.query,keep_blank_values=True))
        for k,v in keep.items():
            params.setdefault(k,v)
        if 'product' not in params and p['id'] is not None:
            params['product']=str(p['id'])
        if params.get('product')=='':
            params.pop('product')
        return 'href="'+E(u.path+('?' + urlencode(params) if params else '')+('#'+u.fragment if u.fragment else ''))+'"'
    return re.sub(r'href="(/r/[^"<>]*)"',link,body)


def freshness(p):
    """One line saying how old the number on screen is.

    A merchant opening this at 8am wants to know whether they are looking at
    this morning's reading or Tuesday's, and a gap in a chart does not tell
    them that. Times are the merchant's own, because "06:12" means nothing
    unless you know whose clock it is on.
    """
    domain = p.get('store_domain') or ''
    if not domain:
        return ''
    tz = storetime.zone(domain)
    last = scheduler.last_scan_at(domain)
    today = storetime.today(tz)
    zone = E(storetime.abbrev(tz))
    if not last:
        return ('<p class="freshness"><span class="fresh-dot fresh-none"></span>'
                'No scan yet</p>')
    when = E(storetime.label(last, tz, '%-d %b, %H:%M'))
    fresh = storetime.date_of(last, tz) == today
    if fresh:
        dot, text = 'fresh-ok', 'Updated today'
    else:
        days = (today - storetime.date_of(last, tz)).days
        dot = 'fresh-stale' if days > 1 else 'fresh-old'
        text = 'Last updated %s' % ('yesterday' if days == 1 else '%d days ago' % days)
    if domain in set(config.DAILY_SCAN_EXCLUDE):
        nxt = 'daily scans off'
    else:
        slot = scheduler.slot_today(domain)
        nxt = ('next scan today at %02d:00' % scheduler.slot_hour(domain)
               if time.time() < slot else
               'next scan tomorrow at %02d:00' % scheduler.slot_hour(domain))
    return ('<p class="freshness"><span class="fresh-dot %s"></span>'
            '<b>%s</b><span>%s %s</span><span>%s</span></p>'
            % (dot, E(text), when, zone, E(nxt)))


def header(s, p, active):
    token=E(s['token']); image=safe_url(p['image'])
    # The store line always shows the store's favicon; a product page shows
    # its photo large beside the title instead (5 Oct 2026). Brand initials
    # sit underneath if the favicon fails to load.
    initials=''.join(w[0] for w in (p['vendor'] or '').split()[:2]).upper() or 'P'
    site=p['store_domain'] or ''
    mark=('<img src="/icon?d=%s" alt="" loading="lazy" onerror="this.hidden=true">'%E(site)) if site else ''
    picture='<span class="product-placeholder"><span aria-hidden="true">%s</span>%s</span>'%(E(initials),mark)
    back='<p class="small"><a href="/r/%s?product=">← Back to catalog</a></p>'%token if p['id'] is not None and not p['_ps']['legacy_product_id'] else ''
    # No manual scan button: the scheduler scans every store daily.
    action=('<a class="btn" href="/store?d=%s">Set up catalog scan</a>'%E(p['store_domain']) if p['_ps']['legacy_product_id'] else
            '' if config.DAILY_SCANS else
            '<button class="btn" id="rescan" data-store="%s">Run catalog scan</button>'%E(p['store_domain']))
    titles = {'overview': 'Catalog overview', 'questions': 'Buyer questions',
              'answers': 'AI answers', 'citations': 'Mentions & citations'}
    descriptions = {'overview': 'See where your products stand in AI recommendations.',
                    'questions': 'Understand the questions that lead buyers to your products.',
                    'answers': 'Explore the recommendations your buyers receive.',
                    'citations': 'Discover the sources behind AI recommendations.'}
    title = titles.get(active, 'Catalog overview') if p['id'] is None else p['title']
    description=E(descriptions.get(active,''))
    if p['id'] is not None:
        # A product page opens on the product's own text, clipped to one line.
        full=_strip(json.loads(p.get('raw_json') or '{}').get('body_html',''),100000)
        if full:
            description='<span class="desc-text" id="desc-text">%s</span> <button type="button" class="desc-more" onclick="var t=document.getElementById(\'desc-text\'),o=t.classList.toggle(\'open\');this.textContent=o?\'show less\':\'show more\'">show more</button>'%E(full)
    catalog=p['id'] is None
    crumb=('<span class="crumb-sep" aria-hidden="true">›</span><span class="crumb-page">%s</span>'%E(title)) if catalog else '<small>%s</small>'%E(p['store_domain'])
    head='' if catalog and not action else '''<div class="product-head">%s<div class="product-title"><h1>%s</h1><p class="page-description%s">%s</p></div>%s</div>'''%(
        # A big product photo: merchants recognise products by sight first (5 Oct 2026).
        ('<img class="product-hero" src="%s" alt="" onerror="this.remove()">'%E(image)) if image else '',
        E(title),' has-more' if 'desc-more' in description else '',description,action) if not catalog else '<div class="product-head">%s</div>'%action
    # The freshness line sits on the breadcrumb row and the period filters
    # dock beside the tabs (app.page moves them into <!--FILTERS-->), so the
    # page header is two rows instead of four.
    return back+'''<div class="workspace-context%s">%s<span><b>%s</b>%s</span>%s</div>
%s
<p id="scan-error" class="err" role="alert" hidden></p><div class="context-bar"><div class="context-row">%s</div><!--FILTERS--></div><span hidden data-rail-store="%s" data-rail-name="%s"></span>'''%(' crumbs' if catalog else '',picture,E(p['vendor'] or p['store_domain']),crumb,freshness(p),head,
        # Buyer questions is its own rail item, not a tab, so its page shows
        # no dashboard tabs (5 Oct 2026).
        '<span hidden data-rail-page="questions"></span>' if active=='questions' else
        ('<nav aria-label="Scan navigation">\n<a %s href="/r/%s">Overview</a><a %s href="/r/%s/answers">Answers</a><a %s href="/r/%s/citations">Mentions &amp; Citations</a></nav>'
         % ('aria-current="page"' if active=='overview' else '',token,
            'aria-current="page"' if active=='answers' else '',token,
            'aria-current="page"' if active=='citations' else '',token)),
        E(p.get('store_domain') or ''),E(p['vendor'] or p.get('store_domain') or ''))


def _catalog_measure(ps,product,ids,engines):
    """One catalog product over a set of scans, against every catalog question."""
    import insight_panels
    item=evidence.product_context(ps,product['id'])
    item['_engines']=engines
    item['_ps']=dict(item['_ps'],relevance=[[item['id']] for _ in item['_ps']['prompts']])
    groups=insight_panels.products(ids,item)
    own=next(r for r in groups if r['own'])
    ranks=list(own['hits'].values())
    own['win']=100*sum(1 for r in ranks if r==1)/len(ranks) if ranks else None
    return item,own,groups


def _delta(now,before,unit='pp',low_best=False,digits=1):
    """Change against the previous period, green when better."""
    if now is None or before is None:
        return ''
    d=round(now-before,digits)
    if not d:
        return '<span class="pc-d">±0</span>'
    good=(d<0) if low_best else (d>0)
    return '<span class="pc-d %s">%s%s%s</span>'%('up' if good else 'down','+' if d>0 else '−',('%.'+str(digits)+'f')%abs(d),unit)


def _strip(html_text,limit=90):
    text=re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',html_text or ''))).strip()
    return text if len(text)<=limit else text[:limit].rsplit(' ',1)[0]+'…'


CATALOG_TIPS={'name':'Your catalog products.',
    'vis':'Share of AI answers that mention this product.',
    'win':'Of the answers that mention this product, the share where it is the #1 recommendation.',
    'pos':'Average position when mentioned. #1 = named first.',
    'price':'The price AI answers quote for this product: the middle of all quotes in this period. Only answers collected since price tracking began (22 Sep 2026) are counted.',
    'sov':'This product\'s share of all product recommendations.',
    'brands':'Other brands named in the same answers as this product.',
    'prods':'Other products named in the same answers as this product.',
    'cov':'Whether this product has been measured yet.'}

CATALOG_SCRIPT='''<script>
(()=>{const search=document.getElementById('products-search'),zero=document.getElementById('products-zero'),tb=document.querySelector('.pc-table tbody');let cat='';
function filter(){let n=0;tb.querySelectorAll('tr').forEach(r=>{r.hidden=!(r.dataset.productSearch.includes(search.value.toLowerCase())&&(!cat||r.dataset.productType===cat)&&(!zero.checked||r.dataset.zero==='yes'));n+=!r.hidden;});document.getElementById('products-empty').hidden=!!n;}
search.oninput=filter;zero.onchange=filter;
document.querySelectorAll('.pc-cat').forEach(b=>b.onclick=()=>{cat=b.dataset.cat;document.querySelectorAll('.pc-cat').forEach(x=>x.setAttribute('aria-pressed',x===b));document.getElementById('pc-title').textContent=cat||'All categories';filter();});
document.querySelectorAll('.pc-sort').forEach(b=>b.onclick=()=>{const th=b.closest('th'),k=b.dataset.sort,cur=th.getAttribute('aria-sort'),asc=cur==='descending'?true:cur==='ascending'?false:(k==='name'||k==='pos');
document.querySelectorAll('.pc-table th[aria-sort]').forEach(x=>x.setAttribute('aria-sort','none'));th.setAttribute('aria-sort',asc?'ascending':'descending');
const val=r=>k==='name'?r.dataset.name:+r.dataset[k],missing=r=>k!=='name'&&(k==='pos'?+r.dataset.pos>=999:+r.dataset[k]<0);
[...tb.rows].sort((a,b)=>missing(a)-missing(b)||(k==='name'?val(a).localeCompare(val(b)):val(a)-val(b))*(asc?1:-1)).forEach(r=>tb.appendChild(r));});})();</script>'''


def _stack(items,kind,p):
    import insight_panels
    if not items:
        return '<span class="pc-none">—</span>'
    out=''
    for g in items[:3]:
        if kind=='brand':
            site=insight_panels.brand_site(g)
            initials=''.join(w[0] for w in (g['brand'] or '?').split()[:2]).upper()
            out+='<span class="pc-logo" title="%s"><span aria-hidden="true">%s</span>%s</span>'%(E(g['brand'] or ''),E(initials),('<img src="/icon?d=%s" alt="" loading="lazy" onerror="this.hidden=true">'%E(site)) if site else '')
        else:
            out+='<span class="pc-prod" title="%s">%s</span>'%(E('%s · %s'%(g['name'],g['brand'] or '')),insight_panels.thumb(g,p))
    more=len(items)-3
    return '<span class="pc-stack">%s%s</span>'%(out,'<span class="pc-more">+%d</span>'%more if more>0 else '')


def catalog_table(s,ps,p,ctx):
    import insight_panels, period as period_mod
    days=(ctx['b']-ctx['a']).days+1
    start=time.mktime(ctx['a'].timetuple())
    # The previous period of the same length, for the change figures.
    prev_ids=[x['id'] for x in period_mod.done_scans(ps['id'],start-days*86400,start-0.001)]
    rows=[]
    for product in p['_catalog']:
        item,own,groups=_catalog_measure(ps,product,ctx['ids'],p.get('_engines'))
        coverage=evidence.state(item)
        before=_catalog_measure(ps,product,prev_ids,p.get('_engines'))[1] if prev_ids else None
        if coverage!='Measured':
            own=dict(own,answers=0,avg=None,win=None,hits={})
            before=None
        if coverage=='Measured' and not own['answers']:
            coverage='No scans in this period' if not ctx['ids'] else 'No completed answers'
        if before is not None and not before['answers']:
            before=None
        # Rivals = products named in the same answers as this one.
        seen=set(own['hits'])
        rivals=[g for g in groups if not g['own'] and seen & set(g['hits'])]
        rivals.sort(key=lambda g:(-len(seen & set(g['hits'])),g['avg'] or 99))
        brands={}
        for g in rivals:
            brands.setdefault(norm(g['brand'] or ''),g)
        brands.pop('',None)
        rows.append(dict(item=item,own=own,before=before,coverage=coverage,rivals=rivals,brands=list(brands.values()),type=db.product_type(item)))
    rows.sort(key=lambda r:(not r['own']['answers'],-r['own']['rate'],r['item']['title']))

    # Catalog summary: wins and positions pooled across every product.
    ranks=[x for r in rows for x in r['own']['hits'].values()]
    summary=('<div class="pc-summary"><span>Win rate <b>%.0f%%</b></span><span>Position <b>#%.1f</b></span></div>'%(100*sum(1 for x in ranks if x==1)/len(ranks),sum(ranks)/len(ranks))) if ranks else ''

    counts=defaultdict(int)
    for r in rows:
        counts[r['type']]+=1
    side='<aside class="pc-side" aria-label="Categories"><h3>Categories</h3><button type="button" class="pc-cat" data-cat="" aria-pressed="true"><span>All categories</span><small>%d</small></button>'%len(rows)
    side+=''.join('<button type="button" class="pc-cat" data-cat="%s" aria-pressed="false"><span>%s</span><small>%d</small></button>'%(E(t),E(t),n) for t,n in sorted(counts.items()))+'</aside>'

    def th(label,key,tip,sort=True):
        if not sort:
            return '<th><span class="pc-th" data-tip="%s" tabindex="0">%s</span></th>'%(E(tip),label)
        return '<th aria-sort="none"><button type="button" class="pc-sort pc-th" data-sort="%s" data-tip="%s">%s<svg viewBox="0 0 10 12" aria-hidden="true"><path d="M2 4.5 5 1.5l3 3M2 7.5l3 3 3-3"/></svg></button></th>'%(key,E(tip),label)
    T=CATALOG_TIPS
    head='<tr>'+th('Products','name',T['name'])+th('Visibility','vis',T['vis'])+th('Win rate','win',T['win'])+th('Position','pos',T['pos'])+th('Mentioned price','price',T['price'])+th('Share of voice','sov',T['sov'])+th('Competing brands','',T['brands'],False)+th('Competing products','',T['prods'],False)+th('Coverage','',T['cov'],False)+'</tr>'
    body=''
    top_vis=max([r['own']['rate'] for r in rows if r['own']['answers']] or [0]) or 1
    for r in rows:
        item,own,before=r['item'],r['own'],r['before']
        m=bool(own['answers'])
        vis=own['rate'] if m else None
        price=insight_panels.mentioned_price(own.get('prices')) if m else None
        desc=_strip(json.loads(item.get('raw_json') or '{}').get('body_html',''))
        body+=('<tr data-product-search="%s" data-product-type="%s" data-zero="%s" data-name="%s" data-vis="%s" data-win="%s" data-pos="%s" data-price="%s" data-sov="%s">'
               '<td><a class="rank-product" href="/r/%s?product=%d">%s<span><b>%s</b>%s</span></a></td>'
               '<td data-label="Visibility"><span class="pc-v">%s</span>%s<span class="pc-meter"><i style="width:%.1f%%"></i></span></td>'
               '<td data-label="Win rate"><span class="pc-v%s">%s</span>%s</td>'
               '<td data-label="Position"><span class="pc-v">%s</span>%s</td>'
               '<td data-label="Mentioned price"><span class="pc-v">%s</span></td>'
               '<td data-label="Share of voice"><span class="pc-v">%s</span></td>'
               '<td data-label="Competing brands">%s</td><td data-label="Competing products">%s</td>'
               '<td data-label="Coverage"><span class="pc-cov%s"><i></i>%s</span></td></tr>')%(
            E(item['title'].lower()),E(r['type']),'yes' if m and not own['hits'] else 'no',E(item['title'].lower()),
            '%.3f'%vis if m else '-1','%.3f'%own['win'] if own['win'] is not None else '-1','%.3f'%own['avg'] if own['avg'] else '999','%.3f'%price['value'] if price else '-1','%.3f'%own['share'] if m else '-1',
            E(s['token']),item['id'],insight_panels.thumb(own,item),E(item['title']),('<small>%s</small>'%E(desc)) if desc else '',
            (('%.1f%%' if 0<vis<1 else '%.0f%%')%vis) if m else '—',_delta(vis,before['rate'] if before else None) if m else '',100*(vis or 0)/top_vis,
            (' pc-pill win-hi' if own['win']>=50 else ' pc-pill win-lo') if own['win'] is not None else '',('%.0f%%'%own['win']) if own['win'] is not None else '—',_delta(own['win'],before and before['win'],digits=0) if own['win'] is not None else '',
            ('#%.1f'%own['avg']) if own['avg'] else '—',_delta(own['avg'],before and before['avg'],'',True) if own['avg'] else '',
            E(price['text']) if price else '—',
            ('%.1f%%'%own['share']) if m else '—',
            _stack(r['brands'],'brand',p),_stack(r['rivals'],'product',p),
            '' if r['coverage']=='Measured' else ' muted',E(r['coverage']))
    top='<div class="pc-top"><h3 id="pc-title">All categories</h3><label class="pc-search"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/></svg><input type="search" id="products-search" placeholder="Search" aria-label="Search products"></label><label class="pc-zero"><input type="checkbox" id="products-zero"> No mentions</label>%s</div>'%summary
    table='<div class="pc-scroll"><table class="pc-table"><thead>'+head+'</thead><tbody>'+body+'</tbody></table></div><script>(()=>{const w=document.currentScript.previousElementSibling;const f=()=>{w.classList.toggle("no-scroll",w.scrollWidth<=w.clientWidth+1);w.classList.toggle("at-end",w.scrollLeft+w.clientWidth>=w.scrollWidth-2)};w.addEventListener("scroll",f,{passive:true});addEventListener("resize",f);f();})()</script><p id="products-empty" class="small pc-empty" hidden>No products match these filters.</p>'
    note='<p class="pc-note">%s</p>'%('Changes compare with the previous %d days.'%days if prev_ids else 'Changes appear once there is an earlier period to compare with.')
    return '<section class="insight-card catalog-results-card pc"><div class="insight-heading"><h2>Your products</h2></div><div class="pc-layout">'+side+'<div class="pc-main">'+top+table+note+'</div></div></section>'+CATALOG_SCRIPT


def panel(title, subtitle, content, cls=''):
    return '<section class="panel %s"><div class="panel-head"><h2>%s</h2><p>%s</p></div><div class="panel-body">%s</div></section>' % (cls, title, subtitle, content)


def brand_rows(s, p):
    answers = db.all_('SELECT id FROM answers WHERE scan_id=?', (s['id'],))
    ms = db.all_('SELECT m.* FROM mentions m JOIN answers a ON a.id=m.answer_id WHERE a.scan_id=?', (s['id'],))
    hits, labels = defaultdict(dict), {}
    for m in ms:
        key = '__own__' if m['is_their_brand'] else norm(m['brand'])
        if not key:
            continue
        labels[key] = (p['vendor'] or p['store_domain']) if key == '__own__' else m['brand']
        hits[key][m['answer_id']] = min(hits[key].get(m['answer_id'], 999), m['rank'])
    labels['__own__'] = p['vendor'] or p['store_domain']
    hits.setdefault('__own__', {})
    rows = [(k, labels[k], 100 * len(v) / len(answers) if answers else 0, sum(v.values()) / len(v) if v else None) for k, v in hits.items()]
    rows.sort(key=lambda r: (-r[2], r[3] or 999, r[1]))
    return ''.join('<tr class="%s"><td>%s%s</td><td class="num">%.1f%%</td><td class="num">%s</td></tr>' % (
        ('you' if k == '__own__' else '') + (' extra-brand' if index >= 8 and k != '__own__' else ''), E(label), ' <span class="own-label">Your brand</span>' if k == '__own__' else '', rate,
        '%.1f' % rank if rank else 'Not named') for index, (k, label, rate, rank) in enumerate(rows))


def overview(s, ps, p, sc, query=None):
    d = json.loads(sc['detail'] or '{}')
    body = header(s, p, 'overview')
    import insight_panels
    ctx = insight_panels.period_context(ps, p, query or {})
    body += insight_panels.render(s, ps, p, sc, ctx)
    own = ctx['own']
    body += '<div class="dash-foot"><div id="citations" class="citation-shortcut"><a href="/r/'+E(s['token'])+'/citations">Explore product mentions &amp; citations →</a></div>'
    # The note about how the questions are written now sits on their own tab.
    body += '<details class="measurement"><summary>Measurement details</summary>'
    body += '<p>Visibility is the share of answers that mention your product; position does not change it. Average position is shown separately (1 = named first). Share of voice measures your share of all recommendations. Brand presence includes any product from that brand.</p>'
    if own['answers']:
        body += '<p>Measurement sensitivity: about ±%d percentage points. This is a noise guide, not a confidence interval.</p>' % round(300/own['answers'])
    if s['error']:
        body += '<p>'+E(s['error'])+'</p>'
    if d.get('borderline'):
        body += '<p>Some brand mentions were close but did not clearly match your product. Review them on the Answers page.</p>'
    body += '</details></div>'
    if p['id'] is None:
        body=re.sub(r'\bYour product\b','Your catalog',body)
        body=re.sub(r'\byour product\b','your catalog',body)
    return scope_links(body + SCRIPT,query or {},p)



# Thresholds for the buyer-question dial. Grey means the catalog was never
# named for that question; the colour band then reads low / middling / strong.
# Four steps, light like PromptWatch's rings, each with a pale track in its own
# hue rather than a neutral grey one - that tinted track is most of what makes
# them read light instead of heavy. (limit, ring, track)
#
# These are the same values as the --up-mark / --down-mark / --signal-mark
# tokens in dashboard.css, which is where the rest of the dashboard's status
# colours live. They are written out rather than referenced because these go
# into an SVG `stroke`, and the ring is also drawn into standalone previews
# that do not load the stylesheet. Change them together.
GAUGE_BANDS = ((30, '#fb7185', '#ffe4e6'),     # rose   - rarely recommended
               (45, '#fb923c', '#ffedd5'),     # orange
               (80, '#fbbf24', '#fef3c7'),     # amber
               (101, '#10b981', '#d1fae5'))    # emerald - usually recommended


def gauge(pct):
    """A small ring that fills with the percentage, with the figure beside it."""
    circumference = 2 * math.pi * 8
    ring, tint = next((c, t) for limit, c, t in GAUGE_BANDS if pct < limit)
    # At 0% there is nothing to colour, so the track stays neutral; tinting it
    # rose would read as a low score rather than as no score.
    track = '<circle cx="10" cy="10" r="8" fill="none" stroke="%s" stroke-width="2.5"/>' % (
        tint if pct > 0 else '#e6eaf1')
    arc = ''
    if pct > 0:
        drawn = circumference * min(pct, 100) / 100
        arc = ('<circle cx="10" cy="10" r="8" fill="none" stroke="%s" stroke-width="2.5"'
               ' stroke-linecap="round" stroke-dasharray="%.2f %.2f"'
               ' transform="rotate(-90 10 10)"/>') % (ring, drawn, circumference - drawn)
    return ('<span class="gauge"><svg viewBox="0 0 20 20" aria-hidden="true">%s%s</svg>'
            '<b>%.0f%%</b></span>') % (track, arc, pct)



def answer_figures(a, ms, p):
    """Share, best position and own-citation ratio for a single answer.

    Share is your products over every product the answer named, which is the
    product-level reading of "how much of this answer was you". A brand-level
    tool can only say yes or no here.
    """
    import concentration
    countable = [m for m in ms if (m['brand'] or '').strip() or (m['url'] or '').strip()
                 or m['matched_product_id'] is not None]
    mine = [m for m in countable if evidence.own(m, p)]
    share = (100.0 * len(mine) / len(countable)) if countable else None
    position = min((m['rank'] for m in mine), default=None)
    own_site = (p['store_domain'] or '').lower()
    urls, own_urls = set(), set()
    for c in json.loads(a['citations'] or '[]'):
        if not isinstance(c, dict) or not safe_url(c.get('url')):
            continue
        urls.add(c['url'])
        host = concentration.domain(c['url'])
        if own_site and (host == own_site or host.endswith('.' + own_site)):
            own_urls.add(c['url'])
    return dict(share=share, position=position, cites=len(urls), own_cites=len(own_urls))


def snippet(text, limit=150):
    """The opening of an answer, with list and heading marks taken off."""
    flat = re.sub(r'\s+', ' ', re.sub(r'[#*`>\-]{1,}', ' ', text or '')).strip()
    return (flat[:limit].rstrip() + '\u2026') if len(flat) > limit else flat


def question_brands(prompt, mentions, by_answer, p, insight_panels):
    """Brands recommended for one buyer question, most-mentioned first."""
    return brand_chips([m for m in mentions if by_answer.get(m['answer_id']) == prompt],
                       p, insight_panels)


def brand_chips(mentions, p, insight_panels, limit=4):
    """Overlapping brand marks for a group of mentions, most-mentioned first.

    Built from saved mentions, so a logo here always corresponds to a real
    recommendation in a real answer. Generic advice with neither a brand nor a
    link is not a product and never becomes a chip.
    """
    groups = {}
    for m in mentions:
        if not ((m['brand'] or '').strip() or (m['url'] or '').strip()
                or m['matched_product_id'] is not None):
            continue
        mine = evidence.own(m, p)
        label = (p['vendor'] or p['store_domain']) if mine else insight_panels.display_brand(m['brand'])
        key = '__mine__' if mine else norm(label)
        if not key:
            continue
        g = groups.setdefault(key, dict(label=label, mine=mine, count=0, url=m['url'] or ''))
        g['count'] += 1
        g['url'] = g['url'] or (m['url'] or '')
    order = sorted(groups.values(), key=lambda g: (not g['mine'], -g['count'], g['label']))
    if not order:
        return '<span class="brand-none">\u2014</span>'
    chips = ''
    for g in order[:4]:
        site = p['store_domain'] if g['mine'] else insight_panels.brand_site(dict(brand=g['label'], url=g['url']))
        initials = ''.join(w[0] for w in g['label'].split()[:2]).upper() or '?'
        image = ('<img src="/icon?d=%s" alt="" loading="lazy" onerror="this.hidden=true">' % E(site)) if site else ''
        chips += '<span class="bchip%s" title="%s"><span aria-hidden="true">%s</span>%s</span>' % (
            ' mine' if g['mine'] else '', E('%s \u00b7 %d mention%s' % (g['label'], g['count'], '' if g['count']==1 else 's')),
            E(initials), image)
    extra = '<span class="more">+%d</span>' % (len(order)-4) if len(order) > 4 else ''
    return '<span class="brand-stack">%s%s</span>' % (chips, extra)



def questions_panel(s, ps, p, ctx):
    """One row per buyer question: how visible, how high, and who won it.

    Every column is read from saved answers. There is deliberately no search
    volume or difficulty column - we do not measure either, and a plausible
    looking bar for a number we never collected would be an invention.
    """
    import insight_panels
    own = ctx['own']
    qs = evidence.relevant_questions(p)
    prompts = json.loads(ps['prompts'])
    by_q = {q: dict(rate=own['questions'][q], avg_rank=own['q_rank'].get(q)) for q in own['questions']}
    answers, mentions = evidence.load(ctx['ids'], p)
    by_answer = {a['id']: a['prompt'] for a in answers}
    runs = defaultdict(int)
    for a in answers:
        runs[a['prompt']] += 1
    named = [q for q in qs if by_q.get(q,{}).get('rate',0)>0]
    if len(named)==1:
        takeaway = 'Your product appeared for \u201c%s\u201d. It did not appear for the other questions with saved answers.' % named[0]
    elif not ctx['ids']:
        takeaway = 'No scans in the selected period. Choose a longer date range above.'
    elif not named:
        takeaway = 'Your product was not recommended in the saved answers. Open a question to see what %s recommended.'%insight_panels.engine_phrase(ctx)
    else:
        takeaway = 'Compare the questions below to see where your product appears and where competitors are recommended.'
    # Most visible first. Opening on a column of zeros buries the questions the
    # merchant actually competes in, and those are the ones worth reading. Ties
    # go to the better average position, then to the question's own number so
    # the order is stable between renders.
    ordered = sorted(
        qs,
        key=lambda q: (by_q.get(q) is None,
                       -((by_q.get(q) or {}).get('rate') or 0),
                       (by_q.get(q) or {}).get('avg_rank') or 999,
                       prompts.index(q)))
    qrows = ''
    import prompt_creation
    prompt_types = {r['prompt']:r['type'] for r in db.all_('SELECT * FROM prompt_types WHERE prompt_set_id=?',(ps['id'],))}
    for q in ordered:
        result = by_q.get(q)
        index = prompts.index(q)
        # Numbered by the question's own place in the set, not by its row, so
        # "04" stays question four wherever the sort puts it.
        i = index
        cluster = p['_ps']['clusters'][index] if index < len(p['_ps']['clusters']) else ''
        topic = '<span class="q-topic">%s</span>' % E(cluster) if cluster else ''
        kind = prompt_types.get(q, 'organic')
        topic += '<span class="q-prompt-type"><i class="pt-dot pt-%s"></i>%s</span>' % (kind, prompt_creation.TYPES.get(kind, 'Organic'))
        vis = gauge(result['rate']) if result else '<span class="gauge-none">No answers</span>'
        if result and result['avg_rank']:
            rank = '<span class="q-pos">#%.1f</span>' % result['avg_rank']
        else:
            rank = '<span class="q-pos none">%s</span>' % ('Not named' if result else '\u2014')
        qrows += ('<tr><td class="vis">%s</td>'
                  '<td class="q"><span class="q-index">%02d</span><span class="q-text">%s</span>%s</td>'
                  '<td class="n">%s</td><td class="brands">%s</td><td class="n q-count">%s</td>'
                  '<td class="ev"><a href="/r/%s/answers?q=%d">View answers \u2192</a></td>'
                  '<td class="act">%s</td></tr>') % (
            vis, i+1, E(q), topic, rank,
            question_brands(q, mentions, by_answer, p, insight_panels),
            runs.get(q, 0) or '\u2014', E(s['token']), index,
            waitlist.button(waitlist.row_data(q, result['rate'] if result else None, runs.get(q, 0),
                                              mentions, by_answer, p, index, insight_panels, evidence)))
    table = ('<div class="qtable-wrap"><table class="qtable">'
             '<colgroup><col class="c-vis"><col><col class="c-pos"><col class="c-brands">'
             '<col class="c-runs"><col class="c-ev"><col class="c-act"></colgroup><thead><tr>'
             '<th>Visibility</th><th>Buyer question</th><th class="n">Avg. position</th>'
             '<th>Brands recommended</th><th class="n">Answers</th><th>Evidence</th>'
             '<th class="act"><span class="sr-only">Actions</span></th>'
             '</tr></thead><tbody>' + qrows + '</tbody></table></div>')
    return '<div id="questions">' + panel('Buyer questions',
        'Results for these questions across the selected period',
        '<p class="takeaway">'+E(takeaway)+'</p>'+table) + '</div>'


def questions(token, query):
    ctx = context(token,query)
    if not ctx:
        return None
    s,ps,p = ctx
    import insight_panels
    pctx = insight_panels.period_context(ps, p, query)
    body = header(s,p,'questions')
    body += insight_panels.filter_bar(pctx, 'buyer questions')
    import prompt_creation
    body += prompt_creation.render(token, p)
    body += questions_panel(s, ps, p, pctx)
    body += '<details class="measurement"><summary>About these questions</summary><p>Prompts come from your catalog or are added by you; they are not measured search demand. Adding prompts starts a new set for future scans. Saved results and their prompt sets are preserved; trends compare scans within the same set.</p></details>'
    if p['id'] is None:
        body=re.sub(r'\bYour product\b','Your catalog',body)
        body=re.sub(r'\byour product\b','your catalog',body)
    # Added after the catalog-view wording swap above: the agent fixes product
    # pages whichever view you are in, so "your product pages" must survive.
    body += waitlist.assets()
    return scope_links(body + insight_panels.FILTER_SCRIPT + SCRIPT,query,p)


def answer_product_chips(mentions, p, panels):
    """Individual identified products, never collapsed to their brand."""
    chips = []
    seen = set()
    for m in mentions:
        if not ((m['brand'] or '').strip() or (m['url'] or '').strip() or m['matched_product_id'] is not None):
            continue
        product = next((c for c in p['_catalog'] if c['id'] == m['matched_product_id']), None)
        name = product['title'] if product else m['product_name'] or m['brand']
        brand = product['vendor'] if product else m['brand']
        key = ('catalog', product['id']) if product else (norm(brand), norm(name))
        if key in seen:
            continue
        seen.add(key)
        mine = evidence.own(m, p)
        label = '%s · %s%s' % (name, brand or 'Brand unavailable', ' · Your product' if mine else '')
        src = product.get('image', '') if product else ''
        if not src:
            site = panels.brand_site(dict(brand=brand or '', url=m['url'] or ''))
            src = '/icon?d=' + site if site else ''
        initials = ''.join(w[0] for w in name.split()[:2]).upper() or '?'
        img = '<img src="%s" alt="" loading="lazy" onerror="this.hidden=true">' % E(src) if src else ''
        chips.append('<span class="product-chip%s" tabindex="0" aria-label="%s"><span aria-hidden="true">%s</span>%s<span class="product-chip-tip">%s</span></span>' % (' mine' if mine else '', E(label), E(initials), img, E(label)))
    return '<span class="answer-products">%s</span>' % ''.join(chips) if chips else '<span class="brand-none">—</span>'


def response_detail(a, ms, p, panels, state, label, identified, links, ring, pos,
                    engine, engine_name, n_sources):
    """The opened answer: what this engine said, and what it means.

    Laid out like PromptWatch's response view - a strip of figures, the buyer's
    question in its own box, then tabbed panels - because the previous two-column
    version put the answer text and a numbered list side by side at half width
    each and read as a wall.

    Deliberately NOT copied from that reference: their Sentiment meter. Produkto
    does not measure sentiment, and a meter with nothing behind it is worse than
    a missing one.
    """
    import engines
    done = a['processing_status'] == 'done'
    brands = answer_product_chips(ms, p, panels) if done else '<span class="brand-none">Pending</span>'
    figures = [('Mentioned', ring, 'Whether one of your products is recommended here'),
               ('Position', pos, 'Where your best-placed product sits in this answer'),
               ('Model', '<span class="ans-engine">%s%s</span>' % (engines.logo(engine), E(engine_name)),
                'The engine that gave this answer'),
               ('Products found', brands, 'Every buyable product this answer recommends'),
               ('Received', '<b>%s</b>' % E(date(a['created_at']).split(',')[0]), E(date(a['created_at'])))]
    strip = ''.join('<div class="resp-figure"><span class="kpi-label" title="%s">%s</span>%s</div>'
                    % (E(t), E(name), value) for name, value, t in figures)
    n_products = identified.count('<li')
    tabs = [('response', 'Response', ''), ('products', 'Products', n_products),
            ('citations', 'Citations', n_sources)]
    tablist = ''.join(
        '<button type="button" role="tab" class="resp-tab%s" data-tab="%s" aria-selected="%s">%s%s</button>'
        % (' on' if i == 0 else '', tab, 'true' if i == 0 else 'false', E(name),
           '' if count == '' else '<span class="resp-count">%d</span>' % count)
        for i, (tab, name, count) in enumerate(tabs))
    # The names worth picking out of the prose, for the highlight toggle: the
    # brands and products this answer actually recommended. Longest first, so
    # "Clubhouse Skin Helsinki Moisturiser" wins over "Clubhouse Skin".
    names = set()
    for m in ms:
        for value in (m['brand'], m['product_name'],
                      ' '.join(x for x in (m['brand'], m['product_name']) if x)):
            if value and len(value.strip()) > 2:
                names.add(value.strip())
    ours = {n for m in ms if evidence.own(m, p)
            for n in (m['brand'], m['product_name']) if n and len(n.strip()) > 2}
    listed = sorted(names, key=len, reverse=True)
    body = ('<div class="resp-tools">'
            '<label class="resp-toggle"><span>Highlight brand names</span>'
            '<input type="checkbox" class="hl-brands"><i class="fb-switch" aria-hidden="true"></i>'
            '</label></div>'
            '<p class="row-label %s">%s</p>'
            # The answer sits in its own panel, the way the buyer saw it in the
            # chat, rather than running straight into the page.
            '<div class="resp-chat" data-brands="%s" data-mine="%s">%s'
            '<div class="resp-body readable">%s</div></div>'
            '<details class="original"><summary>Original text</summary><pre>%s</pre></details>'
            % (state, E(label), E('|'.join(listed)), E('|'.join(sorted(ours))),
               '<div class="resp-engine">%s<span>%s</span></div>' % (engines.logo(engine), E(engine_name))
               + product_cards(ms, p, panels, 'prod-cards strip'),
               readable(overview_text(a['raw_text']) if engine == 'ai-overview' else a['raw_text']), E(a['raw_text'])))
    # One line that answers "so what?" before anyone reads the answer.
    real = sorted((m for m in ms if (m['brand'] or '').strip() or (m['url'] or '').strip()
                   or m['matched_product_id'] is not None), key=lambda m: m['rank'] or 999)
    mine = [m for m in real if evidence.own(m, p)]
    top = real[0] if real else None
    parts = ['<span class="%s">Your product: %s</span>' % (
        'sum-yes' if mine else 'sum-no',
        '#%s' % mine[0]['rank'] if mine else 'not named')]
    if top and not evidence.own(top, p):
        parts.append('Top pick: <b>%s</b>' % E(' '.join(x for x in (top['brand'], top['product_name']) if x)))
    parts.append('%d product%s' % (len(real), '' if len(real) == 1 else 's'))
    parts.append('%d source%s' % (n_sources, '' if n_sources == 1 else 's'))
    summary = '<p class="resp-summary">%s</p>' % ' · '.join(parts) if done else ''
    cites = ('<ul class="sources">%s</ul>' % ''.join(links) if links else
             '<p class="resp-none">This answer cited no sources.</p>')
    return ('<div class="resp-detail">'
            '<div class="resp-stats">%s</div>'
            '<div class="resp-prompt"><span class="kpi-label">Buyer question</span>'
            '<div class="resp-prompt-box"><p>%s</p>'
            '<button type="button" class="resp-copy" data-copy="%s" aria-label="Copy question">Copy</button>'
            '</div></div>'
            '%s<div class="resp-tabs" role="tablist">%s</div>'
            '<div class="resp-panel" data-panel="response">%s</div>'
            '<div class="resp-panel" data-panel="products" hidden>%s</div>'
            '<div class="resp-panel" data-panel="citations" hidden>%s</div>'
            '</div>') % (strip, E(a['prompt']), E(a['prompt']), summary, tablist, body,
                        product_cards(ms, p, panels) or identified, cites)


def answers(token, query):
    ctx = context(token,query)
    if not ctx:
        return None
    s,ps,p = ctx
    import insight_panels
    pctx = insight_panels.period_context(ps, p, query)
    qs = json.loads(ps['prompts'])
    selected = query.get('q','')
    status_filter = query.get('status','')
    search = query.get('search','').strip()
    body = header(s,p,'answers')
    body += insight_panels.filter_bar(pctx, 'answers')
    relevant=set(evidence.relevant_questions(p))
    options = '<option value="">All buyer questions</option>' + ''.join('<option value="%d" %s>%s</option>' % (i,'selected' if selected==str(i) else '',E(q)) for i,q in enumerate(qs) if q in relevant)
    catalog = p['id'] is None
    statuses = [('', 'All results'),('yours','One of your products recommended' if catalog else 'Your product recommended'),('brand','Brand only'),('absent','Not recommended')]
    body += '<form class="answer-filters" method="get"><label>Buyer question<select name="q">'+options+'</select></label><label>Result<select name="status">'+''.join('<option value="%s" %s>%s</option>' % (k,'selected' if k==status_filter else '',v) for k,v in statuses)+'</select></label><label>Search answers<input type="search" name="search" value="'+E(search)+'" placeholder="Product, brand or phrase"></label><button class="btn" type="submit">Apply filters</button><a class="clear-filter" href="/r/'+E(token)+'/answers">Clear</a></form>'
    # Every answer from the scans inside the chosen period.
    ids = pctx['ids']
    rows,_ = evidence.load(ids,p,include_unprocessed=True)
    import insight_panels as _ip
    listing = ''
    matches = []
    for a in rows:
        if selected and (not selected.isdigit() or int(selected)>=len(qs) or a['prompt']!=qs[int(selected)]):
            continue
        if query.get('answer') and query['answer'] != str(a['id']):
            continue
        # Same rule as evidence._raw: a mention with no brand, no link and no
        # matched product is generic advice ("ceramides", "a vitamin C serum"),
        # not something a shopper can buy. The charts have always excluded it;
        # this view read the table directly and listed all of it under
        # "Products identified", so one row could show 8 products beside a
        # "Product mentions" count of zero. 100 of 828 mentions, 21 Sep 2026.
        ms = db.all_("SELECT * FROM mentions WHERE answer_id=? AND ("
                     "COALESCE(TRIM(brand),'')<>'' OR COALESCE(TRIM(url),'')<>'' "
                     "OR matched_product_id IS NOT NULL) ORDER BY rank",(a['id'],))
        state = 'yours' if any(evidence.own(m,p) for m in ms) else 'brand' if any(m['is_their_brand'] for m in ms) else 'absent'
        if status_filter and status_filter != state:
            continue
        if search and search.casefold() not in (a['raw_text']+' '+a['prompt']).casefold():
            continue
        matches.append((a, ms, state, answer_figures(a, ms, p)))
    # Most visible first, like the buyer-questions table. An answer that
    # recommended one of their products outranks one that only named the brand,
    # which outranks one that did neither; then the best position wins, then the
    # newest. Filtering and searching still happen first, so the sort only
    # reorders what the reader asked to see.
    rank_state = {'yours': 0, 'brand': 1, 'absent': 2}
    matches.sort(key=lambda t: (rank_state.get(t[2], 3),
                                t[3]['position'] or 999,
                                -(t[0]['created_at'] or 0)))
    found = len(matches)
    # Paging: build full rows for one batch only. Filtering and sorting above
    # still cover every answer, so batch 2 continues exactly where batch 1 ended.
    try:
        offset = max(0, int(query.get('offset') or 0))
    except ValueError:
        offset = 0
    partial = query.get('partial') == '1'
    batch = matches[offset:offset + ANSWER_BATCH]
    for position, (a, ms, state, fig) in enumerate(batch, start=offset):
        label = dict(statuses)[state]
        if catalog and state=='yours':
            # Name the product: "one of your products" makes the reader open
            # every row to find out which, and a catalog has many.
            named=[]
            for m in ms:
                if evidence.own(m,p):
                    t=next((c['title'] for c in p['_catalog'] if c['id']==m['matched_product_id']),'')
                    if t and t not in named:
                        named.append(t)
            if named:
                label=', '.join(named[:2])+(' +%d more'%(len(named)-2) if len(named)>2 else '')+' recommended'
        if a['processing_status']!='done':
            label='Answer saved — analysis incomplete'
        products = ''
        for m in ms:
            name = ' '.join(x for x in (m['brand'],m['product_name']) if x) or 'Unnamed recommendation'
            site = safe_url(m['url'])
            mark = ('<img class="mention-logo" src="/icon?d=%s" alt="" aria-hidden="true">'
                    % E(urlsplit(site).netloc)) if site else ''
            row = ('<b>%s</b>%s' % (E(name),
                   '<span class="own-label">Your product</span>' if evidence.own(m,p)
                   else '<span class="brand-name">Your brand · another product</span>'
                   if m['is_their_brand'] else ''))
            products += '<li value="%d"%s>%s%s</li>' % (
                m['rank'], ' class="is-own"' if evidence.own(m,p) else '', mark, row)
        identified = ('<ol class="identified">'+products+'</ol>' if products else
                      '<p class="resp-none">No buyable product was recommended in this answer.</p>')
        sources = []
        for m in ms:
            if safe_url(m['url']):
                sources.append((m['url'], m['brand'] or urlsplit(m['url']).netloc))
        for c in json.loads(a['citations'] or '[]'):
            if isinstance(c,dict) and safe_url(c.get('url')):
                sources.append((c['url'],c.get('title') or urlsplit(c['url']).netloc))
        seen=set();links=[]
        for url,title in sources:
            if url not in seen:
                seen.add(url)
                host=urlsplit(url).netloc.lower().removeprefix('www.')
                own_site=bool(p['store_domain']) and (host==p['store_domain'] or host.endswith('.'+p['store_domain']))
                links.append(
                    '<li%s><img class="mention-logo" src="/icon?d=%s" alt="" aria-hidden="true">'
                    '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>'
                    '<span class="cite-host">%s</span>%s</li>'
                    % (' class="is-own"' if own_site else '', E(host), E(url), E(title), E(host),
                       '<span class="own-label">Your site</span>' if own_site else ''))
        # Yes/no, not a percentage: one answer either names the product or it doesn't.
        ring = (('<span class="mentioned yes" title="Your product is recommended">\u2713 Yes</span>'
                 if state == 'yours' else '<span class="mentioned no" title="Not mentioned">No</span>')
                if a['processing_status'] == 'done' else '<span class="gauge-none">\u2014</span>')
        pos = ('<b>#%d</b>' % fig['position']) if fig['position'] else '<span class="stat-dash">\u2014</span>'
        cites = ('<span class="cite-ratio%s">%d/%d</span>' % (
            ' has-own' if fig['own_cites'] else '', fig['own_cites'], fig['cites'])
            ) if fig['cites'] else '<span class="stat-dash">\u2014</span>'
        flag = '<span class="row-flag">Brand only</span>' if state == 'brand' else (
            '<span class="row-flag warn">Incomplete</span>' if a['processing_status'] != 'done' else '')
        eng = a['engine'] or config.DEFAULT_ENGINE
        eng_name = config.engine_label(eng)
        import engines
        eng_badge = ('<span class="ans-engine">%s%s</span>'
                     % (engines.logo(eng), E(eng_name)))
        listing += ('<details class="response response-row" id="answer-%d" %s>'
                    '<summary>'
                    '<span class="ans-share">%s</span>'
                    '<span class="ans-text"><b>%s</b>'
                    '<span class="ans-q">%s \u00b7 run %d%s</span></span>'
                    '<span class="ans-model">%s</span>'
                    '<span class="ans-pos">%s</span>'
                    '<span class="ans-brands">%s</span>'
                    '<span class="ans-cite">%s</span>'
                    '<span class="ans-date" title="%s">%s</span>'
                    '</summary>'
                    '%s</details>') % (
            a['id'], 'open' if query.get('answer') else '',
            ring, E(snippet(a['raw_text'])), E(a['prompt']), a['run_n'], flag, eng_badge,
            pos, answer_product_chips(ms, p, _ip) if a['processing_status']=='done' else '<span class="brand-none">Pending</span>', cites,
            # Full timestamp on hover; the row shows the day, as the date
            # column has to stay narrow enough for the snippet to breathe.
            E(date(a['created_at'])), E(date(a['created_at']).split(',')[0]),
            response_detail(a, ms, p, _ip, state, label, identified, links, ring, pos,
                            eng, eng_name, len(seen)))
    left = found - offset - len(batch)
    if left > 0:
        listing += ('<div class="ans-more" data-offset="%d"><button type="button" class="btn btn-secondary">'
                    'Show more answers <span class="small">(%d more)</span></button></div>'
                    % (offset + len(batch), left))
    if partial:
        return scope_links(listing, query, p)
    if found:
        body += ('<div class="ans-head"><span></span><span title="Whether one of your products is recommended in this answer. Incomplete analysis shows a dash.">Mentioned</span><span>Answer</span>'
                 '<span>Model</span><span>Pos.</span><span>Product mentions</span>'
                 '<span title="Citations pointing at your own site, out of every source '
                 'the answer cited">Cites</span><span>Date</span></div>') + listing
    if not found:
        if rows:
            body += '<div class="no-results"><h2>No answers match these filters</h2><p>Try another question or clear the filters.</p></div>'
        elif ids:
            body += '<div class="no-results"><h2>No completed answers</h2><p>There are no saved responses to review for this period yet.</p></div>'
        else:
            body += '<div class="no-results"><h2>No answers match these filters</h2><p>No scans in the selected period. Choose a longer date range above.</p></div>'
    return scope_links(body + insight_panels.FILTER_SCRIPT + SCRIPT,query,p)


ANSWER_BATCH = 40

# Raw: the brand-highlight regex below needs its backslashes to survive Python.
SCRIPT = r'''<script>
// Answers load in batches: the next batch is fetched when "Show more" nears
// the viewport (or is clicked) and replaces that button, which the batch
// brings back if more remain.
(()=>{let busy=false;
async function more(box){if(busy||!box.isConnected)return;busy=true;const btn=box.querySelector('button');btn.disabled=true;btn.firstChild.textContent='Loading… ';
 try{const u=new URL(location.href);u.searchParams.set('offset',box.dataset.offset);u.searchParams.set('partial','1');
  const r=await fetch(u,{credentials:'same-origin'});if(!r.ok)throw Error();
  const t=document.createElement('template');t.innerHTML=await r.text();box.replaceWith(t.content);watch();}
 catch(e){btn.disabled=false;btn.firstChild.textContent='Show more answers ';}
 finally{busy=false;}}
const io='IntersectionObserver' in window?new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)more(e.target);}),{rootMargin:'600px'}):null;
function watch(){document.querySelectorAll('.ans-more').forEach(b=>{if(b.dataset.w)return;b.dataset.w=1;b.querySelector('button').addEventListener('click',()=>more(b));if(io)io.observe(b);});}
watch();})();
document.querySelectorAll('.show-brands').forEach(button=>{const table=button.previousElementSibling;if(!table.querySelector('.extra-brand')){button.hidden=true;return;}button.addEventListener('click',()=>{const expanded=button.getAttribute('aria-expanded')!=='true';button.setAttribute('aria-expanded',expanded);table.classList.toggle('all-brands',expanded);button.textContent=expanded?'Show fewer brands':'Show all brands';});});
const rescan=document.getElementById('rescan');
if(rescan)rescan.addEventListener('click',async()=>{rescan.disabled=true;const err=document.getElementById('scan-error');err.hidden=true;try{const r=await fetch('/api/scan?d='+encodeURIComponent(rescan.dataset.store),{method:'POST'});const j=await r.json();if(j.redirect){location.href=j.redirect;return;}if(!j.token)throw Error(j.error||'Could not start scan.');location.href='/r/'+j.token;}catch(e){err.textContent=e.message;err.hidden=false;rescan.disabled=false;}});
if(!matchMedia('(prefers-reduced-motion: reduce)').matches)document.querySelectorAll('.count').forEach(el=>{const v=Number(el.dataset.v);let start;function step(t){start??=t;const p=Math.min(1,(t-start)/550);el.textContent=(v*(1-Math.pow(1-p,3))).toFixed(Number(el.dataset.d??1));if(p<1)requestAnimationFrame(step);}requestAnimationFrame(step);});
// Tabs inside an opened answer. Delegated from the document, because rows are
// only in the page once and the handler must survive filtering and paging.
document.addEventListener('click',e=>{
 const tab=e.target.closest('.resp-tab');
 if(tab){const box=tab.closest('.resp-detail');
  box.querySelectorAll('.resp-tab').forEach(t=>{const on=t===tab;t.classList.toggle('on',on);t.setAttribute('aria-selected',on);});
  box.querySelectorAll('.resp-panel').forEach(pnl=>{pnl.hidden=pnl.dataset.panel!==tab.dataset.tab;});
  return;}
 const copy=e.target.closest('.resp-copy');
 if(copy){navigator.clipboard?.writeText(copy.dataset.copy).then(()=>{
   const was=copy.textContent;copy.textContent='Copied';copy.classList.add('done');
   setTimeout(()=>{copy.textContent=was;copy.classList.remove('done');},1400);}).catch(()=>{});}
});
// Highlight the brands this answer recommended, inside the answer itself.
// Only exact appearances are marked: if the extractor read "CeraVe" but the
// prose says "Cera Ve", nothing lights up, which is the honest outcome - a
// fuzzy highlight would claim a mention the measurement did not make.
const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
document.addEventListener('change',e=>{
 const box=e.target.closest('.hl-brands');if(!box)return;
 const chat=box.closest('.resp-panel').querySelector('.resp-chat');
 const body=chat.querySelector('.resp-body');
 if(!chat.dataset.plain)chat.dataset.plain=body.innerHTML;
 if(!box.checked){body.innerHTML=chat.dataset.plain;return;}
 const names=(chat.dataset.brands||'').split('|').filter(n=>n.length>2);
 if(!names.length)return;
 const mine=new Set((chat.dataset.mine||'').split('|').filter(Boolean).map(s=>s.toLowerCase()));
 const re=new RegExp('('+names.map(esc).join('|')+')','gi');
 const walker=document.createTreeWalker(body,NodeFilter.SHOW_TEXT);
 const targets=[];for(let n=walker.nextNode();n;n=walker.nextNode())if(re.test(n.nodeValue)){re.lastIndex=0;targets.push(n);}
 targets.forEach(node=>{
  const frag=document.createDocumentFragment();let last=0,m;re.lastIndex=0;
  while((m=re.exec(node.nodeValue))){
   if(m.index>last)frag.append(node.nodeValue.slice(last,m.index));
   const mark=document.createElement('mark');mark.textContent=m[0];
   if(mine.has(m[0].toLowerCase()))mark.className='mine';
   frag.append(mark);last=m.index+m[0].length;}
  if(last<node.nodeValue.length)frag.append(node.nodeValue.slice(last));
  node.replaceWith(frag);});
});
</script>'''
