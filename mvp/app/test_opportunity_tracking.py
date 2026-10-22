"""Before/after on Done cards, and what a cited page names. Isolated database, no network."""
import os
import tempfile
import time
import unittest

import config
import db
import opportunities
import page_gap


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, 't.db')
        assert not config.DB_PATH.endswith('produkto.db')
        db.init()
        db.write("INSERT INTO products(id,store_domain,title,vendor,image) VALUES(1,'t.invalid','Glow Oil','Mine','')")
        db.write("INSERT INTO stores(domain,brand) VALUES('t.invalid','Mine')")
        db.save_prompts('t.invalid', ['Best glow oil?'], ['best'], ['Oils'], [[1]])
        self.now = time.time()
        self.done_at = self.now - 3 * 86400
        # Before: two answers, neither names you. After: five answers, three name you.
        aid = 0
        for scan, ts, named in [(1, self.done_at - 5 * 86400, [0, 0]), (2, self.now - 86400, [1, 1, 1, 0, 0])]:
            db.write("INSERT INTO scans(id,token,prompt_set_id,run_at,status) VALUES(?,?,1,?,'done')", (scan, 's%d' % scan, ts))
            db.write("INSERT INTO scores(scan_id,visibility,appearance_rate,detail) VALUES(?,0,0,'{}')", (scan,))
            for own in named:
                aid += 1
                db.write("INSERT INTO answers(id,scan_id,prompt,run_n,raw_text,citations,created_at) VALUES(?,?,'Best glow oil?',?,'x','[]',?)",
                         (aid, scan, aid, ts))
                db.write("INSERT INTO answer_processing(answer_id,status) VALUES(?,'done')", (aid,))
                if own:
                    db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url,matched_product_id) "
                             "VALUES(?,'Glow Oil','Mine',1,1,1,'',1)", (aid,))
                else:
                    db.write("INSERT INTO mentions(answer_id,product_name,brand,rank,is_theirs,is_their_brand,url) "
                             "VALUES(?,'Rival Oil','Rival',1,0,0,'')", (aid,))

    def tearDown(self):
        config.DB_PATH = self.old
        self.tmp.cleanup()

    def test_before_after_compares_the_same_question(self):
        card = dict(type='missing', key='Best glow oil?')
        line = opportunities.before_after('t.invalid', card, self.done_at)
        self.assertIn('<b>0 of 2</b> answers (0%)', line)
        self.assertIn('<b>3 of 5</b> answers (60%)', line)
        self.assertIn('up 60 points', line)
        self.assertIn('not why', line)

    def test_too_few_answers_since_done_is_too_early(self):
        line = opportunities.before_after('t.invalid', dict(type='missing', key='Best glow oil?'), self.now - 60)
        self.assertIn('too early', line)

    def test_done_card_whose_problem_went_away_still_shows(self):
        card = opportunities._gone(('missing', 'Best glow oil?'), {'status': 'done'})
        self.assertIn('no longer shows up', card['text'])

    def test_names_on_page_matches_whole_names(self):
        f = dict(text='Our top picks: CeraVe Hydrating Cleanser and The Ordinary. Doveton is not Dove.')
        self.assertEqual(page_gap.names_on_page(f, ['CeraVe', 'The Ordinary', 'Dove', 'Mine']),
                         ['CeraVe', 'The Ordinary', 'Dove'])
        self.assertEqual(page_gap.names_on_page(dict(text='Doveton only'), ['Dove']), [])


if __name__ == '__main__':
    unittest.main()
