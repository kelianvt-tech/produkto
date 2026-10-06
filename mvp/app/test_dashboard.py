"""Presentation checks using an isolated database, never the real scan store."""
import json
import os
import sqlite3
import tempfile
import unittest

import config
import db
import dashboard
import evidence


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, 'test.db')
        db.init()
        db.write("INSERT INTO products(id,store_domain,title,vendor,image) VALUES(1,'test.invalid','Example Cleanser','Example','')")
        db.write("INSERT INTO stores(domain,brand) VALUES('test.invalid','Example')")
        db.save_prompts('test.invalid',['Question one','Question two'],['best','spec'],['Group one','Group two'],[[1],[1]])
        import time
        db.write("INSERT INTO scans(id,token,prompt_set_id,run_at,status) VALUES(1,'test',1,?,'done')",(time.time(),))
        db.write("INSERT INTO scores(scan_id,visibility,appearance_rate,detail) VALUES(1,0,50,'{}')")
        for i,q in [(1,'Question one'),(2,'Question two')]:
            db.write("INSERT INTO answers(id,scan_id,prompt,run_n,raw_text,citations,created_at) VALUES(?,1,?,1,?,'[]',1)",(i,q,'A **readable** answer'))
        db.write("INSERT INTO answer_processing(answer_id,status) SELECT id,'done' FROM answers")
        for aid,name,own in [(1,'Example Cleanser',1),(1,'Other Product',0),(2,'Other Product',0)]:
            db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url) VALUES(?,?,'Example',1,?,1,'')",(aid,name,own))
        db.write('UPDATE mentions SET matched_product_id=1 WHERE is_theirs=1')

    def tearDown(self):
        config.DB_PATH=self.old
        self.tmp.cleanup()

    def test_brand_rate_is_not_product_rate(self):
        s,ps,p=dashboard.context('test',{'product':'1'})
        rows=dashboard.brand_rows(s,p)
        self.assertIn('100.0%',rows)  # Brand in both answers; product in only one.
        self.assertEqual(rows.count('Your brand'),1)

    def test_question_and_status_filters(self):
        self.assertEqual(dashboard.answers('test',{'q':'0'}).count('id="answer-'),1)
        self.assertEqual(dashboard.answers('test',{'status':'yours'}).count('id="answer-'),1)
        self.assertEqual(dashboard.answers('test',{'status':'brand'}).count('id="answer-'),1)
        self.assertIn('No answers match',dashboard.answers('test',{'q':'999'}))
        self.assertIn('No answers match',dashboard.answers('test',{'search':'missing phrase'}))
        self.assertIsNone(dashboard.answers('missing',{}))

    def test_answer_visibility_models_and_individual_products(self):
        html = dashboard.answers('test', {})
        self.assertIn('>Mentioned</span>', html)
        self.assertIn('>Model</span>', html)
        self.assertIn('>Product mentions</span>', html)
        self.assertIn('class="mentioned yes"', html)
        self.assertIn('class="mentioned no"', html)
        self.assertIn('ChatGPT</span>', html)
        # Two products from the same brand remain separate in the first answer.
        first = html.split('id="answer-1"')[1].split('</summary>')[0]
        self.assertIn('Example Cleanser · Example · Your product', first)
        self.assertIn('Other Product · Example', first)
        db.write("UPDATE answer_processing SET status='pending' WHERE answer_id=1")
        first = dashboard.answers('test', {}).split('id="answer-1"')[1].split('</summary>')[0]
        self.assertNotIn('<b>100%</b>', first)
        self.assertIn('Pending', first)

    def test_product_comparisons_use_saved_answer_positions(self):
        import insight_panels
        scan,prompts,product=dashboard.context('test',{'product':'1'})
        rows=insight_panels.products(scan['id'],product)
        own=next(r for r in rows if r['own'])
        rival=next(r for r in rows if not r['own'])
        # Displayed visibility = share of answers mentioning the product.
        self.assertEqual(own['visibility'],50.0)
        self.assertEqual(own['questions'],{'Question one':100.0,'Question two':0.0})
        self.assertEqual(rival['visibility'],100.0)
        self.assertAlmostEqual(sum(r['share'] for r in rows),100.0)
        self.assertAlmostEqual(own['share'],100/3)

    def test_visibility_ignores_position(self):
        import insight_panels
        db.write("UPDATE mentions SET rank=5 WHERE is_theirs=1")
        scan,prompts,product=dashboard.context('test',{'product':'1'})
        own=next(r for r in insight_panels.products(scan['id'],product) if r['own'])
        self.assertEqual(own['visibility'],50.0)       # still named in 1 of 2 answers
        self.assertLess(own['weighted'],50.0)           # the weighted score does drop
        self.assertEqual(own['avg'],5)

    def test_market_comparison_pools_answers_and_deduplicates_brand_hits(self):
        import insight_panels
        scan,ps,p=dashboard.context('test',{'product':'1'})
        db.write("UPDATE mentions SET brand='Rival' WHERE is_theirs=0")
        db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url) VALUES(1,'Second rival product','Rival',3,0,0,'')")
        db.write("INSERT INTO scans(id,token,prompt_set_id,run_at,status) SELECT 2,'second',prompt_set_id,run_at+1,'done' FROM scans WHERE id=1")
        db.write("INSERT INTO answers(id,scan_id,prompt,run_n,raw_text,citations,created_at) VALUES(3,2,'Question one',1,'Nothing recommended','[]',2)")
        db.write("INSERT INTO answer_processing(answer_id,status) VALUES(3,'done')")
        rows=insight_panels.market_rows([1,2],p)
        own=next(r for r in rows if r['own'])
        rival=next(r for r in rows if not r['own'])
        self.assertAlmostEqual(own['rate'],100/3)
        self.assertAlmostEqual(rival['rate'],200/3)
        self.assertEqual(rival['avg'],1)
        self.assertEqual(rival['share'],75)
        self.assertEqual(insight_panels.market_rows([],p)[0]['answers'],0)
        self.assertEqual(insight_panels.display_brand('about:blank'),'Brand unavailable')

    def test_ranking_chart_keeps_products_from_one_brand_separate(self):
        import insight_panels
        db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url) VALUES(1,'Hydrating Serum','Example',3,0,1,'')")
        scan,ps,p=dashboard.context('test',{})
        ctx=insight_panels.period_context(ps,p,{})
        rows=insight_panels.ranking_products(ctx['scans'],ctx,p)
        self.assertEqual(len(rows),3)
        own=next(r for r in rows if r['own'])
        serum=next(r for r in rows if r['name']=='Hydrating Serum')
        self.assertEqual(own['rate'],50)
        self.assertEqual(serum['rate'],50)
        self.assertEqual(serum['scan']['1'],dict(hits=1,ranks=3,count=1))
        self.assertAlmostEqual(sum(r['share'] for r in rows),100)
        self.assertEqual(len({r['key'] for r in rows}),3)

    def test_ranking_chart_keeps_selected_zero_mention_products(self):
        import insight_panels
        db.write('DELETE FROM mentions WHERE is_theirs=1')
        scan,ps,p=dashboard.context('test',{})
        ctx=insight_panels.period_context(ps,p,{})
        rows=insight_panels.ranking_products(ctx['scans'],ctx,p)
        own=next(r for r in rows if r['own'])
        self.assertEqual(own['rate'],0)
        self.assertEqual(own['share'],0)
        self.assertIsNone(own['avg'])
        self.assertEqual(own['scan']['1'],dict(hits=0,ranks=0,count=0))

    def test_catalog_table_uses_all_questions_like_rankings(self):
        import insight_panels
        scan,ps,p=dashboard.context('test',{})
        ps=dict(evidence.prompt_set(ps),relevance=[[1],[]])
        p=evidence.product_context(ps)
        ctx=insight_panels.period_context(ps,p,{})
        table=dashboard.catalog_table(scan,ps,p,ctx)
        self.assertIn('data-label="Visibility"><span class="pc-v">50%',table)
        self.assertNotIn('data-label="Visibility"><span class="pc-v">100%',table)
        own=next(r for r in insight_panels.ranking_products(ctx['scans'],ctx,p) if r['own'])
        self.assertEqual(own['rate'],50)

    def test_mentioned_price_is_median_quote_in_main_currency(self):
        import insight_panels
        mp=insight_panels.mentioned_price
        self.assertEqual(mp(['€16.99','€16.99','€18.50'])['text'],'€16.99')
        self.assertEqual(mp(['16,99 €'])['text'],'€16.99')
        self.assertEqual(mp(['£1,299.00'])['text'],'£1299')
        self.assertEqual(mp(['$20','$30','€99'])['text'],'$25')
        self.assertIsNone(mp([]))
        self.assertIsNone(mp(['about the mid range']))

    def test_quoted_price_reaches_product_and_catalog_table(self):
        import insight_panels
        db.write("UPDATE mentions SET price='€19.50' WHERE is_theirs=1")
        scan,ps,p=dashboard.context('test',{})
        ctx=insight_panels.period_context(ps,p,{})
        self.assertEqual(insight_panels.mentioned_price(ctx['own'].get('prices'))['text'],'€19.50')
        table=dashboard.catalog_table(scan,ps,evidence.product_context(ps),ctx)
        self.assertIn('data-label="Mentioned price"><span class="pc-v">€19.50',table)

    def _add_engine_answers(self):
        """The same two questions, answered by the other two engines too."""
        import time
        rows=[(3,'Question one','ai-overview'),(4,'Question two','ai-overview'),
              (5,'Question one','perplexity'),(6,'Question two','perplexity')]
        for aid,q,eng in rows:
            db.write("INSERT INTO answers(id,scan_id,prompt,engine,run_n,raw_text,citations,created_at)"
                     " VALUES(?,1,?,?,1,?,'[]',1)",(aid,q,eng,'A **readable** answer from '+eng))
            db.write("INSERT INTO answer_processing(answer_id,status) VALUES(?,'done')",(aid,))
        # Their product is named only by ai-overview, so the engines disagree -
        # which is the entire reason the filter exists.
        db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url,matched_product_id)"
                 " VALUES(3,'Example Cleanser','Example',1,1,1,'',1)")
        db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url)"
                 " VALUES(5,'Other Product','Example',1,0,1,'')")
        db._revision+=1
        evidence.clear_cache()

    def test_three_engines_are_three_answers_not_one_duplicate(self):
        """The dedupe key must include the engine. Without it, one question on
        one run collapses to a single answer and two thirds of a scan vanish."""
        self._add_engine_answers()
        p=evidence.product_context(db.one('SELECT * FROM prompt_sets WHERE id=1'))
        answers,_=evidence.load(1,p)
        self.assertEqual(len(answers),6)
        self.assertEqual({a['engine'] for a in answers},{'chatgpt','ai-overview','perplexity'})

    def test_engine_filter_changes_the_numbers(self):
        import engines, insight_panels
        self._add_engine_answers()
        ps=db.one('SELECT * FROM prompt_sets WHERE id=1')
        def rate_for(query):
            p=evidence.product_context(ps)
            ctx=insight_panels.period_context(ps,p,query)
            return next(r for r in ctx['rows'] if r['own'])['visibility']
        # chatgpt names it in 1 of 2; ai-overview in 1 of 2; perplexity in 0 of 2.
        self.assertEqual(rate_for({'engines':'chatgpt'}),50.0)
        self.assertEqual(rate_for({'engines':'perplexity'}),0.0)
        self.assertEqual(rate_for({'engines':'chatgpt,ai-overview'}),50.0)
        self.assertEqual(rate_for({}),100/3)            # all six answers pooled
        # An unknown or empty selection falls back to everything rather than
        # blanking the dashboard.
        self.assertEqual(rate_for({'engines':'nonsense'}),100/3)
        self.assertEqual(engines.parse({'engines':''}),engines.all_ids())

    def test_engine_selection_survives_the_links_between_tabs(self):
        self._add_engine_answers()
        page=dashboard.answers('test',{'engines':'perplexity'})
        self.assertIn('engines=perplexity',page)
        # Only that engine's answers are listed, and each row names its source.
        self.assertEqual(page.count('id="answer-'),2)
        self.assertIn('Perplexity',page)
        self.assertNotIn('ChatGPT’s answer',page)

    def test_safe_formatting_and_original_text(self):
        raw='<script>alert(1)</script> **bold** [bad](javascript:alert(1)) [good](https://example.com/?x=1&y=2)'
        result=dashboard.readable(raw)
        self.assertNotIn('<script>',result)
        self.assertNotIn('href="javascript:',result)
        self.assertIn('<strong>bold</strong>',result)
        self.assertIn('rel="noopener noreferrer"',result)
        self.assertEqual(dashboard.safe_url('data:text/html,bad'),'')

    def test_empty_zero_and_history_states(self):
        s,ps,p=dashboard.context('test',{'product':'1'})
        sc={'visibility':0,'appearance_rate':0,'avg_rank':None,'sov_pct':0,'detail':json.dumps({'sov_rows':[],'other_pct':0,'questions':[]})}
        # A product page follows Peec's layout (2026-09-23): six headline
        # figures, visibility & win rate over time, co-featured products.
        page=dashboard.overview(s,ps,p,sc)
        for label in ('Visibility','Position','Appearances','Mentioned price','Catalog price','Win rate'):
            self.assertIn('<span class="pk-label">%s<'%label,page)
        self.assertIn('class="pp-chart"',page)
        self.assertIn('Co-featured products',page)
        self.assertIn('Position vs competitors',page)
        self.assertNotIn('id="visibility-chart"',page)
        # The catalog page keeps the multi-brand chart.
        s,ps,p=dashboard.context('test',{})
        self.assertIn('Not mentioned',dashboard.overview(s,ps,p,sc))
        self.assertIn('First scan saved',dashboard.overview(s,ps,p,sc))
        db.write("INSERT INTO scans(id,token,prompt_set_id,run_at,status) VALUES(2,'second',1,2,'done')")
        db.write('INSERT INTO scores(scan_id,visibility,appearance_rate) VALUES(2,6,20)')
        s=db.one('SELECT * FROM scans WHERE id=2')
        rendered=dashboard.overview(s,ps,p,sc)
        self.assertIn('id="visibility-chart"',rendered)
        import re
        payload=json.loads(re.search(r'id="visibility-data">(.*?)</script>',rendered).group(1))
        # One entry per saved scan, with answer counts the page pools by period.
        self.assertEqual([x['n'] for x in payload['scans']], [0,2])   # oldest first
        self.assertEqual(payload['scans'][1]['own'], [1,1])
        self.assertIn('data-group="quarter"', rendered)
        self.assertIn('data-group="day"', rendered)     # daily scans, daily points (2026-09-22)
        self.assertIn('View scan history as a table',rendered)
        db.write('DELETE FROM answers')
        self.assertIn('No completed answers',dashboard.answers('test',{}))

    def test_answers_and_citations_follow_the_period(self):
        import citation_panel
        self.assertEqual(dashboard.answers('test',{}).count('id="answer-'),2)
        old={'range':'custom','from':'2001-01-01','to':'2001-01-31','group':'week'}
        self.assertEqual(dashboard.answers('test',old).count('id="answer-'),0)
        self.assertIn('No scans in the selected period',dashboard.answers('test',old))
        self.assertIn('No scans in this period',citation_panel.page('test',old))
        self.assertNotIn('fb-note',citation_panel.page('test',{}))   # scan-count line removed 21 Sep
        self.assertIn('direct product citations',citation_panel.page('test',{'group':'month'}))


    def test_panels_pool_scans_in_the_chosen_period(self):
        import time, insight_panels
        now=time.time()
        # Scan 1 (answers 1-2) is moved to now; scan 3 adds two more answers, one naming the product.
        db.write("INSERT INTO scans(id,token,prompt_set_id,run_at,status) VALUES(3,'third',1,?,'done')",(now-3600,))
        db.write("INSERT INTO scores(scan_id,visibility,appearance_rate,detail) VALUES(3,0,50,'{}')")
        # run_n differs per answer: _run never writes the same (scan, question,
        # run) twice, and evidence.load now treats a repeat as a crash duplicate.
        for i in (3,4):
            db.write("INSERT INTO answers(id,scan_id,prompt,run_n,raw_text,citations,created_at) VALUES(?,3,'Question one',?,'x','[]',1)",(i,i-2))
        db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url) VALUES(3,'Example Cleanser','Example',2,1,1,'')")
        db.write("INSERT OR IGNORE INTO answer_processing(answer_id,status) SELECT id,'done' FROM answers")
        db.write('UPDATE mentions SET matched_product_id=1 WHERE is_theirs=1')
        s,ps,p=dashboard.context('test',{'product':'1'})
        ctx=insight_panels.period_context(ps,p,{'range':'7','group':'week'})
        self.assertEqual(sorted(ctx['ids']),[1,3])
        self.assertEqual(ctx['own']['rate'],50.0)          # named in 2 of 4 pooled answers
        self.assertEqual(ctx['own']['avg'],1.5)            # positions 1 and 2
        self.assertEqual(ctx['own']['q_rank']['Question one'],1.5)
        empty=insight_panels.period_context(ps,p,{'range':'custom','from':'2001-01-01','to':'2001-02-01','group':'month'})
        self.assertEqual(empty['ids'],[])
        sc={'visibility':0,'appearance_rate':0,'avg_rank':None,'sov_pct':0,'detail':json.dumps({'sov_rows':[],'other_pct':0,'questions':[]})}
        html=dashboard.overview(s,ps,p,sc,{'range':'custom','from':'2001-01-01','to':'2001-02-01','group':'month'})
        self.assertIn('No scans in this period',html)

    def test_period_parsing_daily(self):
        # Daily is offered and is the default, because scans run once a day.
        import datetime as dt, period
        self.assertEqual(period.parse({'group':'day'})['group'],'day')
        self.assertEqual(period.parse({})['group'],'day')
        self.assertEqual(period.parse({'group':'hourly'})['group'],'day')
        d=dt.date(2026,9,22)
        self.assertEqual(period.bucket_start(d,'day'),d)
        self.assertEqual(period.next_bucket(d,'day'),dt.date(2026,9,23))
        self.assertEqual(len(period.bucket_starts(dt.date(2026,8,24),d,'day')),30)
        self.assertEqual(period.short_label(d,'day'),'22 Sep')
        self.assertEqual(period.parse({'range':'custom','from':'bad'})['range'],'30')


if __name__=='__main__':
    unittest.main()
