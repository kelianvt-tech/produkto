"""Produkto MVP v1 - one product in, its AI visibility insights out.

    paste a Shopify URL -> pick a product -> questions are written for it
                        -> run -> dashboard

Run it:

    python3 mvp/app/app.py            # start the app on http://localhost:8010
    python3 mvp/app/app.py --check    # test the OpenAI key and model names

Standard library only: no pip install. Pages are plain HTML built in
Python; the only outside script is Chart.js (from cdnjs) for the trend line.
"""

import html
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog      # noqa: E402
import config       # noqa: E402
import db           # noqa: E402
import llm          # noqa: E402
import questions    # noqa: E402
import dashboard    # noqa: E402
import scan         # noqa: E402
import scheduler     # noqa: E402
import waitlist      # noqa: E402
import onboarding   # noqa: E402
import brand_profile
import catalog_setup
import topics
import competitor_setup
import evidence

E = html.escape


# ============================================================ layout

CSS = """
:root{--ink:#0b1b35;--ink-2:#1c2c48;--text:#1a2436;--muted:#586579;--faint:#8b95a5;
--bg:#fafaf8;--surface:#fff;--subtle:#f3f4f1;--line:#e6e7e3;--line-2:#d8dad4;
--comp:#c9ced6;--up:#1f8a4c;--up-bg:#e8f5ec;--signal:#b93c0a;--signal-bg:#fff2ea;
--r:14px;--font:'Geist',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;
--mono:'Geist Mono',ui-monospace,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 var(--font);-webkit-font-smoothing:antialiased}
a{color:var(--ink)}
header.top{border-bottom:1px solid var(--line);background:var(--surface)}
header.top .in{padding:14px 40px;display:flex;align-items:center;gap:10px}
@media(max-width:600px){header.top .in{padding:14px 16px}}
header.top img{height:26px}
header.top b{font-weight:600;color:var(--ink);letter-spacing:-.01em}
header.top .tag{margin-left:auto;font-size:13px;color:var(--muted);text-decoration:none}
header.top a.tag:hover{color:var(--ink);text-decoration:underline}
main{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:30px;line-height:1.15;letter-spacing:-.02em;color:var(--ink);margin:0 0 8px;font-weight:600}
h2{font-size:15px;margin:0 0 4px;color:var(--ink);font-weight:600}
.sub{color:var(--muted);margin:0 0 24px}
.small{font-size:13px;color:var(--muted)}
.faint{color:var(--faint)}
.mono{font-family:var(--mono)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:20px}
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--ink);color:#fff;border:0;border-radius:10px;
 padding:11px 18px;font:500 15px var(--font);cursor:pointer;text-decoration:none}
.btn:hover{background:var(--ink-2)}
.btn[disabled]{opacity:.45;cursor:default}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--line-2)}
.btn.ghost:hover{background:var(--subtle)}
input[type=text],input[type=search]{font:15px var(--font);padding:11px 14px;border:1px solid var(--line-2);
 border-radius:10px;background:#fff;color:var(--text);width:100%}
input:focus{outline:2px solid var(--ink);outline-offset:1px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.err{background:var(--signal-bg);color:var(--signal);border-radius:10px;padding:12px 14px;margin:0 0 16px}
.hero{max-width:620px;margin:60px auto}
.hero form{display:flex;gap:10px;margin-top:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;
 text-decoration:none;color:var(--text);display:flex;flex-direction:column}
.tile:hover{border-color:var(--ink)}
.tile .im{aspect-ratio:1;background:var(--subtle) center/cover no-repeat}
.tile .t{padding:10px 12px;font-size:13px;line-height:1.35}
.tile .p{padding:0 12px 12px;font-size:12px;color:var(--muted)}
.prod{display:grid;grid-template-columns:220px 1fr;gap:28px;align-items:start}
.prod img{width:100%;border-radius:12px;background:var(--subtle)}
ol.qs{margin:12px 0 0;padding:0;list-style:none;counter-reset:q}
ol.qs li{counter-increment:q;padding:11px 0 11px 34px;border-top:1px solid var(--line);position:relative}
ol.qs li:before{content:counter(q);position:absolute;left:0;top:11px;width:22px;height:22px;border-radius:6px;
 background:var(--subtle);font:500 12px/22px var(--mono);text-align:center;color:var(--muted)}
.checking{margin-bottom:22px}
.load{display:flex;flex-direction:column;align-items:center;text-align:center;padding:56px 16px 40px}
.load canvas{margin-bottom:26px}
.load .checking{margin:0 0 10px}
.load-meta{margin:8px 0 0;font-variant-numeric:tabular-nums}
.dots{letter-spacing:.06em}
.dots i{font-style:normal;animation:blink 1.4s infinite both}
.dots i:nth-child(2){animation-delay:.2s}
.dots i:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
.steps{display:flex;gap:8px;align-items:center;margin:0 0 20px;flex-wrap:wrap}
.step{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--faint)}
.step+.step:before{content:"";width:18px;height:1px;background:var(--line-2);margin-right:2px}
.step i{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--subtle);
 color:var(--muted);font:500 11px/1 var(--mono);font-style:normal}
.step.on{color:var(--ink);font-weight:500}
.step.on i{background:var(--ink);color:#fff}
.step.done i{background:#dfe3ea;color:var(--ink)}
.field{display:block;margin:0 0 14px}
.field>span{display:block;font-size:13px;color:var(--muted);margin-bottom:5px}
.field small{display:block;font-size:12px;color:var(--faint);margin-top:5px}
.field input,.field select{width:100%;font:15px var(--font);padding:10px 12px;border:1px solid var(--line-2);
 border-radius:10px;background:#fff;color:var(--text)}
.field-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
ol.qs.editable li{padding-left:0;display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap}
ol.qs.editable li:before{position:static;flex-shrink:0;margin-top:6px}
ol.qs textarea{flex:1;min-width:200px;font:14px var(--font);line-height:1.45;padding:8px 10px;border:1px solid transparent;
 border-radius:8px;resize:vertical;background:transparent;color:var(--text)}
ol.qs textarea:hover{border-color:var(--line)}
ol.qs textarea:focus{border-color:var(--line-2);background:#fff;outline:2px solid var(--ink);outline-offset:1px}
ol.qs .tag{order:3;font-size:11px;color:var(--muted);background:var(--subtle);border-radius:99px;padding:2px 9px;margin-left:34px}
ol.qs .qdel{background:none;border:0;font-size:20px;line-height:1;color:var(--faint);cursor:pointer;padding:4px 6px;border-radius:6px}
ol.qs .qdel:hover{background:var(--subtle);color:var(--signal)}
.small-btn{padding:8px 14px;font-size:13px;margin-top:12px}
@media (max-width:820px){.field-row{grid-template-columns:1fr}}
.loading{display:flex;align-items:center;gap:12px;padding:18px 0;color:var(--muted)}
.spin{width:18px;height:18px;border:2px solid var(--line-2);border-top-color:var(--ink);border-radius:50%;
 animation:sp 0.8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.bar{height:8px;border-radius:99px;background:var(--subtle);overflow:hidden}
.bar i{display:block;height:100%;background:var(--ink);transition:width .4s}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-weight:500;color:var(--muted);font-size:12px;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:10px;border-bottom:1px solid var(--line)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.you td{background:#f1f3f7;font-weight:600;color:var(--ink)}
.dash{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}
.s4{grid-column:span 4}.s8{grid-column:span 8}.s6{grid-column:span 6}.s12{grid-column:span 12}
.big{font-size:64px;line-height:1;font-weight:600;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}
.big small{font-size:20px;color:var(--faint);font-weight:500}
.kv{margin-top:18px;display:grid;gap:8px}
.kv div{display:flex;justify-content:space-between;gap:12px;font-size:14px;border-top:1px solid var(--line);padding-top:8px}
.kv b{font-variant-numeric:tabular-nums;color:var(--ink)}
.hb{display:grid;grid-template-columns:minmax(0,1fr) 110px 48px;gap:10px;align-items:center;padding:6px 0;font-size:14px}
.hb .lab{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hb .lab span{color:var(--faint)}
.hb .track{height:10px;border-radius:99px;background:var(--subtle);overflow:hidden}
.hb .track i{display:block;height:100%;background:var(--comp)}
.hb.you .lab{font-weight:600;color:var(--ink)} .hb.you .track i{background:var(--ink)}
.hb .pct{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-size:12px;padding:2px 8px;border-radius:99px;background:var(--subtle);color:var(--muted)}
.pill.up{background:var(--up-bg);color:var(--up)}
.pill.warn{background:var(--signal-bg);color:var(--signal)}
.pos{display:inline-block;min-width:44px;text-align:center;border-radius:6px;padding:2px 6px;font-variant-numeric:tabular-nums}
.chartbox{position:relative;height:200px}
.empty{height:200px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;
 color:var(--muted);background:var(--subtle);border-radius:10px;text-align:center;padding:0 16px}
details summary{cursor:pointer;color:var(--muted);font-size:13px}
.answer{white-space:pre-wrap;font-size:13px;background:var(--subtle);border-radius:10px;padding:12px;margin:8px 0 18px}
@media (max-width:820px){.s4,.s8,.s6{grid-column:span 12}.prod{grid-template-columns:1fr}.prod img{max-width:240px}
 .hero form{flex-direction:column}.big{font-size:52px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""
import opportunities as _opportunities
CSS += _opportunities.CSS
import content_agent as _content_agent
CSS += _content_agent.CSS
import content_review as _content_review
CSS += _content_review.CSS
import content_calendar as _content_calendar
CSS += _content_calendar.CSS
import content_setup as _content_setup
CSS += _content_setup.CSS
import content_board as _content_board  # noqa: E402
CSS += _content_board.CSS
import stories_hub as _stories_hub  # noqa: E402
CSS += _stories_hub.CSS
import product_preview as _product_preview  # noqa: E402
CSS += _product_preview.CSS
import p_loader as _p_loader  # noqa: E402
CSS += _p_loader.CSS
import content_export as _content_export
CSS += _content_export.CSS


def _dock_filters(body):
    """Move the period filter bar up beside the tabs, where header() left a slot."""
    if '<!--FILTERS-->' not in body:
        return body
    m = re.search(r'<!--filter-bar-->.*?<!--/filter-bar-->', body, re.S)
    if not m:
        return body.replace('<!--FILTERS-->', '')
    body = body[:m.start()] + body[m.end():]
    return body.replace('<!--FILTERS-->', m.group(0), 1)


def page(title, body, extra_head="", here="/"):
    body = _dock_filters(body)
    if "pLoad(" in body:
        body = _p_loader.markup() + body     # first, so a form that submits itself on load can use it
    with open(os.path.join(config.HERE, "dashboard.css")) as css_file:
        extra_head += "<style>" + css_file.read() + "</style>"
    with open(os.path.join(config.HERE, "workspace.css")) as css_file:
        extra_head += "<style>" + css_file.read() + "</style>"
    theme = os.path.join(config.HERE, "theme-graphite.css")
    if os.path.exists(theme):  # dark Graphite look; delete the file to go back
        with open(theme) as css_file:
            extra_head += "<style>" + css_file.read() + "</style>"
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<link rel="icon" type="image/png" href="/favicon.png?v=1"><link rel="apple-touch-icon" href="/favicon.png?v=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;600;700&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>%s</style>%s
%s<script>try{if(localStorage.getItem('produkto-rail')==='shut')document.documentElement.classList.add('rail-shut')}catch(e){}</script>
</head><body>
%s
<main>%s</main>""" % (E(title), CSS, extra_head, THEME_HEAD, rail(here, body), body) + INFO_SCRIPT + "</body></html>"


