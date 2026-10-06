"""Write the buyer questions for ONE selected product, with a model.

No templates and no keyword lists. The model reads that product's own
Shopify record - title, type, price, options, description - and writes the
questions a real buyer would type into ChatGPT where this product should be
one of the answers. A sofa, a floor lamp and a trail shoe get genuinely
different questions because they come from different records.
"""

import json
import re

import config
import llm

INSTRUCTIONS = """You write the questions real shoppers type into ChatGPT when
they are looking to buy something. You will get one product from an online
store. Write {n} different questions where a good answer SHOULD include a
product like this one.

Rules:
- Write like a shopper, not a marketer: short, natural, the way people type.
- Never mention the brand or the product's name. The shopper doesn't know it.
- Base every question on what this specific product is: its category, its
  use, its materials, size, price level and the needs it serves. Use the
  facts given; do not invent features the product doesn't have.
- Make the {n} questions cover different angles a buyer really has, and give
  each one the tag that fits it:
    best      - "what's the best X" for the category
    budget    - a price limit
    spec      - a specific material, size, ingredient or feature
    use case  - a situation, need or problem to solve
    compare   - choosing between two options or types
  Use a different tag for each question where the product allows it.
- When a budget is natural, ALWAYS write the price with its currency symbol
  or code (for example "under £40", not "around 39"). A bare number gets read
  as an age or a size. If no currency is given below, leave prices out of the
  questions entirely and ask about the product another way.
- Each question must be something ChatGPT would answer by recommending
  specific products - not shops or stores."""

SPECIFIC_QUESTIONS = 2   # narrow questions per set, on top of the broad ones

