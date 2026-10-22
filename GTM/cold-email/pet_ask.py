"""Step 2: ask ChatGPT (via Apify) one buyer question per pet brand. Writes pet-apollo-answers-2026-10-08.json."""
import json, os, sys
from pet_question_phrases import P
NOPRICE = {"meowingtons.com","pupring.com","weratedogs.com","dogisgood.com","puplid.com","tateandtaylor.com","thegentlepit.com",
 "spiritpieces.com","samandnala.com","lifekey.co","silidog.com","petoi.com","welovedoodles.com","weareplufl.com","lolahemp.com",
 "petyupp.com","purlifebrands.com","furrymuse.com","getbistrocat.com","incredpets.com","swiftpaws.com","petppi.com",
 "themoderndogcompany.com","majestichomegoods.com","mypetchicken.com","horseguard.com","friendsheepwool.com","petfriendlybox.com"}
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "pet-apollo-questions-2026-10-08.json")))
qs = {}
for dom, phrase in P.items():
    if phrase in ("N", "R", "SKIP"): continue
    p = d[dom]["product"]
    price = "" if (dom in NOPRICE or not p) else " for around $%d" % round(p["price"])
    qs[dom] = "What's the best %s to buy online%s?" % (phrase, price)
FORMAT = " Name three specific products. Reply in ONE line exactly like: 1) Brand: product name; 2) Brand: product name; 3) Brand: product name"
APP = "/Users/kelianvantulder/Desktop/Kelian OS/AEO-for-eccomerce-brands/mvp/app"
sys.path.insert(0, APP)
for line in open(os.path.join(APP, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip("\"'"))
os.chdir(APP)
import apify_answers
print("asking", len(set(qs.values())), "questions", flush=True)
res = apify_answers.ask_batch([q + FORMAT for q in set(qs.values())], engine="chatgpt", timeout=3000,
                              on_start=lambda r, ds: print("run", r, ds, flush=True))
out = {dom: dict(question=q, answer=(res.get(q + FORMAT) or ("",))[0]) for dom, q in qs.items()}
json.dump(out, open(os.path.join(HERE, "pet-apollo-answers-2026-10-08.json"), "w"), indent=1)
print("answered", sum(1 for v in out.values() if v["answer"]), "of", len(out), flush=True)