# The left rail: Dashboard, Buyer questions and Content agents; Support and Settings sit at the foot of it. The catalog
# switcher keeps the place it had in the old top bar, directly under the logo.
def _rail_item(href, label, path, current=""):
    mark = ' aria-current="page"' if current == href else ''
    return ('<a class="rail-item"%s href="%s">'
            '<svg viewBox="0 0 24 24" aria-hidden="true">%s</svg>'
            '<span>%s</span></a>') % (mark, E(href), path, E(label))


_AGENTS_PATH = ('<rect x="4.2" y="6.4" width="15.6" height="12" rx="3.4"/>'
                '<path d="M12 3.4v3"/><circle cx="12" cy="2.8" r=".8"/>'
                '<circle cx="9.2" cy="12" r="1.15"/><circle cx="14.8" cy="12" r="1.15"/>'
                '<path d="M2.6 11v2.8M21.4 11v2.8"/>')
_QUESTIONS_PATH = ('<path d="M4 5.5h16v10H9l-5 4z"/><path d="M10 9.2a2 2 0 1 1 2.6 1.9c-.4.1-.6.5-.6.9"/>'
                   '<circle cx="12" cy="13.4" r=".7" fill="currentColor" stroke="none"/>')
_HOME_PATH = '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h13V9.5"/>'
_SUPPORT_PATH = ('<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.2 2.9'
                 'c-.6.2-.9.7-.9 1.3v.4"/><circle cx="12" cy="17.2" r=".9" fill="currentColor" stroke="none"/>')
_SETTINGS_PATH = ('<circle cx="12" cy="12" r="3.1"/><path d="M19.4 14.2a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8'
                  'l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1.1-1.5'
                  ' 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3'
                  'a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1.1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1'
                  'a1.6 1.6 0 0 0 1.8.3h.1a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3'
                  'l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v.1a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1'
                  'a1.6 1.6 0 0 0-1.5 1z"/>')


# Light / dark mode. The choice is remembered per browser; dark is the default.
THEME_HEAD = ("<script>try{if(localStorage.getItem('produkto-theme')!=='light')"
              "document.documentElement.classList.add('dark')}catch(e){document.documentElement.classList.add('dark')}</script>")
THEME_CLICK = ("var d=document.documentElement.classList.toggle('dark');"
               "try{localStorage.setItem('produkto-theme',d?'dark':'light')}catch(e){}")
_MOON = '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'
_SUN = ('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4'
        'M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>')
THEME_BUTTON = '<div class="theme-switch-row">'+'<button type="button" class="theme-switch" onclick="%s" aria-label="Switch light or dark mode" title="Switch light or dark mode"><span class="ts-opt ts-light"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/></svg></span><span class="ts-opt ts-dark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg></span></button>' % THEME_CLICK+'</div>'

def rail(here="/", body=""):
    """The rail, with the item you are on marked. A dashboard counts as Dashboard.

    The switcher shows the store you are looking at (read from the marker the
    dashboard header leaves in the body), or the only store there is."""
    if here not in ("/support", "/settings", "/agents"):
        # A dashboard's Buyer questions tab is its own rail item, not Dashboard.
        here = ("/buyer-questions" if 'data-rail-page="questions"' in body else
                "/opportunities" if 'data-rail-page="opportunities"' in body else
                "/content" if 'data-rail-page="content"' in body else "/")
    return _RAIL % (_store_switch(body), _rail_item("/", "Dashboard", _HOME_PATH, here)
                    + _questions_item(here, body)
                    + _opportunities_item(here)
                    + (_agent_item(here, body)
                       if _content_agent.enabled()
                       else _rail_item("/agents", "Content agents", _AGENTS_PATH, here)),
                    THEME_BUTTON + _rail_item("/support", "Support", _SUPPORT_PATH, here),
                    _rail_item("/settings", "Settings", _SETTINGS_PATH, here))



# Sub-item icons (18 Oct 2026), same 1.6 stroke as the rail's own icons.
_SUB_ICONS = {
    "questions": '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r=".9"/><circle cx="4" cy="12" r=".9"/><circle cx="4" cy="18" r=".9"/>',
    "suggestions": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2V16h5v-.2c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3z"/>',
    "fixes": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.4"/>',
    "articles": '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h7M9 8h3"/>',
}


def _sub_label(key, label):
    return ('<span class="rail-sub-l"><svg viewBox="0 0 24 24" aria-hidden="true">%s</svg>%s</span>'
            % (_SUB_ICONS[key], E(label)))


def _questions_item(here, body):
    """Buyer questions, with its two sub-tabs (Your questions, Suggestions) open while you are in it."""
    item = _rail_item("/buyer-questions", "Buyer questions", _QUESTIONS_PATH, here)
    import question_suggestions
    import accounts
    user = accounts.current()
    domain = _LAST_STORES.get(user["id"] if user else 0, {}).get("domain", "")
    n = question_suggestions.count(domain) if domain else 0
    if here != "/buyer-questions":
        return item.replace("</span></a>", '</span><span class="rail-badge">%d</span></a>' % n) if n else item
    sub = 'data-rail-sub="suggestions"' in body
    d = "?d=" + E(urllib.parse.quote(domain)) if domain else ""
    return item + ('<div class="rail-sub"><a href="/buyer-questions%s"%s>%s</a>'
                   '<a href="/question-suggestions%s"%s>%s%s</a></div>') % (
        d, "" if sub else ' aria-current="page"', _sub_label("questions", "Your questions"),
        d, ' aria-current="page"' if sub else "", _sub_label("suggestions", "Suggestions"),
        '<span class="rail-badge">%d</span>' % n if n else "")


def _agent_item(here, body):
    """Catalog Optimization Agent, with its two agents as sub-tabs (18 Oct 2026): Product page fixes and
    AEO articles. Open while you are in it, like Buyer questions."""
    item = _with_store(_rail_item("/content", _content_agent.NAME, _AGENTS_PATH, here), "/content")
    if here != "/content":
        return item
    import accounts
    user = accounts.current()
    domain = _LAST_STORES.get(user["id"] if user else 0, {}).get("domain", "")
    m = re.search(r'data-rail-lane="(\w+)"', body)
    cur = m.group(1) if m else ""
    d = ("&d=" + E(urllib.parse.quote(domain))) if domain else ""
    return item + '<div class="rail-sub">%s</div>' % "".join(
        '<a href="/content?lane=%s%s"%s>%s</a>' % (k, d, ' aria-current="page"' if k == cur else "", _sub_label(k, label))
        for k, label in _content_agent.LANES)


