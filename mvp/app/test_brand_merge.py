"""evidence.merge_brands: one competitor written several ways counts as one brand."""
import unittest

import evidence


def merged(*names):
    rows = [dict(brand=n) for n in names]
    evidence.merge_brands(rows)
    return [r['brand'] for r in rows]


class MergeBrandsTest(unittest.TestCase):
    def test_longer_name_folds_into_shorter(self):
        self.assertEqual(merged('adidas', 'adidas', 'adidas Originals'), ['adidas'] * 3)
        self.assertEqual(merged('e.l.f.', 'e.l.f. Skin'), ['e.l.f.', 'e.l.f.'])

    def test_whole_words_only(self):
        self.assertEqual(merged('Dove', 'Dovetail'), ['Dove', 'Dovetail'])
        self.assertEqual(merged('Dr H', 'Dr. Hauschka'), ['Dr H', 'Dr. Hauschka'])

    def test_filler_words_are_never_a_brand(self):
        self.assertEqual(merged('The', 'The Ordinary'), ['The', 'The Ordinary'])

    def test_without_the_short_name_nothing_changes(self):
        self.assertEqual(merged('adidas Originals', 'Nike'), ['adidas Originals', 'Nike'])


if __name__ == '__main__':
    unittest.main()
