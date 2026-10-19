"""Briefs: which questions, which of the merchant's products, and saved for the agent."""
import json
import os
import tempfile
import unittest

import config
import db
import briefs
import catalog_facts

PS = {"prompts": ["q1", "q2", "q3"], "clusters": ["caps", "caps", "oils"],
      "relevance": [[1], [1, 2], [2]],
      "catalog_snapshot": [{"id": 1, "handle": "hat", "title": "Hat", "url": "https://x.com/products/hat"},
                           {"id": 2, "handle": "oil", "title": "Oil", "url": "https://x.com/products/oil"}]}


class BriefsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_only_writable_opportunities(self):
        self.assertIsNone(briefs.build("x.com", "stale", "scan"))
        self.assertIsNone(briefs.build("x.com", "retailer", "boots.com"))

    def test_questions_for_a_topic_and_a_question(self):
        self.assertEqual(briefs._questions(PS, {"type": "topic", "key": "caps"}), ["q1", "q2"])
        self.assertEqual(briefs._questions(PS, {"type": "missing", "key": "q3"}), ["q3"])

    def test_products_carry_their_facts(self):
        catalog_facts.init()
        rec = {"handle": "hat", "facts": [{"label": "Material", "value": "cotton", "source": "catalog"}],
               "description": ["A cap."]}
        with db.conn() as c:
            c.execute("INSERT INTO catalog_facts VALUES (?,?,?,?)", ("x.com", "hat", 0, json.dumps(rec)))
        prods = briefs._products(PS, ["q1", "q2"], "x.com")
        self.assertEqual([p["title"] for p in prods], ["Hat", "Oil"])
        self.assertTrue(prods[0]["facts_ready"])
        self.assertEqual(prods[0]["facts"][0]["value"], "cotton")
        self.assertFalse(prods[1]["facts_ready"])   # not read yet: the agent must not guess its facts

    def test_cited_pages_skip_own_store_and_competitor_pages(self):
        from collections import Counter
        from unittest import mock
        import page_gap
        page_gap.init()
        cites = {"q1": Counter({"https://review.com/best-caps": 3, "https://www.x.com/products/hat": 5,
                                "https://rival.com/products/cap": 2}),
                 "q2": Counter({"https://review.com/best-caps": 1, "https://blog.org/caps": 1})}
        page_gap.store("https://review.com/best-caps", True, {"title": "Best caps", "text": "Fit and fabric matter."})
        with mock.patch("page_gap.fetch_all") as fetch:
            out = briefs._cited(["q1", "q2"], cites, "x.com", {"https://rival.com/products/cap"})
        self.assertEqual([c["url"] for c in out], ["https://review.com/best-caps", "https://blog.org/caps"])
        self.assertEqual((out[0]["cited"], out[0]["page_read"], out[1]["page_read"]), (4, True, False))
        fetch.assert_called()   # unread pages are fetched (free), never guessed; pages cached without a shape are read again

    def test_research_reaches_drafts_as_research_only(self):
        import drafts
        b = dict(store="x.com", questions=[], competitors=[], cited_pages=[
            dict(url="u", site="review.com", page_read=True, page_title="Best caps", page_excerpt="Fit matters.")])
        text = drafts._input(b, dict(title="Hat", url="u", facts=[], description=[]))
        self.assertIn("Fit matters.", text)
        self.assertIn("never take a number, fact or claim", text)

    def test_save(self):
        b = dict(store="x.com", opportunity=dict(type="missing", key="q1"), questions=[], competitors=[],
                 products=[dict(handle="hat", url="https://x.com/products/hat", title="Hat")])
        bid = briefs.save(b)
        row = db.one("SELECT * FROM content_briefs WHERE id=?", (bid,))
        self.assertEqual((row["target_kind"], row["target_id"]), ("product", "hat"))
        self.assertEqual(json.loads(row["data"])["store"], "x.com")


    def _brief(self, kind, qs, n_products):
        prods = [dict(handle="p%d" % i, title="P%d" % i) for i in range(n_products)]
        return dict(opportunity=dict(type=kind), questions=[dict(question=q) for q in qs], products=prods)

    def test_draft_type_rules(self):
        first = lambda *a: briefs.choose_types(self._brief(*a))[0][0]
        self.assertEqual(first("details", ["Which oil brightens skin?"], 1), "product_fix")
        self.assertEqual(first("missing", ["Should I choose a face oil or a moisturiser?"], 2), "comparison")
        self.assertEqual(first("missing", ["What can I get under £40 that cleanses or hydrates?"], 2), "product_fix")
        self.assertEqual(first("missing", ["Best simple three-step skincare routine?"], 1), "guide")
        self.assertEqual(first("topic", ["q"], 0), "guide")
        self.assertIn("faq", [t for t, _ in briefs.choose_types(self._brief("missing", ["Is it waterproof?"], 1))])
        for t, why in briefs.choose_types(self._brief("missing", ["Is it waterproof?"], 1)):
            self.assertTrue(why)                    # every pick says why, for the detail panel

    def test_ai_picks_only_when_no_rule_matches(self):
        from unittest import mock
        with mock.patch("llm.json_call") as call:
            briefs.choose_types(self._brief("missing", ["Is it waterproof?"], 1))
            call.assert_not_called()
            call.return_value = dict(picks=[dict(type="faq", reason="r"), dict(type="guide", reason="Covers it.")])
            picks = briefs.choose_types(self._brief("missing", ["Hat ideas for a beach day"], 0))
        self.assertEqual([t for t, _ in picks], ["guide"])     # no product, so no FAQ
        self.assertIn("chosen by AI", picks[0][1])
        with mock.patch("llm.json_call", side_effect=Exception("down")):
            self.assertEqual(briefs.choose_types(self._brief("missing", ["Hat ideas"], 0))[0][0], "guide")


if __name__ == "__main__":
    unittest.main()
