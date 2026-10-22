"""The agent's brain: cost guard, dedupe, doc-change watch, grading rules, playbook rules, digest.
No network, no Apify, no OpenAI: every outside call is replaced."""
import os
import tempfile
import time
import unittest

import brain
import config
import db

ROOMY = (5.0, 75.0)

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://vendor.test/blog/chatgpt-shopping-study</loc><lastmod>2026-10-20</lastmod></url>
<url><loc>https://vendor.test/blog/ai-overviews-citation-data</loc><lastmod>2026-10-18</lastmod></url>
<url><loc>https://vendor.test/blog/schema-for-products</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>https://vendor.test/blog/team-offsite-photos</loc><lastmod>2026-10-21</lastmod></url>
<url><loc>https://vendor.test/pricing</loc><lastmod>2026-10-21</lastmod></url>
</urlset>"""
NEW_POST = '<url><loc>https://vendor.test/blog/perplexity-merchant-feed</loc><lastmod>2026-10-23</lastmod></url>'
RSS = """<rss><channel><item><title><![CDATA[New ChatGPT product study]]></title>
<link>https://other.test/blog/new-study</link><pubDate>Thu, 22 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>"""
ARTICLE = '<html><title>Study</title><body><p>' + 'ChatGPT product carousel data. ' * 40 + '</p></body></html>'
DOC_V1 = '<html><title>AI features</title><body><p>Pages must be indexed. Updated 2026-10-01.</p></body></html>'


def web(pages):
    def get(url):
        if url not in pages:
            raise OSError('404 %s' % url)
        return pages[url]
    return get


def model(claims, relevant=True, kind='study', announcement=''):
    def call(instructions, text, usage):
        return dict(relevant=relevant, kind=kind, announcement=announcement, claims=claims)
    return call


def claim(text, evidence='measured', by='Peec AI', n='43,000 products', vendor=True, verdict='new', related=0,
          topic='engine_behaviour'):
    return dict(claim=text, topic=topic, engine='ChatGPT', evidence=evidence, measured_by=by, measured_by_vendor=vendor,
                sample_size=n, verdict=verdict, related_id=related)


class BrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, 't.db')
        self.assertNotIn('produkto.db', os.path.basename(config.DB_PATH))
        self.env = {k: os.environ.get(k) for k in ('PRODUKTO_BRAIN', 'PRODUKTO_BRAIN_CAP', 'PRODUKTO_BRAIN_DIGEST')}
        for k in self.env:
            os.environ.pop(k, None)
        os.environ['PRODUKTO_BRAIN_CAP'] = '1'      # pin it: the laptop .env must not change the tests
        db.init()
        brain.init()

    def tearDown(self):
        config.DB_PATH = self.old
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def item(self, **kw):
        row = dict(run_id=0, collector='blogs', source='Peec AI', url='https://peec.ai/blog/x', title='t',
                   published='2026-10-20', vendor=1, official=0, text='x' * 400)
        row.update(kw)
        iid = brain._queue(**row)
        return dict(db.one('SELECT * FROM brain_items WHERE id=?', (iid,)))

    # --- guard ---------------------------------------------------------------

    def test_off_by_default(self):
        ok, reasons = brain.guard(ROOMY)
        self.assertFalse(ok)
        self.assertIn('switched off', reasons[0])
        with self.assertRaises(ValueError):
            brain.run(usage=ROOMY, actor=lambda *a: ([], 0), get=web({}), only=[])

    def test_on_and_money_checks(self):
        os.environ['PRODUKTO_BRAIN'] = '1'
        self.assertTrue(brain.guard(ROOMY)[0])
        ok, reasons = brain.guard((65.0, 75.0))          # $10 left, minus tonight's $1 cap: too close
        self.assertFalse(ok)
        self.assertIn('daily scans', reasons[0])
        ok, _ = brain.guard((0, 75.0), force=False)
        self.assertTrue(ok)

    def test_hand_run_still_respects_money(self):
        self.assertTrue(brain.guard(ROOMY, force=True)[0])
        self.assertFalse(brain.guard((70.0, 75.0), force=True)[0])

    def test_unknown_balance_means_no_spending(self):
        os.environ['PRODUKTO_BRAIN'] = '1'
        orig = brain.account_usage
        brain.account_usage = lambda: (_ for _ in ()).throw(RuntimeError('no token'))
        try:
            ok, reasons = brain.guard()
        finally:
            brain.account_usage = orig
        self.assertFalse(ok)
        self.assertIn('Apify balance', reasons[0])

    # --- blogs: only new items -------------------------------------------------

    def test_blogs_first_run_skips_history_then_only_new(self):
        src = [dict(name='Vendor', feed='https://vendor.test/sitemap.xml', paths=('/blog/',))]
        out = brain.collect_blogs(1, web({'https://vendor.test/sitemap.xml': SITEMAP}), src)
        self.assertIn('first run', out['Vendor'])
        urls = [r['url'] for r in db.all_('SELECT url FROM brain_items')]
        # the two newest on-topic posts; the team post and the pricing page never qualify
        self.assertEqual(urls, ['https://vendor.test/blog/chatgpt-shopping-study',
                                'https://vendor.test/blog/ai-overviews-citation-data'])
        brain.collect_blogs(2, web({'https://vendor.test/sitemap.xml': SITEMAP}), src)
        self.assertEqual(db.one('SELECT COUNT(*) n FROM brain_items')['n'], 2)          # nothing new, nothing queued
        brain.collect_blogs(3, web({'https://vendor.test/sitemap.xml': SITEMAP.replace('</urlset>', NEW_POST + '</urlset>')}), src)
        rows = db.all_('SELECT url, vendor FROM brain_items WHERE run_id=3')
        self.assertEqual([(r['url'], r['vendor']) for r in rows], [('https://vendor.test/blog/perplexity-merchant-feed', 1)])

    def test_rss_feed_and_missing_feed(self):
        src = [dict(name='Other', feed='https://other.test/rss.xml', paths=('/blog/',)), dict(name='NoFeed', feed='')]
        out = brain.collect_blogs(1, web({'https://other.test/rss.xml': RSS}), src)
        self.assertEqual(out['NoFeed'], 'no feed address')
        row = db.one('SELECT * FROM brain_items')
        self.assertEqual((row['title'], row['published']), ('New ChatGPT product study', '2026-10-22'))

    def test_sitemap_with_one_date_everywhere_reads_nothing_on_first_run(self):
        same = SITEMAP.replace('2026-10-20', '2026-10-21').replace('2026-10-18', '2026-10-21').replace('2026-10-01', '2026-10-21')
        brain.collect_blogs(1, web({'https://vendor.test/sitemap.xml': same}),
                            [dict(name='Vendor', feed='https://vendor.test/sitemap.xml', paths=('/blog/',))])
        self.assertEqual(db.one('SELECT COUNT(*) n FROM brain_items')['n'], 0)

    # --- engine docs ------------------------------------------------------------

    def test_doc_change_becomes_official_item(self):
        docs = [('Google', 'https://g.test/ai')]
        self.assertEqual(brain.collect_docs(1, web({'https://g.test/ai': DOC_V1}), docs)['https://g.test/ai'], 'first look stored')
        moved = DOC_V1.replace('2026-10-01', '2026-10-22')
        self.assertEqual(brain.collect_docs(2, web({'https://g.test/ai': moved}), docs)['https://g.test/ai'], 'same')
        changed = moved.replace('</p>', ' Merchant Center feeds are now used to choose products in AI Mode.</p>')
        self.assertEqual(brain.collect_docs(3, web({'https://g.test/ai': changed}), docs)['https://g.test/ai'], 'changed: queued')
        row = db.one('SELECT * FROM brain_items')
        self.assertEqual(row['official'], 1)
        self.assertIn('Merchant Center feeds', row['text'])

    def test_unreadable_doc_is_recorded_not_fatal(self):
        out = brain.collect_docs(1, web({}), [('OpenAI', 'https://blocked.test/help')])
        self.assertEqual(out['https://blocked.test/help'], 'unreadable')
        self.assertIn('unreadable', db.one('SELECT status FROM brain_docs')['status'])

    # --- grading and the playbook ------------------------------------------------

    def test_official_only_from_engine_pages(self):
        blog = self.item()
        brain.store(blog, dict(relevant=True, announcement='', claims=[claim('OpenAI reads feeds.', evidence='official')]))
        doc = self.item(collector='docs', source='OpenAI', url='https://openai.test/help', vendor=0, official=1)
        brain.store(doc, dict(relevant=True, announcement='', claims=[claim('ChatGPT reads Shopify Catalog.', evidence='opinion')]))
        rows = {r['claim']: (r['evidence'], r['status']) for r in db.all_('SELECT * FROM brain_findings')}
        self.assertEqual(rows['OpenAI reads feeds.'], ('opinion', 'test'))
        self.assertEqual(rows['ChatGPT reads Shopify Catalog.'], ('official', 'playbook'))
        self.assertEqual(db.one("SELECT change FROM brain_changes")['change'], 'added')

    def test_measured_needs_who_and_how_big(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[claim('83% overlap.', n='')]))
        self.assertEqual(db.one('SELECT evidence FROM brain_findings')['evidence'], 'opinion')

    def test_one_vendor_study_never_changes_playbook_alone(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[claim('83% of carousel items rank in Shopping.')]))
        f = db.one('SELECT * FROM brain_findings')
        self.assertEqual((f['status'], f['vendor']), ('candidate', 1))
        # The same company saying it again is not a second source.
        brain.store(self.item(url='https://peec.ai/blog/y'), dict(relevant=True, announcement='', claims=[
            claim('Shopping rank predicts carousel rank.', verdict='agrees', related=f['id'])]))
        self.assertEqual(db.one("SELECT COUNT(*) n FROM brain_findings WHERE status='playbook'")['n'], 0)

    def test_independent_confirmation_puts_both_in_playbook(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[claim('83% of carousel items rank in Shopping.')]))
        first = db.one('SELECT id FROM brain_findings')['id']
        other = self.item(collector='search', source='ahrefs.com', url='https://ahrefs.com/blog/study', vendor=0)
        brain.store(other, dict(relevant=True, announcement='', claims=[
            claim('Most ChatGPT carousel products also rank in Google Shopping.', by='Ahrefs', n='10,000 prompts',
                  verdict='agrees', related=first)]))
        rows = db.all_('SELECT status, confirmed_by FROM brain_findings ORDER BY id')
        self.assertEqual([r['status'] for r in rows], ['playbook', 'playbook'])
        self.assertEqual(db.one("SELECT COUNT(*) n FROM brain_changes WHERE change='added'")['n'], 2)

    def test_same_study_reported_twice_is_not_a_second_source(self):
        # 22 Oct manual run: ReFiBuy's study "confirmed" itself across two of its own articles, and the
        # GEO paper was "confirmed" by two blogs quoting the same authors.
        brain.store(self.item(source='ReFiBuy', url='https://refibuy.ai/articles/a'), dict(relevant=True, announcement='', claims=[
            claim('Cards come first in 75% of tasks.', by='ReFiBuy with Clickstream Solutions', n='40 shoppers, 224 tasks')]))
        first = db.one('SELECT id FROM brain_findings')['id']
        brain.store(self.item(source='techblog.test', url='https://techblog.test/x', vendor=0), dict(relevant=True, announcement='', claims=[
            claim('Product cards first in 75% of 224 tasks.', by='Clickstream Solutions, commissioned by ReFiBuy',
                  n='224 tasks', verdict='agrees', related=first)]))
        brain.store(self.item(source='AI News', url='https://news.test/y', vendor=0), dict(relevant=True, announcement='', claims=[
            claim('Cards come first.', by='ReFiBuy', n='224 tasks', verdict='repeats', related=first)]))
        self.assertEqual(db.one("SELECT COUNT(*) n FROM brain_findings WHERE status='playbook'")['n'], 0)

    def test_vague_sample_is_an_opinion(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[
            claim('ChatGPT traffic fell 37%.', by='Peec AI', n='a few hundred domains')]))
        self.assertEqual(db.one('SELECT evidence, status FROM brain_findings')['evidence'], 'opinion')
        self.assertFalse(brain.has_size('one U.S. query, September 2025 vs September 2026'))
        self.assertTrue(brain.has_size('68,879 searches by 900 U.S. adults'))

    def test_settle_reapplies_rules_and_logs_removal(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[claim('83% overlap.')]))
        first = db.one('SELECT id FROM brain_findings')['id']
        brain.store(self.item(source='ahrefs.com', url='https://ahrefs.com/s', vendor=0), dict(relevant=True, announcement='', claims=[
            claim('Most carousel items rank in Shopping.', by='Ahrefs', n='10,000 prompts', verdict='agrees', related=first)]))
        self.assertEqual(db.one("SELECT COUNT(*) n FROM brain_findings WHERE status='playbook'")['n'], 2)
        db.write("UPDATE brain_findings SET verdict='repeats' WHERE related_id=?", (first,))   # a rule or reading changes
        self.assertEqual(len(brain.settle()), 2)
        self.assertEqual(db.one("SELECT COUNT(*) n FROM brain_changes WHERE change='removed'")['n'], 2)
        self.assertEqual(brain.settle(), [])                                                  # stable

    def test_competitor_listicles_are_skipped_launches_kept(self):
        self.assertTrue(brain.OFF_TOPIC.search('https://x.test/blog/best-geo-tools'))
        self.assertTrue(brain.OFF_TOPIC.search('The 12 best AEO software tools'))
        self.assertTrue(brain.on_topic('https://glara.ai/blog/introducing-glara-memory'))

    def test_opinion_agreeing_does_not_confirm(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[claim('83% overlap.')]))
        first = db.one('SELECT id FROM brain_findings')['id']
        brain.store(self.item(source='Someone', url='https://x.test/p', vendor=0), dict(relevant=True, announcement='', claims=[
            claim('I think Shopping matters.', evidence='opinion', by='', n='', verdict='agrees', related=first)]))
        self.assertEqual(db.one("SELECT COUNT(*) n FROM brain_findings WHERE status='playbook'")['n'], 0)
        self.assertEqual(db.one("SELECT status FROM brain_findings WHERE id>?", (first,))['status'], 'test')

    def test_contradiction_flags_both_and_removes_nothing(self):
        doc = self.item(collector='docs', source='Google', url='https://google.test/ai', vendor=0, official=1)
        brain.store(doc, dict(relevant=True, announcement='', claims=[claim('Schema is not required.', evidence='official')]))
        first = db.one('SELECT id FROM brain_findings')['id']
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[
            claim('Schema doubles AI citations.', verdict='contradicts', related=first)]))
        rows = db.all_('SELECT status, disputed FROM brain_findings ORDER BY id')
        self.assertEqual([(r['status'], r['disputed']) for r in rows], [('playbook', 1), ('candidate', 1)])
        self.assertEqual(db.one("SELECT change FROM brain_changes WHERE finding_id=? ORDER BY id DESC", (first,))['change'], 'disputed')

    def test_wording_findings_never_reach_playbook(self):
        doc = self.item(collector='docs', source='Google', url='https://google.test/ai', vendor=0, official=1)
        brain.store(doc, dict(relevant=True, announcement='', claims=[claim('Write in a friendly tone.', evidence='official',
                                                                            topic='wording')]))
        self.assertEqual(db.one('SELECT status FROM brain_findings')['status'], 'test')

    def test_unknown_related_id_is_treated_as_new(self):
        brain.store(self.item(), dict(relevant=True, announcement='', claims=[claim('x', verdict='agrees', related=999)]))
        f = db.one('SELECT verdict, related_id FROM brain_findings')
        self.assertEqual((f['verdict'], f['related_id']), ('new', None))

    def test_competitor_announcement_kept_apart(self):
        brain.store(self.item(source='Glara'), dict(relevant=False, announcement='Glara launched editorial briefs.', claims=[]))
        self.assertEqual(db.one('SELECT competitor, what FROM brain_shipped')['what'], 'Glara launched editorial briefs.')
        self.assertEqual(db.one('SELECT COUNT(*) n FROM brain_findings')['n'], 0)

    # --- money ----------------------------------------------------------------------

    def test_reading_stops_at_the_cap_and_waits_for_tomorrow(self):
        for i in range(5):
            self.item(url='https://peec.ai/blog/%d' % i)
        budget = brain.Budget(brain.LLM_PER_ITEM * 2.5)
        calls = []

        def call(instructions, text, usage):
            calls.append(1)
            return dict(relevant=True, kind='study', announcement='', claims=[])
        orig = brain.read_item
        brain.read_item = lambda item, c=None: (call(None, None, None), brain.LLM_PER_ITEM)
        try:
            out = brain.read_queue(budget, web({}))
        finally:
            brain.read_item = orig
        self.assertEqual((out['read'], out['waiting']), (2, 3))
        self.assertLessEqual(budget.spent, budget.limit)

    def test_paid_collectors_skip_when_over_budget(self):
        spent = []

        def actor(name, body):
            spent.append(name)
            return [], 0.0
        tiny = brain.Budget(0.001)
        self.assertIn('skipped', brain.collect_linkedin(1, actor, tiny, experts=['https://www.linkedin.com/in/a/'] * 40)['status'])
        self.assertIn('skipped', brain.collect_search(1, actor, tiny)['status'])
        self.assertEqual(spent, [])

    def test_linkedin_posts_dedupe_and_filter(self):
        posts = [dict(id='1', content='We counted 40,000 ChatGPT shopping answers and product feeds won. ' * 5,
                      linkedinUrl='https://linkedin.test/p/1', author=dict(name='Lily Ray'), postedAt=dict(date='2026-10-20T10:00')),
                 dict(id='2', content='Hiring! Join our team.', linkedinUrl='https://linkedin.test/p/2', author=dict(name='X'))]
        actor = lambda name, body: (posts, 0.004)
        b = brain.Budget(1.0)
        self.assertEqual(brain.collect_linkedin(1, actor, b, experts=['u'])['queued'], 1)
        self.assertEqual(brain.collect_linkedin(2, actor, b, experts=['u'])['queued'], 0)
        self.assertAlmostEqual(b.spent, 0.008)

    def test_full_night_with_fakes(self):
        os.environ['PRODUKTO_BRAIN'] = '1'
        pages = {'https://other.test/rss.xml': RSS, 'https://other.test/blog/new-study': ARTICLE,
                 'https://study.test/report': ARTICLE}

        def actor(name, body):
            if name == brain.SEARCH_ACTOR:
                return [dict(organicResults=[dict(url='https://study.test/report', title='AI search ecommerce study',
                                                  description='We analysed 1M ChatGPT answers')])], 0.015
            return [], 0.0
        orig = brain.COMPETITORS, brain.ENGINE_DOCS
        brain.COMPETITORS, brain.ENGINE_DOCS = [dict(name='Other', feed='https://other.test/rss.xml', paths=('/blog/',))], []
        try:
            out = brain.run(usage=ROOMY, actor=actor, get=web(pages), only=['docs', 'blogs', 'search'],
                            call=model([claim('Feeds win position 1.', by='Profound', n='1M offers')]))
        finally:
            brain.COMPETITORS, brain.ENGINE_DOCS = orig
        self.assertEqual(out['status'], 'done')
        self.assertEqual(out['detail']['reading']['read'], 2)
        self.assertGreaterEqual(out['cost_usd'], 0.015)
        self.assertLessEqual(out['cost_usd'], brain.cap())
        self.assertEqual(db.one('SELECT COUNT(*) n FROM brain_findings')['n'], 2)
        self.assertIn('Run %d' % out['run_id'], brain.report(out['run_id']))

    def test_run_due_once_a_night_only_when_on(self):
        self.assertFalse(brain.run_due())
        os.environ['PRODUKTO_BRAIN'] = '1'
        db.write("INSERT INTO brain_runs (day, status, started_at) VALUES (?,?,?)",
                 (time.strftime('%Y-%m-%d'), 'done', time.time()))
        self.assertFalse(brain.run_due())

    def test_cadence(self):
        self.assertEqual(set(brain.due_collectors()), set(brain.EVERY))
        import json
        db.write("INSERT INTO brain_runs (day, status, detail, started_at) VALUES (?,?,?,?)",
                 ('2026-10-22', 'done', json.dumps(dict(ran=['linkedin', 'blogs'])), time.time() - 86400))
        due = brain.due_collectors()
        self.assertIn('blogs', due)
        self.assertNotIn('linkedin', due)

    # --- digest ----------------------------------------------------------------------

    def test_digest_off_by_default_and_monday_only(self):
        monday = time.mktime((2026, 10, 26, 9, 0, 0, 0, 0, -1))
        self.assertIsNone(brain.send_digest(monday))
        os.environ['PRODUKTO_BRAIN_DIGEST'] = '1'
        self.assertIsNone(brain.send_digest(monday + 86400))
        doc = self.item(collector='docs', source='Google', url='https://google.test/ai', vendor=0, official=1)
        brain.store(doc, dict(relevant=True, announcement='', claims=[claim('Merchant Center feeds AI Mode.', evidence='official')]))
        text = ' '.join(brain.digest_paragraphs())
        self.assertIn('Merchant Center feeds AI Mode. (Official', text)
        self.assertIsNotNone(brain.send_digest(monday))
        self.assertIsNone(brain.send_digest(monday + 3600))             # once a week


if __name__ == '__main__':
    unittest.main()
