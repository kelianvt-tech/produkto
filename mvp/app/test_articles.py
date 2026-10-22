"""Designed AEO articles (19 Oct 2026): brand style, niche examples, the writer's checks, rendering,
learning from the owner's changes, and the hidden store preview. No AI calls, no network."""
import collections
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

D = 'shop.com'

CSS = """
@font-face{font-family:"Brand Serif";src:url(/cdn/shop/files/BrandSerif.woff2?v=1) format("woff2");font-weight:400}
@font-face{font-family:"Brand Sans";src:url(/cdn/shop/files/BrandSans.woff2?v=1) format("woff2");font-weight:400}
@font-face{font-family:"Brand Mono";src:url(/cdn/shop/files/BrandMono.woff2?v=1) format("woff2");font-weight:400}
:root{--font-body-family:"Brand Sans",sans-serif;--font-heading-family:"Brand Sans",sans-serif}
body{font-family:var(--font-body-family);color:#191919}
h1,h2,h3{font-family:var(--font-heading-family)}
.product__info .product__title h1{font-family:'Brand Serif',serif!important;text-transform:uppercase;color:#1a281e}
.product__text,.price{font-family:"Brand Mono";text-transform:uppercase;font-size:11px;letter-spacing:.1rem}
.button{border-radius:0;background:#1a281e;color:#fff}
.panel{background:#f5f4f0;border-bottom:1px solid #dcd9d1}
.cookie-banner h2{font-family:"Brand Mono"}
"""
PRODUCT_HTML = """<html><body><header class="site-header"><h1>Logo</h1></header><main id="MainContent">
<div class="product__info"><div class="product__title"><h1>Frontier Cleanser</h1></div>
<span class="price">£39</span><div class="product__description rte"><p>A daily cleanser.</p></div></div></main></body></html>"""


def article_body(**kw):
    b = dict(
        layout='article', store=D, title='How to build a simple routine', dek='Cleanse, then moisturise.',
        category='Routines',
        glance=[dict(label='The routine', text='Cleanse, then moisturise.')],
        sections=[dict(step_label='Step 1', heading='How do I cleanse?', paragraphs=['Use it first.'], product_id='P1', photo=True),
                  dict(step_label='', heading='What comes next?', paragraphs=['Moisturise.'], product_id='P9', photo=True)],
        picks=[dict(id='P1', text='A daily cleanser.', labels=['Sea Salt', 'Unicorn'], facts_used=['daily cleanser'])],
        tables=[dict(after_section=0, heading='Morning and evening', columns=['', 'Morning'], rows=[dict(cells=['1', 'Cleanser']),
                                                                                                    dict(cells=['bad'])], note='')],
        faqs=[dict(question='Is it daily?', answer='Yes, it is a daily cleanser.'),
              dict(question='Waiting?', answer='[ask merchant: is it vegan?]')],
        faq_heading='Questions people ask', closing=dict(heading='The routine', text='All of it.', product_id='P1'),
        open_questions=[],
        products=[dict(handle='frontier', title='Frontier Cleanser', url='https://shop.com/products/frontier',
                       image='https://cdn.shopify.com/a/pack.jpg', images=['https://cdn.shopify.com/a/pack.jpg',
                       'https://cdn.shopify.com/a/life1.jpg', 'https://cdn.shopify.com/a/life2.jpg'], price=39.0)])
    b.update(kw)
    return b


STYLE = dict(fonts=dict(heading=dict(family='Brand Serif', faces=[('400', 'normal', 'https://shop.com/cdn/shop/files/BrandSerif.woff2')]),
                        body=dict(family='Brand Sans', faces=[]), label=dict(family='Brand Mono', faces=[])),
             google_css=[], heading_upper=True, label_upper=True, label_spacing='.1rem',
             colors=dict(ink='#191919', accent='#1a281e', soft='#f5f4f0', line='#dcd9d1', muted='#6b6a66'),
             radius=0, learned_at=time.time())

FACTS = [dict(handle='frontier', title='Frontier Cleanser', url='https://shop.com/products/frontier', image='',
              facts=[dict(label='Key ingredient', value='Sea Salt', source='catalog')],
              description=['A daily cleanser that respects your skin.'], variants=[dict(price='39.00')])]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, 't.db')
        assert not config.DB_PATH.endswith('produkto.db')
        db.init()
        content_agent.init()
        content_setup.put(D, dict(part1_done_at=time.time(), brand_style=STYLE))

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()


