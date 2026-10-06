"""Rebuild a scan's numbers from answers you have already paid for.

WHY THIS EXISTS
---------------
Asking ChatGPT a buyer question costs about 10 cents, and a catalog scan
costs about $5. But the expensive part - what ChatGPT actually said - is
saved in the database forever and never changes. Everything after that
(reading the answer into a product list, deciding which mentions are the
merchant's, and every number on the dashboard) is arithmetic on text we
already own.

So while you are building, you almost never need to buy new answers. You
need to re-run the arithmetic. That is what this does, for free.

  --score     recompute every dashboard number            $0.00
  --rematch   redecide which mentions are the merchant's  $0.00
              (use after changing match rules or aliases), then --score
  --extract   re-read the stored answers into product     ~$0.02 per scan
              lists with the cheap helper model

THIS IS A DEVELOPMENT TOOL AND IT IS NOT WIRED INTO THE APP.
The website never imports this file. When a real person clicks "scan", the
app calls scan.start() and buys real answers from the API, exactly as it
does today. Nothing here changes that, and nothing here should ever be put
behind a button. Replay re-reads history; it cannot tell you anything new
about a store, and it never creates a scan that did not happen.

USAGE
-----
    python3 replay.py --list                # what is in the database
    python3 replay.py --score all           # after changing scoring.py
    python3 replay.py --rematch all         # after changing match rules
    python3 replay.py --extract 5 --yes     # after changing EXTRACT_INSTRUCTIONS

Restarting the app is not required - the dashboard notices the rewrite.
"""

import argparse
import json
import shutil
import sys
import time

import config
import db
import evidence
import llm
import scan
import scoring


def resolve(value):
    """'all', '5', or '1,3,5' -> a list of scan ids that exist."""
    have = [r["id"] for r in db.all_("SELECT id FROM scans ORDER BY id")]
    if value in (None, "", "all"):
        return have
    wanted, missing = [], []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or int(part) not in have:
            missing.append(part)
        else:
            wanted.append(int(part))
    if missing:
        raise SystemExit("No such scan: %s. Run --list to see what exists."
                         % ", ".join(missing))
    return wanted


def context(scan_id):
    """The catalog and brand names this scan was run against."""
    row = db.one("SELECT * FROM scans WHERE id=?", (scan_id,))
    ps = db.decode_prompts(
        db.one("SELECT * FROM prompt_sets WHERE id=?", (row["prompt_set_id"],)))
    products = ps["catalog_snapshot"]
    domain = ps["store_domain"] or (products[0]["store_domain"] if products else "")
    return row, ps, products, scan.brand_aliases(domain, products)


def show_list():
    rows = db.all_("""SELECT s.id, s.status, s.run_at, s.cost_cents,
                             ps.store_domain AS domain,
                             (SELECT COUNT(*) FROM answers WHERE scan_id=s.id) AS answers,
                             (SELECT COUNT(DISTINCT prompt) FROM answers WHERE scan_id=s.id) AS questions,
                             (SELECT COUNT(*) FROM mentions m JOIN answers a ON a.id=m.answer_id
                               WHERE a.scan_id=s.id) AS mentions
                      FROM scans s JOIN prompt_sets ps ON ps.id=s.prompt_set_id
                      ORDER BY s.id""")
    if not rows:
        print("No scans yet. The first one has to be bought.")
        return
    print("%3s  %-22s %-9s %9s %7s %8s %9s"
          % ("id", "store", "status", "questions", "answers", "mentions", "cost"))
    paid = 0.0
    for r in rows:
        paid += (r["cost_cents"] or 0) / 100
        print("%3d  %-22s %-9s %9d %7d %8d %9s"
              % (r["id"], (r["domain"] or "-")[:22], r["status"], r["questions"],
                 r["answers"], r["mentions"],
                 "$%.2f" % ((r["cost_cents"] or 0) / 100) if r["cost_cents"] else "-"))
    print("\n%d scans already paid for. Everything below re-uses them." % len(rows))
    if paid:
        print("Recorded spend: $%.2f. Replaying it again costs nothing." % paid)


def do_score(ids):
    for sid in ids:
        answers = db.one("SELECT COUNT(*) n FROM answers WHERE scan_id=?", (sid,))["n"]
        if not answers:
            print("  scan %d: no stored answers, skipped" % sid)
            continue
        scoring.score(sid)
        s = db.one("SELECT appearance_rate, avg_rank, sov_pct FROM scores WHERE scan_id=?", (sid,))
        print("  scan %d: rescored from %d answers -> mentioned in %s of answers, "
              "average position %s, share of voice %s"
              % (sid, answers,
                 "-" if not s or s["appearance_rate"] is None else "%.0f%%" % s["appearance_rate"],
                 "-" if not s or s["avg_rank"] is None else "%.1f" % s["avg_rank"],
                 "-" if not s or s["sov_pct"] is None else "%.1f%%" % s["sov_pct"]))


