"""Build the guide pages into dist/ from the <main> sources in this folder.

    python3 build.py

Each guide gets the site's header and footer (taken from dist/privacy.html),
its own title, description and canonical tag, and JSON-LD (Article + FAQPage,
the FAQ read from the page's own <h3>/<p> pairs so the two never disagree).
Also writes dist/guides.html and refreshes sitemap.xml and llms.txt.
To add a guide: write <slug>.html here (a <main> block) and add it to GUIDES.
"""
import html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "dist")
SITE = "https://getprodukto.com/"

GUIDES = [  # newest first
    dict(slug="best-ai-visibility-tools-for-ecommerce",
         title="Best AI visibility tools for ecommerce brands in 2026",
         desc="Eleven AI visibility tools compared for ecommerce: Produkto, Profound, Peec AI, Promptwatch, Otterly, Scrunch, Semrush, Ahrefs, Glara, Sixthshop and AndromedAI. What each does, product-level features and prices.",
         blurb="Eleven tools compared: what each measures, product-level features and prices.",
         sub="Eleven tools that show whether AI recommends your brand or your products, compared on what they measure, how much of your catalog they cover, and what they cost. Every fact comes from each tool's own website.",
         date="2026-10-20",
         kicker="Comparison",
         term="We make Produkto, one of the tools below. Every claim about another tool comes from that tool's own website, checked on October 20, 2026.",
         term_name="Disclosure",
         term_html="<strong>We make Produkto</strong>, one of the tools below. Every claim about another tool comes from that tool's own website, checked on October 20, 2026, and each entry says who that tool suits best."),
    dict(slug="how-ai-recommends-products-856-answers",
         title="How AI recommends products: what 856 real answers show",
         desc="We collected 856 ChatGPT, Perplexity and Google AI Overview answers to a skincare brand's buyer questions. Half named no product, answers changed every run, and the assistants rarely agreed.",
         blurb="Original data: how often AI names products, how much answers change, and what it reads.",
         sub="We collected 856 answers from ChatGPT, Perplexity and Google AI Overviews to one skincare brand's buyer questions, and counted every product they named. Here is what the data shows.",
         date="2026-10-20",
         kicker="Research"),
    dict(slug="check-if-ai-recommends-your-products",
         title="How to check if ChatGPT recommends your products",
         desc="A step-by-step way to check whether ChatGPT, Perplexity and Google AI Overviews recommend your products: buyer questions, clean sessions, a tracking sheet, and how to read the results.",
         blurb="A step-by-step manual check, with a sheet to record it in.",
         sub="Ask the questions your buyers ask, in a clean session, several times, and record which products AI names. Here is how to do it by hand, step by step.",
         date="2026-10-20",
         term="To check whether ChatGPT recommends your products, ask it your buyers' questions without your brand name, in a fresh chat, several times on more than one day, and record which products it names, in what order and which sites it cites.",
         term_name="The check",
         term_html="<strong>To check whether ChatGPT recommends your products</strong>, ask it the questions your buyers ask, without your brand name, in a fresh chat. Ask each one several times, on more than one day, and record which products it names, in what order, and which sites it cites. Then do the same in Perplexity and Google."),
    dict(slug="what-is-ai-shopping-visibility",
         title="What is AI shopping visibility?",
         desc="AI shopping visibility is how often ChatGPT, Google AI Overviews and Perplexity name your products when shoppers ask what to buy. How it differs from SEO, how to measure it, and what to work on.",
         blurb="The definition, how it differs from SEO, and how to measure it.",
         sub="Shoppers now ask AI what to buy and get a few named products back. This guide explains what AI shopping visibility is, how it differs from SEO, how to measure it and what you can work on.",
         date="2026-10-20",
         term_name="AI shopping visibility",
         term_html="<strong>AI shopping visibility</strong> is how often AI assistants like ChatGPT, Google AI Overviews and Perplexity name your products when a shopper asks what to buy. It is measured per product, on the questions your buyers actually ask, and compared against the competing products AI recommends instead.",
         term="How often AI assistants like ChatGPT, Google AI Overviews and Perplexity name a store's products when a shopper asks what to buy, measured per product on buyers' questions."),
]
PRESS = dict(slug="press", title="Produkto press kit",
             desc="Descriptions, key facts, screenshots, logos and data for writing about Produkto, plus a free account for writers and reviewers.",
             sub="Everything you need to write about Produkto: descriptions to copy, key facts, screenshots, logos and original data. Writing a review? We'll give you a free account.",
             date="2026-10-21", kicker="Press kit", byline=False, schema="WebPage", listed=False)
