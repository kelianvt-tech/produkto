"""Self-review: grades a draft, flags weak ones, never blocks or rewrites."""
import unittest
from unittest import mock

import selfreview

BRIEF = dict(store="x.com", questions=[dict(question="Is the cap cotton?")])
FIX = dict(title="Harbour Cap", description_html="<p>A cotton cap.</p>", spec_table=[dict(label="Material", value="Cotton")])


class SelfReviewTest(unittest.TestCase):
    def test_grades_and_flags(self):
        reply = dict(answers=5, readable=2, voice=4, issues=[dict(problem="Choppy", fix="Join the sentences")])
        with mock.patch("llm.json_call", return_value=reply) as call, \
                mock.patch("content_setup.voice_text", return_value="- Short sentences"):
            rev = selfreview.review(FIX, "product_fix", BRIEF)
        text = call.call_args[0][1]
        self.assertIn("Is the cap cotton?", text)
        self.assertIn("Material: Cotton", text)
        self.assertIn("Short sentences", text)
        self.assertFalse(rev["passed"])
        self.assertEqual(selfreview.weakest(rev), "Reads well 2/5")

    def test_pass_and_failure(self):
        with mock.patch("llm.json_call", return_value=dict(answers=4, readable=5, voice=9, issues=[])):
            rev = selfreview.review(FIX, "product_fix", BRIEF)
        self.assertEqual((rev["passed"], rev["scores"]["voice"], selfreview.weakest(rev)), (True, 5, ""))
        with mock.patch("llm.json_call", side_effect=RuntimeError("down")):
            self.assertIsNone(selfreview.review(FIX, "product_fix", BRIEF))      # never blocks a draft
        with mock.patch("llm.json_call", return_value=dict(title="not a review")):
            self.assertIsNone(selfreview.review(FIX, "product_fix", BRIEF))

    def test_faq_and_guide_text(self):
        self.assertIn("Q: Is it cotton?\nA: Yes.", selfreview.draft_text(
            dict(faqs=[dict(question="Is it cotton?", answer="Yes.")]), "faq"))
        self.assertEqual(selfreview.draft_text(dict(title="How to choose", html="<p>Look at fit.</p><script>{}</script>"),
                                               "guide"), "How to choose\n\nLook at fit.")


if __name__ == "__main__":
    unittest.main()
