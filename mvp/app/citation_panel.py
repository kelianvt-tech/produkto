"""Product-specific citation evidence from saved API annotations only."""
import json
import math
from urllib.parse import urlsplit, parse_qsl, urlencode
import db
import storetime
import evidence as scope


def canonical(url):
    from citation_explorer import key
    return key(url)


def evidence(scan_ids, product):
    answers,ms=scope.load(scan_ids,product)
    own={canonical(p['url']) for p in product['_catalog'] if
         (p['id']==product['id'] if product['id'] is not None else p['id'] in product['_ps']['product_ids'])}
    own.discard('')
    related_by_answer={a['id']:{canonical(m['url']) for m in ms if m['answer_id']==a['id'] and scope.own(m,product) and m['product_name']} for a in answers}
    # A matched name with a homepage URL does not make that homepage a product citation.
    domain=product['store_domain']
    rows = {}
    for a in answers:
        related={url for url in related_by_answer[a['id']] if url and url.split('?')[0] not in (domain,'www.'+domain)}
        for c in json.loads(a['citations'] or '[]'):
            if not isinstance(c,dict):
                continue
            key = canonical(c.get('url'))
            if not key or (key not in own and key not in related):
                continue
            row = rows.setdefault(key,dict(url=c['url'],title=c.get('title') or key,own=key in own,answers={}))
            row['answers'][a['id']] = a
    return sorted(rows.values(),key=lambda r:(not r['own'],-len(r['answers']))), len(answers)


def domains(scan_ids, product):
    """Every website ChatGPT cited, ranked by how many answers mention it."""
    from text import norm
    answers,ms=scope.load(scan_ids,product)
    brands={norm(m['brand']):m['brand'] for m in ms if norm(m['brand'])}
    own_domain = (product['store_domain'] or '').lower()
    rows = {}
    for a in answers:
        seen = set()
        for c in json.loads(a['citations'] or '[]'):
            url = (c or {}).get('url') if isinstance(c, dict) else None
            host = urlsplit(url or '').netloc.lower().removeprefix('www.')
            if not host:
                continue
            row = rows.setdefault(host, dict(domain=host, cites=0, answers=set(), url=url))
            row['cites'] += 1
            row['answers'].add(a['id'])
            seen.add(host)
    stem = lambda d: norm(d.split('.')[0])
    out = []
    for r in rows.values():
        own = r['domain'] == own_domain or r['domain'].endswith('.' + own_domain)
        brand = next((label for key, label in brands.items()
                      if len(key) > 3 and (key in stem(r['domain']) or stem(r['domain']) in key)), '')
        out.append(dict(domain=r['domain'], url=r['url'], cites=r['cites'],
                        answers=len(r['answers']), own=own,
                        brand='' if own else brand))
    out.sort(key=lambda r: (-r['answers'], -r['cites'], r['domain']))
    return out, len(answers)


def domain_panel(ids, product):
    from dashboard import E
    from insight_panels import box
    rows, total = domains(ids, product)
    if not rows:
        return box('Top cited domains', 'Most referenced websites in AI answers.',
                   '<div class="panel-empty"><b>No citations saved in this period</b>'
                   '<span>ChatGPT did not link to any sources, or there are no scans.</span></div>',
                   'domains-card', 'rank')
    trs = ''
    for i, r in enumerate(rows):
        tag = ('<span class="own-label">Your site</span>' if r['own']
               else '<span class="domain-brand">%s</span>' % E(r['brand']) if r['brand'] else '')
        trs += ('<tr class="%s"><td class="rank-number">%d</td>'
                '<td><div class="domain-cell"><span class="domain-icon"><span aria-hidden="true">%s</span>'
                '<img src="/icon?d=%s" alt="" loading="lazy" onerror="this.hidden=true"></span>'
                '<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>%s</div></td>'
                '<td class="num">%.1f%%</td><td class="num">%d</td></tr>') % (
            ('rank-own ' if r['own'] else '') + ('extra-row' if i >= 10 else ''),
            i + 1, E(r['domain'][0].upper()), E(r['domain']), E(r['url'] or 'https://' + r['domain']),
            E(r['domain']), tag, 100.0 * r['answers'] / total if total else 0, r['cites'])
    more = ('<button type="button" class="show-more" id="domains-toggle" aria-expanded="false" '
            'data-more="View all %d domains" data-less="Show fewer">View all %d domains</button>' % (len(rows), len(rows))) if len(rows) > 10 else ''
    table = ('<div class="domain-table"><table class="product-rankings domains" id="domains-table">'
             '<thead><tr><th>#</th><th>Domain</th>'
             '<th class="num">Frequency <span class="heading-info" title="Share of answers in this period that cite this domain">i</span></th>'
             '<th class="num">Cites</th></tr></thead><tbody>%s</tbody></table>%s</div>'
             '<div class="chart-footer"><span>%d domains cited in this period</span></div>') % (trs, more, len(rows))
    return box('Top cited domains', 'Most referenced websites in AI answers.', table, 'domains-card', 'rank')


