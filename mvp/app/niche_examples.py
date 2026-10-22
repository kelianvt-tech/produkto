"""Niche examples: learn how the best brands in a store's niche build their articles (19 Oct 2026).

Kelian: for every store, find the e-commerce brands that do articles really well in that niche and
follow their format and layout. Patagonia was only an example for outdoor clothing; a skincare store
learns from skincare brands (for Clubhouse Skin: Fresh, Dermalogica, Gisou).

How:
  1. Candidates come from the store's own scans, for free: the article-like pages AI cites for its
     buyer questions (blogs, journals, guides, stories), not the store's own site and not the big
     publishers, retailers and authorities in briefs.BIG_SITES. Those are cited for who they are,
     not how they write. The most cited first.
  2. Up to READ pages are fetched (free) and measured: words, headings in order, question headings,
     step headings, tables, lists, photos, FAQ, summary boxes, product links, author and read time.
  3. One helper-model call (~0.3 cent) keeps only BRANDS that sell their own products (not
     magazines, marketplaces or retailers) and writes a playbook: length, the order of blocks, how
     headings are phrased, where products and photos go, the tone, what to do and what to avoid.

The playbook teaches structure only. The writer never copies an example's words, facts or photos.
Cached per store in content_settings['niche_playbook'], refreshed monthly. A store with no scans yet
gets DEFAULT_PLAYBOOK (no paid search here).
"""
import json
import re
import time
import urllib.parse
from collections import Counter
from html.parser import HTMLParser

TTL = 30 * 86400
CANDIDATES = 14       # article pages considered
READ = 8              # fetched and measured
KEEP = 5              # brands the playbook is built from

_ARTICLE_PATH = re.compile(r'/(blogs?|journal|stories|story|articles?|guides?|learn|advice|edit|magazine|insights|'
                           r'expert[\w-]*|skin-?care-?(tips|101)|how-to|the-[\w-]+-(edit|journal)|field-notes|'
                           r'resources|tips|living-[\w-]+)(/|$)', re.I)
_NOT_ARTICLE = re.compile(r'/(products?|collections?|cart|account|search|pages/(contact|faq|shipping))(/|$)', re.I)

DEFAULT_PLAYBOOK = dict(
    sources=[], length_words=1000,
    opening='A one-sentence answer to the title question, then a short intro line in the brand\'s voice.',
    blocks=['Breadcrumbs, a category tag, author and read time under the cover photo',
            'An "At a glance" box: 3-4 short label/answer rows',
            'Sections with question headings; a short direct answer first, then detail',
            'A product card after the section that recommends that product',
            'A wide lifestyle photo between sections, every two sections or so',
            'One small table where buyers compare options',
            '4-6 FAQ questions that fold open',
            'A closing banner for the product or set that fits the whole article'],
    headings='Plain buyer questions or short "Step 1: ..." headings.',
    products='Named where they answer the question, with a card; never a hard sell in the prose.',
    photos='Lifestyle photos wide, between sections; product shots inside cards.',
    tone='Calm, expert and short sentences; the brand\'s own voice.',
    do=[], avoid=['Generic filler intros', 'Repeating the same benefit in several sections'])


# ---- measuring a page ------------------------------------------------------------------------------

