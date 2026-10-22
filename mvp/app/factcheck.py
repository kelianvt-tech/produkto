"""Fact check: the last step before a draft reaches the Inbox.

Day 8 of mvp/content-agent/PLAN.md. Every sentence a draft writes is checked
against what the store (or, for comparisons, the other brand's page) states.
Anything not backed by a stated fact is replaced with an
"[ask merchant: ...]" placeholder, never kept as a guess.

Two passes:

  1. Numbers (free): every number in the prose - "50 ml", "2%", "30 days" -
     must appear in a source. A sentence with an unstated number is replaced.
  2. Claims (one helper-model call, a fraction of a cent): the model reads
     the numbered sentences beside the facts and marks each one stated,
     general (buying advice about no particular product; guides and comparisons only) or
     unsupported. Unsupported sentences are replaced.

The per-draft checks in drafts.py (spec rows, FAQ answers, comparison cells,
guide picks) still run first; this catches what they don't see: the prose.
"""
import html
import re

import llm

PLACEHOLDER = '[ask merchant: %s]'
# Draft types whose intros and advice may speak generally, about no particular product.
GENERAL_OK = ('guide', 'comparison', 'article')
# Designed articles (19 Oct 2026) may also state widely accepted category knowledge (drafts.ARTICLE_RULES).
KNOWLEDGE_OK = ('article',)
# Split after . ! ? but not after a list number ("2. Amalfi") or a lone initial.
_SENT = re.compile(r'(?<!\b\d\.)(?<!\b\d\d\.)(?<=[.!?])\s+(?=[A-Z0-9"“(])')
_LIST_NUM = re.compile(r'(^|\s)\d{1,2}[.)]\s')
_NUM = re.compile(r'\d+(?:[.,]\d+)?')
_TAG = re.compile(r'(<[^>]+>)')


def _norm(s):
    return re.sub(r'\s+', ' ', html.unescape(s or '').lower()).strip()


def sentences(text):
    """Sentences. A one- or two-word answer ("No.", "Yes, it is.") is joined to the sentence after it,
    so it's checked with its reason instead of being flagged alone."""
    parts = [s for s in _SENT.split(text.strip()) if s.strip()] if text and text.strip() else []
    out, hold = [], ''
    for p in parts:
        if len(p.split()) <= 2 and not p.endswith('?'):
            hold = (hold + ' ' + p).strip()
            continue
        out.append((hold + ' ' + p).strip() if hold else p)
        hold = ''
    if hold:
        if out:
            out[-1] = out[-1] + ' ' + hold
        else:
            out.append(hold)
    return out


def _numbers_ok(sentence, source):
    sentence = _LIST_NUM.sub(' ', ' ' + sentence)                 # "2. Amalfi..." is a list marker, not a claim
    for n in _NUM.findall(sentence):
        if not re.search(r'(?<![\d.,])%s(?![\d])' % re.escape(n), source):
            return False, n
    return True, None


class _Draft:
    """The prose fields of one draft as a flat list of sentences, so they can be checked and written back."""

    def __init__(self, result, draft_type):
        self.result, self.type = result, draft_type
        self.slots = []              # (getter, setter) per text field
        r = result
        if draft_type in ('product_fix', 'comparison', 'guide', 'article'):
            self._field(r, 'title')          # titles carry claims and banned words too
        if draft_type == 'product_fix':
            self._field(r, 'description_html', html_field=True)
        elif draft_type == 'faq':
            for f in r.get('faqs', []):
                self._field(f, 'answer')
        elif draft_type == 'comparison':
            self._field(r, 'intro')
            for s in r.get('summary', []):
                self._field(s, 'text')
        elif draft_type == 'guide':
            self._field(r, 'intro')
            for sec in r.get('sections', []):
                for i in range(len(sec['paragraphs'])):
                    self._field(sec['paragraphs'], i)
            for k in r.get('picks', []):
                self._field(k, 'text')
        elif draft_type == 'article':
            self._field(r, 'dek')
            for g in r.get('glance', []):
                self._field(g, 'text')
            for sec in r.get('sections', []):
                for i in range(len(sec.get('paragraphs') or [])):
                    self._field(sec['paragraphs'], i)
            for k in r.get('picks', []):
                self._field(k, 'text')
            for t in r.get('tables', []):
                for row in t.get('rows', []):
                    for i in range(len(row.get('cells') or [])):
                        self._field(row['cells'], i)
            for f in r.get('faqs', []):
                self._field(f, 'answer')
            if r.get('closing'):
                self._field(r['closing'], 'text')
        # Each entry: [container, key, html?, parts]; parts are text pieces split into sentences.
        self.items = []
        for container, key, is_html in self.slots:
            pieces = _TAG.split(container[key]) if is_html else [container[key]]
            parts = [p if (is_html and p.startswith('<')) else sentences(p) for p in pieces]
            self.items.append([container, key, is_html, parts])

    def _field(self, container, key, html_field=False):
        if (container[key] if isinstance(container, list) else container.get(key)):
            self.slots.append((container, key, html_field))

    def all(self):
        """[(item index, part index, sentence index, text)] for every sentence."""
        out = []
        for i, (_, _, _, parts) in enumerate(self.items):
            for j, p in enumerate(parts):
                if isinstance(p, list):
                    for k, s in enumerate(p):
                        out.append((i, j, k, s))
        return out

    def replace(self, ref, text):
        i, j, k = ref
        self.items[i][3][j][k] = html.escape(text, quote=False) if self.items[i][2] else text

    def write_back(self):
        for container, key, is_html, parts in self.items:
            text = ''.join(p if isinstance(p, str) else ' '.join(p) for p in parts) if is_html \
                else ' '.join(parts[0])
            container[key] = text


