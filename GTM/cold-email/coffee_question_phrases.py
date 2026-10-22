# Buyer phrase per coffee/tea brand, from its best-seller (2026-10-15).
# Rules first (keyword -> phrase), then hand overrides. "N" = not sent a line (not US / not a shop / client).
# phrase(dom) returns (phrase, use_price).
import re, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "coffee-questions-2026-10-15.json")))

O = {  # hand overrides: dom -> (phrase, use_price)
 "partnerscoffee.com": ("N", 0),           # Kelian's client
 "thecoffeefactory.co.uk": ("N", 0), "teamountain.co.uk": ("N", 0), "flatwhite.qa": ("N", 0), "teashop.com": ("N", 0),
 "ratiocoffee.com": ("drip coffee maker", 0), "wholelattelove.com": ("home espresso grinder", 0),
 "vistaclaracoffee.com": ("whole bean coffee", 0), "voltagecoffeesupply.com": ("espresso machine accessories", 0),
 "seattlecoffeegear.com": ("home espresso machine", 0), "airtea.co": ("electric tea kettle", 0),
 "beannbeancoffee.com": ("pour over coffee dripper", 0), "uendure.com": ("tea infuser bottle", 1),
 "nepalteacollective.com": ("loose leaf black tea", 0), "rishi-tea.com": ("loose leaf tea", 0),
 "august.la": ("loose leaf tea", 0), "honeyandrosescoffee.com": ("whole bean coffee", 0),
 "strongcoffeecompany.com": ("caffeine gummies", 1), "kiidcoffee.com": ("superfood latte mix", 1),
 "crockettcoffee.com": ("mushroom coffee", 1), "notyouraverage.coffee": ("superfood coffee", 1),
 "tridentcoffee.com": ("functional coffee", 0), "sportcoffee.com": ("protein coffee drink", 0),
 "bobateaprotein.com": ("milk tea protein powder", 1), "tealadybk.com": ("adaptogen latte powder", 1),
 "steepedcoffee.com": ("single-serve coffee bags", 0), "frinjcoffee.com": ("California-grown coffee", 0),
 "kauaicoffee.com": ("Hawaiian coffee", 0), "sweetmarias.com": ("green coffee beans for home roasting", 0),
 "atomocoffee.com": ("ground coffee", 1), "excelsacoffee.com": ("Vietnamese coffee beans", 1),
 "nam.coffee": ("Vietnamese robusta coffee", 1), "nguyencoffeesupply.com": ("Vietnamese coffee beans", 1),
 "vaidaicoffee.com": ("Vietnamese coffee", 0), "owlvericks.com": ("Vietnamese coffee beans", 1),
 "secretsoftea.com": ("baby tummy tea", 1), "senbirdtea.com": ("Japanese buckwheat tea", 1),
 "yauponbrothers.com": ("yaupon tea", 1), "avocadotea.com": ("avocado leaf tea", 1),
 "saintjamesicedtea.com": ("yerba mate drink", 0), "tamatea.com": ("yerba mate tea", 0),
 "drinkkace.com": ("canned green tea", 0), "prettytasty.com": ("canned iced tea", 0), "drinkhalfday.com": ("canned iced tea", 0),
 "kirralife.com": ("canned iced tea", 0), "drinkooso.com": ("canned iced tea", 0), "mabitea.com": ("bottled iced tea", 0),
 "eatthechange.com": ("canned iced tea", 0), "hugotea.com": ("chai concentrate", 0), "transittea.com": ("tea concentrate", 0),
 "revolutiontea.com": ("cold brew iced tea bags", 1), "senchateabar.com": ("Japanese sencha green tea", 0),
 "memteaimports.com": ("ceremonial matcha", 1), "drinkteabar.com": ("matcha powder", 1), "bighearttea.com": ("organic matcha", 0),
 "tatsutea.com": ("matcha energy drink", 0), "teadrunk.com": ("Chinese loose leaf tea", 0), "opendoortea.com": ("loose leaf tea", 0),
 "myteadrop.com": ("instant tea", 0), "joymilktea.com": ("milk tea", 0), "": ("N", 0),
 "highbrewcoffee.com": ("canned espresso drink", 0), "drinklaurels.com": ("canned latte", 0), "sailawaycoffee.com": ("canned oat milk latte", 0),
 "evermorecoffee.com": ("canned oat milk latte", 0), "drinklococoffee.com": ("canned cold brew coffee", 0),
 "lacabra.com": ("light roast coffee beans", 0), "coffeeandcream.app": ("Nespresso compatible capsules", 0),
 "cerinicoffee.com": ("espresso capsules", 1), "maticoffee.com": ("espresso capsules", 0),
 "runyoncoffee.com": ("whole bean coffee", 0), "threetreecoffee.com": ("whole bean coffee", 0), "whirlwindcoffee.com": ("whole bean coffee", 0),
 "timelesscoffee.com": ("whole bean coffee", 0), "coffeeandchill.com": ("whole bean coffee", 0), "enigmacoffee.com": ("whole bean coffee", 0),
 "abbotsfordroad.com": ("specialty coffee beans", 0), "ferriscoffee.com": ("whole bean coffee", 0), "justcoffee.coop": ("organic fair trade coffee", 0),
 "saratogateaandhoney.com": ("loose leaf tea", 0), "sippingstreams.com": ("loose leaf tea", 0), "pointlomatea.com": ("loose leaf tea", 0),
 "davescoffee.com": ("coffee syrup", 1), "hardycoffee.com": ("whole bean coffee", 0), "transcendencecoffee.com": ("whole bean coffee", 0),
 "coffeedose.cafe": ("whole bean coffee", 0), "caljavacoffeeroasters.com": ("whole bean coffee", 0), "coulee coffee": ("N", 0),
 "couleecoffee.com": ("whole bean coffee", 0), "fostercoffee.co": ("whole bean coffee", 0),
 "goodasgold.com": ("green tea bags", 0), "freshroastedcoffee.com": ("whole bean coffee", 0),
 "frenchtruckcoffee.com": ("whole bean coffee", 0), "ahmadteausa.com": ("decaf black tea bags", 0),
 "raazi.co": ("ginger turmeric tea", 1), "happynesstea.co": ("spearmint tea", 1), "teanme.co": ("moringa tea", 1),
 "fullleaftc.com": ("anti-inflammatory tea", 0), "looseleafteamarket.com": ("anti-inflammatory herbal tea", 1),
 "totaltea.com": ("detox tea", 1), "commoditeas.com": ("calming tea", 0), "clubmagichour.com": ("herbal tea", 0),
 "artemistea.com": ("herbal loose leaf tea", 1), "calabashtea.com": ("herbal tea", 0), "panamecoffee.com": ("digestive herbal tea", 1),
 "oregonteatraders.com": ("blue herbal tea", 0), "heavenlytealeaves.com": ("loose leaf herbal tea", 0),
 "snarkytea.com": ("fruit herbal tea", 0), "transcendingtea.com": ("loose leaf tea", 0), "shopmycupoftea.com": ("flavored loose leaf tea", 0),
 "piperandleaf.com": ("tea bags", 0), "rakkasantea.com": ("black tea bags", 0), "chadotea.com": ("pyramid tea bags", 1),
 "stashtea.com": ("tea advent calendar", 1), "tiestatea.com": ("tea advent calendar", 1), "republicoftea.com": ("tea advent calendar", 1),
 "teawithtae.com": ("tea gift box", 1), "ashevilleteacompany.com": ("loose leaf tea gift set", 1), "naturesteacompany.com": ("loose leaf tea gift set", 1),
 "myteaconnection.com": ("loose leaf tea", 0), "spirittea.co": ("loose leaf tea subscription", 0), "oldbarreltea.com": ("tea subscription box", 0),
 "marktwendell.com": ("smoky black tea", 0), "dobrateapgh.com": ("masala chai tea", 0), "frasertea.com": ("cinnamon black tea", 0),
 "lakemissoulateacompany.com": ("flavored black tea", 0), "wakacoffee.com": ("instant tea", 1), "youngmountaintea.com": ("black tea", 1),
 "numitea.com": ("organic black tea", 0),
}
def phrase(dom):
    if dom in O: return O[dom]
    p = (D.get(dom) or {}).get("product")
    if not p: return ("whole bean coffee", 0)
    t = (p["title"] + " " + p["type"]).lower()
    ok = 10 <= p["price"] <= 40
    tea = "tea" in t and "coffee" not in t
    rules = [
        (r"earl grey", "earl grey tea"), (r"matcha", "matcha"), (r"chai|masala", "chai tea"),
        (r"green tea|sencha|jasmine", "green tea"), (r"herbal|rooibos|chamomile|peppermint", "herbal tea"),
        (r"english breakfast|black tea", "black tea"),
        (r"k-?cups?|pods|single.?serve|ecopod", "K-Cup coffee pods"), (r"instant", "instant coffee"),
        (r"cold brew", "cold brew coffee"), (r"decaf", "decaf coffee beans"),
        (r"pecan|grog|mocha|pumpkin|cinnamon|cannoli|vanilla|praline|gingerbread|chocolate|blueberry|butter|cookie|flavor", "flavored coffee"),
        (r"pi[ñn]on", "flavored coffee"),
        (r"kona", "Kona coffee"), (r"hawaiian|ka[ʻ']?ū|kauai|peaberry", "Hawaiian coffee"), (r"robusta", "robusta coffee beans"),
        (r"espresso", "espresso coffee beans"),
        (r"ethiopia|yirgacheffe|guji|sidama", "Ethiopian coffee beans"), (r"colombia", "Colombian coffee beans"),
        (r"guatemala|huehuetenango", "Guatemalan coffee"), (r"sumatra", "Sumatra coffee"), (r"kenya", "Kenyan coffee beans"),
        (r"peru|per[uú]", "Peruvian coffee"), (r"rwanda|burundi", "African single origin coffee"),
        (r"geisha|gesha|microlot|micro lot", "specialty single origin coffee"),
        (r"dark|french|bold|black|night|deadman|death", "dark roast coffee beans"),
        (r"light", "light roast coffee beans"), (r"medium", "medium roast coffee beans"),
        (r"breakfast|morning", "breakfast blend coffee"), (r"organic", "organic coffee beans"),
        (r"single origin|honduras|nicaragua|costa rica|mexic|el salvador|brazil|papua|thailand|tanzania|bourbon|caturra|natural|honey", "single origin coffee beans"),
    ]
    for rx, ph in rules:
        if re.search(rx, t):
            if tea and "coffee" in ph: continue
            return (ph, ok)
    return ("loose leaf tea" if tea else "whole bean coffee", ok if not tea else 0)