class BrandStyleTest(Base):
    def test_cascade_finds_the_brand_heading_face_not_the_theme_default(self):
        import brand_style as b
        sheets = [(CSS, 'https://shop.com/cdn/shop/t/1/assets/base.css')]
        ev = b.evidence(sheets, dict(product=PRODUCT_HTML))
        self.assertEqual(ev['applied']['title']['font'], 'Brand Serif')       # not the logo h1 in the header
        self.assertTrue(ev['applied']['title']['upper'])
        st = b.learn_from(sheets, ai=False, pages=dict(product=PRODUCT_HTML))
        self.assertEqual(st['fonts']['heading']['family'], 'Brand Serif')
        self.assertEqual(st['fonts']['heading']['faces'][0][2], 'https://shop.com/cdn/shop/files/BrandSerif.woff2?v=1')
        self.assertEqual(st['fonts']['body']['family'], 'Brand Sans')
        self.assertEqual(st['radius'], 0)

    def test_ai_answer_off_the_page_falls_back(self):
        import brand_style as b
        ev = b.evidence([(CSS, 'https://shop.com/x.css')], dict(product=PRODUCT_HTML))
        bad = dict(heading_font='Comic Sans', body_font='Brand Sans', label_font='Brand Mono', heading_upper=False,
                   label_upper=True, ink='#123456', accent='#1a281e', soft='#f5f4f0', line='#dcd9d1', muted='#000000',
                   radius=0, why='')
        with mock.patch('llm.json_call', return_value=bad):
            d = b.decide(ev)
        self.assertEqual(d['heading_font'], 'Brand Serif')       # invented font replaced by the cascade's answer
        self.assertNotEqual(d['ink'], '#123456')                 # colour not on the page
        self.assertTrue(d['heading_upper'])                      # the real title is in capitals
        self.assertNotEqual(d['muted'], '#000000')               # black isn't a muted grey

    def test_overrides_win(self):
        import brand_style as b
        st = b.apply_overrides(STYLE, dict(heading_font='Brand Sans', accent='#000000', radius=8, heading_upper=False))
        self.assertEqual(st['fonts']['heading']['family'], 'Brand Sans')
        self.assertEqual(st['colors']['accent'], '#000000')
        self.assertEqual(st['radius'], 8)
        self.assertFalse(st['heading_upper'])
        self.assertIn('Brand Serif', b.summary(STYLE))


class RenderTest(Base):
    def test_page_uses_the_brand_look_and_own_photos(self):
        import article_render as r
        html, cover = r.render(article_body(), article_body()['products'], STYLE, brand='Shop', symbol='£')
        self.assertIn('pk-heading', html)                         # the store's heading face, under an alias
        self.assertIn('text-transform:uppercase', html)
        self.assertIn('Shop &middot; £39', html)
        self.assertIn('application/ld+json', html)
        self.assertNotIn('is it vegan', html.split('application/ld+json')[1])    # gaps never go into FAQ markup
        self.assertIn('<mark class="pk-gap">', html)
        self.assertTrue(cover.endswith('life1.jpg'))
        self.assertEqual(html.count('life1.jpg'), 0)             # the cover photo isn't repeated inside
        self.assertIn('life2.jpg', html)
        self.assertIn('By Shop', html)

    def test_theme_title_only_when_asked(self):
        import article_render as r
        self.assertNotIn('main h1', r.css(STYLE))
        self.assertIn('main h1', r.css(STYLE, theme_title=True))


class ChecksTest(Base):
    def test_ids_picks_labels_tables_are_cleaned(self):
        import drafts
        body = article_body()
        with mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('brand_style.get', return_value=STYLE), \
                mock.patch('factcheck.check') as fc:
            drafts.article_checks(body, D, ai=False)
        self.assertEqual(body['sections'][1]['product_id'], '')           # P9 doesn't exist
        self.assertEqual(body['picks'][0]['labels'], ['Sea Salt'])         # Unicorn isn't stated
        self.assertEqual(len(body['tables'][0]['rows']), 1)                # ragged row dropped
        self.assertIn('html', body)
        self.assertEqual(fc.call_args.args[1], 'article')

    def test_unstated_pick_is_dropped(self):
        import drafts
        body = article_body(picks=[dict(id='P1', text='x', labels=[], facts_used=['cures everything'])])
        with mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('brand_style.get', return_value=STYLE), \
                mock.patch('factcheck.check'):
            drafts.article_checks(body, D, ai=False)
        self.assertEqual(body['picks'], [])

    def test_knowledge_allowed_only_for_articles(self):
        import factcheck
        verdicts = dict(verdicts=[dict(n=1, verdict='knowledge', ask_merchant='')])
        for t, kept in (('article', True), ('guide', False)):
            res = dict(title='', intro='Vitamin C is an antioxidant.', dek='Vitamin C is an antioxidant.', sections=[], picks=[])
            with mock.patch('llm.json_call', return_value=verdicts):
                factcheck.check(res, t, FACTS)
            text = res['dek'] if t == 'article' else res['intro']
            self.assertEqual('[ask merchant' not in text, kept, t)

    def test_verified_sentences_are_not_rechecked(self):
        import factcheck
        res = dict(title='', dek='Old line.', glance=[], sections=[], picks=[], tables=[], faqs=[], closing={})
        with mock.patch('llm.json_call') as call:
            factcheck.check(res, 'article', FACTS, verified={'Old line.'})
        call.assert_not_called()