STATIC = ["", "pricing", "guides", "privacy"]

CSS_V = 6
ORG = {"@type": "Organization", "name": "Produkto", "url": SITE,
       "logo": {"@type": "ImageObject", "url": SITE + "assets/produkto-mark.png"}}


def nice_date(iso):
    import datetime
    d = datetime.date.fromisoformat(iso)
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


AUTHOR = "Kelian Van Tulder"   # as on his LinkedIn


def page(base, main, title, desc, url, graph):
    p = re.sub(r'<main id="main">.*?</main>', lambda m: main.strip(), base, flags=re.S)
    p = re.sub(r"<title>.*?</title>", "<title>%s</title>" % html.escape(title), p)
    p = re.sub(r'<meta name="description" content="[^"]*">',
               '<meta name="description" content="%s">' % html.escape(desc), p)
    p = re.sub(r'<link rel="canonical" href="[^"]*">', '<link rel="canonical" href="%s">' % url, p)
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    head = '  <link rel="stylesheet" href="guide.css?v=%d">\n  <script type="application/ld+json">%s</script>\n' % (CSS_V, ld)
    return p.replace("</head>", head + "</head>", 1)


def fill(k, n):
    """Stretch the last contents cell so the 4-column grid has no empty cells."""
    cols = 3 if n % 4 and n % 3 == 0 else 4
    left = n % cols
    return ' class="toc-last" style="--span:%d"' % (cols - left + 1) if k == n - 1 and left else ""


