"""The Support page's two jobs: say honestly whether scans are healthy, and
record a request with enough context to answer it.

The status line is the part worth testing hardest. A hardcoded "All systems
operational" would be worse than no status at all, because it would be a lie on
exactly the morning a merchant needs the truth.
"""

import datetime as dt
import os
import tempfile
import time
import unittest

import config
import db
import storetime
import support

DOMAIN = "shop-usa.com"


class SupportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        self.old_exclude = config.DAILY_SCAN_EXCLUDE
        config.DAILY_SCAN_EXCLUDE = ()
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        support.init()
        for t in ("scans", "prompt_sets", "stores", "support_requests"):
            db.write("DELETE FROM %s" % t)
        storetime.forget()
        db.write("INSERT INTO stores(domain,country) VALUES(?,?)", (DOMAIN, "US"))
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", (DOMAIN, '["a question"]', time.time()))
        self.ps = db.one("SELECT id FROM prompt_sets")["id"]

    def tearDown(self):
        storetime.forget()
        config.DAILY_SCAN_EXCLUDE = self.old_exclude
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def add_scan(self, when, status="done"):
        db.write("INSERT INTO scans(token,prompt_set_id,run_at,status,done,total)"
                 " VALUES(?,?,?,?,?,?)",
                 ("t%d" % when, self.ps, when, status, 1, 1))

    # --- status ------------------------------------------------------------
    def test_a_slot_only_just_passed_is_not_called_late(self):
        # A scan that is ten minutes overdue is not news; it is still starting.
        import scheduler
        when = scheduler.slot_today(DOMAIN) + 600
        level, headline, _ = support.status(now=when)
        self.assertNotEqual(headline, "Scans delayed")

    def test_a_scan_today_is_operational(self):
        self.add_scan(time.time() - 3600)
        level, headline, _ = support.status()
        self.assertEqual(level, "ok")
        self.assertEqual(headline, "All systems operational")

    def test_a_failed_scan_says_so(self):
        self.add_scan(time.time() - 3600, status="failed")
        level, headline, detail = support.status()
        self.assertEqual(level, "down")
        self.assertEqual(headline, "Scans failing")
        self.assertIn(DOMAIN, detail)

    def test_a_running_scan_is_reported_as_in_progress(self):
        self.add_scan(time.time() - 300, status="running")
        level, headline, _ = support.status()
        self.assertEqual(level, "ok")
        self.assertEqual(headline, "Scan in progress")

    def test_a_missed_slot_is_reported_late_not_operational(self):
        # No scan at all, and the store's slot passed hours ago. This is the
        # morning the merchant must not be told everything is fine.
        import scheduler
        when = scheduler.slot_today(DOMAIN) + support.LATE_AFTER_SECONDS + 60
        level, headline, detail = support.status(now=when)
        self.assertEqual(level, "warn")
        self.assertEqual(headline, "Scans delayed")
        self.assertIn(DOMAIN, detail)

    # --- requests ----------------------------------------------------------
    def test_a_request_records_the_store_and_its_last_scan(self):
        when = time.time() - 7200
        self.add_scan(when)
        support.save("m@example.com", "My numbers look wrong",
                     "The visibility number dropped overnight.", DOMAIN, "TestAgent/1")
        row = db.one("SELECT * FROM support_requests ORDER BY id DESC LIMIT 1")
        self.assertEqual(row["store_domain"], DOMAIN)
        self.assertAlmostEqual(row["last_scan_at"], when, places=3)
        self.assertEqual(row["user_agent"], "TestAgent/1")

    def test_a_bad_address_is_refused(self):
        with self.assertRaises(ValueError):
            support.save("not-an-email", "", "A message long enough to pass.", DOMAIN, "")

    def test_an_empty_message_is_refused(self):
        # A blank request costs a round trip to ask what they meant.
        with self.assertRaises(ValueError):
            support.save("m@example.com", "", "help", DOMAIN, "")

    def test_the_form_attaches_one_store_without_asking(self):
        field, note = support._store_field()
        self.assertIn('type="hidden"', field)
        self.assertIn(DOMAIN, field)
        self.assertIn(DOMAIN, note)

    def test_the_form_asks_which_store_when_there_are_several(self):
        db.write("INSERT INTO stores(domain,country) VALUES(?,?)", ("other.com", "US"))
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", ("other.com", '["q"]', time.time()))
        field, _ = support._store_field()
        self.assertIn("<select", field)
        self.assertIn("other.com", field)
        self.assertIn(DOMAIN, field)


if __name__ == "__main__":
    unittest.main()