class LearningTest(Base):
    def _draft(self, body):
        import json as _j
        with db.conn() as c:
            did = c.execute("INSERT INTO content_drafts (store_domain, draft_type, title, status, created_at, updated_at) "
                            "VALUES (?, 'guide', 't', 'draft', ?, ?)", (D, time.time(), time.time())).lastrowid
            c.execute("INSERT INTO content_draft_versions (draft_id, body, author, sources, open_facts, created_at) "
                      "VALUES (?,?,'agent','[]','[]',?)", (did, _j.dumps(body), time.time()))
        return did

    def test_lessons_dedupe_and_remove(self):
        import article_learning as al
        a = al.add_lesson(D, 'Never mention returns.', 'request')
        self.assertIsNone(al.add_lesson(D, 'never mention returns', 'edit'))
        self.assertIn('Never mention returns.', al.prompt(D))
        al.remove_lesson(D, a['id'])
        self.assertEqual(al.prompt(D), '')

    def test_revise_applies_change_keeps_lessons_and_only_store_fonts(self):
        import article_learning as al
        did = self._draft(article_body())
        new = {k: article_body()[k] for k in al._BLOCK_KEYS}
        new['faqs'] = new['faqs'][:1]
        answer = dict(article=new, reply='Removed the second question.', lessons=['No FAQ about veganism.'],
                      style=dict(heading_font='Brand Sans', body_font='Papyrus', label_font='', heading_upper='false',
                                 accent='#1a281e', ink='#abcdef', soft='', radius=''))
        with mock.patch('llm.json_call', return_value=answer), mock.patch('brand_style.learn', return_value=STYLE), \
                mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('factcheck.check'):
            reply, added, changed = al.revise(D, did, 'Remove the vegan question, and headings in our body font.')
        import content_review
        _, body, _ = content_review.load(did, D)
        self.assertEqual(len(body['faqs']), 1)
        self.assertEqual([l['text'] for l in added], ['No FAQ about veganism.'])
        self.assertEqual(changed.get('heading_font'), 'Brand Sans')
        self.assertNotIn('body_font', changed)                   # Papyrus isn't one of the store's fonts
        self.assertNotIn('ink', changed)                         # nor is that colour
        o = content_setup.get(D)['brand_style_overrides']
        self.assertEqual(o['heading_font'], 'Brand Sans')
        self.assertIs(o['heading_upper'], False)
        self.assertEqual(body['requests'][-1]['reply'], 'Removed the second question.')

    def test_filling_a_gap_is_not_a_lesson(self):
        import article_learning as al
        before = article_body()
        after = article_body(faqs=[before['faqs'][0], dict(question='Waiting?', answer='')])
        with mock.patch('llm.json_call') as call:
            self.assertEqual(al.learn_from_edit(D, before, after), [])
        call.assert_not_called()

    def test_hand_edit_lessons(self):
        import article_learning as al
        before = article_body()
        after = article_body(dek='Two products. One job each. That is the whole routine, kept short on purpose.')
        with mock.patch('llm.json_call', return_value=dict(lessons=['Keep intros short and punchy.'])):
            added = al.learn_from_edit(D, before, after)
        self.assertEqual([l['text'] for l in added], ['Keep intros short and punchy.'])
        self.assertEqual(added[0]['source'], 'edit')


class NicheTest(Base):
    def test_candidates_are_brand_articles_not_big_sites_or_products(self):
        import niche_examples as n
        cites = {'q': collections.Counter({'https://www.vogue.com/article/x': 99, 'https://brand-a.com/blogs/journal/how-to': 9,
                                           'https://brand-a.com/blogs/journal/other': 3,
                                           'https://brand-b.com/products/serum': 50, 'https://shop.com/blogs/news/ours': 40,
                                           'https://brand-c.com/stories/routine': 5})}
        with mock.patch('briefs._evidence', return_value=({}, {}, {}, cites)):
            got = n.candidates(D)
        self.assertEqual([u for u, _ in got], ['https://brand-a.com/blogs/journal/how-to', 'https://brand-c.com/stories/routine'])
        self.assertEqual(got[0][1], 12)                           # one entry per site, citations added up

    def test_measure(self):
        import niche_examples as n
        html = ('<nav><h2>Menu</h2></nav><article><h1>Routine</h1><p>' + 'word ' * 300 + '</p><h2>Step 1: Cleanse</h2>'
                '<h2>Why does it matter?</h2><img src="a.jpg"><table></table><details><summary>Q</summary></details>'
                '<a href="/products/x">x</a><p>5 min read</p><div>At a glance</div></article>')
        m = n.measure(html)
        self.assertEqual(m['h2'], 2)
        self.assertEqual((m['step_headings'], m['question_headings']), (1, 1))
        self.assertTrue(m['faq'] and m['summary_box'] and m['read_time'])
        self.assertEqual((m['images'], m['tables'], m['product_links']), (1, 1, 1))

    def test_no_pages_gives_default(self):
        import niche_examples as n
        self.assertEqual(n.build([], 'x')['length_words'], n.DEFAULT_PLAYBOOK['length_words'])
        self.assertIn('Length: about', n.prompt(n.DEFAULT_PLAYBOOK))