DOMAIN_SCRIPT = """<script>
(()=>{const b=document.getElementById('domains-toggle');if(!b)return;
const t=document.getElementById('domains-table');
b.addEventListener('click',()=>{const open=b.getAttribute('aria-expanded')!=='true';
 b.setAttribute('aria-expanded',open);t.classList.toggle('show-all',open);
 b.textContent=open?b.dataset.less:b.dataset.more;});})();
</script>"""


def render(s, ps, p, ids):
    from dashboard import E, panel, date
    rows, total = evidence(ids,p)
    questions=json.loads(ps['prompts'])
    rates=[]
    for own,label in [(True,'Your product page'),(False,'Other pages about this product')]:
        count=sum(len(r['answers']) for r in rows if r['own']==own)
        rates.append('<div><span>%s</span><strong>%d</strong><small>citations in this period</small></div>'%(label,count))
    content=''
    for r in rows:
        links=''.join('<a href="/r/%s/answers?answer=%d#answer-%d">Q%d · %s · Response %d ↗</a>'%(E(s['token']),a['id'],a['id'],questions.index(a['prompt'])+1 if a['prompt'] in questions else 0,E(date(a['created_at'])[:11]),a['run_n']) for a in r['answers'].values())
        content+='<div class="citation-row"><div><span class="own-label">%s</span><h3><a href="%s" target="_blank" rel="noopener noreferrer">%s ↗</a></h3><small>%s</small></div><strong>%d<small>citations</small></strong><details><summary>Read citing answers</summary><div class="citation-links">%s</div></details></div>'%('Your product page' if r['own'] else 'Other product page',E(r['url']),E(r['title']),E(urlsplit(r['url']).netloc),len(r['answers']),links)
    if not rows:
        content+='<p>No citations to this product’s page or its identified listings were saved in this period.</p>'
    content+='<p class="small">Actual source citations saved with ChatGPT’s answers. Repeated links count once per answer. Other pages are included when their URL matches a recommendation identified as your product; brand-only pages are excluded.</p>'
    return '<div id="citations">'+panel('Citation sources','Where ChatGPT links to your products' if p['id'] is None else 'Where ChatGPT links to '+E(p['title']),content)+'</div>'


def history(ctx, p):
    """One reading per week/month/quarter in the period; counts are None when no scan."""
    import datetime as dt
    import period
    group=ctx['per']['group']
    readings=[]
    for d in period.bucket_starts(ctx['a'],ctx['b'],group):
        nxt=period.next_bucket(d,group)
        ids=[x['id'] for x in ctx['scans'] if d<=storetime.date_of(x['run_at'],ctx.get('tz'))<nxt]
        counts=[None,None,None]
        if ids:
            rows,total=evidence(ids,p)
            marks=','.join('?'*len(ids))
            _,mentions=scope.load(ids,p)
            mentioned=len({m['answer_id'] for m in mentions if scope.own(m,p)})
            if total:
                counts=[mentioned]+[sum(len(r['answers']) for r in rows if r['own']==own) for own in (True,False)]
        readings.append(dict(label=period.short_label(d,group),long=period.long_label(d,group),counts=counts))
    return readings


