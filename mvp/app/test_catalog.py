"""Catalog refactor regression checks; all provider calls are stubbed."""
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
import apify_answers
import app
import citation_panel
import config
import dashboard
import db
import evidence
import insight_panels
import llm
import scan
import scoring


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=config.DB_PATH
        config.DB_PATH=os.path.join(self.tmp.name,'test.db')
        db.init()
        db.write("INSERT INTO stores(domain,brand,brand_name,currency,country) VALUES('example.invalid','Example','Example','GBP','GB')")
        for pid,title,kind in [(1,'Daily Cleanser','Cleanser'),(2,'Soft Cleanser','Cleanser'),(3,'Vitamin C Serum','Serum'),(4,'Night Oil','Oil')]:
            db.write('INSERT INTO products(id,store_domain,title,handle,vendor,url,image,raw_json) VALUES(?,?,?,?,?,?,?,?)',
                     (pid,'example.invalid',title,title.lower().replace(' ','-'),'Example','https://example.invalid/products/'+title.lower().replace(' ','-'),'',json.dumps({'product_type':kind})))
        self.ps=db.save_prompts('example.invalid',['Best cleansers?','Best vitamin C serum?'],['best','best'],['Cleansers','Vitamin C'],[[1,2],[3]])
        db.freeze(self.ps['id'])
        self.sid=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('catalog',?,'done',?,4)",(self.ps['id'],time.time()))
        self.aids=[]
        # run_n is distinct per (scan, question) - that is what _run produces,
        # and two answers sharing one means a crash duplicated them.
        for q,n in [('Best cleansers?',1),('Best cleansers?',2),('Best vitamin C serum?',1),('Best vitamin C serum?',2)]:
            aid=db.write("INSERT INTO answers(scan_id,prompt,raw_text,citations,created_at,run_n) VALUES(?,?,'Saved evidence','[]',?,?)",(self.sid,q,time.time(),n))
            db.write("INSERT INTO answer_processing(answer_id,status) VALUES(?,'done')",(aid,))
            self.aids.append(aid)
        self.mention(self.aids[0],1,2)
        self.mention(self.aids[0],2,3)
        self.mention(self.aids[1],None,1)
        self.mention(self.aids[2],None,1)
        self.mention(self.aids[3],None,1)
        scoring.score(self.sid)

    def tearDown(self):
        config.DB_PATH=self.old
        self.tmp.cleanup()

    def mention(self,aid,pid,rank):
        db.write('INSERT INTO mentions(answer_id,product_name,brand,url,rank,is_theirs,is_their_brand,matched_product_id,match_score) VALUES(?,?,?,?,?,?,?,?,?)',
                 (aid,'Daily Cleanser' if pid else 'Other cleanser','Example' if pid else 'Rival','https://example.invalid' if pid else '',rank,int(pid is not None),int(pid is not None),pid,1 if pid else 0))

    def test_catalog_union_and_relevant_product_denominator(self):
        self.assertEqual(db.one('SELECT appearance_rate FROM scores WHERE scan_id=?',(self.sid,))[0],25)
        rates={r['product_id']:r for r in db.all_('SELECT * FROM product_scores')}
        self.assertEqual(rates[1]['appearance_rate'],50)
        self.assertEqual(rates[2]['appearance_rate'],50)
        self.assertEqual(rates[3]['appearance_rate'],0)
        self.assertIsNone(rates[3]['avg_rank'])
        self.assertIsNone(rates[4]['appearance_rate'])
        self.assertEqual(json.loads(rates[4]['detail'])['coverage'],'Not covered')
        self.assertEqual(json.loads(rates[1]['detail'])['noise_points'],150)
        self.assertEqual(json.loads(db.one('SELECT detail FROM scores')[0])['noise_points'],75)

    def test_questions_scope_and_snapshot_freeze(self):
        before=db.get_prompt_set('example.invalid')
        db.save_prompts('example.invalid',['Changed'],relevance=[[4]])
        db.save_scope('example.invalid',['Cleanser'])
        after=db.get_prompt_set('example.invalid')
        for key in ('prompts','relevance','catalog_snapshot','product_ids','excluded_types'):
            self.assertEqual(before[key],after[key])
        db.write("UPDATE products SET title='Changed name' WHERE id=1")
        self.assertEqual(evidence.product_context(after,1)['title'],'Daily Cleanser')

    def test_browsing_never_calls_a_model_and_preserves_scope(self):
        with patch('llm._post',side_effect=AssertionError('Browsing must be free')):
            out=app.view_result('catalog',{'product':'1','range':'90','group':'month'})[1]
            self.assertIn('Back to catalog',out)
            self.assertIn('/r/catalog/answers?range=90&amp;group=month&amp;product=1',out)
            self.assertIn('/r/catalog?range=90&amp;group=month',out)
            self.assertNotIn('Vitamin C Serum</h1>',out)
            self.assertEqual(dashboard.answers('catalog',{'product':'1'}).count('id="answer-'),2)
            self.assertEqual(dashboard.answers('catalog',{'product':'1','status':'yours'}).count('id="answer-'),1)
            self.assertIn('Your products',app.view_result('catalog',{})[1])
            citation_panel.page('catalog',{'product':'1'})
        self.assertEqual(app.view_result('catalog',{'product':'999'})[0],404)

    def test_other_own_products_are_never_competitors(self):
        p=evidence.product_context(self.ps,1)
        groups=insight_panels.products(self.sid,p)
        self.assertEqual(len([r for r in groups if not r['own']]),1)
        self.assertEqual(next(r for r in groups if r['own'])['rate'],50)

    def test_homepage_not_product_citation_and_period_is_scoped(self):
        # Synthetic fixture creation; production raw answers are never updated.
        db.write('UPDATE answers SET citations=? WHERE id=?',(json.dumps([{'url':'https://example.invalid','title':'Home'},{'url':'https://example.invalid/products/daily-cleanser','title':'Product'}]),self.aids[0]))
        p=evidence.product_context(self.ps,1)
        rows,n=citation_panel.evidence([self.sid],p)
        self.assertEqual(n,2)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['own'])
        self.assertIn('No scans in this period',citation_panel.page('catalog',{'product':'1','range':'custom','from':'2001-01-01','to':'2001-02-01'}))

    def test_extraction_failure_is_not_zero_visibility(self):
        db.write("UPDATE answer_processing SET status='failed' WHERE answer_id IN (?,?)",(self.aids[0],self.aids[1]))
        scoring.score(self.sid)
        self.assertIsNone(db.one('SELECT appearance_rate FROM product_scores WHERE product_id=1')[0])
        self.assertEqual(scan.completion_status(2,4),'failed')
        self.assertEqual(scan.completion_status(3,4),'partial')
        self.assertEqual(scan.completion_status(4,4),'done')

    def test_best_match_and_unicode(self):
        products=[dict(id=1,title='Daily Cleanser Barrier',handle='daily',store_domain='example.invalid'),dict(id=2,title='Daily Cleanser',handle='daily-cleanser',store_domain='example.invalid')]
        self.assertEqual(scan.match_catalog(dict(product_name='Daily Cleanser',brand='Example'),products,{'example'})[0],2)
        self.assertIsNone(scan.match_catalog(dict(product_name='Unrelated',brand='Example'),products,{'example'})[0])
        self.assertIsNone(scan.match_catalog(dict(product_name='',brand='',url='https://example.invalid/products/daily-cleanser-set'),products,{'example'})[0])
        products=[dict(id=3,title='Amalfi Vit-C Face Oil',handle='oil',store_domain='example.invalid')]
        self.assertEqual(scan.match_catalog(dict(product_name='Amalfi Vitamin‑C Face Oil',brand='Example'),products,{'example'})[0],3)

    def test_usage_is_model_specific_and_unknown_cost_is_not_zero(self):
        usage=llm.Usage()
        usage.add(dict(model='gpt-5.6-sol',usage=dict(input_tokens=1000000,input_tokens_details=dict(cached_tokens=100000),output_tokens=1000),output=[{'type':'web_search_call'}]))
        usage.add(dict(model='gpt-5.6-luna',usage=dict(input_tokens=1000,output_tokens=100),output=[]))
        self.assertAlmostEqual(usage.cost_cents(),367.032)
        self.assertEqual(len(usage.as_dict()['by_model']),2)
        usage.add(dict(model='unknown-model',usage=dict(input_tokens=1)))
        self.assertIsNone(usage.cost_cents())

    def test_scan_failure_preserves_raw_answer_and_partial_status(self):
        new=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('run',?,'running',?,4)",(self.ps['id'],time.time()))
        def extract(*args,**kwargs):
            if 'Best vitamin' in args[1]:
                raise llm.LLMError('Extraction failed')
            return {'items':[]}
        with patch.object(config,'ANSWER_SOURCE','openai'),patch.object(config,'RUNS_PER_QUESTION',2),patch.object(config,'PARALLEL_CALLS',1),patch('llm.ask_buyer_question',return_value=('Saved raw',[],'test-model')),patch('llm.json_call',side_effect=extract):
            scan._run(new,'example.invalid',self.ps['prompts'])
        self.assertEqual(db.one('SELECT status FROM scans WHERE id=?',(new,))[0],'failed')
        self.assertEqual(db.one('SELECT COUNT(*) FROM answers WHERE scan_id=?',(new,))[0],4)
        self.assertEqual(db.one("SELECT COUNT(*) FROM answer_processing WHERE status='failed'")[0],2)

    @staticmethod
    def _fake_batch(skip_last=True):
        """Stand-in for Apify: echoes the questions back, one engine at a time."""
        def batch(questions,usage=None,engine=config.DEFAULT_ENGINE,**kwargs):
            asked=questions[:-1] if skip_last else questions
            actor=config.ENGINES[engine]['actor']
            # Curly apostrophes and padding, as Apify echoes them back.
            got={(' '+q.replace("'","’")+' '):('Scraped raw by '+engine,
                 [{'url':'https://x.invalid','title':'x'}],actor) for q in asked}
            if usage is not None:
                usage.add_scraped(len(got),engine)
            return got
        return batch

    def test_scraped_scan_stores_every_answer_once_per_run(self):
        """The Apify path buys in batches; each run must still store one answer
        per question per engine, and a question the scraper skipped must not be
        invented."""
        new=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('scrape',?,'running',?,4)",(self.ps['id'],time.time()))
        prompts=self.ps['prompts']
        with patch.object(config,'ANSWER_SOURCE','apify'),patch.object(config,'RUNS_PER_QUESTION',2),patch.object(config,'PARALLEL_CALLS',1),patch('apify_answers.ask_batch',side_effect=self._fake_batch()),patch('llm.json_call',return_value={'items':[]}):
            scan._run(new,'example.invalid',prompts)
        engines_used=len(config.SCAN_ENGINES)
        stored=db.one('SELECT COUNT(*) FROM answers WHERE scan_id=?',(new,))[0]
        self.assertEqual(stored,(len(prompts)-1)*2*engines_used)   # the skipped one is absent
        self.assertEqual(db.one('SELECT COUNT(DISTINCT run_n) FROM answers WHERE scan_id=?',(new,))[0],2)
        self.assertEqual(db.one('SELECT COUNT(DISTINCT engine) FROM answers WHERE scan_id=?',(new,))[0],engines_used)
        self.assertEqual(db.one("SELECT COUNT(*) FROM answers WHERE scan_id=? AND raw_text=''",(new,))[0],0)
        # Every engine stores its own answer for the same question and run.
        per=db.all_('SELECT engine,COUNT(*) AS n FROM answers WHERE scan_id=? GROUP BY engine',(new,))
        self.assertEqual({r['engine'] for r in per},set(config.SCAN_ENGINES))
        self.assertEqual({r['n'] for r in per},{(len(prompts)-1)*2})
        # Cost is the sum of each engine's own per-answer price, not one price
        # applied to everything - they differ by 6.5x.
        expected=sum((len(prompts)-1)*2*config.engine_price(e) for e in config.SCAN_ENGINES)
        cost=db.one('SELECT cost_cents FROM scans WHERE id=?',(new,))[0]
        self.assertAlmostEqual(cost,expected*100,places=4)   # cost_cents is cents

    def test_one_engine_failing_does_not_lose_the_others(self):
        """Perplexity going down must not cost us the ChatGPT answers."""
        new=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('part',?,'running',?,4)",(self.ps['id'],time.time()))
        good=self._fake_batch(skip_last=False)
        def batch(questions,usage=None,engine=config.DEFAULT_ENGINE,**kwargs):
            if engine=='perplexity':
                raise apify_answers.ApifyError('Perplexity blocked the proxy')
            return good(questions,usage,engine=engine,**kwargs)
        with patch.object(config,'ANSWER_SOURCE','apify'),patch.object(config,'RUNS_PER_QUESTION',1),patch.object(config,'PARALLEL_CALLS',1),patch('apify_answers.ask_batch',side_effect=batch),patch('llm.json_call',return_value={'items':[]}):
            scan._run(new,'example.invalid',self.ps['prompts'])
        got={r['engine'] for r in db.all_('SELECT DISTINCT engine FROM answers WHERE scan_id=?',(new,))}
        self.assertNotIn('perplexity',got)
        self.assertIn('chatgpt',got)
        self.assertIn('ai-overview',got)

    def test_ai_overview_silence_is_not_a_failed_scan(self):
        """Google shows no overview for many searches. That is a finding about
        the buyer's experience, not a broken scan, and must not flag an error."""
        new=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('aio',?,'running',?,4)",(self.ps['id'],time.time()))
        good=self._fake_batch(skip_last=False)
        def batch(questions,usage=None,engine=config.DEFAULT_ENGINE,**kwargs):
            if engine=='ai-overview':
                return {}                      # Google showed no overview at all
            return good(questions,usage,engine=engine,**kwargs)
        with patch.object(config,'ANSWER_SOURCE','apify'),patch.object(config,'RUNS_PER_QUESTION',1),patch.object(config,'PARALLEL_CALLS',1),patch('apify_answers.ask_batch',side_effect=batch),patch('llm.json_call',return_value={'items':[]}):
            scan._run(new,'example.invalid',self.ps['prompts'])
        row=db.one('SELECT status,error,model_versions FROM scans WHERE id=?',(new,))
        self.assertEqual(row['status'],'done')
        self.assertIsNone(row['error'])
        coverage=json.loads(row['model_versions'])['engine_coverage']
        self.assertEqual(coverage['ai-overview']['collected'],0)
        self.assertEqual(coverage['chatgpt']['collected'],len(self.ps['prompts']))

    def test_duplicate_answer_from_a_crash_is_shown_and_counted_once(self):
        """A crash can store the same answer twice; the extracted copy wins."""
        dup=db.write("INSERT INTO answers(scan_id,prompt,raw_text,citations,created_at,run_n) VALUES(?,'Best cleansers?','Saved evidence','[]',?,1)",(self.sid,time.time()))
        db.write("INSERT INTO answer_processing(answer_id,status) VALUES(?,'pending')",(dup,))
        db._revision+=1
        p=evidence.product_context(self.ps,1)
        shown,_=evidence.load(self.sid,p,include_unprocessed=True)
        self.assertEqual(len([a for a in shown if a['prompt']=='Best cleansers?' and a['run_n']==1]),1)
        self.assertNotIn(dup,{a['id'] for a in shown})      # the extracted copy is kept
        scored,_=evidence.load(self.sid,p)
        self.assertEqual(len(scored),2)      # the two real runs, not three

    def test_interrupted_scrape_is_resumed_not_discarded(self):
        """The whole point of scan_batches: a restart must not throw away
        answers already bought. Today's scan 6 lost a paid batch this way."""
        sid=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('crash',?,'running',?,2)",(self.ps['id'],time.time()))
        db.write("INSERT INTO scan_batches(scan_id,run_n,apify_run_id,dataset_id,collected,started_at) VALUES(?,1,'run123','ds123',0,?)",(sid,time.time()))
        bought={q:('Bought before the crash',[],'apify/chatgpt-search-scraper') for q in self.ps['prompts']}

        # A running scan with an open batch must be resumed, never failed.
        with patch('apify_answers.wait',return_value='SUCCEEDED'),patch('apify_answers.collect',return_value=bought):
            self.assertIn(sid,scan.recover_interrupted())
            self.assertEqual(db.one('SELECT status FROM scans WHERE id=?',(sid,))[0],'running')
            with patch('llm.json_call',return_value={'items':[]}):
                scan.resume(sid,'example.invalid')

        self.assertEqual(db.one('SELECT COUNT(*) FROM answers WHERE scan_id=?',(sid,))[0],len(self.ps['prompts']))
        self.assertEqual(db.one('SELECT collected FROM scan_batches WHERE scan_id=?',(sid,))[0],1)
        self.assertEqual(db.one("SELECT COUNT(*) FROM answers a JOIN answer_processing p ON p.answer_id=a.id WHERE a.scan_id=? AND p.status='done'",(sid,))[0],len(self.ps['prompts']))

        # Resuming twice must not store the same answer twice.
        with patch('apify_answers.wait',return_value='SUCCEEDED'),patch('apify_answers.collect',return_value=bought),patch('llm.json_call',return_value={'items':[]}):
            scan.resume(sid,'example.invalid')
        self.assertEqual(db.one('SELECT COUNT(*) FROM answers WHERE scan_id=?',(sid,))[0],len(self.ps['prompts']))

    def test_running_scan_with_nothing_bought_is_still_failed(self):
        sid=db.write("INSERT INTO scans(token,prompt_set_id,status,run_at,total) VALUES('empty',?,'running',?,2)",(self.ps['id'],time.time()))
        self.assertEqual(scan.recover_interrupted(),[])
        self.assertEqual(db.one('SELECT status FROM scans WHERE id=?',(sid,))[0],'failed')

    def test_new_generation_uses_catalog_and_currency(self):
        from questions import catalog_brief,generate_clusters
        products=db.all_('SELECT * FROM products')
        brief=catalog_brief(products,{'currency':'GBP','symbol':'£'})
        self.assertIn('£',brief)
        self.assertIn('Serum',brief)
        model_questions=[dict(question='Question '+str(i),tag='best',cluster='Cluster '+str(i),product_ids=[1]) for i in range(config.QUESTION_CLUSTERS_MIN)]
        with patch('llm.json_call',return_value={'questions':model_questions}) as call:
            result=generate_clusters(products,{'currency':'GBP','symbol':'£'})
        self.assertEqual(result[0]['products'],[1])
        self.assertIn('catalog summary',call.call_args.args[0])
        self.assertNotIn('You will get one product',call.call_args.args[0])

    def test_scope_validation_rejects_unrelated_ids(self):
        db.write("INSERT INTO stores(domain,brand) VALUES('other.invalid','Other')")
        db.write("INSERT INTO products(id,store_domain,title,raw_json) VALUES(99,'other.invalid','Other','{}')")
        with self.assertRaises(ValueError):
            db.save_prompts('other.invalid',['Question'],relevance=[[1]])

if __name__=='__main__':
    unittest.main()