class ShopifyPreviewTest(Base):
    def test_hidden_draft_then_published_same_article(self):
        import shopify_connect as s
        import content_review
        shopify_connect_row = ('INSERT INTO shopify_connections (store_domain, shop, token, scopes, connected_at, connected_by) '
                               "VALUES (?, 'shop.myshopify.com', 'x', '', 0, '')")
        s.init()
        db.write(shopify_connect_row, (D,))
        did = LearningTest._draft(self, article_body(faqs=[dict(question='Q?', answer='A.')]))
        calls = []

        def gql(domain, q, v=None):
            calls.append((q.split('(')[0].split('{')[0].strip(), v))
            if 'blogs(first' in q:
                return {'blogs': {'nodes': [{'id': 'gid://shopify/Blog/1', 'handle': 'news'}]}}
            if 'articleCreate' in q:
                return {'articleCreate': {'article': {'id': 'gid://shopify/Article/77', 'handle': 'how-to'}, 'userErrors': []}}
            if 'articleUpdate' in q:
                return {'articleUpdate': {'article': {'id': 'gid://shopify/Article/77', 'handle': 'how-to',
                                                      'blog': {'handle': 'news'}}, 'userErrors': []}}
            return {}
        with mock.patch('shopify_connect.gql', side_effect=gql), mock.patch('brand_style.get', return_value=STYLE):
            link = s.preview(D, did)
            self.assertEqual(link, 'https://admin.shopify.com/store/shop/content/articles/77')
            created = [v for q, v in calls if 'articleCreate' in str(v) or q == 'mutation($a:ArticleCreateInput!)']
            a = next(v['a'] for _, v in calls if v and 'a' in v and 'blogId' in v['a'])
            self.assertFalse(a['isPublished'])                    # hidden: customers can't see it
            self.assertTrue(a['image']['url'].endswith('life1.jpg'))
            self.assertEqual(a['summary'], 'Cleanse, then moisturise.')
            db.write("UPDATE content_drafts SET status='approved' WHERE id=?", (did,))
            calls.clear()
            url = s.publish(D, did)
        upd = next(v for _, v in calls if v and v.get('id') == 'gid://shopify/Article/77')
        self.assertTrue(upd['a']['isPublished'])                  # the same article goes visible
        self.assertFalse(any(v and 'a' in v and 'blogId' in v['a'] for _, v in calls))   # no second article
        self.assertEqual(url, 'https://shop.myshopify.com/blogs/news/how-to')
        _, body, _ = content_review.load(did, D)
        self.assertEqual(body['shopify_draft']['id'], 'gid://shopify/Article/77')


class ReviewPageTest(Base):
    def test_article_view_shows_preview_and_ask_box(self):
        import content_review
        did = LearningTest._draft(self, article_body())
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('shopify_connect.configured', return_value=False):
            html = content_review.page(D, dict(id=str(did)), None, content_agent.DRAFT_TYPES)
        self.assertIn('class="cr-frame"', html)
        self.assertIn('name="action" value="revise"', html)
        self.assertIn('Intro under the title', html)              # the edit form names article fields plainly


if __name__ == '__main__':
    unittest.main()


