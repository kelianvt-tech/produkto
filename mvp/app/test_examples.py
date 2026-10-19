"""examples.py: approved drafts become style examples; edits show both versions; rejected ones never do."""
import json
import os
import tempfile
import time
import unittest

import config
import content_agent
import db
import examples


class ExamplesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()
        content_agent.init()

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def add(self, status, agent, merchant=None, kind="product_fix"):
        now = time.time()
        with db.conn() as c:
            did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, approved_at, created_at, "
                            "updated_at) VALUES ('s.com',?,?,?,?,?,?)", (kind, "t", status, now, now, now)).lastrowid
            for author, html in (("agent", agent), ("merchant", merchant)):
                if html:
                    c.execute("INSERT INTO content_draft_versions (draft_id, body, author, created_at) VALUES (?,?,?,?)",
                              (did, json.dumps(dict(title="T", description_html=html)), author, now))

    def test_none_approved_gives_nothing(self):
        self.add("draft", "<p>Waiting.</p>")
        self.add("rejected", "<p>Bad.</p>")
        self.assertEqual(examples.section("s.com", "product_fix"), "")

    def test_edit_shows_both_versions(self):
        self.add("approved", "<p>Elevate your routine.</p>", "<p>A light cream for dry skin.</p>")
        s = examples.section("s.com", "product_fix")
        self.assertIn("Elevate your routine.", s)
        self.assertIn("changed it to", s)
        self.assertIn("A light cream for dry skin.", s)
        self.assertIn("never take a fact", s)

    def test_only_same_kind(self):
        self.add("published", "<p>Guide text.</p>", kind="guide")
        self.assertEqual(examples.section("s.com", "product_fix"), "")


if __name__ == "__main__":
    unittest.main()
