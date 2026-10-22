"""Step 3: build Instantly upload CSVs (good / catch_all / noline, plus wave-1 files) from the checked lines."""
import csv, json, re, collections
L = json.load(open('pet-apollo-lines-2026-10-08.json'))
NAMES = {"Lucy & Co.": "Lucy & Co.", "BetterBone - Natural Plant-Based Dog Chew Toys & Essentials": "BetterBone",
         '"I and love and you"​ pet': "I and love and you", "🐶 A Pup Above": "A Pup Above", "GoTags.com": "GoTags",
         "SmarterPaw, Meowijuana® & Dogg": "SmarterPaw", "Earth Animal | B Corp": "Earth Animal",
         "Petsense by Tractor Supply": "Petsense", "Jeffers Pet, Equine, Livestock": "Jeffers", "PET STATION": "Pet Station",
         "COMFURT COLLAR": "Comfurt Collar", "MOSHIQA": "Moshiqa", "PRIDE+GROOM": "Pride+Groom"}
def dom(r): return re.sub(r'^https?://(www\.)?', '', r['website'] or r['email'].split('@')[1]).strip('/').lower()
def short(c):
    c = c.strip()
    for k, v in NAMES.items():
        if c.startswith(k.split(' |')[0][:12]) and (c == k or k.startswith(c[:12])): return v
    c = re.sub(r'\s*[|®™].*$', '', c); c = re.sub(r',?\s*\b(Inc\.?|LLC|Ltd\.?)$', '', c, flags=re.I)
    return c.strip(' "​,')
def prod(p, b):
    p = re.sub(r'\s*[–—-]\s*\d[\d.,]*\s*(oz|lb|lbs|ct|count|pack|in|inch|kg|g|ml)\b.*$', '', p, flags=re.I)
    p = re.split(r'\s+[–—]\s+', p)[0]; p = re.sub(r'\s+\d[\d/"\'×x ]*["\'].*$', '', p)
    p = re.sub(r',\s*\d.*$', '', p); p = re.sub(r'\s*\(.*?\)', '', p).strip(' .')
    if p.lower().startswith(b.lower()): p = p[len(b):].strip(' :-')
    return re.sub(r'^the\s+', '', p, flags=re.I)
def line(r):
    l = L.get(dom(r))
    if not l or l['flag'] != 'ok': return ''
    b = l['competitor_brand'].strip(); p = prod(l['competitor_product'], b)
    if not p: thing = b
    elif len(p.split()) == 1: thing = 'the %s %s' % (b, p if p.isupper() else p.lower())
    else: thing = 'the %s, made by %s' % (p, b)
    return 'I asked ChatGPT "%s" today. One of the products it recommended was %s, another brand in your category.' % (l['question'], thing)
out = collections.defaultdict(list)
for kind in ('good', 'catch_all'):
    for r in csv.DictReader(open(f'2026-10-08-pet-apollo-{kind}.csv')):
        cl = line(r) if r['retailer'] != 'yes' else ''
        out[kind if cl else 'noline'].append(dict(email=r['email'], first_name=r['first_name'], last_name=r['last_name'],
            company_name=short(r['company_name']), website=r['website'], chatgpt_line=cl, wave=int(r['wave']), verify=r['email_result']))
for k, rows in out.items():
    rows.sort(key=lambda r: r['wave'])
    for suffix, sel in (('', rows), ('-wave1', [r for r in rows if r['wave'] == 1])):
        w = csv.DictWriter(open(f'2026-10-08-pet-apollo-instantly-{k}{suffix}.csv', 'w', newline=''), fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(sel)
    print(k, len(rows), 'wave1', sum(r['wave'] == 1 for r in rows))
