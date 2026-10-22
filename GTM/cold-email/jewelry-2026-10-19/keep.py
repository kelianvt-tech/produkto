"""Hand decision from sites.csv (titles, products, cart), 2026-10-19: own jewelry brand selling online = keep.
Dropped: no site found, not jewelry, B2B/wholesale supply, local retail stores selling other brands, wrong person."""
import csv
KEEP = """shapirodiamonds.com parkgems.com sloanest.com chelseacharles.com fiametta.com mareinewyork.com remeinz.com
jainjewelrynetwork.com laurapreshong.com sarahcornwelljewelry.com stephaniegottlieb.com margaretrowe.com jeandousset.com
goldeluxe.com harwellgodfrey.com deeberkley.com jewelrynest.com bravedaughters.com courtneyracquel.com patrickmohs.com
danarebeccadesigns.com lindseyleighjewelry.com lisarobinjewelry.com rebeccaovermann.com jenniferalfano.com barngirljewelry.com
carterevejewelry.com abelobjects.com ino.jewelry shoplemel.com charmedcircle.com erinmcdermott.com saraweinstock.com
rosierjewelry.com kinmarked.com forgejewelryworks.com elysiumblack.com tinytags.com paigenovick.com kimberlypucci.com
stashajewelry.myshopify.com juniperjewelrydesigns.com magnetudejewelry.com aweinspired.com chalonne.com nolitadiamonds.com
bashaharris.com rockswithsoul.com rutareifen.com tatirocks.com janegordon.com circlestonedesigns.com eaarthbones.com
nancyyuanjewelry.com balacia.com""".split()
rows = list(csv.DictReader(open("sites.csv")))
keep = [r for r in rows if r["domain"] in KEEP]
drop = [r for r in rows if r["domain"] not in KEEP]
for name, part in (("keep.csv", keep), ("drop.csv", drop)):
    w = csv.DictWriter(open(name, "w", newline=""), fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(part)
print(len(keep), "kept,", len(drop), "dropped,", len({r["domain"] for r in keep}), "brands")
