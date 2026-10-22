"""Shopify publishing: verified connect, approved drafts only, undo restores, calendar publishes when due."""
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import config
import content_agent
import content_setup
import db
import shopify_connect as sc


class FakeShopify:
    """Answers the GraphQL calls publish/undo make, and records them."""
    def __init__(self):
        self.product = dict(id="gid://shopify/Product/1", title="Hat", handle="hat", onlineStoreUrl=None,
                            descriptionHtml="<p>Old copy.</p>")
        self.calls = []

    def __call__(self, domain, query, variables=None):
        self.calls.append((query.split('{')[0].split('(')[0].strip(), variables))
        if 'products(first' in query:
            return {'products': {'nodes': [dict(self.product)]}}
        if 'productUpdate' in query:
            p = variables['p']
            self.product.update(title=p.get('title', self.product['title']),
                                descriptionHtml=p.get('descriptionHtml', self.product['descriptionHtml']))
            return {'productUpdate': {'product': dict(self.product), 'userErrors': []}}
        if 'pageCreate' in query:
            return {'pageCreate': {'page': {'id': 'gid://shopify/Page/9', 'handle': 'cap-or-hat'}, 'userErrors': []}}
        if 'pageDelete' in query:
            assert 'deletedPageId' in query, "Shopify's field is deletedPageId (live test, 15 Oct)"
            return {'pageDelete': {'deletedPageId': variables['id'], 'userErrors': []}}
        if 'blogs(first' in query:
            return {'blogs': {'nodes': [{'id': 'gid://shopify/Blog/2', 'handle': 'journal'}]}}
        if 'articleCreate' in query:
            return {'articleCreate': {'article': {'id': 'gid://shopify/Article/5', 'handle': 'how-to'}, 'userErrors': []}}
        raise AssertionError(query)


class ShopifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.SHOW_CONTENT_AGENT = True
        db.init()
        content_agent.init()
        sc.init()
        content_setup.put("x.com", dict(part1_done_at=1))
        self.env = mock.patch("config.env", side_effect=lambda k: {"SHOPIFY_CLIENT_ID": "cid", "SHOPIFY_CLIENT_SECRET": "sec",
                                                                    "PRODUKTO_BASE_URL": "https://app.test"}.get(k, ""))
        self.env.start()
        self.shop = FakeShopify()
        self.gql = mock.patch("shopify_connect.gql", self.shop)
        self.gql.start()

    def tearDown(self):
        self.gql.stop()
        self.env.stop()
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def _connect(self):
        db.write("INSERT INTO shopify_connections VALUES ('x.com','x-test.myshopify.com','tok','',?,NULL)", (time.time(),))

    def _draft(self, kind, body, status="approved", planned=None):
        with db.conn() as c:
            bid = c.execute("INSERT INTO content_briefs (store_domain, opportunity_kind, opportunity_key, draft_type, created_at) "
                            "VALUES ('x.com','missing','q',?,?)", (kind, time.time())).lastrowid
            did = c.execute("INSERT INTO content_drafts (brief_id, store_domain, draft_type, title, status, planned_at, created_at) "
                            "VALUES (?, 'x.com',?,?,?,?,?)", (bid, kind, body.get("title", "t"), status, planned, time.time())).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, sources, created_at) VALUES (?,?,'[]',?)",
                      (did, json.dumps(body), time.time()))
        return did

    def test_shop_address_and_signed_callback(self):
        self.assertEqual(sc.clean_shop("https://Produkto-Test.myshopify.com/admin"), "produkto-test.myshopify.com")
        self.assertEqual(sc.clean_shop("produkto-test"), "produkto-test.myshopify.com")
        self.assertEqual(sc.clean_shop("evil.com"), "")
        url = sc.install_url("x.com", "x-test.myshopify.com")
        self.assertIn("redirect_uri=https%3A%2F%2Fapp.test%2Fshopify%2Fcallback", url)
        state = url.split("state=")[1]
        q = dict(code="c", shop="x-test.myshopify.com", state=state, timestamp="1")
        q["hmac"] = "bad"
        with self.assertRaises(sc.ShopifyError):
            sc.finish(dict(q))                                  # wrong signature
        url = sc.install_url("x.com", "x-test.myshopify.com")
        q["state"] = url.split("state=")[1]
        msg = "&".join("%s=%s" % (k, v) for k, v in sorted(q.items()) if k != "hmac")
        q["hmac"] = hmac.new(b"sec", msg.encode(), hashlib.sha256).hexdigest()
        with mock.patch("shopify_connect._post_json", return_value=dict(access_token="tok", scope="write_products")):
            self.assertEqual(sc.finish(dict(q)), "x.com")
        self.assertEqual(sc.connection("x.com")["shop"], "x-test.myshopify.com")
        self.assertNotIn("token", dict(sc.connection("x.com")))   # the token is never read back out for display

    def test_fix_then_faq_then_undo(self):
        self._connect()
        fix = self._draft("product_fix", dict(title="Hat | Cotton Cap", description_html='<p>New copy.</p>',
                                              spec_table=[dict(label="Material", value="Cotton")], product=dict(handle="hat")))
        url = sc.publish("x.com", fix)
        self.assertEqual(self.shop.product["title"], "Hat | Cotton Cap")
        self.assertIn("<p>New copy.</p>", self.shop.product["descriptionHtml"])
        self.assertNotIn("cr-spec", self.shop.product["descriptionHtml"])
        row = db.one("SELECT status, live_url FROM content_drafts WHERE id=?", (fix,))
        self.assertEqual((row["status"], row["live_url"]), ("published", url))
        self.assertEqual(db.one("SELECT status FROM opportunity_status WHERE key='q'")["status"], "done")
        faq = self._draft("faq", dict(faqs=[dict(question="Cotton?", answer="Yes.")], product=dict(handle="hat")))
        sc.publish("x.com", faq)
        body = self.shop.product["descriptionHtml"]
        self.assertTrue(body.startswith("<p>New copy.</p>"))
        self.assertEqual(body.count(sc.FAQ_START), 1)
        self.assertIn('"FAQPage"', body)
        sc.undo("x.com", faq)                                   # FAQ off again
        self.assertNotIn(sc.FAQ_START, self.shop.product["descriptionHtml"])
        sc.undo("x.com", fix)                                   # original back
        self.assertEqual((self.shop.product["title"], self.shop.product["descriptionHtml"]), ("Hat", "<p>Old copy.</p>"))
        self.assertEqual(db.one("SELECT status FROM content_drafts WHERE id=?", (fix,))["status"], "approved")

    def test_faq_replaces_its_own_block(self):
        once = sc.with_faq("<p>A</p>", "<h3>Q1</h3>")
        twice = sc.with_faq(once, "<h3>Q2</h3>")
        self.assertEqual(twice.count(sc.FAQ_START), 1)
        self.assertIn("Q2", twice)
        self.assertNotIn("Q1", twice)

    def test_pages_and_posts_and_undo_deletes(self):
        self._connect()
        comp = self._draft("comparison", dict(title="Cap or hat?", intro="i", columns=[], rows=[], summary=[], names={}))
        self.assertTrue(sc.publish("x.com", comp).endswith("/pages/cap-or-hat"))
        guide = self._draft("guide", dict(title="How to", intro="i", sections=[], picks=[], products=[]))
        self.assertTrue(sc.publish("x.com", guide).endswith("/blogs/journal/how-to"))
        sc.undo("x.com", comp)
        self.assertIn(("mutation", {"id": "gid://shopify/Page/9"}), self.shop.calls)

    def test_only_approved_drafts_without_gaps_publish(self):
        self._connect()
        new = self._draft("faq", dict(faqs=[dict(question="Q", answer="Yes.")], product=dict(handle="hat")), status="draft")
        with self.assertRaises(sc.ShopifyError):
            sc.publish("x.com", new)
        gap = self._draft("faq", dict(faqs=[dict(question="Q", answer="[ask merchant: Size?]")], product=dict(handle="hat")))
        with self.assertRaises(sc.ShopifyError):
            sc.publish("x.com", gap)

    def test_calendar_publishes_when_due_for_connected_stores_only(self):
        due = self._draft("faq", dict(faqs=[dict(question="Q", answer="Yes.")], product=dict(handle="hat")), planned=time.time() - 60)
        later = self._draft("faq", dict(faqs=[dict(question="Q", answer="Yes.")], product=dict(handle="hat")), planned=time.time() + 9999)
        self.assertEqual(sc.publish_due(), ([], []))            # not connected: nothing happens
        self._connect()
        self.assertEqual(sc.publish_due()[0], [due])
        self.assertEqual(db.one("SELECT status FROM content_drafts WHERE id=?", (later,))["status"], "approved")

    def test_buttons(self):
        did = self._draft("faq", dict(faqs=[], product=dict(handle="hat")))
        row = db.one("SELECT * FROM content_drafts WHERE id=?", (did,))
        self.assertIn("Connect Shopify to publish", content_agent.publish_buttons("x.com", row, "/content?d=x.com"))
        self._connect()
        self.assertIn("Publish now", content_agent.publish_buttons("x.com", row, "/content?d=x.com"))


if __name__ == "__main__":
    unittest.main()