def _with_store(item, path):
    """Name the last-opened store in a rail link, so the page opens on it (see _opportunities_item)."""
    import accounts
    user = accounts.current()
    domain = _LAST_STORES.get(user["id"] if user else 0, {}).get("domain", "")
    return item.replace('href="%s"' % path, 'href="%s?d=%s"' % (path, E(urllib.parse.quote(domain))), 1) if domain else item


_OPPS_PATH = '<path d="M12 3.5 14.6 9l5.9.6-4.4 4 1.3 5.9L12 16.5l-5.4 3 1.3-5.9-4.4-4 5.9-.6z"/>'


def _opportunities_item(here):
    """Hidden until config.SHOW_OPPORTUNITIES is switched on."""
    if not config.SHOW_OPPORTUNITIES:
        return ""
    import accounts
    import opportunities
    user = accounts.current()
    domain = _LAST_STORES.get(user["id"] if user else 0, {}).get("domain", "")
    n = opportunities.counts(domain) if domain else 0
    # Name the store in the link: opportunities._store() reads _LAST_STORES via
    # `import app`, which is a second, empty copy when app.py runs as __main__.
    item = _rail_item("/opportunities", "Opportunities", _OPPS_PATH, here)
    if domain:
        item = item.replace('href="/opportunities"', 'href="/opportunities?d=%s"' % E(domain), 1)
    return item.replace("</span></a>", '</span><span class="rail-badge">%d</span></a>' % n) if n else item


_SWITCH_ICON = ('<svg class="rail-switch-icon" viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M8 9.5 12 5.5l4 4"/><path d="M8 14.5l4 4 4-4"/></svg>')


_LAST_STORES = {}  # user id -> the store they last opened on a dashboard


def _store_switch(body):
    import accounts
    user = accounts.current()
    last = _LAST_STORES.setdefault(user["id"] if user else 0, {})
    m = re.search(r'data-rail-store="([^"]*)" data-rail-name="([^"]*)"', body)
    domain, name = (m.group(1), m.group(2)) if m and m.group(1) else ('', '')
    if domain:
        last.update(domain=domain, name=name)
    elif last:
        domain, name = last['domain'], last['name']
    if not domain:
        try:
            import scheduler
            stores = accounts.visible(scheduler.scannable())
        except Exception:
            stores = []
        if len(stores) == 1:
            domain = name = E(stores[0])
    if not domain:
        return ('<a class="rail-switch" href="/new" title="Switch catalog">'
                '<span class="rail-store-logo rail-store-empty" aria-hidden="true">+</span>'
                '<span class="rail-switch-text"><b>Choose a catalog</b><span>Pick a store</span></span>%s</a>' % _SWITCH_ICON)
    # domain and name arrive already escaped (from the header or E() above).
    initial = (re.sub(r'&[^;]+;', '', name) or '?')[0].upper()
    # The card opens this store's dashboard. Only the admin can add or switch
    # stores (customers have one), so only the admin gets that link.
    extra = ('<a class="rail-add" href="/new" title="Add or switch store">+<span> Add or switch store</span></a>'
             if accounts.is_admin() else '')
    return ('<a class="rail-switch" href="/?d=%s" title="Open dashboard">' % domain +
            '<span class="rail-store-logo" aria-hidden="true"><span>%s</span>'
            '<img src="/icon?d=%s" alt="" loading="lazy" onerror="this.hidden=true"></span>'
            '<span class="rail-switch-text"><b>%s</b><span>%s</span></span></a>%s'
            % (initial, domain, name, domain, extra))


_RAIL = """<a class="skip" href="#main">Skip to content</a>
<aside class="rail" aria-label="Produkto">
<div class="rail-top"><div class="rail-brand">%s
<button type="button" class="rail-collapse" id="rail-collapse" aria-expanded="true" title="Collapse sidebar">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.5 7.5 9 12l4.5 4.5"/><path d="M18.5 7.5 14 12l4.5 4.5"/></svg>
<span class="sr-only">Collapse sidebar</span></button></div>
</div>
<nav class="rail-nav" aria-label="Sections">%s</nav>
<div class="rail-foot">%s%s</div></aside>
<script>
/* The rail folds to icons only. The choice is remembered per browser, and is
   applied in <head> too so a collapsed rail does not flash open on load. */
(()=>{const b=document.getElementById('rail-collapse');if(!b)return;
const set=on=>{document.documentElement.classList.toggle('rail-shut',on);
  b.setAttribute('aria-expanded',String(!on));
  const t=on?'Expand sidebar':'Collapse sidebar';b.title=t;b.querySelector('span').textContent=t;
  try{localStorage.setItem('produkto-rail',on?'shut':'open')}catch(e){}};
set(document.documentElement.classList.contains('rail-shut'));
b.addEventListener('click',()=>set(!document.documentElement.classList.contains('rail-shut')));})();
</script>"""


# Every (i) badge opens a small explanation box on click, instead of relying
# on the browser's slow hover tooltip. Uses the badge's own title text.
INFO_SCRIPT = """<div class="info-pop" id="info-pop" role="dialog" hidden><p></p></div><script>
(()=>{const pop=document.getElementById('info-pop'),txt=pop.querySelector('p');let cur=null;
document.querySelectorAll('.heading-info[title]').forEach(b=>{b.dataset.info=b.title;b.removeAttribute('title');
  b.setAttribute('role','button');b.tabIndex=0;b.setAttribute('aria-expanded','false');});
function close(){pop.hidden=true;if(cur)cur.setAttribute('aria-expanded','false');cur=null;}
function open(b){if(cur===b)return close();close();cur=b;txt.textContent=b.dataset.info;pop.hidden=false;b.setAttribute('aria-expanded','true');
  const r=b.getBoundingClientRect(),w=pop.offsetWidth;
  pop.style.left=Math.max(12,Math.min(r.left+r.width/2-w/2,innerWidth-w-12))+scrollX+'px';
  const below=r.bottom+10+pop.offsetHeight<innerHeight;
  pop.style.top=(below?r.bottom+10:r.top-10-pop.offsetHeight)+scrollY+'px';pop.classList.toggle('above',!below);}
document.addEventListener('click',e=>{const b=e.target.closest('.heading-info[data-info]');
  if(b){e.preventDefault();e.stopPropagation();open(b);return;}if(!pop.contains(e.target))close();},true);
document.addEventListener('keydown',e=>{const b=e.target.closest&&e.target.closest('.heading-info[data-info]');
  if(b&&(e.key==='Enter'||e.key===' ')){e.preventDefault();open(b);}if(e.key==='Escape')close();});
addEventListener('resize',close);})();
</script>"""


def fmt_date(ts):
    return time.strftime("%-d %b %Y, %H:%M", time.localtime(ts))


# ============================================================ pages

def view_latest(q):
    """Open the most recent finished dashboard; the start page if none exists."""
    rows = db.all_("SELECT s.token, p.store_domain FROM scans s JOIN scores sc ON sc.scan_id = s.id "
                   "JOIN prompt_sets p ON p.id = s.prompt_set_id "
                   "WHERE s.status IN ('done','partial') ORDER BY s.run_at DESC")
    want = q.get("d", "")
    s = next((r for r in rows if accounts.can_see(r["store_domain"])
              and (not want or r["store_domain"] == want)), None)
    return redirect("/r/" + s["token"]) if s else view_home(q)


def view_latest_questions(q):
    """The rail's Buyer questions item: the questions tab of the store in view."""
    import accounts
    user = accounts.current()
    want = q.get("d") or _LAST_STORES.get(user["id"] if user else 0, {}).get("domain", "")
    r = view_latest({"d": want} if want else {})
    if r[0] == 303 and r[1].startswith("/r/"):
        return redirect(r[1] + "/questions")
    return r


def view_home(q, error=""):
    err = '<div class="err" role="alert">%s</div>' % E(error) if error else ""
    body = """<h1>Welcome</h1>
<p class="sub">Tell us about your brand and the store you want to monitor.</p>
<form id="welcome" method="post" action="/store">%s
<label class="field"><span>Brand name</span><input type="text" name="name" value="%s" autocomplete="organization" placeholder="Your brand" required></label>
<label class="field"><span>Company website</span><input type="text" name="domain" value="%s" placeholder="yourstore.com" autocomplete="url" required>
<small>Enter your Shopify store’s website.</small></label>
<div id="catalog-status" role="status"></div>
<div class="welcome-note"><b>Start with your store</b><p class="small">We’ll find your products and pre-fill your brand details for you to review.</p></div>
</form><script>
document.getElementById('welcome').addEventListener('submit',function(){
var b=document.getElementById('next');b.disabled=true;b.textContent='Loading…';
document.getElementById('catalog-status').innerHTML='<div class="loading"><span class="spin" aria-hidden="true"></span><span>Reading your store<br><small>Loading your brand and product information…</small></span></div>';
});</script>""" % (err, E(q.get("name", "")), E(q.get("domain", "")))
    return 200, onboarding.page("Welcome", body, 1,
        '<button class="btn" id="next" form="welcome" type="submit">Next <span aria-hidden="true">→</span></button>')


