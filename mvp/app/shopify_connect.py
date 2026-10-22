"""Shopify connection and publishing for Agentic AI Search Optimization.

Decided 15 Oct 2026 (DECISIONS.md): build publishing now, before a brand pays.

  Connect   The merchant types their myshopify address in Settings, Shopify asks
            them to approve access (OAuth), and we keep an offline access token.
            A private app ("custom distribution") made in Kelian's Shopify
            Partner org: no App Store review. Free.
  Publish   An APPROVED draft goes live with one click, or by itself when its
            calendar slot arrives:
              product fix  -> the product's title and description
              FAQ          -> appended to the product's live description
                              (inside a marked block, so re-publishing replaces it)
              comparison   -> a new store page
              guide        -> a new blog post
  Undo      Every publish keeps what was there before; undo restores it, or
            deletes the page/post the agent created.

Settings in mvp/app/.env (read with config.env, never os.environ):
  SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET  from the app in the Dev Dashboard
  PRODUKTO_BASE_URL                          e.g. https://app.getprodukto.com

Nothing here runs without the merchant's approval of the draft. Access tokens
never leave the server and are never shown on a page.
"""
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import db

API_VERSION = '2026-10'
SCOPES = ('read_products,write_products,read_content,write_content,read_online_store_pages,write_online_store_pages,'
          'read_files,write_files')   # files (20 Oct 2026): photos the owner uploads for an article go into Shopify Files
FAQ_START, FAQ_END = '<!-- produkto:faq -->', '<!-- /produkto:faq -->'
_SHOP = re.compile(r'^[a-z0-9][a-z0-9-]*\.myshopify\.com$')
_expected = {}               # store domain -> its myshopify address, read once
_states = {}                 # OAuth state -> (store_domain, created_at); short-lived, in memory


class ShopifyError(Exception):
    pass


def init():
    with db.conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS shopify_connections (store_domain TEXT PRIMARY KEY, shop TEXT NOT NULL, '
                  'token TEXT NOT NULL, scopes TEXT, connected_at REAL, connected_by TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS content_publish_log (id INTEGER PRIMARY KEY, draft_id INTEGER, '
                  'store_domain TEXT, action TEXT, target TEXT, before TEXT, after TEXT, live_url TEXT, '
                  'at REAL, by TEXT, undone_at REAL)')


def configured():
    return bool(config.env('SHOPIFY_CLIENT_ID') and config.env('SHOPIFY_CLIENT_SECRET'))


def connection(domain):
    init()
    return db.one('SELECT store_domain, shop, scopes, connected_at, connected_by FROM shopify_connections '
                  'WHERE store_domain=?', (domain,))


def _token(domain):
    row = db.one('SELECT shop, token FROM shopify_connections WHERE store_domain=?', (domain,))
    if not row:
        raise ShopifyError('This store isn\'t connected to Shopify yet.')
    return row['shop'], row['token']


def clean_shop(text):
    """'produkto-test', 'https://produkto-test.myshopify.com/admin' -> 'produkto-test.myshopify.com' or ''."""
    t = (text or '').strip().lower()
    t = re.sub(r'^https?://', '', t).split('/')[0]
    if t and '.' not in t:
        t += '.myshopify.com'
    return t if _SHOP.match(t) else ''


def expected_shop(domain):
    """The store's own myshopify address, from its public /meta.json, or '' when it can't be read.
    A store can only connect the Shopify admin it really is (17 Oct 2026): Clubhouse Skin connected to
    produkto-test, so every drop on Live failed with "couldn't find the product"."""
    if _SHOP.match(domain or ''):
        return domain
    if domain in _expected:
        return _expected[domain]
    import catalog
    try:
        status, body = catalog._get('https://%s/meta.json' % domain, timeout=15)
        _expected[domain] = clean_shop(json.loads(body).get('myshopify_domain', '')) if status == 200 else ''
    except Exception:                                           # noqa: BLE001
        return ''
    return _expected[domain]


def mismatch(domain):
    """The connected shop when it isn't this store's own Shopify admin, else ''."""
    conn = connection(domain)
    want = expected_shop(domain) if conn else ''
    return conn['shop'] if conn and want and conn['shop'] != want else ''


