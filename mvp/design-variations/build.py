"""Builds five static design variations of the Produkto catalog overview.

Real figures come from the Clubhouse Skin overview (last 30 days, 9 Oct 2026).
The daily trend lines are illustrative shapes: the mockups only show layout.
Run: python3 build.py  ->  writes a.html ... e.html and index.html here.
"""
import math
import pathlib

OUT = pathlib.Path(__file__).parent
CDN = "https://cdn.shopify.com/s/files/1/0638/3901/1004/files/"

KPI = [
    ("Avg. visibility", "3%", "of answers mention your products"),
    ("Share of voice", "1.5%", "of all product mentions"),
    ("Average position", "#1.1", "when mentioned · 1 = first"),
    ("Win rate", "89%", "of shared answers you rank higher"),
]
RANK = [  # product, brand, mentioned in, avg pos, own
    ("Hydrating Cleanser", "CeraVe", 9, 1.5, False),
    ("Gentle Exfoliating SA Cleanser", "Cetaphil", 5, 1.3, False),
    ("C.E.O. Glow Vitamin C + Turmeric Face Oil", "Sunday Riley", 5, 1.5, False),
    ("Squalane + Vitamin C Rose Firming Oil", "Biossance", 5, 2.3, False),
    ("Vitamin C Glow Face Oil", "DERMA E", 5, 1.8, False),
    ("Gentle Skin Cleanser", "Cetaphil", 4, 2.7, False),
    ("Helsinki Moisturiser", "Clubhouse Skin", 3, 1.1, True),
]
MINE = [  # product, image, visibility, position, price
    ("Helsinki Moisturiser", "CLUBHOUSE-SKIN-HELSINKI-MOISTURISER_PDP_DT_01_f1010d1d-8596-4dbf-9d11-91a4ddcf9ace.jpg", 3, "#1.1", "$69"),
    ("Amalfi Vitamin-C Face Oil", "CLUBHOUSE-SKIN_AMALFI-VIT-C_PDP_DT_01_676ee991-b6f2-49f8-b4b1-ace3a42de234.jpg", 0, "—", "—"),
    ("Frontier Cleanser", "CLUBHOUSE-SKIN-FRONTIER-CLEANSER_PDP_DT_01_65449da1-a297-41eb-a3e5-35ec80153b11.jpg", 0, "—", "—"),
    ("Essentials Set", "CHS_Essentials-Set_PDP_1.jpg", 0, "—", "—"),
    ("Full Clubhouse Set", "CLUBHOUSE-SKIN_ROUTINE_PDP_DT_01_bc3da229-b518-464f-8dcf-b508d8a18deb.jpg", 0, "—", "—"),
    ("Peau De Clubhouse Hat", "CLUBHOUSE-SKIN_MEMBERS-HAT_PDP_DT_01_90467aed-8988-475f-a39c-b2878915b6dc.jpg", 0, "—", "—"),
]
DATES = ["21 Sep", "24 Sep", "27 Sep", "30 Sep", "3 Oct", "6 Oct", "9 Oct"]


def series(seed, base, amp):
    return [max(0, base + amp * math.sin(i * 0.9 + seed) + amp * 0.6 * math.cos(i * 2.3 + seed * 2)) for i in range(19)]


SERIES = [  # label, values
    ("Clubhouse Skin", series(0.3, 3, 1.6)),
    ("CeraVe", series(1.1, 9, 3.5)),
    ("Cetaphil", series(2.0, 5, 2.4)),
    ("Sunday Riley", series(3.2, 5, 2.2)),
]


def chart(w, h, colors, grid, label, own_width=2.5, other_width=1.6, area=None):
    pad_l, pad_b, top = 34, 24, 8
    iw, ih = w - pad_l - 6, h - pad_b - top
    ymax = 20
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" role="img" aria-label="Visibility over time">']
    for v in (0, 5, 10, 15, 20):
        y = top + ih - v / ymax * ih
        out.append(f'<line x1="{pad_l}" x2="{w-6}" y1="{y:.1f}" y2="{y:.1f}" stroke="{grid}" stroke-dasharray="2 4"/>')
        out.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" fill="{label}" font-size="11">{v}%</text>')
    for i, d in enumerate(DATES):
        x = pad_l + iw * i / (len(DATES) - 1)
        out.append(f'<text x="{x:.1f}" y="{h-6}" text-anchor="middle" fill="{label}" font-size="11">{d}</text>')
    for idx, (name, vals) in reversed(list(enumerate(SERIES))):
        pts = [(pad_l + iw * i / (len(vals) - 1), top + ih - v / ymax * ih) for i, v in enumerate(vals)]
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        if idx == 0 and area:
            out.append(f'<path d="{d} L{pts[-1][0]:.1f},{top+ih} L{pts[0][0]:.1f},{top+ih} Z" fill="{area}"/>')
        sw = own_width if idx == 0 else other_width
        out.append(f'<path d="{d}" fill="none" stroke="{colors[idx]}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')
        if idx == 0:
            x, y = pts[-1]
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colors[0]}" stroke="#fff" stroke-width="2"/>')
    out.append("</svg>")
    return "".join(out)


I = {  # 16px line icons, 1.6 stroke
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "q": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/>',
    "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    "doc": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6M12 17h.01"/>',
    "cog": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    "play": '<path d="M7 4v16l13-8z"/>',
    "down": '<path d="m6 9 6 6 6-6"/>',
    "cal": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
}


def ic(name, size=16):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{I[name]}</svg>')


