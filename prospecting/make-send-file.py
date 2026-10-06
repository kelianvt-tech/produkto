#!/usr/bin/env python3
"""
Turn an enriched CSV into the send-ready markdown file.

    python3 prospecting/make-send-file.py prospecting/enriched-2026-08-07.csv

Writes prospecting/send-today-<date>.md: one block per brand with the email
address, Instagram handle, site, source article, subject line and a finished
email body. Copy, paste, send.

This is the last step of the pipeline:
    1. build a brands-batchN.csv (brand, founder, slug_guess, category,
       size_signal, episode_url)
    2. python3 prospecting/enrich.py prospecting/brands-batchN.csv
    3. this script

The email template below is LOCKED. It has been edited several times by hand
and every clause is deliberate. Read the notes before changing anything.
"""

import argparse
import csv
import difflib
import datetime as dt
import re
import sys

# ─────────────────────────────────────────────────────────────────────────────
# THE TEMPLATE. Change with care.
#
#  - "IE University in Madrid" is true. The student framing is the whole reason
#    this reads as low stakes, and it only works because it is not a lie.
#  - NO em dashes or en dashes anywhere. They read as AI generated.
#  - "report", never "research". Kelian's wording.
#  - "came across your story on the Shopify blog" is deliberately format neutral.
#    The Shopify blog's Podcasts tag also contains written articles, so claiming
#    "your episode" was wrong for a chunk of the list and got caught mid send.
#  - The sign off compliments what they built, not the format of their feature,
#    for the same reason.
#  - No free audit, no link, no attachment. The only ask is 20 minutes.
# ─────────────────────────────────────────────────────────────────────────────

UNIVERSITY = "IE University"
CITY = "Madrid"
SUBJECT = "Student report on AI search"

OPENER = "I came across your story on the Shopify blog about {phrase}."

# Fallback when the article slug yields no usable phrase. Still true (he did come
# across it) and claims no specific detail he hasn't verified, so it stays inside
# the honesty rules while needing no manual work.
OPENER_BLANK = "I came across your story on the Shopify blog and found it really inspiring."


def body(first_name, opener):
    return f"""Hi {first_name},

My name's Kelian, I'm a student at {UNIVERSITY} in {CITY}.

{opener} I'm putting together a report on how e-commerce founders are thinking about AI search, whether buyers asking ChatGPT for products is actually showing up for you yet, or whether it's still mostly noise. I'd rather just ask the actual people running real stores than read another article about it.

Would you have 20 minutes for a short interview? Happy to work around your schedule.

By the way, I really admire what you've built.

Thanks,
Kelian"""


DM = """Hi {first_name}, my name's Kelian, I'm a student at {uni} in {city}.

{opener} I'm putting together a report on how e-commerce founders are thinking about AI search, whether people asking ChatGPT for products is showing up for you yet or whether it's still hype.

Would you be up for a short interview? 20 minutes, just questions."""

# ─────────────────────────────────────────────────────────────────────────────

# Headings, product names and page furniture that the About page scraper
# mistakes for a person. Anything matching is treated as "no founder name".
JUNK_NAME = re.compile(
    r'(?i)^(our|let|meet|about|the|shop|team|figure|certified|bro|art|your|this|new|free|all)\b'
    r'|story|community|brand$|director|mask|collection$|studio$|policy|shipping|returns')

LEAD_STOP = {"how", "the", "a", "an", "to", "of", "and", "why", "what", "from", "for",
             "with", "into", "is", "are", "was", "in", "on", "at", "by", "this", "that",
             "its", "building", "inside"}


# Slugs spell brand names differently from the brand column: "Sugardoh" appears as
# "sugardough", "Eighth Generation" as "8th-generation". Without these the brand
# name leaks into the phrase and the sentence reads oddly.
NUMWORD = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six",
           "7": "seven", "8": "eight", "9": "nine", "10": "ten",
           "1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth",
           "5th": "fifth", "8th": "eighth"}


def _is_brand_token(word, brand_tokens):
    w = NUMWORD.get(word, word)
    for t in brand_tokens:
        t2 = NUMWORD.get(t, t)
        if w == t2:
            return True
        # catch sugardough vs sugardoh, larroude vs larroudé, etc.
        if len(w) > 4 and difflib.SequenceMatcher(None, w, t2).ratio() > 0.82:
            return True
    return False


