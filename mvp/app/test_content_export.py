"""Export: approved drafts become a Shopify CSV and page files; nothing else does."""
import csv
import io
import json
import os
import tempfile
import time
import unittest
import zipfile

from unittest import mock

import config
import content_agent
import content_export
import content_setup
import db


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.SHOW_CONTENT_AGENT = True
        db.init()
        content_agent.init()
        content_setup.put("x.com", dict(part1_done_at=1))
        self.opts = mock.patch("content_export.options", side_effect=lambda d, h: [("Size", ["S", "L"])] if h == "hat" else None)
        self.opts.start()
        db.write("INSERT INTO products (store_domain, handle, title, raw_json) VALUES ('x.com','hat','Hat',?)",
                 (json.dumps(dict(body_html='<p class="x">Original <b>hat</b> copy.</p>')),))

    def tearDown(self):
        self.opts.stop()
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def _draft(self, kind, body, status="approved"):
        with db.conn() as c:
            did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, approved_at, created_at) "
                            "VALUES ('x.com',?,?,?,?,?)", (kind, body.get("title", "t"), status, time.time(), time.time())).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, sources, created_at) VALUES (?,?,'[]',?)",
                      (did, json.dumps(body), time.time()))
        return did

    def test_faq_alone_keeps_original_description(self):
        self._draft("faq", dict(faqs=[dict(question="Cotton?", answer="Yes.")], product=dict(handle="hat")))
        self._draft("faq", dict(faqs=[dict(question="Size?", answer="One.")], product=dict(handle="cap")), status="draft")
        data, ids, counts = content_export.build("x.com")
        z = zipfile.ZipFile(io.BytesIO(data))
        rows = list(csv.reader(io.StringIO(z.read("products.csv").decode())))
        self.assertEqual(rows[0][:5], ["Handle", "Title", "Body (HTML)", "Option1 Name", "Option1 Value"])
        self.assertEqual(len(rows), 3)                  # the hat's two sizes; the unapproved draft is left out
        handle, title, body = rows[1][:3]
        self.assertEqual(rows[1][3:5], ["Size", "S"])
        self.assertEqual(rows[2][:5], ["hat", "", "", "", "L"])
        self.assertEqual((handle, title), ("hat", "Hat"))
        self.assertTrue(body.startswith('<p class="x">Original <b>hat</b> copy.</p>'))
        self.assertIn("Cotton?", body)
        self.assertIn('"@type": "FAQPage"', body)
        self.assertIn("Overwrite products with matching handles", z.read("README.txt").decode())

    def test_fix_and_faq_merge_and_pages_export(self):
        self._draft("product_fix", dict(title="Hat - Cotton Cap", description_html="<p>New copy.</p>",
                                        spec_table=[dict(label="Material", value="Cotton")], product=dict(handle="hat")))
        self._draft("faq", dict(faqs=[dict(question="Cotton?", answer="Yes.")], product=dict(handle="hat")))
        self._draft("guide", dict(title="How to choose a cap", intro="Intro.", sections=[], picks=[], products=[]))
        data, ids, counts = content_export.build("x.com")
        self.assertEqual(counts, dict(products=1, pages=1, drafts=3, skipped=0))
        z = zipfile.ZipFile(io.BytesIO(data))
        handle, title, body = list(csv.reader(io.StringIO(z.read("products.csv").decode())))[1][:3]
        self.assertNotIn("cr-spec", body)
        self.assertEqual(title, "Hat - Cotton Cap")
        self.assertTrue(body.startswith("<p>New copy.</p>"))
        self.assertIn("Cotton", body)
        self.assertIn("Cotton?", body)
        self.assertNotIn("Original", body)
        self.assertIn("pages/how-to-choose-a-cap.html", z.namelist())

    def test_download_marks_exported_and_gaps_never_export(self):
        self._draft("faq", dict(faqs=[dict(question="Q", answer="[ask merchant: Size?]")], product=dict(handle="hat")))
        self.assertEqual(content_export.build("x.com")[0], None)
        self._draft("faq", dict(faqs=[dict(question="Q", answer="Yes.")], product=dict(handle="hat")))
        self.assertIn("Download for Shopify", content_export.bar("x.com"))
        code, data, name = content_agent.export({"d": "x.com"})
        self.assertEqual(code, 200)
        self.assertTrue(name.endswith(".zip"))
        self.assertEqual(content_agent.export({"d": "x.com"})[0], 303)     # nothing new left
        self.assertIn("Download again", content_export.bar("x.com"))
        self.assertEqual(content_agent.export({"d": "x.com", "all": "1"})[0], 200)

    def test_product_whose_options_cant_be_read_is_left_out_and_named(self):
        self._draft("faq", dict(faqs=[dict(question="Q", answer="Yes.")], product=dict(handle="cap")))
        data, ids, counts = content_export.build("x.com")
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertNotIn("products.csv", z.namelist())
        self.assertIn("Not included: cap", z.read("README.txt").decode())
        self.assertEqual(ids, [])                                       # stays waiting, offered again next time


if __name__ == "__main__":
    unittest.main()
