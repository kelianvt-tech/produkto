"""Chart-led overview panels built exclusively from stored scan evidence.

Every panel follows the period chosen in the filter bar (see period.py):
all answers from the scans inside that period are pooled together.

Every panel also follows the engine selection beside it (see engines.py).
Both filters are applied in `evidence.load`, so a panel gets them by reading
its evidence the normal way rather than by remembering to ask.
"""
import datetime as dt
import html
import json
import math
import os
import re
import time
import unicodedata
from collections import defaultdict

import config
import db
import engines
import period
import storetime
import evidence
from text import norm, words

E = html.escape


def display_brand(value):
    value=(value or '').strip()
    return 'Brand unavailable' if not value or re.match(r'^(about:|https?://|undefined$|null$)',value,re.I) else value


def market_rows(scan_ids, p):
    """Read-only brand comparison, pooled over the same answers as the catalog."""
    answers, mentions=evidence.load(scan_ids,p)
    own=next(r for r in products(scan_ids,p) if r['own'])
    result=[dict(own,name=p['vendor'] if p['id'] is None else p['title'])]
    groups={}
    for m in mentions:
        if m['is_theirs']:
            continue
        brand=display_brand(m['brand'])
        key=norm(brand)
        g=groups.setdefault(key,dict(key=key,name=brand,brand=brand,own=False,hits={},count=0))
        g['hits'][m['answer_id']]=min(g['hits'].get(m['answer_id'],999),m['rank'])
        g['count']+=1
    for g in groups.values():
        g.update(rate=100*len(g['hits'])/len(answers) if answers else 0,
                 share=100*g['count']/len(mentions) if mentions else 0,
                 avg=sum(g['hits'].values())/len(g['hits']) if g['hits'] else None)
    return result+sorted(groups.values(),key=lambda r:(-r['rate'],r['name']))


def products(scan_ids, product):
    """Group recommendations into products across one or more scans.

    Follows the existing share-of-voice clustering and keeps which answers
    each product appeared in, so rates and positions can be pooled.
    """
    answers, ms = evidence.load(scan_ids,product)
    own = dict(name=product['title'],brand=product['vendor'] or product['store_domain'],own=True,words=set(),hits={},count=0,url=product['url'] or '')
    groups = [own]
    by_brand = defaultdict(list)   # norm(brand) -> competitor groups, in creation order
    for m in ms:
        group = own if evidence.own(m,product) else None
        if m['is_theirs'] and group is None:
            continue  # Another own product is never an external competitor.
        w = set(words(m['product_name']))
        brand_key = norm(m['brand'])
        if group is None:
            # Same first-match rule as scanning every group, but only among
            # groups of the same brand (the only ones that can match).
            for c in by_brand[brand_key]:
                if (not w and not c['words']) or (w and c['words'] and len(w & c['words'])/len(w | c['words']) >= .5):
                    group=c
                    break
        if group is None:
            group=dict(name=m['product_name'] or m['brand'] or 'Unnamed',brand=m['brand'],own=False,words=w,hits={},count=0,url=m['url'] or '')
            groups.append(group)
            by_brand[brand_key].append(group)
        group.setdefault('counts',{}).setdefault(m['answer_id'],0)
        group['counts'][m['answer_id']]+=1
        group['count']+=1
        group['hits'][m['answer_id']] = min(group['hits'].get(m['answer_id'],999),m['rank'])
        if (m.get('price') or '').strip():
            group.setdefault('prices',[]).append(m['price'].strip())
        if not group['url'] and m['url']:
            group['url']=m['url']
    n=len(answers)
    # Per-question totals are the same for every group: count them once.
    prompt_of={a['id']:a['prompt'] for a in answers}
    q_total={}
    for a in answers:
        q_total[a['prompt']]=q_total.get(a['prompt'],0)+1
    for c in groups:
        # 'visibility' is what the dashboard shows: % of answers that mention it.
        # The position-weighted score is kept as 'weighted' but not displayed.
        c['answers']=n
        c['rate']=100*len(c['hits'])/n if n else 0
        c['visibility']=c['rate']
        c['weighted']=100*sum(1/math.log2(r+1) for r in c['hits'].values())/n if n else 0
        c['avg']=sum(c['hits'].values())/len(c['hits']) if c['hits'] else None
        c['share']=100*c['count']/len(ms) if ms else 0
        c['key']='own' if c['own'] else norm(c['brand'])+'|'+norm(c['name'])
        hit_q,ranks_q=defaultdict(int),defaultdict(list)
        for aid,rank in c['hits'].items():
            q=prompt_of.get(aid)
            if q is None or not rank:
                continue
            hit_q[q]+=1
            ranks_q[q].append(rank)
        c['questions']={q:100*hit_q.get(q,0)/t for q,t in q_total.items()}
        c['q_n']=dict(q_total)
        c['q_rank']={q:sum(ranks_q[q])/len(ranks_q[q]) for q in q_total if ranks_q.get(q)}
    return sorted(groups,key=lambda c:(-c['visibility'],c['avg'] or 99,-c['share'],c['name']))


def mentioned_price(prices):
    """The price AI answers quote for a product: the median quote, in the
    currency most quotes use. Ranges count by their low end. None when no
    answer gave a price."""
    quotes=[]
    for text in prices or []:
        m=re.search(r'(\d[\d.,]*)',text)
        if not m:
            continue
        raw=m.group(1).rstrip('.,')
        # "1.299,00" and "1,299.00" both mean 1299; a lone comma with two
        # decimals ("16,99") is a decimal comma.
        if re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d+)?',raw):
            raw=raw.replace('.','').replace(',','.')
        elif re.fullmatch(r'\d+,\d{1,2}',raw):
            raw=raw.replace(',','.')
        else:
            raw=raw.replace(',','')
        try:
            value=float(raw)
        except ValueError:
            continue
        unit=text[:m.start()].strip()[-3:].strip() or text[m.end():].strip()[:3].strip()
        quotes.append((unit,value))
    if not quotes:
        return None
    units=defaultdict(int)
    for u,_ in quotes:
        units[u]+=1
    unit=max(units,key=units.get)
    values=sorted(v for u,v in quotes if u==unit)
    n=len(values)
    med=values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2
    number=('%.0f'%med) if med==int(med) else ('%.2f'%med)
    symbol=unit if unit in ('€','$','£','¥','₹') else ''
    text=(symbol+number) if symbol else ((number+' '+unit).strip())
    return dict(text=text,quotes=len(quotes),value=med)


def period_context(ps, p, query):
    """Everything the Overview needs for the chosen period and engines.

    The engine selection is written onto `p` itself, so every later
    `evidence.load(ids, p)` in every panel is filtered without being told.
    """
    per=period.parse(query)
    # Dates belong to the merchant's clock, not the server's.
    tz=storetime.zone(p.get('store_domain'))
    a,b,start,end=period.bounds(per,tz=tz)
    picked=engines.parse(query)
    p['_engines']=None if engines.is_all(picked) else list(picked)
    scans=period.done_scans(ps['id'],start,end)
    ids=[x['id'] for x in scans]
    rows=products(ids,p)
    own=next(r for r in rows if r['own'])
    return dict(per=per,a=a,b=b,scans=scans,ids=ids,rows=rows,own=own,engines=picked,tz=tz)


_HOSTS = {'t': 0, 'hosts': ()}


def cited_hosts():
    """Every website the saved answers cited, e.g. icietla.com, roble.store.
    Rebuilt at most every 10 minutes; it is what makes brand_site() find a
    brand's real domain instead of guessing brand + '.com'."""
    import time
    from urllib.parse import urlsplit
    if time.time() - _HOSTS['t'] > 600:
        import db
        hosts = set()
        for r in db.all_("SELECT citations FROM answers WHERE citations IS NOT NULL AND citations != '[]'"):
            try:
                for c in json.loads(r[0]):
                    h = urlsplit(c.get('url') or '').netloc.lower()
                    hosts.add(h[4:] if h.startswith('www.') else h)
            except (ValueError, TypeError, AttributeError):
                continue
        _HOSTS.update(t=time.time(), hosts=tuple(sorted(h for h in hosts if '.' in h)))
    return _HOSTS['hosts']


def brand_site(row):
    """The brand's own domain, for its favicon.

    Preferred: the link ChatGPT gave, when it points at the brand's own site.
    Otherwise the brand name as a .com, which is right often enough and simply
    fails to load when it isn't - the initials stay underneath either way.
    Retailer links (Boots, LookFantastic) are skipped: their logo would be
    misleading next to another brand's product.
    """
    from urllib.parse import urlsplit
    slug=re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',row['brand'] or '')
                .encode('ascii','ignore').decode().lower())
    if not slug:
        return ''
    host=urlsplit(row.get('url') or '').netloc.lower()
    host=host[4:] if host.startswith('www.') else host
    stem=host.split('.')[0] if host else ''
    if stem and (stem in slug or slug in stem):
        return host
    # A brand that is itself a domain ("Roble.Store").
    named=(row['brand'] or '').strip().lower()
    if re.fullmatch(r'[a-z0-9-]+(\.[a-z0-9-]+)+',named):
        return named
    # A site the answers cited whose name is the brand: icietla.com for
    # "Ici et Là", kavehome.com for "Kave Home". Shortest host wins, so the
    # brand's main site beats a subdomain like islas.ikea.es.
    hit=_host_by_stem().get(slug)
    if hit:
        return hit
    return slug + '.com'


_STEMS = {'hosts': None, 'index': {}}


def _host_by_stem():
    """First label of each cited host -> its shortest host (same rule as before,
    built once per cited_hosts() refresh instead of once per brand chip)."""
    hosts = cited_hosts()
    if _STEMS['hosts'] is not hosts:
        index = {}
        for h in hosts:
            stem = h.split('.')[0]
            if stem not in index or len(h) < len(index[stem]):
                index[stem] = h
        _STEMS.update(hosts=hosts, index=index)
    return _STEMS['index']


def thumb(row, p):
    from dashboard import safe_url
    image=row.get('image') or (p['image'] if row['own'] else '')
    if not image:
        with open(os.path.join(os.path.dirname(__file__),'product-images.json')) as f:
            for record in json.load(f):
                if norm(record['brand'])==norm(row['brand']) and norm(record['name'])==norm(row['name']):
                    image=record['image'];break
    initials=''.join(w[0] for w in row['brand'].split()[:2]) or 'P'
    if safe_url(image):
        inner='<img src="%s" alt="%s" loading="lazy" onerror="this.hidden=true">' % (E(image),E(row['name']))
    elif not row['own'] and brand_site(row):
        # The rival's own product photo: from the page the answer linked to,
        # else the brand's Shopify search, else the brand logo (see /pimg).
        from urllib.parse import quote
        link=row.get('url') or ''
        inner=('<img class="product-photo" src="/pimg?u=%s&amp;n=%s&amp;d=%s&amp;b=%s" alt="" loading="lazy" '
               'onerror="this.hidden=true">' % (E(quote(link if safe_url(link) else '',safe='')),E(quote(row['name'] or '',safe='')),
                                                E(brand_site(row)),E(quote(row['brand'] or '',safe=''))))
    else:
        site=brand_site(row)
        inner=('<img class="brand-mark" src="/icon?d=%s" alt="" loading="lazy" '
               'onerror="this.hidden=true">' % E(site)) if site else ''
    return '<span class="rank-thumb"><span aria-hidden="true">%s</span>%s</span>' % (E(initials),inner)


def box(title, subtitle, content, cls='', icon='chart', control=''):
    paths={'chart':'M3 16V5m0 11h15M6 12l4-5 4 3 4-6', 'rank':'M4 5h2m3 0h10M4 10h2m3 0h10M4 15h2m3 0h10', 'pie':'M10 2a8 8 0 1 0 8 8h-8V2zm3 0v5h5a7 7 0 0 0-5-5', 'position':'M5 4v14m5-10v10m5-6v6M3 18h16'}
    return '<section class="insight-card %s"><div class="insight-heading"><svg viewBox="0 0 22 22" aria-hidden="true"><path d="%s"/></svg><h2>%s</h2><span class="heading-info" title="%s" aria-label="%s">i</span>%s</div>%s</section>' % (cls,paths[icon],title,E(subtitle),E(subtitle),control,content)


def engine_menu(selected):
    """The engine picker: one checkbox per engine, plus Select all."""
    picked=set(selected or engines.all_ids())
    rows=''.join(
        '<label class="fb-check"><input type="checkbox" data-engine="%s"%s>'
        '<span class="fb-engine">%s%s</span></label>'
        % (E(eid),' checked' if eid in picked else '',engines.logo(eid),E(label))
        for eid,label in engines.options())
    return ENGINE_MENU % dict(label=E(engines.label(selected)),rows=rows)


def filter_bar(ctx, what):
    """The period + engine bar for any tab. `what` names what the tab shows."""
    n=len(ctx['ids'])
    span=period.describe(ctx['a'],ctx['b'])
    picked=ctx.get('engines') or engines.all_ids()
    # `what` and the scan-count summary are kept out of the bar deliberately:
    # the empty state and the panels already say what period they cover.
    return FILTER_BAR % engine_menu(picked)


EMPTY='<div class="panel-empty"><b>No scans in this period</b><span>Choose a longer date range to see results.</span></div>'

# Answers arrived, but not one of them named a buyable product. On AI Overview
# that is common: it often replies with advice ("use a gentle cleanser") and
# names nobody. Showing a bare 0% there would read as "you are invisible" when
# the truth is "nothing was recommended to anyone, including your rivals" -
# a different finding, and one the merchant cannot fix by changing a product page.
NO_PRODUCTS=('<div class="panel-empty"><b>No products recommended</b>'
             '<span>%s answered, but named no specific product to buy &mdash; '
             'not yours and not a competitor’s. Nothing to rank.</span></div>')


