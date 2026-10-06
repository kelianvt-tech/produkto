#!/usr/bin/env python3
"""
Turn the lead CSV into ready-to-paste messages, split into daily batches.

    python3 prospecting/drafts.py prospecting/enriched-2026-08-05.csv \
        --university "Universitat Pompeu Fabra" --per-day 15

Writes prospecting/drafts-<date>.md -- one block per lead, grouped by day,
with the email and the Instagram DM side by side. You copy, paste, send.

It does NOT send anything. Sending by hand is the point: it keeps you under
spam thresholds, keeps Instagram from restricting the account, and keeps each
message actually personal.

Column names are matched loosely, so it works with brands.csv or the enriched
output. Missing pieces are flagged rather than papered over.
"""

import argparse
import csv
import datetime as dt
import re
import sys

# Loose header matching -- CSVs drift.
ALIASES = {
    "brand":     ("brand", "company", "name"),
    "founder":   ("founder", "guest", "contact", "first_name"),
    "email":     ("email", "emails_published", "email_guesses", "contact_email"),
    "instagram": ("instagram", "ig", "instagram_handle"),
    # Deliberately narrow. A revenue figure or a category is NOT a personal
    # detail -- "the part about $2m stuck with me" reads as fake specificity,
    # which is worse than leaving the slot blank for you to fill by hand.
    "hook":      ("hook", "hook_detail", "detail", "what they said",
                  "hook / what they said"),
    "domain":    ("domain", "website", "store_url", "url"),
    "episode":   ("episode_url", "episode", "podcast_url"),
}


def pick(row, key):
    lowered = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    for alias in ALIASES[key]:
        val = lowered.get(alias)
        if val:
            return val
    return ""


def first_name(full):
    full = re.sub(r"\s+", " ", full).strip()
    return full.split(" ")[0] if full else ""


def build(row, university, city):
    brand = pick(row, "brand")
    founder = pick(row, "founder")
    fn = first_name(founder) or "there"
    hook = pick(row, "hook")
    email = pick(row, "email").split(";")[0].strip()
    ig = pick(row, "instagram").lstrip("@")

    gaps = []
    if not founder:
        gaps.append("no founder name")
    if not hook:
        gaps.append("NO PERSONAL DETAIL - listen to the episode first")
    if not email and not ig:
        gaps.append("no way to reach them")

    if hook:
        h = hook.rstrip(".")
        h = h[0].lower() + h[1:]          # lowercase the first letter only, so VC stays VC
        hook_line = f"The part about {h} was what stuck with me."
    else:
        hook_line = "{{ ← WRITE ONE REAL LINE FROM THE EPISODE HERE }}"

    subject = "Student research - your Shopify podcast episode"

    body = f"""Hi {fn},

My name's Kelian, I'm a student at {university} in {city}.

I just finished your episode on the Shopify podcast. {hook_line}

I'm doing research on how e-commerce founders are thinking about AI search - whether buyers asking ChatGPT for products is actually showing up for you yet, or whether it's still mostly noise. I'd rather ask people running real stores than read another article about it.

Would you have 20 minutes for a short interview? Happy to work around your schedule.

Thanks either way,
Kelian"""

    dm = f"""Hi {fn} - my name's Kelian, I'm a student at {university} in {city}.

Just finished your episode on the Shopify podcast. {hook_line}

I'm doing research on how e-commerce founders are thinking about AI search - whether people asking ChatGPT for products is showing up for you yet, or whether it's still hype. Would you be up for a short interview? 20 minutes, just questions."""

    return dict(brand=brand, founder=founder, email=email, instagram=ig,
                domain=pick(row, "domain"), episode=pick(row, "episode"),
                subject=subject, body=body, dm=dm, gaps=gaps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--university", required=True)
    ap.add_argument("--city", default="Barcelona")
    ap.add_argument("--per-day", type=int, default=15,
                    help="Keep at or below 20 for email, 15 for Instagram.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("No rows found.")

    drafts = [build(r, args.university, args.city) for r in rows]
    drafts = [d for d in drafts if d["brand"]]

    # Reachable and personalised first; blockers last.
    drafts.sort(key=lambda d: (len(d["gaps"]), d["brand"].lower()))

    stamp = dt.date.today().isoformat()
    out = args.out or f"prospecting/drafts-{stamp}.md"
    ready = [d for d in drafts if not d["gaps"]]

    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Outreach drafts - {stamp}\n\n")
        f.write(f"{len(drafts)} leads · {len(ready)} ready to send as-is · "
                f"{len(drafts)-len(ready)} need something filled in first.\n\n")
        f.write(f"**{args.per_day} a day.** Send by hand, one at a time. Do not paste "
                "these into a sequencer - the whole point is that they aren't a campaign.\n\n")
        f.write("Before each send: skim the episode and make sure the personal line is "
                "true. That line is the only reason this works.\n\n---\n\n")

        for i, d in enumerate(drafts):
            day = i // args.per_day + 1
            if i % args.per_day == 0:
                f.write(f"\n\n# ── DAY {day} ──\n\n")

            f.write(f"## {i+1}. {d['brand']}")
            if d["founder"]:
                f.write(f" — {d['founder']}")
            f.write("\n\n")

            if d["gaps"]:
                f.write(f"> ⚠️ {' · '.join(d['gaps'])}\n\n")

            bits = []
            if d["email"]:
                bits.append(f"**Email:** {d['email']}")
            if d["instagram"]:
                bits.append(f"**IG:** [@{d['instagram']}](https://instagram.com/{d['instagram']})")
            if d["domain"]:
                bits.append(f"[site]({d['domain']})")
            if d["episode"]:
                bits.append(f"[episode]({d['episode']})")
            if bits:
                f.write(" · ".join(bits) + "\n\n")

            f.write(f"**Subject:** {d['subject']}\n\n")
            f.write("```\n" + d["body"] + "\n```\n\n")
            f.write("**Instagram DM:**\n\n")
            f.write("```\n" + d["dm"] + "\n```\n\n---\n\n")

    print(f"Wrote {out}")
    print(f"{len(ready)} ready · {len(drafts)-len(ready)} need attention")
    print(f"{-(-len(drafts)//args.per_day)} days at {args.per_day}/day")


if __name__ == "__main__":
    main()
