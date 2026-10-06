"""How entrenched the sources behind a buyer question are.

WHY THIS EXISTS
---------------
"Difficulty" on a competitor dashboard is an estimate: keyword competition
blended with source authority, neither of which we hold. This is the part we
can answer from our own data without estimating anything.

Every answer we store carries the pages ChatGPT cited. If the same two or
three domains are cited on every run of a question, that answer is settled and
a new product page is unlikely to displace it. If the citations scatter across
many domains, the question is still open and there is room to be picked up.

That is a measurement, not a forecast. It says how concentrated the sources we
actually saw were. It does not predict whether remediation will work - nobody
can claim that yet, including the funded competitors.

NOT WIRED INTO THE APP
----------------------
Nothing imports this from a page. It is a signal we are building up before
deciding whether it belongs in front of a merchant. Run it from the command
line:

    python3 concentration.py                 # every question in the newest scan
    python3 concentration.py --scan 5
    python3 concentration.py --json
"""

import argparse
import collections
import json
import sys
from urllib.parse import urlsplit

import db

# Presence is counted once per answer, never per citation. An answer that
# links the same page four times is one vote, not four, so a chatty response
# cannot inflate a domain's apparent hold on the question.
#
# The score is a Herfindahl index over how often each domain appears - the
# standard way to say "how few hands is this in". Coverage measures were tried
# first and were useless: with five runs per question, the top three domains
# cover nearly every answer whatever the question, so everything scored 90+.
# HHI separates them properly, because it falls as the sources broaden.
# Bands follow the usual 0.15 / 0.30 convention.
BANDS = ((15, 'open'), (30, 'mixed'), (101, 'entrenched'))


def domain(url):
    """The host behind a citation, without www. and without the query."""
    host = urlsplit(url or '').netloc.lower().split(':')[0]
    return host[4:] if host.startswith('www.') else host


def answer_domains(citations):
    """Distinct hosts cited by one answer."""
    try:
        rows = json.loads(citations or '[]')
    except ValueError:
        return set()
    return {d for d in (domain(c.get('url')) for c in rows if isinstance(c, dict)) if d}


def measure(citation_rows, own_domain=''):
    """Concentration across a group of answers.

    `citation_rows` is one raw citations JSON string per answer, so answers
    with no citations still count in the denominator - a question nobody
    sourced is not the same as a question with one dominant source.
    """
    total = len(citation_rows)
    if not total:
        return None
    seen = [answer_domains(c) for c in citation_rows]
    present = collections.Counter(d for row in seen for d in row)
    if not present:
        return dict(answers=total, cited=0, domains=0, lead=None, top3=None,
                    hhi=None, score=None, band='no citations', own=0.0, top=[])
    ranked = present.most_common()
    lead = 100 * ranked[0][1] / total
    top3_names = {d for d, _ in ranked[:3]}
    top3 = 100 * sum(1 for row in seen if row & top3_names) / total
    appearances = sum(present.values())
    hhi = sum((n / appearances) ** 2 for _, n in ranked)
    score = round(100 * hhi)
    band = next(name for limit, name in BANDS if score < limit)
    return dict(
        answers=total,
        cited=sum(1 for row in seen if row),
        domains=len(present),
        lead=round(lead, 1),
        top3=round(top3, 1),
        hhi=round(hhi, 3),
        score=score,
        band=band,
        own=round(100 * sum(1 for row in seen if own_domain and own_domain in row) / total, 1),
        top=[(d, n, round(100 * n / total, 1)) for d, n in ranked[:5]],
    )


def by_question(scan_ids, own_domain=''):
    """One reading per buyer question, pooled over the given scans."""
    ids = (scan_ids,) if isinstance(scan_ids, int) else tuple(scan_ids)
    if not ids:
        return {}
    marks = ','.join('?' * len(ids))
    rows = db.all_('SELECT prompt, citations FROM answers WHERE scan_id IN (%s) '
                   'ORDER BY id' % marks, ids)
    grouped = collections.defaultdict(list)
    for r in rows:
        grouped[r['prompt']].append(r['citations'])
    return {q: measure(cites, own_domain) for q, cites in grouped.items()}


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--scan', type=int, help='scan id (default: the newest finished scan)')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    args = parser.parse_args(argv)

    db.init()
    scan = (db.one('SELECT * FROM scans WHERE id=?', (args.scan,)) if args.scan else
            db.one("SELECT * FROM scans WHERE status IN ('done','partial') "
                   'ORDER BY run_at DESC LIMIT 1'))
    if not scan:
        print('No finished scan in the database.')
        return 1
    ps = db.one('SELECT * FROM prompt_sets WHERE id=?', (scan['prompt_set_id'],))
    own = (ps['store_domain'] or '') if ps else ''
    readings = by_question(scan['id'], own)
    if args.json:
        print(json.dumps(dict(scan=scan['id'], store=own, questions=readings), indent=2))
        return 0

    print('Scan %d · %s · %d questions\n' % (scan['id'], own or 'no store', len(readings)))
    print('%-58s %6s %5s %5s %s' % ('BUYER QUESTION', 'SCORE', 'LEAD', 'DOMS', 'BAND'))
    for q, r in sorted(readings.items(), key=lambda kv: -(kv[1]['score'] or 0)):
        print('%-58s %6s %5s %5s %s' % (
            (q[:55] + '...') if len(q) > 58 else q,
            '-' if r['score'] is None else r['score'],
            '-' if r['lead'] is None else '%.0f%%' % r['lead'],
            r['domains'], r['band']))
        for d, n, pct in r['top'][:3]:
            print('    %-54s %d/%d answers (%.0f%%)' % (d, n, r['answers'], pct))
    print('\nScore is a Herfindahl index over cited domains: low means the sources are'
          '\nspread wide, high means a handful of domains carry the question. LEAD is the'
          '\nshare of answers citing the single most common domain, DOMS the distinct'
          '\ncount. It describes the answers we collected - it does not predict whether'
          '\nremediation would move anything. At five runs per question the sample is'
          '\nthin, so treat a single reading as indicative and watch it across scans.')
    return 0


if __name__ == '__main__':
    sys.exit(_main())
