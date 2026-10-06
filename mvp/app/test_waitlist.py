"""The waitlist is evidence, so these tests are about recording it correctly:
the right question, no duplicates, no junk emails. No network involved."""

import json
import os
import tempfile
import unittest

import config
import db
import waitlist


class WaitlistTest(unittest.TestCase):
    def setUp(self):
        # Throwaway database chosen inside setUp - see test_scheduler.setUp
        # for why an import-time environment variable is not enough.
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "w.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        waitlist.init()
        db.write("DELETE FROM waitlist")

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def rows(self):
        return db.all_("SELECT * FROM waitlist ORDER BY id")

    def test_records_the_question_and_where_the_merchant_stood(self):
        self.assertTrue(waitlist.save(" Kelian@Shop.com ", "shop.com", "best cleanser?", 4.0, "CeraVe"))
        r = self.rows()[0]
        self.assertEqual((r["email"], r["store_domain"], r["prompt"], r["visibility"], r["top_competitor"]),
                         ("kelian@shop.com", "shop.com", "best cleanser?", 4.0, "CeraVe"))

    def test_same_question_twice_is_one_signal(self):
        waitlist.save("a@b.co", "shop.com", "q1", 0, None)
        self.assertFalse(waitlist.save("A@b.co", "shop.com", "q1", 0, None))
        self.assertEqual(len(self.rows()), 1)

    def test_a_different_question_is_a_new_signal(self):
        waitlist.save("a@b.co", "shop.com", "q1", 0, None)
        self.assertTrue(waitlist.save("a@b.co", "shop.com", "q2", 10, None))
        self.assertEqual(len(self.rows()), 2)

    def test_rejects_non_emails(self):
        for bad in ("", "nope", "a@b", "a b@c.com", "@c.com"):
            with self.assertRaises(ValueError):
                waitlist.save(bad, "shop.com", "q", 0, None)
        self.assertEqual(self.rows(), [])

    def test_api_reports_errors_without_saving(self):
        # The app's handlers return (status, (kind, text)) - see app.json_out.
        # Checked against json_out itself, so this test cannot drift from it.
        import app
        code, (kind, body) = waitlist.api({}, {"email": "bad", "prompt": "q"})
        self.assertEqual(json.loads(body)["error"], "Enter a valid email address.")
        self.assertEqual((code, kind), app.json_out({})[:1] + (app.json_out({})[1][0],))
        code, (kind, body) = waitlist.api({}, {"email": "x@y.io", "store": "s.com", "prompt": "q", "visibility": "7"})
        self.assertTrue(json.loads(body)["ok"])
        self.assertEqual(self.rows()[0]["visibility"], 7.0)

    def test_button_carries_escaped_data(self):
        html = waitlist.button(dict(prompt='a "quoted" <q>', rate=4, runs=5, top=None, products=[], store="s.com"))
        self.assertIn('class="wl-open"', html)
        self.assertNotIn('<q>', html)

    def test_copy_makes_no_ranking_promise(self):
        page = waitlist.assets().lower()
        for promise in ("rank well", "guarantee", "boost your ranking", "designed to rank"):
            self.assertNotIn(promise, page)
        self.assertIn("in development", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class WaitlistSourceTest(unittest.TestCase):
    """The two doors onto the waitlist must stay apart.

    A merchant clicking "Improve visibility" on one buyer question is telling
    us which question they want fixed. A merchant joining from the Content
    agents page is telling us they want the agents at all. Pooling the two
    throws away the difference, which is the whole reason the rows are kept.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        waitlist.init()
        db.write("DELETE FROM waitlist")

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_the_agents_page_records_its_own_source(self):
        waitlist.save("a@b.com", "shop.com", None, None, None, source="content-agents")
        row = db.one("SELECT * FROM waitlist ORDER BY id DESC LIMIT 1")
        self.assertEqual(row["source"], "content-agents")
        self.assertIsNone(row["prompt"])

    def test_a_question_signup_defaults_to_improve_visibility(self):
        waitlist.save("a@b.com", "shop.com", "best cleanser?", 20.0, "Cerave")
        row = db.one("SELECT * FROM waitlist ORDER BY id DESC LIMIT 1")
        self.assertEqual(row["source"], "improve-visibility")

    def test_the_same_person_can_join_from_both_doors(self):
        # Two different signals from one merchant, not a duplicate.
        self.assertTrue(waitlist.save("a@b.com", "shop.com", None, None, None,
                                      source="content-agents"))
        self.assertTrue(waitlist.save("a@b.com", "shop.com", "best cleanser?", 20.0, None))
        self.assertEqual(db.one("SELECT COUNT(*) c FROM waitlist")["c"], 2)

    def test_joining_the_agents_waitlist_twice_is_one_row(self):
        self.assertTrue(waitlist.save("a@b.com", "shop.com", None, None, None,
                                      source="content-agents"))
        self.assertFalse(waitlist.save("a@b.com", "shop.com", None, None, None,
                                       source="content-agents"))
        self.assertEqual(db.one("SELECT COUNT(*) c FROM waitlist")["c"], 1)
