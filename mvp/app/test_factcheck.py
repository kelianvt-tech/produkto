"""Fact check: unstated numbers and claims become questions for the merchant."""
import unittest
from unittest import mock

import factcheck

PRODUCT = dict(title="Oil", facts=[dict(label="Size", value="30 ml"), dict(label="Oil", value="Jojoba")],
               description=["A light face oil with jojoba."])


class FactCheckTest(unittest.TestCase):
    def test_unstated_number_is_replaced_without_ai(self):
        res = dict(description_html="<p>A light face oil. Comes in 30 ml. Lasts 90 days.</p>", open_questions=[])
        rep = factcheck.check(res, "product_fix", [PRODUCT], ai=False)
        self.assertIn("Comes in 30 ml.", res["description_html"])
        self.assertNotIn("Lasts 90 days", res["description_html"].split("[ask")[0])
        self.assertIn("[ask merchant: confirm &quot;90&quot;", res["description_html"].replace('"', "&quot;"))
        self.assertTrue(res["description_html"].startswith("<p>") and res["description_html"].endswith("</p>"))
        self.assertEqual(rep["numbers"][0]["number"], "90")
        self.assertEqual(len(res["open_questions"]), 1)

    def test_ai_flags_unsupported_claims_and_general_advice_outside_guides(self):
        res = dict(faqs=[dict(question="q", answer="It contains jojoba. It is safe in pregnancy. Oils suit dry skin.",
                              facts_used=[])], open_questions=[])
        reply = dict(verdicts=[dict(n=1, verdict="stated", ask_merchant=""),
                               dict(n=2, verdict="unsupported", ask_merchant="Is it safe in pregnancy?"),
                               dict(n=3, verdict="general", ask_merchant="")])
        with mock.patch("llm.json_call", return_value=reply):
            factcheck.check(res, "faq", [PRODUCT])
        a = res["faqs"][0]["answer"]
        self.assertTrue(a.startswith("It contains jojoba. [ask merchant: Is it safe in pregnancy?]"))
        self.assertTrue(a.endswith("[ask merchant: is this true? \"Oils suit dry skin.\"]"))

    def test_general_advice_is_kept_in_guides(self):
        res = dict(intro="Oils suit dry skin.", sections=[], picks=[], open_questions=[])
        with mock.patch("llm.json_call", return_value=dict(verdicts=[dict(n=1, verdict="general", ask_merchant="")])):
            factcheck.check(res, "guide", [PRODUCT])
        self.assertEqual(res["intro"], "Oils suit dry skin.")

    def test_ai_failure_keeps_number_check(self):
        import llm
        res = dict(intro="Has 5 oils.", summary=[], open_questions=[])
        with mock.patch("llm.json_call", side_effect=llm.LLMError("down")):
            rep = factcheck.check(res, "comparison", [PRODUCT])
        self.assertFalse(rep["ai_checked"])
        self.assertTrue(res["intro"].startswith("[ask merchant"))

    def test_lists_short_answers_and_questions_are_not_flagged(self):
        self.assertEqual(factcheck.sentences("No. It is light. Is it greasy? Yes."), ["No. It is light.", "Is it greasy? Yes."])
        self.assertEqual(factcheck._numbers_ok("2. Calm Face Oil", "nothing")[0], True)
        res = dict(description_html="<p>Use in order: 1. Cleanser. 2. Calm Face Oil.</p><p>Looking for a light oil?</p>",
                   open_questions=[])
        rep = factcheck.check(res, "product_fix", [PRODUCT], ai=False)
        self.assertEqual(rep["numbers"], [])
        self.assertNotIn("[ask", res["description_html"])

    def test_voice_lines_are_allowed(self):
        res = dict(faqs=[dict(question="q", answer="Considered enough to earn its place.", facts_used=[])], open_questions=[])
        with mock.patch("llm.json_call", return_value=dict(verdicts=[dict(n=1, verdict="voice", ask_merchant="")])):
            factcheck.check(res, "faq", [PRODUCT])
        self.assertEqual(res["faqs"][0]["answer"], "Considered enough to earn its place.")


if __name__ == "__main__":
    unittest.main()
