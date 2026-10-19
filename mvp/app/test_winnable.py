"""briefs.winnable: questions where big, established sites dominate the citations are marked harder to win."""
import unittest
from collections import Counter

import briefs


class WinnableTest(unittest.TestCase):
    def test_levels(self):
        cites = {"q1": Counter({"https://www.healthline.com/a": 8, "https://smallbrand.com/b": 2}),
                 "q2": Counter({"https://smallbrand.com/b": 7, "https://www.aad.org/x": 3}),
                 "q3": Counter({"https://nih.gov/x": 5, "https://blog.co/y": 5})}
        self.assertEqual(briefs.winnable(["q1"], cites)["level"], "hard")
        self.assertEqual(briefs.winnable(["q2"], cites)["level"], "winnable")
        self.assertEqual(briefs.winnable(["q3"], cites)["level"], "mixed")       # .gov counts as big
        self.assertEqual(briefs.winnable(["none"], cites)["level"], "")


if __name__ == "__main__":
    unittest.main()
