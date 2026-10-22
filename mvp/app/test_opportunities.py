"""Opportunities stays invisible to users until config.SHOW_OPPORTUNITIES is on."""
import os
import tempfile
import unittest

import config
import db
import app
import opportunities


class OpportunitiesSwitchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_OPPORTUNITIES
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()

    def tearDown(self):
        config.DB_PATH, config.SHOW_OPPORTUNITIES = self.old
        self.tmp.cleanup()

    def test_off_hides_page_rail_and_actions(self):
        config.SHOW_OPPORTUNITIES = False
        self.assertEqual(opportunities.page({})[0], 404)
        self.assertEqual(opportunities.act({}, {"d": "x.com", "kind": "lost", "key": "q", "status": "done"})[0], 404)
        self.assertNotIn("Opportunities", app.rail("/", ""))

    def test_on_shows_rail_item(self):
        config.SHOW_OPPORTUNITIES = True
        self.assertIn("/opportunities", app.rail("/", ""))


if __name__ == "__main__":
    unittest.main()