def phrase_from(url, brand):
    """
    Derive a human phrase from the article slug, e.g.
    .../blog/sabai-design-sustainability -> "sustainability"
    Brand tokens are stripped only from the FRONT so nouns mid phrase survive
    ("celebrity backed brands that sell" keeps its noun).
    """
    if not url:
        return ""
    words = [w for w in url.rstrip('/').split('/')[-1].split('-') if w]
    bt = [t for t in re.split(r'[^a-z0-9]+', brand.lower()) if t]
    i = 0
    while i < len(words) and _is_brand_token(words[i], bt):
        i += 1
    words = words[i:]
    while words and words[0] in LEAD_STOP:
        words = words[1:]
    p = " ".join(words).strip()
    return p if len(p.split()) >= 3 else ""


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def prep(r):
    brand = (r.get('brand') or '').strip()
    f = (r.get('founder') or '').strip()
    name_ok = f and len(f.split()) >= 2 and not JUNK_NAME.search(f)
    # PUBLISHED ADDRESSES ONLY.
    # The email_guesses column (firstname@domain patterns) is deliberately
    # ignored. Those bounce, and a bounce costs more than the send is worth.
    # If a brand publishes no address, it goes out as an Instagram DM instead.
    # Do not reintroduce the guess fallback.
    pub = [e.strip() for e in (r.get('emails_published') or '').split(';')
           if '@' in e and '%' not in e and not e.strip().lower().startswith('the@')]
    gue = []
    # Where the name came from decides how much to trust it.
    #   "episode page"      -> the article named them, they are the interviewee. Trust.
    #   "guessed from site" -> regex found a capitalised word near founder/CEO on the
    #                          About page. About half are wrong: current CEOs rather
    #                          than founders, long dead historical founders (Belstaff's
    #                          Eli Belovitch, 1924), or page headings. Always flag.
    src = (r.get('founder_source') or '').lower()
    shaky = bool(f) and 'guess' in src

    return dict(
        brand=brand,
        founder=f if name_ok else '',
        shaky_name=shaky and name_ok,
        email=(pub[0] if pub else (gue[0] if gue else '')),
        kind=('published' if pub else ('guess' if gue else 'none')),
        ig=(r.get('instagram') or '').strip().lstrip('@'),
        domain=(r.get('domain') or '').strip(),
        episode=(r.get('episode_url') or '').strip(),
        phrase=phrase_from(r.get('episode_url', ''), brand),
        spec='spec' in (r.get('size_signal') or '').lower(),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="enriched CSV from enrich.py")
    ap.add_argument("--per-batch", type=int, default=25)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = [prep(r) for r in load(args.file)]
    rows = [r for r in rows if r['brand']]
    if not rows:
        sys.exit("No usable rows.")

    # Best first: real name + published address + a usable phrase.
    rows.sort(key=lambda r: (r['kind'] == 'none',
                             not (r['founder'] and r['kind'] == 'published' and r['phrase']),
                             r['kind'] == 'guess',
                             not r['founder'],
                             r['brand'].lower()))

    stamp = dt.date.today().isoformat()
    out = args.out or f"prospecting/send-today-{stamp}.md"
    reach = sum(1 for r in rows if r['email'])
    done = sum(1 for r in rows if r['founder'] and r['phrase'] and r['email'])

    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Send today, {stamp}\n\n")
        f.write(f"{len(rows)} brands. {reach} have an email address. {done} fully complete.\n\n")
        f.write(f"Batches of {args.per_batch}, about two hours apart. Send individually, never BCC.\n\n")
        f.write("Ignore any LOW SKU or Yotpo note from the enrichment run. Those filters are for "
                "the audit tool, not for interviews. A nine product brand is still a good "
                "conversation.\n\n")
        f.write("Anything flagged below needs ten seconds of attention before it goes.\n\n---\n")

        for i, r in enumerate(rows):
            if i % args.per_batch == 0:
                f.write(f"\n\n# BATCH {i // args.per_batch + 1}\n\n")
            first = r['founder'].split()[0] if r['founder'] else "{FIRST NAME}"
            opener = OPENER.format(phrase=r['phrase']) if r['phrase'] else OPENER_BLANK

            flags = []
            if r.get('shaky_name'):
                flags.append(f"NAME UNVERIFIED, \"{r['founder']}\" was scraped off their About "
                             "page and may be a current CEO, a historical founder or a heading. "
                             "Open the article and check before sending")
            if not r['founder']:
                flags.append("no founder name, check the article or open with Hi there")
            if not r['phrase']:
                flags.append("generic opener used, no phrase in the article slug. "
                             "Sendable as is, but a real detail lands better")
            if r['kind'] == 'guess':
                flags.append("guessed address, may bounce")
            if r['kind'] == 'none':
                flags.append("NO EMAIL, use Instagram")

            f.write(f"\n## {i+1}. {r['brand']}" + (" (spec heavy)" if r['spec'] else "") + "\n\n")
            if flags:
                f.write(f"> {' / '.join(flags)}\n\n")

            bits = [f"**To:** {r['email'] or '(none)'}"]
            if r['ig']:
                bits.append(f"IG @{r['ig']}")
            if r['domain']:
                bits.append(f"[site]({r['domain']})")
            if r['episode']:
                bits.append(f"[article]({r['episode']})")
            f.write(" / ".join(bits) + f"\n\n**Subject:** {SUBJECT}\n\n")
            f.write("```\n" + body(first, opener) + "\n```\n")
            if r['ig']:
                f.write("\n**Instagram DM:**\n\n```\n"
                        + DM.format(first_name=first, uni=UNIVERSITY, city=CITY, opener=opener)
                        + "\n```\n")

    text = open(out, encoding="utf-8").read()
    dashes = [c for c in ("—", "–") if c in text]
    print(f"Wrote {out}")
    print(f"{len(rows)} brands / {reach} with an email / {done} complete")
    print("Dash check:", "FAILED, found " + " ".join(dashes) if dashes else "clean")


if __name__ == "__main__":
    main()
