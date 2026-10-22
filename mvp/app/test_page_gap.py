"""Opportunities step 3 (missing product details): page parsing and gap rules. No network."""
import unittest

import page_gap

PAGE = '''<html><head><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
"name":"Glow Oil","brand":{"@type":"Brand","name":"Rival"},"gtin13":"123",
"aggregateRating":{"@type":"AggregateRating","ratingValue":"4.6","reviewCount":"1,130"},
"offers":{"@type":"Offer","price":"30"}}</script><style>.x{}</style></head>
<body><h1>Glow Oil</h1><p>A non-greasy vitamin C oil that brightens skin.</p><script>var a=1</script></body></html>'''


class PageGapTests(unittest.TestCase):
    def test_parse_reads_text_and_product_data(self):
        f = page_gap.parse(PAGE)
        self.assertIn('non-greasy', f['text'])
        self.assertNotIn('var a', f['text'])
        self.assertTrue(f['rating'] and f['brand'] and f['gtin'] and f['price'])
        self.assertEqual(f['reviews'], 1130)

    def test_clean_drops_tracking_and_images(self):
        self.assertEqual(page_gap.clean('https://x.com/p?utm_source=openai&_pos=1&size=50'), 'https://x.com/p?size=50')
        self.assertEqual(page_gap.clean('https://images.openai.com/thumbnails/abc'), '')
        self.assertEqual(page_gap.clean('https://x.com/a.jpg'), '')

    def test_word_families_match(self):
        self.assertEqual(page_gap.words('cleanse'), page_gap.words('cleanser'))
        self.assertEqual(page_gap.words('moisturiser'), page_gap.words('moisturizer'))

    def test_gap_needs_two_winning_pages(self):
        win = page_gap.parse(PAGE)
        q = 'Which vitamin C face oil absorbs without feeling greasy?'
        own = dict(text='A vitamin C face oil.', rating=False, brand=True, gtin=False, price=True)
        self.assertEqual(page_gap.gaps(q, own['text'], own, [win]), ([], []))
        missing, data = page_gap.gaps(q, own['text'], own, [win, win])
        self.assertIn('greasy', missing)
        self.assertNotIn('oil', missing)          # your page already says it
        self.assertIn('a review rating', data)
        self.assertNotIn('the brand name', data)  # you already publish it


if __name__ == '__main__':
    unittest.main()
