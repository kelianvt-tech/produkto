import csv, json, re, html
L = "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/prospecting/cold-calls/leads/"
P = json.load(open('products.json')); C = json.load(open('competitors.json'))
STOP = set('the and for with from pack size set new mini travel black white blue count women men mens womens unisex free original'.split())
BADPICK = re.compile(r'upsell|wholesale|carbon|event|book|printed|props|protector|gift box|discovery|trial|\(\d+pk\)|advent', re.I)
def words(s): return {w for w in re.findall(r'[a-z]{4,}', (s or '').lower()) if w not in STOP}
def squash(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
rows = list(csv.DictReader(open(L + 'ALL-with-phone.csv')))
out = []
for r in rows:
    d = r['organization_primary_domain']; p = P.get(d) or {}; c = C.get(d) or {}
    title = html.unescape(p.get('title', '')); ptype = html.unescape(p.get('type', ''))
    cb, cp = c.get('brand', ''), c.get('product', '')
    own = bool(cp) and (squash(cb)[:6] and (squash(cb)[:6] in squash(d) or squash(cb)[:6] in squash(r['organization_name']))
                        or len(words(cp) & words(title)) >= 2 and squash(cb)[:4] in squash(d + r['organization_name']))
    asked_by_name = bool(title) and not ptype.strip()
    echo = len(squash(title)) >= 8 and squash(cp)[:12] == squash(title)[:12]
    own = own or (bool(cp) and echo)
    if title and cp and asked_by_name:
        flag, line = 'check: question used their product name', ''
        cb = cp = ''
    elif not title:
        flag, line = 'no product found', ''
    elif not cp:
        flag, line = 'no competitor found', ''
    elif own:
        flag = 'THEIR product recommended'
        line = ("I've been looking at which %s ChatGPT recommends, and your %s keeps coming up. Can I take 15 seconds to explain why I'm calling?"
                % ((ptype or 'option').lower(), title))
    else:
        match = words(cp) & (words(title) | words(ptype))
        flag = 'ok' if match and not BADPICK.search(title) else 'check: match looks off'
        line = ("I've been looking at which %s ChatGPT recommends, and the %s from %s keeps coming up. Can I take 15 seconds to explain why I'm calling?"
                % ((ptype or 'products').lower(), cp, cb))
    if title and BADPICK.search(title) and flag != 'THEIR product recommended':
        flag = 'check: product pick looks off'
    out.append({'Company': r['organization_name'], 'Website': 'https://' + d,
                'Contact Name': (r['first_name'] + ' ' + r['last_name']).strip(), 'Title': r['title'],
                'Phone': r['mobile_number_formatted'], 'Email': r['email'], 'State': r['state'], 'Time Zone': r['time_zone'],
                'Their product': title, 'Product type': ptype, 'Their price': ('$%.0f' % p['price']) if p.get('price') else '',
                'Product link': ('https://%s/products/%s' % (d, p['handle'])) if p.get('handle') else '',
                'Competitor brand (ChatGPT pick)': '' if own else cb, 'Competitor product (ChatGPT pick)': '' if own else cp,
                'Flag': flag, 'Opener line': line, 'ChatGPT question asked': c.get('question', ''), 'LinkedIn': r['linkedin_url']})
BAD = {'mgemi.com','ora.organic','nemah.com','gibsgrooming.com','branchbasics.com','moodeaux.com'}
for x in out:
    if x['Website'][8:] in BAD:
        x['Flag'] = 'check: match looks off'
order = {'ok': 0, 'THEIR product recommended': 1}
out.sort(key=lambda x: (order.get(x['Flag'], 2), x['Company']))
with open(L + 'call-sheet.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
from collections import Counter
print(Counter(x['Flag'] for x in out))