CLAIM_RULES = """You check sentences written for an online store's page against the facts the store states.

For each numbered sentence, answer:
- "stated": everything it says about a product is in that product's FACTS or its Description (same meaning; rewording, shortening and combining stated facts is fine).
- "voice": a line of brand tone or mood with nothing a buyer could check (e.g. "Considered enough to earn its place on your shelf", "Simple by design"). Allowed everywhere. A line that names a benefit, ingredient, result or property is NOT voice.
- "general": it is general buying advice that makes no claim about a particular product (allowed only when GENERAL ALLOWED is yes). Generic phrases like "for a simple routine" count; any health, performance, ingredient or certification claim does not.
- "knowledge": widely accepted, carefully worded category knowledge or standard how-to advice (e.g. "Vitamin C is an antioxidant", "Moisturiser goes on after cleansing", "Apply it to clean skin", "Patch-test a new product first"), allowed only when KNOWLEDGE ALLOWED is yes. This includes telling the reader how or when to use a store product in the ordinary way for its kind (a cleanser first, a moisturiser after). Not if it gives a number, a statistic, a study, a medical or disease claim, or a promise of results.
- "unsupported": it says something about a product that the facts don't state, or makes a health, safety, performance or certification claim the facts don't state.

For unsupported sentences, write ask_merchant: one short question the merchant could answer to make the sentence true or remove it. Leave it empty otherwise.
Be strict: when in doubt, unsupported."""

CLAIM_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdicts"],
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["n", "verdict", "ask_merchant"],
        "properties": {"n": {"type": "integer"},
                       "verdict": {"type": "string", "enum": ["stated", "voice", "general", "knowledge", "unsupported"]},
                       "ask_merchant": {"type": "string"}}}}},
}


def _facts_text(products, competitors):
    parts = []
    for p in products:
        facts = '\n'.join('  - %s: %s' % (f['label'], f['value']) for f in p['facts'])
        parts.append('%s (the store\'s product)\n%s\n  Description: %s'
                     % (p['title'], facts or '  (none)', ' '.join(p['description'])[:6000] or '(empty)'))
    for c in competitors or []:
        parts.append('%s %s (another brand)\n  Their page says: %s' % (c['brand'], c['product'], c['page_excerpt'][:1500]))
    return '\n\n'.join(parts)


def _banned(sentence, rules):
    """The first never-use word or never-name brand in a sentence (whole words, any case), or None."""
    low = _norm(sentence)
    for w in list(rules.get('never_words') or []) + list(rules.get('never_name') or []):
        w = _norm(w)
        if w and re.search(r'(?<!\w)%s(?!\w)' % re.escape(w), low):
            return w
    return None


def verified_sentences(result, draft_type, with_gaps=False):
    """Every sentence of a checked draft that holds no gap: what a later re-check can skip. with_gaps: every
    sentence at all (a change to one part must never re-question the parts it didn't touch)."""
    return {t.strip() for _, _, _, t in _Draft(result, draft_type).all() if with_gaps or PLACEHOLDER.split('%')[0] not in t}