def act_store(q, form):
    raw = form.get("domain", "")
    try:
        domain = catalog.normalise_domain(raw)
        rows, meta = catalog.fetch(domain)
        accounts.claim(domain)
    except (catalog.CatalogError, PermissionError) as e:
        return view_home({"domain": raw, "name": form.get("name", "")}, str(e))
    previous = db.brand(domain)
    db.save_catalog(domain, rows, meta)
    identity = previous or db.brand(domain)
    db.save_brand(domain, form.get("name") or identity["brand_name"],
                  identity["aliases"], identity.get("country") or "", identity.get("currency") or "")
    # Step 2 opens already filled from the store's own data (instant, free);
    # brand-identity adjectives follow in the background via ChatGPT/Apify.
    brand_profile.fill_now(domain)
    brand_profile.start(domain)
    return redirect("/brand?d=" + urllib.parse.quote(domain))


def view_store(q):
    return catalog_setup.catalog(q.get('d',''))


def api_catalog(q, form):
    try:
        excluded=json.loads(form.get('excluded','[]'))
        if not isinstance(excluded,list) or not all(isinstance(x,str) for x in excluded):
            raise ValueError('Choose valid product types.')
        db.save_scope(q.get('d',''),excluded)
        return json_out({'saved':True})
    except (ValueError,TypeError) as e:
        return json_out({'error':str(e)})


COUNTRIES = [("", "Not set"), ("GB", "United Kingdom"), ("US", "United States"),
             ("IE", "Ireland"), ("ES", "Spain"), ("FR", "France"), ("DE", "Germany"),
             ("IT", "Italy"), ("NL", "Netherlands"), ("BE", "Belgium"), ("PT", "Portugal"),
             ("SE", "Sweden"), ("DK", "Denmark"), ("NO", "Norway"), ("FI", "Finland"),
             ("PL", "Poland"), ("CH", "Switzerland"), ("AT", "Austria"), ("CA", "Canada"),
             ("AU", "Australia"), ("NZ", "New Zealand"), ("JP", "Japan"), ("IN", "India")]


def view_brand(q, error=""):
    domain = q.get("d", "")
    brand = db.brand(domain)
    if not brand:
        return redirect('/new')
    options = list(COUNTRIES)
    country = brand.get('country') or ''
    if country and country not in dict(options):
        options.append((country, country))
    countries = ''.join('<option value="%s" %s>%s</option>' % (
        E(code), 'selected' if code == country else '', E(label)) for code, label in options)
    body = '''<h1>Verify brand profile</h1>
<p class="sub">We’ve read your store and filled this in. Check it over — it’s how we recognise your products in AI answers.</p>
<form id="brand-form" method="post" action="/brand?d=%s">
%s<label class="field"><span>Brand name</span><input type="text" name="name" value="%s" required></label>
<label class="field"><span>Company website</span><input type="text" value="%s" readonly><small><a href="/new">Change website</a></small></label>
<label class="field"><span>Description</span><small>Context of your brand.</small><textarea name="description" rows="4">%s</textarea></label>
<label class="field"><span>Industry</span><small>Industry your brand operates in.</small><input type="text" name="industry" value="%s" placeholder="e.g. Furniture Retail"></label>
<div class="field"><span>Brand identity</span><small>Adjectives that describe your brand.</small>
<div class="chips" id="c-identity" data-name="identity" data-placeholder="Add an adjective"></div></div>
<div class="field"><span>Products &amp; Services</span><small>What your brand offers.</small>
<div class="chips" id="c-services" data-name="services" data-placeholder="Add a category"></div></div>
<div class="field"><span>Target markets</span><small>Where your brand operates.</small>
<div class="chips" id="c-markets" data-name="markets" data-placeholder="Add a country or city"></div></div>
<div class="field"><span id="alias-label">Brand aliases</span><small>Alternative names or spellings help us recognise your brand.</small>
<div class="chips" id="c-aliases" data-name="aliases" data-placeholder="Alternative brand name"></div></div>
<div class="field-row"><label class="field"><span>Target country</span><select name="country">%s</select><small>Ask as a shopper in this country.</small></label>
<label class="field"><span>Currency</span><input type="text" name="currency" value="%s" maxlength="3" pattern="[A-Za-z]{3}" placeholder="e.g. GBP"><small>Used for price-related questions.</small></label></div>
<p class="small">These details apply to future scans. Existing answers stay unchanged.</p></form>
<script>
// One chip widget for every tag field. Each writes a comma-joined hidden
// input on submit, which is what the POST handler reads.
var CHIPS=%s;
function chipField(box){
 var name=box.dataset.name,hidden=document.createElement('input');
 hidden.type='hidden';hidden.name=name;box.after(hidden);
 function add(value,focus){
  var chip=document.createElement('span');chip.className='chip';
  var input=document.createElement('input');input.type='text';input.value=value;
  input.placeholder=box.dataset.placeholder;input.setAttribute('aria-label',name);
  input.size=Math.max(6,value.length||10);
  input.oninput=function(){input.size=Math.max(6,input.value.length);sync();};
  var del=document.createElement('button');del.type='button';del.textContent='\u00d7';
  del.setAttribute('aria-label','Remove');del.onclick=function(){chip.remove();sync();};
  chip.append(input,del);box.insertBefore(chip,addBtn);sync();
  if(focus)input.focus();
  return input;
 }
 var addBtn=document.createElement('button');addBtn.type='button';addBtn.className='chip-add';
 addBtn.textContent='Add +';addBtn.onclick=function(){add('',true);};
 box.append(addBtn);
 (CHIPS[name]||[]).forEach(function(v){add(v,false);});
 function sync(){
  hidden.value=Array.prototype.map.call(box.querySelectorAll('.chip input'),
   function(i){return i.value.trim();}).filter(Boolean).join(',');
  box.dispatchEvent(new CustomEvent('chipchange',{bubbles:true}));
 }
 sync();
}
document.querySelectorAll('.chips').forEach(function(box){chipField(box);});
// Brand-identity adjectives arrive in the background (brand_profile.start).
// No waiting message: poll quietly, then fill ONLY fields that are still empty, so nothing the merchant
// has typed in the meantime is overwritten.
(function(){
 var form=document.getElementById('brand-form');
 function empty(name){var box=document.getElementById('c-'+name);
  return !box.querySelector('.chip input')||![].some.call(box.querySelectorAll('.chip input'),function(i){return i.value.trim();});}
 function fillChips(name,values){var box=document.getElementById('c-'+name);if(!values.length||!empty(name))return;
  box.querySelectorAll('.chip').forEach(function(c){c.remove();});
  var add=box.querySelector('.chip-add');values.forEach(function(v){add.click();var i=box.querySelectorAll('.chip input');i=i[i.length-1];i.value=v;i.dispatchEvent(new Event('input'));});
  document.activeElement&&document.activeElement.blur();}
 function poll(){fetch('/api/brand-profile?d='+encodeURIComponent(new URL(form.action).searchParams.get('d'))).then(function(r){return r.json();}).then(function(j){
  if(j.status==='running'){setTimeout(poll,4000);return;}
  if(j.status!=='done')return;
  var p=j.profile,d=form.elements.description,ind=form.elements.industry;
  if(p.description&&!d.value.trim())d.value=p.description;
  if(p.industry&&!ind.value.trim())ind.value=p.industry;
  ['identity','services','markets'].forEach(function(n){fillChips(n,p[n]||[]);});
  form.dispatchEvent(new Event('input',{bubbles:true}));
 }).catch(function(){setTimeout(poll,8000);});}
 poll();
})();
document.getElementById('brand-form').addEventListener('submit',function(){
 var b=document.getElementById('brand-next');b.disabled=true;b.textContent='Saving\u2026';});
</script>''' % (E(urllib.parse.quote(domain)),
        '<div class="err" role="alert">%s</div>' % E(error) if error else '',
        E(brand['brand_name']), E(domain), E(brand.get('description') or ''),
        E(brand.get('industry') or ''), countries, E(brand.get('currency') or ''),
        json.dumps({'identity': brand.get('identity') or [],
                    'services': brand.get('services') or [],
                    'markets': brand.get('markets') or [],
                    'aliases': brand.get('aliases') or []}).replace('</', '<\\/'))
    # Peec-style ghost preview: the real Brand profile screen, filling in as
    # the merchant verifies what the AI proposed.
    body += """<template id="ghost-tpl"><div class="cat-ghost" aria-hidden="true"><div class="gw">
<div class="gw-side"><div class="gw-brand"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><b id="g-brandname">%s</b><span>&#8964;</span></div>
<span class="sk h"></span><span class="sk"></span><span class="sk s"></span><span class="sk l"></span><span class="sk s"></span>
<div class="gw-nav"><svg viewBox="0 0 16 16"><circle cx="8" cy="5.5" r="2.8"/><path d="M2.5 14c.5-2.7 2.7-4.2 5.5-4.2S13 11.3 13.5 14"/></svg>Profile</div></div>
<div class="gw-main"><h3>Brand profile</h3><p>Define your brand's identity, location and positioning.</p>
<div class="gw-store"><img src="/icon?d=%s" alt="" onerror="this.style.visibility='hidden'"><div><b id="g-store">%s</b><small>%s</small></div></div>
<div class="gw-label">Description</div><p class="gw-para" id="g-description"></p>
<div class="gw-label">Industry</div><div class="gw-inp" id="g-industry"></div>
<div class="gw-label">Brand identity</div><div class="gw-chips" id="g-identity"></div>
<div class="gw-label">Products &amp; Services</div><div class="gw-chips" id="g-services"></div>
<div class="gw-label">Target markets</div><div class="gw-chips" id="g-markets"></div>
<div class="gw-two"><div><div class="gw-label">Target country</div><div class="gw-inp" id="g-country"></div></div>
<div><div class="gw-label">Currency</div><div class="gw-inp" id="g-currency"></div></div></div></div></div></div></template>
<script>document.addEventListener('DOMContentLoaded',function(){
 var a=document.querySelector('aside'),t=document.getElementById('ghost-tpl');if(!a||!t)return;
 a.append(t.content.cloneNode(true));
 var form=document.getElementById('brand-form');
 function set(id,value,empty){var el=document.getElementById(id);if(!el)return;
  el.textContent=value||empty;el.classList.toggle('muted',!value);}
 function chips(id,values,empty){
  var out=document.getElementById(id);if(!out)return;out.replaceChildren();
  if(!values.length){var g=document.createElement('span');g.className='ghost';
   g.textContent=empty;out.append(g);return;}
  values.slice(0,8).forEach(function(v){var s=document.createElement('span');
   s.textContent=v;out.append(s);});
  if(values.length>8){var m=document.createElement('span');m.className='ghost';
   m.textContent='+'+(values.length-8);out.append(m);}
 }
 function read(name){
  var box=document.getElementById('c-'+name);if(!box)return [];
  return Array.prototype.map.call(box.querySelectorAll('.chip input'),
   function(i){return i.value.trim();}).filter(Boolean);
 }
 function sync(){
  var name=form.elements['name'].value.trim();
  set('g-name',name,'Your brand');set('g-brandname',name,'Your brand');set('g-store',name,'Your brand');
  set('g-description',form.elements['description'].value.trim(),'No description yet');
  set('g-industry',form.elements['industry'].value.trim(),'Not set');
  var sel=form.elements['country'];
  set('g-country',sel.value?sel.options[sel.selectedIndex].text:'','Not set');
  set('g-currency',form.elements['currency'].value.trim().toUpperCase(),'\u2014');
  chips('g-identity',read('identity'),'No adjectives yet');
  chips('g-services',read('services'),'No categories yet');
  chips('g-markets',read('markets'),'No markets yet');
 }
 form.addEventListener('input',sync);
 form.addEventListener('change',sync);
 // Chips are added and removed by the form's own widget, which announces it.
 form.addEventListener('chipchange',sync);
 sync();
});</script>""" % (E(domain), E(brand['brand_name']), E(domain), E(brand['brand_name']), E(domain))

    return 200, onboarding.page('Brand Hub', body, 2,
        '<a class="btn ghost" href="/new?domain=%s&amp;name=%s">← Back</a><button class="btn" id="brand-next" form="brand-form">Next →</button>' % (
            E(urllib.parse.quote(domain)), E(urllib.parse.quote(brand['brand_name']))))


