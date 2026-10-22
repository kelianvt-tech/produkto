"""The stories page (stories_hub.py) and Instagram photos (social_photos.py), 20 Oct 2026. No network, no AI."""
import base64
import json
import time
import unittest
from unittest import mock

import db
from test_articles import Base, D, STYLE, article_body

JPG = b'\xff\xd8\xff\xe0' + b'0' * 50


def _draft(body, status='draft', live_url=None, kind='guide', at=None):
    at = at or time.time()
    with db.conn() as c:
        did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, live_url, published_at, "
                        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (D, kind, body.get('title', 't'), status, live_url, at if status == 'published' else None, at, at)).lastrowid
        c.execute("INSERT INTO content_draft_versions (draft_id, body, author, sources, open_facts, created_at) "
                  "VALUES (?,?,'agent','[]','[]',?)", (did, json.dumps(body), at))
    return did


def _connect(scopes='write_content'):
    import shopify_connect as s
    s.init()
    db.write("INSERT OR REPLACE INTO shopify_connections (store_domain, shop, token, scopes, connected_at, connected_by) "
             "VALUES (?, 'shop.myshopify.com', 'x', ?, 0, '')", (D, scopes))


class HubTest(Base):
    def test_live_articles_only_newest_first_with_filter_and_itemlist(self):
        import stories_hub as h
        _draft(article_body(title='Old one', category='Routines', cover='https://cdn.shopify.com/a/c1.jpg'), 'published',
               'https://shop.com/blogs/news/old-one', at=time.time() - 100)
        _draft(article_body(title='New one', category='Ingredients'), 'published', 'https://shop.com/blogs/news/new-one')
        _draft(article_body(title='Unfinished'), 'draft')
        _draft(article_body(title='Rejected'), 'rejected')
        st = h.items(D)
        self.assertEqual([s['title'] for s in st], ['New one', 'Old one'])
        self.assertEqual(st[1]['url'], '/blogs/news/old-one')          # relative: works on the store's own domain
        html = h.render(D, st, STYLE, 'Shop')
        self.assertIn('pk-feat', html)
        self.assertIn('for="pk-c1"', html)                             # two categories -> a filter
        self.assertIn('"@type": "ItemList"', html)
        self.assertIn('https://shop.com/blogs/news/new-one', html)
        self.assertNotIn('Unfinished', html)
        self.assertNotIn('<script>', html.replace('<script type="application/ld+json">', ''))   # no JS on the page

    def test_preview_uses_drafts_until_something_is_live(self):
        import stories_hub as h
        _draft(article_body(title='Designed draft'), 'approved')
        _draft(dict(title='Old plain guide', html='<p>x</p>'), 'draft')
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('content_agent.enabled', return_value=True), \
                mock.patch('accounts.can_see', return_value=True):
            code, page = h.preview(dict(d=D))
        self.assertEqual(code, 200)
        self.assertIn('Designed draft', page)
        self.assertIn('Not live yet', page)
        self.assertNotIn('Old plain guide', page)
        self.assertEqual(h.items(D), [])                               # the store page itself never shows drafts
        with mock.patch('content_agent.enabled', return_value=True), mock.patch('accounts.can_see', return_value=False):
            self.assertEqual(h.preview(dict(d=D))[0], 404)

    def test_put_up_then_update_then_take_down(self):
        import stories_hub as h
        _connect()
        _draft(article_body(title='Live one'), 'published', 'https://shop.com/blogs/news/live-one')
        calls = []

        def gql(domain, q, v=None):
            calls.append((q, v))
            if 'pageCreate' in q:
                return {'pageCreate': {'page': {'id': 'gid://shopify/Page/5', 'handle': 'stories'}, 'userErrors': []}}
            if 'pageUpdate' in q:
                return {'pageUpdate': {'page': {'id': 'gid://shopify/Page/5', 'handle': 'stories'}, 'userErrors': []}}
            if 'pageDelete' in q:
                return {'pageDelete': {'deletedPageId': 'gid://shopify/Page/5', 'userErrors': []}}
            return {}
        with mock.patch('shopify_connect.gql', side_effect=gql), mock.patch('brand_style.get', return_value=STYLE):
            self.assertEqual(h.publish(D), 'https://shop.com/pages/stories')
            self.assertIn('Live one', calls[0][1]['p']['body'])
            h.sync(D)
            self.assertIn('pageUpdate', calls[-1][0])
            self.assertEqual(sum('pageCreate' in q for q, _ in calls), 1)
            h.take_down(D)
            self.assertIn('pageDelete', calls[-1][0])
        self.assertEqual(h.live_url(D), '')
        calls.clear()
        h.sync(D)                                                       # nothing up -> nothing touched
        self.assertEqual(calls, [])

    def test_page_deleted_in_shopify_is_made_again(self):
        import shopify_connect as s
        import stories_hub as h
        _connect()
        h._put(D, dict(id='gid://shopify/Page/5', handle='stories', shop='shop.myshopify.com'))

        def gql(domain, q, v=None):
            if 'pageUpdate' in q:
                raise s.ShopifyError('Shopify refused the request: invalid id')
            return {'pageCreate': {'page': {'id': 'gid://shopify/Page/9', 'handle': 'stories'}, 'userErrors': []}}
        with mock.patch('shopify_connect.gql', side_effect=gql), mock.patch('brand_style.get', return_value=STYLE):
            h.publish(D)
        self.assertEqual(h.settings(D)['id'], 'gid://shopify/Page/9')

    def test_publishing_an_article_refreshes_the_page(self):
        import shopify_connect as s
        import stories_hub as h
        _connect()
        h._put(D, dict(id='gid://shopify/Page/5', handle='stories', shop='shop.myshopify.com'))
        did = _draft(article_body(faqs=[dict(question='Q?', answer='A.')]), 'approved')
        with mock.patch('shopify_connect.gql', return_value={
                'blogs': {'nodes': [{'id': 'b', 'handle': 'news'}]},
                'articleCreate': {'article': {'id': 'gid://shopify/Article/1', 'handle': 'a'}, 'userErrors': []}}), \
                mock.patch('brand_style.get', return_value=STYLE), mock.patch('threading.Thread') as th:
            s.publish(D, did)
        th.assert_called_once()
        self.assertIs(th.call_args.kwargs['target'], h.sync)

    def test_panel_states(self):
        import stories_hub as h
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('shopify_connect.configured', return_value=False):
            self.assertIn('Connect Shopify', h.panel(D))
        _connect()
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('shopify_connect.configured', return_value=True), \
                mock.patch('shopify_connect.expected_shop', return_value='shop.myshopify.com'):
            self.assertIn('disabled', h.panel(D))                       # nothing live yet
            _draft(article_body(), 'published', 'https://shop.com/blogs/news/a')
            self.assertIn('Put it on your store', h.panel(D))
            self.assertNotIn(' disabled>', h.panel(D))
            h._put(D, dict(id='gid://shopify/Page/5', handle='stories', shop='shop.myshopify.com'))
            self.assertIn('Take it down', h.panel(D))


