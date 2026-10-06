"""Tests for the source-concentration signal. Does not touch the network."""

import json
import unittest

import concentration


def cites(*hosts_per_answer):
    """One citations JSON string per answer."""
    return [json.dumps([{'url': 'https://%s/page?utm_source=openai' % h, 'title': h}
                        for h in hosts]) for hosts in hosts_per_answer]


class Concentration(unittest.TestCase):

    def test_one_domain_everywhere_is_entrenched(self):
        r = concentration.measure(cites(['aad.org'], ['aad.org'], ['aad.org']))
        self.assertEqual(r['score'], 100)
        self.assertEqual(r['band'], 'entrenched')
        self.assertEqual(r['lead'], 100.0)

    def test_scattered_sources_score_low(self):
        r = concentration.measure(cites(*[['site%d.com' % n] for n in range(10)]))
        self.assertEqual(r['band'], 'open')
        self.assertLess(r['score'], 15)

    def test_repeated_link_in_one_answer_counts_once(self):
        """A chatty answer must not inflate a domain's hold on the question."""
        once = concentration.measure(cites(['a.com'], ['b.com']))
        many = concentration.measure(cites(['a.com', 'a.com', 'a.com'], ['b.com']))
        self.assertEqual(once['score'], many['score'])

    def test_www_and_query_are_stripped(self):
        self.assertEqual(concentration.domain('https://www.Boots.com/x?y=1'), 'boots.com')

    def test_answers_without_citations_stay_in_the_denominator(self):
        r = concentration.measure(cites(['a.com']) + ['[]', ''])
        self.assertEqual(r['answers'], 3)
        self.assertEqual(r['cited'], 1)
        self.assertAlmostEqual(r['lead'], 33.3, places=1)

    def test_no_citations_at_all_is_not_zero_concentration(self):
        r = concentration.measure(['[]', '[]'])
        self.assertIsNone(r['score'])
        self.assertEqual(r['band'], 'no citations')

    def test_empty_group_returns_nothing(self):
        self.assertIsNone(concentration.measure([]))

    def test_own_domain_is_reported_separately(self):
        r = concentration.measure(cites(['mine.com'], ['other.com']), own_domain='mine.com')
        self.assertEqual(r['own'], 50.0)


if __name__ == '__main__':
    unittest.main()
