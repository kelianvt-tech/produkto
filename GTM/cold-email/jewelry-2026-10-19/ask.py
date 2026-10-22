"""Step 3 (paid, ~$0.005 per question via Apify ChatGPT): one buyer question per brand, from its best-seller."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
B = json.load(open(os.path.join(HERE, "best-sellers.json")))
FIX = {"paigenovick.com": "ear cuff", "sarahcornwelljewelry.com": "pearl necklace"}  # best-seller misread by keyword
qs = {}
for d, p in B.items():
    t = FIX.get(d) or (p and p["type"]) or "gold necklace"
    price = p and p["price"] >= 20 and d not in FIX and " for around $%s" % format(round(p["price"], -1 if p["price"] < 1000 else -2), ",.0f") or ""
    qs[d] = dict(type=t, question="What's the best %s to buy online%s?" % (t, price))
FORMAT = " Name three specific products. Reply in ONE line exactly like: 1) Brand: product name; 2) Brand: product name; 3) Brand: product name"
APP = os.path.abspath(os.path.join(HERE, "../../../mvp/app"))
sys.path.insert(0, APP)
for line in open(os.path.join(APP, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip("\"'"))
os.chdir(APP)
import apify_answers
uniq = sorted({v["question"] for v in qs.values()})
print("asking", len(uniq), "questions", flush=True)
res = apify_answers.ask_batch([q + FORMAT for q in uniq], engine="chatgpt", timeout=3000,
                              on_start=lambda r, ds: print("run", r, ds, flush=True))
for d, v in qs.items():
    v["answer"] = (res.get(v["question"] + FORMAT) or ("",))[0]
json.dump(qs, open(os.path.join(HERE, "answers.json"), "w"), indent=1)
print("answered", sum(1 for v in qs.values() if v["answer"]), "of", len(qs), flush=True)