NAV = [("grid", "Dashboard", None), ("q", "Buyer questions", None), ("spark", "Opportunities", "44"), ("doc", "Content agents", None)]
import base64
_B64 = base64.b64encode((OUT.parent / "app" / "logo.png").read_bytes()).decode()
LOGO = f'<img src="data:image/png;base64,{_B64}" alt="" width="26" height="26" style="border-radius:7px;display:block">'


def page(title, font, css, body):
    fam = font.replace(" ", "+")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Produkto · {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={fam}:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{min-width:1280px;font-family:'{font}',system-ui,sans-serif;-webkit-font-smoothing:antialiased;font-feature-settings:'tnum' 1,'cv11' 1}}
button{{font:inherit;cursor:pointer}}img{{display:block}}a{{color:inherit;text-decoration:none}}
.note{{font-size:11px;opacity:.6;margin-top:10px}}{css}</style></head><body>{body}</body></html>"""


def rank_rows(cls_own, bar_color, track):
    rows = []
    for i, (p, b, m, pos, own) in enumerate(RANK, 1):
        rows.append(f'<tr class="{cls_own if own else ""}"><td class="n">{i}</td><td><div class="pn">{p}</div><div class="pb">{b}</div></td>'
                    f'<td class="num"><div class="bar"><span style="width:{m/10*100:.0f}%;background:{bar_color if not own else "var(--own)"}"></span></div>{m}%</td>'
                    f'<td class="num">{pos}</td></tr>')
    return "".join(rows)


def mine_rows():
    out = []
    for p, img, v, pos, price in MINE:
        state = '<span class="pill ok">Mentioned</span>' if v else '<span class="pill">Not mentioned yet</span>'
        out.append(f'<tr><td><div class="prod"><img src="{CDN+img}" alt="" width="36" height="36"><span>{p}</span></div></td>'
                   f'<td class="num">{v}%</td><td class="num">{pos}</td><td class="num">{price}</td><td>{state}</td></tr>')
    return "".join(out)


# ---------------------------------------------------------------- A. Clarity
A_CSS = """
:root{--bg:#fff;--side:#fafbfc;--line:#e8ebf0;--ink:#0b1b35;--mute:#5d6878;--acc:#0b1b35;--own:#2f6bff}
body{background:var(--bg);color:var(--ink)}
.app{display:grid;grid-template-columns:240px 1fr;min-height:100vh}
aside{background:var(--side);border-right:1px solid var(--line);padding:18px 12px;display:flex;flex-direction:column;gap:4px}
.brand{display:flex;gap:10px;align-items:center;font-weight:700;letter-spacing:.08em;font-size:13px;padding:2px 8px 18px}
.store{display:flex;gap:10px;align-items:center;padding:8px;border:1px solid var(--line);border-radius:10px;background:#fff;margin-bottom:14px}
.store b{font-size:13px;display:block}.store small{font-size:11.5px;color:var(--mute)}
.av{width:30px;height:30px;border-radius:8px;background:#e9eefb;color:var(--ink);display:grid;place-items:center;font-size:11px;font-weight:700}
.nav{display:flex;gap:10px;align-items:center;padding:8px 10px;border-radius:8px;font-size:13.5px;color:#3a4558;font-weight:500}
.nav.on{background:#eef1f6;color:var(--ink);font-weight:600}.nav .ct{margin-left:auto;font-size:11px;background:var(--ink);color:#fff;border-radius:99px;padding:1px 7px}
.sp{flex:1}
main{padding:28px 40px 48px;max-width:1240px}
.top{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:20px}
h1{font-size:22px;font-weight:650;letter-spacing:-.02em}
.sub{color:var(--mute);font-size:13px;margin-top:4px;display:flex;gap:8px;align-items:center}.dot{width:7px;height:7px;border-radius:50%;background:#1aa36b}
.btn{display:inline-flex;gap:8px;align-items:center;background:var(--ink);color:#fff;border:0;border-radius:8px;padding:9px 14px;font-size:13px;font-weight:600}
.bar2{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);margin-bottom:22px}
.tabs{display:flex;gap:24px}.tab{padding:10px 0;font-size:13.5px;color:var(--mute);font-weight:500;border-bottom:2px solid transparent;margin-bottom:-1px}.tab.on{color:var(--ink);border-color:var(--ink);font-weight:600}
.filters{display:flex;gap:8px;align-items:center}.sel{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12.5px;background:#fff;color:#333d4d}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:12px;margin-bottom:20px}
.kpi{padding:18px 20px}.kpi+.kpi{border-left:1px solid var(--line)}
.kpi .l{font-size:12.5px;color:var(--mute);font-weight:500}.kpi .v{font-size:28px;font-weight:650;letter-spacing:-.02em;margin:6px 0 2px}.kpi .s{font-size:12px;color:var(--mute)}
.grid{display:grid;grid-template-columns:1.35fr 1fr;gap:20px;margin-bottom:20px}
.panel{border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.ph{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.ph h2{font-size:14px;font-weight:600}.ph small{color:var(--mute);font-size:12px}
.legend{display:flex;gap:14px;font-size:12px;color:var(--mute);margin-top:8px}.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11.5px;color:var(--mute);font-weight:500;padding:0 8px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 8px;border-bottom:1px solid #f1f3f6;vertical-align:middle}tr:last-child td{border:0}
.n{color:var(--mute);width:22px}.pn{font-weight:550;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px}.pb{font-size:11.5px;color:var(--mute)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th.num{text-align:right}
.bar{display:inline-block;width:60px;height:5px;background:#eef1f5;border-radius:3px;margin-right:8px;vertical-align:middle;overflow:hidden}.bar span{display:block;height:100%;border-radius:3px}
tr.own td{background:#f3f6ff}tr.own .pn{color:#1d4fd6}
.prod{display:flex;gap:12px;align-items:center;font-weight:550}.prod img{border-radius:8px;object-fit:cover;background:#f2f2f2}
.pill{font-size:11.5px;padding:3px 9px;border-radius:99px;background:#f1f3f6;color:#5d6878;font-weight:500}.pill.ok{background:#e6f6ee;color:#137a50}
"""


def build_a():
    colors = ["#2f6bff", "#0b1b35", "#8a96a8", "#c3cad6"]
    kp = "".join(f'<div class="kpi"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for l, v, s in KPI)
    nav = "".join(f'<a class="nav{" on" if i == 0 else ""}">{ic(n)}{t}{f"<span class=ct>{c}</span>" if c else ""}</a>' for i, (n, t, c) in enumerate(NAV))
    leg = "".join(f'<span><i style="background:{c}"></i>{s[0]}</span>' for c, s in zip(colors, SERIES))
    body = f"""<div class="app"><aside><div class="brand">{LOGO}PRODUKTO</div>
<div class="store"><div class="av">CS</div><div><b>Clubhouse Skin</b><small>clubhouseskin.com</small></div></div>
{nav}<div class="sp"></div><a class="nav">{ic('help')}Support</a><a class="nav">{ic('cog')}Settings</a></aside>
<main><div class="top"><div><h1>Catalog overview</h1><div class="sub"><span class="dot"></span>Updated 8 Oct, 2:53 PM ET · next scan tomorrow 1:00 AM ET</div></div>
<button class="btn">{ic('play',14)}Run catalog scan</button></div>
<div class="bar2"><div class="tabs"><a class="tab on">Overview</a><a class="tab">Answers</a><a class="tab">Mentions &amp; Citations</a></div>
<div class="filters"><span class="sel">{ic('cal',14)}Last 30 days{ic('down',14)}</span><span class="sel">Daily{ic('down',14)}</span><span class="sel">All engines{ic('down',14)}</span></div></div>
<div class="kpis">{kp}</div>
<div class="grid"><section class="panel"><div class="ph"><h2>Visibility over time</h2><small>Share of answers that mention each brand</small></div>
{chart(640, 250, colors, "#e4e8ee", "#8590a1", area="rgba(47,107,255,.07)")}<div class="legend">{leg}</div></section>
<section class="panel"><div class="ph"><h2>Product rankings</h2><small>1,297 mentions</small></div>
<table><tr><th></th><th>Product</th><th class="num">Mentioned in</th><th class="num">Pos.</th></tr>{rank_rows("own", "#0b1b35", "")}</table></section></div>
<section class="panel"><div class="ph"><h2>Your products</h2><small>6 products · 1 mentioned this period</small></div>
<table><tr><th>Product</th><th class="num">Visibility</th><th class="num">Position</th><th class="num">Mentioned price</th><th>Status</th></tr>{mine_rows()}</table></section>
<p class="note">Design variation A · figures from Clubhouse Skin, last 30 days; trend lines illustrative.</p></main></div>"""
    return page("A Clarity", "Geist", A_CSS, body)


# ---------------------------------------------------------------- B. Navy rail
def build_b():
    css = """
:root{--bg:#eef2f8;--card:#fff;--line:#dfe5ef;--ink:#0b1b35;--mute:#5a667a;--own:#3b7bff}
body{background:var(--bg);color:var(--ink)}
.app{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
aside{background:#0b1b35;color:#c9d3e6;padding:20px 14px;display:flex;flex-direction:column;gap:3px}
.brand{display:flex;gap:10px;align-items:center;color:#fff;font-weight:700;letter-spacing:.1em;font-size:13px;padding:0 8px 22px}
.brand img{box-shadow:0 0 0 1px rgba(255,255,255,.15)}
.store{display:flex;gap:10px;align-items:center;padding:10px;border-radius:10px;background:rgba(255,255,255,.06);margin-bottom:18px;color:#fff}
.store small{display:block;color:#93a1bb;font-size:11.5px}.store b{font-size:13px}
.av{width:30px;height:30px;border-radius:8px;background:#2a3d63;display:grid;place-items:center;font-size:11px;font-weight:700}
.nav{display:flex;gap:11px;align-items:center;padding:9px 10px;border-radius:8px;font-size:13.5px;font-weight:500}
.nav.on{background:#1d3157;color:#fff}.nav .ct{margin-left:auto;font-size:11px;background:#3b7bff;color:#fff;border-radius:99px;padding:1px 7px}
.sp{flex:1}
main{padding:24px 32px 44px}
.hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
.crumb{font-size:12.5px;color:var(--mute)}h1{font-size:24px;font-weight:700;letter-spacing:-.02em;margin-top:2px}
.btn{display:inline-flex;gap:8px;align-items:center;background:#0b1b35;color:#fff;border:0;border-radius:9px;padding:10px 16px;font-size:13px;font-weight:600;box-shadow:0 2px 6px rgba(11,27,53,.2)}
.ghost{background:#fff;color:var(--ink);border:1px solid var(--line);box-shadow:none}
.tools{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.seg{display:inline-flex;background:#dfe6f2;border-radius:10px;padding:3px}.seg a{padding:7px 14px;border-radius:8px;font-size:13px;color:#4b5870;font-weight:500}.seg a.on{background:#fff;color:var(--ink);font-weight:600;box-shadow:0 1px 2px rgba(11,27,53,.1)}
.sel{display:inline-flex;gap:6px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:9px;padding:7px 11px;font-size:12.5px;margin-left:8px}
.card{background:var(--card);border-radius:14px;box-shadow:0 1px 2px rgba(11,27,53,.05),0 6px 20px rgba(11,27,53,.05)}
.hero{display:grid;grid-template-columns:300px 1fr;margin-bottom:18px}
.big{padding:24px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:18px}
.big .l{font-size:12.5px;color:var(--mute);font-weight:600}.big .v{font-size:44px;font-weight:700;letter-spacing:-.03em;line-height:1}.big .s{font-size:12.5px;color:var(--mute);margin-top:6px}
.mini{display:grid;grid-template-columns:1fr 1fr;gap:14px;border-top:1px solid var(--line);padding-top:16px}.mini div b{display:block;font-size:20px;letter-spacing:-.02em}.mini span{font-size:11.5px;color:var(--mute)}
.ch{padding:20px 22px}.ph{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}.ph h2{font-size:14.5px;font-weight:650}.ph small{font-size:12px;color:var(--mute)}
.legend{display:flex;gap:16px;font-size:12px;color:var(--mute);margin-top:6px}.legend i{display:inline-block;width:10px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.two .card{padding:20px 22px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11.5px;color:var(--mute);font-weight:600;padding:0 6px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 6px;border-bottom:1px solid #eef1f6}tr:last-child td{border:0}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th.num{text-align:right}
.n{color:var(--mute);width:20px}.pn{font-weight:600;max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pb{font-size:11.5px;color:var(--mute)}
.bar{display:inline-block;width:56px;height:6px;border-radius:3px;background:#edf1f7;margin-right:8px;vertical-align:middle;overflow:hidden}.bar span{display:block;height:100%}
tr.own td{background:#eef4ff}
.prod{display:flex;gap:11px;align-items:center;font-weight:600}.prod img{border-radius:9px;object-fit:cover}
.pill{font-size:11px;padding:3px 8px;border-radius:6px;background:#f0f2f6;color:#5a667a;font-weight:600}.pill.ok{background:#e3f5ec;color:#147a4f}
"""
    colors = ["#3b7bff", "#0b1b35", "#22a06b", "#9aa6ba"]
    nav = "".join(f'<a class="nav{" on" if i == 0 else ""}">{ic(n)}{t}{f"<span class=ct>{c}</span>" if c else ""}</a>' for i, (n, t, c) in enumerate(NAV))
    leg = "".join(f'<span><i style="background:{c}"></i>{s[0]}</span>' for c, s in zip(colors, SERIES))
    body = f"""<div class="app"><aside><div class="brand">{LOGO}PRODUKTO</div>
<div class="store"><div class="av">CS</div><div><b>Clubhouse Skin</b><small>clubhouseskin.com</small></div></div>
{nav}<div class="sp"></div><a class="nav">{ic('help')}Support</a><a class="nav">{ic('cog')}Settings</a></aside>
<main><div class="hd"><div><div class="crumb">Clubhouse Skin › Catalog</div><h1>Overview</h1></div>
<div><button class="btn ghost">Last updated 8 Oct, 2:53 PM ET</button> <button class="btn">{ic('play',14)}Run scan</button></div></div>
<div class="tools"><div class="seg"><a class="on">Overview</a><a>Answers</a><a>Mentions &amp; Citations</a></div>
<div><span class="sel">{ic('cal',14)}Last 30 days{ic('down',14)}</span><span class="sel">Daily{ic('down',14)}</span><span class="sel">All engines{ic('down',14)}</span></div></div>
<div class="card hero"><div class="big"><div><div class="l">Avg. visibility</div><div class="v">3%</div><div class="s">of AI answers mention your products</div></div>
<div class="mini"><div><b>1.5%</b><span>Share of voice</span></div><div><b>#1.1</b><span>Avg. position</span></div><div><b>89%</b><span>Win rate</span></div><div><b>1,297</b><span>Mentions tracked</span></div></div></div>
<div class="ch"><div class="ph"><h2>Visibility over time</h2><small>Daily · 17 scans</small></div>{chart(820, 240, colors, "#e3e8f0", "#8592a8", area="rgba(59,123,255,.08)")}<div class="legend">{leg}</div></div></div>
<div class="two"><section class="card"><div class="ph"><h2>Product rankings</h2><small>All products in answers</small></div>
<table><tr><th></th><th>Product</th><th class="num">Mentioned in</th><th class="num">Pos.</th></tr>{rank_rows("own", "#9aa6ba", "")}</table></section>
<section class="card"><div class="ph"><h2>Your products</h2><small>1 of 6 mentioned</small></div>
<table><tr><th>Product</th><th class="num">Vis.</th><th class="num">Pos.</th><th class="num">Price</th><th>Status</th></tr>{mine_rows()}</table></section></div>
<p class="note">Design variation B · figures from Clubhouse Skin, last 30 days; trend lines illustrative.</p></main></div>"""
    return page("B Navy rail", "Manrope", css, body)


# ---------------------------------------------------------------- C. Briefing (top bar)
def build_c():
    css = """
:root{--bg:#f4f5f7;--card:#fff;--line:#e2e5ea;--ink:#0b1b35;--mute:#5f6876;--own:#e8590c}
body{background:var(--bg);color:var(--ink)}
header{background:#fff;border-bottom:1px solid var(--line)}
.bar{max-width:1280px;margin:0 auto;padding:0 32px;height:60px;display:flex;align-items:center;gap:28px}
.brand{display:flex;gap:10px;align-items:center;font-weight:700;letter-spacing:.1em;font-size:13px}
nav{display:flex;gap:4px;height:100%}nav a{display:flex;align-items:center;gap:8px;padding:0 12px;font-size:13.5px;color:var(--mute);font-weight:500;border-bottom:2px solid transparent}nav a.on{color:var(--ink);border-color:var(--ink);font-weight:600}
nav .ct{font-size:11px;background:#fde7da;color:#b34507;border-radius:99px;padding:1px 7px;font-weight:600}
.right{margin-left:auto;display:flex;gap:10px;align-items:center}.store{display:flex;gap:8px;align-items:center;border:1px solid var(--line);border-radius:99px;padding:4px 12px 4px 4px;font-size:13px;font-weight:600}
.av{width:26px;height:26px;border-radius:50%;background:#0b1b35;color:#fff;display:grid;place-items:center;font-size:10px;font-weight:700}
.icb{width:34px;height:34px;border-radius:50%;border:1px solid var(--line);display:grid;place-items:center;color:var(--mute);background:#fff}
main{max-width:1280px;margin:0 auto;padding:30px 32px 48px}
.lead{display:flex;justify-content:space-between;align-items:flex-end;gap:40px;margin-bottom:26px}
.lead h1{font-size:30px;line-height:1.2;font-weight:600;letter-spacing:-.025em;max-width:760px}.lead h1 em{font-style:normal;color:var(--own)}
.lead p{color:var(--mute);font-size:13.5px;margin-top:10px}
.btn{display:inline-flex;gap:8px;align-items:center;background:#0b1b35;color:#fff;border:0;border-radius:99px;padding:10px 18px;font-size:13px;font-weight:600;white-space:nowrap}
.sub{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.tabs{display:flex;gap:6px}.tabs a{padding:7px 14px;border-radius:99px;font-size:13px;font-weight:500;color:var(--mute)}.tabs a.on{background:#0b1b35;color:#fff}
.sel{display:inline-flex;gap:6px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:99px;padding:7px 13px;font-size:12.5px;margin-left:6px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px}
.main{display:grid;grid-template-columns:1fr 290px;margin-bottom:18px}
.ch{padding:22px 24px}.side{border-left:1px solid var(--line);display:flex;flex-direction:column}
.k{padding:18px 22px;flex:1}.k+.k{border-top:1px solid var(--line)}.k .l{font-size:12px;color:var(--mute);font-weight:500}.k .v{font-size:26px;font-weight:650;letter-spacing:-.02em;margin-top:4px}.k .s{font-size:11.5px;color:var(--mute)}
.ph{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}.ph h2{font-size:15px;font-weight:600}.ph small{font-size:12px;color:var(--mute)}
.legend{display:flex;gap:16px;font-size:12px;color:var(--mute);margin-top:8px}.legend i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.two{display:grid;grid-template-columns:1.1fr 1fr;gap:18px}.two .card{padding:20px 22px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11.5px;color:var(--mute);font-weight:500;padding:0 6px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 6px;border-bottom:1px solid #f0f2f5}tr:last-child td{border:0}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th.num{text-align:right}
.n{color:var(--mute);width:20px}.pn{font-weight:550;max-width:250px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pb{font-size:11.5px;color:var(--mute)}
.bar{display:inline-block;width:60px;height:5px;background:#eef0f3;border-radius:3px;margin-right:8px;vertical-align:middle;overflow:hidden}.bar span{display:block;height:100%}
tr.own .pn{color:var(--own)}tr.own td{background:#fff6f0}
.prod{display:flex;gap:11px;align-items:center;font-weight:550}.prod img{border-radius:50%;object-fit:cover}
.pill{font-size:11px;padding:3px 9px;border-radius:99px;background:#f0f2f5;color:#5f6876;font-weight:500}.pill.ok{background:#fde7da;color:#b34507}
"""
    colors = ["#e8590c", "#0b1b35", "#7b8696", "#c2c8d1"]
    nav = "".join(f'<a class="{"on" if i == 0 else ""}">{t}{f"<span class=ct>{c}</span>" if c else ""}</a>' for i, (n, t, c) in enumerate(NAV))
    leg = "".join(f'<span><i style="background:{c}"></i>{s[0]}</span>' for c, s in zip(colors, SERIES))
    side = "".join(f'<div class="k"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for l, v, s in KPI)
    body = f"""<header><div class="bar"><div class="brand">{LOGO}PRODUKTO</div><nav>{nav}</nav>
<div class="right"><span class="store"><span class="av">CS</span>Clubhouse Skin{ic('down',14)}</span><span class="icb">{ic('help')}</span><span class="icb">{ic('cog')}</span></div></div></header>
<main><div class="lead"><div><h1>AI mentions <em>1 of your 6 products</em>. When it does, Helsinki Moisturiser ranks first.</h1>
<p>Last 30 days · 17 daily scans · updated 8 Oct, 2:53 PM ET</p></div><button class="btn">{ic('play',14)}Run catalog scan</button></div>
<div class="sub"><div class="tabs"><a class="on">Overview</a><a>Answers</a><a>Mentions &amp; Citations</a></div>
<div><span class="sel">{ic('cal',14)}Last 30 days{ic('down',14)}</span><span class="sel">Daily{ic('down',14)}</span><span class="sel">All engines{ic('down',14)}</span></div></div>
<div class="card main"><div class="ch"><div class="ph"><h2>Visibility over time</h2><small>Share of answers mentioning each brand</small></div>
{chart(900, 300, colors, "#e6e9ee", "#8a93a2")}<div class="legend">{leg}</div></div><div class="side">{side}</div></div>
<div class="two"><section class="card"><div class="ph"><h2>Who AI recommends</h2><small>Top products across all answers</small></div>
<table><tr><th></th><th>Product</th><th class="num">Mentioned in</th><th class="num">Pos.</th></tr>{rank_rows("own", "#0b1b35", "")}</table></section>
<section class="card"><div class="ph"><h2>Your products</h2><small>6 products</small></div>
<table><tr><th>Product</th><th class="num">Vis.</th><th class="num">Pos.</th><th class="num">Price</th><th>Status</th></tr>{mine_rows()}</table></section></div>
<p class="note">Design variation C · figures from Clubhouse Skin, last 30 days; trend lines illustrative.</p></main>"""
    return page("C Briefing", "Schibsted Grotesk", css, body)


# ---------------------------------------------------------------- D. Catalog shelf
def build_d():
    css = """
:root{--bg:#fbfbfa;--line:#e7e6e3;--ink:#14171c;--mute:#666b73;--acc:#0b1b35;--own:#0f9d6e}
body{background:var(--bg);color:var(--ink)}
.app{display:grid;grid-template-columns:68px 1fr;min-height:100vh}
aside{border-right:1px solid var(--line);background:#fff;display:flex;flex-direction:column;align-items:center;padding:16px 0;gap:6px}
aside a{width:42px;height:42px;border-radius:11px;display:grid;place-items:center;color:#7a7f87;position:relative}aside a.on{background:#0b1b35;color:#fff}
aside .ct{position:absolute;top:4px;right:2px;font-size:9px;background:var(--own);color:#fff;border-radius:99px;padding:0 4px;font-weight:700}
aside .lg{margin-bottom:14px}.sp{flex:1}
main{padding:24px 36px 48px}
.hd{display:flex;align-items:center;gap:14px;margin-bottom:22px}
.av{width:40px;height:40px;border-radius:10px;background:#0b1b35;color:#fff;display:grid;place-items:center;font-weight:700;font-size:13px}
h1{font-size:20px;font-weight:650;letter-spacing:-.02em}.hd small{display:block;color:var(--mute);font-size:12.5px;margin-top:2px}
.hd .r{margin-left:auto;display:flex;gap:8px;align-items:center}
.sel{display:inline-flex;gap:6px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:8px;padding:7px 11px;font-size:12.5px}
.btn{display:inline-flex;gap:8px;align-items:center;background:#0b1b35;color:#fff;border:0;border-radius:8px;padding:9px 14px;font-size:13px;font-weight:600}
.tabs{display:flex;gap:22px;border-bottom:1px solid var(--line);margin-bottom:22px}.tabs a{padding:10px 0;font-size:13.5px;color:var(--mute);border-bottom:2px solid transparent;margin-bottom:-1px;font-weight:500}.tabs a.on{color:var(--ink);border-color:var(--ink);font-weight:600}
h2{font-size:14.5px;font-weight:650;margin-bottom:12px;display:flex;justify-content:space-between;align-items:baseline}h2 small{font-weight:400;font-size:12px;color:var(--mute)}
.shelf{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-bottom:26px}
.item{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden}
.item img{width:100%;aspect-ratio:1/1;object-fit:cover;background:#f1f0ed}
.item .b{padding:12px 14px}.item .t{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .v{display:flex;justify-content:space-between;align-items:baseline;margin-top:8px}.item .v b{font-size:22px;letter-spacing:-.02em}.item .v span{font-size:11.5px;color:var(--mute)}
.item.on{border-color:var(--own);box-shadow:0 0 0 1px var(--own)}.item.on .v b{color:var(--own)}
.meter{height:4px;border-radius:2px;background:#efeeeb;margin-top:8px;overflow:hidden}.meter span{display:block;height:100%;background:var(--own)}
.row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:0;background:#fff;border:1px solid var(--line);border-radius:14px;margin-bottom:22px}
.k{padding:16px 20px}.k+.k{border-left:1px solid var(--line)}.k .l{font-size:12px;color:var(--mute)}.k .v{font-size:24px;font-weight:650;letter-spacing:-.02em;margin-top:4px}
.two{display:grid;grid-template-columns:1.3fr 1fr;gap:18px}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.legend{display:flex;gap:16px;font-size:12px;color:var(--mute);margin-top:6px}.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11.5px;color:var(--mute);font-weight:500;padding:0 6px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 6px;border-bottom:1px solid #f1f0ee}tr:last-child td{border:0}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th.num{text-align:right}
.n{color:var(--mute);width:20px}.pn{font-weight:600;max-width:210px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pb{font-size:11.5px;color:var(--mute)}
.bar{display:inline-block;width:50px;height:5px;background:#efeeeb;border-radius:3px;margin-right:8px;vertical-align:middle;overflow:hidden}.bar span{display:block;height:100%}
tr.own .pn{color:var(--own)}
"""
    colors = ["#0f9d6e", "#0b1b35", "#8b8f96", "#c8cbcf"]
    icons = "".join(f'<a class="{"on" if i == 0 else ""}" title="{t}">{ic(n,20)}{f"<span class=ct>{c}</span>" if c else ""}</a>' for i, (n, t, c) in enumerate(NAV))
    shelf = "".join(f'<div class="item{" on" if v else ""}"><img src="{CDN+img}" alt=""><div class="b"><div class="t">{p}</div>'
                    f'<div class="v"><b>{v}%</b><span>{"pos. " + pos if v else "not mentioned"}</span></div><div class="meter"><span style="width:{v*10}%"></span></div></div></div>'
                    for p, img, v, pos, price in MINE)
    kp = "".join(f'<div class="k"><div class="l">{l}</div><div class="v">{v}</div></div>' for l, v, s in KPI)
    leg = "".join(f'<span><i style="background:{c}"></i>{s[0]}</span>' for c, s in zip(colors, SERIES))
    body = f"""<div class="app"><aside><span class="lg">{LOGO}</span>{icons}<div class="sp"></div><a title="Support">{ic('help',20)}</a><a title="Settings">{ic('cog',20)}</a></aside>
<main><div class="hd"><div class="av">CS</div><div><h1>Clubhouse Skin</h1><small>Catalog overview · updated 8 Oct, 2:53 PM ET</small></div>
<div class="r"><span class="sel">{ic('cal',14)}Last 30 days{ic('down',14)}</span><span class="sel">Daily{ic('down',14)}</span><span class="sel">All engines{ic('down',14)}</span><button class="btn">{ic('play',14)}Run scan</button></div></div>
<div class="tabs"><a class="on">Overview</a><a>Answers</a><a>Mentions &amp; Citations</a></div>
<h2>Your catalog in AI answers <small>Visibility per product · last 30 days</small></h2><div class="shelf">{shelf}</div>
<div class="row">{kp}</div>
<div class="two"><section class="card"><h2>Visibility over time <small>Daily</small></h2>{chart(700, 250, colors, "#ecebe8", "#8b8f96")}<div class="legend">{leg}</div></section>
<section class="card"><h2>Product rankings <small>1,297 mentions</small></h2><table><tr><th></th><th>Product</th><th class="num">Mentioned in</th><th class="num">Pos.</th></tr>{rank_rows("own", "#0b1b35", "")}</table></section></div>
<p class="note">Design variation D · figures from Clubhouse Skin, last 30 days; trend lines illustrative.</p></main></div>"""
    return page("D Catalog shelf", "Hanken Grotesk", css, body)


# ---------------------------------------------------------------- E. Graphite
def build_e():
    css = """
:root{--bg:#0e1116;--panel:#151a21;--line:#252c36;--ink:#e8ecf2;--mute:#8b95a5;--own:#5b9bff}
body{background:var(--bg);color:var(--ink)}
.app{display:grid;grid-template-columns:228px 1fr;min-height:100vh}
aside{border-right:1px solid var(--line);padding:18px 12px;display:flex;flex-direction:column;gap:2px}
.brand{display:flex;gap:10px;align-items:center;font-weight:700;letter-spacing:.1em;font-size:13px;padding:0 8px 20px}
.store{display:flex;gap:10px;align-items:center;padding:9px;border:1px solid var(--line);border-radius:10px;margin-bottom:16px}.store small{display:block;color:var(--mute);font-size:11.5px}.store b{font-size:13px}
.av{width:28px;height:28px;border-radius:7px;background:#223047;color:#cfe0ff;display:grid;place-items:center;font-size:11px;font-weight:700}
.nav{display:flex;gap:10px;align-items:center;padding:8px 10px;border-radius:7px;font-size:13.5px;color:#aeb7c5}.nav.on{background:#1c232d;color:#fff}.nav .ct{margin-left:auto;font-size:11px;background:#223a63;color:#bcd4ff;border-radius:99px;padding:1px 7px}
.sp{flex:1}
main{padding:22px 30px 44px}
.hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}h1{font-size:20px;font-weight:600;letter-spacing:-.01em}
.status{font-size:12.5px;color:var(--mute);display:flex;gap:8px;align-items:center;margin-top:3px}.dot{width:7px;height:7px;border-radius:50%;background:#3ccf8e;box-shadow:0 0 0 3px rgba(60,207,142,.15)}
.btn{display:inline-flex;gap:8px;align-items:center;background:#e8ecf2;color:#0e1116;border:0;border-radius:8px;padding:9px 14px;font-size:13px;font-weight:600}
.tools{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);margin-bottom:18px}
.tabs{display:flex;gap:22px}.tabs a{padding:10px 0;font-size:13.5px;color:var(--mute);border-bottom:2px solid transparent;margin-bottom:-1px}.tabs a.on{color:#fff;border-color:var(--own)}
.sel{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--line);border-radius:7px;padding:6px 10px;font-size:12.5px;color:#c4ccd8;margin-left:6px;background:var(--panel)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}
.k{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}.k .l{font-size:12px;color:var(--mute)}.k .v{font-size:26px;font-weight:600;letter-spacing:-.02em;margin:6px 0 2px}.k .s{font-size:11.5px;color:var(--mute)}
.grid{display:grid;grid-template-columns:1.4fr 1fr;gap:12px;margin-bottom:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.ph{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}.ph h2{font-size:13.5px;font-weight:600}.ph small{font-size:12px;color:var(--mute)}
.legend{display:flex;gap:14px;font-size:12px;color:var(--mute);margin-top:6px}.legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;font-size:11.5px;color:var(--mute);font-weight:500;padding:0 6px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 6px;border-bottom:1px solid #1d232c}tr:last-child td{border:0}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th.num{text-align:right}
.n{color:var(--mute);width:20px}.pn{font-weight:500;max-width:230px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pb{font-size:11.5px;color:var(--mute)}
.bar{display:inline-block;width:56px;height:5px;background:#222a35;border-radius:3px;margin-right:8px;vertical-align:middle;overflow:hidden}.bar span{display:block;height:100%}
tr.own td{background:rgba(91,155,255,.08)}tr.own .pn{color:#9cc2ff}
.prod{display:flex;gap:11px;align-items:center;font-weight:500}.prod img{border-radius:7px;object-fit:cover}
.pill{font-size:11px;padding:3px 8px;border-radius:6px;background:#1f2630;color:#9aa4b3}.pill.ok{background:rgba(60,207,142,.12);color:#5fe0a6}
::selection{background:#2b4e86}
"""
    colors = ["#5b9bff", "#e8ecf2", "#3ccf8e", "#6b7585"]
    nav = "".join(f'<a class="nav{" on" if i == 0 else ""}">{ic(n)}{t}{f"<span class=ct>{c}</span>" if c else ""}</a>' for i, (n, t, c) in enumerate(NAV))
    kp = "".join(f'<div class="k"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for l, v, s in KPI)
    leg = "".join(f'<span><i style="background:{c}"></i>{s[0]}</span>' for c, s in zip(colors, SERIES))
    body = f"""<div class="app"><aside><div class="brand">{LOGO}PRODUKTO</div>
<div class="store"><div class="av">CS</div><div><b>Clubhouse Skin</b><small>clubhouseskin.com</small></div></div>
{nav}<div class="sp"></div><a class="nav">{ic('help')}Support</a><a class="nav">{ic('cog')}Settings</a></aside>
<main><div class="hd"><div><h1>Catalog overview</h1><div class="status"><span class="dot"></span>Updated 8 Oct, 2:53 PM ET · next scan tomorrow</div></div><button class="btn">{ic('play',14)}Run catalog scan</button></div>
<div class="tools"><div class="tabs"><a class="on">Overview</a><a>Answers</a><a>Mentions &amp; Citations</a></div>
<div style="padding-bottom:8px"><span class="sel">{ic('cal',14)}Last 30 days{ic('down',14)}</span><span class="sel">Daily{ic('down',14)}</span><span class="sel">All engines{ic('down',14)}</span></div></div>
<div class="kpis">{kp}</div>
<div class="grid"><section class="panel"><div class="ph"><h2>Visibility over time</h2><small>Daily · 17 scans</small></div>{chart(660, 250, colors, "#232a34", "#6f7a8a", area="rgba(91,155,255,.10)")}<div class="legend">{leg}</div></section>
<section class="panel"><div class="ph"><h2>Product rankings</h2><small>1,297 mentions</small></div><table><tr><th></th><th>Product</th><th class="num">Mentioned in</th><th class="num">Pos.</th></tr>{rank_rows("own", "#6b7585", "")}</table></section></div>
<section class="panel"><div class="ph"><h2>Your products</h2><small>1 of 6 mentioned</small></div><table><tr><th>Product</th><th class="num">Visibility</th><th class="num">Position</th><th class="num">Mentioned price</th><th>Status</th></tr>{mine_rows()}</table></section>
<p class="note">Design variation E · figures from Clubhouse Skin, last 30 days; trend lines illustrative.</p></main></div>"""
    return page("E Graphite", "Onest", css, body)


INDEX = [
    ("a.html", "A · Clarity", "White, hairline borders, one navy accent. Stripe/Linear calm. KPI strip, chart beside rankings, your products below."),
    ("b.html", "B · Navy rail", "Logo-navy sidebar on a soft blue-grey ground. One big visibility number fused with the chart; white cards."),
    ("c.html", "C · Briefing", "No sidebar: top navigation. Opens on a plain-English sentence of what changed, then a wide chart with stats on the side."),
    ("d.html", "D · Catalog shelf", "Product photos lead: your six products as a shelf with visibility under each, slim icon rail."),
    ("e.html", "E · Graphite", "Dark analyst mode. Same structure as A, built for long sessions and demos on a big screen."),
]


def build_index():
    cards = "".join(f'<a class="c" href="{f}"><iframe src="{f}" loading="lazy" tabindex="-1" title="{t}"></iframe><div class="t"><b>{t}</b><p>{d}</p></div></a>' for f, t, d in INDEX)
    css = """body{background:#f3f4f6;color:#0b1b35;padding:40px}h1{font-size:24px;letter-spacing:-.02em}.lead{color:#5d6878;margin:6px 0 28px;font-size:14px}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:24px}.c{background:#fff;border:1px solid #e3e6eb;border-radius:14px;overflow:hidden;transition:box-shadow .2s}
.c:hover{box-shadow:0 8px 28px rgba(11,27,53,.12)}.c iframe{width:1440px;height:960px;border:0;transform:scale(.3);transform-origin:0 0;pointer-events:none;margin-bottom:-672px;margin-right:-1008px}
.c{display:block}.c>div:first-child{}.t{padding:14px 18px;border-top:1px solid #e3e6eb}.t b{font-size:15px}.t p{font-size:13px;color:#5d6878;margin-top:4px;line-height:1.45}"""
    body = f'<h1>Produkto · five directions for the logged-in app</h1><p class="lead">Catalog overview for Clubhouse Skin. Click a card to open it full size, then pick one.</p><div class="g">{cards}</div>'
    return page("Directions", "Geist", css, body)


if __name__ == "__main__":
    for name, fn in [("a", build_a), ("b", build_b), ("c", build_c), ("d", build_d), ("e", build_e)]:
        (OUT / f"{name}.html").write_text(fn())
    (OUT / "index.html").write_text(build_index())
    print("wrote", sorted(p.name for p in OUT.glob("*.html")))