def act_brand(q, form):
    domain = q.get('d', '')
    if not db.brand(domain):
        return redirect('/new')
    if not form.get('name', '').strip():
        return view_brand(q, 'Enter your brand name before continuing.')
    currency = form.get('currency', '').strip()
    if currency and (len(currency) != 3 or not currency.isascii() or not currency.isalpha()):
        return view_brand(q, 'Use a three-letter currency code, such as GBP or EUR.')
    db.save_brand(domain, form['name'], form.get('aliases', '').split(','),
                  form.get('country', ''), currency, {
                      'description': form.get('description', ''),
                      'industry': form.get('industry', ''),
                      'identity': form.get('identity', '').split(','),
                      'services': form.get('services', '').split(','),
                      'markets': form.get('markets', '').split(',')})
    return redirect('/store?d=' + urllib.parse.quote(domain))


def view_product(q):
    domain=q.get('d','')
    if not domain and q.get('id','').isdigit():
        p=db.one('SELECT store_domain FROM products WHERE id=?',(int(q['id']),))
        domain=p['store_domain'] if p else ''
    return catalog_setup.question_page(domain)


def api_brand(q, form):
    pid = int(q.get("id", "0") or 0)
    p = db.one("SELECT store_domain FROM products WHERE id=?", (pid,))
    if not p:
        return json_out({"error": "Unknown product."})
    aliases = [a for a in (form.get("aliases") or "").split(",")]
    b = db.save_brand(p["store_domain"], form.get("name") or "", aliases,
                      form.get("country") or "", form.get("currency") or "")
    return json_out({"brand": b["brand_name"], "aliases": b["aliases"]})


def _questions_out(ps):
    return json_out({'questions':catalog_setup.items_out(ps)})


def api_questions(q, form):
    domain=q.get('d','')
    if not db.brand(domain):
        return json_out({'error':'Unknown store.'})
    ps=db.get_prompt_set(domain)
    stale=(topics.saved(domain) or ([],[],False))[2]
    # A scanned set can still be edited; the edit saves as a new version.
    if ps and ps['frozen_at'] and not stale and 'questions' not in form:
        return _questions_out(ps)
    try:
        selected=db.scope(domain)
        if 'questions' in form:
            items=json.loads(form['questions'])
            if not isinstance(items,list) or not all(isinstance(x,dict) for x in items):
                raise ValueError('Could not read the edited questions.')
            cleaned=[]
            for it in items:
                if not isinstance(it.get('products'),list) or not all(type(i) is int for i in it['products']):
                    raise ValueError('Choose relevant products for every question.')
                question=str(it.get('q','')).strip()
                if not question:
                    raise ValueError('Enter a question or remove its row.')
                cleaned.append(dict(q=question,tag=str(it.get('tag','')),cluster=str(it.get('cluster','Buyer questions')),products=it['products']))
            items=cleaned
            if ps and [(x['q'],x['products']) for x in items]==[(x['q'],x['products']) for x in catalog_setup.items_out(ps)]:
                return _questions_out(ps)
        elif ps and not q.get('regen') and not (topics.saved(domain) or ([],[],False))[2]:
            return _questions_out(ps)
        else:
            store=db.brand(domain)
            money=dict(currency=store['currency'],symbol=catalog.SYMBOLS.get(store['currency'],''))
            products=[p for p in db.all_('SELECT * FROM products WHERE store_domain=?',(domain,)) if p['id'] in selected['product_ids']]
            place=', '.join(x for x in ((store.get('markets') or [])[:1] or [brand_profile.COUNTRY_NAMES.get(store.get('country') or '', store.get('country') or '')]) if x)
            # Write only as many questions as the plan allows: fewer per topic
            # when many topics are chosen, so every topic still gets some.
            chosen=topics.chosen(domain)
            cap=accounts.question_limit(domain)
            per_topic=topics.PROMPTS_PER_TOPIC
            if cap and chosen:
                per_topic=max(1,min(per_topic,(cap-questions.SPECIFIC_QUESTIONS)//len(chosen)))
            items=questions.generate_clusters(products,money,location=place,topics=chosen,per_topic=per_topic)
            if cap and len(items)>cap:
                items=questions.trim_to(items,cap)
            topics.clear_stale(domain)
        saved=db.save_prompts(domain,[x['q'] for x in items],[x['tag'] for x in items],
                              [x['cluster'] for x in items],[x['products'] for x in items],expected_ids=selected['product_ids'],
                              new_version=bool(ps and ps['frozen_at']))
        return _questions_out(saved)
    except (ValueError,TypeError,llm.LLMError) as e:
        return json_out({'error':str(e)})


def api_scan_start(q, form):
    # No competitor gate. The dashboard's main comparison - rankings, share of
    # voice, the brand chart - already measures this catalog against every
    # competitor that turns up in the answers, with nothing to configure. The
    # saved six-vs-six panel is an extra view, so a missing selection leaves
    # that one panel empty rather than blocking the measurement itself.
    # Kelian, 2026-09-21; supersedes the pre-scan gate added 2026-09-18.
    if not config.SCANS_ALLOWED:
        return json_out({'error':'Scans are switched off on this test copy.'})
    if not config.api_key():
        return json_out({'error':'Add your OpenAI key to mvp/app/.env first.'})
    try:
        return json_out({'token':scan.start(q.get('d',''))})
    except ValueError as e:
        return json_out({'error':str(e)})


P_POINTS = ';'.join(row.rsplit(',', 1)[0] for row in     # x,y only; drop the edge flag
                    open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      'p-points.txt')).read().strip().split(';'))

