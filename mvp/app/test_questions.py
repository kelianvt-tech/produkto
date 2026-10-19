"""questions._drop_page_copies: narrow questions that copy their product page are dropped, broad ones never,
and never below the coverage floor."""
import json
import unittest

import questions


class PageCopyTest(unittest.TestCase):
    def test_drop(self):
        prods = [dict(title="Helsinki Moisturiser", raw_json=json.dumps(dict(
            body_html="<p>Lightweight moisturiser with snow mushroom, squalane and niacinamide for deep hydration.</p>")))]
        items = [dict(q="Which lightweight moisturiser contains snow mushroom, squalane and niacinamide for deep hydration?",
                      tag="specific"),
                 dict(q="Which moisturiser is best for deep hydration without feeling heavy?", tag="best"),
                 dict(q="Best moisturiser with squalane for dry skin under £40", tag="specific")]
        self.assertEqual([i["tag"] for i in questions._drop_page_copies(items, prods, 0)], ["best", "specific"])
        self.assertEqual(len(questions._drop_page_copies(items, prods, 3)), 3)


if __name__ == "__main__":
    unittest.main()