class ArticleSetupTest(Base):
    GEN = dict(niche='Dog supplements', questions=[
        dict(id='species', question='Which animals are they for?', hint='', kind='lines', options=[], is_fact=True,
             answer='', answer_lines=['Dogs']),
        dict(id='vet', question='Should articles tell readers to ask a vet?', hint='', kind='choice',
             options=['Always', 'Never'], is_fact=False, answer='Always', answer_lines=[]),
        dict(id='length', question='Clashes with a common key', hint='', kind='text', options=[], is_fact=False,
             answer='x', answer_lines=[])],
        common=dict(readers='Dog owners', level='Beginners', help_with=['Joint care'], length='Short (600-800 words)',
                    blocks=['FAQ', 'Product cards'], photos='A mix of both', selling='Gently: name them where they help',
                    feature=[], never_products=['Old Chew'], avoid_topics=['Raw feeding'], author='', expert='Made with a vet',
                    categories=['Guides'], compliance=['cures arthritis'], disclaimer='Ask your vet first.',
                    loved=['https://x.com/blog/a']))

    def test_prefill_keeps_niche_questions_and_never_invents_loved_links(self):
        import article_setup as a
        with mock.patch('llm.json_call', return_value=self.GEN), mock.patch('article_setup._context', return_value=''):
            ab = a.prefill(D)
        self.assertEqual([q['id'] for q in ab['questions']], ['species', 'vet'])      # clash with a common key dropped
        self.assertEqual(ab['answers']['n.species'], ['Dogs'])
        self.assertEqual(ab['answers']['loved'], [])                                   # only the owner adds those

    def test_answers_reach_writer_facts_and_rules(self):
        import article_setup as a
        with mock.patch('llm.json_call', return_value=self.GEN), mock.patch('article_setup._context', return_value=''):
            ab = a.prefill(D)
        s = content_setup.get(D); s['article_brief'] = ab; content_setup.put(D, s)
        form = {'a.length': 'In-depth (1,500+ words)', 'a.blocks.5': '1', 'a.never_products': 'Old Chew',
                'a.compliance': 'cures arthritis', 'a.loved': 'https://brand.com/blogs/a\nnot a link',
                'a.n.species': 'Dogs\nCats', 'a.n.vet': 'Sometimes', 'a.disclaimer': 'Ask your vet first.'}
        a.save_form(D, form)
        self.assertTrue(a.done(D))
        self.assertEqual(a.length(D), 1600)
        self.assertEqual(a.answer(a.get(D), 'blocks'), ['FAQ'])
        self.assertEqual(a.answer(a.get(D), 'n.vet'), '')                  # not one of the options
        self.assertEqual(a.loved(D), ['https://brand.com/blogs/a'])
        self.assertEqual([f['value'] for f in content_setup.brand_facts(D)], ['Dogs', 'Cats'])
        self.assertIn('cures arthritis', content_setup.rules(D)['no_claims'])
        p = a.prompt(D)
        self.assertIn('DOG SUPPLEMENTS', p)
        self.assertIn('Which animals are they for? Dogs; Cats', p)
        self.assertNotIn('Old Chew', p)                                     # left out by code, not by asking nicely

    def test_setup_step_and_loved_articles_lead_niche_examples(self):
        import article_setup as a
        import niche_examples as n
        with mock.patch('llm.json_call', return_value=self.GEN), mock.patch('article_setup._context', return_value=''):
            ab = a.prefill(D)
        s = content_setup.get(D); s['article_brief'] = ab; content_setup.put(D, s)
        a.save_form(D, {'a.loved': 'https://loved.com/journal/x'})
        cites = {'q': collections.Counter({'https://brand-a.com/blogs/journal/how-to': 9})}
        with mock.patch('briefs._evidence', return_value=({}, {}, {}, cites)):
            got = n.candidates(D)
        self.assertEqual(got[0], ('https://loved.com/journal/x', 0))
        with mock.patch('config.ARTICLES_V2', True):
            html = content_setup.page(D, dict(step='articles'))
            self.assertIn('Questions for Dog supplements', html)
            self.assertIn('Your articles', content_setup._steps('articles', D))


class FullPreviewTest(Base):
    def test_full_page_preview_for_owner_only(self):
        import content_review
        did = LearningTest._draft(self, article_body())
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('content_agent.enabled', return_value=True), \
                mock.patch('accounts.can_see', return_value=True):
            code, html = content_review.full_preview(dict(d=D, id=str(did)))
        self.assertEqual(code, 200)
        self.assertIn('Not live.', html)
        self.assertIn('pk-a', html)
        with mock.patch('content_agent.enabled', return_value=True), mock.patch('accounts.can_see', return_value=False):
            self.assertEqual(content_review.full_preview(dict(d=D, id=str(did)))[0], 404)


