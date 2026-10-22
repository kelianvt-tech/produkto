"""Check that the prices quoted in the tools comparison are still on each vendor's page.

    python3 check_prices.py

For each tool, fetches its pricing page and looks for every price the article
quotes. A missing price means the page changed (or now loads prices with
JavaScript): open the page, check by hand, then update
../guides-src/best-ai-visibility-tools-for-ecommerce.html and rebuild.
Free: plain HTTP, no Apify or Firecrawl.
"""
import re, subprocess, sys

UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36"
# tool: (url, prices the article quotes)
TOOLS = {
    "Otterly.AI": ("https://otterly.ai/pricing", ["29", "189", "489"]),
    "Scrunch": ("https://scrunch.com/pricing", ["250"]),
    "Semrush": ("https://www.semrush.com/kb/1493-ai-toolkit", ["99", "60"]),
    "Ahrefs Brand Radar": ("https://ahrefs.com/brand-radar", ["199", "50", "699"]),
    "Glara": ("https://glara.ai/pricing", ["120", "345"]),
    "Sixthshop": ("https://www.sixthshop.com/pricing", ["29", "59", "99"]),
    "Peec AI": ("https://peec.ai/pricing", ["95", "245", "495"]),
    "Promptwatch": ("https://www.promptwatch.com/pricing", ["95", "245", "579"]),
    "Profound": ("https://www.tryprofound.com/pricing", []),      # trial + custom only
    "AndromedAI": ("https://www.andromed.ai/", []),                # no public pricing
}


# Prices these pages only draw with JavaScript: plain HTTP can't see them.
MANUAL = {"Peec AI"}


def fetch(url):
    out = subprocess.run(["curl", "-sL", "-m", "30", "-f", "-A", UA, url], capture_output=True)
    if out.returncode:
        raise RuntimeError("curl exit %d" % out.returncode)
    return out.stdout.decode("utf-8", "ignore")


def main():
    problems = 0
    for tool, (url, prices) in TOOLS.items():
        if tool in MANUAL:
            print("MANUAL %-20s prices load with JavaScript; open %s and compare with $%s"
                  % (tool, url, ", $".join(prices)))
            continue
        try:
            page = fetch(url)
        except Exception as e:
            print("CHECK  %-20s could not load (%s)" % (tool, e))
            problems += 1
            continue
        flat = re.sub(r"[\s\\]+", " ", page)
        missing = [p for p in prices if not re.search(r'[$€]\s*(?:<[^>]*>\s*)*%s\b|"price":\s*"%s(?:\.0+)?"' % (p, p), flat)]
        if missing:
            problems += 1
            print("CHECK  %-20s price(s) not found: %s  %s" % (tool, ", ".join("$" + m for m in missing), url))
        else:
            print("ok     %-20s" % tool)
    print("\n%d tool(s) to check by hand." % problems if problems else "\nAll quoted prices still found.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