def check(result, draft_type, products, competitors=(), usage=None, ai=True, rules=None, context=(), number_source='',
          verified=()):
    """Fact-check a draft in place. Returns the report also stored on result['fact_check'].

    rules (from setup): never_words and never_name are caught here for free; no_claims goes to the AI pass.
    context: the store's other products (articles, 19 Oct 2026): their pages are the store's own facts too
    (a set's page says which product follows which), shown to the AI pass as supporting facts.
    number_source: extra text numbers may come from (the buyer questions: "under £40" is the buyer's budget).
    verified: sentences already checked in an earlier version (an owner's change request re-checks only what changed)."""
    rules = rules or {}
    source = ' | '.join(_norm(number_source) for _ in [0]) + ' | ' + ' | '.join(_norm(f['value']) for p in products for f in p['facts']) + ' | ' + \
        ' | '.join(_norm(' '.join(p['description'])) for p in products) + ' | ' + \
        ' | '.join(_norm(c.get('page_excerpt', '')) for c in competitors or [])
    d = _Draft(result, draft_type)
    report = dict(sentences=0, numbers=[], claims=[], banned=[], ai_checked=False)
    asks = []
    remaining = []
    for i, j, k, s in d.all():
        report['sentences'] += 1
        word = _banned(s, rules)
        if word:
            q = 'rewrite without "%s": %s' % (word, s.strip()[:120])
            d.replace((i, j, k), PLACEHOLDER % q)
            report['banned'].append(dict(sentence=s, word=word))
            asks.append(dict(question='Rewrite without "%s"? The draft says: %s' % (word, s.strip()[:160]),
                             why='You asked never to use "%s".' % word))
            continue
        if s.strip().endswith('?') or s.strip() in verified:      # a question claims nothing; old sentences passed
            continue
        ok, n = _numbers_ok(s, source)
        if ok:
            remaining.append(((i, j, k), s))
            continue
        q = 'confirm "%s" in: %s' % (n, s.strip()[:120])
        d.replace((i, j, k), PLACEHOLDER % q)
        report['numbers'].append(dict(sentence=s, number=n))
        asks.append(dict(question='Can you confirm "%s"? The draft says: %s' % (n, s.strip()[:160]),
                         why='The number is not stated on the product page or in the catalog.'))
    if ai and remaining:
        listing = '\n'.join('%d. %s' % (n + 1, s) for n, (_, s) in enumerate(remaining))
        text = 'GENERAL ALLOWED: %s\nKNOWLEDGE ALLOWED: %s\n\nCLAIMS THE STORE NEVER MAKES (any sentence making one is unsupported, even if a fact seems to back it):\n%s\n\nFACTS:\n%s\n\nSENTENCES:\n%s' % (
            'yes' if draft_type in GENERAL_OK else 'no', 'yes' if draft_type in KNOWLEDGE_OK else 'no', '\n'.join('- ' + c for c in rules.get('no_claims') or []) or '(none)',
            _facts_text(products, competitors) + (('\n\nTHE STORE\'S OTHER PRODUCTS (also the store\'s own facts):\n'
                                                   + _facts_text(list(context), ())) if context else ''), listing)
        try:
            verdicts = llm.json_call(CLAIM_RULES, text, 'fact_check', CLAIM_SCHEMA, usage=usage)['verdicts']
            report['ai_checked'] = True
        except llm.LLMError:
            verdicts = []
        for v in verdicts:
            if not 1 <= v['n'] <= len(remaining):
                continue
            bad = v['verdict'] == 'unsupported' or (v['verdict'] == 'general' and draft_type not in GENERAL_OK) \
                or (v['verdict'] == 'knowledge' and draft_type not in KNOWLEDGE_OK)
            if not bad:
                continue
            ref, s = remaining[v['n'] - 1]
            q = v['ask_merchant'].strip() or 'is this true? "%s"' % s.strip()[:120]
            d.replace(ref, PLACEHOLDER % q)
            report['claims'].append(dict(sentence=s, question=q))
            asks.append(dict(question=q, why='The draft said: %s' % s.strip()[:160]))
    d.write_back()
    result['open_questions'] = list(result.get('open_questions') or []) + asks
    result['fact_check'] = report
    return report
