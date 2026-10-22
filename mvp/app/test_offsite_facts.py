"""Off-site facts: only pages naming brand + product, only answers the page states, never filled in by itself."""
import os
import tempfile
import unittest
from unittest import mock

import config
import content_agent
import content_setup
import db
import offsite_facts
import page_gap

HAT = dict(handle="hat", title="Harbour Cap", url="u", image="", facts=[], description=["A cap."])
PAGES = {
    "https://shop.com/harbour-cap": "Acme Harbour Cap. One size, adjustable strap. 100% organic cotton.",
    "https://other.com/harbour-cap": "Zeta Harbour Cap in wool.",                 # same product name, other brand
    "https://blog.com/caps": "Acme makes caps. Fit matters.",                     # brand, but not this product
}


class OffsiteFactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.SHOW_CONTENT_AGENT = True
        db.init()
        content_agent.init()
        page_gap.init()
        for u, t in PAGES.items():
            page_gap.store(u, True, dict(title="", text=t))

    def tearDown(self):
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def _for(self):
        with mock.patch("offsite_facts.candidate_urls", return_value=list(PAGES)), mock.patch("page_gap.fetch_all"), \
                mock.patch("offsite_facts._apify_search", side_effect=AssertionError("no paid search in tests")):
            return offsite_facts.for_products("acme.com", [HAT], brand="Acme")

    def test_only_pages_naming_brand_and_product(self):
        self.assertEqual([w["site"] for w in self._for()["hat"]], ["shop.com"])

    def test_supported(self):
        text = PAGES["https://shop.com/harbour-cap"]
        self.assertTrue(offsite_facts.supported("One size", text))
        self.assertTrue(offsite_facts.supported("Organic cotton, 100%", text))
        self.assertFalse(offsite_facts.supported("80% cotton", text))
        self.assertFalse(offsite_facts.supported("Machine washable", text))

    def test_missing_facts_offer_the_web_answer_without_filling_it_in(self):
        reply = dict(products=[dict(handle="hat", missing=[
            dict(label="Size", question="What sizes?", suggestion="", web_suggestion="One size", web_source="W1"),
            dict(label="Care", question="How to wash?", suggestion="", web_suggestion="Hand wash", web_source="W1"),
        ])])
        with mock.patch("catalog_facts.get", return_value=[HAT]), mock.patch("llm.json_call", return_value=reply) as call, \
                mock.patch("offsite_facts.candidate_urls", return_value=list(PAGES)), mock.patch("page_gap.fetch_all"), \
                mock.patch("db.brand", return_value=dict(brand_name="Acme")):
            out = content_setup.find_missing("acme.com")
            self.assertIn("adjustable strap", call.call_args[0][1])        # the page reached the model
            size, care = out["hat"]
            self.assertEqual(size["web"]["site"], "shop.com")
            self.assertNotIn("web", care)                                   # the page never says "hand wash"
            content_setup.put("acme.com", dict(missing=out))
            html = content_setup._facts_page("acme.com", content_setup.get("acme.com"))
        self.assertIn("shop.com says <strong>One size</strong>", html)
        self.assertIn('value=""', html)                                     # not filled in until "Use this"


    def test_search_runs_once_per_product_within_the_monthly_cap(self):
        prods = [dict(HAT, handle="h%d" % i, title="Cap %d" % i) for i in range(4)]
        def fake(queries, country):
            return [(q, ["https://shop.com/%d" % i]) for i, q in enumerate(queries)], 0.0075
        with mock.patch("content_plan.allowance", return_value=3), \
                mock.patch("offsite_facts._apify_search", side_effect=fake) as run:
            first = offsite_facts.search("acme.com", prods, "Acme")
            self.assertEqual(len(run.call_args[0][0]), 3)              # cap: 3 searches this month
            self.assertEqual(run.call_args[0][0][0], '"Acme" "Cap 0"')
            self.assertEqual(sorted(first), ["h0", "h1", "h2"])
            again = offsite_facts.search("acme.com", prods, "Acme")
            self.assertEqual(run.call_count, 1)                         # cached, and the cap is used up
        self.assertEqual(sorted(again), ["h0", "h1", "h2"])
        self.assertAlmostEqual(db.one("SELECT SUM(cost_usd) c FROM offsite_searches")["c"], 0.0075)

    def test_no_search_when_free_pages_found_the_product_or_switched_off(self):
        with mock.patch("offsite_facts.candidate_urls", return_value=list(PAGES)), mock.patch("page_gap.fetch_all"), \
                mock.patch("offsite_facts._apify_search") as run:
            offsite_facts.for_products("acme.com", [HAT], brand="Acme")
            run.assert_not_called()
            with mock.patch("config.env", return_value="0"):
                self.assertEqual(offsite_facts.search("acme.com", [dict(HAT, handle="new")], "Acme"), {})
            run.assert_not_called()

    def test_searched_pages_are_read_and_filtered_like_free_ones(self):
        page_gap.store("https://press.com/acme-sun-hat", True, dict(title="", text="The Acme Sun Hat. UPF 50 fabric."))
        sun = dict(HAT, handle="sun", title="Sun Hat")
        with mock.patch("offsite_facts.candidate_urls", return_value=[]), mock.patch("page_gap.fetch_all"), \
                mock.patch("offsite_facts.searches_left", return_value=10), \
                mock.patch("offsite_facts._apify_search", return_value=([('"Acme" "Sun Hat"', [
                    "https://acme.com/products/sun-hat", "https://www.instagram.com/p/1", "https://press.com/acme-sun-hat"])], 0.0025)):
            out = offsite_facts.for_products("acme.com", [sun], brand="Acme")
        self.assertEqual([w["site"] for w in out["sun"]], ["press.com"])   # own store and Instagram skipped


if __name__ == "__main__":
    unittest.main()
