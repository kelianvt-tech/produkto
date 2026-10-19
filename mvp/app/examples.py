"""Examples: the agent learns a store's taste from the drafts it approved (18 Oct 2026).

No fine-tuning. Before writing a new draft, the agent is shown the store's last few
APPROVED drafts of the same kind (product fix, FAQ, comparison, guide). When the
merchant edited a draft before approving it, it sees both versions: what the agent
wrote and what the merchant changed it to. That edit is the clearest lesson there is.

Examples teach style and shape only. The writer is told never to take facts from
them: every fact still comes from the product it is writing about, and the fact
check runs as before. Rejected drafts are not used.

Free: no extra model call, just a longer prompt (a few hundred words, well under a
cent).
"""
import json
import re

import db

LIMIT = 3            # examples per draft
CHARS = 1200         # per text, so the prompt stays short
DONE = ('approved', 'scheduled', 'published')


def _text(body, draft_type):
    """The part of a draft that shows its style, as plain text."""
    if draft_type == 'product_fix':
        html = body.get('description_html') or body.get('html') or ''
        out = 'Title: %s\n%s' % (body.get('title', ''), html)
    elif draft_type == 'faq':
        out = '\n'.join('Q: %s\nA: %s' % (f.get('question', ''), f.get('answer', '')) for f in body.get('faqs') or []) \
            or body.get('html', '')
    else:
        out = 'Title: %s\n%s' % (body.get('title', ''), body.get('html', ''))
    out = re.sub(r'</(p|li|h\d|tr)>', '\n', out)
    out = re.sub(r'<[^>]+>', ' ', out)
    out = re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n', out)).strip()
    return out[:CHARS] + ('…' if len(out) > CHARS else '')


def approved(store, draft_type, limit=LIMIT):
    """[(agent text, final text, edited)] for the store's newest approved drafts of this kind."""
    rows = db.all_('SELECT id FROM content_drafts WHERE store_domain=? AND draft_type=? AND status IN (%s) '
                  'ORDER BY COALESCE(approved_at, updated_at) DESC LIMIT ?' % ','.join('?' * len(DONE)),
                  (store, draft_type) + DONE + (limit,))
    out = []
    for r in rows:
        vs = db.all_('SELECT body, author FROM content_draft_versions WHERE draft_id=? ORDER BY id', (r['id'],))
        if not vs:
            continue
        try:
            first, last = json.loads(vs[0]['body'] or '{}'), json.loads(vs[-1]['body'] or '{}')
        except ValueError:
            continue
        edited = any(v['author'] == 'merchant' for v in vs)
        a, b = _text(first, draft_type), _text(last, draft_type)
        if b:
            out.append((a, b, edited and a != b))
    return out


def section(store, draft_type):
    """A prompt section with the examples, or '' when the store has approved none yet."""
    if not store:
        return ''
    try:
        ex = approved(store, draft_type)
    except Exception:                                            # tables not made yet (fresh store, tests)
        return ''
    if not ex:
        return ''
    parts = []
    for i, (agent, final, edited) in enumerate(ex, 1):
        if edited:
            parts.append('Example %d. You wrote:\n%s\n\nThe owner changed it to, then approved:\n%s' % (i, agent, final))
        else:
            parts.append('Example %d. The owner approved this as written:\n%s' % (i, final))
    return ('\n\nEXAMPLES THIS STORE APPROVED (match their style, length and structure, and learn from the owner\'s '
            'changes. They are about OTHER products: never take a fact, number or claim from them; facts come only '
            'from the facts above):\n\n' + '\n\n---\n\n'.join(parts))