# The loading page: the Produkto P fills with navy squares, bottom to top, as
# insights come in. Real progress = answers collected (80%) + answers read
# (20%). Apify returns answers in batches, so between batches the fill creeps
# on elapsed time - capped below the next real milestone, never overshooting -
# and catches up the moment real answers land. The percentage shown is the
# same number the P shows.
LOADING = """<div class="load">
<canvas id="pfill" width="200" height="200" aria-hidden="true"></canvas>
<h1 class="checking">Checking your visibility<span class="dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></h1>
<p class="small load-meta"><span id="pct">0%</span> of insights ready · usually 3–5 minutes</p>
</div>
<script>
(function(){
 var token={TOKEN},pts='{POINTS}'.split(';').map(function(r){var p=r.split(',');return {x:+p[0],y:+p[1],a:0};});
 // Fill order: bottom row first, left to right, with a little jitter so it
 // rises like a soft edge rather than a hard line.
 pts.forEach(function(p,i){p.k=p.y+((i*0.618)%1)*0.04;});
 pts.sort(function(a,b){return b.k-a.k;});
 var still=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 var c=document.getElementById('pfill'),ctx=c.getContext('2d'),dpr=window.devicePixelRatio||1;
 c.width=c.height=200*dpr;c.style.width=c.style.height='200px';ctx.scale(dpr,dpr);
 var shown=0,target=0,cap=0,real=0,t0=Date.now(),elapsed0=0,done=false;
 function draw(){
  var n=Math.round(shown*pts.length);ctx.clearRect(0,0,200,200);
  for(var i=0;i<pts.length;i++){var p=pts[i],on=i<n;
   p.a+=still?((on?1:0)-p.a):((on?1:0)-p.a)*0.08;
   ctx.fillStyle='rgba(11,27,53,'+(0.09+0.91*p.a).toFixed(3)+')';
   ctx.fillRect(100+p.x*180-1.5,100+p.y*180-1.5,3,3);}
  document.getElementById('pct').textContent=Math.round(shown*100)+'%';
 }
 function frame(){
  var el=elapsed0+(Date.now()-t0)/1000;
  // Creep: approaches `cap` on a ~3-minute curve, but never passes it.
  var creep=real+(cap-real)*(1-Math.exp(-Math.max(0,el-lastReal)/90));
  target=done?1:Math.max(real,Math.min(creep,cap));
  shown+=(target-shown)*(still?1:0.06);if(target-shown<0.0005)shown=target;
  draw();requestAnimationFrame(frame);
 }
 var lastReal=0,prevReal=-1;
 function tick(){fetch('/api/scan?t='+encodeURIComponent(token)).then(function(r){return r.json();}).then(function(j){
  if(j.status&&j.status!=='running'){done=true;setTimeout(function(){location.reload();},700);return;}
  var collect=j.total?Math.min(1,Math.max(j.done,j.answers||0)/j.total):0,read=j.answers?j.read/j.answers:0;
  real=0.8*collect+0.2*read;
  elapsed0=j.elapsed||0;t0=Date.now();
  if(real!==prevReal){prevReal=real;lastReal=elapsed0;}
  cap=collect<1?0.78:read<1?0.97:0.99;
  setTimeout(tick,2000);
 }).catch(function(){setTimeout(tick,4000);});}
 tick();requestAnimationFrame(frame);
})();
</script>"""


def api_scan_status(q):
    """Progress for the loading page. Besides done/total it reports the real
    stages - which engines have answered, how many answers have been read -
    so the page can say what is happening during the flat stretches while
    an Apify batch is still out."""
    s = db.one("SELECT id, status, done, total, error, run_at FROM scans WHERE token=?",
               (q.get("t", ""),))
    if not s:
        return json_out({"error": "Unknown scan."})
    out = {k: s[k] for k in ("status", "done", "total", "error")}
    got = {r["engine"] for r in db.all_(
        "SELECT engine FROM scan_batches WHERE scan_id=? AND collected=1", (s["id"],))}
    out["engines"] = [{"label": config.engine_label(e), "answered": e in got}
                      for e in scan._engines()]
    read = db.one("SELECT COUNT(*) n, SUM(p.status!='pending') r FROM answers a "
                  "JOIN answer_processing p ON p.answer_id=a.id WHERE a.scan_id=?", (s["id"],))
    out["answers"], out["read"] = read["n"] or 0, read["r"] or 0
    out["elapsed"] = max(0, time.time() - (s["run_at"] or time.time()))
    return json_out(out)


# ============================================================ dashboard

def _pos_style(rank):
    """Heat colour: 1 = dark navy, 6+ = pale."""
    if rank is None:
        return ""
    t = max(0.0, min(1.0, (rank - 1) / 5.0))
    alpha = 0.85 - 0.75 * t
    color = "#fff" if alpha > 0.45 else "var(--ink)"
    return "background:rgba(11,27,53,%.2f);color:%s" % (alpha, color)


def view_result(token, query=None):
    s = db.one("SELECT * FROM scans WHERE token=?", (token,))
    if not s:
        return 404, page("Not found", "<h1>Scan not found</h1>")
    context=dashboard.context(token,query or {})
    if not context:
        return 404,page('Not found','<h1>Product not in this catalog baseline</h1>')
    s,ps,p=context
    back='<p class="small"><a href="/questions?d=%s">← Buyer questions</a></p>' % E(urllib.parse.quote(p['store_domain']))

    if s["status"] == "running":
        body = back + LOADING.replace('{POINTS}', P_POINTS).replace('{TOKEN}', json.dumps(token))
        return 200, page("Checking your visibility", body)

    sc = db.one("SELECT * FROM scores WHERE scan_id=?", (s["id"],))
    if s["status"] == "failed" or not sc:
        body = back + '<h1>The scan didn\'t finish</h1><div class="err">%s</div>' \
               '<p>Saved answers are preserved. Return to buyer questions to retry the catalog scan.</p>' % E(
                   s["error"] or "Unknown error.")
        return 200, page("Scan failed", body)

    user = accounts.current()
    key = ("overview", s["id"], ps["id"], p["id"], sc["id"] if "id" in sc.keys() else 0,
           tuple(sorted((query or {}).items())), user["id"] if user else 0, time.strftime("%Y-%m-%d"))
    return 200, page("Insights: " + p["title"], db.memo(key, lambda: dashboard.overview(s, ps, p, sc, query),
                                                       stamp=db.data_stamp()))


def view_answers(token, query=None):
    body = dashboard.answers(token, query or {})
    if body is None:
        return 404, page("Not found", "<h1>Scan not found</h1>")
    if (query or {}).get("partial") == "1":
        return 200, body          # one batch of rows, appended by the page's script
    return 200, page("Answers", body)


def view_questions(token, query=None):
    body = dashboard.questions(token, query or {})
    if body is None:
        return 404, page("Not found", "<h1>Scan not found</h1>")
    return 200, page("Buyer questions", body)


def view_costs(q):
    rows=[]
    for scan_row in db.all_('SELECT * FROM scans ORDER BY run_at DESC'):
        usage=json.loads(scan_row['model_versions'] or '{}')
        known=bool(usage.get('by_model')) and scan_row['cost_cents'] is not None
        cost='$%.3f'%(scan_row['cost_cents']/100) if known else 'Not available'
        monthly=('$%.2f'%(scan_row['cost_cents']/100*config.SCANS_PER_MONTH)) if known and config.SCANS_PER_MONTH is not None else 'Cadence not set' if config.SCANS_PER_MONTH is None else 'Not available'
        models='; '.join('%s: %s input, %s cached, %s output, %s searches'%(m,v['input_tokens'],v['cached_tokens'],v['output_tokens'],v['searches']) for m,v in usage.get('by_model',{}).items())
        rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'%(E(fmt_date(scan_row['run_at'])),E(scan_row['status']),cost,monthly,E(models)))
    body='<h1>Recorded scan spend</h1><p>Internal operator view. Estimates from recorded provider usage, not a reconciled invoice.</p><p class="small">Price table: '+E(config.PRICE_DATE)+'. Question generation before a scan and unreported failed-call charges are not included. No automatic cadence has been enabled.</p><table><thead><tr><th>Scan</th><th>Status</th><th>Estimated spend</th><th>Monthly projection</th><th>Usage by model</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
    return 200,page('Recorded scan spend',body)


