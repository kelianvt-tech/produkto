"""How much agent work a store's plan includes each month. Two allowances (Kelian, 15 Oct 2026):

  Page fixes  product page fixes and FAQs on product pages. Enough a month to work through a
              whole catalog over time: that is Produkto's difference (Promptwatch sells articles
              and doesn't fix product pages at all). They cost us under a cent each.
  Articles    buying guides and comparison pages, new pages on the store. Not included in
              Growth; bought in packs of 10 at $10 each, like Promptwatch's article dropdown.

  Starter ($99)   tracking only: no agent (like Promptwatch Essential, "No AEO Articles")
  Growth  ($297)  50 page fixes a month, no articles; article packs of 10-50 can be added
  Custom          agreed per store (300 fixes + 30 articles until set)

A page counts when the merchant APPROVES it, in the store's own calendar month.
Rejected drafts cost nothing, so the agent can offer more than the allowance;
approving stops at the limit. Stores with no paying owner (Kelian's demos) are unlimited.

Add-ons are set per store (content_settings 'extra_fixes', 'extra_articles') until a
Stripe add-on exists; the pricing page sends add-on buyers to Book a demo meanwhile.
"""
import datetime as dt

import db
import storetime

KINDS = {'product_fix': 'fixes', 'faq': 'fixes', 'collection': 'fixes', 'comparison': 'articles', 'guide': 'articles'}
LABEL = {'fixes': ('page fix', 'page fixes'), 'articles': ('article', 'articles')}
INCLUDED = {'starter': dict(fixes=0, articles=0), 'growth': dict(fixes=50, articles=0)}
CUSTOM_DEFAULT = dict(fixes=300, articles=30)
# Add-ons, matching the pricing page dropdowns (produkto-site/dist/pricing.html).
FIX_OPTIONS = (50, 100, 200, 300, 500)     # Growth page fixes a month; $1 a month per fix above 50
ARTICLE_PACKS = (10, 20, 30, 40, 50)       # articles a month; $10 a month each
PRICE_PER_FIX = 1
PRICE_PER_ARTICLE = 10


def kind_of(draft_type):
    return KINDS.get(draft_type, 'fixes')


def _owner(domain):
    """The first non-admin user who owns this store, or None."""
    return db.one('SELECT u.* FROM users u JOIN user_stores s ON s.user_id=u.id '
                  'WHERE s.store_domain=? AND COALESCE(u.is_admin,0)=0 ORDER BY u.id LIMIT 1', (domain,))


def plan(domain):
    """(plan key, display name). Stores with no paying owner (demos, admin) are 'admin'."""
    try:
        owner = _owner(domain)
    except Exception:                       # users table not made (tests, fresh install)
        owner = None
    if not owner:
        return 'admin', 'Admin'
    import billing
    key, name, _ = billing.plan_for(dict(owner))
    return key, name


def allowance(domain, kind):
    """Pages of this kind a month, or None for unlimited."""
    import content_setup
    key, _ = plan(domain)
    if key == 'admin':
        return None
    s = content_setup.get(domain)
    if key == 'custom':
        base = (s.get('custom') or {}).get(kind, CUSTOM_DEFAULT[kind])
    else:
        base = INCLUDED.get(key, INCLUDED['starter'])[kind]
    extra = int(s.get('extra_articles' if kind == 'articles' else 'extra_fixes') or 0)
    return int(base) + extra


def month_bounds(domain):
    tz = storetime.zone(domain)
    first = storetime.today(tz).replace(day=1)
    nxt = (first + dt.timedelta(days=32)).replace(day=1)
    return storetime.day_bounds(first, tz)[0], storetime.day_bounds(nxt, tz)[0]


def used(domain, kind):
    """Pages of this kind approved this calendar month (store time)."""
    start, end = month_bounds(domain)
    types = [t for t, k in KINDS.items() if k == kind]
    row = db.one('SELECT COUNT(*) n FROM content_drafts WHERE store_domain=? AND approved_at>=? AND approved_at<? '
                 "AND status IN ('approved','scheduled','published') AND draft_type IN (%s)" % ','.join('?' * len(types)),
                 (domain, start, end) + tuple(types))
    return row['n'] if row else 0


def left(domain, kind):
    """Pages of this kind still available this month, or None for unlimited."""
    a = allowance(domain, kind)
    return None if a is None else max(0, a - used(domain, kind))


def can_draft(domain, draft_type):
    """False when the plan includes none of this kind at all (e.g. articles switched off)."""
    return allowance(domain, kind_of(draft_type)) != 0


def monthly_total(domain):
    a = [allowance(domain, k) for k in LABEL]
    return None if None in a else sum(a)


def max_pace(domain):
    """Most pages a week the pace setting should offer (the month's pages over ~4 weeks)."""
    total = monthly_total(domain)
    return 7 if total is None else max(1, min(7, -(-total // 4)))


def summary(domain):
    """One plain line for the Content page."""
    parts = []
    for kind, (one, many) in LABEL.items():
        a = allowance(domain, kind)
        if a:
            parts.append('%d of %d %s' % (min(used(domain, kind), a), a, many))
    return ('%s used this month.' % ' · '.join(parts)) if parts else ''


def locked(domain):
    """True when the plan includes no agent work at all (Starter)."""
    return monthly_total(domain) == 0


UPGRADE = ('Catalog Optimization Agent is included from the Growth plan: 50 product page fixes a month, '
           'with buying guides and comparison pages available in packs of 10. <a href="/settings">See your plan</a>.')
