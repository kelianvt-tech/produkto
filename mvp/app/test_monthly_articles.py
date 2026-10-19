"""monthly_articles: once a month, only tracked questions, winnable first, dated over the month, never approved."""
import os
import tempfile
import time
import unittest
from unittest import mock

import config
import content_agent
import content_setup
import db
import monthly_articles as m


class MonthlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        content_agent.init()
        content_setup.put("s.com", dict(part1_done_at=time.time(), monthly_articles=True))

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_off_for_unlimited_store_until_switched_on(self):
        content_setup.put("s.com", dict(part1_done_at=time.time()))
        self.assertEqual(m.count("s.com"), 0)

    def test_winnable_beats_bigger_but_hard(self):
        opps = [dict(type="missing", key="hard q", weight=10), dict(type="missing", key="easy q", weight=6),
                dict(type="position", key="other", weight=99)]
        levels = {"hard q": dict(level="hard", big_share=90), "easy q": dict(level="winnable", big_share=10)}
        with mock.patch("briefs._evidence", return_value=({"id": 1}, {}, {}, {})), \
                mock.patch("opportunities.find", return_value=opps), \
                mock.patch("opportunities._statuses", return_value={}), \
                mock.patch("briefs.winnable", side_effect=lambda qs, c: levels[qs[0]]):
            self.assertEqual([r["key"] for r in m.ranked("s.com")], ["easy q", "hard q"])

    def test_runs_once_a_month_and_dates_drafts(self):
        made = []

        def draft(domain, kind, key, only=None):
            self.assertEqual(only, m.ARTICLE_TYPES)
            with db.conn() as c:
                did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, created_at, "
                                "updated_at) VALUES ('s.com','guide',?, 'draft', 0, 0)", (key,)).lastrowid
            made.append(did)
            return did, None
        ranked = [dict(type="missing", key="q%d" % i, score=1, level="winnable", big_share=0) for i in range(3)]
        with mock.patch.object(m, "count", return_value=2), mock.patch.object(m, "ranked", return_value=ranked), \
                mock.patch.object(m, "_slots", return_value=[111.0, 222.0]), \
                mock.patch("content_agent.draft_for", side_effect=draft), \
                mock.patch("threading.Thread", side_effect=lambda target, daemon: mock.Mock(start=target)):
            self.assertTrue(m.run("s.com"))
            self.assertFalse(m.run("s.com"))                    # already ran this month
        self.assertEqual(len(made), 2)
        rows = db.all_("SELECT status, planned_at FROM content_drafts ORDER BY id")
        self.assertEqual([(r["status"], r["planned_at"]) for r in rows], [("draft", 111.0), ("draft", 222.0)])
        self.assertEqual(m.state("s.com")["short"], 0)


if __name__ == "__main__":
    unittest.main()
