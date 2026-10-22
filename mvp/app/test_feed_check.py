"""Feed readiness: robots.txt, product data and policy pages become Product Data cards."""
import json
import os
import tempfile
import time
import unittest

import config
import db
import feed_check


def page(**kw):
    p = dict(url="u", title="Hat", product=True, price=True, availability=True, gtin=True, rating=True, barcode=True)
    p.update(kw)
    return p


class FeedCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        feed_check.init()

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def _store(self, **data):
        base = dict(blocked=[], robots_read=True, sample_path="/products/hat", policies=dict(refund=True, shipping=True),
                    pages=[page()])
        base.update(data)
        db.write("INSERT INTO feed_checks VALUES (?,?,?)", ("x.com", json.dumps(base), time.time()))

    def test_robots(self):
        shopify = "User-agent: *\nDisallow: /cart\nDisallow: /checkouts/\n"
        self.assertEqual(feed_check.blocked_crawlers(shopify, "/products/hat"), [])
        strict = shopify + "\nUser-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: PerplexityBot\nDisallow: /products/\n"
        self.assertEqual(feed_check.blocked_crawlers(strict, "/products/hat"), ["OAI-SearchBot", "PerplexityBot"])

    def test_a_clean_store_has_no_cards_and_an_unchecked_one_none_either(self):
        self.assertEqual(feed_check.cards("x.com"), [])
        self._store()
        self.assertEqual(feed_check.cards("x.com"), [])

    def test_cards_say_where_to_fix(self):
        self._store(blocked=["OAI-SearchBot"], policies=dict(refund=False, shipping=True),
                    pages=[page(gtin=False, barcode=True, rating=False), page(title="Oil", product=False),
                           page(title="Cap", availability=False, rating=False)])
        cards = {c["key"]: c for c in feed_check.cards("x.com")}
        self.assertEqual(cards["robots"]["impact"], "critical")
        self.assertIn("robots.txt.liquid", cards["robots"]["text"])
        self.assertIn("1 of 3", cards["markup"]["title"])
        self.assertIn("Cap", cards["offers"]["text"])
        self.assertIn("theme is leaving them out", cards["gtin"]["text"])   # catalog has the barcode
        self.assertIn("reviews", cards)                                      # no marked-up page has a rating
        self.assertNotIn("policy-refund", cards)                             # folded into the ChatGPT card
        self.assertIn("Return and refund policy", cards["chatgpt-policies"]["text"])
        self.assertNotIn("policy-shipping", cards)

    def test_unknown_stock_is_not_reported_as_missing(self):
        self._store(pages=[page(availability=None)])          # cached before the field existed
        self.assertEqual(feed_check.cards("x.com"), [])


    def test_reviews_and_customer_qa_cards(self):
        from unittest import mock
        self._store(pages=[page(title="Cap", rating=False, review_app=False, qa=False, id=1),
                           page(title="Oil", rating=False, review_app=True, qa=True, id=2)])
        ps = dict(prompts=["Which cap fits a big head?", "Best face oil?"], relevance=[[1], [2]])
        with mock.patch.object(db, "get_prompt_set", return_value=ps):
            cards = {c["key"]: c for c in feed_check.cards("x.com")}
        self.assertIn("1 of 2", cards["show-reviews"]["title"])
        self.assertIn("Cap", cards["show-reviews"]["text"])
        self.assertEqual(cards["show-reviews"]["impact"], "medium")
        self.assertIn("Which cap fits a big head?", cards["customer-qa"]["text"])
        self.assertNotIn("Best face oil?", cards["customer-qa"]["text"])   # the oil page has a Q&A
        self.assertIn("show reviews but don", cards["reviews"]["text"])    # Oil shows reviews, publishes no rating

    ALL = dict(refund=True, shipping=True, terms=True, privacy=True)

    def _country(self, country):
        db.write("INSERT OR REPLACE INTO stores (domain, brand, country) VALUES (?,?,?)", ("x.com", "X", country))

    def test_chatgpt_needs_shopifys_three_policies(self):
        self._store(policies=dict(self.ALL, terms=False, privacy=False))
        cards = {c["key"]: c for c in feed_check.cards("x.com")}
        card = cards["chatgpt-policies"]
        self.assertEqual(card["impact"], "critical")                         # no country: treated as US
        self.assertIn("Terms of service", card["text"])
        self.assertIn("/policies/privacy-policy", card["text"])
        self.assertIn("Settings &gt; Policies", card["text"])
        self.assertNotIn("covers", card)
        self.assertNotIn("chatgpt-catalog", cards)

    def test_with_the_policies_in_place_it_is_a_one_time_check(self):
        self._store(policies=self.ALL)
        cards = {c["key"]: c for c in feed_check.cards("x.com")}
        self.assertEqual(list(cards), ["chatgpt-catalog"])
        self.assertEqual(cards["chatgpt-catalog"]["impact"], "high")
        self.assertIn("Shopify Catalog access", cards["chatgpt-catalog"]["text"])
        self._country("GB")
        card = feed_check.cards("x.com")[0]
        self.assertEqual(card["impact"], "medium")
        self.assertIn("sell to customers in the US", card["text"])

    def test_google_shopping_is_critical_outside_the_us(self):
        shopping = lambda: [dict(type="feed", key="google-shopping", impact="high", weight=11, title="t", text="x.")]
        gb = feed_check.by_country(shopping(), us=False)[0]
        self.assertEqual(gb["impact"], "critical")
        self.assertIn("Outside the US", gb["text"])
        self.assertEqual(feed_check.by_country(shopping(), us=True)[0]["impact"], "high")
        self._country("GB")
        self.assertFalse(feed_check.is_us("x.com"))
        self._country("US")
        self.assertTrue(feed_check.is_us("x.com"))


if __name__ == "__main__":
    unittest.main()
