"""Find founder names on each brand's own site (free: plain page fetches, no API).

Usage: python3 find_founders.py <store_dir>
Reads <store_dir>/apollo-domains.txt, opens the homepage plus common About pages,
and looks for sentences like "founded by Jane Smith" / "Jane Smith, Founder".
Writes <store_dir>/founders-from-site.csv with the evidence sentence on every row,
so each name can be checked by eye. A name is a lead, not a fact.
"""
import csv, html, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
PATHS = ["", "/pages/about", "/pages/about-us", "/pages/our-story", "/pages/story", "/pages/meet-the-founder"]
NAME = r"([A-Z][a-z]+(?:[- ][A-Z][a-z']+){1,2})"
ROLE = r"(?:co-?founders?|founders?|owners?|ceo|roasters? and owner|head roaster and founder)"
PATTERNS = [
    re.compile(rf"(?:founded|started|created|established) (?:in \d{{4}} )?by {NAME}(?: and {NAME})?"),
    re.compile(rf"{NAME},? (?:our |the )?(?i:{ROLE})"),
    re.compile(rf"(?i:{ROLE})[,:]? {NAME}"),
    re.compile(rf"(?:I'm|I am|Hi,? I'm|Hey,? I'm) {NAME}"),
]
STOP = {"Meet The Owner", "Meet The Founder", "Owner Wild", "Sip The", "Our Story", "About Us", "Coffee Company", "Tea Company", "Shop Now", "Read More", "Learn More",
        "Free Shipping", "Our Coffee", "Our Founder", "The Founder", "Meet The"}


def text_of(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12) as r:
            raw = r.read(400_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))


def find(domain):
    for p in PATHS:
        t = text_of(f"https://{domain}{p}")
        for pat in PATTERNS:
            for m in pat.finditer(t):
                names = [n for n in m.groups() if n and n not in STOP and not any(w in n.split() for w in ("Coffee", "Tea", "Roast", "Roasting", "Company", "Co", "Meet", "The", "Our", "Sip", "Explore", "Join", "Shop", "Us", "About"))]
                if names:
                    s = max(0, m.start() - 80)
                    return {"domain": domain, "founder": " & ".join(names), "page": f"https://{domain}{p}",
                            "evidence": t[s:m.end() + 80].strip()}
    return {"domain": domain, "founder": "", "page": "", "evidence": ""}


def main():
    d = sys.argv[1]
    domains = [l.strip() for l in open(f"{d}/apollo-domains.txt") if l.strip()]
    with ThreadPoolExecutor(24) as ex:
        rows = list(ex.map(find, domains))
    with open(f"{d}/founders-from-site.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["domain", "founder", "page", "evidence"])
        w.writeheader()
        w.writerows(rows)
    print(f"{sum(1 for r in rows if r['founder'])} of {len(rows)} brands: founder name found on site")


if __name__ == "__main__":
    main()
