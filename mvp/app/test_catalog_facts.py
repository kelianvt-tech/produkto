"""Catalog facts: read only what the store states, and say where each fact came from."""
import os
import tempfile
import unittest

import config
import db
import catalog_facts as cf

PRODUCT = {
    "id": 1, "handle": "oak-table", "title": "Oak Table", "vendor": "Acme", "product_type": "Table",
    "tags": ["dining"], "images": [{"src": "https://x/img.jpg"}],
    "body_html": "<p>A solid table.</p><ul><li>Material: solid oak</li><li>Seats - 6 people</li></ul>",
    "options": [{"name": "Size", "values": ["180cm", "220cm"]}],
    "variants": [{"title": "180cm", "price": "900.00", "sku": "T1", "barcode": "", "grams": 0},
                 {"title": "220cm", "price": "1100.00", "sku": "T2", "barcode": "0123456789012", "grams": 0}],
}
PAGE = """<html><head><script type="application/ld+json">{"@type":"Product","brand":{"name":"Acme"},
"gtin13":"0123456789012","aggregateRating":{"ratingValue":"4.6","reviewCount":"31"},
"offers":{"availability":"https://schema.org/InStock"},
"additionalProperty":[{"name":"Finish","value":"Oiled"}]}</script></head><body>Hello</body></html>"""


class CatalogFactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        db.init()

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_description_specs_are_read(self):
        lines = cf.text_lines(PRODUCT["body_html"])
        self.assertEqual(lines[0], "A solid table.")
        self.assertIn(("Material", "solid oak"), cf.spec_lines(lines))
        self.assertIn(("Seats", "6 people"), cf.spec_lines(lines))

    def test_page_markup(self):
        p = cf.page_data(PAGE)
        self.assertEqual((p["brand"], p["gtin"], p["rating"], p["reviews"], p["availability"]),
                         ("Acme", "0123456789012", "4.6", 31, "InStock"))
        self.assertEqual(p["properties"], [("Finish", "Oiled")])

    def test_record_sources_and_no_invention(self):
        rec = cf.record(PRODUCT, "x.com", "USD", "Dining tables", cf.page_data(PAGE))
        facts = {(f["label"], f["value"]): f["source"] for f in rec["facts"]}
        self.assertEqual(facts[("Size", "180cm, 220cm")], "catalog")
        self.assertEqual(facts[("Price", "USD 900.00-1100.00")], "catalog")
        self.assertEqual(facts[("Finish", "Oiled")], "page")
        self.assertEqual(facts[("Review count", "31")], "page")
        self.assertNotIn("Weight", [f["label"] for f in rec["facts"]])  # zero grams is not a fact
        self.assertEqual(rec["url"], "https://x.com/products/oak-table")

    def test_get_empty_until_built(self):
        self.assertEqual(cf.get("x.com"), [])
        self.assertTrue(cf.stale("x.com"))


if __name__ == "__main__":
    unittest.main()
