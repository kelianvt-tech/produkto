"""Builds playbook.html (then PDF via headless Chrome). Edit the CHAPTERS text here, not the HTML."""
CHAPTERS = [
 ("6-before-after", "What changed", "Shopping before AI vs after AI",
  "A shopper used to search, open ten tabs, compare and pick. Now more of them ask an AI assistant once and get a few names back. The work of getting picked didn't disappear. It moved, and it grew.",
  ["Ranking on Google still matters. It's the foundation, not the finish line.",
   "AI needs three things from you: to find your product, to understand what it's for, and to trust it.",
   "Each of those is a separate job. Most stores have done one."],
  "Read the right-hand stack and tick each layer you've actually worked on in the last 6 months."),
 ("5-journey", "Why you can't see it", "“ChatGPT doesn't send us any sales”",
  "Most of the AI part of a purchase happens where your analytics can't see it. The shopper asks, reads, compares, comes back later and buys. Your dashboard logs it as “direct” or as the last ad they clicked.",
  ["Low AI referral traffic doesn't mean AI isn't involved.",
   "The only way to know if AI names your products is to ask it the way a buyer would.",
   "Ask about your products and your category, never just your brand name."],
  "Ask your customers “how did you first hear about us?” at checkout, and add “ChatGPT or another AI” as an option."),
 ("2-versus", "Where shoppers ask", "Google Shopping vs ChatGPT vs Perplexity",
  "Each assistant finds and picks products differently. Google leans on your product feed. ChatGPT reads the web and reviews. Perplexity shows its sources, which tells you exactly where to be mentioned.",
  ["You don't need a different strategy for each one. You need the same product facts, stated clearly, everywhere.",
   "Use Perplexity's sources as your to-do list: those are the pages it trusts in your category.",
   "Track which products each one names, for which questions."],
  "Ask all three the same buyer question about your best seller. Write down every product named."),
 ("1-layers", "What to do, in order", "6 Layers Of AI Shopping",
  "Start at the top. Each layer depends on the one above it: if AI can't read your store, nothing below it counts.",
  ["Layers 1 and 2 are technical and usually quick to fix.",
   "Layer 3, answering the buyer's question on the page, is where most stores have the biggest gap.",
   "Layers 4 and 5 are earned off your site, and take longest."],
  "Open your robots.txt today and make sure it doesn't block OAI-SearchBot or PerplexityBot."),
 ("4-shelf", "The method", "The SHELF Framework",
  "SHELF is the checklist we use when we look at a store: Structured, Helpful, Earned, Listed, Followed. It turns “get recommended by AI” into five jobs you can assign to someone.",
  ["S and L are mostly one-off setup.",
   "H is page-by-page work, best done product by product, starting with best sellers.",
   "F is the habit: ask, note, fix, re-ask. Without it you never know if anything worked."],
  "Score your store 1–5 on each letter. Start with your lowest."),
 ("3-master", "One product, start to finish", "How To Master AI Shopping",
  "The fastest way to learn this is to do it once, properly, on one product. This sheet walks through a single best seller, from the buyer's question to the fixed page.",
  ["Pick a product that sells well and has clear competitors.",
   "Use the category table to see what your page must state.",
   "Avoid the four mistakes at the bottom right. They're the most common ones."],
  "Block one afternoon this week and do the six steps on your best seller."),
 ("7-funnel", "The whole picture", "The AI Shopping Funnel",
  "AI isn't a separate channel bolted on the side. It shows up at every stage, from first discovery to the repeat order. Use this to see where your current marketing already covers it and where it doesn't.",
  ["Discover and Intent are where AI recommendations matter most.",
   "Each stage has its own KPIs. Track the ones on the left.",
   "Loyalty feeds discovery: reviews that name a use case are what AI reads next."],
  "Pick one KPI per stage and write down today's number, so you have a baseline."),
]
CHECKS = [
 ("READ", ["robots.txt doesn't block OAI-SearchBot or PerplexityBot", "Price, size and stock are in the page text, not only in images", "Product structured data passes Google's Rich Results Test"]),
 ("ANSWER", ["Your best seller's page states material, size and what it's for", "The page answers the 3 questions buyers ask before buying", "It says who it's for, and who it's not for"]),
 ("TALKED ABOUT", ["Reviews on your product pages", "Mentioned in at least one “best [product]” article or Reddit thread", "Listed in Google Merchant Center"]),
 ("CHECKED", ["You've asked ChatGPT your buyer's question this month", "You know which competitor product it picks instead", "Someone on your team owns this"]),
]
CSS = open('../../../../.claude/skills/cheatsheet-design/templates/d.css').read().split('html,body')[0]
pages = []
pages.append('''<section class="cover"><img class="lg" src="logo.png"><div class="ct">The <em>AI Shelf</em><br>Playbook</div>
<div class="cs">What ChatGPT, Perplexity and Google AI look for before they recommend a product, and what your store can do about it.</div>
<div class="cb">By Kelian van Tulder<br><span>Founder, Produkto</span></div></section>''')
toc = ''.join(f'<li><b>{i+1}.</b> {c[2]} <span>{c[1]}</span></li>' for i, c in enumerate(CHAPTERS))
pages.append(f'''<section class="txt"><div class="kick">INTRODUCTION</div><h2>Your products are on a <em>new shelf</em></h2>
<p>More shoppers now ask an AI assistant what to buy. It reads the web, then names a few products. If yours isn't one of them, that shopper never sees it, and nothing in your analytics tells you it happened.</p>
<p>This playbook is what you can control. It's seven cheat sheets, each with a page on how to use it and one thing to do this week. Start wherever your store is weakest. The scorecard at the end shows you where that is.</p>
<p class="note">A playbook, not a promise. It lists the work; it can't guarantee an AI will pick a product. What it will do is make sure you've given it every reason to.</p>
<div class="kick" style="margin-top:46px">INSIDE</div><ol class="toc">{toc}<li><b>8.</b> Scorecard: is your store AI-ready? <span>Score yourself</span></li></ol></section>''')
for i, (img, kick, title, intro, pts, do) in enumerate(CHAPTERS):
    lis = ''.join(f'<li>{p}</li>' for p in pts)
    pages.append(f'''<section class="txt"><div class="num">{i+1}</div><div class="kick">{kick.upper()}</div><h2>{title}</h2><p>{intro}</p>
<div class="kick" style="margin-top:34px">WHAT TO TAKE FROM IT</div><ul class="pts">{lis}</ul>
<div class="do"><b>Do this week:</b> {do}</div><div class="next">The sheet is on the next page →</div></section>''')
    pages.append(f'<section class="img"><img src="img/{img}.png"></section>')
