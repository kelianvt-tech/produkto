"""Check the setup handoff without external requests or real scan data."""
import os
import tempfile
import unittest
from unittest.mock import patch

import app
import config
import db


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, 'setup.db')
        db.init()
        # The brand page auto-fills through Apify; never buy answers in tests.
        self.fill = patch('brand_profile.generate', side_effect=RuntimeError('no network in tests'))
        self.fill.start()
        self.addCleanup(self.fill.stop)
        db.write("INSERT INTO stores(domain,brand,products,variants,country,currency) VALUES('test.invalid','Test',1,1,'GB','GBP')")
        db.write("INSERT INTO products(id,store_domain,title,vendor,image,url,price) VALUES(1,'test.invalid','Test Cleanser','Test','','https://test.invalid/product','20')")

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_brand_saved_before_product_and_questions(self):
        result = app.act_brand({'d':'test.invalid'}, {'name':'New name','aliases':'New, Test','country':'ES','currency':'EUR'})
        self.assertEqual(result, (303,'/store?d=test.invalid'))
        b = db.brand('test.invalid')
        self.assertEqual((b['brand_name'], b['country'], b['currency']), ('New name','ES','EUR'))
        self.assertEqual(b['aliases'], ['New','Test'])
        with patch('app.questions.generate_clusters', return_value=[dict(q='Under €30?',tag='budget',cluster='Budget',products=[1])]) as gen:
            app.api_questions({'d':'test.invalid'}, {})
            self.assertEqual(gen.call_args.args[1]['currency'], 'EUR')

    def test_invalid_brand_does_not_advance(self):
        self.assertEqual(app.act_brand({'d':'test.invalid'}, {'name':''})[0],200)
        self.assertEqual(db.brand('test.invalid')['brand_name'],'Test')

    def test_returning_store_keeps_aliases_and_location(self):
        db.save_brand('test.invalid','Test',['Alias'],'ES','EUR')
        with patch('app.catalog.fetch', return_value=([],{'products':1,'variants':1,'vendor':'Test','country':'GB','currency':'GBP'})):
            self.assertEqual(app.act_store({}, {'domain':'test.invalid','name':'Test'}),(303,'/brand?d=test.invalid'))
        b=db.brand('test.invalid')
        self.assertEqual((b['aliases'],b['country'],b['currency']),(['Alias'],'ES','EUR'))

    def test_existing_frozen_questions_stay_locked(self):
        ps=db.save_prompts('test.invalid',['Original question'],['best'],['Cleanser'],[[1]])
        db.freeze(ps['id'])
        app.api_questions({'d':'test.invalid'}, {'questions':'[{"q":"Changed","tag":"best"}]'})
        self.assertEqual(db.get_prompt_set('test.invalid')['prompts'],['Original question'])
        with patch('competitor_setup.ready', return_value=True):
            self.assertIn('These are locked now',app.view_product({'d':'test.invalid'})[1])
