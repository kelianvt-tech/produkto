"""Comparison arithmetic and saved onboarding choices, with no live AI calls."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import config
import db
import evidence
import competitor_comparison as compare
import competitor_setup as setup


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.temp.name, 'test.db')
        db.init()
        db.write("INSERT INTO stores(domain,brand_name) VALUES('own.test','Own')")
        for i in range(1,7):
            db.write("INSERT INTO products(id,store_domain,title,raw_json) VALUES(?,'own.test',?,'{}')", (i, 'Own '+str(i)))
        self.selection = dict(brand='Rival', pairs=[dict(own_id=i,title='Product '+str(i),url='https://rival.test/products/'+str(i)) for i in range(1,7)])
        self.p = dict(_ps=dict(prompts=['Q','Unrelated'],relevance=[[1,2],[99]]))

    def tearDown(self):
        config.DB_PATH = self.old
        self.temp.cleanup()
        evidence.clear_cache()

    def test_shared_answers_duplicate_mentions_and_denominator(self):
        answers = [dict(id=1,prompt='Q'),dict(id=2,prompt='Q'),dict(id=3,prompt='Unrelated')]
        def mention(aid,pid=None,rank=1,brand='Rival',url='https://rival.test/products/1'):
            return dict(answer_id=aid,matched_product_id=pid,rank=rank,brand=brand,url=url,product_name='Product 1',is_theirs=bool(pid),is_their_brand=bool(pid))
        mentions = [mention(1,1,2),mention(1,1,3),mention(1,2,4),mention(2),mention(2),mention(3)]
        with patch.object(evidence,'load',return_value=(answers,mentions)):
            result=compare.calculate([1],self.p,self.selection)
        self.assertEqual(result['n'],2)
        self.assertEqual(result['own']['rate'],50)
        self.assertEqual(result['rival']['rate'],50)
        self.assertEqual(result['own']['count'],2)
        self.assertEqual(result['rival']['count'],1)
        self.assertAlmostEqual(result['own']['share'],200/3)
        self.assertEqual(result['own']['avg'],2)

    def test_empty_period_is_not_zero(self):
        with patch.object(evidence,'load',return_value=([],[])):
            result=compare.calculate([],self.p,self.selection)
        self.assertIsNone(result['own']['rate'])
        self.assertIsNone(result['own']['share'])

    def test_other_brand_and_ambiguous_names_do_not_match(self):
        self.assertIsNone(compare.competitor_match(dict(brand='Wrong',product_name='Product 1',url=''),self.selection))
        self.assertIsNone(compare.competitor_match(dict(brand='Rival',product_name='Product',url=''),self.selection))
        self.assertEqual(compare.competitor_match(dict(brand='Rival',product_name='Product 1',url='https://rival.test/products/1?ref=foo'),self.selection),0)
        self.assertIsNone(compare.competitor_match(dict(brand='',product_name='',url='https://rival.test/products/10'),self.selection))

    def test_save_rejects_duplicate_own_products_and_survives_reload(self):
        setup.save('own.test',[self.selection])
        self.assertEqual(compare.saved('own.test'),[self.selection])
        self.selection['pairs'][1]['own_id']=1
        with self.assertRaises(ValueError):
            setup.save('own.test',[self.selection])
        self.assertEqual(compare.saved('own.test')[0]['pairs'][1]['own_id'],2)

    def test_suggestions_are_grounded_in_selected_products_and_cached(self):
        with patch.object(setup.competitor_finder,'suggest',return_value=([self.selection],[])) as finder:
            result=setup.suggest('own.test',list(range(1,7)))
            self.assertEqual(result['competitors'],[self.selection])
            setup.suggest('own.test',list(range(1,7)))
            self.assertEqual(finder.call_count,1)
            self.assertIn('Own 6',[p['title'] for p in finder.call_args.args[2]])
        self.assertEqual(compare.saved('own.test'),[])

    def test_onboarding_goes_catalog_topics_questions(self):
        # The Competitors step was removed from onboarding on 2026-09-25:
        # without topics the question page sends the merchant to Topics.
        import app
        import catalog_setup
        import topics
        self.assertEqual(catalog_setup.question_page('own.test'), (303, '/topics?d=own.test'))
        topics.save('own.test', ['Serums'], ['Serums'])
        self.assertEqual(catalog_setup.question_page('own.test')[0], 200)
        self.assertEqual(app.ROUTES_GET['/competitors']({'d':'own.test'}), (303, '/topics?d=own.test'))

    def test_scan_is_not_blocked_by_missing_competitor_selection(self):
        """The main measurement - rankings, share of voice, the brand chart -
        compares this catalog against every competitor found in the answers and
        needs nothing configured. Only the saved six-vs-six panel depends on a
        selection, so a missing one must leave that panel empty, not stop the
        scan. (The gate that did stop it was removed on 2026-09-21.)"""
        import app
        self.assertFalse(setup.ready('own.test'))
        with patch.object(app.scan, 'start', return_value='tok') as start:
            result = app.api_scan_start({'d':'own.test'}, {})
        self.assertEqual(json.loads(result[1][1]), {'token':'tok'})
        self.assertEqual(start.call_count, 1)
        # The comparison panel still refuses to invent a competitor.
        self.assertEqual(compare.render({}, {}, {'store_domain':'own.test'}, {}), '')

    def test_manual_setup_without_ai(self):
        with patch.object(setup.llm,'ask_buyer_question',side_effect=AssertionError('AI called')):
            status, payload=setup.api({'d':'own.test'},{'selections':json.dumps([self.selection])})
            self.assertTrue(json.loads(payload[1])['saved'])
            self.assertEqual(status,200)
            status, page=setup.page({'d':'own.test'})
            self.assertEqual(status,200)
            self.assertIn('Rival',page)

if __name__=='__main__':
    unittest.main()
