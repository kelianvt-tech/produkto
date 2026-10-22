"""Step 4 (free): first product in each ChatGPT answer -> competitor + opener; writes close-import.csv/json."""
import csv, json, re
A = json.load(open("answers.json")); B = json.load(open("best-sellers.json"))
PLURAL = {"stud earrings": "stud earrings", "hoop earrings": "hoop earrings", "earrings": "earrings", "ear cuff": "ear cuffs",
          "watch band": "watch bands", "tennis bracelet": "tennis bracelets", "wedding band": "wedding bands",
          "engagement ring": "engagement rings", "pearl necklace": "pearl necklaces"}
RETAIL = re.compile(r"nordstrom|macy|amazon|zales|steven singer|robinson|smyth|pampillonia|monaco jewelers|ross-simons", re.I)
def picks(ans):
    ans = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", ans).lstrip("* ")
    return [(b.strip(" *"), p.strip(" .;*")) for b, p in re.findall(r"\d\)\s*([^:;]+):\s*([^;]+)", ans)]
rows = list(csv.DictReader(open("keep.csv")))
NAME = {"barngirljewelry.com": "Barn Girl Jewelry", "rebeccaovermann.com": "Rebecca Overmann", "jenniferalfano.com": "Jennifer Alfano Jewelry",
        "rosierjewelry.com": "Rosier Fine Jewelry", "paigenovick.com": "Paige Novick", "jainjewelrynetwork.com": "Jain Jewelry Network",
        "magnetudejewelry.com": "Magnetude Jewelry", "sami": ""}
out = []
for r in rows:
    d = r["domain"]; a = A[d]; t = a["type"]
    ptype = PLURAL.get(t, t + "s")
    own = re.sub(r"\W", "", r["matched_name"].lower())
    brand = prod = ""; flag = "ok"
    for b, p in picks(a["answer"]):
        if own and own[:6] in re.sub(r"\W", "", b.lower()):
            brand, prod, flag = b, p, "THEIR product recommended"; break
        if not RETAIL.search(b):
            brand, prod = b, p; break
    if "for around" not in a["question"] and t == "gold necklace":
        flag = "no names (generic question)"
    if not brand: flag = "no names"
    if flag == "ok":
        opener = "I've been looking at which %s ChatGPT recommends, and the %s from %s keeps coming up." % (ptype, re.sub(r"^the ", "", prod, flags=re.I), brand)
    elif flag.startswith("THEIR"):
        opener = "I've been looking at which %s ChatGPT recommends, and your %s keeps coming up." % (ptype, prod)
    else:
        opener = "I've been looking at which %s ChatGPT recommends, and it only names two or three." % ("pieces of jewelry" if t == "gold necklace" else ptype)
    bs = B.get(d) or {}
    out.append({"Company": NAME.get(d) or (r["matched_name"] if r["current_company"] in ("", "Self-employed") else r["current_company"].strip()),
                "URL": "https://" + d, "Contact Name": r["name"], "Contact Title": r["linkedin_headline"], "Contact Phone": r["phone"],
                "Location": r["location"], "LinkedIn": r["linkedin"], "Product type": ptype,
                "Their product": bs.get("title", ""), "Their price": "$%d" % bs["price"] if bs else "",
                "Competitor product": prod if flag == "ok" else "", "Competitor brand": brand if flag == "ok" else "",
                "Call flag": flag, "Opener": opener + " Can I take 15 seconds to explain why I'm calling?",
                "ChatGPT question": a["question"], "Batch": "2026-10-19-jewelry"})
w = csv.DictWriter(open("close-import.csv", "w", newline=""), fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
from collections import Counter; print(Counter(o["Call flag"] for o in out))
for o in out: print(o["Company"][:24], "|", o["Call flag"][:10], "|", o["Opener"][:120])
