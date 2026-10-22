"""Build the roundup outreach list from the pages AI cited in our visibility readings.

    python3 build_list.py

Reads every produkto-site/aeo-case-study/results/*.json, keeps "best tools",
"alternatives" and comparison articles, fetches each page (free, plain HTTP)
and writes roundups.csv: url, site, who owns it, author, date, how often AI
cited it, which assistants, whether Produkto is already listed, a contact
lead (mailto or contact page).
"""
import collections, concurrent.futures as cf, csv, glob, html, json, os, re, subprocess
from urllib.parse import urljoin, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "..", "produkto-site", "aeo-case-study", "results")
UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36"
LISTICLE = re.compile(r"best|top-|alternatives|tools|platforms|trackers|-vs-|compare|reviewed|ranked", re.I)
SKIP_HOSTS = ("apps.shopify.com", "help.shopify.com", "community.shopify.com", "reddit.com", "youtube.com",
              "instagram.com", "openai.com", "google.com", "chatgpt.com", "trustradius.com")
# What each site is, read from its own homepage title and description (checked 2026-10-20).
# Not guessed from the name: re-check new hosts the same way before adding them.
KIND = {
    # sells its own AI-visibility / GEO tool: ranks itself first, low odds of adding us
    **dict.fromkeys(["airops.com", "alhena.ai", "citadex.io", "cognizo.ai", "deepsmith.ai", "ecommerceinsights.ai",
                     "geoly.ai", "glara.ai", "ismybrandinai.com", "listablelabs.com", "mention.network", "nudgenow.com",
                     "ranketta.com", "rankspot.ai", "searcheye.io", "searchmention.com", "strideftw.com",
                     "thewhitebox.io", "vizby.ai", "workduo.ai", "yotpo.com", "frizerly.com", "blog.frizerly.com",
                     "amplitude.com",
                     # NoGood runs Goodie, an AI-visibility tool (Mostafa ElBermawy's LinkedIn, 2026-10-20)
                     "nogood.io", "bermawy.com"], "Competing tool"),
    # independent: publishers, directories, agencies, freelancers, adjacent software
    **dict.fromkeys(["agentvisibilitytools.com", "ecommerceguide.com", "business.com", "nerdbot.com", "sitepoint.com",
                     "fritz.ai", "superframeworks.com", "marketingforllms.com"], "Publisher / directory"),
    **dict.fromkeys(["wrkngdigital.com", "shopos.ai", "width.ai", "gtm8020.com", "marketerhire.com"],
                    "Agency / consultancy"),
    **dict.fromkeys(["nathanojaokomo.com"], "Individual expert / writer"),
    **dict.fromkeys(["debutify.com", "elementor.com", "triplewhale.com", "trustmary.com", "allintitle.co",
                     "answersocrates.com", "flint.com", "genixly.io", "thesocialcat.com"], "Adjacent software (not a competitor)"),
    **dict.fromkeys(["shopify.com", "blog.hubspot.com", "hubspot.com"], "Platform blog"),
}
PRIORITY = {"Publisher / directory": 1, "Individual expert / writer": 1, "Agency / consultancy": 1,
            "Adjacent software (not a competitor)": 2, "Platform blog": 2, "Competing tool": 3}


def host(u):
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def cited():
    seen = collections.defaultdict(lambda: dict(n=0, engines=set(), questions=set(), weeks=set()))
    for f in sorted(glob.glob(os.path.join(RESULTS, "*.json"))):
        d = json.load(open(f))
        for eng, answers in d["answers"].items():
            for q, a in answers.items():
                for c in a["citations"]:
                    u = c["url"].split("?")[0].split("#")[0]
                    if any(s in host(u) for s in SKIP_HOSTS) or not LISTICLE.search(urlparse(u).path):
                        continue
                    s = seen[u]
                    s["n"] += 1; s["engines"].add(eng); s["questions"].add(q); s["weeks"].add(d["date"])
    return seen


def fetch(u):
    r = subprocess.run(["curl", "-sL", "-m", "25", "-A", UA, u], capture_output=True)
    return r.stdout.decode("utf-8", "ignore")


def inspect(u):
    t = fetch(u)
    info = dict(title="", author="", date="", produkto="", contact="", status="ok" if t else "no response")
    if not t:
        return info
    m = re.search(r"<title[^>]*>(.*?)</title>", t, re.S)
    info["title"] = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:120] if m else ""
    for pat in (r'"author"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"', r'"author"\s*:\s*\[\s*\{[^}]*?"name"\s*:\s*"([^"]+)"',
                r'<meta[^>]+name="author"[^>]+content="([^"]+)"', r'rel="author"[^>]*>([^<]+)<'):
        m = re.search(pat, t)
        if m:
            info["author"] = html.unescape(m.group(1)).strip()[:80]
            break
    m = re.search(r'"dateModified"\s*:\s*"([0-9-]{10})|"datePublished"\s*:\s*"([0-9-]{10})|article:modified_time"\s+content="([0-9-]{10})', t)
    info["date"] = next((g for g in m.groups() if g), "") if m else ""
    info["produkto"] = "yes" if re.search(r"produkto", t, re.I) else ""
    mails = sorted({e for e in re.findall(r"mailto:([\w.+-]+@[\w-]+\.[\w.-]+)", t)
                    if not re.search(r"example|sentry|your@|name@|wixpress", e)})
    if mails:
        info["contact"] = mails[0]
    else:
        m = re.search(r'href="([^"]*(?:/contact|/about)[^"]*)"', t, re.I)
        info["contact"] = urljoin(u, m.group(1)) if m else ""
    return info


def main():
    seen = cited()
    with cf.ThreadPoolExecutor(8) as ex:
        infos = dict(zip(seen, ex.map(inspect, seen)))
    rows = []
    for u, s in seen.items():
        h = host(u); i = infos[u]
        owner = KIND.get(h, "UNCHECKED: read the homepage")
        priority = PRIORITY.get(owner, 2)
        rows.append(dict(priority=priority, owner=owner, site=h, title=i["title"], url=u, author=i["author"],
                         updated=i["date"], times_cited=s["n"], assistants=" ".join(sorted(s["engines"])),
                         lists_produkto=i["produkto"], contact=i["contact"], fetch=i["status"], status="", notes=""))
    rows.sort(key=lambda r: (r["priority"], -r["times_cited"], r["site"]))
    out = os.path.join(HERE, "roundups.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    c = collections.Counter(r["owner"] for r in rows)
    print(len(rows), "roundups ->", out, dict(c))


if __name__ == "__main__":
    main()
