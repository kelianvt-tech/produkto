"""A saved six-product comparison, evaluated locally against existing answers."""
import html
import json
from urllib.parse import urlsplit, unquote
import db
import evidence
from text import norm, words

E = html.escape


def saved(domain):
    row = db.one('SELECT selection FROM competitor_comparisons WHERE store_domain=?', (domain,))
    return json.loads(row['selection']) if row else []


def canonical(url):
    u = urlsplit(url or '')
    return (u.hostname or '').lower().removeprefix('www.') + unquote(u.path).rstrip('/') if u.scheme in ('http', 'https') and u.hostname else ''


def validate(ps, value):
    if not isinstance(value, dict):
        raise ValueError('Choose a competitor and six product pairs.')
    brand = str(value.get('brand', '')).strip()[:120]
    pairs = value.get('pairs', [])
    if not brand or not isinstance(pairs, list) or len(pairs) != 6:
        raise ValueError('Enter one competitor brand and exactly six product pairs.')
    allowed = set(evidence.prompt_set(ps)['product_ids'])
    clean = []
    for pair in pairs:
        if not isinstance(pair, dict) or type(pair.get('own_id')) is not int or pair['own_id'] not in allowed:
            raise ValueError('Choose six products included in this catalog scan.')
        title = str(pair.get('title', '')).strip()[:240]
        url = str(pair.get('url', '')).strip()[:2000]
        if not title or (url and not canonical(url)):
            raise ValueError('Each competitor product needs a name and, optionally, a valid http(s) product URL.')
        clean.append(dict(own_id=pair['own_id'], title=title, url=url))
    if len({p['own_id'] for p in clean}) != 6 or len({norm(p['title']) for p in clean}) != 6:
        raise ValueError('Choose six distinct products on each side.')
    urls = [canonical(p['url']) for p in clean if p['url']]
    if len(set(urls)) != len(urls):
        raise ValueError('Each competitor product URL must be different.')
    return dict(brand=brand, pairs=clean)


def competitor_match(m, selection):
    # Exact product URLs also recognise retailer links. Name-only matching
    # requires the chosen brand; ambiguous equal matches are left unassigned.
    url = canonical(m.get('url'))
    exact = [i for i, p in enumerate(selection['pairs']) if url and canonical(p['url']) == url]
    if len(exact) == 1:
        return exact[0]
    if norm(m.get('brand')) != norm(selection['brand']):
        return None
    named = set(words(m.get('product_name')))
    scores = []
    for i, p in enumerate(selection['pairs']):
        title = set(words(p['title'])) - set(words(selection['brand']))
        score = len(title & named) / len(title) if title else 0
        if score >= .6:
            scores.append((score, i))
    scores.sort(reverse=True)
    if scores and (len(scores) == 1 or scores[0][0] > scores[1][0]):
        return scores[0][1]
    return None


def calculate(ids, p, selection):
    answers, mentions = evidence.load(ids, p)
    selected = {x['own_id'] for x in selection['pairs']}
    ps = p['_ps']
    questions = {q for q, relevant in zip(ps['prompts'], ps['relevance']) if selected.intersection(relevant)}
    answers = [a for a in answers if a['prompt'] in questions]
    aids = {a['id'] for a in answers}
    own, rival = {}, {}
    for m in mentions:
        if m['answer_id'] not in aids:
            continue
        pid = m.get('matched_product_id')
        if pid in selected:
            key = (m['answer_id'], pid)
            own[key] = min(own.get(key, 999), m['rank'])
        elif not m.get('is_theirs') and not m.get('is_their_brand'):
            match = competitor_match(m, selection)
            if match is not None:
                key = (m['answer_id'], match)
                rival[key] = min(rival.get(key, 999), m['rank'])
    total = len(own) + len(rival)
    def stats(rows):
        best = {}
        for (aid, _), rank in rows.items():
            best[aid] = min(best.get(aid, 999), rank)
        return dict(rate=100*len(best)/len(answers) if answers else None,
                    avg=sum(best.values())/len(best) if best else None,
                    share=100*len(rows)/total if total else None,
                    count=len(rows), answers=sorted(best))
    return dict(own=stats(own), rival=stats(rival), n=len(answers), questions=len(questions))


def render_one(s, ps, p, ctx, selection):
    catalog = [x for x in p['_catalog'] if x['id'] in p['_ps']['product_ids']]
    body = '<section class="insight-card comparison-card" ><div class="insight-heading"><h2>Your six vs competitor’s six</h2></div><div class="comparison-body">'
    body += '<p class="small">Compare two selected groups using the same buyer answers. The share below is between these groups only; the Share of voice donut above includes all recommended competitors.</p>'
    if len(catalog) < 6:
        return body + '<p>This comparison needs six included products in your catalog scan.</p></div></section>'
    if selection:
        result = calculate(ctx['ids'], p, selection)
        if not result['n']:
            body += '<p>No completed answers in this period. Choose a longer date range to see the comparison.</p>'
        else:
            body += '<div class="comparison-bars" role="img" aria-label="Visibility comparison: percentage of shared answers recommending either selected group">'
            for label, key, color in [(p['vendor'], 'own', '#0b1b35'), (selection['brand'], 'rival', '#a78bfa')]:
                row = result[key]
                body += '<div class="comparison-bar"><span>%s</span><div><i style="width:%.2f%%;background:%s"></i></div><strong>%.1f%%</strong></div>' % (E(label), row['rate'], color, row['rate'])
            body += '</div><p class="small">Visibility · percentage of shared answers recommending at least one selected product</p>'
            body += '<div class="comparison-table-wrap"><table><thead><tr><th>Selected group</th><th>Avg. position</th><th>Share between groups</th><th>Product recommendations</th></tr></thead><tbody>'
            for label, key in [(p['vendor'], 'own'), (selection['brand'], 'rival')]:
                row = result[key]
                body += '<tr><td>%s · 6 products</td><td>%s</td><td>%s</td><td>%d</td></tr>' % (E(label), '%.1f' % row['avg'] if row['avg'] is not None else '—', '%.1f%%' % row['share'] if row['share'] is not None else '—', row['count'])
            body += '</tbody></table></div><p class="small">%d completed answers · %d shared questions. Questions come from your selected products. Position uses the first selected product in each answer; recommendations count each selected product once per answer. No recommendations for either group means no share to calculate.</p>' % (result['n'], result['questions'])
            body += '<details><summary>Review matched answers</summary>'
            for label, key in [(p['vendor'], 'own'), (selection['brand'], 'rival')]:
                links = ' · '.join('<a href="/r/%s/answers?answer=%d">Answer %d</a>' % (E(s['token']), aid, i+1) for i, aid in enumerate(result[key]['answers']))
                body += '<p><b>%s:</b> %s</p>' % (E(label), links or 'No selected products identified in the saved answers.')
            body += '</details>'
    else:
        body += '<p>Choose a competitor and pair six comparable products to display the chart. No new scan is needed.</p>'
    body += '<p><a href="/competitors?d=%s">Edit competitors and selected products →</a></p></div></section>' % E(p['store_domain'])
    return body


def render(s, ps, p, ctx):
    selections = saved(p['store_domain'])
    if not selections:
        return ''  # Older scans predate required competitor onboarding.
    valid = []
    for selection in selections:
        try:
            selection = validate(ps, selection)
            valid.append(render_one(s, ps, p, ctx, selection))
        except ValueError:
            continue
    return ''.join(valid)