def trend_card(title, subtitle, readings, columns, unit):
    from dashboard import E
    from insight_panels import box
    labels=['Product recommended','Your product page','Other listings of your products']
    colors=['#0b1b35','#0b1b35','#a78bfa']
    main=columns[0]
    filled=[i for i,r in enumerate(readings) if r['counts'][main] is not None]
    total=sum(readings[i]['counts'][main] for i in filled) if filled else None
    delta=readings[filled[-1]]['counts'][main]-readings[filled[-2]]['counts'][main] if len(filled)>1 else None
    # Same tokens as the rest of the dashboard; these land in small text,
    # so they use the readable ink weight rather than the light mark.
    color=lambda d:'var(--up)' if d>0 else 'var(--down)' if d<0 else 'var(--ink)'
    if delta is None:
        change='First reading' if filled else 'No scans'
    else:
        change=('↗ +' if delta>0 else '↘ −' if delta<0 else '→ ')+str(abs(delta))+' vs previous '+unit
    content='<div class="chart-summary"><div><span>%s</span><strong>%s</strong></div><span class="citation-change" style="color:%s">%s</span></div>'%(('Total mentions' if main==0 else 'Total citations · your product pages'),'%d'%total if total is not None else '—',color(delta or 0),change)
    svg='<svg class="citation-trend" viewBox="0 0 660 280" role="img" aria-label="%s trend, count per %s">'%(E(title),unit)
    peak=max([r['counts'][c] or 0 for r in readings for c in columns]+[1])
    step=max(1,math.ceil(peak/5))
    maximum=step*5
    scale=180/maximum
    for v in range(0,maximum+1,step):
        y=225-v*scale
        svg+='<line x1="48" x2="612" y1="%s" y2="%s" stroke="#eceef1"/><text x="37" y="%s" text-anchor="end" class="axis-label">%d</text>'%(y,y,y+4,v)
    n=len(readings)
    x=lambda i:330 if n==1 else 48+564*i/max(1,n-1)
    for col in columns:
        prev=None
        for i,r in enumerate(readings):
            v=r['counts'][col]
            if v is None:
                continue
            y=225-v*scale
            stroke=colors[col]
            if prev is not None:
                pi,pv=prev
                stroke=color(v-pv) if col==main else colors[col]
                svg+='<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s" stroke-width="3" %s/>'%(x(pi),x(i),225-pv*scale,y,stroke,'stroke-dasharray="5 4"' if col==2 else '')
            label='%s · %s: %d'%(r['long'],labels[col],v)
            svg+='<circle cx="%s" cy="%s" r="5" fill="%s" stroke="white" stroke-width="2" tabindex="0" aria-label="%s"><title>%s</title></circle>'%(x(i),y,stroke,E(label),E(label))
            prev=(i,v)
    if len(filled)==1:
        svg+='<text x="330" y="100" text-anchor="middle" class="first-scan-title">A trend needs scans in two different %ss</text>'%unit
    if not filled:
        svg+='<text x="330" y="135" text-anchor="middle" class="first-scan-title">No scans in this period</text>'
    every=max(1,math.ceil(n/7))
    for i,r in enumerate(readings):
        if i%every==0 or i==n-1:
            if i!=n-1 and n-1-i<every:
                continue
            svg+='<line x1="%s" x2="%s" y1="225" y2="229" stroke="#c9ced6"/><text x="%s" y="250" text-anchor="middle" class="axis-label">%s</text>'%(x(i),x(i),x(i),E(r['label']))
    content+=svg+'</svg><div class="chart-legend">'+''.join('<span><i style="background:%s"></i>%s</span>'%(colors[c],labels[c]) for c in columns)+'</div>'
    content+='<div class="chart-footer">Counts per %s · same buyer questions</div><details class="chart-evidence"><summary>View history</summary><table><thead><tr><th>Period</th>'%unit+''.join('<th>%s</th>'%labels[c] for c in columns)+'</tr></thead><tbody>'
    for r in readings:
        content+='<tr><td>%s</td>'%E(r['long'])+''.join('<td>%s</td>'%('%d'%r['counts'][c] if r['counts'][c] is not None else 'No scan') for c in columns)+'</tr>'
    content+='</tbody></table></details>'
    return box(title,subtitle,content,'citation-chart','chart')


def page(token, query=None):
    from dashboard import context,header,SCRIPT,scope_links
    import insight_panels
    ctx=context(token,query or {})
    if not ctx:return None
    s,ps,p=ctx
    pctx=insight_panels.period_context(ps,p,query or {})
    body=header(s,p,'citations')+insight_panels.filter_bar(pctx,'mentions and citations')
    rows,total=evidence(pctx['ids'],p)
    direct=sum(len(r['answers']) for r in rows if r['own'])
    other=sum(len(r['answers']) for r in rows if not r['own'])
    if total:
        body+='<div class="product-citation-summary" aria-label="Product citations in the selected period"><span><b>%d</b> direct product citations</span><span aria-hidden="true">·</span><span><b>%d</b> other product-listing citations</span></div>'%(direct,other)
    else:
        body+='<p class="product-citation-summary">%s</p>'%('No scans in this period' if not pctx['ids'] else 'No completed answers in this period')
    import citation_explorer
    body+=citation_explorer.render(s,pctx,p)+insight_panels.FILTER_SCRIPT+SCRIPT
    if p['id'] is None:
        body=body.replace('your selected product','your selected products').replace('your product page,','your product pages,').replace('recommending your product.','recommending your selected products.').replace('identified as your product;','identified as one of your products;')
    return scope_links(body,query or {},p)
