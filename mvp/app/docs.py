"""How Produkto measures — the methodology questions, out of Support.

These are the questions a merchant asks while reading the dashboard, not while
something is broken, so they do not belong on a page about things going wrong.
Keeping them here also means the answers can be linked to from the panel that
raises them.

The tone rule from the rest of the product holds: say what is measured and what
it does not show. Nobody has demonstrated that fixing product pages moves AI
visibility, so nothing here promises it.
"""

import config

SECTIONS = [
    ("Why did my number move this week?",
     """<p>Some of it is real movement, and some of it is the AI itself. Ask the same
question twice and you can get two different answers — these models do not
answer identically every time, and the web results behind them change through
the day. Produkto asks each of your buyer questions several times per scan and
reports the share of answers your product appeared in, which smooths a lot of
that out but does not remove it.</p>
<p>So a few points of movement day to day is usually noise, not a change in how
you are doing. <b>Read the direction over a couple of weeks rather than the gap
between yesterday and today.</b> A move that holds across several days, or one
big enough to change your position against competitors, is the kind worth
acting on.</p>
<p>This is the most honest thing we can tell you about the measurement, and we
would rather say it here than have you act on a wobble.</p>"""),

    ("What counts as my product being mentioned?",
     """<p>The answer has to name a real, buyable product — a product name with a brand
behind it, or a link. Generic advice does not count. When an AI says "use a
gentle fragrance-free cleanser", that is not a recommendation of anyone's
product and it is filtered out everywhere, including from your competitors'
counts.</p>
<p>Matching is on the product, not just the brand: your catalog is compared
against what the answer names, so a mention of a different product of yours is
counted as that product, not this one.</p>"""),

    ("Where do the competitors come from?",
     """<p>Nowhere you choose. They are simply every product an AI named in answer to
your buyer questions — so the comparison is against whoever is actually being
recommended to your buyers, which is often not the competitor set you would
have picked.</p>"""),

    ("Why are my buyer questions frozen?",
     """<p>A trend only means something if the question behind it stayed the same.
Questions are fixed at your first scan so that this week's reading and last
month's are comparable. You can change them whenever you like — that starts a
new trend line, and the old readings are kept rather than rewritten.</p>"""),

    ("What is share of voice?",
     """<p>Of all the product mentions across your answers, the share that were yours.
Visibility tells you how often you appear at all; share of voice tells you how
much of the conversation you hold when you do. A product can be mentioned often
and still hold a small share, if the same answers name many competitors.</p>"""),

    ("Which AI engines are measured?",
     """<p>%s. Each buyer question is asked on each engine, several times, and every
answer is kept. The <b>Answers</b> tab shows them word for word — nothing on the
dashboard is calculated from anything you cannot go and read.</p>"""
     % ', '.join(config.engine_label(e) for e in ('chatgpt', 'ai-overview', 'perplexity'))),

    ("What Produkto does not tell you",
     """<p>It measures what AI answers say. It does not measure traffic, sales, or
whether a mention led to anything — and it cannot tell you that changing your
product pages will move these numbers, because that has not been demonstrated
by anyone yet. Treat it as a measurement of where you stand, not as a promise
about what fixes it.</p>"""),
]


def page(_q=None):
    from html import escape as E
    nav = ''.join('<li><a href="#%d">%s</a></li>' % (i, E(t))
                  for i, (t, _) in enumerate(SECTIONS))
    parts = ''.join('<section id="%d"><h2>%s</h2>%s</section>' % (i, E(t), b)
                    for i, (t, b) in enumerate(SECTIONS))
    body = """<div class="plain-page docs"><h1>How Produkto measures</h1>
<p class="page-description">What the numbers on your dashboard are, how they are collected, and what they do not show.</p>
<nav class="docs-nav" aria-label="On this page"><ul>%s</ul></nav>
%s
<p class="small">Something not answered here? <a href="/support">Ask us</a>.</p>
</div>""" % (nav, parts)
    return 200, body
