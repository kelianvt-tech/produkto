"""Drafts: only facts the store states, and nothing goes to the store."""
import json
import os
import tempfile
import unittest
from unittest import mock

import config
import db
import drafts
import factcheck

PRODUCT = dict(handle="hat", title="Hat", url="https://x.com/products/hat", facts_ready=True,
               facts=[dict(label="Material", value="100% cotton", source="catalog")],
               description=["A structured cap."])
BRIEF = dict(store="x.com", opportunity=dict(type="missing", key="q"), products=[PRODUCT], competitors=[],
             questions=[dict(question="Cotton cap under £30?", answers=10, own=0, theirs=9)])
REPLY = dict(title="Hat - Cotton Cap", title_reason="r", description_html="<p>A structured cap.</p>",
             spec_table=[dict(label="Material", value="100% cotton"), dict(label="Fit", value="Adjustable")],
             open_questions=[dict(question="What sizes?", why="fit")], changes=["c"])


class DraftsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        # The canned replies below are the drafts; the fact check's own AI pass is tested in test_factcheck.
        real = factcheck.check
        self.fc = mock.patch("factcheck.check", lambda *a, **k: real(*a, **dict(k, ai=False)))
        self.fc.start()

    def tearDown(self):
        self.fc.stop()
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_invented_spec_is_removed(self):
        with mock.patch("llm.json_call", return_value=json.loads(json.dumps(REPLY))):
            res = drafts.product_fix(BRIEF)
        self.assertEqual(res["spec_table"], [dict(label="Material", value="100% cotton")])
        self.assertEqual(res["removed_specs"], [dict(label="Fit", value="Adjustable")])

    def test_junk_spec_rows_and_shipping_weight_are_dropped(self):
        product = dict(PRODUCT, facts=PRODUCT["facts"] + [dict(label="Shipping weight", value="92 g", source="catalog"),
                                                          dict(label="Brand", value="Hatco", source="catalog")])
        reply = dict(REPLY, spec_table=[dict(label="Material", value="100% cotton"), dict(label="Brand", value="Hatco"),
                                        dict(label="Weight", value="92 g")])
        with mock.patch("llm.json_call", return_value=json.loads(json.dumps(reply))) as call:
            res = drafts.product_fix(dict(BRIEF, products=[product]))
        self.assertNotIn("92 g", call.call_args_list[0][0][1])              # the model never sees shipping weight
        self.assertEqual(res["spec_table"], [dict(label="Material", value="100% cotton")])

    def test_title_may_only_add_stated_words(self):
        p = dict(title="Harbour Cap", description=["A structured cap."],
                 facts=[dict(label="Material", value="100% cotton", source="catalog")])
        ok = dict(title="Acme Harbour Cap - 100% Cotton Structured Cap", title_reason="")
        self.assertEqual(drafts.check_title(ok, p, "Acme"), "")
        self.assertEqual(ok["title"], "Acme Harbour Cap - 100% Cotton Structured Cap")
        invented = dict(title="Acme Harbour Cap - Waterproof Cotton Cap", title_reason="")
        self.assertIn("waterproof", drafts.check_title(invented, p, "Acme"))
        self.assertEqual(invented["title"], "Harbour Cap")              # reverted, with the reason shown
        renamed = dict(title="Acme Cotton Cap", title_reason="")
        self.assertTrue(drafts.check_title(renamed, p, "Acme"))       # lost the product's own name
        long = dict(title="Acme Harbour Cap " + "cotton " * 10, title_reason="")
        self.assertIn("70", drafts.check_title(long, p, "Acme"))

    def test_hedging_about_sources_is_rewritten(self):
        self.assertEqual(drafts.unhedge("Beauty products are non-returnable under the stated refund policy."),
                         "Beauty products are non-returnable under our refund policy.")
        self.assertEqual(drafts.unhedge("The oil is described as light. its description says it absorbs well."),
                         "The oil is light. It absorbs well.")

    def test_no_facts_no_draft(self):
        with self.assertRaises(ValueError):
            drafts.product_fix(dict(BRIEF, products=[dict(PRODUCT, facts_ready=False)]))

    def test_saved_to_inbox_as_draft(self):
        with mock.patch("llm.json_call", return_value=json.loads(json.dumps(REPLY))):
            res = drafts.product_fix(BRIEF)
        did = drafts.save(None, BRIEF, res)
        row = db.one("SELECT * FROM content_drafts WHERE id=?", (did,))
        self.assertEqual(row["status"], "draft")
        self.assertIsNone(row["published_at"])
        self.assertEqual(drafts.latest(did)["open_questions"][0]["question"], "What sizes?")


    def test_faq_answers_must_rest_on_stated_facts(self):
        reply = dict(faqs=[dict(question="Is it cotton?", answer="Yes.", facts_used=["100% cotton"]),
                           dict(question="Is it waterproof?", answer="Yes.", facts_used=["waterproof"])],
                     open_questions=[])
        with mock.patch("llm.json_call", return_value=reply):
            res = drafts.faq(BRIEF)
        self.assertEqual([f["question"] for f in res["faqs"]], ["Is it cotton?"])
        self.assertEqual(res["removed_faqs"][0]["question"], "Is it waterproof?")
        self.assertIn('"@type": "FAQPage"', res["html"])

    def test_comparison_blanks_unstated_cells(self):
        comp = dict(brand="Rival", product="Cap", url="https://r.com/cap", named=5, page_read=True,
                    page_excerpt="Made from 100% polyester.", reviews=0)
        brief = dict(BRIEF, competitors=[comp])
        reply = dict(title="Hat vs Rival Cap", intro="For buyers choosing a cap.", columns=["P1", "C1"],
                     rows=[dict(label="Material", cells=[dict(id="P1", value="100% cotton"),
                                                          dict(id="C1", value="100% polyester")]),
                           dict(label="Waterproof", cells=[dict(id="P1", value="Yes"), dict(id="C1", value="Yes")])],
                     summary=[dict(id="P1", text="For cotton fans.", facts_used=["100% cotton"]),
                              dict(id="C1", text="Lasts forever.", facts_used=["lifetime warranty"])],
                     open_questions=[])
        with mock.patch("llm.json_call", return_value=reply):
            res = drafts.comparison(brief)
        self.assertEqual([r["label"] for r in res["rows"]], ["Material"])
        self.assertEqual([s["id"] for s in res["summary"]], ["P1"])
        self.assertIn("100% polyester", res["html"])
        did = drafts.save(None, brief, res, "comparison")
        self.assertEqual(db.one("SELECT title FROM content_drafts WHERE id=?", (did,))["title"], "Hat vs Rival Cap")

    def test_comparison_needs_two_products(self):
        with self.assertRaises(ValueError):
            drafts.comparison(BRIEF)

    def test_guide_drops_unbacked_picks_and_other_brands(self):
        brief = dict(BRIEF, competitors=[dict(brand="Rival", product="Cap", url="", named=3, page_read=False,
                                              page_excerpt="", reviews=0)])
        reply = dict(title="How to choose a cap", intro="i",
                     sections=[dict(heading="Fabric", paragraphs=["Cotton breathes.", "Rival caps fade."])],
                     picks=[dict(id="P1", for_whom="Everyday", text="Cotton.", facts_used=["100% cotton"]),
                            dict(id="P1", for_whom="Rain", text="Waterproof.", facts_used=["waterproof"])],
                     open_questions=[])
        with mock.patch("llm.json_call", return_value=reply):
            res = drafts.guide(brief)
        self.assertEqual([k["for_whom"] for k in res["picks"]], ["Everyday"])
        self.assertEqual(res["removed_paragraphs"], ["Rival caps fade."])
        self.assertIn('href="https://x.com/products/hat"', res["html"])


if __name__ == "__main__":
    unittest.main()
