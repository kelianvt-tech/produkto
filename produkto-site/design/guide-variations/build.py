"""Build five design variations of the 'What is AI shopping visibility?' guide.

    python3 build.py   ->  v1-journal.html ... v5-field-guide.html + index.html

Same content (content.py) in every file; only the design changes.
Prototypes for choosing a direction, not the live site.
"""
import html, os
from content import *

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = "logo-dark.png"
LOGO_LIGHT = "logo-light.png"
e = html.escape


def page(title, fonts, css, body, dark_header=False):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?{fonts}&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{-webkit-text-size-adjust:100%;scroll-behavior:smooth}}
img{{display:block;max-width:100%}}
a{{color:inherit}}
:focus-visible{{outline:2px solid var(--focus,#2f5bd3);outline-offset:3px;border-radius:3px}}
@media (prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}*{{animation:none!important;transition:none!important}}}}
{css}
</style></head><body>
{body}
</body></html>"""


def stat_sources():
    seen, out = set(), []
    for _, _, src, url, _ in STATS:
        if url not in seen:
            seen.add(url); out.append((src, url))
    return out


# ---------------------------------------------------------------- V1 JOURNAL
def v1():
    css = """
:root{--paper:#f6f2ea;--ink:#0b1b35;--text:#25262b;--muted:#5d5a54;--rule:#d9d2c3;--accent:#9a3412;--focus:#9a3412}
::selection{background:#0b1b35;color:#f6f2ea}
body{background:var(--paper);color:var(--text);font:400 1.1875rem/1.68 'Source Serif 4',Georgia,serif;font-optical-sizing:auto}
.top{display:flex;justify-content:space-between;align-items:center;max-width:1180px;margin:0 auto;padding:22px 24px;border-bottom:1px solid var(--rule)}
.top img{height:26px;width:auto}
.top a.cta{font:600 .9rem/1 'Source Serif 4',serif;color:var(--ink);text-decoration:none;border-bottom:1.5px solid var(--ink);padding-bottom:3px}
.masthead{max-width:1180px;margin:0 auto;padding:72px 24px 40px;display:grid;grid-template-columns:1fr minmax(0,760px) 1fr}
.masthead>*{grid-column:2}
.section-name{font:italic 400 1.05rem/1 'Newsreader',serif;color:var(--accent)}
h1{font:500 clamp(2.6rem,6vw,4.6rem)/1.02 'Newsreader',serif;color:var(--ink);letter-spacing:-.025em;text-wrap:balance}
.dek{font:italic 400 clamp(1.2rem,2vw,1.45rem)/1.45 'Newsreader',serif;color:var(--muted);margin-top:22px;text-wrap:pretty}
.byline{margin-top:30px;font-size:.95rem;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap}
.byline b{color:var(--ink);font-weight:600}
.article{max-width:1180px;margin:0 auto;padding:0 24px 80px;display:grid;grid-template-columns:1fr minmax(0,680px) 1fr;column-gap:48px}
.article>*{grid-column:2}
.article p+p{margin-top:1.05em}
.lede::first-letter{float:left;font:500 5.2em/.82 'Newsreader',serif;color:var(--ink);padding:.06em .1em 0 0}
.lede{font-size:1.25rem}
h2{font:500 clamp(1.7rem,3vw,2.2rem)/1.15 'Newsreader',serif;color:var(--ink);letter-spacing:-.015em;margin:2.4em 0 .7em;text-wrap:balance}
h3{font:600 1.1rem/1.3 'Source Serif 4',serif;color:var(--ink);margin:1.6em 0 .3em}
.rule{border:0;border-top:1px solid var(--rule);margin:3em 0 0}
.pull{grid-column:1/4;margin:2.2em 0;padding:0 0 0;text-align:center;font:italic 400 clamp(1.6rem,3.4vw,2.5rem)/1.25 'Newsreader',serif;color:var(--ink);max-width:900px;justify-self:center;text-wrap:balance}
.pull::before,.pull::after{content:"";display:block;width:56px;height:1px;background:var(--accent);margin:0 auto 28px}
.pull::after{margin:28px auto 0}
.with-note{position:relative}
.note{font:400 .84rem/1.5 'Source Serif 4',serif;color:var(--muted)}
.note b{display:block;font:500 1.6rem/1 'Newsreader',serif;color:var(--ink);margin-bottom:6px}
.note a{color:var(--muted)}
@media(min-width:1100px){.note{position:absolute;left:calc(100% + 48px);width:220px;top:.3em}}
@media(max-width:1099px){.note{display:block;margin:14px 0 6px;padding:14px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}}
table{width:100%;border-collapse:collapse;font-size:.98rem;margin:1.4em 0}
caption{text-align:left;font:italic .95rem 'Newsreader',serif;color:var(--muted);margin-bottom:8px}
th,td{text-align:left;vertical-align:top;padding:12px 14px 12px 0;border-bottom:1px solid var(--rule)}
thead th{font:600 .82rem/1.3 'Source Serif 4',serif;letter-spacing:.04em;text-transform:uppercase;color:var(--ink);border-bottom:1.5px solid var(--ink)}
td.ours{color:var(--ink);font-weight:600}
.tablewrap{overflow-x:auto;grid-column:1/4;max-width:900px;justify-self:center;width:100%}
ol.steps{counter-reset:s;list-style:none;margin-top:1em}
ol.steps li{counter-increment:s;display:grid;grid-template-columns:2.2em 1fr;margin:0 0 1.1em}
ol.steps li::before{content:counter(s);font:italic 500 1.5rem/1.2 'Newsreader',serif;color:var(--accent)}
ol.steps b{color:var(--ink)}
.exhibit{grid-column:1/4;max-width:900px;width:100%;justify-self:center;margin:2em 0;border-top:1.5px solid var(--ink);border-bottom:1px solid var(--rule);padding:24px 0}
.exhibit .q{font:italic 1.25rem/1.4 'Newsreader',serif;color:var(--ink)}
.exhibit .a{margin:10px 0 14px;color:var(--muted)}
.exhibit li{list-style:none;display:grid;grid-template-columns:2em 1fr;padding:9px 0;border-top:1px dotted var(--rule)}
.exhibit li.yours b{background:linear-gradient(transparent 60%,#f2d7b8 60%)}
.exhibit li.missing{color:var(--muted)}
.exhibit li.missing b{text-decoration:line-through;text-decoration-color:var(--accent)}
.exhibit small{display:block;color:var(--muted);font-size:.92rem}
.exhibit .cap{font:italic .9rem 'Newsreader',serif;color:var(--muted);margin-top:12px}
dl.terms{margin-top:1em}
dl.terms dt{font:600 1.05rem 'Source Serif 4',serif;color:var(--ink);margin-top:1em}
dl.terms dd{margin-left:0}
.faq details{border-bottom:1px solid var(--rule);padding:16px 0}
.faq summary{cursor:pointer;font:500 1.25rem/1.35 'Newsreader',serif;color:var(--ink);list-style:none}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:" +";color:var(--accent)}
.faq details[open] summary::after{content:" \\2013"}
.faq p{margin-top:10px}
.end{margin-top:3.4em;padding-top:28px;border-top:1.5px solid var(--ink);display:flex;justify-content:space-between;gap:24px;align-items:baseline;flex-wrap:wrap}
.end p{font:italic 1.3rem/1.4 'Newsreader',serif;color:var(--ink);max-width:28ch}
.end a{font:600 1rem 'Source Serif 4',serif;color:var(--paper);background:var(--ink);text-decoration:none;padding:14px 22px;border-radius:2px}
.end a:hover{background:#1c3260}
.sources{margin-top:2.6em;font-size:.85rem;color:var(--muted)}
.sources li{margin:.3em 0 0 1.2em}
"""
    s = STATS
    def note(i):
        v, t, src, url, _ = s[i]
        return f'<span class="note"><b>{e(v)}</b>{e(t)} <a href="{url}">{e(src)}</a></span>'
    seo = "".join(f"<tr><th>{e(a)}</th><td>{e(b)}</td><td>{e(c)}</td><td class='ours'>{e(d)}</td></tr>" for a, b, c, d in SEO_ROWS)
    steps = "".join(f"<li><span><b>{e(a)}.</b> {e(b)}</span></li>" for a, b in STEPS)
    ex = "".join(f"<li class='{st}'><span>{r}</span><span><b>{e(n)}</b><small>{e(t)}</small></span></li>" for r, n, t, st in EXAMPLE)
    metrics = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in METRICS)
    work = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in WORK)
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in FAQ)
    src = "".join(f'<li><a href="{u}">{e(n)}</a></li>' for n, u in stat_sources())
    body = f"""
<header class="top"><a href="#"><img src="{LOGO}" alt="Produkto" style="height:22px;width:auto"></a><a class="cta" href="#">Book a demo</a></header>
<div class="masthead">
  <h1>{e(TITLE)}</h1>
  <p class="dek">{e(DEK)}</p>
  <p class="byline"><span>By <b>{AUTHOR}</b></span><span>·</span><span>{DATE}</span><span>·</span><span>6 minute read</span></p>
</div>
<article class="article">
  <hr class="rule">
  <p class="lede" style="margin-top:2em"><strong>{e(DEFINITION)}</strong> {e(DEFINITION_MORE)}</p>
  <p>{e(POINTS[0])} {e(POINTS[1])}</p>
  <p class="with-note">{e(POINTS[3])} It goes by other names too: AEO, GEO, AI search visibility, LLM visibility. “Shopping” narrows it to the thing a store sells.{note(5)}</p>
  <h2 id="why-now">Why it matters now</h2>
  <p class="with-note">Shoppers are already doing it. Adobe found that 42% of consumers have used an AI assistant to shop online, and that AI-driven traffic to US retail sites grew 127% year over year in August 2026.{note(0)}</p>
  <p class="with-note">Those visitors arrive ready: in July 2026 they converted 60% better than other traffic. McKinsey puts AI-powered search use at about half of consumers and projects $750 billion in US revenue flowing through it by 2028.{note(4)}</p>
  <p>Meanwhile the click is shrinking. When Google shows an AI summary, Pew found people click a search result on 8% of visits, against 15% without one. For a store, the products named in the answer are the shortlist.</p>
  <blockquote class="pull">When the shopper reads the answer instead of clicking, the products named in it are the shortlist.</blockquote>
  <h2 id="vs-seo">How it differs from SEO</h2>
  <p>{e(SEO_RULE)}</p>
  <div class="tablewrap"><table><caption>Three ways of being found</caption><thead><tr><th></th><th>SEO</th><th>AEO / GEO</th><th>AI shopping visibility</th></tr></thead><tbody>{seo}</tbody></table></div>
  <p>{e(SEO_PARA)}</p>
  <h2 id="how-ai-chooses">How AI assistants choose products</h2>
  <p>With web search on, an assistant reads a handful of pages and writes its answer from them. What those pages state decides which products it can recommend.</p>
  <ol class="steps">{steps}</ol>
  <figure class="exhibit"><p class="q">“{e(EXAMPLE_Q)}”</p><p class="a">{e(EXAMPLE_A)}</p><ol>{ex}</ol><figcaption class="cap">An illustrative answer. The products are invented.</figcaption></figure>
  <h2 id="measure">How to measure it</h2>
  <p>Ask your buyer questions several times, on more than one assistant, and track four numbers per product over time.</p>
  <dl class="terms">{metrics}</dl>
  <p style="margin-top:1.2em">{e(MEASURE_RULE)}</p>
  <h2 id="work-on">What you can work on</h2>
  <p>Most of it is product data: making each page state the facts a shopper’s question depends on, and being mentioned on the sites AI reads.</p>
  <dl class="terms">{work}</dl>
  <p style="margin-top:1.2em"><em>{e(HONEST)}</em></p>
  <h2 id="faq">Questions people ask</h2>
  <div class="faq">{faq}</div>
  <div class="end"><p>See which of your products AI recommends.</p><a href="#">Book a demo</a></div>
  <ol class="sources">{src}</ol>
</article>"""
    return page("Journal | " + TITLE, "family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400;1,6..72,500&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400", css, body)


# ---------------------------------------------------------- V2 RESEARCH REPORT
def v2():
    css = """
:root{--bg:#fbfbfa;--ink:#0b1b35;--text:#1d2433;--muted:#5b6475;--line:#e3e5e8;--blue:#2448c4;--soft:#eef1f8;--focus:#2448c4}
::selection{background:#d6defa}
body{background:var(--bg);color:var(--text);font:400 1.0625rem/1.65 'IBM Plex Sans',system-ui,sans-serif}
.bar{position:sticky;top:0;z-index:10;background:rgba(251,251,250,.94);backdrop-filter:saturate(1.4) blur(8px);border-bottom:1px solid var(--line)}
.bar .in{max-width:1240px;margin:0 auto;padding:14px 28px;display:flex;align-items:center;justify-content:space-between}
.bar img{height:24px;width:auto}
.bar a.cta{font:500 .9rem 'IBM Plex Sans';background:var(--ink);color:#fff;padding:9px 16px;border-radius:6px;text-decoration:none}
.progress{position:absolute;left:0;bottom:-1px;height:2px;background:var(--blue);width:0}
.wrap{max-width:1240px;margin:0 auto;padding:0 28px;display:grid;grid-template-columns:220px minmax(0,1fr);gap:64px}
.head{grid-column:1/-1;padding:72px 0 40px;border-bottom:1px solid var(--ink);display:grid;grid-template-columns:220px minmax(0,1fr);gap:64px}
.head .meta{font:400 .85rem/1.6 'IBM Plex Sans';color:var(--muted);padding-top:12px}
.head .meta b{display:block;color:var(--ink);font-weight:600}
h1{font:600 clamp(2.4rem,5.2vw,4rem)/1.04 'IBM Plex Sans';color:var(--ink);letter-spacing:-.03em;max-width:16ch;text-wrap:balance}
.dek{font-size:1.3rem;line-height:1.5;color:var(--muted);margin-top:20px;max-width:46ch}
.def{margin-top:32px;font:400 1.35rem/1.5 'IBM Plex Serif',serif;color:var(--ink);max-width:56ch}
.def strong{font-weight:600}
nav.toc{position:sticky;top:84px;align-self:start;padding-top:40px;font-size:.88rem}
nav.toc p{font-weight:600;color:var(--ink);margin-bottom:10px}
nav.toc a{display:block;padding:6px 0 6px 12px;color:var(--muted);text-decoration:none;border-left:1px solid var(--line)}
nav.toc a.on{color:var(--ink);border-left:2px solid var(--blue);padding-left:11px;font-weight:500}
main{padding:40px 0 96px;min-width:0}
section{padding:32px 0 40px;border-bottom:1px solid var(--line);scroll-margin-top:90px}
h2{font:600 1.75rem/1.2 'IBM Plex Sans';color:var(--ink);letter-spacing:-.02em;margin-bottom:16px}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:40px;align-items:start}
.prose p+p{margin-top:1em}
.prose ol{margin:1em 0 0 1.2em}.prose li{margin:.45em 0;padding-left:.2em}
.prose b,.prose strong{color:var(--ink)}
figure.fig{margin:8px 0 0}
figure.fig figcaption{font-size:.85rem;color:var(--muted);margin-top:10px;line-height:1.5}
figure.fig figcaption b{color:var(--ink)}
.chart{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px}
.chart svg{width:100%;height:auto;display:block}
.chart text{font-family:'IBM Plex Sans';fill:var(--text)}
.statlist{margin-top:18px;border-top:1px solid var(--line)}
.statlist div{display:grid;grid-template-columns:7.5em 1fr;gap:16px;padding:12px 0;border-bottom:1px solid var(--line);font-size:.95rem}
.statlist b{font:600 1.15rem/1.3 'IBM Plex Sans';color:var(--ink);font-variant-numeric:tabular-nums}
.statlist a{color:var(--muted);font-size:.85rem}
table{width:100%;border-collapse:collapse;font-size:.93rem;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:12px 14px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
thead th{background:var(--soft);font-weight:600;color:var(--ink);font-size:.85rem}
.hl{background:#f3f6fd}
thead .hl{background:var(--ink);color:#fff}
tbody th{font-weight:600;color:var(--ink);width:16%}
.tw{overflow-x:auto;margin-top:8px}
.tw table{min-width:640px}
.answer{background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.answer .q{background:var(--soft);padding:14px 18px;font-weight:500;color:var(--ink)}
.answer .a{padding:14px 18px 6px;color:var(--muted)}
.answer ol{list-style:none;padding:0 18px 14px}
.answer li{display:grid;grid-template-columns:28px 1fr auto;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--line);font-size:.93rem}
.answer li span:first-child{font-variant-numeric:tabular-nums;color:var(--muted)}
.answer li b{color:var(--ink)}
.answer small{display:block;color:var(--muted)}
.tag{font-size:.75rem;font-weight:600;padding:3px 8px;border-radius:5px;background:var(--soft);color:var(--muted)}
li.yours .tag{background:var(--blue);color:#fff}
li.missing b{color:var(--muted)}
li.missing .tag{background:#fdecea;color:#a1271b}
dl.def-list{display:grid;grid-template-columns:12em 1fr;border-top:1px solid var(--line);margin-top:8px}
dl.def-list dt,dl.def-list dd{padding:12px 0;border-bottom:1px solid var(--line)}
dl.def-list dt{font-weight:600;color:var(--ink)}
.note{margin-top:20px;padding:16px 18px;background:var(--soft);border-radius:8px;color:var(--ink)}
.faq details{border-bottom:1px solid var(--line)}
.faq summary{cursor:pointer;padding:16px 0;font-weight:600;color:var(--ink);display:flex;justify-content:space-between;list-style:none}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"";width:10px;height:10px;border-right:1.5px solid var(--blue);border-bottom:1.5px solid var(--blue);transform:rotate(45deg);transition:transform .2s}
.faq details[open] summary::after{transform:rotate(-135deg)}
.faq p{padding:0 0 16px;max-width:62ch}
.cta-band{margin-top:48px;display:flex;justify-content:space-between;align-items:center;gap:24px;padding:28px;border:1px solid var(--ink);border-radius:10px}
.cta-band p{font:600 1.3rem/1.3 'IBM Plex Sans';color:var(--ink)}
.cta-band a{background:var(--ink);color:#fff;text-decoration:none;padding:12px 20px;border-radius:6px;font-weight:500;white-space:nowrap}
.refs{margin-top:28px;font-size:.82rem;color:var(--muted)}.refs li{margin:.3em 0 0 1.4em}
@media(max-width:960px){.wrap,.head{grid-template-columns:1fr;gap:0}nav.toc{display:none}.cols{grid-template-columns:1fr;gap:24px}dl.def-list{grid-template-columns:1fr}dl.def-list dt{border-bottom:0;padding-bottom:0}.cta-band{flex-direction:column;align-items:flex-start}}
"""
    # Figure 1: horizontal bars for the stats that are shares of people/visits (same unit: percent)
    bars = [("Consumers who have used AI assistants to shop (Adobe, Jul 2026)", 42),
            ("Consumers using AI-powered search (McKinsey)", 50),
            ("Google visits with a result click, no AI summary (Pew)", 15),
            ("Google visits with a result click, with an AI summary (Pew)", 8)]
    rows = ""
    for i, (lab, v) in enumerate(bars):
        y = 18 + i * 54
        col = "#2448c4" if i < 2 else ("#0b1b35" if i == 2 else "#7f8db3")
        rows += (f'<text x="0" y="{y}" font-size="13">{e(lab)}</text>'
                 f'<rect x="0" y="{y+8}" width="{v*6}" height="18" rx="3" fill="{col}"/>'
                 f'<text x="{v*6+8}" y="{y+22}" font-size="13" font-weight="600">{v}%</text>')
    chart = f'<svg viewBox="0 0 420 225" role="img" aria-label="Bar chart: 42% of consumers have used AI assistants to shop; about 50% use AI-powered search; Google visits with a result click: 15% without an AI summary, 8% with one.">{rows}</svg>'
    statl = "".join(f'<div><b>{e(v)}</b><span>{e(t)} <a href="{u}">{e(src)}</a></span></div>' for v, t, src, u, _ in STATS)
    seo = "".join(f"<tr><th>{e(a)}</th><td>{e(b)}</td><td>{e(c)}</td><td class='hl'>{e(d)}</td></tr>" for a, b, c, d in SEO_ROWS)
    steps = "".join(f"<li><b>{e(a)}.</b> {e(b)}</li>" for a, b in STEPS)
    ex = "".join(f"<li class='{st}'><span>{r}</span><span><b>{e(n)}</b><small>{e(t)}</small></span><span class='tag'>{ {'named':'Named','yours':'Yours','missing':'Missing'}[st] }</span></li>" for r, n, t, st in EXAMPLE)
    metrics = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in METRICS)
    work = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in WORK)
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in FAQ)
    toc = "".join(f'<a href="#{i}">{e(h)}</a>' for i, h in SECTIONS)
    src = "".join(f'<li><a href="{u}">{e(n)}</a></li>' for n, u in stat_sources())
    body = f"""
<div class="bar"><div class="in"><img src="{LOGO}" alt="Produkto" style="height:24px;width:auto"><a class="cta" href="#">Book a demo</a></div><div class="progress" id="prog"></div></div>
<div class="wrap">
  <header class="head"><div class="meta"><b>Guide</b>{DATE}<br>By {AUTHOR}<br>6 minute read</div>
    <div><h1>{e(TITLE)}</h1><p class="dek">{e(DEK)}</p><p class="def"><strong>{e(DEFINITION)}</strong> {e(DEFINITION_MORE)}</p></div></header>
  <nav class="toc" aria-label="Contents"><p>On this page</p>{toc}</nav>
  <main>
    <section id="short"><h2>The short version</h2><div class="prose"><ol>{"".join(f"<li>{e(p)}</li>" for p in POINTS)}</ol></div></section>
    <section id="why-now"><h2>Why it matters now</h2><div class="cols"><div class="prose"><p>Shoppers are already using AI to decide what to buy, the visitors it sends convert well, and fewer people click through to search results when an AI answer sits on top.</p><div class="statlist">{statl}</div></div>
      <figure class="fig"><div class="chart">{chart}</div><figcaption><b>Figure 1.</b> Share of consumers, or of Google visits, by source. Sources linked on the left.</figcaption></figure></div></section>
    <section id="vs-seo"><h2>How it differs from SEO</h2><div class="prose"><p>{e(SEO_RULE)}</p></div><figure class="fig"><div class="tw"><table><thead><tr><th></th><th>SEO</th><th>AEO / GEO</th><th class="hl">AI shopping visibility</th></tr></thead><tbody>{seo}</tbody></table></div><figcaption><b>Table 1.</b> Three ways of being found.</figcaption></figure><div class="prose" style="margin-top:18px;max-width:62ch"><p>{e(SEO_PARA)}</p></div></section>
    <section id="how-ai-chooses"><h2>How AI assistants choose products</h2><div class="cols"><div class="prose"><p>With web search on, an assistant reads a handful of pages and writes its answer from them.</p><ol>{steps}</ol></div>
      <figure class="fig"><div class="answer"><p class="q">{e(EXAMPLE_Q)}</p><p class="a">{e(EXAMPLE_A)}</p><ol>{ex}</ol></div><figcaption><b>Figure 2.</b> An illustrative answer. The products are invented.</figcaption></figure></div></section>
    <section id="measure"><h2>How to measure it</h2><div class="prose" style="max-width:62ch"><p>Ask your buyer questions several times, on more than one assistant, and track four numbers per product over time.</p></div><dl class="def-list">{metrics}</dl><p class="note">{e(MEASURE_RULE)}</p></section>
    <section id="work-on"><h2>What you can work on</h2><div class="prose" style="max-width:62ch"><p>Most of it is product data: making each page state the facts a shopper’s question depends on, and being mentioned on the sites AI reads.</p></div><dl class="def-list">{work}</dl><p class="note">{e(HONEST)}</p></section>
    <section id="faq" style="border-bottom:0"><h2>Questions people ask</h2><div class="faq">{faq}</div>
      <div class="cta-band"><p>See which of your products AI recommends.</p><a href="#">Book a demo</a></div><ol class="refs">{src}</ol></section>
  </main>
</div>
<script>
(()=>{{const p=document.getElementById('prog'),links=[...document.querySelectorAll('nav.toc a')],secs=links.map(a=>document.querySelector(a.getAttribute('href')));
addEventListener('scroll',()=>{{const h=document.documentElement;p.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight)*100)+'%';
let cur=0;secs.forEach((s,i)=>{{if(s.getBoundingClientRect().top<140)cur=i}});links.forEach((a,i)=>a.classList.toggle('on',i===cur))}},{{passive:true}})}})();
</script>"""
    return page("Research report | " + TITLE, "family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;600", css, body)


# ---------------------------------------------------------------- V3 POSTER
def v3():
    css = """
:root{--navy:#0b1b35;--deep:#050f22;--paper:#f4f3ef;--ink:#0b1b35;--text:#1b2230;--muted:#5a6273;--signal:#e8590c;--line:#d8d8d2;--focus:#e8590c}
::selection{background:var(--signal);color:#fff}
body{background:var(--paper);color:var(--text);font:400 1.125rem/1.6 'Geist',system-ui,sans-serif}
.top{position:absolute;inset:0 0 auto 0;display:flex;justify-content:space-between;align-items:center;padding:24px clamp(20px,4vw,48px);z-index:2}
.top img{height:24px;width:auto}
.top a{color:#fff;font-weight:500;font-size:.95rem;text-decoration:none;border:1px solid rgba(255,255,255,.35);padding:9px 16px;border-radius:999px}
.top a:hover{background:#fff;color:var(--navy)}
.hero{background:var(--deep);color:#fff;min-height:min(92vh,860px);display:flex;flex-direction:column;justify-content:flex-end;padding:120px clamp(20px,4vw,48px) 56px}
.hero h1{font:600 clamp(3rem,10.5vw,8.4rem)/.9 'Geist';letter-spacing:-.04em;max-width:11ch}
.hero h1 em{font-style:normal;color:var(--signal)}
.hero .below{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:40px;margin-top:48px;align-items:end;border-top:1px solid rgba(255,255,255,.2);padding-top:28px}
.hero .def{font:400 clamp(1.25rem,2.2vw,1.7rem)/1.4 'Geist';color:rgba(255,255,255,.92);max-width:34ch}
.hero .meta{font-size:.92rem;color:rgba(255,255,255,.6);text-align:right}
.band{padding:clamp(72px,10vw,140px) clamp(20px,4vw,48px)}
.statement{font:500 clamp(2rem,5.4vw,4.4rem)/1.08 'Geist';letter-spacing:-.035em;color:var(--ink);max-width:20ch;text-wrap:balance}
.statement .n{color:var(--signal)}
.statement a{font-size:.3em;letter-spacing:0;font-weight:400;color:var(--muted);vertical-align:super;text-decoration:none;margin-left:.15em}
.statement a:hover{color:var(--ink)}
.stack>*+*{margin-top:clamp(48px,7vw,96px)}
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:clamp(32px,6vw,96px);align-items:start}
h2{font:600 clamp(2rem,4.4vw,3.4rem)/1.02 'Geist';letter-spacing:-.035em;color:var(--ink);text-wrap:balance}
.lead{font-size:1.3rem;line-height:1.5;color:var(--text);max-width:46ch}
.lead+p,.body p+p{margin-top:1em}
.body{max-width:62ch}
.navy{background:var(--navy);color:#fff}
.navy h2{color:#fff}.navy .lead{color:rgba(255,255,255,.85)}
.compare{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:48px;border-top:1px solid rgba(255,255,255,.25)}
.compare div{padding:24px 24px 24px 0}
.compare div+div{padding-left:24px;border-left:1px solid rgba(255,255,255,.18)}
.compare h3{font:600 1.35rem 'Geist';letter-spacing:-.02em;margin-bottom:16px}
.compare div:last-child h3{color:var(--signal)}
.compare dl{font-size:.95rem}
.compare dt{color:rgba(255,255,255,.55);font-size:.8rem;margin-top:14px}
.compare dd{color:#fff}
.steps{counter-reset:s;list-style:none;border-top:2px solid var(--ink)}
.steps li{counter-increment:s;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:clamp(24px,5vw,80px);padding:28px 0;border-bottom:1px solid var(--line)}
.steps h3{font:600 clamp(1.4rem,2.6vw,2rem)/1.15 'Geist';letter-spacing:-.025em;color:var(--ink)}
.steps h3::before{content:counter(s)" ";color:var(--signal)}
.answer{margin-top:24px;font-size:1rem}
.answer .q{font:500 1.5rem/1.3 'Geist';letter-spacing:-.02em;color:var(--ink);max-width:32ch}
.answer ol{list-style:none;margin-top:20px}
.answer li{display:flex;gap:16px;align-items:baseline;padding:14px 0;border-top:1px solid var(--line);font-size:1.1rem}
.answer li b{font-weight:600;color:var(--ink)}
.answer li small{color:var(--muted);font-size:.95rem}
.answer li.yours b{color:var(--signal)}
.answer li.missing{color:var(--muted)}.answer li.missing b{color:var(--muted);text-decoration:line-through}
.cap{font-size:.85rem;color:var(--muted);margin-top:10px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);border-top:2px solid var(--ink);margin-top:40px}
.metrics div{padding:24px 20px 0 0}
.metrics div+div{padding-left:20px;border-left:1px solid var(--line)}
.metrics h3{font:600 1.5rem 'Geist';letter-spacing:-.025em;color:var(--ink);margin-bottom:8px}
.work{columns:2;column-gap:64px;margin-top:40px}
.work div{break-inside:avoid;padding:0 0 28px}
.work h3{font:600 1.2rem 'Geist';color:var(--ink);letter-spacing:-.015em}
.honest{font:500 clamp(1.4rem,2.6vw,2rem)/1.3 'Geist';letter-spacing:-.02em;color:var(--ink);max-width:36ch;margin-top:24px}
.faq details{border-top:1px solid rgba(255,255,255,.2);padding:22px 0}
.faq summary{cursor:pointer;list-style:none;font:500 clamp(1.2rem,2vw,1.5rem)/1.3 'Geist';letter-spacing:-.015em;display:flex;justify-content:space-between;gap:24px}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";color:var(--signal);font-weight:400}
.faq details[open] summary::after{content:"\\2212"}
.faq p{margin-top:12px;color:rgba(255,255,255,.8);max-width:62ch}
.final{display:flex;justify-content:space-between;align-items:flex-end;gap:32px;flex-wrap:wrap}
.final a{background:#c2410c;color:#fff;text-decoration:none;font-weight:600;padding:18px 28px;border-radius:999px;font-size:1.1rem}
.final a:hover{background:#9a3412}
.refs{font-size:.8rem;color:var(--muted);margin-top:40px;columns:2}
@media(max-width:860px){.hero .below,.two,.steps li{grid-template-columns:1fr}.hero .meta{text-align:left}.compare,.metrics{grid-template-columns:1fr}.compare div+div,.metrics div+div{border-left:0;padding-left:0;border-top:1px solid rgba(127,127,127,.25)}.work,.refs{columns:1}}
"""
    def sup(i):
        return f'<a href="{STATS[i][3]}" title="{e(STATS[i][2])}">{e(STATS[i][2])}</a>'
    cmp_ = ""
    for col, name in ((1, "SEO"), (2, "AEO / GEO"), (3, "AI shopping visibility")):
        cmp_ += f"<div><h3>{name}</h3><dl>" + "".join(f"<dt>{e(r[0])}</dt><dd>{e(r[col])}</dd>" for r in SEO_ROWS) + "</dl></div>"
    steps = "".join(f"<li><h3>{e(a)}</h3><p>{e(b)}</p></li>" for a, b in STEPS)
    ex = "".join(f"<li class='{st}'><span>{r}</span><span><b>{e(n)}</b> <small>{e(t)}</small></span></li>" for r, n, t, st in EXAMPLE)
    metrics = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in METRICS)
    work = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in WORK)
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in FAQ)
    src = "".join(f'<li><a href="{u}">{e(n)}</a></li>' for n, u in stat_sources())
    body = f"""
<header class="top"><img src="{LOGO_LIGHT}" alt="Produkto" style="height:22px;width:auto"><a href="#">Book a demo</a></header>
<section class="hero"><h1>What is AI shopping <em>visibility?</em></h1>
  <div class="below"><p class="def">{e(DEFINITION)}</p><p class="meta">A guide by {AUTHOR}<br>{DATE} · 6 minute read</p></div></section>
<section class="band stack" id="why-now">
  <p class="statement"><span class="n">42%</span> of consumers have already used an AI assistant to shop online.{sup(0)}</p>
  <p class="statement">AI-driven traffic to US retail sites grew <span class="n">127%</span> in a year,{sup(1)} and it converts <span class="n">60%</span> better.{sup(2)}</p>
  <p class="statement">With an AI summary on top, Google visits end in a result click <span class="n">8%</span> of the time, not 15%.{sup(5)}</p>
</section>
<section class="band" id="short" style="padding-top:0"><div class="two"><h2>The short version</h2><div class="body"><p class="lead">{e(DEFINITION_MORE)}</p>{"".join(f"<p>{e(p)}</p>" for p in (POINTS[0], POINTS[1], POINTS[3], POINTS[4]))}</div></div></section>
<section class="band navy" id="vs-seo"><div class="two"><h2>How it differs from SEO</h2><p class="lead">{e(SEO_RULE)}</p></div><div class="compare">{cmp_}</div><p class="lead" style="margin-top:40px;max-width:62ch;font-size:1.1rem">{e(SEO_PARA)}</p></section>
<section class="band" id="how-ai-chooses"><div class="two" style="margin-bottom:48px"><h2>How AI assistants choose products</h2><p class="lead">With web search on, an assistant reads a handful of pages and writes its answer from them. What those pages state decides which products it can recommend.</p></div>
  <ol class="steps">{steps}</ol>
  <div class="answer" style="margin-top:72px"><p class="q">“{e(EXAMPLE_Q)}”</p><ol>{ex}</ol><p class="cap">An illustrative answer. The products are invented.</p></div></section>
<section class="band" id="measure" style="padding-top:0"><div class="two"><h2>How to measure it</h2><p class="lead">Ask your buyer questions several times, on more than one assistant, and track four numbers per product over time.</p></div><div class="metrics">{metrics}</div><p class="honest">{e(MEASURE_RULE)}</p></section>
<section class="band" id="work-on" style="padding-top:0"><div class="two"><h2>What you can work on</h2><p class="lead">Most of it is product data: making each page state the facts a shopper’s question depends on, and being mentioned on the sites AI reads.</p></div><div class="work">{work}</div><p class="honest">{e(HONEST)}</p></section>
<section class="band navy" id="faq"><div class="two"><h2>Questions people ask</h2><div class="faq">{faq}</div></div></section>
<section class="band"><div class="final"><p class="statement" style="max-width:14ch">See which of your products AI recommends.</p><a href="#">Book a demo</a></div><ol class="refs">{src}</ol></section>"""
    return page("Poster | " + TITLE, "family=Geist:wght@400;500;600", css, body)


# ---------------------------------------------------------- V4 ANSWER ANATOMY
def v4():
    css = """
:root{--bg:#ffffff;--ink:#0b1b35;--text:#222a38;--muted:#5d6676;--line:#e6e8ec;--wash:#f4f6fa;--teal:#0f766e;--tealbg:#e6f4f2;--amber:#b45309;--amberbg:#fdf3e6;--focus:#0f766e}
::selection{background:var(--tealbg)}
body{background:var(--bg);color:var(--text);font:400 1.0625rem/1.65 'Geist',system-ui,sans-serif}
.top{max-width:1160px;margin:0 auto;padding:20px 24px;display:flex;justify-content:space-between;align-items:center}
.top img{height:24px;width:auto}
.top a{font-weight:500;font-size:.92rem;color:var(--ink)}
.intro{max-width:1160px;margin:0 auto;padding:56px 24px 0;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:56px;align-items:center}
h1{font:400 clamp(2.6rem,5.4vw,4.2rem)/1.02 'Instrument Serif',serif;color:var(--ink);letter-spacing:-.01em}
h1 i{color:var(--teal)}
.intro .dek{margin-top:20px;font-size:1.15rem;color:var(--muted);max-width:44ch}
.intro .by{margin-top:24px;font-size:.88rem;color:var(--muted)}
.intro .by b{color:var(--ink);font-weight:500}
/* the anatomy diagram */
.anat{position:relative;background:var(--wash);border-radius:16px;padding:28px}
.anat .card{background:#fff;border-radius:12px;box-shadow:0 1px 2px rgba(11,27,53,.06),0 12px 32px -14px rgba(11,27,53,.22);padding:18px 18px 8px}
.anat .q{font-size:.92rem;background:var(--wash);border-radius:10px;padding:10px 12px;color:var(--ink)}
.anat .a{font-size:.9rem;color:var(--muted);margin:12px 2px}
.anat li{list-style:none;display:grid;grid-template-columns:22px 1fr;gap:8px;padding:9px 2px;border-top:1px solid var(--line);font-size:.9rem}
.anat li b{color:var(--ink);font-weight:600}
.anat li small{display:block;color:var(--muted)}
.anat li.yours{background:var(--tealbg);border-radius:8px;border-top-color:transparent;padding-left:8px;margin:0 -6px}
.anat li.missing{color:var(--muted)}
.anat .lbl{position:absolute;font-size:.8rem;line-height:1.35;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:8px;padding:6px 9px;max-width:170px;box-shadow:0 4px 14px -6px rgba(11,27,53,.25)}
.anat .lbl b{color:var(--teal)}
.anat .l1{top:6px;right:-24px}.anat .l2{bottom:96px;right:-36px}.anat .l3{bottom:-14px;left:24px}
.def{max-width:1160px;margin:72px auto 0;padding:0 24px}
.def p{font:400 clamp(1.5rem,2.8vw,2.1rem)/1.35 'Instrument Serif',serif;color:var(--ink);max-width:40ch}
.def p mark{background:linear-gradient(transparent 62%,var(--tealbg) 62%);color:inherit}
.qa{max-width:1160px;margin:0 auto;padding:0 24px}
.qblock{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr);gap:56px;padding:64px 0;border-bottom:1px solid var(--line);scroll-margin-top:24px}
.qblock h2{font:400 clamp(1.8rem,3vw,2.5rem)/1.1 'Instrument Serif',serif;color:var(--ink)}
.qblock .short{font:500 1.2rem/1.5 'Geist';color:var(--ink);margin-bottom:16px}
.qblock .more p+p{margin-top:.9em}
.qblock .more ol{margin:.8em 0 0 1.2em}.qblock .more li{margin:.4em 0}
.qblock .more b{color:var(--ink)}
.facts{margin-top:18px;border-top:1px solid var(--line)}
.facts div{display:grid;grid-template-columns:6.5em 1fr;gap:14px;padding:12px 0;border-bottom:1px solid var(--line);font-size:.95rem}
.facts b{font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
.facts a{color:var(--muted);font-size:.85rem}
.tw{overflow-x:auto;margin-top:12px}
table{width:100%;border-collapse:collapse;font-size:.92rem;min-width:600px}
th,td{text-align:left;vertical-align:top;padding:11px 12px;border-bottom:1px solid var(--line)}
thead th{font-weight:600;color:var(--muted);font-size:.82rem}
thead th.us{color:var(--teal)}
td.us{background:var(--tealbg);color:var(--ink)}
tbody th{color:var(--ink);font-weight:600}
.pairs{display:grid;grid-template-columns:1fr 1fr;gap:20px 32px;margin-top:8px}
.pairs h3{font:600 1rem 'Geist';color:var(--ink)}
.pairs p{color:var(--muted);font-size:.95rem;margin-top:2px}
.aside{margin-top:20px;font-size:.95rem;color:var(--amber);background:var(--amberbg);padding:12px 14px;border-radius:10px}
.faq details{border-bottom:1px solid var(--line);padding:14px 0}
.faq summary{cursor:pointer;font-weight:600;color:var(--ink);list-style:none}
.faq summary::-webkit-details-marker{display:none}
.faq p{margin-top:8px;color:var(--text)}
.end{max-width:1160px;margin:0 auto;padding:80px 24px 96px;text-align:center}
.end p{font:400 clamp(2rem,4vw,3rem)/1.1 'Instrument Serif',serif;color:var(--ink)}
.end a{display:inline-block;margin-top:24px;background:var(--ink);color:#fff;text-decoration:none;padding:14px 24px;border-radius:999px;font-weight:500}
.end a:hover{background:var(--teal)}
.refs{margin:40px auto 0;max-width:560px;text-align:left;font-size:.8rem;color:var(--muted)}.refs li{margin:.25em 0 0 1.2em}
@media(max-width:900px){.intro,.qblock{grid-template-columns:minmax(0,1fr);gap:24px}.pairs{grid-template-columns:1fr}.anat .lbl{position:static;display:block;max-width:none;margin-top:10px;box-shadow:none}}
"""
    ex = "".join(f"<li class='{st}'><span>{r}</span><span><b>{e(n)}</b><small>{e(t)}</small></span></li>" for r, n, t, st in EXAMPLE)
    facts = "".join(f'<div><b>{e(v)}</b><span>{e(t)} <a href="{u}">{e(src)}</a></span></div>' for v, t, src, u, _ in STATS)
    seo = "".join(f"<tr><th>{e(a)}</th><td>{e(b)}</td><td>{e(c)}</td><td class='us'>{e(d)}</td></tr>" for a, b, c, d in SEO_ROWS)
    steps = "".join(f"<li><b>{e(a)}.</b> {e(b)}</li>" for a, b in STEPS)
    metrics = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in METRICS)
    work = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in WORK)
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in FAQ)
    src = "".join(f'<li><a href="{u}">{e(n)}</a></li>' for n, u in stat_sources())
    def q(id_, h, short, more):
        return f'<section class="qblock" id="{id_}"><h2>{h}</h2><div><p class="short">{short}</p><div class="more">{more}</div></div></section>'
    body = f"""
<header class="top"><img src="{LOGO}" alt="Produkto" style="height:24px;width:auto"><a href="#">Book a demo</a></header>
<div class="intro"><div><h1>What is AI shopping <i>visibility?</i></h1><p class="dek">{e(DEK)}</p><p class="by">By <b>{AUTHOR}</b> · {DATE}</p></div>
  <figure class="anat" aria-label="Anatomy of an AI shopping answer"><div class="card"><p class="q">{e(EXAMPLE_Q)}</p><p class="a">{e(EXAMPLE_A)}</p><ol>{ex}</ol></div>
    <figcaption><span class="lbl l1"><b>Named.</b> The shortlist is all a shopper sees.</span><span class="lbl l2"><b>Yours, third.</b> The page states the rating and seam taping.</span><span class="lbl l3"><b>Missing.</b> No waterproof rating on the page.</span></figcaption></figure></div>
<div class="def"><p><mark>{e(DEFINITION)}</mark> {e(DEFINITION_MORE)}</p></div>
<div class="qa">
{q("why-now", "Why does it matter now?", "Shoppers already ask AI what to buy, and the click to a search result is shrinking.", f"<div class='facts'>{facts}</div>")}
{q("vs-seo", "Isn't this just SEO?", e(SEO_RULE), f"<div class='tw'><table><thead><tr><th></th><th>SEO</th><th>AEO / GEO</th><th class='us'>AI shopping visibility</th></tr></thead><tbody>{seo}</tbody></table></div><p style='margin-top:16px'>{e(SEO_PARA)}</p>")}
{q("how-ai-chooses", "How does AI pick products?", "It reads a handful of pages and names the few products it can justify for the shopper's need.", f"<ol>{steps}</ol><p class='aside'>The answer at the top of this page is an illustration. The products are invented.</p>")}
{q("measure", "How do you measure it?", "Ask your buyer questions several times, on more than one assistant, and track four numbers per product over time.", f"<div class='pairs'>{metrics}</div><p style='margin-top:16px'>{e(MEASURE_RULE)}</p>")}
{q("work-on", "What can a store work on?", "Mostly product data: state the facts a shopper's question depends on, and get mentioned where AI reads.", f"<div class='pairs'>{work}</div><p class='aside'>{e(HONEST)}</p>")}
{q("faq", "Other questions", "Short answers to what brands ask most.", f"<div class='faq'>{faq}</div>")}
</div>
<div class="end"><p>See which of your products AI recommends.</p><a href="#">Book a demo</a><ol class="refs">{src}</ol></div>"""
    return page("Answer anatomy | " + TITLE, "family=Geist:wght@400;500;600&family=Instrument+Serif:ital@0;1", css, body)


# ---------------------------------------------------------- V5 FIELD GUIDE
def v5():
    css = """
:root{--paper:#fbf8f2;--ink:#0b1b35;--text:#2b2a28;--muted:#6b665d;--line:#e4ddcf;--hi:#ffe9a8;--green:#2f5d50;--focus:#2f5d50}
::selection{background:var(--hi)}
body{background:var(--paper);color:var(--text);font:400 1.125rem/1.7 'Geist',system-ui,sans-serif}
.top{max-width:1120px;margin:0 auto;padding:22px 24px;display:flex;justify-content:space-between;align-items:center}
.top img{height:24px;width:auto}
.top a{font-size:.92rem;font-weight:500;color:var(--paper);background:var(--ink);padding:9px 16px;border-radius:10px;text-decoration:none}
.cover{max-width:1120px;margin:24px auto 0;padding:0 24px;display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:48px;align-items:end}
h1{font:600 clamp(2.8rem,6.4vw,5.2rem)/.98 'Fraunces',serif;color:var(--ink);letter-spacing:-.03em;font-variation-settings:'SOFT' 100,'opsz' 144}
.cover .side{font-size:1rem;color:var(--muted);border-top:2px solid var(--ink);padding-top:16px}
.cover .side b{color:var(--ink)}
.hi{background:linear-gradient(104deg,transparent .5%,var(--hi) 2%,var(--hi) 97%,transparent 99%);padding:0 .15em;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.def{max-width:1120px;margin:56px auto 0;padding:0 24px}
.def p{font:400 clamp(1.4rem,2.6vw,1.9rem)/1.45 'Fraunces',serif;color:var(--ink);max-width:36ch;font-variation-settings:'SOFT' 50}
.page{max-width:1120px;margin:0 auto;padding:24px 24px 96px;display:grid;grid-template-columns:minmax(0,1fr) 260px;column-gap:64px}
.page>section{grid-column:1;padding-top:56px;scroll-margin-top:24px}
.page>aside{grid-column:2;grid-row:1/span 3;padding-top:64px;font-size:.88rem;line-height:1.55;color:var(--muted)}
.page>aside p{margin-bottom:22px;padding-left:14px;position:relative}
.page>aside p::before{content:"";position:absolute;left:0;top:.45em;width:6px;height:6px;border-radius:50%;background:var(--green)}
.page>aside b{display:block;font:600 1.25rem/1.2 'Fraunces',serif;color:var(--ink);margin-bottom:4px}
.page>aside a{color:var(--muted)}
h2{font:600 clamp(1.8rem,3.2vw,2.5rem)/1.1 'Fraunces',serif;color:var(--ink);letter-spacing:-.02em;margin-bottom:16px;font-variation-settings:'SOFT' 100}
section p+p{margin-top:1em}
section>p,section>ol{max-width:64ch}
ol.walk{list-style:none;counter-reset:w;margin-top:20px}
ol.walk li{counter-increment:w;display:grid;grid-template-columns:44px 1fr;padding:14px 0;border-top:1px dashed var(--line)}
ol.walk li::before{content:counter(w);width:30px;height:30px;border-radius:50%;border:1.5px solid var(--green);color:var(--green);display:grid;place-items:center;font:600 .9rem 'Geist'}
ol.walk b{color:var(--ink)}
.side-by-side{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-top:20px;border:1.5px solid var(--ink);border-radius:14px;overflow:hidden;background:#fff}
.side-by-side>div{padding:20px 22px}
.side-by-side>div+div{border-left:1.5px solid var(--ink);background:#f3f7f5}
.side-by-side h3{font:600 1.3rem 'Fraunces',serif;color:var(--ink);margin-bottom:6px}
.side-by-side dt{font-size:.8rem;color:var(--muted);margin-top:12px}
.side-by-side dd{color:var(--ink)}
.small{font-size:.92rem;color:var(--muted);margin-top:12px}
.receipt{margin-top:24px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 22px;max-width:560px;box-shadow:0 1px 2px rgba(60,50,30,.05),0 14px 30px -18px rgba(60,50,30,.3)}
.receipt .q{font:italic 400 1.2rem/1.4 'Fraunces',serif;color:var(--ink)}
.receipt .a{font-size:.95rem;color:var(--muted);margin:8px 0 10px}
.receipt li{list-style:none;display:grid;grid-template-columns:24px 1fr;padding:8px 0;border-top:1px dashed var(--line);font-size:.95rem}
.receipt li b{color:var(--ink)}
.receipt li small{display:block;color:var(--muted)}
.receipt li.yours b{background:var(--hi)}
.receipt li.missing{color:var(--muted)}.receipt li.missing b{color:var(--muted)}
.gloss{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 40px;margin-top:16px}
.gloss div{padding:14px 0;border-top:1px dashed var(--line)}
.gloss h3{font:600 1.05rem 'Geist';color:var(--ink)}
.gloss p{font-size:.98rem;color:var(--text)}
.faq details{border-top:1px dashed var(--line);padding:14px 0}
.faq summary{cursor:pointer;list-style:none;font:600 1.15rem/1.35 'Fraunces',serif;color:var(--ink)}
.faq summary::-webkit-details-marker{display:none}
.faq p{margin-top:6px}
.end{margin-top:56px;background:var(--ink);color:var(--paper);border-radius:18px;padding:36px;display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap}
.end p{font:600 1.7rem/1.2 'Fraunces',serif;max-width:20ch}
.end a{background:var(--hi);color:var(--ink);text-decoration:none;font-weight:600;padding:14px 22px;border-radius:12px}
.refs{font-size:.8rem;color:var(--muted);margin-top:24px}.refs li{margin:.25em 0 0 1.2em}
@media(max-width:900px){.cover,.page{grid-template-columns:1fr}.page>aside{grid-column:1;padding-top:24px;columns:1}.side-by-side,.gloss{grid-template-columns:1fr}.side-by-side>div+div{border-left:0;border-top:1.5px solid var(--ink)}}
"""
    notes = "".join(f'<p><b>{e(v)}</b>{e(t)} <a href="{u}">{e(src)}</a></p>' for v, t, src, u, _ in STATS)
    seo_l = "".join(f"<dt>{e(r[0])}</dt><dd>{e(r[1])}</dd>" for r in SEO_ROWS)
    seo_r = "".join(f"<dt>{e(r[0])}</dt><dd>{e(r[3])}</dd>" for r in SEO_ROWS)
    steps = "".join(f"<li><span><b>{e(a)}.</b> {e(b)}</span></li>" for a, b in STEPS)
    ex = "".join(f"<li class='{st}'><span>{r}</span><span><b>{e(n)}</b><small>{e(t)}</small></span></li>" for r, n, t, st in EXAMPLE)
    metrics = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in METRICS)
    work = "".join(f"<div><h3>{e(a)}</h3><p>{e(b)}</p></div>" for a, b in WORK)
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in FAQ)
    src = "".join(f'<li><a href="{u}">{e(n)}</a></li>' for n, u in stat_sources())
    body = f"""
<header class="top"><img src="{LOGO}" alt="Produkto" style="height:24px;width:auto"><a href="#">Book a demo</a></header>
<div class="cover"><h1>What is AI shopping visibility?</h1><div class="side"><b>A field guide for ecommerce brands.</b> {e(DEK)}<br><br>By {AUTHOR} · {DATE}</div></div>
<div class="def"><p><span class="hi">{e(DEFINITION)}</span> {e(DEFINITION_MORE)}</p></div>
<div class="page">
  <section id="short"><h2>The short version</h2><p>{e(POINTS[0])} <span class="hi">{e(POINTS[1])}</span></p><p>{e(POINTS[3])}</p><p>{e(POINTS[4])}</p></section>
  <aside aria-label="Numbers worth knowing">{notes}</aside>
  <section id="why-now"><h2>Why it matters now</h2><p>Shoppers are already using AI to decide what to buy, the visitors it sends convert well, and <span class="hi">fewer people click through to search results when an AI answer sits on top.</span> The numbers in the margin have the sources.</p></section>
  <section id="vs-seo"><h2>How it differs from SEO</h2><p>{e(SEO_RULE)}</p>
    <div class="side-by-side"><div><h3>SEO</h3><dl>{seo_l}</dl></div><div><h3>AI shopping visibility</h3><dl>{seo_r}</dl></div></div><p class="small">AEO and GEO sit in between: getting any content quoted or cited in AI answers.</p><p style="margin-top:1em">{e(SEO_PARA)}</p></section>
  <section id="how-ai-chooses"><h2>How AI assistants choose products</h2><p>With web search on, an assistant reads a handful of pages and writes its answer from them. What those pages state decides which products it can recommend.</p><ol class="walk">{steps}</ol>
    <div class="receipt"><p class="q">“{e(EXAMPLE_Q)}”</p><p class="a">{e(EXAMPLE_A)}</p><ol>{ex}</ol><p class="small">An illustrative answer. The products are invented.</p></div></section>
  <section id="measure"><h2>How to measure it</h2><p>Ask your buyer questions several times, on more than one assistant, and track four numbers per product over time.</p><div class="gloss">{metrics}</div><p style="margin-top:1em"><span class="hi">{e(MEASURE_RULE)}</span></p></section>
  <section id="work-on"><h2>What you can work on</h2><p>Most of it is product data: making each page state the facts a shopper’s question depends on, and being mentioned on the sites AI reads.</p><div class="gloss">{work}</div><p style="margin-top:1em"><em>{e(HONEST)}</em></p></section>
  <section id="faq"><h2>Questions people ask</h2><div class="faq">{faq}</div>
    <div class="end"><p>See which of your products AI recommends.</p><a href="#">Book a demo</a></div><ol class="refs">{src}</ol></section>
</div>"""
    return page("Field guide | " + TITLE, "family=Fraunces:opsz,wght,SOFT@9..144,400..600,0..100&family=Geist:wght@400;500;600", css, body)


VARIANTS = [
    ("v1-journal.html", "1. Journal", "A printed long-read: Newsreader and Source Serif on warm paper, a drop cap, a pull quote, and sourced numbers set as margin notes beside the text they support.", v1),
    ("v2-research-report.html", "2. Research report", "IBM Plex on a strict grid with a sticky contents rail and reading progress. Numbers become a real chart and a sourced list; tables and figures are labelled like a report.", v2),
    ("v3-poster.html", "3. Poster", "Huge Geist type, a full-height navy opening and orange accents. Stats become sentences, SEO vs AI is a three-column spread, steps are big rows.", v3),
    ("v4-answer-anatomy.html", "4. Answer anatomy", "The page explains itself: an annotated AI answer up top, then each section is a buyer question with a one-line answer first and detail beside it. Instrument Serif headings, teal accent.", v4),
    ("v5-field-guide.html", "5. Field guide", "Warm and human: Fraunces on cream, highlighted key sentences, sourced numbers in a margin column, SEO vs AI as a side-by-side spread.", v5),
]


def index():
    cards = "".join(f'<a href="{f}"><b>{e(n)}</b><span>{e(d)}</span></a>' for f, n, d, _ in VARIANTS)
    css = """
:root{--ink:#0b1b35;--muted:#5a6273;--line:#e3e4e6}
body{background:#fafaf8;color:var(--ink);font:400 1rem/1.6 'Geist',system-ui,sans-serif;padding:56px 24px}
main{max-width:860px;margin:0 auto}
h1{font:600 2.2rem/1.1 'Geist';letter-spacing:-.03em}
p.lede{color:var(--muted);margin-top:12px;max-width:60ch}
.list{margin-top:32px;border-top:1px solid var(--ink)}
.list a{display:grid;grid-template-columns:220px 1fr;gap:24px;padding:20px 0;border-bottom:1px solid var(--line);text-decoration:none}
.list a:hover b{text-decoration:underline}
.list b{font-size:1.15rem}
.list span{color:var(--muted)}
.cur{margin-top:24px;font-size:.92rem;color:var(--muted)}
@media(max-width:640px){.list a{grid-template-columns:1fr;gap:4px}}
"""
    body = f"""<main><h1>Guide design: five directions</h1><p class="lede">The same article, “{e(TITLE)}”, with identical facts, in five different designs. Pick one (or parts of several) and it becomes the template for every guide.</p>
<div class="list">{cards}</div><p class="cur">For comparison: <a href="../../dist/what-is-ai-shopping-visibility.html">the current live design</a>.</p></main>"""
    return page("Guide design directions", "family=Geist:wght@400;600", css, body)


if __name__ == "__main__":
    for f, _, _, fn in VARIANTS:
        open(os.path.join(HERE, f), "w").write(fn())
    open(os.path.join(HERE, "index.html"), "w").write(index())
    print("built", len(VARIANTS), "variations + index")
