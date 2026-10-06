#!/usr/bin/env python3
"""
The 30-second triage, automated.

Runs the checks from context/ICP.md against a list of candidate domains and
tells you which ones are worth auditing. Hard filters only -- it sorts the
queue, it does not reject anyone except on the three real exclusions.

    python3 prospecting/triage.py prospecting/candidates.txt

Writes prospecting/triage-<date>.md and prints a summary.

Standard library only, same as the audit tool. Be polite: default 1s between
requests, and it reads robots.txt before touching anything else.
"""

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; catalog-triage/1.0; +research)"
TIMEOUT = 20

# Hard floor from ICP.md. Below this they don't have the problem.
SKU_FLOOR = 150

# Hard exclusion. They'll be sold Yotpo Discover as an upsell.
YOTPO_MARKERS = ("yotpo.com", "staticw2.yotpo", "yotpo-widget", "yotpoRefreshWidgets")

# Signals worth noting but never disqualifying.
REVIEW_APPS = {
    "judge.me": "Judge.me",
    "loox.io": "Loox",
    "stamped.io": "Stamped",
    "okendo": "Okendo",
    "reviews.io": "Reviews.io",
}

AI_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ClaudeBot", "PerplexityBot", "Google-Extended")


def get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="replace"), dict(r.headers)


def try_get(url):
    try:
        return get(url)
    except urllib.error.HTTPError as e:
        return e.code, "", {}
    except Exception:
        return None, "", {}


def normalise(domain):
    d = domain.strip()
    if not d:
        return None
    if not d.startswith("http"):
        d = "https://" + d
    p = urllib.parse.urlparse(d)
    return f"{p.scheme}://{p.netloc}"


def count_products(base, delay):
    """Page through /products.json. Returns (count, sample_titles, available)."""
    total, titles, page = 0, [], 1
    while page <= 40:  # 10k products is plenty
        status, body, _ = try_get(f"{base}/products.json?limit=250&page={page}")
        if status != 200 or not body:
            return (None, [], False) if page == 1 else (total, titles, True)
        try:
            items = json.loads(body).get("products", [])
        except json.JSONDecodeError:
            return (None, [], False) if page == 1 else (total, titles, True)
        if not items:
            break
        total += len(items)
        if len(titles) < 5:
            titles.extend(p.get("title", "") for p in items[:5])
        if len(items) < 250:
            break
        page += 1
        time.sleep(delay)
    return total, titles[:5], True


def check_home(base):
    """Platform, review app, Yotpo. Returns dict."""
    status, body, headers = try_get(base)
    out = {"reachable": status == 200, "shopify": False, "yotpo": False, "review_app": None}
    if status != 200:
        return out
    blob = (body + " " + " ".join(f"{k}:{v}" for k, v in headers.items())).lower()
    out["shopify"] = ("cdn.shopify.com" in blob or "shopify" in blob
                      or "x-shopid" in {k.lower() for k in headers})
    out["yotpo"] = any(m.lower() in blob for m in YOTPO_MARKERS)
    for marker, name in REVIEW_APPS.items():
        if marker in blob:
            out["review_app"] = name
            break
    return out


def check_robots(base):
    """Does the site block AI crawlers? Not a filter -- a talking point."""
    status, body, _ = try_get(f"{base}/robots.txt")
    if status != 200:
        return None
    blocked = []
    for block in re.split(r"\n\s*\n", body):
        agents = re.findall(r"(?i)^user-agent:\s*(.+)$", block, re.M)
        disallows = re.findall(r"(?i)^disallow:\s*(.*)$", block, re.M)
        if any(d.strip() == "/" for d in disallows):
            for a in agents:
                a = a.strip()
                if any(c.lower() == a.lower() for c in AI_CRAWLERS):
                    blocked.append(a)
    return blocked


