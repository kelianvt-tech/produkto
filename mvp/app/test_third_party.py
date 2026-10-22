"""Third-party context: the cost guard, what a pull stores, and what each agent step gets. No Apify calls."""
import json
import os
import tempfile
import time
import unittest

import config
import db
import drafts
import feed_check
import third_party

DOMAIN = "clubhouse.test"
QUESTIONS = ["best gentle cleanser under £40", "lightweight moisturiser for oily skin"]


def shopping(domain, questions, country):
    rows = [
        dict(productName="Nivea Cleansing Cream", merchantName="Amazon.co.uk", positionOnSearchPage=1,
             searchKeyword=QUESTIONS[0], price="£2", reviewsScore="4.4", reviewsCount="616"),
        dict(productName="Clubhouse Skin Frontier Cleanser 255ml", merchantName="eBay", positionOnSearchPage=17,
             searchKeyword=QUESTIONS[0], price="£30"),
        dict(productName="CeraVe PM", merchantName="Boots", positionOnSearchPage=1, searchKeyword=QUESTIONS[1]),
    ]
    return rows, 0.0132


def web(queries, country):
    res = [
        dict(url="https://www.earlofeast.com/products/clubhouse-skin-frontier-face-cleanser-225ml",
             title="Frontier Face Cleanser - 225ml", description="Frontier Face Cleanser by Clubhouse Skin."),
        dict(url="https://goodhoodstore.com/products/clubhouse-skin-helsinki-moisturiser-75ml",
             title="Clubhouse Skin Helsinki Moisturiser - 75ml", description="Lightweight moisturiser."),
        dict(url="https://www.amazon.com/stores/CLEANSKINCLUB/page/x", title="CLEAN SKIN CLUB: Skincare",
             description="Clean Skin Club towels."),
        dict(url="https://clubhouseskinandlaser.com/", title="ClubHouse Skin and Laser",
             description="Med spa."),
        dict(url="https://www.youtube.com/watch?v=1", title="Clubhouse Skin routine", description=""),
        dict(url="https://clubhouse.test/products/frontier-cleanser", title="Frontier Cleanser", description=""),
    ]
    return [dict(searchQuery=dict(term=queries[0]), organicResults=[dict(r, position=i + 1) for i, r in enumerate(res)])], 0.01


def trustpilot(domain):
    return [dict(reviewId="r1", rating=2, title="Slow delivery", text="Took three weeks.",
                 publishedDate="2026-10-15T00:00:00Z", companyTrustScore=3.2, companyTotalReviews=2),
            dict(reviewId="r2", rating=5, title="Great", text="Lovely.", publishedDate="2026-09-01T00:00:00Z",
                 companyTrustScore=3.2, companyTotalReviews=2)], 0.006


ACTORS = dict(shopping=shopping, web=web, trustpilot=trustpilot)
ROOMY = (4.0, 75.0)


class ThirdPartyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.THIRD_PARTY
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.THIRD_PARTY = True
        db.init()
        db.write("INSERT INTO stores (domain, brand, brand_name, country) VALUES (?,?,?,?)",
                 (DOMAIN, "Clubhouse Skin", "Clubhouse Skin", "GB"))
        for i, (h, t, body) in enumerate((("frontier-cleanser", "Frontier Cleanser", "<p>A 225ml daily cleanser.</p>"),
                                          ("helsinki-moisturiser", "Helsinki Moisturiser", "<p>75ml.</p>")), 1):
            db.write("INSERT INTO products (id, store_domain, shopify_id, handle, title, url, raw_json) VALUES (?,?,?,?,?,?,?)",
                     (i, DOMAIN, i, h, t, "https://%s/products/%s" % (DOMAIN, h), json.dumps(dict(body_html=body))))
        db.write("INSERT INTO prompt_sets (store_domain, prompts, relevance, product_ids, catalog_snapshot, created_at) "
                 "VALUES (?,?,?,?,?,?)", (DOMAIN, json.dumps(QUESTIONS), json.dumps([[1], [2, 1]]), json.dumps([1, 2]),
                                          "[]", time.time()))
        third_party._running.clear()

    def tearDown(self):
        config.DB_PATH, config.THIRD_PARTY = self.old
        self.tmp.cleanup()

    def test_estimate(self):
        est = third_party.estimate(DOMAIN)
        self.assertEqual(est["questions"], 2)
        self.assertAlmostEqual(est["shopping"], 2 * 20 * 0.0044 + 0.001, places=4)
        self.assertAlmostEqual(est["web"], 2 * 2 * 0.0025 + 0.001, places=4)     # two queries, two pages each
        self.assertAlmostEqual(est["total"], est["shopping"] + est["web"] + est["trustpilot"], places=4)
        self.assertEqual(third_party.search_queries(DOMAIN)[0], '"Clubhouse Skin" -site:clubhouse.test')
        self.assertIn("Frontier Cleanser review", third_party.search_queries(DOMAIN)[1])   # fits most questions

    def test_guard(self):
        self.assertTrue(third_party.guard(DOMAIN, usage=ROOMY)[0])
        ok, why, _ = third_party.guard(DOMAIN, usage=(70.0, 75.0))                       # within $10 of the limit
        self.assertFalse(ok)
        self.assertIn("daily scans", why[0])
        config.THIRD_PARTY = False
        self.assertFalse(third_party.guard(DOMAIN, usage=ROOMY)[0])
        config.THIRD_PARTY = True
        os.environ["PRODUKTO_THIRD_PARTY_CAP"] = "0.05"
        try:
            ok, why, _ = third_party.guard(DOMAIN, usage=ROOMY)
            self.assertFalse(ok)
            self.assertIn("cap", why[0])
        finally:
            del os.environ["PRODUKTO_THIRD_PARTY_CAP"]
        with self.assertRaises(ValueError):                                              # refused before any call
            third_party.run(DOMAIN, usage=(70.0, 75.0), actors=dict(shopping=lambda *a: self.fail("called")))
        self.assertIsNone(db.one("SELECT id FROM third_party_runs"))

    def test_unreadable_balance_refuses(self):
        def boom():
            raise RuntimeError("offline")
        orig = third_party.account_usage
        third_party.account_usage = boom
        try:
            ok, why, _ = third_party.guard(DOMAIN)
        finally:
            third_party.account_usage = orig
        self.assertFalse(ok)
        self.assertIn("Apify balance", why[0])

    def test_run_and_facts(self):
        out = third_party.run(DOMAIN, usage=ROOMY, actors=ACTORS)
        self.assertEqual(out["status"], "done")
        self.assertAlmostEqual(out["cost_usd"], 0.0292, places=4)
        f = third_party.facts(DOMAIN)
        sh = f["shopping"]
        self.assertEqual((sh["searched"], sh["with_brand"], sh["with_own_store"]), (2, 1, 0))
        ebay = sh["questions"][0]["brand"][0]
        self.assertEqual((ebay["position"], ebay["merchant"], ebay["own_store"], ebay["product_id"]), (17, "eBay", False, 1))
        off = f["offsite"]
        sites = {p["site"] for p in off["pages"]}
        self.assertEqual(sites, {"earlofeast.com", "goodhoodstore.com", "youtube.com"})   # own site + clashes left out
        self.assertEqual(off["collisions"], 2)
        self.assertEqual(off["by_kind"], {"retailer": 2, "video": 1})
        self.assertEqual(f["trustpilot"]["count"], 2)
        self.assertEqual([c["title"] for c in f["trustpilot"]["complaints"]], ["Slow delivery"])
        conflict = next(c for c in f["conflicts"] if c["product"] == "Frontier Cleanser")
        self.assertEqual(set(conflict["values"]), {"225", "255"})
        self.assertIn("your store", conflict["values"]["225"])
        self.assertFalse(any(c["product"] == "Helsinki Moisturiser" for c in f["conflicts"]))   # 75ml agrees

    def test_one_failed_actor_keeps_the_rest(self):
        def broken(*a):
            raise RuntimeError("Apify down")
        out = third_party.run(DOMAIN, usage=ROOMY, actors=dict(ACTORS, web=broken))
        self.assertEqual(out["status"], "partial")
        f = third_party.facts(DOMAIN)
        self.assertIsNone(f["offsite"])
        self.assertIsNotNone(f["shopping"])

    def test_context_slices(self):
        self.assertEqual(third_party.context(DOMAIN, "feed"), "")                           # never pulled
        third_party.run(DOMAIN, usage=ROOMY, actors=ACTORS)
        diag = third_party.context(DOMAIN, "diagnose", questions=[QUESTIONS[1]])
        self.assertIn("research only", diag)
        self.assertIn("not in the top 1", diag)
        self.assertNotIn(QUESTIONS[0], diag)                                                 # narrowed to the task
        self.assertIn("in none of the Google Shopping", third_party.context(DOMAIN, "feed"))
        cit = third_party.context(DOMAIN, "citations")
        self.assertIn("earlofeast.com", cit)
        self.assertIn("No review articles or forum threads", cit)
        self.assertIn("Slow delivery", third_party.context(DOMAIN, "reviews"))
        brief = dict(third_party=third_party.for_brief(DOMAIN, QUESTIONS, [dict(handle="frontier-cleanser")]))
        self.assertEqual(set(brief["third_party"]), {"diagnose", "feed", "citations", "reviews"})
        self.assertIn("225", brief["third_party"]["diagnose"])
        text = drafts._third_party(brief)
        self.assertIn("DIAGNOSE", text)
        self.assertNotIn("FEED", text)                       # the feed slice goes to Product Data cards, not drafts
        config.THIRD_PARTY = False
        self.assertEqual(third_party.for_brief(DOMAIN, QUESTIONS, []), {})

    def test_cards(self):
        third_party.run(DOMAIN, usage=ROOMY, actors=ACTORS)
        keys = [c["key"] for c in feed_check.cards(DOMAIN)]                                 # no feed check cached
        self.assertIn("google-shopping", keys)
        self.assertIn("numbers-1-ml", keys)
        self.assertIn("trustpilot-complaints", keys)
        self.assertEqual(third_party.offsite_urls(DOMAIN)[0],
                         "https://www.earlofeast.com/products/clubhouse-skin-frontier-face-cleanser-225ml")
        config.THIRD_PARTY = False
        self.assertEqual(feed_check.cards(DOMAIN), [])

    def test_kind_and_collision(self):
        self.assertEqual(third_party.kind("https://www.facebook.com/groups/1/posts/2", "Has anyone tried"), "forum")
        self.assertEqual(third_party.kind("https://www.amazon.com/live/video/abc"), "video")
        self.assertEqual(third_party.kind("https://nebula.org/blog/5strands-review/", "5Strands review"), "review")
        self.assertEqual(third_party.kind("https://www.walmart.com/ip/5Strands-x"), "retailer")
        self.assertFalse(third_party.collision("https://chewy.com/x", "5Strands Food Test", "", "5 Strands", "5strands.com"))
        self.assertTrue(third_party.collision("https://x.org/merger", "Review of Merger Guidelines", "", "5Strands", "5strands.com"))
        self.assertEqual(dict(third_party.counts("5Strands Test, 640 Items Tested; 800+ foods")), {"items": {"640", "800+"}})


if __name__ == "__main__":
    unittest.main()
