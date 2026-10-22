"""Calendar: approving plans a weekday slot in the store's zone; items move; the panel tells the whole story."""
import datetime as dt
import json
import os
import tempfile
import time
import unittest

import config
import content_agent
import content_calendar
import db
import storetime


class CalendarTest(unittest.TestCase):
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

    def _draft(self):
        brief = dict(opportunity=dict(title="Get recommended for cotton caps"),
                     questions=[dict(question="Cotton cap?", own=0, answers=9)],
                     competitors=[dict(brand="Rival", product="Cap", named=7, page_read=False, url="")])
        with db.conn() as c:
            bid = c.execute("INSERT INTO content_briefs (store_domain, draft_type, data, created_at) VALUES "
                            "('x.com','faq',?,?)", (json.dumps(brief), time.time())).lastrowid
            # A guide: only articles get calendar dates (product pages go live from the board, 16 Oct 2026).
            did = c.execute("INSERT INTO content_drafts (brief_id, store_domain, draft_type, title, status, created_at) "
                            "VALUES (?, 'x.com','guide','Hat: guide','draft',?)", (bid, time.time())).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, sources, created_at) VALUES (?,?,?,?)",
                      (did, json.dumps(dict(title="Choosing a cap", intro="Cotton caps breathe.",
                                            sections=[dict(heading="Fit", paragraphs=["Pick a structured cap."])], picks=[],
                                            products=[dict(title="Hat", url="https://x.com/products/hat", handle="hat")],
                                            product=dict(title="Hat", url="https://x.com/products/hat"))),
                       json.dumps([dict(label="Material", value="Cotton")]), time.time()))
        return did

    def test_approve_plans_next_free_weekdays(self):
        a, b = self._draft(), self._draft()
        for did in (a, b):
            content_agent.act({}, {"d": "x.com", "id": str(did), "status": "approved"})
        tz = storetime.zone("x.com")
        days = [storetime.date_of(db.one("SELECT planned_at FROM content_drafts WHERE id=?", (d,))["planned_at"], tz)
                for d in (a, b)]
        self.assertNotEqual(days[0], days[1])                    # one a day
        self.assertTrue(all(d.weekday() < 5 and d > storetime.today(tz) for d in days))

    def test_move_and_reject_clears_plan(self):
        did = self._draft()
        content_agent.act({}, {"d": "x.com", "id": str(did), "status": "approved"})
        tz = storetime.zone("x.com")
        target = storetime.today(tz) + dt.timedelta(days=20)
        code, where = content_agent.act({}, {"d": "x.com", "id": str(did), "action": "move", "day": target.isoformat()})
        self.assertEqual(code, 303)
        self.assertIn("id=%d" % did, where)
        row = db.one("SELECT planned_at FROM content_drafts WHERE id=?", (did,))
        self.assertEqual(storetime.date_of(row["planned_at"], tz), target)
        past = (storetime.today(tz) - dt.timedelta(days=1)).isoformat()
        self.assertEqual(content_agent.act({}, {"d": "x.com", "id": str(did), "action": "move", "day": past})[0], 400)
        content_agent.act({}, {"d": "x.com", "id": str(did), "status": "rejected"})
        self.assertIsNone(db.one("SELECT planned_at FROM content_drafts WHERE id=?", (did,))["planned_at"])

    def test_panel_shows_the_story(self):
        did = self._draft()
        content_agent.act({}, {"d": "x.com", "id": str(did), "status": "approved"})
        at = db.one("SELECT planned_at FROM content_drafts WHERE id=?", (did,))["planned_at"]
        week = storetime.date_of(at, storetime.zone("x.com")).isoformat()
        body = content_agent.page({"d": "x.com", "view": "calendar", "week": week, "id": str(did)})[1]
        for text in ("Where it goes", "Get recommended for cotton caps", "Cotton cap?", "Rival Cap (7)",
                     "1 fact from your catalog", "Not published yet", "Move to"):
            self.assertIn(text, body)



class FeedTest(CalendarTest):
    def test_private_feed_lists_planned_drafts_and_a_new_link_kills_the_old(self):
        import content_calendar
        with db.conn() as c:
            c.execute("INSERT INTO content_drafts (brief_id, store_domain, draft_type, title, status, planned_at, "
                      "created_at) VALUES (0,'x.com','faq','Hat; FAQ, sizes','draft',1792400000,0)")
            c.execute("INSERT INTO content_drafts (brief_id, store_domain, draft_type, title, status, created_at) "
                      "VALUES (0,'x.com','guide','Unplanned','draft',0)")
        old = content_calendar.feed_token("x.com")
        code, text = content_calendar.ical(old)
        self.assertEqual(code, 200)
        self.assertIn("SUMMARY:Hat\\; FAQ\\, sizes (needs approval)", text)
        self.assertNotIn("Unplanned", text)
        self.assertTrue(all(len(l.encode()) <= 75 for l in text.split("\r\n")))
        self.assertEqual(content_calendar.ical("nope")[0], 404)
        content_calendar.feed_token("x.com", new=True)
        self.assertEqual(content_calendar.ical(old)[0], 404)

if __name__ == "__main__":
    unittest.main()