# ============================================================ plumbing

def redirect(to):
    return 303, to


def json_out(obj):
    return 200, ("json", json.dumps(obj))


import accounts
import agents
import linkcheck
import docs
import billing
import settings_page
import support

import opportunities

ROUTES_GET = {"/topics": topics.page,
              "/opportunities": lambda q: (lambda r: (r[0], page("Opportunities", r[1])))(opportunities.page(q)), "/question-suggestions": lambda q: (lambda r: (r[0], page("Buyer question suggestions", r[1])))(__import__("question_suggestions").page(q)),
              "/content": lambda q: (lambda r: (r[0], page(_content_agent.NAME, r[1])))(_content_agent.page(q)),
              "/agents": lambda q: (lambda r: (r[0], page("Content agents", r[1], here="/agents")))(agents.page(q)),
              "/oauth/authorize": lambda q: (lambda r: (r[0], page("Connect", r[1], here="/settings")))(__import__("mcp_oauth").authorize_page(q)),
              "/settings": lambda q: (lambda r: (r[0], page("Settings", r[1], here="/settings")))(settings_page.settings(q)),
              "/support": lambda q: (lambda r: (r[0], page("Support", r[1], here="/support")))(support.page(q)),
              "/docs": lambda q: (lambda r: (r[0], page("How Produkto measures", r[1], here="/support")))(docs.page(q)), "/api/brand-profile": lambda q: json_out(brand_profile.status(q.get("d", ""))), "/competitors": lambda q: (303, "/topics?d=" + urllib.parse.quote(q.get("d", ""))), "/costs": view_costs, "/": view_latest, "/buyer-questions": view_latest_questions, "/new": view_home, "/brand": view_brand, "/store": view_store, "/product": view_product, "/questions": view_product,
              "/api/scan": api_scan_status}
import prompt_creation

ROUTES_POST = {"/question-suggestions": lambda q, form: (lambda r: r if r[0] == 303 or isinstance(r[1], tuple) else (r[0], page("Buyer question suggestions", r[1])))(__import__("question_suggestions").act(q, form)), "/content": lambda q, form: (lambda r: r if r[0] == 303 or isinstance(r[1], tuple) else (r[0], page(_content_agent.NAME, r[1])))(_content_agent.act(q, form)), "/opportunities": lambda q, form: (lambda r: r if r[0] == 303 else (r[0], page("Opportunities", r[1])))(opportunities.act(q, form)), "/api/topics": topics.api, "/api/prompts": prompt_creation.api, "/api/competitors": competitor_setup.api, "/api/catalog": api_catalog, "/store": act_store, "/brand": act_brand, "/api/questions": api_questions,
               "/api/brand": api_brand,
               "/api/scan": api_scan_start,
               "/api/waitlist": waitlist.api,
               "/api/support": support.api,
               "/settings/password": settings_page.act_password,
               "/settings/cancel": settings_page.act_cancel,
               "/settings/mcp-key": settings_page.act_mcp_key,
               "/oauth/authorize": lambda q, form: (lambda r: r if r[0] == 303 else (r[0], page("Connect", r[1])))(__import__("mcp_oauth").authorize_act(q, form)),
               "/settings/keep": settings_page.act_keep,
               "/api/linkcheck": linkcheck.api}
