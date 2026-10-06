# 50 Shopify-brand founders to connect with on LinkedIn

**Built:** 9 September 2026
**Source files:** `founders-linkedin-2026-09-09.csv` (the 50), `bench-16-extra.csv` (16 more), `candidates.csv` (the 138-brand pool searched)

---

## How this was built, and what "verified" means here

1. **Brand pool (138):** the ICP-triaged brands already in this project — batch 5 (merino base layers + cycling apparel, prepped but never sent), the mineral-sunscreen niche (also never sent), the 21 `OK`-status brands from `prospecting/` with 150+ SKUs, and the 70 brands emailed in batches 2-4.
2. **Search:** 121 Google queries of the shape `site:linkedin.com/in "<Brand>" (founder OR "co-founder" OR CEO)`, run through Apify's Google SERP scraper (~$0.55 of Apify credit). 967 organic results.
3. **Acceptance rule — this is the important bit:** a person only made the list if the LinkedIn search result **itself** stated a founder/co-founder/owner role **at that brand**, and the role was **current**. The exact wording is in the `evidence_from_linkedin` column of the CSV.

**What was rejected and why** — so you know the list isn't padded:
- **Founders who have left.** Chris Birchby (COOLA, ended Feb 2024), Kevin Brodwick (Thinksport, exited 2020), Jaya Rao (Molekule, former CEO), Paul Tanswell (Sigr, ended Jan 2026), Outi Pulkkinen and Graham Stewart (Duckworth, both ended 2019), Derek Wiback (Eliel).
- **Right title, wrong company.** "Tower 28" returned two founders of a Santa Monica *ad agency* of the same name, not Tower 28 Beauty. "AirDoctor" returned an Israeli travel-health company. "Windmill" returned a Yext co-founder's unrelated venture. All dropped.
- **Real founders whose LinkedIn headline doesn't say so.** Amy Liu (Tower 28 Beauty), Shontay Lundy (Black Girl Sunscreen), Brian Guadagno (Raw Elements), Tony Post (Topo Athletic), Jim Winjum (Kenetrek). I know from other sources that they founded those brands, but their LinkedIn result doesn't state it, so they're not in the table. Say the word and I'll add them as a separate group.

**One caveat I can't remove:** these URLs come from Google's index of LinkedIn, not from LinkedIn itself. They're real profile URLs with matching titles and follower counts, but I haven't opened them logged-in. If any 404s when you click it, tell me and I'll re-run that one brand.

---

## The 50

Rows 1-39 are brands **nobody here has emailed**. Rows 40-50 are brands from batches 2-4 who got a cold email from you — a connection request there is a second touch on a warm-ish name, not a fresh approach. Sort however suits you.

