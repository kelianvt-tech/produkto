"""Draft view: gaps get filled or left out, edits rebuild the page, the original is kept."""
import json
import os
import tempfile
import time
import unittest

import config
import content_agent
import content_review
import db


def _faq():
    return dict(faqs=[dict(question="Is it cotton?", answer="Yes, 100% cotton.", facts_used=["100% cotton"]),
                      dict(question="What sizes?", answer="[ask merchant: Which sizes does it come in?]", facts_used=[])],
                open_questions=[dict(question="Which sizes does it come in?", why="")],
                product=dict(title="Hat", url="https://x.com/products/hat"))


class ContentReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.SHOW_CONTENT_AGENT = True
        db.init()
        content_agent.init()
        import content_setup
        content_setup.put("x.com", dict(part1_done_at=1))   # setup has its own tests

    def tearDown(self):
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def _draft(self, body, kind="faq"):
        with db.conn() as c:
            did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, created_at) "
                            "VALUES ('x.com',?,'Hat: FAQ','draft',?)", (kind, time.time())).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, sources, created_at) VALUES (?,?,'[]',?)",
                      (did, json.dumps(body), time.time()))
        return did

    def test_answering_a_gap_unblocks_approval(self):
        did = self._draft(_faq())
        code, body = content_agent.page({"d": "x.com", "view": "draft", "id": str(did)})
        self.assertEqual(code, 200)
        self.assertIn("1 gap to fill", body)
        self.assertIn("Which sizes does it come in?", body)
        content_agent.act({}, {"d": "x.com", "id": str(did), "action": "fill",
                               "q.0": "Which sizes does it come in?", "a.0": "One size, adjustable strap"})
        latest = content_review.load(did, "x.com")[1]
        self.assertEqual(latest["faqs"][1]["answer"], "One size, adjustable strap")
        self.assertIn("One size, adjustable strap", latest["html"])          # FAQ markup rebuilt
        self.assertEqual(content_agent.act({}, {"d": "x.com", "id": str(did), "status": "approved"})[0], 303)
        versions = db.all_("SELECT author FROM content_draft_versions WHERE draft_id=? ORDER BY id", (did,))
        self.assertEqual([v["author"] for v in versions], ["agent", "merchant"])   # original kept

    def test_leaving_a_gap_out_removes_the_faq(self):
        did = self._draft(_faq())
        content_agent.act({}, {"d": "x.com", "id": str(did), "action": "fill",
                               "q.0": "Which sizes does it come in?", "skip.0": "1"})
        latest = content_review.load(did, "x.com")[1]
        self.assertEqual([f["question"] for f in latest["faqs"]], ["Is it cotton?"])

    def test_edit_in_place_and_html_is_cleaned(self):
        body = dict(title="Hat", description_html="<p>A cap.</p>", spec_table=[dict(label="Material", value="Cotton")],
                    open_questions=[], current=dict(title="Hat", description=["Old."]), product=dict(title="Hat"))
        did = self._draft(body, "product_fix")
        page = content_agent.page({"d": "x.com", "view": "draft", "id": str(did)})[1]
        self.assertIn("Now on your store", page)           # 20 Oct: Before/After over the real product page
        self.assertIn("/content/fix-preview?", page)
        content_agent.act({}, {"d": "x.com", "id": str(did), "action": "save", "f.title": "Hat - Cotton Cap",
                               "f.description_html": '<p onclick="x()">New <b>cap</b>.</p><script>bad()</script>',
                               "f.spec_table.0.value": "100% cotton", "f.current.title": "hacked"})
        latest = content_review.load(did, "x.com")[1]
        self.assertEqual(latest["title"], "Hat - Cotton Cap")
        self.assertEqual(latest["description_html"], "<p>New <b>cap</b>.</p>")
        self.assertEqual(latest["spec_table"][0]["value"], "100% cotton")
        self.assertEqual(latest["current"]["title"], "Hat")                  # bookkeeping can't be edited

    def test_other_store_cannot_open_or_edit(self):
        import content_setup
        content_setup.put("y.com", dict(part1_done_at=1))
        did = self._draft(_faq())
        self.assertEqual(content_agent.page({"d": "y.com", "view": "draft", "id": str(did)})[0], 404)
        self.assertEqual(content_agent.act({}, {"d": "y.com", "id": str(did), "action": "save", "f.title": "x"})[0], 400)


if __name__ == "__main__":
    unittest.main()
