"""Build the wave 2-3 upload files from the trimmed keep list, with the new
ChatGPT line that names the recipient's own company (2026-10-13)."""
import csv, re, collections

SUFFIX = re.compile(r"(,?\s+(inc\.?|llc|co\.|company|corp\.?|pet products|pet supplies|pet food|pets?))+$", re.I)
# hand-checked: only names where the brand plainly calls itself the shorter form
RENAME = {"Open Farm Pet": "Open Farm", "Redbarn Pet Products": "Redbarn", "Innovet Pet Products": "Innovet",
          "Earth Buddy Pet": "Earth Buddy", "Dr. Buzby's Senior Dog Co.": "Dr. Buzby's",
          "Under the Weather Pet": "Under the Weather", "Portland Pet Food Company": "Portland Pet Food"}
def clean(name):
    n = name.replace("®", "").replace("™", "").strip()
    return RENAME.get(n, n)

OLD_A = re.compile(r"One of the products it recommended was (.+?), made by (.+?), another brand in your category\.")
OLD_B = re.compile(r"It recommended (.+?) from (.+?)\.$")

def rewrite(line, co):
    m = OLD_A.search(line) or OLD_B.search(line)
    if not m:
        return None
    return line[:m.start()] + f"One of its picks was {m.group(1)} by {m.group(2)}, a competitor of {co}."

rows = list(csv.DictReader(open("2026-10-13-pet-keep-all-waves.csv")))
out = collections.defaultdict(list)
renamed, unmatched = set(), []
for r in rows:
    if r["wave"] not in ("2", "3"):
        continue
    co = clean(r["company_name"])
    if co != r["company_name"]:
        renamed.add((r["company_name"], co))
    line = r["chatgpt_line"]
    if line:
        new = rewrite(line, co)
        if new is None:
            unmatched.append((r["email"], line)); continue
        line = new
    out[(r["kind"], r["wave"])].append({"email": r["email"], "first_name": r["first_name"],
        "last_name": r["last_name"], "company_name": co, "website": r["website"], "chatgpt_line": line})

for (kind, wave), rs in sorted(out.items()):
    fn = f"2026-10-13-pet-UPLOAD-{kind}-wave{wave}.csv"
    with open(fn, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rs[0])); w.writeheader(); w.writerows(rs)
    print(f"{fn}: {len(rs)}")
print("\nrenamed:"); [print(f"  {a}  ->  {b}") for a, b in sorted(renamed)]
print("\nunmatched lines (left out):", len(unmatched)); [print(" ", e, l[:150]) for e, l in unmatched]
