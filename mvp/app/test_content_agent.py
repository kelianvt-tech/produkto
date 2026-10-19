"""The Content tab stays invisible until config.SHOW_CONTENT_AGENT is on."""
import os
import tempfile
import time
import unittest

import config
import db
import app
import content_agent


class ContentAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.CONTENT_AGENT_ADMIN_ONLY = False
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        content_agent.init()
        import content_setup
        content_setup.put("x.com", dict(part1_done_at=1))   # setup has its own tests

    def tearDown(self):
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def test_off_hides_tab_and_keeps_waitlist(self):
        config.SHOW_CONTENT_AGENT = False
        self.assertEqual(content_agent.page({})[0], 404)
        rail = app.rail("/", "")
        self.assertNotIn('href="/content', rail)
        self.assertIn("/agents", rail)

    def test_admin_only_mode_hides_it_from_customers(self):
        from unittest import mock
        old = config.CONTENT_AGENT_ADMIN_ONLY
        config.SHOW_CONTENT_AGENT, config.CONTENT_AGENT_ADMIN_ONLY = False, True
        try:
            with mock.patch("accounts.is_admin", return_value=False):
                self.assertEqual(content_agent.page({"d": "x.com"})[0], 404)
                self.assertNotIn('href="/content', app.rail("/", ""))
            with mock.patch("accounts.is_admin", return_value=True):
                self.assertIn('href="/content', app.rail("/", ""))
        finally:
            config.CONTENT_AGENT_ADMIN_ONLY = old

    def test_on_replaces_waitlist_with_content_tab(self):
        config.SHOW_CONTENT_AGENT = True
        rail = app.rail("/", "")
        self.assertIn('href="/content', rail)
        self.assertNotIn('href="/agents"', rail)

    def test_views_render_and_calendar_places_planned_drafts(self):
        config.SHOW_CONTENT_AGENT = True
        with db.conn() as c:
            c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, planned_at, created_at) "
                      "VALUES (?,?,?,?,?,?)", ("x.com", "guide", "Sofa guide", "approved", time.time(), time.time()))
        for view in ("inbox", "calendar", "published"):
            code, body = content_agent.page({"d": "x.com", "view": view})
            self.assertEqual(code, 200)
            self.assertIn('data-rail-page="content"', body)
        self.assertIn("Sofa guide", content_agent.page({"d": "x.com", "view": "calendar"})[1])
        board = content_agent.page({"d": "x.com", "view": "inbox", "lane": "articles"})[1]
        scheduled = board.split('data-col="scheduled"')[1].split('data-col="live"')[0]
        self.assertIn("Sofa guide", scheduled)                      # an approved article -> Scheduled

    def _draft(self, body):
        import json
        with db.conn() as c:
            did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, created_at, updated_at) "
                            "VALUES ('x.com','faq','Hat FAQ','draft',?,?)", (time.time(), time.time())).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, open_facts, created_at) VALUES (?,?,?,?)",
                      (did, json.dumps(body), json.dumps([dict(question="Size?", why="")]), time.time()))
        return did

    def test_inbox_approve_and_reject(self):
        config.SHOW_CONTENT_AGENT = True
        did = self._draft(dict(faqs=[dict(question="q", answer="Cotton.")]))
        body = content_agent.page({"d": "x.com", "view": "inbox", "lane": "fixes"})[1]
        self.assertIn("Hat FAQ", body.split('data-col="ready"')[1].split('data-col="scheduled"')[0])
        code, back = content_agent.act({}, {"d": "x.com", "id": str(did), "status": "approved",
                                            "back": "/content?d=x.com&view=inbox"})
        self.assertEqual((code, back), (303, "/content?d=x.com&view=inbox"))
        self.assertEqual(db.one("SELECT status FROM content_drafts WHERE id=?", (did,))["status"], "approved")
        board = content_agent.page({"d": "x.com", "view": "inbox", "lane": "fixes"})[1]
        ready = board.split('data-col="ready"')[1].split('data-col="scheduled"')[0]
        self.assertIn("Hat FAQ", ready)                             # an approved product page waits in Ready
        self.assertIn("Approved", ready)                            # until it's dragged to Live
        self.assertIsNone(db.one("SELECT planned_at FROM content_drafts WHERE id=?", (did,))["planned_at"])
        content_agent.act({}, {"d": "x.com", "id": str(did), "status": "rejected"})
        row = db.one("SELECT * FROM content_drafts WHERE id=?", (did,))
        self.assertEqual((row["status"], row["approved_at"]), ("rejected", None))
        self.assertEqual(content_agent.act({}, {"d": "other.com", "id": str(did), "status": "draft"})[0], 400)

    def test_drag_to_live_and_back(self):
        import json
        config.SHOW_CONTENT_AGENT = True
        did = self._draft(dict(faqs=[dict(question="q", answer="Cotton.")]))
        from unittest import mock
        code, out = content_agent.act({}, {"d": "x.com", "id": str(did), "action": "golive", "ajax": "1"})
        self.assertIn("Connect Shopify", json.loads(out[1])["error"])   # no Shopify, no going live
        self.assertEqual(db.one("SELECT status FROM content_drafts WHERE id=?", (did,))["status"], "draft")
        def publish(domain, d, by=None):
            db.write("UPDATE content_drafts SET status='published', live_url='https://x.com/products/hat' WHERE id=?", (d,))
        with mock.patch("shopify_connect.configured", return_value=True), \
                mock.patch("shopify_connect.connection", return_value={"shop": "x.myshopify.com"}), \
                mock.patch("shopify_connect.publish", side_effect=publish), mock.patch("shopify_connect.undo") as undo:
            code, out = content_agent.act({}, {"d": "x.com", "id": str(did), "action": "golive", "ajax": "1"})
            self.assertEqual(json.loads(out[1]), dict(ok=True, when="Live", status="published"))
            code, out = content_agent.act({}, {"d": "x.com", "id": str(did), "action": "unlive", "ajax": "1"})
            undo.assert_called_once()
        self.assertEqual(json.loads(out[1])["status"], "draft")
        gap = self._draft(dict(faqs=[dict(question="q", answer="[ask merchant: Size?]")]))
        with mock.patch("shopify_connect.configured", return_value=True), \
                mock.patch("shopify_connect.connection", return_value={"shop": "x.myshopify.com"}):
            code, out = content_agent.act({}, {"d": "x.com", "id": str(gap), "action": "golive", "ajax": "1"})
        self.assertFalse(json.loads(out[1])["ok"])                  # open questions still block going live
        self.assertEqual(db.one("SELECT status FROM content_drafts WHERE id=?", (gap,))["status"], "draft")

    def test_draft_with_gaps_cannot_be_approved(self):
        config.SHOW_CONTENT_AGENT = True
        did = self._draft(dict(faqs=[dict(question="q", answer="[ask merchant: What sizes?]")]))
        board = content_agent.page({"d": "x.com", "view": "inbox", "lane": "fixes"})[1]
        self.assertIn("Hat FAQ", board.split('data-col="facts"')[1].split('data-col="ready"')[0])   # Needs your facts
        sheet = content_agent.page({"d": "x.com", "view": "inbox", "lane": "fixes", "id": str(did)})[1]
        self.assertIn("1 gap to fill", sheet)
        self.assertNotIn('value="approved"', sheet)                 # no Approve while a gap is open
        self.assertEqual(content_agent.act({}, {"d": "x.com", "id": str(did), "status": "approved"})[0], 409)
        self.assertEqual(db.one("SELECT status FROM content_drafts WHERE id=?", (did,))["status"], "draft")

    def test_draft_fix_button_creates_draft_then_links_to_it(self):
        from unittest import mock
        import briefs
        import drafts
        config.SHOW_CONTENT_AGENT = True
        brief = dict(store="x.com", opportunity=dict(type="missing", key="q"), competitors=[],
                     questions=[dict(question="Is it cotton?", answers=3, own=0, theirs=3)],
                     products=[dict(handle="hat", title="Hat", url="u", facts_ready=True, description=["Cotton."],
                                    facts=[dict(label="Material", value="Cotton", source="catalog")])])
        card = dict(type="missing", key="q")
        self.assertIn("Draft fix", content_agent.opportunity_button("x.com", card)[0])
        self.assertEqual(content_agent.opportunity_button("x.com", dict(type="stale", key="q")), ("", ""))
        res = dict(title="Hat", title_reason="", description_html="<p>Cotton.</p>", spec_table=[], open_questions=[],
                   changes=[], product=dict(handle="hat", title="Hat", url="u"), current=dict(title="Hat", description=[]))
        with mock.patch("catalog_facts.get", return_value=[1]), mock.patch("briefs.build", return_value=brief), \
                mock.patch("drafts.product_fix", return_value=res):
            code, where = content_agent.act({}, {"d": "x.com", "action": "draft", "kind": "missing", "key": "q"})
        self.assertEqual(code, 303)
        self.assertIn("view=draft", where)
        self.assertIn("Open draft", content_agent.opportunity_button("x.com", card)[0])

    def test_draft_fix_explains_when_it_cannot_write(self):
        from unittest import mock
        config.SHOW_CONTENT_AGENT = True
        with mock.patch("catalog_facts.get", return_value=[1]), mock.patch("briefs.build", return_value=None):
            code, body = content_agent.act({}, {"d": "x.com", "action": "draft", "kind": "missing", "key": "q"})
        self.assertEqual(code, 200)
        self.assertIn("can&#x27;t write a fix", body)

    def test_one_rewrite_per_page(self):
        from unittest import mock
        config.SHOW_CONTENT_AGENT = True
        brief = dict(store="x.com", opportunity=dict(type="missing", key="q"), competitors=[],
                     questions=[dict(question="Is it cotton?", answers=3, own=0, theirs=3)],
                     products=[dict(handle="hat", title="Hat", url="u", facts_ready=True, description=["Cotton."],
                                    facts=[dict(label="Material", value="Cotton", source="catalog")])])
        with mock.patch("catalog_facts.get", return_value=[1]), mock.patch("briefs.build", return_value=brief), \
                mock.patch("drafts.faq", return_value=dict(faqs=[], open_questions=[], html="",
                                                           product=dict(handle="hat", title="Hat", url="u"))) as faq, \
                mock.patch("drafts.product_fix") as fix, \
                mock.patch("selfreview.review", return_value=dict(scores=dict(a=5), issues=[], passed=True)):
            content_agent.draft_for("x.com", "missing", "q", avoid={("product_fix", "hat")})
        fix.assert_not_called()                 # the page already has a fix in progress: write the FAQ instead
        faq.assert_called_once()

    def test_failed_review_rewrites_once_and_keeps_the_better(self):
        from unittest import mock
        config.SHOW_CONTENT_AGENT = True
        brief = dict(store="x.com", opportunity=dict(type="missing", key="q"), competitors=[],
                     questions=[dict(question="Is it cotton?", answers=3, own=0, theirs=3)],
                     products=[dict(handle="hat", title="Hat", url="u", facts_ready=True, description=["Cotton."],
                                    facts=[dict(label="Material", value="Cotton", source="catalog")])])
        out = lambda: dict(faqs=[], open_questions=[], html="", product=dict(handle="hat", title="Hat", url="u"))
        grades = iter([dict(scores=dict(a=2), issues=[dict(problem="p", fix="f")], passed=False),
                       dict(scores=dict(a=5), issues=[], passed=True)])
        with mock.patch("catalog_facts.get", return_value=[1]), mock.patch("briefs.build", return_value=brief), \
                mock.patch("drafts.faq", side_effect=lambda b, usage=None: out()) as faq, \
                mock.patch("drafts.product_fix"), mock.patch("drafts.save", return_value=7) as save, \
                mock.patch("briefs.save", return_value=1), \
                mock.patch("selfreview.review", side_effect=lambda *a, **k: next(grades)):
            content_agent.draft_for("x.com", "missing", "q", avoid={("product_fix", "hat")})
        self.assertEqual(faq.call_count, 2)
        self.assertEqual(faq.call_args_list[1].args[0]["editor_notes"][0]["fix"], "f")
        saved = save.call_args.args[2]
        self.assertTrue(saved["rewritten"])
        self.assertTrue(saved["review"]["passed"])


if __name__ == "__main__":
    unittest.main()