class _Shape(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'svg', 'nav', 'header', 'footer', 'form', 'button', 'select'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.tag, self.words, self.heads, self.paras = 0, [], 0, [], 0
        self.imgs = self.tables = self.lists = self.details = self.product_links = 0
        self.title, self.cur, self.text = '', None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        if self.skip:
            return
        if tag in ('h1', 'h2', 'h3'):
            self.cur = [tag, '']
        elif tag == 'p':
            self.paras += 1
        elif tag == 'img' and not re.search(r'logo|icon|avatar|badge|payment', (a.get('src') or '') + (a.get('alt') or ''), re.I):
            self.imgs += 1
        elif tag == 'table':
            self.tables += 1
        elif tag in ('ul', 'ol'):
            self.lists += 1
        elif tag == 'details':
            self.details += 1
        elif tag == 'a' and '/products/' in (a.get('href') or ''):
            self.product_links += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.cur and tag == self.cur[0]:
            t = re.sub(r'\s+', ' ', self.cur[1]).strip()
            if t:
                self.heads.append((self.cur[0], t[:90]))
                if self.cur[0] == 'h1' and not self.title:
                    self.title = t
            self.cur = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.cur:
            self.cur[1] += data
        self.words += len(data.split())
        if len(self.text) < 400:
            self.text.append(data)


def measure(html):
    p = _Shape()
    try:
        p.feed(html)
    except Exception:                                                     # noqa: BLE001 - broken markup
        pass
    low = html.lower()
    text = ' '.join(p.text)
    h2 = [t for tag, t in p.heads if tag == 'h2']
    ld = set(re.findall(r'"@type"\s*:\s*"(FAQPage|HowTo|Article|BlogPosting|Product|BreadcrumbList)"', html))
    return dict(
        title=p.title, words=p.words, paragraphs=p.paras, h2=len(h2), h3=sum(1 for tag, _ in p.heads if tag == 'h3'),
        outline=[t for tag, t in p.heads if tag in ('h2', 'h3')][:14],
        question_headings=sum(1 for t in h2 if t.endswith('?')),
        step_headings=sum(1 for t in h2 if re.match(r'(step\s*\d|\d+[.)])', t, re.I)),
        images=p.imgs, tables=p.tables, lists=p.lists,
        faq=bool(p.details or 'faqpage' in low or re.search(r'>\s*(faqs?|frequently asked)', low)),
        summary_box=bool(re.search(r'at a glance|key takeaways|in short|tl;?dr|the short answer|quick answer|summary', low)),
        product_links=p.product_links,
        author=bool(re.search(r'\b(written by|author|by [A-Z][a-z]+ [A-Z])', html[:200000])),
        read_time=bool(re.search(r'\d+\s*(min|minute)s?\s*read', low)),
        breadcrumbs=bool('breadcrumb' in low),
        schema=sorted(ld), sample=text[:400])


# ---- candidates ------------------------------------------------------------------------------------

def _host(url):
    h = urllib.parse.urlsplit(url).netloc.lower()
    return h[4:] if h.startswith('www.') else h


def candidates(domain):
    """[(url, times cited)] article-like pages AI cites for the store's questions, most cited first,
    one per site."""
    import briefs
    _, _, _, cites = briefs._evidence(domain)
    total = Counter()
    for c in cites.values():
        total.update(c)
    own = _host('https://' + domain)
    by_site = {}
    for url, n in total.most_common():
        host = _host(url)
        path = urllib.parse.urlsplit(url).path
        if not host or host == own or host.endswith('.' + own) or briefs._big(host):
            continue
        if not _ARTICLE_PATH.search(path) or _NOT_ARTICLE.search(path):
            continue
        if host not in by_site:
            by_site[host] = (url, n)
        else:
            by_site[host] = (by_site[host][0], by_site[host][1] + n)
    ranked = sorted(by_site.values(), key=lambda x: -x[1])
    try:                                    # articles the owner said they love come first (article_setup, 19 Oct)
        import article_setup
        mine = [(u, 0) for u in article_setup.loved(domain)]
    except Exception:                                                     # noqa: BLE001
        mine = []
    picked = {_host(u) for u, _ in mine}
    return (mine + [r for r in ranked if _host(r[0]) not in picked])[:CANDIDATES]


def read(cands, delay=0.6):
    """[(url, cited, measures)] for the pages that could be fetched."""
    import page_gap
    out = []
    for url, n in cands:
        if len(out) >= READ:
            break
        try:
            html = page_gap.fetch(url)
        except Exception:                                                 # noqa: BLE001 - blocked or gone
            continue
        m = measure(html)
        if m['words'] >= 250:
            out.append((url, n, m))
        time.sleep(delay)
    return out


# ---- the playbook ----------------------------------------------------------------------------------

PLAYBOOK_RULES = """You are an editor studying how the best e-commerce brands in one niche write the articles that AI assistants cite, so a store in that niche can write articles to the same standard.

You get measured pages (counts, heading outlines, which blocks they use, a text sample). First keep only pages from BRANDS that sell their own products (like a skincare brand's journal). Drop magazines, news sites, blogs without products, marketplaces, retailers selling many brands, clinics and apps. Keep at most 5.

Then write the playbook for the store's articles, from what the kept brands do in common, in plain instructions a writer can follow:
- length_words: a target length for the article itself (the counts include menus; real articles are shorter). Between 700 and 1600.
- opening: how the article opens.
- blocks: the article's building blocks in order (e.g. "At a glance box with 3-4 rows", "Step sections, one per product", "Wide lifestyle photo between sections", "Product card after the section that recommends it", "Small comparison table", "FAQ of 4-6 questions", "Closing banner for the full set"). 5-10 items.
- headings: how headings are phrased.
- products: how and where the brand's own products appear.
- photos: how photos are used.
- tone: the tone in one sentence.
- do / avoid: 2-5 short items each.
Never copy a sentence, claim or fact from the samples. sources: the kept pages, with one short reason each."""

PLAYBOOK_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["sources", "length_words", "opening", "blocks", "headings", "products", "photos", "tone", "do", "avoid"],
    "properties": {
        "sources": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                               "required": ["site", "url", "why"],
                                               "properties": {"site": {"type": "string"}, "url": {"type": "string"},
                                                              "why": {"type": "string"}}}},
        "length_words": {"type": "integer"},
        "opening": {"type": "string"}, "headings": {"type": "string"}, "products": {"type": "string"},
        "photos": {"type": "string"}, "tone": {"type": "string"},
        "blocks": {"type": "array", "items": {"type": "string"}},
        "do": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
}