TAGS = ["best", "budget", "spec", "use case", "compare", "specific"]

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "tag": {"type": "string", "enum": TAGS},
                },
                "required": ["question", "tag"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def _plain(html):
    t = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", t).strip()[:2500]


def product_brief(product, currency=None):
    raw = json.loads(product["raw_json"] or "{}")
    money = ('%s (%s)' % (currency.get('symbol') or currency.get('currency'), currency['currency'])
             if currency and currency.get('currency') else 'not published by the store')
    lines = [
        "Title: %s" % product["title"],
        "Store: %s" % product["store_domain"],
        "Currency: %s" % money,
        "Category (product_type): %s" % (raw.get("product_type") or "not stated"),
        "Price: %s" % (product["price"] or "not stated"),
        "Options: %s" % (", ".join(o for o in raw.get("options") or [] if o) or "none"),
        "Tags: %s" % (", ".join(raw.get("tags") or [])[:400] or "none"),
        "Description: %s" % (_plain(raw.get("body_html")) or "none"),
    ]
    return "\n".join(lines)


def generate(product, currency=None, n=5):
    """Return [(question, tag), ...] for this product."""
    out = llm.json_call(INSTRUCTIONS.format(n=n), product_brief(product, currency),
                        "buyer_questions", SCHEMA)
    seen, uniq = set(), []
    for item in out.get("questions") or []:
        q = (item.get("question") or "").strip()
        tag = (item.get("tag") or "").strip().lower()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append((q, tag if tag in TAGS else ""))
    if len(uniq) < n:
        raise llm.LLMError("The model returned %d usable questions instead of "
                           "%d. Try again." % (len(uniq), n))
    return uniq[:n]


def catalog_brief(products, currency=None):
    """Compact type summaries plus IDs/titles for explicit coverage decisions."""
    from collections import defaultdict
    import db
    groups=defaultdict(list)
    for p in products:
        groups[db.product_type(p)].append(p)
    money=(currency.get('symbol') or currency.get('currency')) if currency else ''
    out=['Store currency: '+(money or 'unknown — omit prices')]
    for category,rows in sorted(groups.items()):
        prices=[]
        for p in rows:
            try: prices.append(float(p['price']))
            except (TypeError,ValueError): pass
        facts=[]
        for p in rows[:5]:
            raw=json.loads(p['raw_json'] or '{}')
            facts.append({'title':p['title'],'options':raw.get('options') or [],
                          'facts':_plain(raw.get('body_html'))[:450]})
        out.append(json.dumps(dict(category=category,price_range=[min(prices),max(prices)] if prices else [],
            samples=facts,products=[dict(id=p['id'],title=p['title'],price=p['price']) for p in rows]),ensure_ascii=False))
    return '\n'.join(out)


def generate_clusters(products, currency=None, target=None, location='', topics=None, per_topic=4):
    import copy
    if not products:
        raise llm.LLMError('Include products before generating questions.')
    target=target or config.QUESTION_CLUSTERS
    schema=copy.deepcopy(SCHEMA)
    item=schema['properties']['questions']['items']
    item['properties'].update(cluster={'type':'string'},product_ids={'type':'array','items':{'type':'integer'}})
    item['required']+=['cluster','product_ids']
    instructions=INSTRUCTIONS.format(n='distinct').replace(
        'they are looking to buy something. You will get one product from an online\nstore. Write distinct different questions where a good answer SHOULD include a\nproduct like this one.',
        'they are looking to buy something. You will get a compact catalog summary. Identify distinct buyer needs shared by its products and write one question per buyer-need cluster.')
    instructions+='''\nUse the catalog, not a single product. Cover its distinct real buying needs without near-duplicate questions.
Return between %d and %d questions, aiming around %d only when justified by the catalog.
cluster: a short human-readable buying-need label. product_ids: every included product for which
this question is a reasonable test, based on its supplied facts. Never attach unrelated categories.
Use IDs from the supplied catalog only. Give each question at least one relevant product.
Coverage must be determined before seeing any answers. Do not claim measured search demand.
Do not invent product features, brands or question templates. If a feature is only stated for
one sample, do not assume it applies to every other product in the category.

Most questions should be broad, the common questions most shoppers ask. But ALSO write exactly
%d narrow questions tagged "specific": each one combines two or three concrete facts stated for ONE
product in the samples (a material, a dimension, a finish, a feature, a style) so that this
product is one of very few good answers. %s Still never name the brand or the product. Attach
only the product(s) that genuinely fit.''' % (config.QUESTION_CLUSTERS_MIN,config.QUESTION_CLUSTERS_MAX,target,
        SPECIFIC_QUESTIONS,
        ('You may add where the shopper is (%s) to at most one of them, when buying locally is natural.' % location)
        if location else '')
    lo,hi=config.QUESTION_CLUSTERS_MIN,config.QUESTION_CLUSTERS_MAX
    if topics:
        # The merchant chose the topics (onboarding step 5): write per_topic
        # broad questions under each one, cluster = the topic name verbatim.
        instructions+='''

The merchant has chosen these topics: %s. Ignore the question-count guidance above.
Write exactly %d broad questions for EACH topic, with cluster set to that topic's name exactly
as given. The %d "specific" questions also use the name of the topic they belong to. A topic
that no supplied product fits still gets its questions; attach the closest products.
Write every question in the same language as the topics, the way shoppers in that market type.
%s'''  % (
            json.dumps(topics,ensure_ascii=False),per_topic,SPECIFIC_QUESTIONS,
            ('Shoppers are in %s: about a third of the questions should mention that city or country '
             'naturally, but still ask for a PRODUCT, e.g. "which designer sofa should I buy in '
             'Barcelona?" or "best oak dining table with delivery in Spain". Never ask which shops '
             'or stores to visit, or where to buy in general: those answers name shops, not products.'
             % location) if location else '')
        lo,hi=len(topics),len(topics)*(per_topic+1)+SPECIFIC_QUESTIONS
    out=llm.json_call(instructions,catalog_brief(products,currency),'catalog_questions',schema)
    allowed={p['id'] for p in products};seen=set();result=[]
    for it in out.get('questions') or []:
        q=(it.get('question') or '').strip()
        ids=sorted(set(it.get('product_ids') or []))
        cluster=(it.get('cluster') or '').strip()
        if q and q.casefold() not in seen and ids and set(ids)<=allowed and cluster:
            result.append(dict(q=q,tag=it['tag'],cluster=cluster,products=ids))
            seen.add(q.casefold())
    # Broad questions are the ones most shoppers ask, but a small brand can
    # be absent from all of them - a 0% first scan (M&O Living, 2026-09-25)
    # tells the merchant nothing. The specific ones are where it has a real
    # chance, so the model is asked for SPECIFIC_QUESTIONS of them.
    if not lo<=len(result)<=hi:
        raise llm.LLMError('The generated questions did not pass the coverage checks. Try again.')
    # Broad questions first, the specific ones listed underneath them.
    if topics:
        # Grouped topic by topic in the merchant's order; within a topic the
        # specific questions sit under the broad ones.
        order={t.casefold():i for i,t in enumerate(topics)}
        return sorted(result,key=lambda r:(order.get(r['cluster'].casefold(),len(order)),r['tag']=='specific'))
    return sorted(result,key=lambda r:r['tag']=='specific')