def _base():
    return (config.env('PRODUKTO_BASE_URL') or 'http://localhost:%d' % config.PORT).rstrip('/')


def redirect_uri():
    return _base() + '/shopify/callback'


def install_url(domain, shop):
    """Where to send the merchant to approve access."""
    state = secrets.token_urlsafe(24)
    _states[state] = (domain, time.time())
    for k in [k for k, (_, t) in _states.items() if time.time() - t > 900]:
        _states.pop(k, None)
    return 'https://%s/admin/oauth/authorize?%s' % (shop, urllib.parse.urlencode(dict(
        client_id=config.env('SHOPIFY_CLIENT_ID'), scope=SCOPES, redirect_uri=redirect_uri(), state=state)))


def valid_hmac(q):
    """Shopify signs the callback's query string with the app secret."""
    given = q.get('hmac', '')
    msg = '&'.join('%s=%s' % (k, v) for k, v in sorted(q.items()) if k not in ('hmac', 'signature'))
    want = hmac.new(config.env('SHOPIFY_CLIENT_SECRET').encode(), msg.encode(), hashlib.sha256).hexdigest()
    return bool(given) and hmac.compare_digest(given, want)


def _post_json(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers=dict({'Content-Type': 'application/json', 'Accept': 'application/json'},
                                              **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ShopifyError('Shopify answered %s.' % e.code)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise ShopifyError('Couldn\'t reach Shopify (%s).' % e)


def finish(q, user_email=None):
    """The OAuth callback. Returns the store domain it connected."""
    import accounts
    state = q.get('state', '')
    domain, made = _states.pop(state, (None, 0))
    shop = clean_shop(q.get('shop', ''))
    if not domain or time.time() - made > 900:
        raise ShopifyError('That connection link expired. Start again from Settings.')
    if not shop or not valid_hmac(q):
        raise ShopifyError('Shopify\'s answer couldn\'t be verified. Start again from Settings.')
    if not accounts.can_see(domain):
        raise ShopifyError('You can\'t connect a store you don\'t own.')
    want = expected_shop(domain)
    if want and shop != want:
        raise ShopifyError('That Shopify store (%s) isn\'t %s. Connect %s instead.' % (shop, domain, want))
    res = _post_json('https://%s/admin/oauth/access_token' % shop, dict(
        client_id=config.env('SHOPIFY_CLIENT_ID'), client_secret=config.env('SHOPIFY_CLIENT_SECRET'), code=q.get('code', '')))
    if not res.get('access_token'):
        raise ShopifyError('Shopify didn\'t give an access token.')
    init()
    with db.conn() as c:
        c.execute('INSERT OR REPLACE INTO shopify_connections VALUES (?,?,?,?,?,?)',
                  (domain, shop, res['access_token'], res.get('scope', ''), time.time(), user_email))
    return domain


def disconnect(domain):
    init()
    db.write('DELETE FROM shopify_connections WHERE store_domain=?', (domain,))


def gql(domain, query, variables=None):
    shop, token = _token(domain)
    res = _post_json('https://%s/admin/api/%s/graphql.json' % (shop, API_VERSION),
                     dict(query=query, variables=variables or {}), {'X-Shopify-Access-Token': token})
    if res.get('errors'):
        raise ShopifyError('Shopify refused the request: %s' % str(res['errors'])[:300])
    return res['data']


def _user_errors(payload):
    errs = (payload or {}).get('userErrors') or []
    if errs:
        raise ShopifyError('; '.join(e.get('message', '') for e in errs))


# ---- products ---------------------------------------------------------------------

def product(domain, handle):
    d = gql(domain, 'query($q:String!){products(first:1, query:$q){nodes{id title handle descriptionHtml onlineStoreUrl}}}',
            dict(q='handle:%s' % handle))
    nodes = d['products']['nodes']
    if not nodes or nodes[0]['handle'] != handle:
        raise ShopifyError('Couldn\'t find the product "%s" in your Shopify store.' % handle)
    return nodes[0]


def update_product(domain, pid, title=None, body=None):
    fields = dict(id=pid)
    if title is not None:
        fields['title'] = title
    if body is not None:
        fields['descriptionHtml'] = body
    d = gql(domain, 'mutation($p:ProductUpdateInput!){productUpdate(product:$p){product{id title handle onlineStoreUrl}'
                    ' userErrors{field message}}}', dict(p=fields))
    _user_errors(d['productUpdate'])
    return d['productUpdate']['product']


def with_faq(body, faq_html):
    """The description with our FAQ block added, or replaced if an earlier one is there."""
    block = '%s\n<h2>Questions and answers</h2>\n%s\n%s' % (FAQ_START, faq_html, FAQ_END)
    if FAQ_START in (body or '') and FAQ_END in body:
        return re.sub(re.escape(FAQ_START) + '.*?' + re.escape(FAQ_END), lambda m: block, body, flags=re.S)
    return (body or '') + '\n' + block


# ---- pages and blog posts -----------------------------------------------------------

def create_page(domain, title, body):
    d = gql(domain, 'mutation($p:PageCreateInput!){pageCreate(page:$p){page{id handle} userErrors{field message}}}',
            dict(p=dict(title=title, body=body, isPublished=True)))
    _user_errors(d['pageCreate'])
    return d['pageCreate']['page']


def _blog(domain):
    d = gql(domain, '{blogs(first:1){nodes{id handle}}}')
    if d['blogs']['nodes']:
        return d['blogs']['nodes'][0]
    d = gql(domain, 'mutation{blogCreate(blog:{title:"Journal"}){blog{id handle} userErrors{field message}}}')
    _user_errors(d['blogCreate'])
    return d['blogCreate']['blog']


def create_article(domain, title, body, author, image='', summary='', tags=None, published=True):
    blog = _blog(domain)
    a = dict(blogId=blog['id'], title=title, body=body, isPublished=published, author=dict(name=author))
    a.update(_article_extras(image, summary, tags))
    d = gql(domain, 'mutation($a:ArticleCreateInput!){articleCreate(article:$a){article{id handle} userErrors{field message}}}',
            dict(a=a))
    _user_errors(d['articleCreate'])
    return d['articleCreate']['article'], blog


def _article_extras(image='', summary='', tags=None):
    """Cover photo, the excerpt the blog page shows, and the category as a tag (designed articles, 19 Oct)."""
    out = {}
    if image:
        out['image'] = dict(url=re.sub(r'([?&])width=\d+', r'\1', image).rstrip('?&'), altText=summary[:120] or 'Cover')
    if summary:
        out['summary'] = summary
    if tags:
        out['tags'] = [t for t in tags if t][:5]
    return out


def update_article(domain, gid, title=None, body=None, published=None, image='', summary='', tags=None):
    a = _article_extras(image, summary, tags)
    if title is not None:
        a['title'] = title
    if body is not None:
        a['body'] = body
    if published is not None:
        a['isPublished'] = published
    d = gql(domain, 'mutation($id:ID!,$a:ArticleUpdateInput!){articleUpdate(id:$id,article:$a){article{id handle blog{handle}} '
                    'userErrors{field message}}}', dict(id=gid, a=a))
    _user_errors(d['articleUpdate'])
    return d['articleUpdate']['article']


def admin_article_url(shop, gid):
    return 'https://admin.shopify.com/store/%s/content/articles/%s' % (shop.split('.')[0], gid.rsplit('/', 1)[-1])


def preview(domain, draft_id):
    """Put a designed article on the store as a HIDDEN draft (customers can't see it) so the merchant can
    preview it in their own theme. Updates the same hidden draft on later calls. Returns the admin link."""
    import content_review
    row, body, prev = content_review.load(draft_id, domain)
    if not row or body.get('layout') != 'article':
        raise ShopifyError('Only AEO articles can be previewed on the store.')
    if row['status'] == 'published':
        raise ShopifyError('This article is already live.')
    shop, _ = _token(domain)
    host_uploads(domain, body)
    content_review.rebuild(body, row['draft_type'])
    name = body.get('author') or (db.brand(domain) or {}).get('brand_name') or 'The team'
    extras = dict(image=body.get('cover', ''), summary=body.get('dek', ''), tags=[body.get('category', '')])
    sd = body.get('shopify_draft') or {}
    if sd.get('id') and sd.get('shop') == shop:
        art = update_article(domain, sd['id'], title=body.get('title'), body=_clean(body.get('html', '')), published=False,
                             **extras)
        handle = art['handle']
    else:
        art, blog = create_article(domain, body.get('title') or row['title'], _clean(body.get('html', '')), name,
                                   published=False, **extras)
        handle = art['handle']
    body['shopify_draft'] = dict(id=art['id'], handle=handle, shop=shop, at=time.time())
    content_review.save_version(draft_id, body, prev, author='agent')
    return admin_article_url(shop, art['id'])


def delete(domain, kind, gid):
    name, field = {'page': ('pageDelete', 'deletedPageId'), 'article': ('articleDelete', 'deletedArticleId')}[kind]
    d = gql(domain, 'mutation($id:ID!){%s(id:$id){%s userErrors{field message}}}' % (name, field), dict(id=gid))
    _user_errors(d[name])


# ---- the owner's uploaded photos, into Shopify Files (20 Oct 2026) ----------------------------------------
# Photos uploaded in the article editor live at app.getprodukto.com/content/media/... until the article goes to the
# store. Then each one is copied into the store's own Shopify Files (Shopify fetches it from our public link), and the
# article points at Shopify's copy, so the store never depends on our server. One upload per photo per store.

FILE_WAIT = 25          # seconds to wait for Shopify to finish processing a photo


def can_upload(domain):
    conn = connection(domain)
    return bool(conn and 'write_files' in (conn['scopes'] or ''))


def _media_shopify(token, shop, url=None):
    import json as _j
    import article_learning
    article_learning._media_init()
    with db.conn() as c:
        cols = [r[1] for r in c.execute('PRAGMA table_info(content_media)')]
        if 'shopify' not in cols:
            c.execute('ALTER TABLE content_media ADD COLUMN shopify TEXT')
    row = db.one('SELECT shopify FROM content_media WHERE token=?', (token,))
    if not row:
        return None
    known = _j.loads(row['shopify'] or '{}')
    if url:
        known[shop] = url
        db.write('UPDATE content_media SET shopify=? WHERE token=?', (_j.dumps(known), token))
    return known.get(shop)


def upload_file(domain, source_url, alt=''):
    """Copy one image into the store's Shopify Files. Returns Shopify's CDN url."""
    d = gql(domain, 'mutation($f:[FileCreateInput!]!){fileCreate(files:$f){files{id fileStatus ... on MediaImage{image{url}}} '
                    'userErrors{field message}}}', dict(f=[dict(originalSource=source_url, contentType='IMAGE', alt=alt[:120])]))
    _user_errors(d['fileCreate'])
    f = (d['fileCreate']['files'] or [{}])[0]
    url = ((f.get('image') or {}).get('url'))
    end = time.time() + FILE_WAIT
    while not url and time.time() < end:
        time.sleep(1)
        n = gql(domain, 'query($id:ID!){node(id:$id){... on MediaImage{fileStatus image{url}}}}', dict(id=f['id']))['node'] or {}
        if n.get('fileStatus') == 'FAILED':
            raise ShopifyError('Shopify couldn\'t process that photo.')
        url = (n.get('image') or {}).get('url')
    if not url:
        raise ShopifyError('Shopify is still processing a photo. Try again in a minute.')
    return url


_MEDIA = re.compile(r'/content/media/([\w-]+)\.jpg$')


def host_uploads(domain, body):
    """Swap the article's uploaded photos for copies in the store's Shopify Files. Changes body in place.
    Returns how many photos are still on Produkto's server (no permission yet, or Shopify was slow)."""
    o = body.get('photo_overrides') or {}
    left = 0
    conn = connection(domain)
    shop = conn['shop'] if conn else None
    for slot, url in list(o.items()):
        m = _MEDIA.search(url or '')
        if not m:
            continue
        if not shop or not can_upload(domain):
            left += 1
            continue
        try:
            hosted = _media_shopify(m.group(1), shop) or _media_shopify(m.group(1), shop, upload_file(domain, url, body.get('title', '')))
        except ShopifyError:
            left += 1
            continue
        o[slot] = hosted
    body['photos_on_produkto'] = left
    return left


# ---- publish and undo ---------------------------------------------------------------

def _clean(html_text):
    return re.sub(r' class="cr-[a-z-]+"', '', html_text or '')


def related(domain, handle):
    """A link from a product page to the live guides and comparisons that feature it (internal links,
    18 Oct 2026). Relative paths, so they work on the store's own domain. '' when there are none."""
    import content_review
    links = []
    for r in db.all_("SELECT id, title, live_url FROM content_drafts WHERE store_domain=? AND status='published' "
                     "AND draft_type IN ('guide','comparison') AND live_url IS NOT NULL ORDER BY published_at DESC",
                     (domain,)):
        _, b, _ = content_review.load(r['id'], domain)
        if handle in [p.get('handle') for p in (b or {}).get('products') or []]:
            path = urllib.parse.urlsplit(r['live_url']).path
            links.append('<a href="%s">%s</a>' % (_esc(path), _esc(b.get('title') or r['title'])))
    return ('\n<p>Read more: %s</p>' % ' · '.join(links[:3])) if links else ''


def _esc(t):
    import html
    return html.escape(t or '', quote=True)


def publish(domain, draft_id, by=None):
    """Put an approved draft live. Returns the live URL. Raises ShopifyError with a plain reason."""
    import content_agent
    import content_review
    row, body, _ = content_review.load(draft_id, domain)
    if not row:
        raise ShopifyError('Draft not found.')
    if row['status'] not in ('approved', 'scheduled'):
        raise ShopifyError('Only approved drafts can be published.')
    if content_agent.placeholders(body):
        raise ShopifyError('This draft still has gaps to fill.')
    if body.get('layout') == 'article':
        host_uploads(domain, body)
    content_review.rebuild(body, row['draft_type'])
    t = row['draft_type']
    shop, _ = _token(domain)
    if t in ('product_fix', 'faq'):
        handle = (body.get('product') or {}).get('handle')
        live = product(domain, handle)
        before = dict(title=live['title'], body=live['descriptionHtml'])
        if t == 'product_fix':
            new_body = _clean(body.get('html') or body.get('description_html', '')) + related(domain, handle)
            # Keep an FAQ block published earlier: the page fix only replaces the description above it.
            m = re.search(re.escape(FAQ_START) + '.*?' + re.escape(FAQ_END), live['descriptionHtml'] or '', re.S)
            if m:
                new_body += '\n' + m.group(0)
            after = dict(title=body.get('title') or live['title'], body=new_body)
        else:
            after = dict(title=live['title'], body=with_faq(live['descriptionHtml'], _clean(body.get('html', ''))))
        res = update_product(domain, live['id'], after['title'], after['body'])
        url = res.get('onlineStoreUrl') or 'https://%s/products/%s' % (shop, handle)
        action, target = 'product', live['id']
    elif t == 'comparison':
        page = create_page(domain, body.get('title') or row['title'], _clean(body.get('html', '')))
        before, after = None, dict(title=body.get('title'), id=page['id'])
        url = 'https://%s/pages/%s' % (shop, page['handle'])
        action, target = 'page', page['id']
    elif t == 'guide':
        name = body.get('author') or (db.brand(domain) or {}).get('brand_name') or 'The team'
        extras = dict(image=body.get('cover', ''), summary=body.get('dek', ''), tags=[body.get('category', '')]) \
            if body.get('layout') == 'article' else {}
        sd = body.get('shopify_draft') or {}
        if sd.get('id') and sd.get('shop') == shop:          # the hidden preview draft goes visible, same article
            art = update_article(domain, sd['id'], title=body.get('title') or row['title'],
                                 body=_clean(body.get('html', '')), published=True, **extras)
            blog = art.get('blog') or _blog(domain)
        else:
            art, blog = create_article(domain, body.get('title') or row['title'], _clean(body.get('html', '')), name,
                                       **extras)
        before, after = None, dict(title=body.get('title'), id=art['id'])
        url = 'https://%s/blogs/%s/%s' % (shop, blog['handle'], art['handle'])
        action, target = 'article', art['id']
    else:
        raise ShopifyError('This kind of draft can\'t be published yet.')
    now = time.time()
    with db.conn() as c:
        c.execute('INSERT INTO content_publish_log (draft_id, store_domain, action, target, before, after, live_url, at, by) '
                  'VALUES (?,?,?,?,?,?,?,?,?)', (draft_id, domain, action, target, json.dumps(before), json.dumps(after),
                                                   url, now, by))
        c.execute("UPDATE content_drafts SET status='published', published_at=?, live_url=?, updated_at=? WHERE id=?",
                  (now, url, now, draft_id))
    _mark_done(domain, draft_id)
    if t in ('guide', 'comparison'):
        _resync_stories(domain)
    return url


def _resync_stories(domain):
    """The stories page (stories_hub.py) lists live articles: rewrite it in the background after one changes."""
    import threading
    import stories_hub
    if stories_hub.settings(domain).get('id'):
        threading.Thread(target=stories_hub.sync, args=(domain,), daemon=True).start()


def _mark_done(domain, draft_id):
    """Publishing a fix marks its Opportunity Done, which starts Opportunities' before/after tracking."""
    row = db.one('SELECT b.opportunity_kind k, b.opportunity_key key FROM content_drafts d JOIN content_briefs b '
                 'ON b.id=d.brief_id WHERE d.id=?', (draft_id,))
    if not row or not row['k']:
        return
    try:
        import opportunities
        opportunities.init()
        db.write('INSERT OR REPLACE INTO opportunity_status VALUES (?,?,?,?,?)',
                 (domain, row['k'], row['key'], 'done', time.time()))
    except Exception:                                       # noqa: BLE001 - tracking is a bonus, never block a publish
        pass


def last_publish(draft_id):
    init()
    return db.one('SELECT * FROM content_publish_log WHERE draft_id=? AND undone_at IS NULL ORDER BY id DESC LIMIT 1',
                  (draft_id,))


def undo(domain, draft_id):
    """Put back what was there before the last publish of this draft."""
    log = last_publish(draft_id)
    if not log or log['store_domain'] != domain:
        raise ShopifyError('Nothing to undo.')
    if log['action'] == 'product':
        before = json.loads(log['before'])
        update_product(domain, log['target'], before['title'], before['body'])
    else:
        delete(domain, log['action'], log['target'])
        import content_review
        row, body, prev = content_review.load(draft_id, domain)
        if body and body.get('shopify_draft', {}).get('id') == log['target']:
            body.pop('shopify_draft')
            content_review.save_version(draft_id, body, prev, author='agent')
    now = time.time()
    with db.conn() as c:
        c.execute('UPDATE content_publish_log SET undone_at=? WHERE id=?', (now, log['id']))
        c.execute("UPDATE content_drafts SET status='approved', published_at=NULL, live_url=NULL, updated_at=? WHERE id=?",
                  (now, draft_id))
    if log['action'] in ('article', 'page'):
        _resync_stories(domain)


def publish_due(now=None):
    """Publish approved drafts whose calendar slot has arrived, for connected stores. Returns (published, failed)."""
    import content_agent
    content_agent.init()           # a fresh server has no content tables until the agent is first opened
    init()
    now = now or time.time()
    done, failed = [], []
    rows = db.all_("SELECT d.id, d.store_domain FROM content_drafts d JOIN shopify_connections s ON s.store_domain=d.store_domain "
                   "WHERE d.status IN ('approved','scheduled') AND d.planned_at IS NOT NULL AND d.planned_at<=?", (now,))
    for r in rows:
        try:
            publish(r['store_domain'], r['id'], by='calendar')
            done.append(r['id'])
        except ShopifyError as e:
            failed.append((r['id'], str(e)))
            db.write('UPDATE content_drafts SET planned_at=NULL WHERE id=?', (r['id'],))   # don't retry every minute
    return done, failed
