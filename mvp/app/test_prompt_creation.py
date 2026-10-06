import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import config
import db
import dashboard
import prompt_creation as pc
import scan


class PromptCreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, 'test.db')
        # Exercise migration from the production unique-domain schema.
        with sqlite3.connect(config.DB_PATH) as c:
            c.executescript(db.SCHEMA.replace('store_domain TEXT,','store_domain TEXT UNIQUE,',1))
        db.init()
        db.write("INSERT INTO stores(domain,brand) VALUES('shop.test','Shop')")
        db.write("INSERT INTO products(id,store_domain,title,vendor,raw_json,price) VALUES(1,'shop.test','Cleanser','Shop','{}','20')")
        self.ps = db.save_prompts('shop.test',['Best gentle cleanser?'],['best'],['Cleansers'],[[1]])
        db.freeze(self.ps['id'])
        db.write("INSERT INTO scans(id,token,prompt_set_id,run_at,status) VALUES(1,'test',?,?,'done')", (self.ps['id'],__import__('time').time()))

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def item(self,q='Is Shop Cleanser suitable for me?'):
        return dict(q=q,type='product',products=[1])

    def api(self,**form):
        return json.loads(pc.api({'token':'test'},form)[1][1])

    def test_version_preserves_baseline_and_scan_context(self):
        before = dict(db.one('SELECT * FROM prompt_sets WHERE id=?',(self.ps['id'],)))
        new = pc.save('shop.test',self.ps['id'],[self.item()])
        self.assertNotEqual(new,self.ps['id'])
        self.assertEqual(before,dict(db.one('SELECT * FROM prompt_sets WHERE id=?',(self.ps['id'],))))
        self.assertEqual(len(db.get_prompt_set('shop.test')['prompts']),2)
        self.assertEqual(scan._context('shop.test',1)[0]['prompts'],['Best gentle cleanser?'])
        rendered=dashboard.questions('test',{})
        self.assertIn('Ready for the next scan',rendered)
        self.assertIn(self.item()['q'],rendered)
        self.assertIn('Product-specific',rendered)

    def test_duplicate_invalid_products_and_stale_saves(self):
        for item in [self.item('Best gentle cleanser?'),dict(self.item(),products=[99]),dict(self.item(),products=[]),dict(self.item(),type='bogus')]:
            with self.assertRaises(ValueError):
                pc.save('shop.test',self.ps['id'],[item])
        pc.save('shop.test',self.ps['id'],[self.item()])
        with self.assertRaises(ValueError):
            pc.save('shop.test',self.ps['id'],[self.item('Another prompt?')])

    def test_running_scan_blocks_changes(self):
        db.write("UPDATE scans SET status='running' WHERE id=1")
        with self.assertRaises(ValueError):
            pc.save('shop.test',self.ps['id'],[self.item()])

    def test_upload_and_generation_are_review_only(self):
        out=self.api(action='upload',text='prompt,notes\n"A cleanser, for dry skin?",test',format='csv',type='organic',products='[1]')
        self.assertEqual(out['items'][0]['q'],'A cleanser, for dry skin?')
        with patch.object(pc.llm,'json_call',return_value={'prompts':[dict(q='What cleanser suits dry skin?',products=[1])]}) as generate:
            out=self.api(action='keywords',keywords='dry skin',type='organic',products='[1]')
            self.assertEqual(len(out['items']),1)
            self.assertIn('Cleanser',generate.call_args[0][1])
        self.assertEqual(db.get_prompt_set('shop.test')['id'],self.ps['id'])
        self.assertIn('error',self.api(action='upload',text='',format='txt',type='organic',products='[1]'))


if __name__ == '__main__':
    unittest.main()
