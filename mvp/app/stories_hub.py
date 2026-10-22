"""The stories hub: one page on the store that lists every live AEO article as a card (20 Oct 2026).

Kelian asked for it after the designed articles: like Patagonia's "All Stories", a page with a big first story,
then a grid of cards (cover photo, category, title, one-line summary, read time), filterable by category, in the
store's own look (brand_style, the same .pk-a styles as the articles). Optionally a strip of the store's own
Instagram photos (social_photos.py) at the bottom.

On Shopify it is an ordinary store page at /pages/stories, made the first time the owner clicks "Put it on your
store". After that it rewrites itself whenever an article goes live or is taken down (shopify_connect.publish /
undo call sync), so it never lists a dead link. "Take it down" deletes the page. Its state lives in
content_settings['stories_hub'] = {id, handle, shop, at, instagram}.

Why a page and not the theme's blog index: changing the theme needs theme access and differs per theme; a page
needs only the content permission the agent already has. The page also gives AI crawlers one place that links to
every article (plus ItemList markup).

Before anything is live, the preview shows the store's article drafts instead, labelled "Not live yet", so the
owner can see the design.
"""
import html
import json
import re
import time
import urllib.parse

import db

E = lambda s: html.escape(s or '', quote=True)
HANDLE = 'stories'
TITLE = 'Stories'
KINDS = ('guide', 'comparison')


# ---- what goes on the page ---------------------------------------------------------------------------------

def _minutes(body):
    text = [body.get('dek', '')] + [t for s in body.get('sections') or [] for t in [s.get('heading', '')] +
                                    list(s.get('paragraphs') or [])] + \
        [f.get('question', '') + ' ' + f.get('answer', '') for f in body.get('faqs') or []]
    words = len(' '.join(text).split()) or len(re.sub(r'<[^>]+>', ' ', body.get('html', '')).split())
    return max(2, round(words / 230))


def _summary(body):
    if body.get('dek'):
        return body['dek']
    t = re.sub(r'\s+', ' ', re.sub(r'<style.*?</style>|<script.*?</script>|<[^>]+>', ' ', body.get('html', ''), flags=re.S)).strip()
    return (t[:157] + '...') if len(t) > 160 else t


def items(domain, drafts_if_empty=False):
    """[{id, title, summary, cover, category, url, at, minutes, live}] newest first. Live articles only; with
    drafts_if_empty, the store's unpublished article drafts stand in when nothing is live (preview only)."""
    import content_agent
    import content_review
    content_agent.init()
    q = ("SELECT * FROM content_drafts WHERE store_domain=? AND draft_type IN ('guide','comparison') AND %s "
         "ORDER BY COALESCE(published_at, updated_at, created_at) DESC")
    rows = db.all_(q % "status='published' AND live_url IS NOT NULL", (domain,))
    live = True
    if not rows and drafts_if_empty:
        rows = db.all_(q % "status IN ('draft','approved','scheduled')", (domain,))
        live = False
    out = []
    for r in rows:
        _, body, _ = content_review.load(r['id'], domain)
        if not body:
            continue
        if not live and body.get('layout') != 'article':
            continue                                           # old plain drafts would misrepresent the page
        cover = body.get('cover') or content_review.styled(body, domain)[1]
        out.append(dict(id=r['id'], title=body.get('title') or r['title'] or 'Untitled', summary=_summary(body),
                        cover=cover or '', category=(body.get('category') or ('Comparisons' if r['draft_type'] == 'comparison'
                                                                                 else 'Guides')).strip(),
                        url=urllib.parse.urlsplit(r['live_url']).path if live and r['live_url'] else '',
                        at=r['published_at'] or r['updated_at'] or r['created_at'], minutes=_minutes(body), live=live))
    return out


# ---- render --------------------------------------------------------------------------------------------------