def engine_phrase(ctx,the=False):
    """How to name the engines in a sentence: one name, or a collective."""
    picked=(ctx or {}).get('engines') or engines.all_ids()
    if len(picked)==1:
        return config.engine_label(picked[0])
    return 'The selected engines' if the else 'the selected engines'


def ranking_products(history, ctx, p):
    """One stable product cohort across history, with the same answer scope.

    Selected products include zero mentions. Every product uses the overview's
    answers, so list rates, trend rates and share denominators are comparable.
    """
    ids=[h['id'] for h in history]
    answers, mentions=evidence.load(ids,p)
    aid_scan={a['id']:a['scan_id'] for a in answers}
    period_aids={a['id'] for a in answers if a['scan_id'] in ctx['ids']}
    period_mentions=sum(1 for m in mentions if m['answer_id'] in period_aids)
    # A mention with no product name is a shop recommendation ("Roble.Store"):
    # it still counts in brand share of voice, but it is not a product, so it
    # has no row here (Kelian, 2026-09-25).
    rows=[r for r in products(ids,p) if not r['own'] and r['words']]
    for item in p['_catalog']:
        if item['id'] not in p['_ps']['product_ids']:
            continue
        selected=evidence.product_context(p['_ps'],item['id'])
        scope=set(evidence.relevant_questions(p))
        selected['_ps']=dict(selected['_ps'],relevance=[
            [item['id']] if q in scope else [] for q in selected['_ps']['prompts']])
        row=next(r for r in products(ids,selected) if r['own'])
        row.update(key='product:'+str(item['id']),image=item['image'])
        rows.append(row)
    out=[]
    for r in rows:
        hits={a:rank for a,rank in r['hits'].items() if a in period_aids}
        counts=r.get('counts',{})
        count=sum(v for a,v in counts.items() if a in period_aids)
        if not hits and not r['own']:
            continue
        per_scan={}
        for h in history:
            ranks=[rank for a,rank in r['hits'].items() if aid_scan.get(a)==h['id']]
            per_scan[str(h['id'])]=dict(hits=len(ranks),ranks=sum(ranks),
                count=sum(v for a,v in counts.items() if aid_scan.get(a)==h['id']))
        r.update(rate=100*len(hits)/len(period_aids) if period_aids else 0,
                 share=100*count/period_mentions if period_mentions else 0,
                 avg=sum(hits.values())/len(hits) if hits else None,
                 count=count,scan=per_scan)
        out.append(r)
    return sorted(out,key=lambda r:(-r['rate'],r['avg'] or 999,r['name']))


def render(s, ps, p, sc, ctx=None):
    from dashboard import date
    ctx=ctx or period_context(ps,p,{})
    if p['id'] is not None:
        return render_product(s,ps,p,sc,ctx)
    rows,own,has_data=ctx['rows'],ctx['own'],bool(ctx['own']['answers'])
    market=market_rows(ctx['ids'],p)
    competitors=market[1:6]
    tracked=[market[0]]+competitors
    questions=evidence.relevant_questions(p)

    # Chart data: every finished scan (the browser picks the ones in the period).
    history=period.done_scans(ps['id'])
    scans=[]
    for h in history:
        hist={r['key']:r for r in market_rows(h['id'],p)}
        n=hist['own']['answers']
        mine=hist['own']['hits']
        # Raw mention counts, not percentages: a bucket holding several scans
        # has to pool them by weight, which a stored percentage cannot do.
        _answers,_mentions=evidence.load(h['id'],p)
        scans.append(dict(id=h['id'],ts=h['run_at'],n=n,own=[len(mine),sum(mine.values())],
                          comp=[len(hist.get(r['key'],{}).get('hits',{})) for r in competitors],
                          mt=len(_mentions),
                          sv=[hist['own']['count']]+[hist.get(r['key'],{}).get('count',0) for r in competitors]))
    # Assign the displayed cohort unique colours, independent of its ranking.
    # The same mapping feeds every primary chart mode.
    brand_palette=['#3282ff','#8b4dff','#f52f98','#2fb8d6','#7d8079']
    brand_colors={r['name']:brand_palette[i] for i,r in enumerate(sorted(competitors,key=lambda r:r['name'].casefold()))}
    brand_colors[tracked[0]['name']]='#32bd83'
    series=[dict(name=r['name'],brand=('Your selected products' if r['own'] else 'All mentioned products'),color=brand_colors[r['name']]) for r in tracked]
    chart_data=json.dumps(dict(series=series,scans=scans)).replace('<','\\u003c')

    result=filter_bar(ctx,'every panel combined')
    if evidence.state(p)!='Measured':
        result+='<p class="coverage-note">'+E(evidence.state(p))+' — this product is outside the measured buyer-question coverage.</p>'

    switches='<span class="small" style="margin-left:auto" id="vis-group-label">%s</span>' % period.GROUPS[ctx['per']['group']]
    rate='%.0f' % own['rate'] if has_data else '—'
    # Headline numbers sit in one strip above the panels, so the page has a
    # single place to read "how am I doing" before any chart is interpreted.
    thing='catalog' if p['id'] is None else 'product'
    detail=json.loads(sc['detail'] or '{}')

    # The market chart uses one consistent cohort; saved six-vs-six groups
    # retain their own explicit denominator in competitor_comparison.
    compare=[dict(name=r['name'],own=r['own'],logo='/icon?d='+ (p['store_domain'] if r['own'] else brand_site(next((x for x in rows if norm(x['brand'])==norm(r['brand'])),r))),color=brand_colors[r['name']],rate=r['rate'] if has_data else None,
                  share=r['share'] if has_data else None,avg=r['avg'] if has_data else None)
             for r in tracked]
    compare_source='brands mentioned in the same answers'

    in_period=[x for x in scans if x['id'] in set(ctx['ids']) and x['n']]
    # Visibility = the newest scan, like the bars it opens (5 Oct 2026).
    latest_rate=(100*in_period[-1]['own'][0]/in_period[-1]['n']) if in_period else None
    def num(v,suffix=''):
        return ('%.0f%s'%(v,suffix)) if v is not None else '<span class="stat-dash">&mdash;</span>'

    def kpi(mode,label,sub,info,value):
        tip='<span class="heading-info" title="%s" aria-label="%s">i</span>'%(E(info),E(info)) if info else ''
        return ('<button type="button" class="kpi-cell" data-mode="%s" aria-pressed="false">'
                '<span class="kpi-label">%s%s</span><strong>%s%s</strong></button>'
                )%(E(mode),E(label),tip,value,('<small>%s</small>'%E(sub)) if sub else '')

    rate_txt='%.0f'%own['rate'] if has_data else '&mdash;'
    # Change figures compare with the period just before, product pages only.
    prev=previous_own(ps,p,ctx) if p['id'] is not None and has_data else None
    strip='<div class="kpi-strip%s" role="group" aria-label="Choose what the chart shows">'%(' kpi-strip-six' if p['id'] is not None else '')
    strip+=kpi('overtime','Avg. visibility','',
        'The average of every date on the chart: each date counts once, '
        'whatever its size. Your %s.'%thing,
        '<span class="vis-num %s" id="vis-rate" data-v="%s" data-d="0">%s</span><small class="kpi-unit">%%</small>'%(
            'count' if has_data else '',rate_txt,rate_txt)+(change(own['rate'],prev['rate'],'pp') if prev else ''))
    latest_txt='%.0f'%latest_rate if latest_rate is not None else '&mdash;'
    strip+=kpi('visibility','Visibility','latest',
        'Your newest scan in this period, set against %s.'%(compare_source or 'competitors'),
        '<span class="vis-num %s" id="vis-latest" data-v="%s" data-d="0">%s</span><small class="kpi-unit">%%</small>'%(
            'count' if latest_rate is not None else '',latest_txt,latest_txt)
        if latest_rate is not None else '<span class="stat-dash">&mdash;</span>')
    tracked_share=sum(r['share'] for r in rows if r['own'] or norm(r['brand']) in
                      {norm(t['brand']) for t in tracked[1:]}) if has_data else 0
    untracked=max(0,100-tracked_share)
    strip+=kpi('sov','Share of voice',
        ('%.0f%% untracked'%untracked) if has_data else '',
        'Your share of every product recommendation in these answers. The '
        'sub-label is the share held by products outside your catalog and the '
        'products on this chart.',
        (('%.1f<small class="kpi-unit">%%</small>'%own['share'])+(change(own['share'],prev['share'],'pp') if prev else '')) if has_data else '&mdash;')
    strip+=kpi('position','Position','1 = first',
        'Average place in the answer when named. Lower is better.',
        ('<b id="vis-pos">#%.1f</b>'%own['avg']+(change(own['avg'],prev['avg'],'',True) if prev and prev['avg'] else '')) if has_data and own['avg']
        else '<b id="vis-pos"><span class="stat-dash">&mdash;</span></b>')
    if p['id'] is not None:
        def stat(label,info,value):
            return ('<div class="kpi-cell kpi-static"><span class="kpi-label">%s<span class="heading-info" title="%s" aria-label="%s">i</span></span>'
                    '<strong>%s</strong></div>')%(E(label),E(info),E(info),value)
        n_hits=len(own['hits'])
        strip+=stat('Appearances','Number of AI answers in this period that mention this product.',
            ('%d'%n_hits+(change(n_hits,len(prev['hits']),'',digits=0) if prev else '')) if has_data else '&mdash;')
        quoted=mentioned_price(own.get('prices'))
        strip+=stat('Mentioned price','The price AI answers quote for this product: the middle of all quotes in this period. Only answers collected since price tracking began (22 Sep 2026) are counted.',
            ('%s<small>%d quote%s</small>'%(E(quoted['text']),quoted['quotes'],'' if quoted['quotes']==1 else 's')) if quoted else '<span class="stat-dash">&mdash;</span><small>no price quoted</small>')
        win=win_rate(own)
        strip+=stat('Win rate','Of the answers that mention this product, the share where it is the #1 recommendation.',
            ('%.0f<small class="kpi-unit">%%</small>'%win+(change(win,win_rate(prev),'pp',digits=0) if prev else '')) if win is not None else '&mdash;')
    # The rankings column starts level with the KPI strip, so its header sits
    # in the same row as the four figures and the list reads as an equal part
    # of the card rather than a panel tucked beside the chart.
    result+='<div class="analysis-card"><div class="analysis-main">'+strip+'</div>'
    ranking_rows=[]
    if has_data:
        tr=''
        ranking_rows=ranking_products(history,ctx,p)
        for i,r in enumerate(ranking_rows):
            tr+='<tr class="%s" data-product="%d" data-own="%s"><td class="rank-number">%d</td><td><div class="rank-product"><i class="rank-dot"></i>%s<div><b>%s</b><span>%s%s</span></div></div></td><td class="num">%.0f%%</td><td class="num">%.1f%%</td><td class="num">%s</td></tr>' % (
                'rank-own' if r['own'] else '',i,str(r['own']).lower(),i+1,thumb(r,p),E(r['name']),E(display_brand(r['brand'])),
                ' <em>Selected</em>' if r['own'] else '',r['rate'],r['share'],'%.1f'%r['avg'] if r['avg'] else '—')
        ranking='<div class="ranking-scroll" tabindex="0" aria-label="Product rankings; scroll to compare more products"><table class="product-rankings"><thead><tr><th>#</th><th>Product</th><th class="num">Mentioned in</th><th class="num">SOV</th><th class="num">Avg. pos.</th></tr></thead><tbody>'+tr+'</tbody></table></div><div class="ranking-footer" id="ranking-status" aria-live="polite">Scroll to compare products</div>'

    else:
        ranking=EMPTY
    # Zero MENTIONS, not zero rows: the merchant's own products are always
    # listed, at zero, so the rankings are never actually empty. What marks
    # "nothing was recommended to anyone" is that no mention was found at all.
    if has_data and not sum(r['count'] for r in rows):
        ranking=NO_PRODUCTS % E(engine_phrase(ctx,the=True))
    visibility='<div class="visibility-plot"><svg id="visibility-chart" viewBox="0 0 660 260" role="img" aria-label="Product visibility chart"></svg><div id="chart-tooltip" class="chart-tooltip" role="status"></div></div><div id="trend-change" class="trend-change" role="status"></div><div id="chart-legend" class="chart-legend"></div>'
    visibility+='<div class="chart-footer"><span id="chart-note">First scan saved</span></div><details class="chart-evidence"><summary>View scan history as a table</summary><table><thead><tr><th>Scan</th><th>Mentioned in</th></tr></thead><tbody>'+''.join('<tr><td>%s%s</td><td>%s</td></tr>' % (date(h['run_at']),' · Partial' if h['status']=='partial' else '',('%.0f%% of answers'%(100*x['own'][0]/x['n'])) if x['n'] else 'Not measured') for h,x in zip(history,scans))+'</tbody></table></details>'
    mentions=sum(r['count'] for r in rows) if has_data else 0
    rank_info='Every product %s recommended in this period, most-named first.'%engine_phrase(ctx)
    result+=('<div class="rank-head"><span class="kpi-label">Product rankings'
             '<span class="heading-info" title="%s" aria-label="%s">i</span></span>'
             '<strong>%s<small>%s</small></strong><div class="rank-controls"><label class="sr-only" for="rank-scope">Products to show</label><select id="rank-scope"><option value="all">All products</option><option value="mine">My products</option></select><details class="rank-options"><summary aria-label="Comparison options">···</summary><div><label for="rank-count">Number of products</label><select id="rank-count"><option>7</option><option>14</option><option>21</option><option>28</option><option value="100000">All</option></select></div></details></div></div>')%(
        E(rank_info),E(rank_info),mentions,' mention' if mentions==1 else ' mentions')
    # Four grid children, not two nested columns: the strip and the rankings
    # header share a grid row, so they are the same height without either one
    # padding itself out to guess the other's.
    result+=box('Visibility over time','Individual products from the visible ranking rows, measured against the same saved answers. Headline figures describe your selected catalog.',visibility,'visibility-card','chart',switches)
    result+=box('Product rankings','Ranked by how often %s name each one in this period.'%engine_phrase(ctx)
                if len((ctx or {}).get('engines') or engines.all_ids())>1
                else 'Ranked by how often %s names each one in this period.'%engine_phrase(ctx),
                ranking,'ranking-card','rank')
    result+='</div></div>'
    if p['id'] is not None:
        result+=product_sections(p,ctx)
    # The "Your six vs competitor's six" panels were removed from the
    # dashboard on 2026-09-25 (Kelian). The main comparison above already
    # measures the catalog against every competitor found in the answers.
    if p['id'] is None:
        from dashboard import catalog_table
        result+=catalog_table(s,ps,p,ctx)
    if p['id'] is None:
        result=re.sub(r'\bYour product\b','Your catalog',result).replace('YOUR PRODUCT','YOUR CATALOG')
        result=re.sub(r'\byour product\b','your catalog',result).replace('<em>Your catalog</em>','<em>Your product</em>')
    result+='<script type="application/json" id="compare-data">'+json.dumps(dict(rows=compare,source=compare_source)).replace('<','\\u003c')+'</script>'
    result+='<script type="application/json" id="ranking-data">'+json.dumps([dict((k,r[k]) for k in ('key','name','brand','own','rate','share','avg','scan','count')) for r in ranking_rows]).replace('<','\\u003c')+'</script>'
    return result+'<script type="application/json" id="visibility-data">'+chart_data+'</script>'+FILTER_SCRIPT+CHART_SCRIPT


