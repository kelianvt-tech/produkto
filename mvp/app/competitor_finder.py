"""Competitor suggestions without the OpenAI API.

One ChatGPT answer bought through Apify (half a cent) is asked for three
competing brands and the closest product each sells to each of the
merchant's six products, in a fixed line format that is parsed here.
The Apify actor splits queries on newlines, so the question must stay one line.

Suggestions are for review only; they never enter measured evidence.
"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import apify_answers

LINE = re.compile(r'P([1-6])\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*)')


def _clean_url(url):
    url = url.replace('\\', '')
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.startswith('utm_')])
    return urlunsplit(parts._replace(query=query))


def question(brand, domain, products):
    items = '; '.join('P%d: %s (%s %s)' % (i + 1, p['title'], brand.get('currency') or '', p.get('price') or '')
                      for i, p in enumerate(products))
    return ('I sell at %s (%s). Name 3 competing online brands at a similar price, and for EACH brand '
            'the single closest product to each of my products below. Reply ONLY with lines in this '
            'exact format, no other text: P1 | Brand | Exact product name | product page URL. '
            'My products: %s' % (domain, brand.get('country') or '', items)).replace('\n', ' ')


def parse(text, cites, products):
    rivals = {}
    for raw in text.splitlines():
        m = LINE.search(raw.replace('\\[', '[').replace('\\]', ']'))
        if not m:
            continue
        slot, brand, title, rest = int(m[1]) - 1, m[2].strip(' *'), m[3].strip(' *'), m[4]
        url = ''
        ref = re.search(r'\[(\d+)\]', rest)
        link = re.search(r'https?://[^\s)\]]+', rest)
        if link:
            url = link[0]
        elif ref and 0 < int(ref[1]) <= len(cites):
            url = cites[int(ref[1]) - 1]['url']
        pairs = rivals.setdefault(brand, {})
        pairs.setdefault(slot, dict(own_id=products[slot]['id'], title=title,
                                    url=_clean_url(url) if url else ''))
    out = []
    for brand, pairs in rivals.items():
        if len(pairs) == 6:
            ps = [pairs[i] for i in range(6)]
            seen = set()
            for p in ps:                        # a reused link is a category page, not the product
                if p['url'] in seen:
                    p['url'] = ''
                seen.add(p['url'])
            out.append(dict(brand=brand, pairs=ps))
    return out


def suggest(domain, brand, products):
    run_id, dataset = apify_answers.start_run([question(brand, domain, products)])
    status = apify_answers.wait(run_id, poll=3, timeout=300)
    found = []
    for text, cites, _ in apify_answers.collect(dataset, status, run_id).values():
        found += parse(text, cites, products)
    return found, []
