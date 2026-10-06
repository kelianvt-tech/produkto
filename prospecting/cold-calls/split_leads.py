"""Split a leads CSV into two files: leads with a mobile number (to call)
and leads without one (to email or DM).

Usage: python3 split_leads.py leads/2026-09-29-test-100.csv
Writes <name>-with-phone.csv and <name>-no-phone.csv next to the input.
"""

import csv
import sys
from pathlib import Path

PHONE_FIELDS = ("mobile_number_formatted", "mobile_number")


def has_phone(row):
    return any((row.get(f) or "").strip() for f in PHONE_FIELDS)


def main(path):
    src = Path(path)
    with src.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Apify CSVs start with a byte-order mark inside a quoted header.
        reader.fieldnames = [k.replace("﻿", "").strip('"') for k in reader.fieldnames]
        fields = reader.fieldnames
        rows = list(reader)

    with_phone = [r for r in rows if has_phone(r)]
    no_phone = [r for r in rows if not has_phone(r)]

    for suffix, subset in (("with-phone", with_phone), ("no-phone", no_phone)):
        out = src.with_name(f"{src.stem}-{suffix}.csv")
        with out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(subset)
        print(f"{out.name}: {len(subset)} leads")

    emailable = sum(1 for r in no_phone if (r.get("email") or "").strip())
    print(f"  of the no-phone leads, {emailable} have an email, "
          f"{len(no_phone) - emailable} only LinkedIn or nothing")


if __name__ == "__main__":
    main(sys.argv[1])
