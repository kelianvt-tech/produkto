"""Step 4: Instantly upload files for coffee & tea: good / catch_all / noline, one file per wave."""
import csv, json, re, collections
from coffee_question_phrases import phrase
L = json.load(open("coffee-lines-2026-10-15.json"))
def dom(r): return re.sub(r"^https?://(www\.)?", "", r["website"] or r["email"].split("@")[1]).strip("/").lower()
out, dropped = collections.defaultdict(list), collections.Counter()
for r in csv.DictReader(open("2026-10-13-coffee-main.csv")):
    d = dom(r)
    if phrase(d)[0] == "N": dropped["client / not US"] += 1; continue
    l = L.get(d, {})
    line = l.get("line", "") if l.get("flag") == "ok" else ""
    kind = "noline" if not line else ("good" if r["email_result"] == "ok" else "catch_all")
    out[(kind, r["wave"])].append(dict(email=r["email"], first_name=r["first_name"], last_name=r["last_name"],
        company_name=l.get("company") or r["company_name"], website=r["website"], chatgpt_line=line))
for (k, w), rows in sorted(out.items()):
    fn = f"2026-10-15-coffee-UPLOAD-{k}-wave{w}.csv"
    with open(fn, "w", newline="") as fh:
        wr = csv.DictWriter(fh, list(rows[0])); wr.writeheader(); wr.writerows(rows)
    print(fn, len(rows))
print("dropped", dict(dropped))