class LegacyPreviewTest(Base):
    def test_old_guide_and_comparison_get_the_styled_preview_and_a_rewrite_button(self):
        import content_review
        old = dict(store=D, title='Old guide', intro='Plain old text.', sections=[dict(heading='H', paragraphs=['P.'])], picks=[],
                   open_questions=[], html='<p>Plain old text.</p>', products=[dict(image='https://cdn.shopify.com/x.jpg', url='u', title='t')])
        did = LearningTest._draft(self, old)
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('shopify_connect.configured', return_value=False), \
                mock.patch('config.ARTICLES_V2', True):
            html = content_review.page(D, dict(id=str(did)), None, content_agent.DRAFT_TYPES)
            self.assertIn('class="cr-frame"', html)
            self.assertIn('value="redesign"', html)
            self.assertNotIn('value="revise"', html)
            styled, cover = content_review.styled(old, D)
            self.assertIn('class="pk-a"', styled)
            self.assertEqual(cover, 'https://cdn.shopify.com/x.jpg')

    def test_redesign_rejects_the_old_draft(self):
        import content_review
        did = LearningTest._draft(self, dict(store=D, title='Old', html='<p>x</p>'))
        with db.conn() as c:
            bid = c.execute("INSERT INTO content_briefs (store_domain, opportunity_kind, opportunity_key, draft_type, created_at) "
                            "VALUES (?, 'missing', 'q', 'guide', 0)", (D,)).lastrowid
            c.execute('UPDATE content_drafts SET brief_id=?, planned_at=123 WHERE id=?', (bid, did))
        new = LearningTest._draft(self, dict(store=D, title='New', layout='article'))
        with mock.patch('content_agent.draft_for', return_value=(new, None)) as df:
            got, err = content_review.redesign(D, did)
        self.assertEqual((got, err), (new, None))
        self.assertEqual(df.call_args.kwargs['only'], ('guide',))
        rows = {r['id']: r for r in db.all_('SELECT id, status, planned_at FROM content_drafts')}
        self.assertEqual(rows[did]['status'], 'rejected')
        self.assertEqual(rows[new]['planned_at'], 123)


class PencilTest(Base):
    def _article(self):
        return LearningTest._draft(self, article_body())

    def test_marks_only_in_the_editable_preview(self):
        import article_render as r
        html, _ = r.render(article_body(), article_body()['products'], STYLE, marks=True)
        self.assertIn('data-pk="sections.0.paragraphs.0"', html)
        self.assertIn('data-photo="s.0"', html)
        self.assertIn('data-gap="is it vegan?"', html)
        plain, _ = r.render(article_body(), article_body()['products'], STYLE)
        self.assertNotIn('data-pk', plain)
        self.assertNotIn('data-gap', plain)

    def test_list_paragraphs_render_as_bullets(self):
        import article_render as r
        self.assertIn('<li>two</li>', r._para('Intro:\n- one\n- two'))
        self.assertEqual(r._para('plain'), '<p>plain</p>')

    def test_change_one_part_and_remember(self):
        import article_learning as al
        import content_review
        did = self._article()
        answer = dict(part='Use it first, every morning.', lesson='Keep step paragraphs to one sentence.', reply='Shortened.')
        with mock.patch('llm.json_call', return_value=answer), mock.patch('catalog_facts.get', return_value=FACTS), \
                mock.patch('brand_style.get', return_value=STYLE), mock.patch('factcheck.check') as fc:
            reply, lesson = al.change_part(D, did, 'sections.0.paragraphs.0', quick='shorter', remember=True)
        _, body, _ = content_review.load(did, D)
        self.assertEqual(body['sections'][0]['paragraphs'][0], 'Use it first, every morning.')
        self.assertEqual(body['change_note'], 'Paragraph: Shorter')
        self.assertEqual(lesson['text'], 'Keep step paragraphs to one sentence.')
        self.assertIn('Use it first.', fc.call_args.kwargs['verified'])          # untouched text isn't re-checked
        with mock.patch('llm.json_call', return_value=dict(answer, lesson='Another rule.')), \
                mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('brand_style.get', return_value=STYLE), \
                mock.patch('factcheck.check'):
            _, lesson = al.change_part(D, did, 'sections.0.heading', instruction='friendlier', remember=False)
        self.assertIsNone(lesson)                                                 # owner unticked "remember"

    def test_a_label_instead_of_a_rewrite_is_refused(self):
        import article_learning as al
        did = self._article()
        with mock.patch('llm.json_call', return_value=dict(part='Paragraph', lesson='', reply='')), \
                mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('brand_style.get', return_value=STYLE):
            with self.assertRaises(ValueError):
                al.change_part(D, did, 'sections.0.paragraphs.0', quick='shorter')

    def test_a_change_that_adds_gaps_is_retried_then_refused(self):
        import article_learning as al
        import content_review
        did = self._article()
        calls = []

        def check(result, *a, **k):
            calls.append(1)
            result['sections'][0]['paragraphs'][0] = '[ask merchant: is that true?]'
            result['fact_check'] = dict(claims=[dict(sentence='x')])
        with mock.patch('llm.json_call', return_value=dict(part='A new claim about results.', lesson='', reply='')), \
                mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('brand_style.get', return_value=STYLE), \
                mock.patch('factcheck.check', side_effect=check):
            with self.assertRaises(ValueError):
                al.change_part(D, did, 'sections.0.paragraphs.0', instruction='say it works in a week')
        self.assertEqual(len(calls), 2)
        _, body, _ = content_review.load(did, D)
        self.assertEqual(body['sections'][0]['paragraphs'][0], 'Use it first.')       # unchanged

    def test_remove_photo_undo_restore_history(self):
        import article_learning as al
        import content_review
        did = self._article()
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('catalog_facts.get', return_value=FACTS):
            al.remove_part(D, did, 'faqs.1')
            al.remove_part(D, did, 'card.P1')
            al.set_photo(D, did, 'cover', 'https://cdn.shopify.com/a/life2.jpg')
            with self.assertRaises(ValueError):
                al.set_photo(D, did, 'cover', 'https://evil.example/x.jpg')       # only the store's own photos
            _, body, _ = content_review.load(did, D)
            self.assertEqual(len(body['faqs']), 1)
            self.assertEqual(body['sections'][0]['product_id'], '')
            self.assertTrue(body['cover'].endswith('life2.jpg'))
            al.restore(D, did)                                                     # undo: the photo goes back
            _, body, _ = content_review.load(did, D)
            self.assertNotIn('photo_overrides', body)
            notes = [h[3] for h in al.history(did)]
            self.assertEqual(notes[:4], ['Undid the last change', 'Changed a photo', 'Removed: Product card', 'Removed: Question and answer'])
            first = al.history(did)[-1][0]
            al.restore(D, did, first)
            _, body, _ = content_review.load(did, D)
            self.assertEqual(len(body['faqs']), 2)