def do_rematch(ids):
    """Re-run the 'is this mention theirs?' decision over stored mentions.

    Only the decision columns are rewritten. The mention's text, brand, url
    and rank are what the engine said and are left exactly as they are.
    """
    for sid in ids:
        _, _, products, aliases = context(sid)
        if not products:
            print("  scan %d: no catalog snapshot, skipped" % sid)
            continue
        prepared = scan.prepare_catalog(products, aliases)
        rows = db.all_("""SELECT m.* FROM mentions m JOIN answers a ON a.id=m.answer_id
                          WHERE a.scan_id=?""", (sid,))
        changed = 0
        with db._lock, db.conn() as c:
            for m in rows:
                pid, brand, value = scan.match_catalog(dict(m), products, aliases, prepared)
                if (pid, int(brand), value) == (m["matched_product_id"],
                                                m["is_their_brand"], m["match_score"]):
                    continue
                changed += 1
                c.execute("""UPDATE mentions SET is_theirs=?, is_their_brand=?,
                             match_score=?, matched_product_id=? WHERE id=?""",
                          (int(pid is not None), int(brand), value, pid, m["id"]))
        db._revision += 1
        theirs = db.one("""SELECT COUNT(*) n FROM mentions m JOIN answers a ON a.id=m.answer_id
                           WHERE a.scan_id=? AND m.is_theirs=1""", (sid,))["n"]
        print("  scan %d: %d of %d mentions changed, %d now count as theirs"
              % (sid, changed, len(rows), theirs))
    do_score(ids)


def do_extract(ids, yes):
    """Re-read stored answers into product lists with the helper model.

    This is the only replay that touches the API, because reading prose into
    a list is a model's job. It uses the cheap model and the answers are
    already bought, so it is roughly 0.4% of what the scan cost.
    """
    answers = db.all_("SELECT id, scan_id, prompt, raw_text FROM answers "
                      "WHERE scan_id IN (%s) ORDER BY id" % ",".join("?" * len(ids)), ids)
    estimate = 0.0004 * len(answers)
    print("  %d stored answers to re-read with %s. Estimated cost: $%.2f"
          % (len(answers), config.HELPER_MODEL, estimate))
    if not yes:
        print("  Nothing spent. Add --yes to re-extract for real.")
        return False
    backup = str(config.DB_PATH) + ".pre-replay-" + str(int(time.time())) + ".bak"
    shutil.copy2(config.DB_PATH, backup)
    print("  Backed up to %s" % backup)

    usage = llm.Usage()
    per_scan = {}
    for a in answers:
        try:
            items = llm.json_call(scan.EXTRACT_INSTRUCTIONS,
                                  "Shopping question: %s\n\nAnswer:\n%s"
                                  % (a["prompt"], a["raw_text"]),
                                  "recommendations", scan.EXTRACT_SCHEMA, usage).get("items") or []
        except llm.LLMError as e:
            print("  ! answer %d failed: %s (its old mentions are left alone)" % (a["id"], e))
            continue
        items.sort(key=lambda i: i.get("rank") or 999)
        with db._lock, db.conn() as c:
            # Replaces this answer's product list. The answer itself - the only
            # record of what the engine said - is never touched.
            c.execute("DELETE FROM mentions WHERE answer_id=?", (a["id"],))
            for pos, it in enumerate(items, 1):
                c.execute("""INSERT INTO mentions(answer_id,product_name,brand,url,rank,
                             is_theirs,is_their_brand,match_score,matched_product_id,price)
                             VALUES(?,?,?,?,?,0,0,0,NULL,?)""",
                          (a["id"], it.get("product_name", ""), it.get("brand", ""),
                           it.get("url", ""), pos, (it.get("price") or "").strip()[:40]))
            c.execute("UPDATE answer_processing SET status='done', error=NULL WHERE answer_id=?",
                      (a["id"],))
        db._revision += 1
        per_scan[a["scan_id"]] = per_scan.get(a["scan_id"], 0) + len(items)
    cents = usage.cost_cents()
    for sid, n in sorted(per_scan.items()):
        print("  scan %d: %d mentions re-extracted" % (sid, n))
    print("  Actual cost: %s" % ("unknown" if cents is None else "$%.4f" % (cents / 100)))
    do_rematch(ids)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("USAGE")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show the scans on disk")
    ap.add_argument("--score", metavar="IDS", nargs="?", const="all",
                    help="recompute the dashboard numbers (free)")
    ap.add_argument("--rematch", metavar="IDS", nargs="?", const="all",
                    help="redecide which mentions are theirs, then rescore (free)")
    ap.add_argument("--extract", metavar="IDS", nargs="?", const="all",
                    help="re-read stored answers into product lists (~$0.02/scan)")
    ap.add_argument("--yes", action="store_true", help="required by --extract")
    args = ap.parse_args()

    db.init()
    scan.recover_interrupted()
    evidence.clear_cache()

    if args.list or not (args.score or args.rematch or args.extract):
        show_list()
        if not (args.score or args.rematch or args.extract):
            print("\nNothing replayed. Pick --score, --rematch or --extract.")
            return 0

    if args.extract:
        print("\nRe-extracting:")
        touched = do_extract(resolve(args.extract), args.yes)
    elif args.rematch:
        print("\nRematching:")
        do_rematch(resolve(args.rematch))
        touched = True
    else:
        print("\nRescoring:")
        do_score(resolve(args.score))
        touched = True

    if touched:
        print("\nDone. Reload the dashboard - no restart needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
