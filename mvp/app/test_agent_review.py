"""agent_review: honest verdicts (noise is "no change", short or thin is "too early"), one review a month per
agent, lessons without a model call when nothing has a verdict, re-fixes only for fixes that didn't move."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import agent_review as ar
import config
import content_agent
import db


class AgentReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        content_agent.init()
        ar.init()

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_verdicts(self):
        self.assertEqual(ar.verdict(0, 28, 9, 30, 30), "moved")        # 0% -> 30%: past noise
        self.assertEqual(ar.verdict(9, 30, 0, 28, 30), "dropped")
        self.assertEqual(ar.verdict(3, 28, 4, 30, 30), "flat")         # 11% -> 13% is noise
        self.assertEqual(ar.verdict(0, 28, 9, 30, 10), "early")        # live under 14 days
        self.assertEqual(ar.verdict(0, 28, 3, 6, 30), "early")         # too few answers since

    def test_lessons_need_a_verdict(self):
        with mock.patch("llm.json_call") as call:
            out = ar.lessons([dict(verdict="early"), dict(verdict="unmeasured")])
        call.assert_not_called()
        self.assertIn("Not enough evidence yet", out[0])

    def test_review_runs_once_a_month_and_refixes_flat_fixes(self):
        rows = [dict(id=1, type="product_fix", title="Hat: page fix", published_at=time.time() - 40 * 86400, days=40,
                     questions=["q"], product="Hat", change="title", live_url="", opp=("missing", "q"),
                     before=[2, 28], after=[3, 40], verdict="flat"),
                dict(id=2, type="product_fix", title="Oil: page fix", published_at=time.time() - 5 * 86400, days=5,
                     questions=["q2"], product="Oil", change="title", live_url="", opp=("missing", "q2"),
                     before=[0, 28], after=[1, 5], verdict="early")]
        made = []
        with mock.patch.object(ar, "measure", return_value=rows), \
                mock.patch.object(ar, "lessons", return_value=["Lead with the material."]), \
                mock.patch("briefs.build", return_value=dict(store="x.com", products=[], questions=[])), \
                mock.patch("briefs.save", return_value=1), \
                mock.patch("drafts.product_fix", side_effect=lambda b, usage=None: made.append(b) or {"title": "t"}), \
                mock.patch("selfreview.review", return_value=None), \
                mock.patch("drafts.save", return_value=99), \
                mock.patch("content_plan.allowance", return_value=50):
            out = ar.review("x.com", "fixes")
            self.assertIsNone(ar.review("x.com", "fixes"))                # already reviewed this month
        self.assertEqual(out["refixes"], [99])                             # only the flat, 40-day-old fix
        self.assertIn("different angle", made[0]["editor_notes"][0]["fix"])
        self.assertEqual(ar.current_lessons("x.com", "fixes"), ["Lead with the material."])

    def test_results_page_says_what_changed_not_why(self):
        db.write("INSERT INTO agent_reviews (store_domain, month, lane, rows, lessons, refixes, created_at) VALUES "
                 "('x.com','2026-10','fixes',?,?,'[]',0)", (json.dumps([dict(
                     id=1, type="product_fix", title="Hat", product="Hat", change="title", before=[1, 28],
                     after=[9, 30], verdict="moved", days=30)]), json.dumps(["Lead with the material."])))
        html = ar.page("x.com", "fixes")
        self.assertIn("Named more often", html)
        self.assertIn("not why", html)
        self.assertIn("Lead with the material.", html)


if __name__ == "__main__":
    unittest.main()