def previous_own(ps, p, ctx):
    """The same product over the period just before this one, or None."""
    days=(ctx['b']-ctx['a']).days+1
    start=time.mktime(ctx['a'].timetuple())
    ids=[x['id'] for x in period.done_scans(ps['id'],start-days*86400,start-0.001)]
    if not ids:
        return None
    own=next(r for r in products(ids,p) if r['own'])
    return own if own['answers'] else None


def win_rate(row):
    ranks=list(row['hits'].values())
    return 100*sum(1 for r in ranks if r==1)/len(ranks) if ranks else None


def change(now, before, unit='', low_best=False, digits=1):
    """Green when better, red when worse; nothing when there is no earlier period."""
    if now is None or before is None:
        return ''
    d=round(now-before,digits)
    if not d:
        return '<span class="kpi-delta">±0%s</span>'%unit
    good=(d<0) if low_best else (d>0)
    return '<span class="kpi-delta %s">%s%s%s</span>'%('up' if good else 'down','+' if d>0 else '−',('%.'+str(digits)+'f')%abs(d),unit)


def _median(v):
    v=sorted(v); n=len(v)
    return (v[n//2] if n%2 else (v[n//2-1]+v[n//2])/2) if n else None


def rank_sentence(row):
    """One plain sentence about where a product ranks."""
    ranks=list(row['hits'].values())
    name=row['name'] if row['own'] else '%s (%s)'%(row['name'],display_brand(row['brand'])) if row.get('brand') else row['name']
    if not ranks:
        return '%s has not been named in an answer in this period.'%name
    n=len(ranks); ans='answer' if n==1 else 'answers'
    if len(set(ranks))==1:
        return '%s was named #%d in %s %d %s that mentioned it.'%(name,ranks[0],'all' if n>1 else 'the',n,ans)
    first=sum(1 for r in ranks if r==1)
    extra=' It was the first pick in %d of them.'%first if first else ''
    return '%s was usually named #%g, ranging from #%g to #%g across %d %s.%s'%(name,_median(ranks),min(ranks),max(ranks),n,ans,extra)


def product_sections(p, ctx, parts=False):
    """Co-featured products and position vs competitors, for one product."""
    rows,own=ctx['rows'],ctx['own']
    def head(title,sub):
        return '<div class="pp-head"><h2>%s<span class="heading-info" title="%s" aria-label="%s">i</span></h2><p>%s</p></div>'%(E(title),E(sub),E(sub),E(sub))
    seen=set(own['hits'])
    # A product AI never names has no co-featured products. Show what AI
    # recommends for its buyer questions instead: the question an invisible
    # merchant actually has (5 Oct 2026).
    instead=not seen
    co=[r for r in rows if not r['own'] and (r['hits'] if instead else seen & set(r['hits']))]
    co.sort(key=lambda r:(-r['rate'],r['avg'] or 99,r['name']))
    co=co[:8]
    if co:
        top=max(r['rate'] for r in co) or 1
        bars=''.join('<li><span class="pp-bar" style="width:%.1f%%"></span>%s<span class="pp-name"><b>%s</b><small>%s</small></span><span class="pp-val">%.0f%%</span></li>'%(
            max(18,100*r['rate']/top),thumb(r,p),E(r['name']),E(display_brand(r['brand'])),r['rate']) for r in co)
        cofeat='<div class="pp-card"><div class="pp-card-head"><span>%s</span><span>Visibility</span></div><ol class="pp-bars">'%('Recommended instead' if instead else 'Co-featured products')+bars+'</ol></div>'
    else:
        cofeat='<div class="pp-card"><div class="pp-card-head"><span>Co-featured products</span></div>'+('<div class="panel-empty"><b>No co-featured products yet</b><span>Products named alongside yours will appear here.</span></div>')+'</div>'

    # Position vs competitors, as Peec draws it: one vertical box per product,
    # ordered by how often each appears. Whiskers = best and worst rank, box =
    # middle 50%, line = median. Your product is red and its label bold.
    field=[own]+sorted(co,key=lambda r:-len(r['hits']))[:4]
    field=sorted([r for r in field if r['hits']],key=lambda r:(-len(r['hits']),not r['own']))
    if field:
        def quart(v,q):
            v=sorted(v); i=(len(v)-1)*q; lo=int(i)
            return v[lo]+(v[min(lo+1,len(v)-1)]-v[lo])*(i-lo)
        worst=max(5,max(max(r['hits'].values()) for r in field))
        worst+=worst%2==0   # odd bottom tick, so #1, #3, #5 ... line up
        W,H,L,T,B=1000,300,56,16,14
        cols=len(field); cw=(W-L)/cols; bw=min(150,cw*.5)
        Y=lambda r:T+(H-T-B)*(r-1)/(worst-1)
        palette=['#1f4b7a','#6d63e0','#1ba5cf','#e0843a']
        svg='<svg class="pv-chart" viewBox="0 0 %d %d" role="img" aria-label="Rank distribution per product">'%(W,H)

        for t in range(1,worst+1,2):
            svg+='<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/><text x="8" y="%.1f" class="ax">#%d</text>'%(L-6,W,Y(t),Y(t),Y(t)+4,t)
        labels=''; k=0
        for i,r in enumerate(field):
            ranks=list(r['hits'].values())
            lo,q1,med,q3,hi=min(ranks),quart(ranks,.25),_median(ranks),quart(ranks,.75),max(ranks)
            if r['own']:
                col='#d9424a'
            else:
                col=palette[k%len(palette)]; k+=1
            cx=L+cw*(i+.5); x0=cx-bw/2
            # A box needs some height to read as a box when every rank is the same.
            by0,by1=Y(q1),Y(q3)
            if by1-by0<14:
                mid=(by0+by1)/2; by0,by1=mid-7,mid+7
            tip='%s · best #%g, median #%g, worst #%g · %d answer%s'%(r['name'],lo,med,hi,len(ranks),'' if len(ranks)==1 else 's')
            svg+=('<g class="pv-box%s" style="--c:%s" data-said="%s" tabindex="0" role="button" aria-label="%s"><title>%s</title>'
                  +'<rect class="pv-lane" x="%.1f" y="%d" width="%.1f" height="%d" rx="8"/>'%(L+cw*i+cw*.12,T-8,cw*.76,H-T-B+16)+
                  '<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" class="whisk"/>'
                  '<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" class="cap"/><line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" class="cap"/>'
                  '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3"/>'
                  '<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" class="med"/></g>')%(
                ' on' if r['own'] else '',col,E(rank_sentence(r)),E('Explain '+r['name']),E(tip),cx,cx,Y(lo),Y(hi),cx-bw/3,cx+bw/3,Y(lo),Y(lo),cx-bw/3,cx+bw/3,Y(hi),Y(hi),
                x0,by0,bw,by1-by0,x0,x0+bw,Y(med),Y(med))
            labels+='<span class="pv-label%s">%s<b>%s</b></span>'%(' own' if r['own'] else '',thumb(r,p),E(r['name']))
        svg+='</svg>'
        # "How to read this": a labelled example box and one plain sentence
        # about the merchant's own product.
        said=rank_sentence(own)
        key=('<div class="pv-key"><svg viewBox="0 0 150 120" aria-hidden="true">'
             '<line x1="30" x2="30" y1="12" y2="108" class="k"/><line x1="18" x2="42" y1="12" y2="12" class="k"/><line x1="18" x2="42" y1="108" y2="108" class="k"/>'
             '<rect x="14" y="36" width="32" height="40" rx="3" class="kb"/><line x1="14" x2="46" y1="54" y2="54" class="k km"/>'
             '<text x="54" y="16">Best rank</text><text x="54" y="58">Median rank</text><text x="54" y="80">Usual range</text><text x="54" y="112">Worst rank</text></svg>'
             '<div><b>How to read this</b><p>Each column is one product. Higher up is better: #1 means the AI named it first. '
             'The line inside the box is its typical rank, the box holds the middle half of its rankings, and the whiskers reach its best and worst. '
             'A short box near #1 means the AI reliably puts it at the top; a tall box means its position varies from answer to answer.</p>'
             '<p class="pv-said" aria-live="polite">'+E(said)+'</p><p class="pv-hint">Click a column to explain that product.</p></div></div>')
        pos=('<div class="pp-card"><div class="pp-card-head"><span>Position vs competitors</span></div>'
             '<div class="pv-wrap">'+svg+'<div class="pv-labels" style="grid-template-columns:repeat(%d,minmax(0,1fr))">'%cols+labels+'</div></div>'+key+'</div>')
    else:
        pos='<div class="pp-card"><div class="pp-card-head"><span>Position vs competitors</span></div><div class="panel-empty"><b>No positions yet</b><span>Positions appear once this product is named in an answer.</span></div></div>'
    if parts:
        if instead and co:
            return (head('Recommended instead','Products AI recommends for this product\'s buyer questions, where this product is not named.')+cofeat,
                    head('Position vs competitors','Where the products AI recommends instead usually rank (#1 is best). Yours appears here once it is named.')+pos)
        return (head('Co-featured products','Products that appear in the same AI answers as this one.')+cofeat,
                head('Position vs competitors','How this product ranks against competitors in AI answers (#1 is best), ordered by how often each appears. The line is the median rank; the box spans the middle 50%.')+pos)
    return ('<div class="pp-grid"><section>'+head('Co-featured products','Products named in the same AI answers as this one, by how often each appears.')+cofeat+'</section>'
            '<section>'+head('Position vs competitors','Where this product ranks against the products it appears with (#1 is best). The dot is the median rank; the bar spans best to worst.')+pos+'</section></div>')


def _nice_max(v, floor):
    """A round axis top at or above v."""
    v=max(v,floor)
    for step in (1,2,5,10,20,25,50,100):
        top=math.ceil(v/step)*step
        if top/step<=6:
            return top
    return math.ceil(v/100)*100


def _smooth(points):
    """SVG path through the points with gentle curves, like Peec's lines."""
    if not points:
        return ''
    d='M%.1f %.1f'%points[0]
    for (x0,y0),(x1,y1) in zip(points,points[1:]):
        mx=(x0+x1)/2
        d+=' C%.1f %.1f %.1f %.1f %.1f %.1f'%(mx,y0,mx,y1,x1,y1)
    return d


def trend_chart(ps, p, ctx):
    """Visibility (left axis) and win rate (right axis) per period bucket."""
    group=ctx['per']['group']
    if group=='quarter':
        group='month'
    buckets={}
    for sc in ctx['scans']:
        own=next(r for r in products([sc['id']],p) if r['own'])
        if not own['answers']:
            continue
        day=storetime.date_of(sc['run_at'],ctx.get('tz'))
        b=buckets.setdefault(period.bucket_start(day,group),dict(n=0,hits=0,wins=0))
        b['n']+=own['answers']; b['hits']+=len(own['hits'])
        b['wins']+=sum(1 for r in own['hits'].values() if r==1)
    # Every bucket in the period gets an axis slot; only measured ones get a point.
    slots=[]; d=period.bucket_start(ctx['a'],group)
    while d<=ctx['b']:
        slots.append(d); d=period.next_bucket(d,group)
    # Start at the first measured bucket (rule of 2026-09-20): leading empty
    # dates only push the line into a corner. A lone reading keeps context.
    measured=[i for i,s in enumerate(slots) if s in buckets]
    if len(measured)>1:
        slots=slots[measured[0]:]
    pts=[(i,buckets[s]) for i,s in enumerate(slots) if s in buckets]
    W,H,L,R,T,B=640,300,46,50,18,34
    vis=[(i,100*b['hits']/b['n']) for i,b in pts]
    win=[(i,100*b['wins']/b['hits']) for i,b in pts if b['hits']]
    # Round axis tops that split into four clean steps; win rate stops at 100%.
    vmax=max([v for _,v in vis] or [0])*1.1
    vtop=next((t for t in (4,8,12,20,40,60,80,100) if t>=vmax),100)
    wmax=max([v for _,v in win] or [0])
    wtop=next((t for t in (20,40,60,80,100) if t>=wmax),100)
    n=max(1,len(slots)-1)
    X=lambda i:L+(W-L-R)*(i/n if len(slots)>1 else .5)
    Yv=lambda v:T+(H-T-B)*(1-v/vtop)
    Yw=lambda v:T+(H-T-B)*(1-v/wtop)
    svg='<svg class="pp-chart" viewBox="0 0 %d %d" role="img" aria-label="Visibility and win rate over time">'%(W,H)
    svg+=('<defs><linearGradient id="pk-vis-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#3b73e0" stop-opacity=".22"/><stop offset="1" stop-color="#3b73e0" stop-opacity="0"/></linearGradient>'
          '<linearGradient id="pk-win-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#d9424a" stop-opacity=".05"/><stop offset="1" stop-color="#d9424a" stop-opacity="0"/></linearGradient></defs>')
    for k in range(5):
        y=T+(H-T-B)*k/4
        svg+='<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/>'%(L,W-R,y,y)
        svg+='<text x="%d" y="%.1f" class="ax" text-anchor="end">%s%%</text>'%(L-10,y+4,('%g'%round(vtop*(1-k/4),1)))
        svg+='<text x="%d" y="%.1f" class="ax">%s%%</text>'%(W-R+10,y+4,('%g'%round(wtop*(1-k/4))))
    step=max(1,math.ceil(len(slots)/6))
    for i,s in enumerate(slots):
        if i%step==0 or i==len(slots)-1 and len(slots)<=6:
            svg+='<text x="%.1f" y="%d" class="ax" text-anchor="middle">%s</text>'%(X(i),H-10,E('%d %s'%(s.day,s.strftime('%b'))))
    for series,Y,cls,label in ((vis,Yv,'vis','Visibility'),(win,Yw,'win','Win rate')):
        xy=[(X(i),Y(v)) for i,v in series]
        if len(xy)>1:
            # Soft gradient fill under each line, down to the 0% baseline.
            svg+='<path d="%s L%.1f %.1f L%.1f %.1f Z" class="area %s"/>'%(_smooth(xy),xy[-1][0],H-B,xy[0][0],H-B,cls)
            svg+='<path d="%s" class="line plot-line %s"/>'%(_smooth(xy),cls)
        for (i,v),(x,y) in zip(series,xy):
            svg+='<circle cx="%.1f" cy="%.1f" r="3.5" class="dot %s"><title>%s · %s %.0f%%</title></circle>'%(x,y,cls,E('%d %s'%(slots[i].day,slots[i].strftime('%b'))),label,v)
    # Hover guide: one entry per measured bucket, read by PK_SCRIPT.
    hover=[dict(x=round(X(i),1),label='%d %s'%(slots[i].day,slots[i].strftime('%b %Y')),
                vis=round(100*b['hits']/b['n'],1),win=round(100*b['wins']/b['hits']) if b['hits'] else None,
                n=b['n'],yv=round(Yv(100*b['hits']/b['n']),1),yw=round(Yw(100*b['wins']/b['hits']),1) if b['hits'] else None)
           for i,b in pts]
    svg+='<line class="guide" x1="0" x2="0" y1="%d" y2="%d" visibility="hidden"/><circle class="hover-dot vis" r="5" visibility="hidden"/><circle class="hover-dot win" r="5" visibility="hidden"/>'%(T,H-B)
    svg+='<rect class="hover-zone" x="%d" y="%d" width="%d" height="%d" fill="transparent"/>'%(L,T,W-L-R,H-T-B)
    svg+='</svg><div class="pk-tip" role="status" hidden></div>'
    svg+='<script type="application/json" class="pk-data">%s</script>'%json.dumps(dict(w=W,points=hover)).replace('<','\\u003c')
    if not pts:
        svg+='<div class="pp-chart-empty">No scans in this period</div>'
    return svg


def render_product(s, ps, p, sc, ctx):
    """A single product, laid out like Peec's product view."""
    own,has=ctx['own'],bool(ctx['own']['answers'])
    prev=previous_own(ps,p,ctx) if has else None
    result=filter_bar(ctx,'every panel combined')
    if evidence.state(p)!='Measured':
        result+='<p class="coverage-note">'+E(evidence.state(p))+' — this product is outside the measured buyer-question coverage.</p>'
    dash='<span class="stat-dash">&mdash;</span>'
    def cell(label,info,value,note=''):
        return ('<div class="pk-cell"><span class="pk-label">%s<span class="heading-info" title="%s" aria-label="%s">i</span></span>'
                '<strong>%s</strong>%s</div>')%(E(label),E(info),E(info),value,('<small class="pk-note">%s</small>'%E(note)) if note else '')
    win=win_rate(own) if has else None
    quoted=mentioned_price(own.get('prices')) if has else None
    store=db.one('SELECT currency FROM stores WHERE domain=?',(p['store_domain'],))
    import catalog as catalog_mod
    symbol=catalog_mod.SYMBOLS.get((store['currency'] if store else '') or '','')
    # Variant range when the catalog read recorded one, else the single price.
    rng=json.loads(p.get('raw_json') or '{}').get('price_range') or []
    lo,hi=(rng[0],rng[1]) if len(rng)==2 else (p.get('price'),p.get('price'))
    def money(v):
        v=float(v); return symbol+(('%.0f'%v) if v==int(v) else ('%.2f'%v))
    try:
        catalog_price=(money(lo) if float(lo)==float(hi) else money(lo)+' – '+money(hi)) if lo else dash
    except (TypeError,ValueError):
        catalog_price=dash
    strip='<div class="pk-strip">'
    # The catalog table divides by every catalog answer; this page divides by
    # the answers to this product's own questions. Say so, or 3% vs 6% looks
    # like a bug (5 Oct 2026).
    nq=len(evidence.relevant_questions(p))
    strip+=cell('Visibility','Share of AI answers to this product\'s buyer questions that mention it. The catalog table divides by every answer in the catalog, so it shows a lower figure.',
        ('%s%%'%('%.1f'%own['rate'] if 0<own['rate']<1 else '%.0f'%own['rate'])+(change(own['rate'],prev['rate'],'pp') if prev else '')) if has else dash,
        ('of %d answers to its %d question%s'%(own.get('answers',0),nq,'' if nq==1 else 's')) if has and own.get('answers') else '')
    strip+=cell('Position','Average position when mentioned. #1 = named first.',
        ('#%.1f'%own['avg']+(change(own['avg'],prev['avg'],'',True) if prev and prev['avg'] else '')) if has and own['avg'] else dash)
    strip+=cell('Appearances','Number of AI answers in this period that mention this product.',
        ('%d'%len(own['hits'])+(change(len(own['hits']),len(prev['hits']),'',digits=0) if prev else '')) if has else dash)
    strip+=cell('Mentioned price','The price AI answers quote for this product: the middle of all quotes in this period. Counted from answers collected since 22 Sep 2026.',
        E(quoted['text']) if quoted else dash,
        ('from %d answer%s'%(quoted['quotes'],'' if quoted['quotes']==1 else 's')
         +(' · quoted in %s, your store prices in %s'%(quoted['text'][0],symbol) if symbol and quoted['text'][:1] in '€$£¥₹' and quoted['text'][:1]!=symbol else '')) if quoted else '')
    strip+=cell('Catalog price','The price on your own store for this product.',catalog_price)
    strip+=cell('Win rate','Of the answers that mention this product, the share where it is the #1 recommendation.',
        ('%.0f%%'%win+(change(win,win_rate(prev),'pp',digits=0) if prev else '')) if win is not None else dash)
    strip+='</div>'
    group=ctx['per']['group']
    toggle=''.join('<button type="button" data-pk-group="%s" aria-pressed="%s">%s</button>'%(g,str(group==g or (g=='month' and group=='quarter')).lower(),t) for g,t in (('day','D'),('week','W'),('month','M')))
    chart=('<div class="pp-card pk-chart-card"><div class="pp-card-head"><span>Visibility &amp; win rate</span><span class="pk-toggle">%s</span></div>%s'
           '<p class="pk-legend"><i class="vis"></i>Visibility <i class="win"></i>Win rate</p></div>')%(toggle,trend_chart(ps,p,ctx))
    cofeat,pos=product_sections(p,ctx,parts=True)
    def head(title,sub):
        return '<div class="pp-head"><h2>%s<span class="heading-info" title="%s" aria-label="%s">i</span></h2><p>%s</p></div>'%(E(title),E(sub),E(sub),E(sub))
    result+=strip
    result+='<div class="pp-grid"><section>'+head('Visibility & win rate','Share of AI answers mentioning this product, and its win rate, over time.')+chart+'</section><section>'+cofeat+'</section></div>'
    result+='<div class="pp-full">'+pos+'</div>'
    result+=FILTER_SCRIPT+PK_SCRIPT
    return result


PK_SCRIPT='''<script>
document.querySelectorAll('.pv-chart').forEach(svg=>{
  const card=svg.closest('.pp-card'),said=card&&card.querySelector('.pv-said');
  function pick(g){svg.querySelectorAll('.pv-box').forEach(x=>x.classList.toggle('on',x===g));if(said)said.textContent=g.dataset.said;}
  svg.querySelectorAll('.pv-box').forEach(g=>{g.addEventListener('click',()=>pick(g));
    g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(g);}});});});
document.querySelectorAll('.pk-chart-card').forEach(card=>{
  const svg=card.querySelector('.pp-chart'),data=JSON.parse((card.querySelector('.pk-data')||{}).textContent||'{"points":[]}');
  if(!svg||!data.points.length)return;
  const tip=card.querySelector('.pk-tip'),guide=svg.querySelector('.guide'),dv=svg.querySelector('.hover-dot.vis'),dw=svg.querySelector('.hover-dot.win');
  function hide(){[guide,dv,dw].forEach(e=>e.setAttribute('visibility','hidden'));tip.hidden=true;}
  function show(e){
    const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)*data.w/r.width;
    const p=data.points.reduce((a,b)=>Math.abs(b.x-x)<Math.abs(a.x-x)?b:a);
    guide.setAttribute('x1',p.x);guide.setAttribute('x2',p.x);guide.setAttribute('visibility','visible');
    dv.setAttribute('cx',p.x);dv.setAttribute('cy',p.yv);dv.setAttribute('visibility','visible');
    if(p.yw!=null){dw.setAttribute('cx',p.x);dw.setAttribute('cy',p.yw);dw.setAttribute('visibility','visible');}else dw.setAttribute('visibility','hidden');
    tip.innerHTML='<b>'+p.label+'</b><div><i class="vis"></i>Visibility<strong>'+p.vis+'%</strong></div><div><i class="win"></i>Win rate<strong>'+(p.win==null?'—':p.win+'%')+'</strong></div><small>'+p.n+' answers</small>';
    tip.hidden=false;
    const px=p.x*r.width/data.w+svg.offsetLeft;
    tip.style.left=Math.min(Math.max(px-tip.offsetWidth/2,8),card.clientWidth-tip.offsetWidth-8)+'px';}
  svg.addEventListener('pointermove',show);svg.addEventListener('pointerleave',hide);});
document.querySelectorAll('[data-pk-group]').forEach(b=>b.addEventListener('click',()=>{
  const u=new URL(location.href);u.searchParams.set('group',b.dataset.pkGroup);
  try{const k='produkto-period',s=JSON.parse(localStorage.getItem(k)||'null');if(s){s.group=b.dataset.pkGroup;localStorage.setItem(k,JSON.stringify(s));}}catch(e){}
  location.href=u.toString();}));
</script>'''


FILTER_BAR = '''<!--filter-bar--><div class="filter-bar" id="filter-bar">
 <div class="fb-group">
  <button type="button" class="fb-btn" id="range-btn" aria-haspopup="true" aria-expanded="false"><span id="range-label">Last 30 days</span><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3"/></svg></button>
  <div class="fb-menu range-menu" id="range-menu" hidden>
   <div class="range-cols">
    <div class="fb-col"><p class="fb-title">Select range</p>
     <button type="button" data-range="7">Last 7 days</button><button type="button" data-range="30">Last 30 days</button>
     <button type="button" data-range="90">Last 90 days</button><button type="button" data-range="365">Last 365 days</button>
     <button type="button" data-range="custom">Custom</button><hr><button type="button" data-reset>Reset</button></div>
    <div class="fb-custom"><p class="fb-title">Custom range</p>
     <label>From<input type="date" id="from-date"></label><label>To<input type="date" id="to-date"></label>
     <button type="button" class="btn" id="apply-custom">Apply range</button><p class="fb-hint-inline" id="custom-error" hidden>Pick both dates.</p></div>
   </div>
   <label class="fb-default"><span>Save as my default<small>Use on future visits</small></span><input type="checkbox" id="save-default"><i class="fb-switch" aria-hidden="true"></i></label>
   <div class="fb-summary"><span id="range-summary"></span><span id="range-days"></span></div>
  </div>
 </div>
 <div class="fb-group">
  <button type="button" class="fb-btn" id="group-btn" aria-haspopup="true" aria-expanded="false"><span id="group-label">Daily</span><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3"/></svg></button>
  <div class="fb-menu group-menu" id="group-menu" hidden>
   <button type="button" data-group="day">Daily</button><button type="button" data-group="week">Weekly</button><button type="button" data-group="month">Monthly</button><button type="button" data-group="quarter">Quarterly</button>
   <p class="fb-hint">Group data by time interval</p>
  </div>
 </div>
 %s
</div><!--/filter-bar-->'''


ENGINE_MENU = '''<div class="fb-group">
  <button type="button" class="fb-btn" id="engine-btn" aria-haspopup="true" aria-expanded="false"><svg class="fb-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.2v2.3"/><circle cx="8" cy="1.9" r=".7"/><rect x="2.8" y="4.5" width="10.4" height="8.6" rx="2.2"/><circle cx="6" cy="8.3" r=".9"/><circle cx="10" cy="8.3" r=".9"/><path d="M6.3 10.9h3.4"/></svg><span id="engine-label">%(label)s</span><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3"/></svg></button>
  <div class="fb-menu engine-menu" id="engine-menu" hidden>
   <div class="fb-search"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg><input type="search" id="engine-search" placeholder="Search..." aria-label="Search engines"></div>
   <label class="fb-check fb-all"><input type="checkbox" id="engine-all"><span>Select all</span></label>
   <div class="fb-checks" id="engine-list">%(rows)s</div>
   <p class="fb-hint" id="engine-empty" hidden>No engine matches.</p>
   <p class="fb-hint-inline" id="engine-none" hidden>Keep at least one engine.</p>
   <div class="fb-apply"><button type="button" class="btn" id="engine-apply">Apply</button></div>
  </div>
 </div>'''


FILTER_SCRIPT = r"""<script>
(()=>{
const $=id=>document.getElementById(id);
const DAY=864e5, MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTH=['January','February','March','April','May','June','July','August','September','October','November','December'];
const GROUP_NAME={day:'Daily',week:'Weekly',month:'Monthly',quarter:'Quarterly'}, UNIT={day:'day',week:'week',month:'month',quarter:'quarter'};
const RANGE_NAME={'7':'Last 7 days','30':'Last 30 days','90':'Last 90 days','365':'Last 365 days'};
const DEFAULT={range:'30',group:'day',from:'',to:'',engines:''};
const KEY='produkto-period';
// Every engine the page knows about, in the order they are drawn.
const ALL_ENGINES=[...document.querySelectorAll('[data-engine]')].map(el=>el.dataset.engine);
const ENGINE_NAME={};document.querySelectorAll('[data-engine]').forEach(el=>{
  ENGINE_NAME[el.dataset.engine]=el.closest('label').textContent.trim();});

// Period: page address first, then the saved default, then the built-in default.
let saved=null;try{saved=JSON.parse(localStorage.getItem(KEY)||'null');}catch(e){}
const state=Object.assign({},DEFAULT,saved||{});
const qp=new URLSearchParams(location.search);
['range','group','from','to','engines'].forEach(k=>{if(qp.get(k))state[k]=qp.get(k);});
if(!GROUP_NAME[state.group])state.group='day';
if(state.range!=='custom'&&!RANGE_NAME[state.range])state.range='30';
if(state.range==='custom'&&!(state.from&&state.to))state.range='30';
// Engines: an empty value means all of them, which is also what an empty
// selection falls back to - a blank dashboard reads as a bug, not a filter.
function engineList(){
  const picked=state.engines.split(',').filter(e=>ALL_ENGINES.includes(e));
  return picked.length?picked:ALL_ENGINES.slice();}
function setEngines(list){
  const picked=ALL_ENGINES.filter(e=>list.includes(e));
  state.engines=(picked.length&&picked.length<ALL_ENGINES.length)?picked.join(','):'';}

const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const nice=d=>d.getDate()+' '+MON[d.getMonth()]+' '+d.getFullYear();
function period(){
  if(state.range==='custom'){
    let f=state.from,t=state.to;if(f>t)[f,t]=[t,f];
    return [new Date(f+'T00:00:00'),new Date(t+'T23:59:59.999')];}
  const end=new Date();end.setHours(23,59,59,999);
  const start=new Date(end);start.setDate(start.getDate()-(Number(state.range)-1));start.setHours(0,0,0,0);
  return [start,end];
}
function bucketStart(d){const b=new Date(d);b.setHours(0,0,0,0);
  if(state.group==='day'){}
  else if(state.group==='week')b.setDate(b.getDate()-((b.getDay()+6)%7));
  else{b.setDate(1);if(state.group==='quarter')b.setMonth(Math.floor(b.getMonth()/3)*3);}
  return b;}
function nextBucket(b){const n=new Date(b);if(state.group==='day')n.setDate(n.getDate()+1);else if(state.group==='week')n.setDate(n.getDate()+7);else n.setMonth(n.getMonth()+(state.group==='month'?1:3));return n;}
const quarter=b=>'Q'+(Math.floor(b.getMonth()/3)+1)+' '+b.getFullYear();
function shortLabel(b){if(state.group==='day'||state.group==='week')return b.getDate()+' '+MON[b.getMonth()];if(state.group==='month')return MON[b.getMonth()]+' '+b.getFullYear();return quarter(b);}
function longLabel(b){if(state.group==='day')return nice(b);if(state.group==='week')return 'Week of '+nice(b);if(state.group==='month')return MONTH[b.getMonth()]+' '+b.getFullYear();return quarter(b);}
// Filter bar
function syncEngines(){
  const picked=engineList(),all=picked.length===ALL_ENGINES.length;
  document.querySelectorAll('[data-engine]').forEach(el=>{el.checked=picked.includes(el.dataset.engine);});
  const box=$('engine-all');
  if(box){box.checked=all;box.indeterminate=!all&&picked.length>0;}
  const lab=$('engine-label');
  if(lab)lab.textContent=all?'All engines':(picked.length===1?ENGINE_NAME[picked[0]]:picked.length+' engines');
}
function syncControls(){
  const [a,b]=period();
  $('range-label').textContent=state.range==='custom'?nice(a)+' – '+nice(b):RANGE_NAME[state.range];
  $('group-label').textContent=GROUP_NAME[state.group];
  syncEngines();
  const gl=$('vis-group-label');if(gl)gl.textContent=GROUP_NAME[state.group];
  document.querySelectorAll('[data-range]').forEach(el=>el.classList.toggle('on',el.dataset.range===state.range));
  document.querySelectorAll('[data-group]').forEach(el=>el.classList.toggle('on',el.dataset.group===state.group));
  $('range-summary').textContent=nice(a)+' – '+nice(b);
  const days=Math.round((b-a)/DAY);$('range-days').textContent=days+(days===1?' day':' days');
  $('from-date').value=iso(a);$('to-date').value=iso(b);
  document.querySelector('.fb-custom').classList.toggle('active',state.range==='custom');
  history.replaceState(null,'',url());
}
function url(){const u=new URL(location.href);['range','group','from','to','engines'].forEach(k=>u.searchParams.delete(k));
  u.searchParams.set('range',state.range);u.searchParams.set('group',state.group);
  if(state.range==='custom'){u.searchParams.set('from',state.from);u.searchParams.set('to',state.to);}
  if(state.engines)u.searchParams.set('engines',state.engines);
  return u;}
function apply(){if($('save-default').checked){try{localStorage.setItem(KEY,JSON.stringify(state));}catch(e){}}location.href=url();}
const openMenus=[];
function menu(btn,box){
  const close=()=>{box.hidden=true;btn.setAttribute('aria-expanded','false');};
  openMenus.push(close);
  btn.addEventListener('click',e=>{e.stopPropagation();const wasClosed=box.hidden;openMenus.forEach(c=>c());if(wasClosed){box.hidden=false;btn.setAttribute('aria-expanded','true');}});
  box.addEventListener('click',e=>e.stopPropagation());
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!box.hidden){close();btn.focus();}});
  return close;
}
document.addEventListener('click',()=>openMenus.forEach(c=>c()));
const closeRange=menu($('range-btn'),$('range-menu')),closeGroup=menu($('group-btn'),$('group-menu'));
document.querySelectorAll('[data-range]').forEach(el=>el.addEventListener('click',()=>{
  if(el.dataset.range==='custom'){document.querySelector('.fb-custom').classList.add('active');$('from-date').focus();return;}
  state.range=el.dataset.range;state.from='';state.to='';apply();closeRange();}));
$('apply-custom').addEventListener('click',()=>{const f=$('from-date').value,t=$('to-date').value;$('custom-error').hidden=!!(f&&t);if(!f||!t)return;
  state.range='custom';state.from=f;state.to=t;apply();closeRange();});
document.querySelector('[data-reset]').addEventListener('click',()=>{Object.assign(state,DEFAULT);apply();closeRange();});
document.querySelectorAll('[data-group]').forEach(el=>el.addEventListener('click',()=>{state.group=el.dataset.group;apply();closeGroup();}));
// Engines. Ticking is instant on screen but only reloads on Apply, so three
// clicks cost one page load instead of three.
if($('engine-btn')){
  const closeEngine=menu($('engine-btn'),$('engine-menu'));
  const pending=()=>[...document.querySelectorAll('[data-engine]')].filter(el=>el.checked).map(el=>el.dataset.engine);
  const repaint=()=>{const picked=pending(),all=picked.length===ALL_ENGINES.length;
    const box=$('engine-all');if(box){box.checked=all;box.indeterminate=!all&&picked.length>0;}
    const btn=$('engine-apply');if(btn)btn.disabled=!picked.length;
    const warn=$('engine-none');if(warn)warn.hidden=!!picked.length;};
  document.querySelectorAll('[data-engine]').forEach(el=>el.addEventListener('change',repaint));
  $('engine-all').addEventListener('change',e=>{
    document.querySelectorAll('[data-engine]').forEach(el=>{el.checked=e.target.checked;});repaint();});
  $('engine-apply').addEventListener('click',()=>{
    const picked=pending();if(!picked.length)return;setEngines(picked);apply();closeEngine();});
  $('engine-search').addEventListener('input',e=>{
    const q=e.target.value.trim().toLowerCase();let shown=0;
    document.querySelectorAll('#engine-list .fb-check').forEach(row=>{
      const hit=row.textContent.trim().toLowerCase().includes(q);row.hidden=!hit;shown+=hit;});
    $('engine-empty').hidden=!!shown;});
  // Reopening after cancelling must not leave the old ticks behind.
  $('engine-btn').addEventListener('click',()=>{syncEngines();repaint();});
}
$('save-default').checked=!!saved;
$('save-default').addEventListener('change',e=>{try{if(e.target.checked)localStorage.setItem(KEY,JSON.stringify(state));else localStorage.removeItem(KEY);}catch(err){}});
// Keep the period when moving between tabs, questions and answers.
function carry(){const keep=new URLSearchParams();['range','group','from','to','engines'].forEach(k=>{if(state[k])keep.set(k,state[k]);});
  document.querySelectorAll('a[href^="/r/"]').forEach(a=>{const u=new URL(a.getAttribute('href'),location.origin);keep.forEach((v,k)=>u.searchParams.set(k,v));a.setAttribute('href',u.pathname+u.search+u.hash);});
  document.querySelectorAll('form.answer-filters').forEach(f=>{if(qp.get('product')){let input=f.querySelector('input[name=product]');if(!input){input=document.createElement('input');input.type='hidden';input.name='product';f.append(input);}input.value=qp.get('product');}f.querySelectorAll('input[data-period]').forEach(i=>i.remove());keep.forEach((v,k)=>{const i=document.createElement('input');i.type='hidden';i.name=k;i.value=v;i.dataset.period='';f.append(i);});});}
window.PK={state,period,bucketStart,nextBucket,shortLabel,longLabel,UNIT,GROUP_NAME,redirecting:false};
// A saved default only reaches the server through the page address.
if(saved&&!qp.get('range')&&!qp.get('engines')&&(state.range!==DEFAULT.range||state.group!==DEFAULT.group||state.engines!==DEFAULT.engines)){window.PK.redirecting=true;location.replace(url());}
else{syncControls();if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',carry);else carry();}
})();
</script>"""


CHART_SCRIPT = r"""<script>
(()=>{
if(!window.PK||window.PK.redirecting)return;
const {state,period,bucketStart,nextBucket,shortLabel,longLabel,UNIT,GROUP_NAME}=window.PK;
const $=id=>document.getElementById(id);
const D=JSON.parse(document.getElementById('visibility-data').textContent);
const svg=document.getElementById('visibility-chart'),tip=document.getElementById('chart-tooltip');
// The tooltip is pointable: a long brand list scrolls inside it rather than
// growing past the card and making the whole page scroll. That means the
// pointer has to be able to travel from the chart into the tooltip without it
// vanishing on the way, so leaving the chart only hides it when the pointer
// did not land on the tooltip itself.
let overTip=false;
// Each chart registers how to put itself away - the trend chart also has a
// guide line and hover markers to clear, not just the tooltip.
let activeClear=null;
// Hiding waits a moment and then re-checks where the pointer is. Moving from a
// column onto the tooltip fires the chart's pointerleave BEFORE the tooltip's
// pointerenter, so hiding straight away removed the tooltip from under the
// pointer, which put the pointer back on the column, which showed it again:
// the tooltip flickered on and off. Only hide when the pointer has settled
// somewhere that is neither the chart nor the tooltip.
let overSvg=false,hideTimer=null;
svg.addEventListener('pointerenter',()=>{overSvg=true;});
svg.addEventListener('pointerleave',()=>{overSvg=false;});
function later(fn){clearTimeout(hideTimer);hideTimer=setTimeout(()=>{if(!overTip&&!overSvg)fn();},150);}
tip.addEventListener('pointerenter',()=>{overTip=true;clearTimeout(hideTimer);});
tip.addEventListener('pointerleave',()=>{overTip=false;
  later(activeClear||(()=>tip.classList.remove('shown')));});
const hideTip=()=>later(()=>tip.classList.remove('shown'));
// The tooltip lets the pointer pass through (CSS), so dragging across the
// dates never gets stuck on it. A long list is scrolled with the wheel over
// the chart instead; once the list reaches its end, the page scrolls as usual.
svg.addEventListener('wheel',e=>{
  if(!tip.classList.contains('shown')||tip.scrollHeight<=tip.clientHeight)return;
  const down=e.deltaY>0,atEnd=down?tip.scrollTop+tip.clientHeight>=tip.scrollHeight-1:tip.scrollTop<=0;
  if(atEnd)return;
  e.preventDefault();tip.scrollTop+=e.deltaY;},{passive:false});
let W=660,animateChart=true;
const ns='http://www.w3.org/2000/svg';
// "Scanned 18 Sep" under a "Week of 14 Sep" heading: the bucket and the
// reading inside it are different dates and both are worth showing.
// The tooltip follows the column being hovered instead of sitting in a
// corner: it lands just beside the mark, flips to the mark's other side when
// it would overflow, and is clamped inside the plot. Call it AFTER the
// content is in and 'shown' is set - a hidden element measures as zero wide.
function placeTip(cx){
  const box=svg.getBoundingClientRect(),host=tip.offsetParent;
  if(!host||!box.width)return;
  const px=box.left-host.getBoundingClientRect().left+(cx/W)*box.width;
  // Never taller than the plot it sits in. Anything longer scrolls inside the
  // tooltip, which is the whole point: the reader should not have to scroll the
  // dashboard to finish reading a date's brands.
  tip.style.maxHeight=Math.max(120,host.clientHeight-16)+'px';
  const w=tip.offsetWidth||260,room=host.clientWidth,gap=18;
  let left=px+gap;
  if(left+w>room-8)left=px-gap-w;
  tip.style.left=Math.max(8,Math.min(left,room-w-8))+'px';
  tip.style.right='auto';
  // Keep it inside the plot vertically too. Only when it is positioned against
  // the plot - the narrow layout pins it to the bottom instead, and an inline
  // top would fight that rule.
  if(getComputedStyle(tip).position==='absolute'){
    const h=tip.offsetHeight;
    tip.style.top=Math.max(8,Math.min(20,host.clientHeight-h-8))+'px';
  }else{tip.style.top='';}
}
// A product's logo for a tooltip row: the same image the chart and rankings
// use, falling back to initials when there is none or it fails to load.
function tipMark(logo,label){const m=document.createElement('span');m.className='tip-mark';
  m.textContent=(label||'').split(/\s+/).slice(0,2).map(w=>w[0]||'').join('').toUpperCase()||'?';
  if(logo){const img=document.createElement('img');img.alt='';img.src=logo;img.addEventListener('error',()=>img.remove());m.append(img);}
  return m;}
function subline(dates){const el=document.createElement('small');el.className='tip-sub';
  el.textContent=(dates.length===1?'Scanned ':dates.length+' scans · ')+dates.join(', ');return el;}
function node(tag,attrs,text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;}
function buckets(){
  const [a,b]=period(),out=[];
  for(let s=bucketStart(a);s<=b;s=nextBucket(s))out.push({start:s,end:nextBucket(s),scans:[]});
  D.scans.forEach(sc=>{const t=new Date(sc.ts*1000);if(t<a||t>b)return;const k=out.find(x=>t>=x.start&&t<x.end);if(k)k.scans.push(sc);});
  return out;}
// Empty calendar buckets before the first reading only push the line to the
// right, so the axis starts where the measurements start. A lone reading keeps
// centred context on both sides, because it has no line to anchor it. These are
// display buckets only: no extra scans or values enter the calculation.
function axisBuckets(B){
  const measured=B.filter(b=>b.scans.some(s=>s.n));
  if(measured.length>1)return B.slice(B.indexOf(measured[0]));
  if(measured.length!==1)return B;
  const center=measured[0];
  return [-2,-1,0,1,2].map(offset=>{
    if(offset===0)return center;
    const start=new Date(center.start);
    if(state.group==='day')start.setDate(start.getDate()+offset);
    else if(state.group==='week')start.setDate(start.getDate()+offset*7);
    else start.setMonth(start.getMonth()+offset*(state.group==='quarter'?3:1));
    return {start,end:nextBucket(start),scans:[]};
  });
}
// Pool every answer in the bucket: answers naming the product / all answers.
function rate(list,si){const n=list.reduce((t,s)=>t+s.n,0);if(!n)return null;
  const named=list.reduce((t,s)=>t+((s.productHits||[])[si]||0),0);return 100*named/n;}

// "Visibility over time" is the mean of the dates drawn on the chart - each
// date counts once, so it matches what you get by adding the points up and
// dividing. Pooling every answer instead would weight a date by how many
// answers it happens to hold, which is not what the chart shows.
// "Visibility" is the newest date in the period, and so are the bars it opens.
function updateHeadline(list,dates,measured){
  const el=$('vis-rate'),pos=$('vis-pos'),latest=$('vis-latest');if(!el)return;
  const pts=(measured||[]).map(i=>dates[i]).filter(v=>v!==null&&v!==undefined);
  if(!pts.length){el.classList.remove('count');el.textContent='—';
    if(latest){latest.classList.remove('count');latest.textContent='—';}
    pos.innerHTML='<em class="stat-empty">No scans</em>';return;}
  const avg=pts.reduce((t,v)=>t+v,0)/pts.length;
  el.classList.add('count');el.dataset.v=Math.round(avg);el.textContent=Math.round(avg);
  if(latest){const v=Math.round(pts[pts.length-1]);
    latest.classList.add('count');latest.dataset.v=v;latest.textContent=v;}
  const named=list.reduce((t,s)=>t+s.own[0],0),ranks=list.reduce((t,s)=>t+s.own[1],0);
  if(named)pos.textContent='#'+(ranks/named).toFixed(1);
  else pos.innerHTML='<em class="stat-empty">Not mentioned</em>';
}

// A faint Produkto mark behind the plot, the way PromptWatch signs its charts.
// Prepended, so every line, bar, marker and guide paints on top of it, and
// ignored by the pointer so it cannot swallow a hover meant for the chart.
//
// Measured off the live viewBox rather than hardcoded: W grows with the window
// (see draw()), so a fixed centre only lands correctly at the narrowest size
// and drifts left on a wide screen. The plot runs x 56..W-48 and y 30..208.
const LOGO_RATIO=480/86;
function watermark(){
  const L=56,R=W-48,w=Math.min(300,(R-L)*0.45),h=w/LOGO_RATIO;
  svg.prepend(node('image',{href:'/logo.png',
    x:(L+R)/2-w/2, y:(30+208)/2-h/2, width:w, height:h,
    opacity:.07,'pointer-events':'none',preserveAspectRatio:'xMidYMid meet',
    'aria-hidden':'true',class:'chart-watermark'}));
}

function drawTrend(){
  svg.replaceChildren();tip.replaceChildren();tip.classList.remove('shown','compact','sov-tip');
  let B=axisBuckets(buckets());
  const compare=true;
  const S=compare?D.series:D.series.slice(0,1);
  const V=S.map((s,si)=>B.map(b=>rate(b.scans,si)));
  const idx=B.map((b,i)=>b.scans.some(s=>s.n)?i:-1).filter(i=>i>=0);
  const inRange=B.flatMap(b=>b.scans);
  const ownRates=B.map(b=>{const n=b.scans.reduce((t,s)=>t+s.n,0);return n?100*b.scans.reduce((t,s)=>t+s.own[0],0)/n:null;});
  updateHeadline(inRange,ownRates,idx);
  if(!S.length){svg.append(node('text',{x:W/2,y:120,'text-anchor':'middle',class:'axis-label'},'No products in this selection'));return;}
  const top=Math.max(0,...V.flat().filter(v=>v!==null));
  const max=Math.min(100,Math.max(20,Math.ceil(top/20)*20));
  const single=idx.length===1,L=56,R=W-48;
  const x=i=>single?L+i*(R-L)/(B.length-1):B.length===1?(L+R)/2:L+(B[i].start-B[0].start)*(R-L)/(B.at(-1).start-B[0].start),y=v=>208-v/max*178;
  for(let i=1;i<=4;i++)svg.append(node('line',{x1:L,x2:W-48,y1:y(max*i/4),y2:y(max*i/4),stroke:'#e4e8ef','stroke-dasharray':'3 4'}));
  for(let i=0;i<=4;i++)svg.append(node('text',{x:L-14,y:y(max*i/4)+4,'text-anchor':'end',class:'axis-label'},Math.round(max*i/4)+'%'));
  svg.append(node('line',{x1:L,x2:W-48,y1:y(0),y2:y(0),stroke:'#c9ced6'}));
  const every=Math.max(1,Math.ceil(B.length/(compare&&single?4:7)));
  B.forEach((b,i)=>{if(i%every&&i!==B.length-1)return;if(i!==B.length-1&&B.length-1-i<every)return;
    svg.append(node('line',{x1:x(i),x2:x(i),y1:y(0),y2:y(0)+4,stroke:'#c9ced6'}));
    svg.append(node('text',{x:x(i),y:y(0)+19,'text-anchor':'middle',class:'axis-label'},shortLabel(b.start)));});
  const trend=$('trend-change'),unit=UNIT[state.group];
  if(!idx.length){
    svg.append(node('text',{x:(L+W-48)/2,y:y(max*0.8),'text-anchor':'middle',class:'axis-label empty-note'},'No scans in this period'));
    trend.textContent='';$('chart-note').textContent='No scans in this period · try a longer range';
  }else{
    S.forEach((s,si)=>{
      for(let k=1;k<idx.length;k++){const i=idx[k],prev=idx[k-1];
        // Only consecutive readings join. A missing scan breaks the line:
        // a bridge across it would read as a trend nobody measured.
        if(i!==prev+1)continue;
        svg.append(node('line',{x1:x(prev),x2:x(i),y1:y(V[si][prev]),y2:y(V[si][i]),
          stroke:s.color,'stroke-width':si===0?3:2.5,'data-si':si,class:'plot-line'}));}
      // A reading with no neighbour on either side has no line, so it gets a
      // small dot; otherwise it would silently vanish from the chart.
      if(idx.length>1)idx.forEach((i,k)=>{if(idx[k-1]===i-1||idx[k+1]===i+1)return;
        svg.append(node('circle',{cx:x(i),cy:y(V[si][i]),r:3.5,fill:s.color,
          stroke:'white','stroke-width':1.5,'data-si':si,class:'plot-dot'}));});
    });
    // The lines are left bare: a marker appears only on the date under the
    // pointer, drawn into `marks` by the hover handler below. The exception
    // is a lone reading, which has no line to draw and would otherwise leave
    // the chart blank.
    if(idx.length===1)S.slice().reverse().forEach((s,ri)=>{const si=S.length-1-ri;
      idx.forEach(i=>svg.append(node('circle',{cx:x(i),cy:y(V[si][i]),r:5,
        fill:s.color,stroke:'white','stroke-width':2,'data-si':si})));});
    // No week-on-week change sentence under the chart: the lines show the
    // movement and the tooltip gives the exact figures for any date.
    if(idx.length>1)trend.textContent='';
    else{trend.style.color='#6c778b';trend.textContent='First reading · your trend will build as you scan.';}
    const n=inRange.length;
    $('chart-note').textContent=GROUP_NAME[state.group]+' · '+n+' scan'+(n===1?'':'s')+' in this period'+' · breaks mean no scan';
  }
  const guide=node('line',{x1:0,x2:0,y1:20,y2:208,stroke:'#dce1e9',visibility:'hidden','pointer-events':'none'});svg.append(guide);
  // Markers for the hovered date only. Brands sharing a percentage stack.
  const marks=node('g',{'pointer-events':'none'});svg.append(marks);
  const clear=()=>{tip.classList.remove('shown');marks.replaceChildren();
    guide.setAttribute('visibility','hidden');};
  const w=Math.min(90,(W-48-L)/Math.max(1,B.length));
  B.forEach((b,i)=>{
    // The heading names the bucket, exactly as the axis tick does. The scan's
    // own date goes underneath: "14 Sep" on the axis and "18 Sep" in the
    // tooltip read as a contradiction otherwise.
    const label=longLabel(b.start);
    const dates=b.scans.map(sc=>shortLabel(new Date(sc.ts*1000)));
    const text=label+'; '+(V[0][i]!==null?S.map((s,si)=>s.name+': '+Math.round(V[si][i])+'%').join(', '):'no scan');
    const hit=node('rect',{x:x(i)-w/2,y:15,width:w,height:200,fill:'transparent',tabindex:0,role:'button','aria-label':text});
    const show=()=>{guide.setAttribute('x1',x(i));guide.setAttribute('x2',x(i));guide.setAttribute('visibility','visible');
      marks.replaceChildren();
      if(V[0][i]!==null&&idx.length>1)S.slice().reverse().forEach((s,ri)=>{const si=S.length-1-ri;
        marks.append(node('circle',{cx:x(i),cy:y(V[si][i]),r:5,fill:s.color,stroke:'white','stroke-width':2,class:'hover-mark','data-si':si}));});
      tip.replaceChildren();const t=document.createElement('b');t.textContent=label;tip.append(t);
      if(dates.length)t.append(subline(dates));
      if(V[0][i]===null){const e=document.createElement('div');e.textContent='No measured answers in this '+unit;tip.append(e);}
      else S.map((s,si)=>({s,si})).sort((a,b)=>V[b.si][i]-V[a.si][i]).forEach(({s,si})=>{const row=document.createElement('div'),dot=document.createElement('i'),name=document.createElement('span'),val=document.createElement('strong');
        dot.style.background=s.color;name.textContent=s.name;if(s.brand){const brand=document.createElement('small');brand.className='trend-brand';brand.textContent=s.brand;name.append(brand);}val.textContent=Math.round(V[si][i])+'%';const pr=rate(B.flatMap(b=>b.scans),si);if(pr!==null&&B.length>1){const ps=document.createElement('small');ps.className='trend-period';ps.textContent=Math.round(pr)+'% in period';val.append(ps);}row.append(dot,name,val);tip.append(row);});
      tip.classList.add('shown','compact');placeTip(x(i));};
    hit.addEventListener('pointerenter',show);hit.addEventListener('focus',show);hit.addEventListener('blur',clear);hit.addEventListener('click',show);
    svg.append(hit);
  });
  activeClear=clear;
  svg.onpointerleave=()=>later(clear);
  // No colour key under the chart: each product in the rankings carries its
  // brand's dot, so the list is the key.
  $('chart-legend').replaceChildren();
  if(locked!==null&&locked>=S.length)locked=null;   // cohort shrank under it
  applyFocus(locked);
  reveal();
}
function reveal(){
  if(!animateChart||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const defs=node('defs',{}),clip=node('clipPath',{id:'vis-clip'}),rect=node('rect',{x:0,y:0,width:0,height:260});
  clip.append(rect);defs.append(clip);svg.prepend(defs);
  svg.querySelectorAll('.starting-baseline,.trend-segment,.plot-line,circle').forEach(el=>el.setAttribute('clip-path','url(#vis-clip)'));
  const labels=[...svg.querySelectorAll('.end-label')];labels.forEach(l=>{l.style.opacity=0;l.style.transition='opacity .35s';});
  const t0=performance.now(),dur=1100;
  const step=t=>{const k=Math.max(0,Math.min(1,(t-t0)/dur)),e=1-Math.pow(1-k,3);rect.setAttribute('width',W*e);
    if(k<1)requestAnimationFrame(step);else{rect.setAttribute('width',W);labels.forEach(l=>l.style.opacity=1);}};
  requestAnimationFrame(step);
}


// --- share of voice over time: one 100% stacked column per date ----------
// Share of voice is a split of a fixed whole, so it reads as a stacked
// column per date rather than one bar per brand: the question is how the
// split moved, which a bar chart with no time axis cannot show.
const OTHER='#cfd6e2';
function drawStacked(){
  svg.replaceChildren();tip.replaceChildren();tip.classList.remove('shown');
  const B=axisBuckets(buckets()),S=D.series,trend=$('trend-change');
  // Pooled by weight: a bucket's share is its mentions over its own total,
  // never an average of percentages from scans of different sizes.
  const totals=B.map(b=>b.scans.reduce((t,sc)=>t+(sc.mt||0),0));
  const shares=B.map((b,i)=>!totals[i]?null:S.map((s,si)=>
    100*b.scans.reduce((t,sc)=>t+((sc.sv||[])[si]||0),0)/totals[i]));
  const idx=B.map((b,i)=>shares[i]?i:-1).filter(i=>i>=0);
  const L=56,R=W-48,TOP=30,BASE=208,y=v=>BASE-v/100*(BASE-TOP);
  for(let i=1;i<=4;i++)svg.append(node('line',{x1:L,x2:R,y1:y(i*25),y2:y(i*25),stroke:'#e4e8ef','stroke-dasharray':'3 4'}));
  for(let i=0;i<=4;i++)svg.append(node('text',{x:L-14,y:y(i*25)+4,'text-anchor':'end',class:'axis-label'},(i*25)+'%'));
  svg.append(node('line',{x1:L,x2:R,y1:BASE,y2:BASE,stroke:'#c9ced6'}));
  const inRange=B.flatMap(b=>b.scans);
  if(!idx.length){
    svg.append(node('text',{x:(L+R)/2,y:y(60),'text-anchor':'middle',class:'axis-label empty-note'},'No scans in this period'));
    trend.style.color='#6c778b';trend.textContent='';
    $('chart-legend').replaceChildren();
    $('chart-note').textContent='No scans in this period · try a longer range';
    return;
  }
  const slot=(R-L)/B.length,w=Math.min(74,slot*0.6);
  const every=Math.max(1,Math.ceil(B.length/8));
  B.forEach((b,i)=>{
    const cx=L+slot*(i+0.5);
    if(!(i%every)||i===B.length-1)
      svg.append(node('text',{x:cx,y:BASE+19,'text-anchor':'middle',class:'axis-label'},shortLabel(b.start)));
    if(!shares[i])return;
    // Everything the cohort does not hold is one neutral band, so the column
    // always totals 100% and the merchant can see how much is unaccounted for.
    const parts=S.map((sc,si)=>({name:sc.name,brand:sc.brand,color:sc.color,logo:sc.logo,initials:sc.initials,v:shares[i][si]}));
    const rest=Math.max(0,100-parts.reduce((t,r)=>t+r.v,0));
    if(rest>0.05)parts.push({name:'Every other product',brand:'',color:OTHER,v:rest});
    const label=longLabel(b.start),dates=b.scans.map(sc=>shortLabel(new Date(sc.ts*1000)));
    const g=node('g',{class:'comparison-column',tabindex:0,role:'button',
      'aria-label':label+'; '+parts.map(r=>r.name+' '+r.v.toFixed(1)+'%').join(', ')});
    let acc=0;
    parts.forEach((r,k)=>{
      const h=Math.max(r.v>0?1:0,(BASE-TOP)*r.v/100);
      if(!h)return;
      g.append(node('rect',{x:cx-w/2,y:y(acc+r.v),width:w,height:h,fill:r.color,class:'stack-seg',
        style:'transform-origin:'+cx+'px '+BASE+'px;animation-delay:'+(i*55)+'ms'}));
      acc+=r.v;
    });
    const show=()=>{
      // Already showing this column: leave it alone. Rebuilding reloads every
      // logo and restarts the layout, which reads as a flash.
      if(tip.classList.contains('shown')&&tip.classList.contains('sov-tip')&&tip.dataset.key===label)return;
      tip.dataset.key=label;tip.replaceChildren();
      const head=document.createElement('b');
      head.textContent=label;tip.append(head);
      if(dates.length)head.append(subline(dates));
      // One line per product so the whole list fits without scrolling. The
      // leftover band goes last: it is the biggest number but the least
      // interesting row, and at the top it pushed the products out of view.
      const other=parts.filter(r=>!r.brand&&r.name==='Every other product');
      parts.filter(r=>!other.includes(r)).sort((a,c)=>c.v-a.v).concat(other).forEach(r=>{
        const row=document.createElement('div');row.className='tip-line';row.title=r.name+(r.brand?' · '+r.brand:'');
        const dot=document.createElement('i');dot.style.background=r.color;
        const name=document.createElement('span');name.className='tip-name';name.textContent=r.name;
        if(r.brand){const brand=document.createElement('small');brand.textContent=r.brand;name.append(brand);}
        const val=document.createElement('strong');val.textContent=r.v.toFixed(1)+'%';
        row.append(dot);if(r.brand)row.append(tipMark(r.logo,r.initials||r.brand));row.append(name,val);tip.append(row);});
      tip.classList.add('shown','compact','sov-tip');placeTip(cx);};
    g.addEventListener('pointerenter',show);g.addEventListener('focus',show);g.addEventListener('click',show);
    g.addEventListener('blur',()=>tip.classList.remove('shown'));
    g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show();}});
    svg.append(g);
  });
  activeClear=hideTip;svg.onpointerleave=hideTip;
  trend.style.color='#6c778b';
  trend.textContent=idx.length>1
    ?'Each column is every product recommendation in that '+UNIT[state.group]+', split by product.'
    :'First reading · the split will move as you scan again.';
  // The brand colours are keyed by the rankings list. Only the neutral band
  // has no row of its own, so it is the only key left under the chart.
  const legend=$('chart-legend');legend.replaceChildren();
  const item=document.createElement('span'),dot=document.createElement('i');
  dot.style.background=OTHER;const label=document.createElement('span');
  label.className='trend-series-label';label.textContent='Every other product';
  item.append(dot,label);legend.append(item);
  $('chart-note').textContent=GROUP_NAME[state.group]+' · '+inRange.length+' scan'+(inRange.length===1?'':'s')
    +' in this period · share of all product recommendations';
}

// --- comparison bars: your catalog against the chosen competitors --------
const CMP=(()=>{const el=document.getElementById('compare-data');
  try{return el?JSON.parse(el.textContent):{rows:[],source:''};}catch(e){return {rows:[],source:''};}})();
const METRIC={visibility:{key:'rate',unit:'%',lowBest:false,title:'Mentioned in'},
              sov:{key:'share',unit:'%',lowBest:false,title:'Share of voice'},
              position:{key:'avg',unit:'',lowBest:true,title:'Average position'}};

function drawBars(mode){
  svg.replaceChildren();tip.replaceChildren();tip.classList.remove('shown','compact','sov-tip');
  const spec=METRIC[mode];
  let source=CMP.rows.map((r,si)=>({...r,si}));
  // Visibility bars show the newest date, the same reading as the Visibility
  // card; Avg. visibility and the ranking list cover the whole period (5 Oct 2026).
  if(mode==='visibility'){
    const last=axisBuckets(buckets()).filter(b=>b.scans.some(x=>x.n)).pop();
    const n=last?last.scans.reduce((t,x)=>t+x.n,0):0;
    if(n)source=source.map(r=>r.scan?{...r,rate:100*last.scans.reduce((t,x)=>t+((r.scan[String(x.id)]||{}).hits||0),0)/n}:r);
  }
  const rows=source.filter(r=>r[spec.key]!==null&&r[spec.key]!==undefined);
  const trend=$('trend-change');
  if(!rows.length){
    svg.append(node('text',{x:W/2,y:120,'text-anchor':'middle',class:'axis-label empty-note'},'Nothing to compare in this period'));
    trend.style.color='#6c778b';trend.textContent='';$('chart-legend').replaceChildren();return;
  }
  // Position: lower is better, so sort ascending and keep the axis honest.
  rows.sort((a,b)=>spec.lowBest?a[spec.key]-b[spec.key]:b[spec.key]-a[spec.key]);
  const top=Math.max(...rows.map(r=>r[spec.key]));
  // Position is a rank: 1 is best. Hang those bars from the top so the
  // longest bar is always the best performer, never the worst.
  const flip=spec.lowBest,TOP=30,BASE=208,SPAN=BASE-TOP;
  const lo=flip?1:0,hi=flip?Math.max(2,Math.ceil(top)):(spec.unit==='%'?Math.min(100,Math.max(20,Math.ceil(top/20)*20)):Math.max(1,Math.ceil(top)));
  const y=v=>flip?TOP+(v-lo)/(hi-lo)*SPAN:BASE-v/hi*SPAN;
  const tick=i=>lo+(hi-lo)*i/4;
  const L=56,R=W-48;
  for(let i=flip?1:1;i<=4;i++)svg.append(node('line',{x1:L,x2:R,y1:y(tick(i)),y2:y(tick(i)),stroke:'#e4e8ef','stroke-dasharray':'3 4'}));
  for(let i=0;i<=4;i++)svg.append(node('text',{x:L-14,y:y(tick(i))+4,'text-anchor':'end',class:'axis-label'},
    spec.unit==='%'?Math.round(tick(i))+'%':'#'+tick(i).toFixed(1)));
  svg.append(node('line',{x1:L,x2:R,y1:y(lo),y2:y(lo),stroke:'#c9ced6'}));
  const slot=(R-L)/rows.length,w=Math.min(140,slot*0.68);
  rows.forEach((r,i)=>{
    const cx=L+slot*(i+0.5),v=r[spec.key];
    const a=y(lo),b=y(v),h=Math.max(2,Math.abs(b-a));
    const color=r.color;
    const g=node('g',{class:'comparison-column','data-si':r.si,tabindex:0,role:'button','aria-label':r.name+': '+v.toFixed(1)+spec.unit});
    // A hit area over the whole column slot. Without it the only thing to
    // hover is the mark itself - fine for a tall bar, hopeless for the 6px
    // dot the position chart draws.
    g.append(node('rect',{x:cx-slot/2,y:TOP-12,width:slot,height:BASE-TOP+62,fill:'transparent'}));
    g.append(node(flip?'circle':'rect',flip?{cx,cy:b,r:6,fill:color,class:'cmp-dot'}:{x:cx-w/2,y:Math.min(a,b),width:w,height:h,rx:4,
      fill:color,class:'cmp-bar',style:'transform-origin:'+cx+'px '+BASE+'px;animation-delay:'+(i*45)+'ms'}));
    g.append(node('text',{x:cx,y:flip?b+15:b-9,'text-anchor':'middle',class:'axis-label cmp-value',
      'font-weight':500,fill:'#657084',style:'font-size:13px'},
      spec.unit==='%'?(mode==='sov'?v.toFixed(1):Math.round(v))+'%':'#'+v.toFixed(1)));
    const labelWidth=slot-10;
    const labelBox=node('foreignObject',{x:cx-labelWidth/2,y:BASE+9,width:labelWidth,height:32});
    const label=document.createElementNS('http://www.w3.org/1999/xhtml','div');label.className='chart-brand-label';label.title=r.name;
    const mark=document.createElement('span');mark.className='chart-brand-mark';mark.textContent=r.initials||r.brand.split(/\s+/).slice(0,2).map(w=>w[0]).join('').toUpperCase();
    if(r.logo){const img=document.createElement('img');img.alt='';img.src=r.logo;img.addEventListener('error',()=>img.remove());mark.append(img);}
    const labelText=document.createElement('span');labelText.className='chart-brand-name';labelText.textContent=r.name;
    label.append(mark,labelText);labelBox.append(label);g.append(labelBox);
    const show=()=>{tip.replaceChildren();const title=document.createElement('b');title.textContent=r.name;const row=document.createElement('div');row.textContent=spec.title+' · '+(spec.unit==='%'?(mode==='sov'?v.toFixed(1):Math.round(v))+'%':'#'+v.toFixed(1));const scope=document.createElement('small');scope.textContent='Selected period · '+r.brand;tip.append(title,row,scope);tip.classList.add('shown');placeTip(cx);};
    g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show();}});g.addEventListener('pointerenter',show);g.addEventListener('focus',show);g.addEventListener('click',show);g.addEventListener('blur',()=>tip.classList.remove('shown'));svg.append(g);
  });
  trend.style.color='#6c778b';
  trend.textContent=spec.lowBest?'Lower is better — 1 means named first.':'';
  const legend=$('chart-legend');legend.replaceChildren();
  if(CMP.source){const note=document.createElement('span');
    note.textContent='Compared against '+CMP.source;legend.append(note);}
}

function drawPositionTrend(){
  svg.replaceChildren();tip.replaceChildren();tip.classList.remove('shown');
  const B=axisBuckets(buckets()),S=D.series,L=56,R=W-48,TOP=30,BASE=208;
  const values=S.map(s=>B.map(b=>{
    const totals=b.scans.reduce((v,sc)=>{const r=s.scan[String(sc.id)]||{};return [v[0]+(r.hits||0),v[1]+(r.ranks||0)];},[0,0]);
    return totals[0]?totals[1]/totals[0]:null;
  }));
  const max=Math.max(6,Math.ceil(Math.max(0,...values.flat().filter(v=>v!==null))));
  const x=i=>B.length===1?(L+R)/2:L+i*(R-L)/(B.length-1),y=v=>TOP+(v-1)/(max-1)*(BASE-TOP);
  const step=Math.max(1,Math.ceil((max-1)/6));
  for(let v=1;v<=max;v+=step){
    svg.append(node('line',{x1:L,x2:R,y1:y(v),y2:y(v),stroke:'#e4e8ef','stroke-dasharray':'3 4'}));
    svg.append(node('text',{x:L-14,y:y(v)+4,'text-anchor':'end',class:'axis-label'},'#'+v));
  }
  const every=Math.max(1,Math.ceil(B.length/7));
  B.forEach((b,i)=>{if(i%every&&i!==B.length-1)return;svg.append(node('text',{x:x(i),y:BASE+25,'text-anchor':'middle',class:'axis-label'},shortLabel(b.start)));});
  S.forEach((s,si)=>{
    const V=values[si];
    for(let i=1;i<B.length;i++){
      // A missing recommendation has no position; do not draw through it.
      if(V[i]===null||V[i-1]===null)continue;
      svg.append(node('line',{x1:x(i-1),x2:x(i),y1:y(V[i-1]),y2:y(V[i]),stroke:s.color,'stroke-width':2,'data-si':si,class:'position-line'}));
    }
    V.forEach((v,i)=>{
      if(v===null)return;
      const g=node('g',{'data-si':si,class:'position-mark',tabindex:0,role:'button','aria-label':s.name+', '+longLabel(B[i].start)+', average position '+v.toFixed(1)});
      g.append(node('rect',{x:x(i)-11,y:y(v)-11,width:22,height:22,rx:5,fill:'white',stroke:'#dfe3e8'}));
      g.append(node('text',{x:x(i),y:y(v)+3,'text-anchor':'middle',fill:s.color,style:'font-size:8px'},s.initials||'P'));
      if(s.logo){const pic=node('image',{href:s.logo,x:x(i)-9,y:y(v)-9,width:18,height:18,preserveAspectRatio:'xMidYMid meet'});pic.addEventListener('error',()=>pic.remove());g.append(pic);}
      const show=()=>{tip.replaceChildren();const title=document.createElement('b');title.className='tip-title';
        const t=document.createElement('span');t.textContent=s.name;
        if(s.brand){const br=document.createElement('small');br.textContent=s.brand;t.append(br);}
        title.append(tipMark(s.logo,s.initials||s.brand||s.name),t);
        const date=document.createElement('div');date.textContent=longLabel(B[i].start);const value=document.createElement('div');value.textContent='Average position · #'+v.toFixed(1);tip.append(title,date,value);tip.classList.add('shown');placeTip(x(i));};
      g.addEventListener('pointerenter',show);g.addEventListener('focus',show);g.addEventListener('click',show);g.addEventListener('blur',()=>tip.classList.remove('shown'));svg.append(g);
    });
  });
  if(!values.flat().some(v=>v!==null))svg.append(node('text',{x:W/2,y:115,'text-anchor':'middle',class:'axis-label'},'No product positions in this period'));
  $('chart-legend').replaceChildren();
  $('trend-change').textContent='';
  $('chart-note').textContent='Lower is better · #1 is first · gaps mean no recorded position';
  applyFocus(locked);
}

function draw(){
  const bounds=svg.getBoundingClientRect();W=Math.max(bounds.width<500?340:660,bounds.width/Math.max(1,bounds.height)*260);svg.setAttribute('viewBox','0 0 '+W+' 260');
  const mode=(document.querySelector('.kpi-cell[aria-pressed="true"]')||{}).dataset;
  const m=mode&&mode.mode||'overtime';
  document.querySelectorAll('.compare-control').forEach(el=>{el.hidden=m!=='overtime';});
  const titles={overtime:'Visibility over time',visibility:'Product visibility',sov:'Product share of voice',position:'Average position over time'};
  document.querySelector('.visibility-card h2').textContent=titles[m];svg.setAttribute('aria-label',titles[m]);
  $('vis-group-label').textContent=(m==='overtime'||m==='sov'||m==='position')?GROUP_NAME[state.group]:'All products mentioned';
  document.querySelector('.chart-evidence').hidden=m!=='overtime';
  if(m!==rankMode){rankMode=m;applyRankingMode(m);return;}
  if(m==='overtime')drawTrend();
  else if(m==='sov')drawStacked();
  else if(m==='position')drawPositionTrend();
  else {drawBars(m);$('chart-note').textContent=m==='visibility'?'Newest scan in the selected period':'Same saved answers · selected period';}
  watermark();
  const scale=260/Math.max(1,svg.getBoundingClientRect().height);
  svg.querySelectorAll('text').forEach(t=>t.style.fontSize=((t.closest('.position-mark')?8:12)*scale)+'px');
  activeClear=hideTip;svg.onpointerleave=hideTip;
}

// Isolating one brand's line. Two ways in: hovering a product in the rankings
// previews it, clicking a legend entry locks it until clicked again. A
// preview that ends falls back to whatever is locked rather than to nothing.
// Trend only - the bar and stacked charts have no lines to isolate.
let locked=null;
const rankRows=[...document.querySelectorAll('.analysis-main .product-rankings tbody tr[data-product]')];
function applyFocus(si){
  svg.querySelectorAll('.plot-line,circle[data-si],.position-line,.position-mark,.comparison-column[data-si]').forEach(l=>{
    l.style.opacity=(si===null||Number(l.dataset.si)===si)?'':'.10';});
}
function focusSeries(si){applyFocus(si===null?locked:si);}
function toggleLock(si){
  locked=locked===si?null:si;
  rankRows.forEach(r=>r.setAttribute('aria-pressed',String(Number(r.dataset.si)===locked)));
  applyFocus(locked);
}
rankRows.forEach(row=>{
  const si=()=>row.hasAttribute('data-si')?Number(row.dataset.si):null;
  row.tabIndex=0;row.setAttribute('role','button');row.setAttribute('aria-pressed','false');
  row.title='Highlight this product on the chart';
  const on=()=>focusSeries(si()),off=()=>focusSeries(null);
  row.addEventListener('pointerenter',on);row.addEventListener('pointerleave',off);
  row.addEventListener('focusin',on);row.addEventListener('focusout',off);
  row.addEventListener('click',()=>toggleLock(si()));
  row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleLock(si());}});
});

const cells=[...document.querySelectorAll('.kpi-cell[data-mode]')];
cells.forEach(c=>c.addEventListener('click',()=>{
  cells.forEach(o=>o.setAttribute('aria-pressed',String(o===c)));
  draw();
}));
if(cells.length)cells[0].setAttribute('aria-pressed','true');


window.addEventListener('resize',()=>{clearTimeout(window.chartResize);window.chartResize=setTimeout(draw,150);});
document.addEventListener('keydown',e=>{if(e.key==='Escape')tip.classList.remove('shown');});
const productData=JSON.parse($('ranking-data').textContent);
const allScans=D.scans.map(s=>({...s}));
const palette=['#32bd83','#3282ff','#8b4dff','#2fb8d6','#f52f98','#7d8079'];
const scroll=document.querySelector('.analysis-main .ranking-scroll');
let filtered=[],cohortKey='';
function syncProducts(force=false){
  if(!scroll)return;
  const rowHeight=filtered[0]?.getBoundingClientRect().height||58;
  const first=Math.min(Math.max(0,Math.round(scroll.scrollTop/rowHeight)),Math.max(0,filtered.length-6));
  const visible=filtered.slice(first,first+6);
  const key=visible.map(r=>r.dataset.product).join(',');
  if(!force&&key===cohortKey)return;
  animateChart=cohortKey==='';cohortKey=key;locked=null;
  rankRows.forEach(r=>{r.removeAttribute('data-si');r.setAttribute('aria-pressed','false');r.querySelector('.rank-dot').style.background='#d8dfe9';});
  const selected=visible.map((row,i)=>{
    row.dataset.si=i;row.querySelector('.rank-dot').style.background=palette[i];
    const img=row.querySelector('.rank-thumb img');
    return {...productData[Number(row.dataset.product)],color:palette[i],
      logo:img?img.getAttribute('src'):'',
      initials:row.querySelector('.rank-thumb>span')?.textContent||'P'};
  });
  D.series=selected;
  D.scans=allScans.map(s=>({...s,
    productHits:selected.map(r=>(r.scan[String(s.id)]||{}).hits||0),
    sv:selected.map(r=>(r.scan[String(s.id)]||{}).count||0)}));
  // Use the exact selected-period metrics displayed by the adjacent ranking.
  // The catalog headline alone carries the separate latest-date reading.
  CMP.rows=selected.map(r=>({...r}));
  CMP.source='products visible in the ranking list';
  const other=document.querySelector('.kpi-cell[data-mode=sov] strong small:not(.kpi-unit)');
  if(other)other.textContent=Math.round(Math.max(0,100-selected.reduce((n,r)=>n+r.share,0)))+'% to products not shown in the chart';
  $('ranking-status').textContent=filtered.length?'Showing '+(first+1)+'–'+Math.min(first+6,filtered.length)+' of '+filtered.length+' products · scroll to compare':'No products in this selection';
  draw();
}
// Clicking Visibility switches the rankings to the newest scan, like the card
// and its bars; every other view shows the whole selected period (5 Oct 2026).
let rankMode=null;
const rankHead=document.querySelector('.analysis-main .product-rankings thead th:nth-child(3)');
const rankHeadText=rankHead?rankHead.innerHTML:'';
function countTo(el,to,unit){
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){el.textContent=to+unit;return;}
  const t0=performance.now(),from=0;
  const step=t=>{const k=Math.min(1,(t-t0)/450);el.textContent=Math.round(from+(to-from)*k)+unit;if(k<1)requestAnimationFrame(step);};
  requestAnimationFrame(step);
}
function applyRankingMode(m){
  const today=m==='visibility';
  const last=today?axisBuckets(buckets()).filter(b=>b.scans.some(x=>x.n)).pop():null;
  const n=last?last.scans.reduce((t,x)=>t+x.n,0):0;
  const vals=rankRows.map((row,i)=>{
    const d=productData[Number(row.dataset.product)];
    if(!today||!n)return {row,rate:d.rate,avg:d.avg,order:i};
    let hits=0,ranks=0;
    last.scans.forEach(x=>{const v=d.scan[String(x.id)];if(v){hits+=v.hits||0;ranks+=v.ranks||0;}});
    return {row,rate:100*hits/n,avg:hits?ranks/hits:null,order:i};
  });
  if(today&&n)vals.sort((a,b)=>b.rate-a.rate||(a.avg||99)-(b.avg||99)||a.order-b.order);
  else vals.sort((a,b)=>Number(a.row.dataset.product)-Number(b.row.dataset.product));
  const body=rankRows[0]&&rankRows[0].parentNode;
  vals.forEach((v,i)=>{
    const c=v.row.children;c[0].textContent=i+1;
    countTo(c[2],Math.round(v.rate),'%');c[4].textContent=v.avg?v.avg.toFixed(1):'—';
    if(body)body.append(v.row);
  });
  rankRows.length=0;vals.forEach(v=>rankRows.push(v.row));
  if(rankHead)rankHead.innerHTML=today&&n?'Mentioned<small>today</small>':rankHeadText;
  filterProducts();
}
function filterProducts(){
  const mine=$('rank-scope').value==='mine',limit=Number($('rank-count').value);
  filtered=rankRows.filter(r=>!mine||r.dataset.own==='true').slice(0,limit);
  const keep=new Set(filtered);rankRows.forEach(r=>r.hidden=!keep.has(r));
  if(scroll)scroll.scrollTop=0;
  syncProducts(true);
}
$('rank-scope').addEventListener('change',filterProducts);
$('rank-count').addEventListener('change',()=>{filterProducts();document.querySelector('.rank-options').open=false;});
let scrollFrame;
if(scroll)scroll.addEventListener('scroll',()=>{cancelAnimationFrame(scrollFrame);scrollFrame=requestAnimationFrame(()=>syncProducts());},{passive:true});
document.addEventListener('click',e=>{const menu=document.querySelector('.rank-options');if(!menu.contains(e.target))menu.open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelector('.rank-options').open=false;});
filterProducts();
if(!scroll)draw();
})();
</script>"""