class InstagramTest(Base):
    ITEMS = [dict(type='Image', id='1', shortCode='AAA', url='https://www.instagram.com/p/AAA/', displayUrl='https://ig/1.jpg',
                  caption='Sunny day'),
             dict(type='Video', id='2', displayUrl='https://ig/2.jpg'),
             dict(type='Sidecar', id='3', shortCode='CCC', displayUrl='https://ig/3a.jpg',
                  images=['https://ig/3a.jpg', 'https://ig/3b.jpg'])]

    def test_handles(self):
        import social_photos as sp
        self.assertEqual(sp.clean_handle('@Clubhouse.Skin'), 'clubhouse.skin')
        self.assertEqual(sp.clean_handle('https://www.instagram.com/clubhouse.skin/'), 'clubhouse.skin')
        self.assertEqual(sp.clean_handle('instagram.com/p/'), '')
        self.assertEqual(sp.clean_handle('not a handle!'), '')
        with mock.patch('brand_style._fetch', return_value='<a href="https://instagram.com/p/x">x</a>'
                        '<a href="https://www.instagram.com/brand.co/">IG</a><a href="https://instagram.com/brand.co">IG</a>'):
            self.assertEqual(sp.find_handle(D), 'brand.co')

    def test_photo_posts_saved_once_and_offered_in_the_picker(self):
        import article_learning as al
        import social_photos as sp
        found = sp.picks(self.ITEMS)
        self.assertEqual([u for u, *_ in found], ['https://ig/1.jpg', 'https://ig/3a.jpg', 'https://ig/3b.jpg'])   # video skipped
        with mock.patch('social_photos._download', return_value=('image/jpeg', JPG)):
            self.assertEqual(sp.save(D, found), 3)
            self.assertEqual(sp.save(D, found), 0)                     # already kept
        pics = sp.photos(D)
        self.assertEqual(len(pics), 3)
        al.save_upload(D, 'data:image/jpeg;base64,' + base64.b64encode(JPG).decode())
        self.assertEqual(len(al.uploaded_photos(D)), 1)                # uploads and Instagram stay apart
        offered = al.store_photos(D, article_body())
        self.assertTrue(set(pics) <= set(offered))
        did = _draft(article_body())
        al.set_photo(D, did, 'cover', pics[0])                          # an Instagram photo can be chosen

    def test_start_needs_a_handle_and_respects_the_cooldown(self):
        import social_photos as sp
        with mock.patch('social_photos.find_handle', return_value=''):
            with self.assertRaises(ValueError):
                sp.start(D)
        sp.set_handle(D, '@brand.co')
        with mock.patch('social_photos._posts', return_value=(self.ITEMS, 0.0045)), \
                mock.patch('social_photos._download', return_value=('image/jpeg', JPG)), \
                mock.patch('threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            sp.start(D)
        st = sp.state(D)
        self.assertEqual((st['status'], st['count'], st['cost']), ('done', 3, 0.0045))
        with self.assertRaises(ValueError):
            sp.start(D)                                                  # once a week at most: it costs money
        with self.assertRaises(ValueError):
            sp.set_handle(D, 'not a handle!')

    def test_hub_strip_only_when_switched_on(self):
        import social_photos as sp
        import stories_hub as h
        sp.set_handle(D, 'brand.co')
        with mock.patch('social_photos._download', return_value=('image/jpeg', JPG)):
            sp.save(D, sp.picks(self.ITEMS))
        _draft(article_body(), 'published', 'https://shop.com/blogs/news/a')
        with mock.patch('brand_style.get', return_value=STYLE):
            self.assertNotIn('From our Instagram', h.page_html(D, for_store=False))
            h.set_instagram(D, True)
            html = h.page_html(D, for_store=False)
        self.assertIn('From our Instagram', html)
        self.assertIn('https://www.instagram.com/p/AAA/', html)

    def test_settings_box(self):
        import content_setup
        with mock.patch('social_photos.find_handle', return_value='brand.co'):
            box = content_setup.instagram_box(D, {})
        self.assertIn('@brand.co', box)
        self.assertIn('Get photos from Instagram', box)
        self.assertIn('5 cents', box)


if __name__ == '__main__':
    unittest.main()
