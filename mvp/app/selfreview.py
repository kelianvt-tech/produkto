"""Self-review: a second, cheap model call grades each draft before the merchant sees it.

Day 22 of mvp/content-agent/PLAN.md. The fact check (factcheck.py) already
decides whether each sentence is true to the store; this pass judges the rest:

  answers   does it answer the buyer questions it was written for?
  readable  does it read like a person wrote it for a buyer?
  voice     does it sound like the brand (the voice confirmed in setup)?

Each is scored 1-5, with up to three concrete problems and how to fix them.
A draft "passes" when every score is 4 or more. A draft that doesn't is
flagged in the Inbox ("Worth a closer look") with the problems listed in the
draft view; it is never blocked, and nothing is rewritten here: an automatic
rewrite could bring back the invented facts the fact check removed. Phase 4's
autopilot will only publish drafts that pass.

Costs one HELPER_MODEL call per draft (~0.05-0.1 cent).
"""
import re

import llm

PASS = 4

RULES = """You are the editor at an online store. Grade one draft before the owner sees it.
Score each from 1 (poor) to 5 (ready to publish):
- answers: does the draft directly answer the BUYER QUESTIONS (as far as its facts allow)? A draft that dodges them or buries the answer scores low.
- readable: plain, natural, easy for a shopper to scan; no filler, repetition, awkward phrasing or robotic lists. Score 3 or lower if a section opens with warm-up instead of the answer, if headings are labels rather than buyer questions (guides and FAQs), or if it uses stock AI phrasing ("elevate", "game-changer", "whether you're X or Y", "when it comes to", "in today's...", "look no further", "unlock", "delve", "the perfect addition").
- voice: matches the BRAND VOICE. If no voice is given, score how consistent and natural the tone is.
issues: up to 3 concrete problems, worst first, each with a specific fix ("Move the answer to the first sentence"). Do not raise missing facts or "[ask merchant: ...]" gaps: the owner fills those separately. Do not suggest adding claims, numbers or benefits. Empty if there is nothing worth fixing."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answers", "readable", "voice", "issues"],
          "properties": {"answers": {"type": "integer"}, "readable": {"type": "integer"}, "voice": {"type": "integer"},
                         "issues": {"type": "array", "items": {
                             "type": "object", "additionalProperties": False, "required": ["problem", "fix"],
                             "properties": {"problem": {"type": "string"}, "fix": {"type": "string"}}}}}}

LABELS = (('answers', 'Answers the buyer questions'), ('readable', 'Reads well'), ('voice', 'Sounds like you'))


def _plain(html_text):
    import html
    text = re.sub(r'</(p|li|h2|h3|tr)>', '\n', html_text or '')
    return re.sub(r'[ \t]+', ' ', html.unescape(re.sub(r'<script\b.*?</script>|<[^>]+>', ' ', text, flags=re.S))).strip()


def draft_text(result, draft_type):
    """What a shopper would read, as plain text. "[ask merchant: ...]" gaps are left out: the merchant fills
    them, and graded as text they'd make every draft with a gap "read badly"."""
    return re.sub(r'\s*\[ask merchant:[^\]]*\]', '', _draft_text(result, draft_type))


def _draft_text(result, draft_type):
    if draft_type == 'product_fix':
        specs = '\n'.join('%s: %s' % (r['label'], r['value']) for r in result.get('spec_table') or [])
        return 'Title: %s\n\n%s\n\n%s' % (result.get('title', ''), _plain(result.get('description_html')), specs)
    if draft_type == 'faq':
        return '\n\n'.join('Q: %s\nA: %s' % (f['question'], f['answer']) for f in result.get('faqs') or [])
    return ('%s\n\n' % result['title'] if result.get('title') else '') + _plain(result.get('html'))


def review(result, draft_type, brief, usage=None):
    """Grade a draft. Returns dict(scores, issues, passed), or None if the call fails (never blocks a draft)."""
    try:
        import content_setup
        voice = content_setup.voice_text(brief['store'])
    except Exception:                                   # noqa: BLE001
        voice = ''
    text = 'BUYER QUESTIONS:\n%s\n\nBRAND VOICE:\n%s\n\nDRAFT (%s):\n%s' % (
        '\n'.join('- ' + q['question'] for q in brief.get('questions') or []) or '(none)', voice or '(none given)',
        draft_type, draft_text(result, draft_type)[:6000])
    try:
        res = llm.json_call(RULES, text, 'self_review', SCHEMA, usage=usage, attempts=2)
        scores = {k: max(1, min(5, int(res[k]))) for k, _ in LABELS}
        issues = [dict(problem=str(i['problem']), fix=str(i['fix'])) for i in res.get('issues') or []][:3]
    except Exception:                                   # noqa: BLE001 - a failed review never blocks a draft
        return None
    return dict(scores=scores, issues=issues, passed=min(scores.values()) >= PASS)


def weakest(rev):
    """'Reads well 2/5' for the Inbox, or '' if the draft passed or was never reviewed."""
    if not rev or rev.get('passed'):
        return ''
    k, label = min(LABELS, key=lambda kl: rev['scores'].get(kl[0], 5))
    return '%s %d/5' % (label, rev['scores'][k])
