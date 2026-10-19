"""Pages a month follow the plan, like Promptwatch: Starter none, Growth 5 + packs, admin unlimited."""
import json
import os
import tempfile
import time
import unittest

import accounts
import config
import content_agent
import content_plan
import content_setup
import db


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.SHOW_CONTENT_AGENT = True
        db.init()
        accounts.init()
        content_agent.init()
        content_setup.put("x.com", dict(part1_done_at=1))

    def tearDown(self):
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def _owner(self, limit):
        uid = accounts.create_user("o%d@x.com" % limit, "password1234", question_limit=limit)
        db.write("INSERT INTO user_stores VALUES (?, 'x.com')", (uid,))

    def _draft(self):
        with db.conn() as c:
            did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, created_at) "
                            "VALUES ('x.com','faq','t','draft',?)", (time.time(),)).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, sources, created_at) VALUES (?,?,'[]',?)",
                      (did, json.dumps(dict(faqs=[])), time.time()))
        return did

    def test_admin_store_is_unlimited(self):
        self.assertIsNone(content_plan.allowance("x.com", "fixes"))
        self.assertEqual(content_plan.max_pace("x.com"), 7)

    def test_starter_is_locked(self):
        self._owner(accounts.PLANS["starter"])
        self.assertTrue(content_plan.locked("x.com"))
        self.assertIn("included from the Growth plan", content_agent.page({"d": "x.com"})[1])
        self.assertIn("(Growth)", content_agent.opportunity_button("x.com", dict(type="missing", key="q"))[0])

    def _draft_of(self, kind):
        did = self._draft()
        db.write("UPDATE content_drafts SET draft_type=? WHERE id=?", (kind, did))
        return did

    def test_growth_has_fixes_and_articles_only_with_packs(self):
        self._owner(accounts.PLANS["growth"])
        self.assertEqual((content_plan.allowance("x.com", "fixes"), content_plan.allowance("x.com", "articles")), (50, 0))
        self.assertFalse(content_plan.can_draft("x.com", "guide"))      # the agent doesn't write articles...
        self.assertTrue(content_plan.can_draft("x.com", "product_fix"))
        fixes = [self._draft_of("product_fix") for _ in range(51)]
        codes = [content_agent.act({}, {"d": "x.com", "id": str(i), "status": "approved"})[0] for i in fixes]
        self.assertEqual(codes, [303] * 50 + [409])
        page = content_agent.page({"d": "x.com", "view": "inbox", "lane": "fixes"})[1]
        self.assertIn("<b>50</b> of 50 approved", page)                  # the Product page fixes meter
        content_agent.act({}, {"d": "x.com", "id": str(fixes[0]), "status": "rejected"})   # frees a fix
        self.assertEqual(content_agent.act({}, {"d": "x.com", "id": str(fixes[50]), "status": "approved"})[0], 303)
        s = content_setup.get("x.com")
        s["extra_articles"] = 10                                         # ...until a pack is bought
        content_setup.put("x.com", s)
        self.assertEqual(content_plan.allowance("x.com", "articles"), 10)
        self.assertTrue(content_plan.can_draft("x.com", "guide"))
        s["extra_fixes"] = 150                                           # 200 a month on the pricing page
        content_setup.put("x.com", s)
        self.assertEqual(content_plan.allowance("x.com", "fixes"), 200)
        guide = self._draft_of("guide")
        self.assertEqual(content_agent.act({}, {"d": "x.com", "id": str(guide), "status": "approved"})[0], 303)

if __name__ == "__main__":
    unittest.main()