class MoreEditingTest(Base):
    def _article(self, **kw):
        b = article_body(**kw)
        b['sections'].append(dict(step_label='', heading='Third?', paragraphs=['Three.'], product_id='', photo=False))
        b['photo_overrides'] = {'s.0': 'https://cdn.shopify.com/a/life2.jpg'}
        return LearningTest._draft(self, b)

    def _load(self, did):
        import content_review
        return content_review.load(did, D)[1]

    def test_typing_saves_own_words_and_learns_in_background(self):
        import article_learning as al
        did = self._article()
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('article_learning.learn_in_background') as bg:
            al.set_text(D, did, 'dek', '  My own   intro.  ')
            with self.assertRaises(ValueError):
                al.set_text(D, did, 'sections.0', 'x')                      # a whole section isn't one text
        self.assertEqual(self._load(did)['dek'], 'My own intro.')
        self.assertEqual(self._load(did)['change_note'], 'You typed: Intro')
        bg.assert_called_once()

    def test_move_and_remove_sections_keep_tables_and_photos_with_them(self):
        import article_learning as al
        did = self._article()
        with mock.patch('brand_style.get', return_value=STYLE):
            al.move_section(D, did, 0, 'down')
            b = self._load(did)
            self.assertEqual(b['sections'][1]['heading'], 'How do I cleanse?')
            self.assertEqual(b['tables'][0]['after_section'], 1)
            self.assertIn('s.1', b['photo_overrides'])
            with self.assertRaises(ValueError):
                al.move_section(D, did, 2, 'down')
            al.remove_part(D, did, 'sections.0')
            b = self._load(did)
            self.assertEqual([s['heading'] for s in b['sections']], ['How do I cleanse?', 'Third?'])
            self.assertEqual(b['tables'][0]['after_section'], 0)
            self.assertEqual(list(b['photo_overrides']), ['s.0'])

    def test_add_section_goes_in_the_right_place(self):
        import article_learning as al
        did = self._article()
        new = dict(step_label='', heading='What about mornings?', paragraphs=['Cleanse first.'], product_id='', photo=False)
        with mock.patch('llm.json_call', return_value=dict(section=new, reply='Added.')), \
                mock.patch('catalog_facts.get', return_value=FACTS), mock.patch('brand_style.get', return_value=STYLE), \
                mock.patch('factcheck.check'):
            al.add_section(D, did, 0, 'mornings')
        b = self._load(did)
        self.assertEqual(b['sections'][1]['heading'], 'What about mornings?')
        self.assertEqual(b['tables'][0]['after_section'], 0)
        self.assertEqual(b['sections'][2]['heading'], 'What comes next?')

    def test_swap_product_card(self):
        import article_learning as al
        did = self._article()
        other = dict(handle='helsinki', title='Helsinki Moisturiser', url='https://shop.com/products/helsinki', image='h.jpg',
                     images=['h.jpg', 'h2.jpg'], facts=[], description=['A lightweight moisturiser. It hydrates.'],
                     variants=[dict(price='34.00')])
        with mock.patch('catalog_facts.get', return_value=FACTS + [other]), mock.patch('brand_style.get', return_value=STYLE):
            al.swap_product(D, did, 'P1', 'helsinki')
            with self.assertRaises(ValueError):
                al.swap_product(D, did, 'P2', 'not-a-product')
        b = self._load(did)
        self.assertEqual(b['sections'][0]['product_id'], 'P2')
        self.assertEqual(b['products'][1]['title'], 'Helsinki Moisturiser')
        self.assertEqual(next(k for k in b['picks'] if k['id'] == 'P2')['text'], 'A lightweight moisturiser.')

    def test_look_controls_only_take_the_stores_own_fonts_and_colours(self):
        import article_learning as al
        with mock.patch('brand_style.learn', return_value=STYLE):
            al.look_quick(D, dict(heading_font='Brand Sans', body_font='Papyrus', heading_upper='0', accent='#dcd9d1'))
            o = content_setup.get(D)['brand_style_overrides']
            self.assertEqual(o['heading_font'], 'Brand Sans')
            self.assertNotIn('body_font', o)
            self.assertIs(o['heading_upper'], False)
            self.assertEqual(o['accent'], '#dcd9d1')
            al.look_quick(D, dict(heading_font='Brand Serif'))              # back to what the site uses: no override
            self.assertNotIn('heading_font', content_setup.get(D)['brand_style_overrides'])

    def test_upload_photo(self):
        import article_learning as al
        import base64
        did = self._article()
        jpg = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff\xe0' + b'0' * 100).decode()
        with mock.patch('brand_style.get', return_value=STYLE), mock.patch('catalog_facts.get', return_value=FACTS):
            al.upload_photo(D, did, 'cover', jpg)
            with self.assertRaises(ValueError):
                al.upload_photo(D, did, 'cover', 'data:image/jpeg;base64,' + base64.b64encode(b'<script>').decode())
            with self.assertRaises(ValueError):
                al.upload_photo(D, did, 'cover', 'data:text/html;base64,AAAA')
        url = self._load(did)['photo_overrides']['cover']
        self.assertIn('/content/media/', url)
        mime, raw = al.media(url.rsplit('/', 1)[1][:-4])
        self.assertEqual(mime, 'image/jpeg')
        self.assertTrue(raw.startswith(b'\xff\xd8'))
        self.assertIn(url, al.store_photos(D))
        self.assertIsNone(al.media('nope'))