HUB_CSS = '''
A.pk-hub{max-width:1100px;margin:0 auto}
A .pk-hub-head{text-align:center;max-width:640px;margin:0 auto 34px}
A .pk-hub-head .pk-step{margin:0 0 10px}
A .pk-hub-head h1{font-family:var(--h);font-weight:400;text-transform:UPH;color:var(--accent);font-size:44px;line-height:1.1;margin:0 0 14px}
A .pk-hub-head .pk-dek{margin:0;font-size:19px}
A .pk-cats{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:0 0 34px}
A .pk-cats label{cursor:pointer}
A .pk-radio{position:absolute;opacity:0;pointer-events:none}
A .pk-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:40px 26px}
A .pk-story{display:block;color:inherit!important;text-decoration:none!important}
A .pk-story .pk-img{display:block;aspect-ratio:4/5;background:var(--soft);overflow:hidden;margin:0 0 14px;border-radius:RADBOX}
A .pk-story img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s ease}
A .pk-story:hover img{transform:scale(1.03)}
A .pk-story .pk-meta{margin:0 0 8px}
A .pk-story h2{font-size:21px;margin:0 0 8px;line-height:1.25}
A .pk-story p{font-size:14.5px;line-height:1.55;margin:0;color:var(--ink)}
A .pk-feat{grid-column:1/-1;display:grid;grid-template-columns:1.35fr 1fr;gap:34px;align-items:center}
A .pk-feat .pk-img{aspect-ratio:4/3;margin:0}
A .pk-feat h2{font-size:32px}
A .pk-feat p{font-size:16.5px}
A .pk-soon{font-family:var(--l);font-size:10px;text-transform:uppercase;letter-spacing:.08em;background:#fff1c2;color:#5c4400;padding:2px 6px}
A .pk-ig{margin:70px 0 0;border-top:1px solid var(--ink);padding-top:22px}
A .pk-ig-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 16px}
A .pk-ig-head h2{margin:0;font-size:22px}
A .pk-ig-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
A .pk-ig-grid a{display:block;aspect-ratio:1;overflow:hidden;background:var(--soft)}
A .pk-ig-grid img{width:100%;height:100%;object-fit:cover;display:block}
@media (max-width:900px){A .pk-grid{grid-template-columns:repeat(2,1fr)}A .pk-feat{grid-template-columns:1fr;gap:16px}}
@media (max-width:640px){A .pk-grid{grid-template-columns:1fr}A .pk-hub-head h1{font-size:32px}A .pk-feat h2{font-size:24px}A .pk-ig-grid{grid-template-columns:repeat(3,1fr)}}
'''


def _css(style, cats):
    import article_render
    base = article_render.css(style)[len('<style>'):-len('</style>')]
    r = int(style.get('radius') or 0)
    a = '.' + article_render.FOLD
    rules = HUB_CSS.replace('A.', a + '.').replace('A ', a + ' ').replace('UPH', 'uppercase' if style.get('heading_upper') else 'none') \
        .replace('RADBOX', '%dpx' % min(r, 12))
    # category filter without JavaScript (Shopify may strip scripts from page bodies): radio + :checked
    for i in range(1, len(cats) + 1):
        rules += ('%s #pk-c%d:checked ~ .pk-grid .pk-story:not([data-c="%d"]){display:none}' % (a, i, i) +
                  '%s #pk-c%d:checked ~ .pk-grid .pk-feat{grid-column:auto;display:block}' % (a, i) +
                  '%s #pk-c%d:checked ~ .pk-grid .pk-feat .pk-img{aspect-ratio:4/5;margin:0 0 14px}' % (a, i) +
                  '%s #pk-c%d:checked ~ .pk-cats label[for="pk-c%d"] .pk-tag{background:var(--ink);color:#fff}' % (a, i, i))
    rules += '%s #pk-c0:checked ~ .pk-cats label[for="pk-c0"] .pk-tag{background:var(--ink);color:#fff}' % a
    return '<style>%s%s</style>' % (base, rules)


def _img(url, width):
    import article_render
    return article_render._img(url, width)


