"""Keep at most 3 contacts per brand across all pet waves, best roles first.
Wave-1 contacts were already emailed, so they always count toward the 3.
Writes the contacts to REMOVE from the Instantly drafts (waves 2-4) and trimmed CSVs."""
import csv, re, collections

TITLES = {}
for f in ["2026-10-08-pet-apollo-good.csv", "2026-10-08-pet-apollo-catch_all.csv"]:
    for r in csv.DictReader(open(f)):
        TITLES[r["email"].lower()] = r["title"]

def score(title):
    t = title.lower()
    if re.search(r"\b(founder|co-founder|owner|ceo|chief executive|president)\b", t) and "vice" not in t:
        return 1
    if re.search(r"(marketing|e-?commerce|growth|digital|dtc|brand|cmo)", t) and re.search(r"(chief|vp|vice|head|director|cmo)", t):
        return 2
    if re.search(r"\b(coo|chief operating|general manager)\b", t):
        return 3
    if re.search(r"(marketing|e-?commerce|brand|growth|digital)", t):
        return 4
    return 9  # finance, HR, sales, supply chain, creative, ops staff...

# people a reply pointed us to
REFERRED = {"dawn.miedler@antelopepets.com"}

rows = []
for kind in ["good", "catch_all", "noline"]:
    for r in csv.DictReader(open(f"2026-10-08-pet-apollo-instantly-{kind}.csv")):
        r["kind"] = kind
        r["title"] = TITLES.get(r["email"].lower(), "")
        r["wave"] = int(r["wave"])
        rows.append(r)

brands = collections.defaultdict(list)
for r in rows:
    brands[r["website"].lower().rstrip("/")].append(r)

keep, drop = [], []
for site, rs in brands.items():
    sent = [r for r in rs if r["wave"] == 1]
    dom = re.sub(r"^https?://(www\.)?", "", site).split("/")[0]
    # other companies' addresses (agencies, sister brands) never count as this brand
    rest = [r for r in rs if r["wave"] > 1 and r["email"].lower().endswith("@" + dom)]
    rest.sort(key=lambda r: (r["email"].lower() not in REFERRED, score(r["title"]), r["wave"]))
    slots = max(0, 3 - len(sent))
    ok = [r for r in rest if score(r["title"]) < 9 or r["email"].lower() in REFERRED][:slots]
    if not ok and slots:  # no decision maker on file: one director rather than nobody
        ok = [r for r in rest if "director" in r["title"].lower()][:1]
    for i, r in enumerate(ok):  # 2nd contact -> wave 2, 3rd -> wave 3
        r["old_wave"], r["wave"] = r["wave"], 2 + i
    keep += sent + ok
    drop += [r for r in rest if r not in ok]

for r in rows: r.setdefault("old_wave", r["wave"])
moved_in = [r for r in keep if r["old_wave"] != r["wave"] and r["wave"] > 1]
with open("2026-10-13-pet-add-to-waves-2-3.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, ["email","first_name","last_name","company_name","website","chatgpt_line","title","kind","old_wave","wave"], extrasaction="ignore"); w.writeheader()
    w.writerows(sorted(moved_in, key=lambda r: (r["kind"], r["wave"], r["company_name"])))
print("add to wave drafts:", collections.Counter((r["kind"], r["wave"]) for r in moved_in))
print("remove from wave 2-4 drafts:", collections.Counter((r["kind"], r["old_wave"]) for r in drop + [r for r in keep if r["old_wave"]!=r["wave"] and r["old_wave"]<=4] if r["old_wave"]<=4))
cols = ["email","first_name","last_name","company_name","title","kind","wave","website"]
with open("2026-10-13-pet-remove-from-waves-2-4.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, cols, extrasaction="ignore"); w.writeheader()
    w.writerows(sorted([r for r in drop + [k for k in keep if k["old_wave"] != k["wave"]] if r["old_wave"] <= 4], key=lambda r: (r["kind"], r["wave"], r["company_name"])))
with open("2026-10-13-pet-keep-all-waves.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, cols + ["chatgpt_line"], extrasaction="ignore"); w.writeheader()
    w.writerows(sorted(keep, key=lambda r: (r["wave"], r["kind"], r["company_name"])))

def count(rs, waves): return sum(1 for r in rs if r["wave"] in waves)
print("brands:", len(brands))
for wv in [2,3,4]:
    print(f"wave {wv}: {count(rows,[wv])} now -> {count(keep,[wv])} after")
print("waves 5+:", count(rows, range(5,99)), "->", count(keep, range(5,99)))
print("remove from Instantly drafts (waves 2-4):", sum(1 for r in drop if r["old_wave"]<=4))
print("\nAntelope:")
for r in sorted(brands["https://antelopepets.com"], key=lambda r: r["wave"]):
    print(f"  w{r['wave']:<2} {'KEEP' if r in keep else 'drop'}  {r['first_name']} {r['last_name']} - {r['title']}")
print("\nearthbath:")
for r in sorted(brands["https://earthbath.com"], key=lambda r: r["wave"]):
    print(f"  w{r['wave']:<2} {'KEEP' if r in keep else 'drop'}  {r['first_name']} {r['last_name']} - {r['title']}")