def triage(domain, delay):
    base = normalise(domain)
    if not base:
        return None
    row = {"domain": base.replace("https://", ""), "base": base}

    home = check_home(base)
    row.update(home)
    if not home["reachable"]:
        row["verdict"] = "UNREACHABLE"
        row["why"] = "site did not respond"
        return row

    time.sleep(delay)
    count, titles, feed_ok = count_products(base, delay)
    row["products"] = count
    row["sample"] = titles
    row["feed_open"] = feed_ok

    time.sleep(delay)
    row["ai_blocked"] = check_robots(base)

    # The three hard exclusions from ICP.md, plus the SKU floor.
    if home["yotpo"]:
        row["verdict"] = "EXCLUDE"
        row["why"] = "Yotpo present -- will be upsold Discover on incumbency"
    elif count is None:
        row["verdict"] = "MANUAL"
        row["why"] = "products.json closed; count SKUs by hand or skip"
    elif count < SKU_FLOOR:
        row["verdict"] = "EXCLUDE"
        row["why"] = f"{count} products -- below the {SKU_FLOOR} floor, they have an afternoon of work"
    elif not home["shopify"]:
        row["verdict"] = "MANUAL"
        row["why"] = "not obviously Shopify; audit tool may not parse the feed"
    else:
        row["verdict"] = "AUDIT"
        band = "500-5000 preferred" if 500 <= count <= 5000 else "outside preferred band"
        row["why"] = f"{count} products ({band})"
    return row


def to_markdown(rows):
    today = dt.date.today().isoformat()
    order = {"AUDIT": 0, "MANUAL": 1, "EXCLUDE": 2, "UNREACHABLE": 3}
    rows = sorted(rows, key=lambda r: (order.get(r.get("verdict"), 9), -(r.get("products") or 0)))

    out = [f"# Triage run -- {today}", ""]
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    out.append("  ".join(f"**{k}**: {v}" for k, v in counts.items()))
    out.append("")
    out.append("| Domain | Verdict | Products | Shopify | Yotpo | Reviews | Blocks AI | Note |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        blocked = r.get("ai_blocked")
        blocked_s = ", ".join(blocked) if blocked else ("--" if blocked == [] else "?")
        out.append(
            f"| {r['domain']} | **{r['verdict']}** | {r.get('products') or '?'} | "
            f"{'yes' if r.get('shopify') else 'no'} | {'YES' if r.get('yotpo') else '--'} | "
            f"{r.get('review_app') or '--'} | {blocked_s} | {r.get('why','')} |"
        )
    out.append("")
    out.append("## Next")
    out.append("")
    out.append("Run the audit on everything marked AUDIT:")
    out.append("")
    out.append("```bash")
    for r in rows:
        if r["verdict"] == "AUDIT":
            out.append(f"python3 build/audit.py {r['base']} --category furniture --delay 0.35")
    out.append("```")
    out.append("")
    out.append("`Blocks AI` lists crawlers disallowed in robots.txt. Not a filter -- but if a "
               "brand blocks GPTBot they have decided this channel doesn't matter, which is "
               "worth knowing before you write to them, and is itself a finding.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="text file, one domain per line, # for comments")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.file) as f:
        domains = [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()]

    rows = []
    for i, d in enumerate(domains, 1):
        print(f"[{i}/{len(domains)}] {d} ... ", end="", flush=True)
        try:
            row = triage(d, args.delay)
        except Exception as e:
            print(f"error: {e}")
            continue
        if row:
            rows.append(row)
            print(f"{row['verdict']} ({row.get('products') or '?'} products)")
        time.sleep(args.delay)

    out_path = args.out or f"prospecting/triage-{dt.date.today().isoformat()}.md"
    with open(out_path, "w") as f:
        f.write(to_markdown(rows))
    print(f"\nWrote {out_path}")
    print(f"AUDIT: {sum(1 for r in rows if r['verdict']=='AUDIT')} of {len(rows)}")


if __name__ == "__main__":
    main()
