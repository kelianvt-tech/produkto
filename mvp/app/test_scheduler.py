"""The scheduler's whole job is 'one scan per store per day'. These tests are
about the two ways that goes wrong: scanning twice in a day, and skipping a
day. Nothing here touches Apify or OpenAI - scan.start is patched out."""

import datetime as dt
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import config   # noqa: E402
import db       # noqa: E402
import scheduler  # noqa: E402
import storetime  # noqa: E402

DOMAIN = "example.com"
# The test store sells from the US, so its day is an America/New_York day.
# Slots and the hours below are in that zone, the same one the scheduler uses.
COUNTRY = "US"


def at(hour, day=15):
    """Unix time for a fixed day at the given hour, in the STORE's zone."""
    return dt.datetime.combine(dt.date(2026, 9, day), dt.time(hour),
                               storetime.zone(DOMAIN)).timestamp()


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        # Point at a throwaway file INSIDE setUp, like the other test files.
        # Setting PRODUKTO_DB at import time is not enough: if another test
        # module loaded config first, the real database is already chosen, and
        # the DELETEs below would wipe real scans.
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        self.old_daily_scan_exclude = config.DAILY_SCAN_EXCLUDE
        config.DAILY_SCAN_EXCLUDE = ()
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert os.path.abspath(config.DB_PATH) != os.path.abspath(self.old) or "produkto.db" not in self.old
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        for t in ("scans", "prompt_sets", "stores"):
            db.write("DELETE FROM %s" % t)
        storetime.forget()
        db.write("INSERT INTO stores(domain,country) VALUES(?,?)", (DOMAIN, COUNTRY))
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", (DOMAIN, '["a question"]', time.time()))
        self.ps = db.one("SELECT id FROM prompt_sets")["id"]
        self.slot = scheduler.slot_hour(DOMAIN)

    def tearDown(self):
        storetime.forget()
        config.DB_PATH = self.old
        config.DAILY_SCAN_EXCLUDE = self.old_daily_scan_exclude
        self.tmp.cleanup()

    def add_scan(self, when, status="done"):
        return db.write("INSERT INTO scans(token,prompt_set_id,run_at,status,done,total)"
                        " VALUES(?,?,?,?,0,1)", ("tok%s" % when, self.ps, when, status))

    # --- the slot ---------------------------------------------------------
    def test_slot_is_inside_the_window_and_stable(self):
        for d in ("a.com", "b.com", "shop.example.co.uk"):
            h = scheduler.slot_hour(d)
            self.assertIn(h, range(config.SCAN_WINDOW_START,
                                   config.SCAN_WINDOW_START + config.SCAN_WINDOW_HOURS))
            self.assertEqual(h, scheduler.slot_hour(d))

    def test_stores_are_spread_across_the_window(self):
        hours = {scheduler.slot_hour("shop%d.com" % i) for i in range(40)}
        self.assertGreater(len(hours), 1, "every store got the same slot")

    # --- due ---------------------------------------------------------------
    def test_not_due_before_its_slot(self):
        self.assertEqual(scheduler.due(at(self.slot) - 60), [])

    def test_due_at_its_slot_when_never_scanned(self):
        self.assertEqual(scheduler.due(at(self.slot)), [DOMAIN])

    def test_not_due_again_after_scanning_today(self):
        self.add_scan(at(self.slot))
        self.assertEqual(scheduler.due(at(self.slot) + 3600), [])

    def test_due_again_the_next_day(self):
        self.add_scan(at(self.slot))
        self.assertEqual(scheduler.due(at(self.slot, day=16)), [DOMAIN])

    def test_yesterdays_scan_does_not_satisfy_today(self):
        self.add_scan(at(self.slot, day=14))
        self.assertEqual(scheduler.due(at(self.slot)), [DOMAIN])

    def test_a_running_scan_counts_as_today(self):
        """Started is what matters, not finished - otherwise a slow scan gets
        a second one started on top of it at the next tick."""
        self.add_scan(at(self.slot), status="running")
        self.assertEqual(scheduler.due(at(self.slot) + 600), [])

    def test_a_failed_scan_is_not_retried_today(self):
        """A retry would buy a second set of answers for the same date and put
        two points on one day. A gap in the line is the honest result."""
        self.add_scan(at(self.slot), status="failed")
        self.assertEqual(scheduler.due(at(self.slot) + 7200), [])
        self.assertEqual(scheduler.due(at(self.slot, day=16)), [DOMAIN])

    # --- which stores ------------------------------------------------------
    def test_store_without_questions_is_never_due(self):
        db.write("DELETE FROM prompt_sets")
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", (DOMAIN, "[]", time.time()))
        self.assertEqual(scheduler.due(at(23)), [])

    def test_legacy_prompt_set_without_a_domain_is_skipped(self):
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", (None, '["q"]', time.time()))
        self.assertEqual(scheduler.scannable(), [DOMAIN])

    def test_a_newly_set_up_store_is_scheduled_without_being_listed(self):
        # The whole point of the daily scan: onboard a store, and its dashboard
        # holds today's reading the next time it is opened.
        db.write("INSERT INTO stores(domain,country) VALUES(?,?)", ("new-shop.com", COUNTRY))
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", ("new-shop.com", '["q"]', time.time()))
        self.assertEqual(scheduler.scheduled(), [DOMAIN, "new-shop.com"])
        self.assertEqual(scheduler.due(at(23)), [DOMAIN, "new-shop.com"])

    def test_an_excluded_store_is_not_scheduled(self):
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", ("held-back.com", '["q"]', time.time()))
        config.DAILY_SCAN_EXCLUDE = ("held-back.com",)
        self.assertEqual(scheduler.scheduled(), [DOMAIN])
        self.assertEqual(scheduler.due(at(23)), [DOMAIN])

    # --- run_due -----------------------------------------------------------
    def test_run_due_starts_one_scan_per_due_store(self):
        with patch("scan.start") as start:
            started = scheduler.run_due(at(self.slot))
        self.assertEqual(started, [DOMAIN])
        start.assert_called_once_with(DOMAIN)

    def test_one_broken_store_does_not_stop_the_others(self):
        db.write("INSERT INTO prompt_sets(store_domain,prompts,created_at)"
                 " VALUES(?,?,?)", ("broken.com", '["q"]', time.time()))
        def boom(domain):
            if domain == "broken.com":
                raise RuntimeError("Apify is down")
        with patch("scan.start", side_effect=boom):
            started = scheduler.run_due(at(23))
        self.assertEqual(started, [DOMAIN])

    def test_scheduler_is_off_when_daily_scans_is_off(self):
        with patch.object(config, "DAILY_SCANS", False):
            self.assertIsNone(scheduler.start())


if __name__ == "__main__":
    unittest.main(verbosity=2)