def hero(g, minutes):
    byline = ('<p class="g-byline"><span class="g-avatar" aria-hidden="true">K</span><span>By <strong>%s</strong>, founder of Produkto · Updated %s · %d min read</span></p>'
              % (AUTHOR, nice_date(g["date"]), minutes)) if g.get("byline", True) else ""
    d = ""
    if g.get("term"):
        d = ('<div class="g-def"><p class="g-kicker">%s</p><p>%s</p></div>'
             % (html.escape(g["term_name"] + ("" if g["term_name"] == "Disclosure" else ", defined")), g["term_html"]))
    return """<section class="g-hero"><div class="g-hero-card">
      <p class="g-kicker">%s</p>
      <h1>%s</h1>
      <p class="g-sub">%s</p>
      <div class="g-ctas"><a class="btn btn-primary" href="index.html#request">Book a demo <svg class="icon icon-sm icon-shift" aria-hidden="true"><use href="#i-arrow-right"/></svg></a><a class="btn btn-secondary" href="guides.html">All guides</a></div>
      %s
      %s
    </div></section>""" % (g.get("kicker", "Guide"), html.escape(g["title"]), g["sub"], byline, d)


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def main():
    base = open(os.path.join(DIST, "privacy.html")).read()
    for g in GUIDES + [PRESS]:
        url = SITE + g["slug"]
        body = open(os.path.join(HERE, g["slug"] + ".html")).read()
        n = iter(range(1, 100))
        body = re.sub(r'<p class="g-num"></p>', lambda m: '<p class="g-num">%02d</p>' % next(n), body)
        body = body.replace('<p class="g-sec-sum"></p>', "")
        toc = re.findall(r'<section class="g-sec" id="([^"]+)" data-toc="([^"]+)"', body)
        toc_html = '<nav class="g-toc%s" aria-label="Contents">%s</nav>' % (" cols-3" if len(toc) % 4 and len(toc) % 3 == 0 else "", "".join(
            '<a href="#%s"%s><span>%02d</span>%s</a>' % (i, fill(k, len(toc)), k + 1, html.escape(t)) for k, (i, t) in enumerate(toc)))
        minutes = max(2, round(len(text(body).split()) / 220))
        others = [o for o in GUIDES if o is not g][:2]
        related = "".join('<a href="%s.html"><span>Guide</span><b>%s</b></a>' % (o["slug"], html.escape(o["title"])) for o in others)
        end = """<section class="g-end"><div class="g-cta"><div><h2>See which of your products AI recommends</h2>
      <p>Produkto measures your whole Shopify catalog in ChatGPT, Google AI Overviews and Perplexity, and shows who AI picks instead.</p></div>
      <div class="g-ctas"><a class="btn btn-primary" href="index.html#request">Book a demo <svg class="icon icon-sm icon-shift" aria-hidden="true"><use href="#i-arrow-right"/></svg></a></div></div>
      <div class="g-related">%s</div></section>""" % related
        main_html = '<main id="main" class="g">%s<div class="wrap" style="max-width:calc(var(--container) + 2*var(--gutter))">%s</div>%s%s</main>' % (
            hero(g, minutes), toc_html, body, end)
        faq = [{"@type": "Question", "name": text(q), "acceptedAnswer": {"@type": "Answer", "text": text(a)}}
               for q, a in re.findall(r"<summary>(.*?)</summary>\s*<p>(.*?)</p>", body, re.S)]
        if g.get("schema") == "WebPage":
            graph = [{"@type": "WebPage", "name": g["title"], "description": g["desc"], "url": url, "publisher": ORG}]
        else:
          graph = [{"@type": {"Research": "Report"}.get(g.get("kicker"), "Article"), "headline": g["title"], "description": g["desc"],
                  "datePublished": g["date"], "dateModified": g["date"],
                  "author": {"@type": "Person", "name": AUTHOR, "jobTitle": "Founder", "worksFor": ORG},
                  "publisher": ORG, "mainEntityOfPage": url}]
        if g.get("term"):
            if g["term_name"] not in ("The check", "Disclosure"):
                graph.append({"@type": "DefinedTerm", "name": g["term_name"], "description": g["term"], "url": url})
        if faq:
            graph.append({"@type": "FAQPage", "mainEntity": faq})
        out = page(base, main_html, g["title"] + " — Produkto", g["desc"], url, graph)
        open(os.path.join(DIST, g["slug"] + ".html"), "w").write(out)

    items = "\n".join(
        '<a href="%s.html"><b>%s</b><p>%s</p><span class="more">Read the guide →</span></a>' % (g["slug"], html.escape(g["title"]), html.escape(g["blurb"]))
        for g in GUIDES)
    index_main = """<main id="main" class="g"><section class="g-hero"><div class="g-hero-card">
      <p class="g-kicker">Guides</p><h1>Guides to AI shopping visibility</h1>
      <p class="g-sub">How AI assistants recommend products, and how ecommerce brands can measure it.</p>
    </div></section><div class="wrap"><div class="g-list">%s</div></div></main>""" % items
    graph = [{"@type": "CollectionPage", "name": "Produkto guides", "url": SITE + "guides",
              "hasPart": [{"@type": "Article", "headline": g["title"], "url": SITE + g["slug"]} for g in GUIDES]}]
    open(os.path.join(DIST, "guides.html"), "w").write(
        page(base, index_main, "Guides to AI shopping visibility — Produkto",
             "Guides for ecommerce brands on how AI assistants recommend products and how to measure it.",
             SITE + "guides", graph))

    urls = STATIC[:2] + [g["slug"] for g in GUIDES] + STATIC[2:] + ["press"]
    last = max(g["date"] for g in GUIDES)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += ["  <url><loc>%s%s</loc><lastmod>%s</lastmod></url>" % (SITE, u, last) for u in urls]
    open(os.path.join(DIST, "sitemap.xml"), "w").write("\n".join(sm + ["</urlset>", ""]))

    llms_path = os.path.join(DIST, "llms.txt")
    llms = open(llms_path).read()
    block = "## Guides\n\n" + "\n".join(
        "- [%s](%s%s): %s" % (g["title"], SITE, g["slug"], g["blurb"]) for g in GUIDES) + "\n\n"
    llms = re.sub(r"## Guides\n\n.*?\n\n", lambda m: block, llms, flags=re.S)
    open(llms_path, "w").write(llms)
    print("built", len(GUIDES), "guides")


if __name__ == "__main__":
    main()
