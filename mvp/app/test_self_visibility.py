"""Produkto's own AI visibility (self_visibility.py): counts who AI names, runs once a week,
refuses near the Apify limit, and shows on the admin page. No real Apify call."""

import os
import tempfile
import unittest

import accounts
import billing
import config
import db
import hub
import self_visibility as sv


def fake_ask(questions, engine):
    out = {}
    for i, q in enumerate(questions):
        text = "Try Profound or Peec AI." if i else "Produkto measures every product; Profound is brand level."
        out[q] = (text, [{"url": "https://www.getprodukto.com/pricing" if not i else "https://peec.ai/x"}], engine)
    return out


class SelfVisibilityTest(unittest.TestCase):
    def setUp(self):
        # Throwaway database chosen inside setUp - see test_scheduler.setUp.
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "sv.db")
        assert not os.path.basename(config.DB_PATH).startswith("produkto.db")
        db.init()
        accounts.init()
        billing.init()
        self.old_usage = hub.apify_usage
        hub.apify_usage = lambda: (5.0, 75.0)

    def tearDown(self):
        hub.apify_usage = self.old_usage
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_run_counts_us_and_rivals(self):
        r = sv.run(ask=fake_ask)
        self.assertTrue(r["ok"], r)
        last = sv.report()[0]
        engines = len(config.ENGINE_ORDER)
        self.assertEqual(last["answers"], len(sv.QUESTIONS) * engines)
        self.assertEqual(last["named"], engines)            # first question names us on each engine
        self.assertEqual(last["cited"], engines)
        self.assertEqual(dict(last["rivals"])["Profound"], len(sv.QUESTIONS) * engines)
        self.assertEqual(dict(last["rivals"])["Peec AI"], (len(sv.QUESTIONS) - 1) * engines)
        self.assertIn("Produkto in AI answers", hub.page()[1])

    def test_once_a_week_and_apify_headroom(self):
        sv.run(ask=fake_ask)
        self.assertFalse(sv.run(ask=fake_ask)["ok"])          # same week
        self.assertTrue(sv.guard(force=True)[0])
        ok, why = sv.guard(force=True, usage=(70.0, 75.0))
        self.assertFalse(ok)
        self.assertIn("daily scans", why[0])

    def test_word_matching(self):
        sv.store("2026-10-20", "chatgpt", "q", "Produktos? no. Peec is fine, profoundly not.", [])
        last = sv.report()[0]
        self.assertEqual(last["named"], 0)
        self.assertEqual(dict(last["rivals"]), {"Peec AI": 1})


if __name__ == "__main__":
    unittest.main()