class StepNumberTest(Base):
    def test_steps_renumber_after_a_move(self):
        import article_learning as al
        b = article_body()
        b['sections'][1]['step_label'] = 'Step 2'
        al._reindex(b, {0: 1, 1: 0})
        b['sections'].reverse()
        al._renumber(b)
        self.assertEqual([s['step_label'] for s in b['sections']], ['Step 1', 'Step 2'])


class ShopifyFilesTest(Base):
    def _connect(self, scopes):
        import shopify_connect as s
        s.init()
        db.write("INSERT OR REPLACE INTO shopify_connections (store_domain, shop, token, scopes, connected_at, connected_by) "
                 "VALUES (?, 'shop.myshopify.com', 'x', ?, 0, '')", (D, scopes))

    def test_uploads_go_to_shopify_once_and_only_with_permission(self):
        import article_learning as al
        import base64
        import shopify_connect as s
        jpg = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff\xe0' + b'0' * 50).decode()
        url = al.save_upload(D, jpg)
        body = dict(photo_overrides={'cover': url, 's.1': 'https://cdn.shopify.com/a/life2.jpg'}, title='T')
        self._connect('write_content')
        self.assertEqual(s.host_uploads(D, dict(body, photo_overrides=dict(body['photo_overrides']))), 1)   # no permission yet
        self._connect('write_content,write_files')
        calls = []

        def gql(domain, q, v=None):
            calls.append(q)
            if 'fileCreate' in q:
                self.assertEqual(v['f'][0]['originalSource'], url)
                return {'fileCreate': {'files': [{'id': 'gid://shopify/MediaImage/1', 'fileStatus': 'UPLOADED', 'image': None}], 'userErrors': []}}
            return {'node': {'fileStatus': 'READY', 'image': {'url': 'https://cdn.shopify.com/s/files/owner.jpg'}}}
        b1 = dict(body, photo_overrides=dict(body['photo_overrides']))
        with mock.patch('shopify_connect.gql', side_effect=gql), mock.patch('time.sleep'):
            self.assertEqual(s.host_uploads(D, b1), 0)
            b2 = dict(body, photo_overrides=dict(body['photo_overrides']))
            s.host_uploads(D, b2)
        self.assertEqual(b1['photo_overrides']['cover'], 'https://cdn.shopify.com/s/files/owner.jpg')
        self.assertEqual(b1['photo_overrides']['s.1'], 'https://cdn.shopify.com/a/life2.jpg')        # store photos untouched
        self.assertEqual(b2['photo_overrides']['cover'], 'https://cdn.shopify.com/s/files/owner.jpg')
        self.assertEqual(sum('fileCreate' in q for q in calls), 1)                                    # uploaded once

    def test_settings_ask_to_reconnect_without_the_files_permission(self):
        self._connect('write_content')
        with mock.patch('shopify_connect.configured', return_value=True):
            self.assertIn('Reconnect Shopify', content_setup.shopify_section(D))
            self._connect('write_content,write_files')
            self.assertNotIn('Reconnect Shopify', content_setup.shopify_section(D))