LOGO = os.path.join(config.HERE, "logo.png")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    _set_cookie = None

    def _send(self, result):
        code, payload = result
        if code == 303:
            self.send_response(303)
            self.send_header("Location", payload)
            self._send_cookies()
            self.end_headers()
            return
        ctype, csp = "text/html; charset=utf-8", None
        if isinstance(payload, tuple) and payload[0] == "csp":     # a store's own page, shown inside Produkto
            import product_preview
            csp, payload = product_preview.CSP, payload[1]
        elif isinstance(payload, tuple):
            ctype, payload = "application/json", payload[1]
        data = payload.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.send_header("Content-Length", str(len(data)))
        self._send_cookies()
        self.end_headers()
        self.wfile.write(data)

    def _send_cookies(self):
        if self._set_cookie:
            self.send_header("Set-Cookie", self._set_cookie)
        # Keep the website's "signed in" marker in step with the real session.
        marker = None
        if self._set_cookie:
            marker = accounts.site_cookie_header(clear="Max-Age=0" in self._set_cookie)
        elif getattr(self, "_fix_marker", None):
            marker = accounts.site_cookie_header(clear=self._fix_marker == "clear")
        if marker:
            self.send_header("Set-Cookie", marker)

    def _session_token(self):
        from http.cookies import SimpleCookie
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie") or "")
        except Exception:                                       # noqa: BLE001
            return ""
        self._has_marker = accounts.SITE_COOKIE in jar
        return jar[accounts.COOKIE].value if accounts.COOKIE in jar else ""

    def _accounts(self, method, u, q):
        """Sign-in and store access. Returns a response to send, or None to carry on."""
        self._has_marker = False
        user = accounts.user_for(self._session_token())
        accounts.set_current(user)
        # Marker out of step with the session (signed in before it existed, or
        # the session expired): correct it on this visit.
        self._fix_marker = ("set" if user and not self._has_marker else
                            "clear" if not user and self._has_marker else None)
        path = u.path
        form = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            self._body = self.rfile.read(length).decode()
            form = dict(urllib.parse.parse_qsl(self._body))
        if path == "/login":
            if method == "GET":
                return (303, "/") if user else (200, accounts.login_page(nxt=q.get("next", "/")))
            code, payload, token = accounts.do_login(form)
            if token:
                self._set_cookie = accounts.cookie_header(token)
            return code, payload
        if path == "/logout":
            if user:
                db.write("DELETE FROM sessions WHERE token=?", (self._session_token(),))
            self._set_cookie = accounts.cookie_header("", clear=True)
            return 303, "/login"
        if path.startswith("/reset/"):
            token = path[len("/reset/"):]
            if method == "GET":
                return accounts.reset_page(token)
            code, payload, session = accounts.accept_reset(token, form)
            if session:
                self._set_cookie = accounts.cookie_header(session)
            return code, payload
        if path == "/forgot":
            return accounts.request_reset(form) if method == "POST" else accounts.forgot_page()
        if path == "/welcome":
            return accounts.welcome_page(q)
        if path.startswith("/invite/"):
            token = path[len("/invite/"):]
            if method == "GET":
                return accounts.invite_page(token)
            code, payload, session = accounts.accept_invite(token, form)
            if session:
                self._set_cookie = accounts.cookie_header(session)
            return code, payload
        if path.startswith(accounts.PUBLIC):
            return None
        if not user:
            if method == "GET" and not path.startswith("/api/"):
                nxt = self.path if self.path != "/" else ""
                return 303, "/login" + ("?next=" + urllib.parse.quote(nxt) if nxt else "")
            return 401, ("json", json.dumps({"error": "Your session ended. Sign in again."}))
        if (path == "/admin" or path.startswith("/admin/") or path == "/costs") and not user["is_admin"]:
            return 404, page("Not found", "<h1>Not found</h1>")
        if path == "/admin":                             # hub.py: the admin hub, everything in one place
            import hub
            return 200, hub.document(q)
        if path == "/admin/self-visibility" and method == "POST":   # self_visibility.py: Produkto's own AI visibility
            import self_visibility
            return 303, "/admin?sv=" + urllib.parse.quote(self_visibility.start()[1])
        if path == "/admin/accounts":
            return accounts.admin_page(q)
        if path == "/admin/invite" and method == "POST":
            return accounts.create_invite(form)
        if path == "/admin/reset" and method == "POST":
            return accounts.create_reset(form)
        if path == "/admin/disable" and method == "POST":
            return accounts.set_disabled(form)
        if path == "/admin/third-party":                 # third_party.py: manual pull, off unless PRODUKTO_THIRD_PARTY=1
            import third_party
            note = third_party.start(form.get("d", ""))[1] if method == "POST" else ""
            return 200, page("Third-party context", third_party.admin_body(form if method == "POST" else q, note))
        # Store access: every store named in the request must be one this user owns.
        # A new store being added (POST /store) is claimed inside act_store instead.
        domains = [v for v in (q.get("d"), form.get("d"), q.get("domain") if path != "/new" else None) if v]
        tokens = [v for v in (q.get("t"), q.get("token"), form.get("token")) if v]
        if path.startswith("/r/"):
            tokens.append(path.split("/")[2])
        for t in tokens:
            row = db.one("SELECT p.store_domain FROM scans s JOIN prompt_sets p ON p.id=s.prompt_set_id "
                         "WHERE s.token=?", (t,))
            if row:
                domains.append(row["store_domain"])
        pid = q.get("id", "")
        if pid.isdigit():
            row = db.one("SELECT store_domain FROM products WHERE id=?", (int(pid),))
            if row:
                domains.append(row["store_domain"])
        if any(not accounts.can_see(d) for d in domains):
            return 404, page("Not found", "<h1>Not found</h1>")
        return None

    def _handle(self, method):
        evidence.clear_cache()
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        self._body = None
        try:
            if u.path == "/mcp":
                return self._mcp(method)
            if u.path.startswith(("/.well-known/oauth", "/.well-known/openid", "/oauth/register", "/oauth/token")):
                import mcp_oauth
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode() if method == "POST" else ""
                out = mcp_oauth.handle(method, u.path, body)
                if out is None:
                    return self._raw(404, "", {})
                return self._raw(*out)
            gate = self._accounts(method, u, q)
            if gate is not None:
                return self._send(gate)
            if method == "GET":
                if u.path == "/shopify/callback":
                    return self._send(_content_agent.shopify_callback(q))
                if u.path.startswith("/content/media/") and u.path.endswith(".jpg"):   # an owner's uploaded photo
                    import article_learning
                    got = article_learning.media(u.path[len("/content/media/"):-len(".jpg")])
                    if not got:
                        return self._send((404, "<h1>Not found</h1>"))
                    self.send_response(200)
                    self.send_header("Content-Type", got[0])
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                    self.send_header("Content-Length", str(len(got[1])))
                    self.end_headers()
                    self.wfile.write(got[1])
                    return
                if u.path == "/content/fix-preview":             # a product fix on the real product page
                    import product_preview
                    return self._send(product_preview.preview(q))
                if u.path == "/content/stories":                 # the stories page (stories_hub.py), previewed
                    import stories_hub
                    return self._send(stories_hub.preview(q))
                if u.path == "/content/preview":                 # an AEO article, full page, as a shopper sees it
                    import content_review
                    return self._send(content_review.full_preview(q))
                if u.path.startswith("/content/cal/") and u.path.endswith(".ics"):
                    import content_calendar
                    code, text = content_calendar.ical(u.path[len("/content/cal/"):-len(".ics")]) \
                        if config.SHOW_CONTENT_AGENT or config.CONTENT_AGENT_ADMIN_ONLY else (404, "")
                    data = text.encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "text/calendar; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if u.path == "/content/export":
                    code, data, name = _content_agent.export(q)
                    if code != 200:
                        return self._send((code, data))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(data)))
                    self._send_cookies()
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if u.path == "/icon":
                    import icons
                    path, ctype = icons.fetch(q.get("d", ""), cached_only=True)
                    if not path:
                        # Not cached yet (now fetching in the background) or no
                        # logo: the initials tile shows. Don't let the browser
                        # remember the miss, so the logo appears next view.
                        self.send_response(404)
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    with open(path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Cache-Control", "public, max-age=604800")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if u.path == "/pimg":
                    # A rival product's photo when its page has one, else the
                    # brand logo. Loaded by the browser after the page, so a
                    # slow brand site never delays the dashboard.
                    import icons
                    # Cache only: never wait on a brand site during a page view.
                    # Unknown photos are fetched in the background; this view
                    # shows the logo, the next one the photo.
                    u = q.get("u", "")
                    # ChatGPT answers often carry the product's own image
                    # (images.openai.com/thumbnails/...): that IS the photo.
                    if icons.is_image_url(u):
                        by_url = u
                    else:
                        by_url = icons.product_photo(u, cached_only=True) if u else ""
                    by_shop = "" if by_url else icons.shop_photo(q.get("d", ""), q.get("n", ""), cached_only=True)
                    # Not on Shopify and no link (IKEA, BoConcept): image search.
                    by_search = "" if (by_url or by_shop or not q.get("b")) else \
                        icons.search_photo(q.get("b", ""), q.get("n", ""))
                    photo = by_url or by_shop or by_search
                    pending = by_url is None or by_shop is None or by_search is None
                    target = photo or ("/icon?d=" + urllib.parse.quote(q.get("d", "")))
                    self.send_response(302)
                    self.send_header("Location", target)
                    self.send_header("Cache-Control", "no-store" if pending else
                                     "public, max-age=%d" % (86400 if photo else 3600))
                    self.end_headers()
                    return
                if u.path in ("/favicon.png", "/favicon.ico"):
                    with open(os.path.join(config.HERE, "favicon.png"), "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "public, max-age=604800")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if u.path == "/logo.png":
                    with open(LOGO, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if u.path.startswith("/r/"):
                    parts = u.path.split("/")
                    if len(parts) == 4 and parts[3] == "answers":
                        return self._send(view_answers(parts[2], q))
                    if len(parts) == 4 and parts[3] == "questions":
                        return self._send(view_questions(parts[2], q))
                    if len(parts) == 4 and parts[3] == "citations":
                        import citation_panel
                        body = citation_panel.page(parts[2], q)
                        return self._send((200, page("Mentions & Citations", body)) if body is not None else (404, page("Not found", "<h1>Scan not found</h1>")))
                    return self._send(view_result(parts[2], q))
                fn = ROUTES_GET.get(u.path)
                if not fn:
                    return self._send((404, page("Not found", "<h1>Not found</h1>")))
                return self._send(fn(q))
            form = dict(urllib.parse.parse_qsl(self._body or ""))
            fn = ROUTES_POST.get(u.path)
            if not fn:
                return self._send((404, page("Not found", "<h1>Not found</h1>")))
            return self._send(fn(q, form))
        except Exception:                                       # noqa: BLE001
            traceback.print_exc()
            self._send((500, page("Error", "<h1>Something broke</h1>"
                                  "<pre>%s</pre>" % E(traceback.format_exc()))))

    def _raw(self, code, text, headers):
        """A reply for AI assistants: no cookies, readable from other sites."""
        data = (text or "").encode()
        self.send_response(code)
        for k, v in dict({"Access-Control-Allow-Origin": "*",
                          "Access-Control-Allow-Headers": "Authorization, Content-Type, Mcp-Session-Id, Mcp-Protocol-Version",
                          "Access-Control-Expose-Headers": "WWW-Authenticate, Mcp-Session-Id",
                          "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}, **headers).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._raw(204, "", {})

    def _mcp(self, method):
        """The hosted MCP endpoint: a merchant's AI assistant, signed in with a key, not a cookie."""
        import mcp_oauth
        import mcp_server
        if method != "POST":
            return self._raw(405, "", {"Allow": "POST"})
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
        code, text = mcp_server.http(body, self.headers.get("Authorization"))
        headers = {"Content-Type": "application/json"} if text else {}
        if code == 401:
            headers["WWW-Authenticate"] = mcp_oauth.challenge_header()
        return self._raw(code, text, headers)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def create_admin():
    """python3 app.py --create-admin you@example.com  (asks for the password)"""
    import getpass
    email = sys.argv[sys.argv.index("--create-admin") + 1] if len(sys.argv) > sys.argv.index("--create-admin") + 1 else input("Email: ")
    pw = getpass.getpass("Password (10+ characters): ")
    if len(pw) < 10 or pw != getpass.getpass("Again: "):
        print("Passwords too short or don't match. Nothing saved.")
        sys.exit(1)
    row = db.one("SELECT id FROM users WHERE email=?", (email.strip().lower(),))
    if row:
        db.write("UPDATE users SET pw_hash=?, is_admin=1 WHERE id=?", (accounts.hash_pw(pw), row["id"]))
        print("Updated admin", email)
    else:
        accounts.create_user(email, pw, is_admin=True)
        print("Created admin", email)


def main():
    db.init()
    waitlist.init()
    support.init()
    accounts.init()
    billing.init()
    if "--create-admin" in sys.argv:
        return create_admin()
    if "--check" in sys.argv:
        try:
            for line in llm.check():
                print("OK  ", line)
        except llm.LLMError as e:
            print("FAILED:", e)
            sys.exit(1)
        return
    scan.recover_interrupted()
    if config.DAILY_SCANS and scheduler.start():
        print("Daily scans on: one scan per store per day, %d run per question, "
              "engines %s." % (config.RUNS_PER_QUESTION, ", ".join(scan._engines())))
        for domain in scheduler.scheduled():
            due = "due now" if domain in scheduler.due() else "next at %02d:00" % scheduler.slot_hour(domain)
            print("  %s - %s" % (domain, due))
    print("Produkto MVP running on http://localhost:%d  (Ctrl-C to stop)" % config.PORT)
    if not config.api_key():
        print("Note: no OpenAI key yet. Copy .env.example to .env and add it.")
    if config.ANSWER_SOURCE == "apify" and not config.env("APIFY_TOKEN"):
        print("Note: answers are set to come from Apify but APIFY_TOKEN is "
              "missing from .env, so scans will fail. Add it, or set "
              'config.ANSWER_SOURCE = "openai" to go back to the API '
              "(about 19x the cost per answer).")
    ThreadingHTTPServer(("127.0.0.1", config.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
