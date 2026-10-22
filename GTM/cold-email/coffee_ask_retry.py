"""Re-ask only unanswered coffee questions, in batches of 50, merging into coffee-answers-2026-10-15.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, "coffee-answers-2026-10-15.json")
out = json.load(open(F))
FORMAT = " Name three specific products. Reply in ONE line exactly like: 1) Brand: product name; 2) Brand: product name; 3) Brand: product name"
APP = "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/mvp/app"
sys.path.insert(0, APP)
for line in open(os.path.join(APP, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip("\"'"))
os.chdir(APP)
import apify_answers
todo = sorted({v["question"] for v in out.values() if not v["answer"]})
print("missing", len(todo), flush=True)
for i in range(0, len(todo), 50):
    batch = todo[i:i + 50]
    try:
        res = apify_answers.ask_batch([q + FORMAT for q in batch], engine="chatgpt", timeout=1800,
                                      on_start=lambda r, ds: print("run", r, ds, flush=True))
    except Exception as e:
        print("batch failed", e, flush=True); continue
    for v in out.values():
        if not v["answer"] and v["question"] in batch:
            v["answer"] = (res.get(v["question"] + FORMAT) or ("",))[0]
    json.dump(out, open(F, "w"), indent=1)
    print("after batch", i // 50 + 1, "answered", sum(1 for v in out.values() if v["answer"]), "of", len(out), flush=True)