| # | Name | Role | Brand | Category | LinkedIn | Emailed before |
|---|---|---|---|---|---|---|
| 1 | Alexandra Feechan | CEO & Founder | Findra | merino base layers | [profile](https://uk.linkedin.com/in/alexfeechanentrepreneur) | no |
| 2 | Dan English | Founder & CEO | Voormi | merino base layers | [profile](https://www.linkedin.com/in/dan-english-17700734) | no |
| 3 | Anthony Symonds | Co-founder | Le Bent | merino base layers | [profile](https://au.linkedin.com/in/anthonysymonds) | no |
| 4 | Simon Dawes Blondel | Co-Founder | Le Bent | merino base layers | [profile](https://it.linkedin.com/in/simon-dawes-blondel-9b574820) | no |
| 5 | Charlie Stewart | Co-Founder | Albion | cycling apparel | [profile](https://uk.linkedin.com/in/charlie-stewart-870a5185) | no |
| 6 | Rupert Hartley | Co-founder & Director | Albion | cycling apparel | [profile](https://uk.linkedin.com/in/rupert-hartley-448527116) | no |
| 7 | Remi Clermont | Founder & Director | Cafe du Cycliste | cycling apparel | [profile](https://fr.linkedin.com/in/remi-clermont-62524722) | no |
| 8 | Jose Ramon Ortin | Co-Founder & Co-CEO | Gobik | cycling apparel | [profile](https://es.linkedin.com/in/jos%C3%A9-ram%C3%B3n-ort%C3%ADn-4b146b64) | no |
| 9 | Alberto Garcia Cantero | Co-Founder | Gobik | cycling apparel | [profile](https://es.linkedin.com/in/alberto-garcia-cantero-743395140) | no |
| 10 | Martin Velits | Co-founder & CEO | Isadore | cycling apparel | [profile](https://sk.linkedin.com/in/martin-velits-818a6669) | no |
| 11 | Sam Calder | Founder & Managing Director | Rule 28 | cycling apparel | [profile](https://uk.linkedin.com/in/sam-calder-7ba885105) | no |
| 12 | Daniel Golden | Founder & Creative Director | Search and State | cycling apparel | [profile](https://www.linkedin.com/in/daniel-golden-b7b95419) | no |
| 13 | Hideto Suzuki | Founder | PEdALED | cycling apparel | [profile](https://it.linkedin.com/in/hideto-suzuki-719b37b1) | no |
| 14 | John Polson | Co-Founder / Managing Director | Black Sheep Cycling | cycling apparel | [profile](https://au.linkedin.com/in/john-polson-86622836) | no |
| 15 | Frank Kim | Owner & Executive Chair | Pactimo | cycling apparel | [profile](https://www.linkedin.com/in/frank-kim-328168a) | no |
| 16 | Nichole Powell | Founder & CEO | Kinfield | mineral sunscreen | [profile](https://www.linkedin.com/in/nicholepowell) | no |
| 17 | Dakota Green | Founding Partner | Vacation | mineral sunscreen | [profile](https://www.linkedin.com/in/dktgrn) | no |
| 18 | Marty Bell | Co-Founder | Vacation | mineral sunscreen | [profile](https://ky.linkedin.com/in/martyy) | no |
| 19 | Autumn Blum | Founder | Stream2Sea | mineral sunscreen | [profile](https://www.linkedin.com/in/autumn-blum-3b30629) | no |
| 20 | Tricia Trimble | Founder | Suntegrity | mineral sunscreen | [profile](https://www.linkedin.com/in/triciatrimble) | no |
| 21 | Kate Solomon | Founder | Babo Botanicals | mineral sunscreen | [profile](https://www.linkedin.com/in/kate-solomon-45213314) | no |
| 22 | Thomas Hiney | Co-founder & COO | SunButter Skincare | mineral sunscreen | [profile](https://au.linkedin.com/in/thomas-hiney-997535b0) | no |
| 23 | Priscilla Tsai | Founder & CEO | Cocokind | skincare | [profile](https://www.linkedin.com/in/priscilla-tsai-58564015) | no |
| 24 | Ava Chandler-Matthews | Co-Founder | Ultra Violette | SPF skincare | [profile](https://au.linkedin.com/in/ava-chandler-matthews-29132228) | no |
| 25 | Rebecca Jefferd | Co-Founder | Ultra Violette | SPF skincare | [profile](https://au.linkedin.com/in/rebecca-jefferd-46283b2b) | no |
| 26 | Samantha Brett | Founder | Naked Sundays | SPF skincare | [profile](https://au.linkedin.com/in/samanthabrett) | no |
| 27 | Ann McFerran | Founder & CEO | Glamnetic | beauty | [profile](https://www.linkedin.com/in/ann-mcferran-755b4534) | no |
| 28 | Alex Cannon | Founder & Creative Director | CRAFTD London | jewellery | [profile](https://uk.linkedin.com/in/alex-cannon-997a5aa7) | no |
| 29 | Olajuwon Ajanaku | Founder & Creative Director | Eastside Golf | golf apparel | [profile](https://www.linkedin.com/in/olajuwon-ajanaku-5011811a) | no |
| 30 | Jazzi McGilbert | Founder & CEO | Reparations Club | books & goods | [profile](https://www.linkedin.com/in/jazzimcg) | no |
| 31 | Jonathan Grahm | Founder & CEO | Compartes | chocolate | [profile](https://www.linkedin.com/in/jonathan-grahm-110150a) | no |
| 32 | Rima Vaidila | Co-Founder & CEO | Goldie Swimwear | swimwear | [profile](https://www.linkedin.com/in/rima-vaidila-86532667) | no |
| 33 | Adria Vaidila | Co-Founder & CCO | Goldie Swimwear | swimwear | [profile](https://www.linkedin.com/in/adria-vaidila-189348135) | no |
| 34 | Sam Assaf | Founder & CEO | L'Intervalle | footwear | [profile](https://ca.linkedin.com/in/sam-assaf-2898727a) | no |
| 35 | Vita (Vicky) Scalia | Co-Founder & Co-CEO | L'Intervalle | footwear | [profile](https://ca.linkedin.com/in/vita-vicky-scalia-emba-b5412916a) | no |
| 36 | Kimberley Gordon | Founder | Selkie | fashion | [profile](https://www.linkedin.com/in/kimberley-gordon-b4b26394) | no |
| 37 | Emma Sibley | Founder | London Terrariums | plants | [profile](https://uk.linkedin.com/in/emma-sibley-24924267) | no |
| 38 | Amy Denet Deal | Owner & Creative Director | 4Kinship | apparel | [profile](https://www.linkedin.com/in/amyyeung) | no |
| 39 | Douglas Watters | Founder | Spirited Away NYC | non-alcoholic drinks | [profile](https://www.linkedin.com/in/douglaswatters) | no |
| 40 | Mike Feldstein | Founder | Jaspr | air purifiers | [profile](https://www.linkedin.com/in/mike-feldstein-0512342b) | yes (batch 3) |
| 41 | Moe Barani | Co-founder & CTO | Oransi | air purifiers | [profile](https://www.linkedin.com/in/moe-barani-33156818b) | yes (batch 3) |
| 42 | H Pedro | Co-Founder & President | Airpura | air purifiers | [profile](https://ca.linkedin.com/in/h-pedro-760a4324) | yes (batch 3) |
| 43 | Jeff Bennert | Co-Owner & COO | Air Oasis | air purifiers | [profile](https://www.linkedin.com/in/jeff-bennert-84149616) | yes (batch 3) |
| 44 | Lauren Picasso | Founder & CEO | Cure Hydration | electrolytes | [profile](https://www.linkedin.com/in/laurenpicasso) | yes (batch 2) |
| 45 | Mike Xhaxho | Co-Founder & CEO | Waterboy | electrolytes | [profile](https://www.linkedin.com/in/mikexhaxho) | yes (batch 2) |
| 46 | Connor Saeli | Co-founder | Waterboy | electrolytes | [profile](https://www.linkedin.com/in/connorsaeli) | yes (batch 2) |
| 47 | John Sherwin | Co-Founder | Hydrant | electrolytes | [profile](https://www.linkedin.com/in/johnfsherwin) | yes (batch 2) |
| 48 | Brandon Smith | Co-Founder | NOOMA | sports drinks | [profile](https://www.linkedin.com/in/brandon-smith-97a08259) | yes (batch 2) |
| 49 | Jenny Vierling | Co-Founder | Tailwind Nutrition | sports nutrition | [profile](https://www.linkedin.com/in/jennyvierling) | yes (batch 2) |
| 50 | Daniel Schaefer | Co-Founder | Native Pet | dog supplements | [profile](https://www.linkedin.com/in/danielcschaefer) | yes (batch 2) |

---

## 16 more, if you want to go past 50

All founders/co-founders, all from brands already emailed in batches 2-4.

| # | Name | Role | Brand | Category | LinkedIn | Emailed before |
|---|---|---|---|---|---|---|
| 51 | Pat Barron | Co-Founder | Native Pet | dog supplements | [profile](https://www.linkedin.com/in/pat-barron-85739b28) | yes (batch 2) |
| 52 | Benjamin Arneberg | Founder | PetHonesty | dog supplements | [profile](https://www.linkedin.com/in/benjaminarneberg) | yes (batch 2) |
| 53 | Camille Arneberg | Co-Founder | PetHonesty | dog supplements | [profile](https://www.linkedin.com/in/camilleszramiak) | yes (batch 2) |
| 54 | Josh Savinson | Founder | Wuffes | dog supplements | [profile](https://uk.linkedin.com/in/josh-savinson-b3333922) | yes (batch 2) |
| 55 | T Madden Alford | Co-Founder | Honest Paws | dog supplements | [profile](https://www.linkedin.com/in/t-madden-alford-8281b04) | yes (batch 2) |
| 56 | Andrea Tovar | Founder | Bocce's Bakery | dog treats | [profile](https://www.linkedin.com/in/andrea-maria-tovar987) | yes (batch 2) |
| 57 | Sean Lake | Co-Founder & CEO | BUBS Naturals | collagen | [profile](https://www.linkedin.com/in/sean-lake-4578596) | yes (batch 3) |
| 58 | Ronak Shah | Co-Founder | Obvi | collagen | [profile](https://www.linkedin.com/in/ronak06) | yes (batch 3) |
| 59 | Augustin Quancard | Founder | Codeage | supplements | [profile](https://www.linkedin.com/in/augustinquancard) | yes (batch 3) |
| 60 | Matt Kilts | Founding CEO & Chairman | Trace Minerals | supplements | [profile](https://www.linkedin.com/in/matt-kilts-48aa3053) | yes (batch 2) |
| 61 | Alexandria Best | Co-Founder & COO | Swolverine | supplements | [profile](https://www.linkedin.com/in/alexandriabest) | yes (batch 2) |
| 62 | Brian Littlefield | Co-Founder & CPO | Jocko Fuel | supplements | [profile](https://www.linkedin.com/in/brian-littlefield-52933450) | yes (batch 3) |
| 63 | Mike McAdams | Co-Founder & CEO | LyteLine | electrolytes | [profile](https://www.linkedin.com/in/mcadamsmike) | yes (batch 2) |
| 64 | Jim Wirth | Founder & CEO | GiantMouse Knives | EDC knives | [profile](https://www.linkedin.com/in/jimwirth) | yes (batch 4) |
| 65 | Stuart Hutchins | Co-Founder & Owner | Kenetrek Boots | hiking boots | [profile](https://www.linkedin.com/in/stuarthutchinscrc) | yes (batch 4) |
| 66 | John Schweizer | Founder & CEO | Garmont NA | hiking boots | [profile](https://www.linkedin.com/in/john-schweizer-9553a54) | yes (batch 4) |

---

## Notes worth having before you send requests

- **Non-US founders are over-represented on purpose**: Gobik (Spain), Isadore (Slovakia), Cafe du Cycliste (France), Le Bent (Australia), Ultra Violette / Naked Sundays / SunButter (Australia), Findra / Albion / Rule 28 / CRAFTD (UK), L'Intervalle / Airpura (Canada). Given you're in Barcelona, the European ones are the easiest to turn into a real conversation.
- **Two brands have both co-founders listed** (Le Bent, Albion, Gobik, Vacation, Ultra Violette, Goldie, L'Intervalle, Waterboy, Native Pet). Connect with one first; the second is a fallback if the first goes quiet.
- **Acquired brands, flagged so you don't misread the reply:** Babo Botanicals (Laboratoires Expanscience), Bocce's Bakery (Antelope), Selkie. The founder is still on the profile but may not control the catalog.
- **These are connection targets, not a send list.** No message copy here — that's the `linkedin-growth` skill's job when you're ready.