def _niche(domain):
    import db
    b = db.brand(domain) or {}
    bits = [b.get('brand_name') or domain, b.get('industry') or '', ', '.join(b.get('services') or [])[:200]]
    return ' / '.join(x for x in bits if x)


def build(pages, niche, usage=None):
    """The playbook from measured pages (one helper-model call). DEFAULT_PLAYBOOK when nothing was read."""
    if not pages:
        return dict(DEFAULT_PLAYBOOK)
    import llm
    listing = []
    for url, n, m in pages:
        listing.append('- %s (%s): %d words, %d paragraphs, %d h2 (%d as questions, %d as steps), %d h3, '
                       '%d images, %d tables, %d lists, FAQ %s, summary box %s, %d product links, author %s, read time %s, '
                       'breadcrumbs %s, markup %s\n  Outline: %s\n  Sample: %s'
                       % (url, 'THE OWNER CHOSE THIS ONE: always keep it' if n == 0 else 'cited %d times' % n, m['words'], m['paragraphs'], m['h2'], m['question_headings'], m['step_headings'],
                          m['h3'], m['images'], m['tables'], m['lists'], m['faq'], m['summary_box'], m['product_links'],
                          m['author'], m['read_time'], m['breadcrumbs'], ', '.join(m['schema']) or '-',
                          ' | '.join(m['outline']) or '-', m['sample'][:300]))
    text = 'THE STORE: %s\n\nPAGES AI CITES FOR ITS BUYER QUESTIONS:\n%s' % (niche, '\n'.join(listing))
    try:
        pb = llm.json_call(PLAYBOOK_RULES, text, 'niche_playbook', PLAYBOOK_SCHEMA, usage=usage, attempts=3)
    except Exception:                                                     # noqa: BLE001
        return dict(DEFAULT_PLAYBOOK)
    pb['length_words'] = max(700, min(1600, int(pb.get('length_words') or 1000)))
    if not pb.get('sources'):
        return dict(DEFAULT_PLAYBOOK, measured=len(pages))
    return pb


def learn(domain, force=False, usage=None):
    """The store's playbook: cached for a month, rebuilt from its latest scans."""
    import content_setup
    s = content_setup.get(domain)
    pb = s.get('niche_playbook')
    if pb and not force and time.time() - pb.get('learned_at', 0) < TTL:
        return pb
    pb = build(read(candidates(domain)), _niche(domain), usage=usage)
    pb['learned_at'] = time.time()
    s = content_setup.get(domain)
    s['niche_playbook'] = pb
    content_setup.put(domain, s)
    return pb


def get(domain):
    import content_setup
    return content_setup.get(domain).get('niche_playbook') or learn(domain)


def prompt(pb):
    """The playbook as a writer's prompt section."""
    src = ', '.join(s['site'] for s in pb.get('sources') or []) or 'a standard editorial layout'
    lines = ['Learned from: %s.' % src,
             'Length: about %d words for the article itself.' % pb.get('length_words', 1000),
             'Opening: %s' % pb.get('opening', ''),
             'Blocks, in order:'] + ['- ' + b for b in pb.get('blocks') or []] + [
        'Headings: %s' % pb.get('headings', ''), 'Products: %s' % pb.get('products', ''),
        'Photos: %s' % pb.get('photos', ''), 'Tone: %s' % pb.get('tone', '')]
    if pb.get('do'):
        lines.append('Do: ' + '; '.join(pb['do']))
    if pb.get('avoid'):
        lines.append('Avoid: ' + '; '.join(pb['avoid']))
    return ('\n\nHOW THE BEST BRANDS IN THIS NICHE BUILD THEIR ARTICLES (follow this structure and standard; never copy '
            'their words, facts or photos):\n' + '\n'.join(lines))


if __name__ == '__main__':
    import sys
    import llm
    u = llm.Usage()
    cs = candidates(sys.argv[1])
    print('candidates:', cs)
    pg = read(cs)
    for url, n, m in pg:
        print(n, url, m['words'], 'words', m['h2'], 'h2', m['images'], 'img', 'faq' if m['faq'] else '', 'box' if m['summary_box'] else '')
    pb = build(pg, _niche(sys.argv[1]), usage=u)
    print(json.dumps(pb, indent=1))
    print('%.2f cents' % (u.cost_cents() or 0))
