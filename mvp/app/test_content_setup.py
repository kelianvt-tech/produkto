"""Agent setup: first visit shows it; voice and scope are enforced, not just stored."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import config
import content_agent
import content_setup
import db

REC = dict(handle="hat", title="Hat", url="u", image="", facts=[dict(label="Material", value="Cotton", source="catalog")],
           description=["A soft cotton cap, made in Leeds."])


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH, config.SHOW_CONTENT_AGENT
        config.DB_PATH = os.path.join(self.tmp.name, "t.db")
        assert not config.DB_PATH.endswith("produkto.db")
        config.SHOW_CONTENT_AGENT = True
        db.init()
        content_agent.init()

    def tearDown(self):
        config.DB_PATH, config.SHOW_CONTENT_AGENT = self.old
        self.tmp.cleanup()

    def test_first_visit_opens_setup_and_draft_button_waits_for_it(self):
        body = content_agent.page({"d": "x.com"})[1]
        self.assertIn("Read my product pages", body)
        code, where = content_agent.act({}, {"d": "x.com", "action": "draft", "kind": "missing", "key": "q"})
        self.assertEqual((code, "view=setup" in where), (303, True))

    def test_voice_then_scope(self):
        reply = dict(traits=["Short sentences", "British spelling"], sample="A soft cotton cap.")
        with mock.patch("catalog_facts.get", return_value=[REC]), mock.patch("llm.json_call", return_value=reply) as call, \
                mock.patch("content_setup.brand_pages", return_value=[]), mock.patch("content_setup.store_pages", return_value=[]):
            content_agent.act({}, {"d": "x.com", "action": "voice"})
            content_agent.act({}, {"d": "x.com", "action": "voice", "adjust": "less poetic"})
            self.assertIn("less poetic", call.call_args[0][1])                 # adjustment reaches the model
            self.assertIn("British spelling", content_agent.page({"d": "x.com"})[1])
            self.assertEqual(content_setup.voice_text("x.com"), "")            # not confirmed yet
            content_agent.act({}, {"d": "x.com", "action": "voice_ok"})
            self.assertIn("Fill in from my pages", content_agent.page({"d": "x.com"})[1])
            prefill = dict(customers="Busy people", story="Simple skincare", different=["Made in Leeds"], proof=[],
                           policies=[], objections=["Is it for oily skin?"], naming="", always_words=["considered"],
                           never_words=["amazing"], no_claims=["treats acne"], never_name=["x"], love_page="x",
                           length="Medium", format="A mix", spelling="British")
            call.return_value = prefill
            content_agent.act({}, {"d": "x.com", "action": "brief_prefill"})
            page = content_agent.page({"d": "x.com"})[1]
            self.assertIn("Busy people", page)
            self.assertIn("may state these as facts", page)
            content_agent.act({}, {"d": "x.com", "action": "brief", "b.customers": "Busy parents",
                                   "b.different": "Made in Leeds\n- Vegan", "b.never_words": "amazing\nmiracle",
                                   "b.no_claims": "treats acne", "b.spelling": "British", "b.length": "Nonsense"})
            self.assertIn("Products to leave alone", content_agent.page({"d": "x.com"})[1])
            content_agent.act({}, {"d": "x.com", "action": "scope", "allow.faqs": "1", "leave.hat": "1"})
            self.assertFalse(content_setup.done("x.com"))
            self.assertIn("Your time zone", content_agent.page({"d": "x.com"})[1])
            content_agent.act({}, {"d": "x.com", "action": "schedule", "tz": "America/Chicago", "pace": "2",
                                   "hour": "10", "day.1": "1", "day.3": "1"})
            call.return_value = dict(products=[dict(handle="hat", missing=[
                dict(label="Sizes", question="Which sizes?", suggestion=""),
                dict(label="Care", question="How do I wash it?", suggestion="Hand wash")])])
            content_agent.act({}, {"d": "x.com", "action": "missing"})
            page = content_agent.page({"d": "x.com"})[1]
            self.assertIn("Which sizes?", page)
            self.assertIn('value="Hand wash"', page)                      # suggestion shown for checking
            with mock.patch("content_setup.plan_first_weeks") as plan:
                code, where = content_agent.act({}, {"d": "x.com", "action": "facts", "m.hat.Sizes": "One size",
                                                     "m.hat.Care": ""})
                plan.assert_called_once_with("x.com")
            self.assertIn("view=calendar", where)
        self.assertTrue(content_setup.done("x.com"))
        self.assertEqual(content_setup.product_facts("x.com", "hat"), [dict(label="Sizes", value="One size", source="merchant")])
        self.assertEqual(content_setup.schedule("x.com"), ([1, 3], 2, 10))
        import storetime
        self.assertEqual(storetime.zone_name("x.com"), "America/Chicago")
        self.assertIn("British spelling", content_setup.voice_text("x.com"))
        self.assertIn("less poetic", content_setup.voice_text("x.com"))
        self.assertEqual(content_setup.allowed_types("x.com"), {"faq"})
        self.assertEqual(content_setup.get("x.com")["leave_alone"], ["hat"])
        brief = content_setup.get("x.com")["brief"]
        self.assertEqual(brief["different"], ["Made in Leeds", "Vegan"])
        self.assertEqual(brief["length"], "")                               # not one of the choices
        self.assertIn("Busy parents", content_setup.voice_text("x.com"))
        self.assertNotIn("Made in Leeds", content_setup.voice_text("x.com"))  # facts go in as facts, not style
        self.assertEqual([f["value"] for f in content_setup.brand_facts("x.com")], ["Made in Leeds", "Vegan"])

    def test_brand_facts_and_banned_words_reach_the_fact_check(self):
        import drafts
        import factcheck
        content_setup.put("x.com", dict(brief=dict(different=["Made in Leeds"], never_words=["amazing"],
                                                   no_claims=["treats acne"], never_name=["Rival"])))
        brief = dict(store="x.com", questions=[], competitors=[], products=[dict(REC, facts_ready=True)])
        reply = dict(title="Hat", title_reason="", spec_table=[], open_questions=[], changes=[],
                     description_html="<p>Made in Leeds. An amazing cap. Better than Rival.</p>")
        real = factcheck.check
        with mock.patch("llm.json_call", return_value=reply), \
                mock.patch("factcheck.check", lambda *a, **k: real(*a, **dict(k, ai=False))):
            res = drafts.product_fix(brief)
        html = res["description_html"]
        self.assertIn("Made in Leeds.", html)                              # merchant-stated fact kept
        self.assertNotIn("An amazing cap", html.split("[ask")[0])
        self.assertEqual([b["word"] for b in res["fact_check"]["banned"]], ["amazing", "rival"])

    def test_draft_respects_scope(self):
        content_setup.put("x.com", dict(part1_done_at=1, allowed=["comparisons"], leave_alone=["hat"]))
        brief = dict(store="x.com", opportunity=dict(type="missing", key="q"), competitors=[],
                     questions=[dict(question="Is it cotton?", answers=1, own=0, theirs=1)],
                     products=[dict(REC, facts_ready=True)])
        with mock.patch("catalog_facts.get", return_value=[REC]), mock.patch("briefs.build", return_value=brief):
            did, err = content_agent.draft_for("x.com", "missing", "q")
        self.assertIsNone(did)
        self.assertIn("leave the products", err)
        content_setup.put("x.com", dict(part1_done_at=1, allowed=["comparisons"], leave_alone=[]))
        with mock.patch("catalog_facts.get", return_value=[REC]), \
                mock.patch("briefs.build", return_value=dict(brief, products=[dict(REC, facts_ready=True)])):
            did, err = content_agent.draft_for("x.com", "missing", "q")
        self.assertIn("switched off in Settings", err)

    def test_voice_reads_about_page_and_keeps_only_real_example_lines(self):
        about = [("About page", "We started in a Leeds kitchen. Small batches, nothing you don't need, ever.")]
        reply = dict(traits=["Short sentences"], sample="A soft cotton cap.",
                     examples=["Small batches, nothing you don\u2019t need, ever.", "We craft luxurious, timeless pieces."])
        with mock.patch("catalog_facts.get", return_value=[REC, dict(REC, handle="hat-2")]), \
                mock.patch("content_setup.brand_pages", return_value=about), \
                mock.patch("llm.json_call", return_value=reply) as call:
            v = content_setup.make_voice("x.com")
        self.assertIn("Leeds kitchen", call.call_args[0][1])                    # About page reaches the model
        self.assertEqual(call.call_args[0][1].count("A soft cotton cap"), 2)    # duplicate description read once (+ sample)
        self.assertEqual(v["examples"], ["Small batches, nothing you don\u2019t need, ever."])  # invented line dropped
        self.assertIn("About page", v["pages"])
        content_setup.put("x.com", dict(voice=dict(v, confirmed=True)))
        self.assertIn("nothing you don", content_setup.voice_text("x.com"))

    def test_fix_keeps_parts_not_allowed(self):
        res = dict(title="New title", spec_table=[dict(label="a", value="b")], description_html="<p>New.</p>",
                   current=dict(title="Hat", description=["Old."]))
        content_agent._limit_fix(res, {"descriptions"})
        self.assertEqual((res["title"], res["spec_table"], res["description_html"]), ("Hat", [], "<p>New.</p>"))

    def test_confirmed_voice_reaches_drafts(self):
        import drafts
        content_setup.put("x.com", dict(voice=dict(traits=["Warm, short"], confirmed=True)))
        brief = dict(store="x.com", questions=[], competitors=[])
        self.assertIn("Warm, short", drafts._input(brief, dict(REC, facts_ready=True)))

    def test_slots_follow_days_and_pace(self):
        import content_calendar
        import storetime
        content_setup.put("x.com", dict(days=[0, 2, 4], pace=2, hour=10, timezone="America/New_York"))
        storetime.forget("x.com")
        tz = storetime.zone("x.com")
        slots = content_calendar.free_slots("x.com", weeks=3)
        days = [storetime.date_of(t, tz) for t in slots]
        self.assertTrue(all(d.weekday() in (0, 2, 4) for d in days))
        weeks = {}
        for d in days:
            weeks[d.isocalendar()[1]] = weeks.get(d.isocalendar()[1], 0) + 1
        self.assertTrue(all(n <= 2 for n in weeks.values()))
        self.assertEqual(storetime.label(slots[0], tz, "%H:%M"), "10:00")
        storetime.forget("x.com")


if __name__ == "__main__":
    unittest.main()