def render(domain, stories, style, brand='', instagram=None, preview=False, link=None):
    """The page's HTML. instagram: {'handle', 'photos': [(img, post url)]} or None.
    link(story) -> href; defaults to the story's path on the store."""
    link = link or (lambda s: s['url'] or '#')
    cats = []
    for s in stories:
        if s['category'] and s['category'] not in cats:
            cats.append(s['category'])
    cid = {c: i + 1 for i, c in enumerate(cats)}
    out = [_css(style, cats), '<div class="pk-a pk-hub">']
    out.append('<header class="pk-hub-head"><span class="pk-step">%s</span><h1>%s</h1><p class="pk-dek">%s</p></header>' % (
        E(('%s Journal' % brand) if brand else 'Journal'), TITLE,
        E('Guides, comparisons and answers to the questions people ask before they buy.')))
    if len(cats) > 1:
        out.append('<input class="pk-radio" type="radio" name="pk-cat" id="pk-c0" checked>' +
                   ''.join('<input class="pk-radio" type="radio" name="pk-cat" id="pk-c%d">' % cid[c] for c in cats))
        out.append('<div class="pk-cats"><label for="pk-c0"><span class="pk-tag">All</span></label>%s</div>' % ''.join(
            '<label for="pk-c%d"><span class="pk-tag">%s</span></label>' % (cid[c], E(c)) for c in cats))
    if not stories:
        out.append('<p class="pk-note" style="text-align:center">No stories yet.</p>')
    cards = []
    for n, s in enumerate(stories):
        soon = '' if s['live'] else '<span class="pk-soon">Not live yet</span>'
        cards.append(
            '<a class="pk-story%s" data-c="%d" href="%s"><span class="pk-img">%s</span><div><div class="pk-meta">'
            '<span class="pk-tag">%s</span><span>%d min read</span>%s</div><h2>%s</h2><p>%s</p></div></a>' % (
                ' pk-feat' if n == 0 else '', cid.get(s['category'], 0), E(link(s)),
                ('<img src="%s" alt="" loading="%s">' % (E(_img(s['cover'], 1200 if n == 0 else 700)), 'eager' if n == 0 else 'lazy'))
                if s['cover'] else '', E(s['category']), s['minutes'], soon, E(s['title']), E(s['summary'])))
    out.append('<div class="pk-grid">%s</div>' % ''.join(cards))
    ig = instagram or {}
    if ig.get('photos'):
        h = ig.get('handle', '')
        out.append('<section class="pk-ig"><div class="pk-ig-head"><h2>From our Instagram</h2>%s</div><div class="pk-ig-grid">%s'
                   '</div></section>' % (
                       ('<a class="pk-note" href="https://www.instagram.com/%s/" rel="noopener">@%s</a>' % (E(h), E(h))) if h else '',
                       ''.join('<a href="%s" rel="noopener"><img src="%s" alt="" loading="lazy"></a>' % (
                           E(post or ('https://www.instagram.com/%s/' % h if h else '#')), E(img)) for img, post in ig['photos'][:6])))
    out.append('</div>')
    live = [s for s in stories if s['live'] and s['url']]
    if live and not preview:
        base = 'https://%s' % domain
        ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": base + s['url'], "name": s['title']} for i, s in enumerate(live)]}
        out.append('<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False).replace('</', '<\\/'))
    return ''.join(out)


def _instagram(domain, for_store=False):
    """{'handle', 'photos': [(img url, post url)]} if the owner chose to show Instagram on the page, else None.
    for_store: photos copied into the store's Shopify Files where allowed (never left pointing at Instagram)."""
    import social_photos
    st = settings(domain)
    if not st.get('instagram'):
        return None
    social_photos.init()
    rows = db.all_("SELECT token, meta FROM content_media WHERE store_domain=? AND source='instagram' "
                   "ORDER BY created_at DESC LIMIT 6", (domain,))
    import article_learning
    photos = []
    for r in rows:
        url = article_learning.media_url(r['token'])
        if for_store:
            url = _hosted(domain, url)
        try:
            post = json.loads(r['meta'] or '{}').get('post', '')
        except ValueError:
            post = ''
        photos.append((url, post))
    return dict(handle=social_photos.handle(domain), photos=photos) if photos else None


def _hosted(domain, url):
    """Our uploaded/Instagram photo -> its copy in the store's Shopify Files (made once), else unchanged."""
    import shopify_connect
    m = shopify_connect._MEDIA.search(url or '')
    if not m:
        return url
    conn = shopify_connect.connection(domain)
    if not conn or not shopify_connect.can_upload(domain):
        return url
    try:
        return shopify_connect._media_shopify(m.group(1), conn['shop']) or \
            shopify_connect._media_shopify(m.group(1), conn['shop'], shopify_connect.upload_file(domain, url, TITLE))
    except shopify_connect.ShopifyError:
        return url


def _brand(domain):
    return (db.brand(domain) or {}).get('brand_name') or ''


def page_html(domain, for_store=True):
    """What goes into the Shopify page body: live stories only."""
    import brand_style
    stories = items(domain)
    if for_store:
        for s in stories:
            s['cover'] = _hosted(domain, s['cover'])
    return render(domain, stories, brand_style.get(domain), _brand(domain), _instagram(domain, for_store=for_store))


def preview(q):
    """GET /content/stories?d=: the hub as a shopper would see it (drafts stand in when nothing is live)."""
    import accounts
    import brand_style
    import content_agent
    domain = q.get('d', '')
    if not content_agent.enabled() or not accounts.can_see(domain):
        return 404, '<h1>Not found</h1>'
    stories = items(domain, drafts_if_empty=True)
    link = lambda s: s['url'] and ('https://%s%s' % (domain, s['url'])) or \
        '/content/preview?' + urllib.parse.urlencode(dict(d=domain, id=s['id']))
    body = render(domain, stories, brand_style.get(domain), _brand(domain), _instagram(domain), preview=True, link=link)
    page = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<base target="_top"><style>body{margin:0;background:#fff}.pk-wrap{padding:48px 20px 80px}</style></head>'
            '<body><div class="pk-wrap">%s</div></body></html>') % body
    if q.get('embed'):
        return 200, page
    bar = ('<div style="position:sticky;top:0;z-index:5;background:#0b1b35;color:#fff;font:600 13px/1.4 -apple-system,'
           'Helvetica,Arial,sans-serif;padding:10px 16px;display:flex;justify-content:space-between;gap:12px">'
           '<span>Preview: your stories page. %s</span><a style="color:#fff" href="%s">Back</a></div>') % (
        'Live articles only.' if stories and stories[0]['live'] else 'Your drafts stand in until an article is live.',
        E('/content?' + urllib.parse.urlencode(dict(d=domain, lane='articles', view='published'))))
    return 200, page.replace('<body>', '<body>' + bar, 1)


# ---- on the store ------------------------------------------------------------------------------------------

def settings(domain):
    import content_setup
    return content_setup.get(domain).get('stories_hub') or {}


def _put(domain, hub):
    import content_setup
    s = content_setup.get(domain)
    if hub is None:
        s.pop('stories_hub', None)
    else:
        s['stories_hub'] = hub
    content_setup.put(domain, s)


def live_url(domain):
    hub = settings(domain)
    return ('https://%s/pages/%s' % (domain, hub['handle'])) if hub.get('id') else ''


def publish(domain):
    """Create the page on the store, or rewrite it. Returns its URL. Raises shopify_connect.ShopifyError."""
    import shopify_connect
    if shopify_connect.mismatch(domain):
        raise shopify_connect.ShopifyError('The connected Shopify isn\'t this store\'s own.')
    shop, _ = shopify_connect._token(domain)
    hub = settings(domain)
    body = page_html(domain)
    if hub.get('id') and hub.get('shop') == shop:
        try:
            d = shopify_connect.gql(domain, 'mutation($id:ID!,$p:PageUpdateInput!){pageUpdate(id:$id,page:$p){page{id handle} '
                                            'userErrors{field message}}}', dict(id=hub['id'], p=dict(body=body)))
            page = d['pageUpdate'].get('page')
        except shopify_connect.ShopifyError:
            page = None
        if page:
            hub.update(handle=page['handle'], at=time.time())
            _put(domain, hub)
            return live_url(domain)
        hub = {k: v for k, v in hub.items() if k == 'instagram'}   # deleted in Shopify by hand: make it again
    d = shopify_connect.gql(domain, 'mutation($p:PageCreateInput!){pageCreate(page:$p){page{id handle} userErrors{field message}}}',
                            dict(p=dict(title=TITLE, handle=HANDLE, body=body, isPublished=True)))
    shopify_connect._user_errors(d['pageCreate'])
    p = d['pageCreate']['page']
    _put(domain, dict(hub, id=p['id'], handle=p['handle'], shop=shop, at=time.time()))
    return live_url(domain)


def take_down(domain):
    import shopify_connect
    hub = settings(domain)
    if hub.get('id'):
        try:
            shopify_connect.delete(domain, 'page', hub['id'])
        except shopify_connect.ShopifyError:
            pass                                          # already gone in Shopify
    keep = {k: v for k, v in hub.items() if k == 'instagram'}
    _put(domain, keep or None)


def sync(domain):
    """After an article goes live or comes down: rewrite the page if the owner put one up. Never raises."""
    try:
        if settings(domain).get('id'):
            publish(domain)
    except Exception:                                                   # noqa: BLE001 - never block a publish
        pass


def set_instagram(domain, on):
    hub = settings(domain)
    hub['instagram'] = bool(on)
    _put(domain, hub)


# ---- the panel on the AEO articles "Live" tab ---------------------------------------------------------------

def panel(domain, q=None):
    import shopify_connect
    import social_photos
    q = q or {}
    hub = settings(domain)
    url = live_url(domain)
    n_live = len(items(domain))
    hidden = lambda a: ('<input type="hidden" name="d" value="%s"><input type="hidden" name="action" value="%s">' % (E(domain), a))
    can = shopify_connect.configured() and shopify_connect.connection(domain) and not shopify_connect.mismatch(domain)
    if url:
        state = ('<p class="cr-muted">Live at <a href="%s" target="_blank" rel="noopener">%s</a>. It updates itself when an '
                 'article goes live or comes down. Add it to your store menu in Shopify (Online Store › Navigation).</p>' % (E(url), E(url)))
        buttons = ('<form method="post" action="/content">%s<button class="ca-btn">Update it now</button></form>'
                   '<form method="post" action="/content">%s<button class="ca-btn" title="Deletes the page from your store. '
                   'Your articles stay live.">Take it down</button></form>') % (hidden('stories_publish'), hidden('stories_remove'))
    elif can:
        state = ('<p class="cr-muted">One page on your store that lists every live article as a card, in your look. %s</p>' % (
            '%d article%s live now.' % (n_live, '' if n_live == 1 else 's') if n_live else
            'Nothing is live yet, so the preview shows your drafts. Put it up once your first article is live.'))
        buttons = ('<form method="post" action="/content">%s<button class="ca-btn ca-primary"%s>Put it on your store</button></form>'
                   % (hidden('stories_publish'), '' if n_live else ' disabled'))
    else:
        wrong = shopify_connect.connection(domain) and shopify_connect.mismatch(domain)
        state = ('<p class="cr-muted">One page on your store that lists every live article as a card, in your look. %s</p>' % (
            'The connected Shopify isn\'t this store\'s own, so it can\'t go on the store yet.' if wrong else
            'Connect Shopify in Settings to put it on your store.'))
        buttons = ''
    ig_handle = social_photos.handle(domain)
    has_ig = bool(social_photos.photos(domain))
    ig = ''
    if has_ig:
        ig = ('<form method="post" action="/content" class="sh-ig">%s<label><input type="checkbox" name="on" value="1"%s '
              'onchange="this.form.submit()"> Show 6 photos from @%s at the bottom</label></form>') % (
            hidden('stories_instagram'), ' checked' if hub.get('instagram') else '', E(ig_handle))
    err = ('<p class="ca-error">%s</p>' % E(q['error'])) if q.get('error') else ''
    src = '/content/stories?' + urllib.parse.urlencode(dict(d=domain, embed=1))
    full = '/content/stories?' + urllib.parse.urlencode(dict(d=domain))
    return ('<section class="cr-box sh-box"><div class="sh-top"><div><h2>Stories page</h2>%s%s%s</div>'
            '<div class="ca-actions">%s<a class="ca-btn" href="%s" target="_blank" rel="noopener">Open full preview</a></div></div>'
            '<iframe class="sh-frame" title="Stories page preview" src="%s" loading="lazy"></iframe></section>') % (
        state, ig, err, buttons, E(full), E(src))


CSS = """
.sh-box{margin:0 0 22px}
.sh-top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap}
.sh-top h2{margin:0 0 6px}
.sh-top .ca-actions{display:flex;gap:8px;flex-wrap:wrap}
.sh-top .ca-actions form{margin:0}
.sh-ig{margin:6px 0 0;font-size:14px}
.sh-frame{width:100%;height:560px;border:1px solid var(--line,#e3e8ef);border-radius:10px;margin-top:14px;background:#fff}
"""
