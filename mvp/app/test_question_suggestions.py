"""question_suggestions: weak questions become swaps (worst evidence first); filters keep out brand names,
page copies and near-duplicates; dismissed ones never return; a swap edits the tracked questions."""
import json
import os
import tempfile
import unittest
from unittest import mock

import config
import db
import question_suggestions as qs


class SuggestionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        qs.init()

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_general_advice_questions_come_first(self):
        ps = dict(prompts=["copy q", "advice q", "fine q"])
        stats = {"advice q": dict(answers=78, named=8, own=0), "fine q": dict(answers=78, named=70, own=0),
                 "copy q": dict(answers=78, named=70, own=0)}
        with mock.patch.object(qs, "_quality", return_value={"copy q": "Reads like your page."}):
            out = qs.poor("s.com", ps, stats)
        self.assertEqual([q for q, _, _ in out], ["advice q", "copy q"])
        self.assertIn("8 of 78", out[0][1])

    def test_near_duplicates(self):
        self.assertTrue(qs._too_close("best cotton cap under £30", ["What's a cotton cap under £30, the best one?"]))
        self.assertFalse(qs._too_close("moisturiser with squalane for dry skin", ["best cotton cap under £30"]))

    def test_dismiss_and_open_count(self):
        db.write("INSERT INTO question_suggestions (store_domain, kind, new_q, created_at) VALUES ('s.com','add','q',0)")
        self.assertEqual(qs.count("s.com"), 1)
        sid = db.one("SELECT id FROM question_suggestions")["id"]
        self.assertEqual(qs.decide("s.com", sid, "dismiss"), "")
        self.assertEqual(qs.count("s.com"), 0)
        self.assertIn("gone", qs.decide("s.com", sid, "add"))

    def test_swap_replaces_the_old_question(self):
        db.write("INSERT INTO question_suggestions (store_domain, kind, old_q, new_q, products, created_at) "
                 "VALUES ('s.com','swap','old one','new one','[]',0)")
        sid = db.one("SELECT id FROM question_suggestions")["id"]
        items = [dict(q="old one", tag="best", cluster="Caps", products=[5]), dict(q="keep", tag="", cluster="Caps", products=[5])]
        sent = {}
        with mock.patch("db.get_prompt_set", return_value={"id": 1}), \
                mock.patch("catalog_setup.items_out", return_value=items), \
                mock.patch("accounts.check_question_limit"), \
                mock.patch("app.api_questions", side_effect=lambda q, f: sent.update(f) or (200, ("json", "{}"))):
            self.assertEqual(qs.decide("s.com", sid, "swap"), "")
        saved = json.loads(sent["questions"])
        self.assertEqual([x["q"] for x in saved], ["keep", "new one"])
        self.assertEqual(saved[1]["products"], [5])                 # the swap keeps the old question's products
        self.assertEqual(saved[1]["cluster"], "Caps")


if __name__ == "__main__":
    unittest.main()