sec = ''
for name, items in CHECKS:
    rows = ''.join(f'<div class="row"><div class="box"></div>{t}</div>' for t in items)
    sec += f'<div class="sec"><span class="lab">{name}</span>{rows}</div>'
pages.append(f'''<section class="txt"><div class="num">8</div><div class="kick">SCORECARD</div><h2>Is your store <em>AI-ready?</em></h2>
<p>12 checks, one point each. Takes about 10 minutes.</p>{sec}
<div class="score"><div style="background:#fde8e6"><b>0–4</b>AI probably can't read or understand you</div><div style="background:#fff4cc"><b>5–8</b>Visible, but rarely the one picked</div><div style="background:#e1f5e9"><b>9–12</b>Ahead of most stores</div></div></section>''')
pages.append('''<section class="end"><div class="kick" style="color:#9fbaff">WHEN YOU HAVE MORE THAN A FEW PRODUCTS</div><h2 style="color:#fff">Doing this by hand works for <em>one product</em></h2>
<p>Produkto does it for your whole catalog. Paste your store URL and it asks AI assistants the questions your buyers ask, every day, then shows which of your products get recommended, where they rank, and which competitors get picked instead.</p>
<p>Its Catalog Optimization Agent finds the details buyers ask about that your product pages leave out, and drafts the fixes. You review and approve every one before anything changes on your store.</p>
<div class="ctas"><div class="c1">Free check of your store</div><div class="c2">Reply to the post, or email kelian@getprodukto.com</div></div>
<div class="ctas"><div class="c1">Book a demo</div><div class="c2">getprodukto.com</div></div>
<img class="lg2" src="logo.png"></section>''')
html = f'''<!doctype html><html><head><meta charset="utf-8"><style>{CSS}
@page{{size:1200px 1500px;margin:0}}
body{{margin:0;font-family:Outfit,sans-serif;color:var(--ink)}}
section{{width:1200px;height:1500px;page-break-after:always;position:relative;overflow:hidden;background:#fbfcfe;
 background-image:repeating-linear-gradient(90deg,transparent 0 59px,rgba(11,27,53,.035) 59px 60px)}}
.cover{{background:linear-gradient(160deg,#16306a 0%,#0b1b35 60%,#081226 100%);color:#fff;padding:120px 110px}}
.lg{{width:96px;height:96px;border-radius:20px}}
.ct{{font-family:'DM Serif Display',serif;font-size:150px;line-height:1;margin-top:140px}}
.ct em,.end h2 em{{color:#9fbaff;font-style:italic;background:none;padding:0}}
.cs{{font-size:36px;line-height:1.35;margin-top:50px;color:#d5def2;max-width:880px}}
.cb{{position:absolute;left:110px;bottom:110px;font-family:'DM Serif Display',serif;font-style:italic;font-size:40px;color:#cfdcff}}
.cb span{{font-family:Outfit;font-style:normal;font-size:24px;color:#9fb0d6}}
.txt{{padding:110px 110px}}
.kick{{font-weight:800;letter-spacing:4px;font-size:20px;color:var(--acc)}}
h2{{font-family:'DM Serif Display',serif;font-weight:400;font-size:84px;line-height:1.05;margin:18px 0 34px;letter-spacing:-1px}}
h2 em{{color:var(--acc);font-style:italic;background:var(--hlbg);padding:0 10px}}
p{{font-size:28px;line-height:1.5;color:#22314c;margin-bottom:22px;max-width:960px}}
.note{{font-size:22px;color:var(--muted);border-left:4px solid #cdd5e2;padding-left:18px}}
.toc{{list-style:none;margin-top:14px}}.toc li{{font-size:28px;padding:12px 0;border-bottom:1.5px dashed #d6dce7}}
.toc b{{color:var(--acc);margin-right:10px}}.toc span{{float:right;color:var(--muted);font-size:20px;padding-top:6px}}
.num{{position:absolute;right:110px;top:70px;font-family:'DM Serif Display',serif;font-size:260px;color:rgba(35,80,200,.08);line-height:1}}
.pts{{list-style:none;margin-top:12px}}.pts li{{font-size:27px;line-height:1.45;padding:14px 0 14px 40px;position:relative;border-bottom:1px solid #e3e8f0}}
.pts li::before{{content:"";position:absolute;left:4px;top:26px;border-left:14px solid var(--acc);border-top:9px solid transparent;border-bottom:9px solid transparent}}
.do{{margin-top:40px;background:var(--hlbg);border-left:6px solid var(--acc);padding:24px 28px;font-size:27px;line-height:1.45;border-radius:8px}}
.do b{{color:var(--acc)}}
.next{{position:absolute;bottom:90px;right:110px;font-size:22px;color:var(--muted);font-weight:600}}
.img{{background:#fff}}.img img{{width:1200px;height:1500px;display:block}}
.sec{{margin-top:22px}}.lab{{display:inline-block;background:var(--ink);color:#fff;font-weight:800;letter-spacing:2px;font-size:17px;padding:5px 12px;border-radius:5px;margin-bottom:8px}}
.row{{display:flex;gap:16px;align-items:center;font-size:24px;padding:11px 0;border-bottom:1px dashed #d6dce7}}
.box{{flex:0 0 30px;height:30px;border:3px solid var(--ink);border-radius:6px}}
.score{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:34px}}.score div{{border-radius:14px;padding:18px;font-size:21px;font-weight:600;line-height:1.3}}.score b{{display:block;font-size:32px;font-weight:900}}
.end{{background:linear-gradient(160deg,#16306a 0%,#0b1b35 60%,#081226 100%);padding:130px 110px}}
.end p{{color:#d5def2}}
.ctas{{display:flex;margin-top:30px;border:2px solid #fff;border-radius:8px;overflow:hidden;max-width:980px}}
.ctas .c1{{background:#fff;color:var(--ink);font-weight:800;font-size:28px;padding:22px 28px;white-space:nowrap}}
.ctas .c2{{color:#fff;font-size:24px;padding:24px 28px}}
.lg2{{position:absolute;right:110px;bottom:110px;width:90px;height:90px;border-radius:20px}}
</style></head><body>{"".join(pages)}</body></html>'''
open('playbook.html', 'w').write(html)
print(len(pages), 'pages')
