# Launch film v3: asset list

Modelled on Promptwatch's "Agentic AI Search Optimization" launch video (youtube.com/watch?v=iBA_Ee10MmY, 70 s, light white background, one blue brand colour, soft blue glows, clean product UI, kinetic type). Every asset below is checked against its source before it goes in. Status: ✅ have it and checked · 🔍 need to fetch · ❓ needs Kelian.

## How Promptwatch's video is built (what we copy)
| # | Their shot | Ours |
|---|---|---|
| 1 | White screen, kinetic text: "In today's [AI logo] world." / "With AI…" | Same: "In today's [ChatGPT logo] world." / "Shoppers ask AI what to buy." |
| 2 | Search box with soft blue glow, question typed | "What are the best dog leashes for my dog golden retriever?" (Kelian's real capture, exact wording) |
| 3 | AI answer: rows with brand logo, name, price, stars. Their client greyed out | The 5 real answer rows with product photos and prices. Wild One's Lightweight Dog Leash greyed out as "not in the answer" |
| 4 | Full blue gradient: "Agentic AI Search Optimization" → logo | Blue gradient: "Catalog Optimization Agent" → Produkto logo |
| 5 | Big stat: "100,000,000+ data points every day" | A real Produkto number (see ❓4), or cut |
| 6 | The client's real website; agent writes pages; checklist ticks ("H1, H2, H3 titles structured") | wildone.com's real product page; the agent's fix ticks in: length up front, pull strength, swivel clip, FAQ |
| 7 | Their product UI: citations table | Produkto UI: Opportunities / citations view, designed mockup |
| 8 | Client now appears in the answer, "Cited 78×" callouts | ❓2: this implies the fix got them recommended, which is unproven |
| 9 | "Increase your sales", rising chart | ❓2: uplift claim, banned by our copy rules. Proposed: "Checked every day" + visibility trend |
| 10 | End card: logo, title, "Talk to an expert today", Trusted-by logo strip | Produkto logo, "Catalog Optimization Agent", **Book a demo**, getprodukto.com. Logo strip only with permission (❓3) |

## Brand assets
| Asset | Source | Status |
|---|---|---|
| Produkto mark (P icon) | `produkto-site/dist/assets/produkto-mark.png` (2000×2000) / `produkto-mark-rounded.png` | ✅ |
| Produkto wordmark | `produkto-site/dist/assets/produkto-wordmark-transparent.png` (2000×2000), `-light.png` (645×110) | ✅ check which one is the current lockup |
| Logo lockup used in film v1 | `launch-film/assets/logo.png` (632×338) | ✅ low-res, use the 2000 px files instead |
| ChatGPT logo (shot 1 and the answer header) | The inline SVG the dashboard already draws (commit 06f59b0) | 🔍 extract from the app |
| Produkto blue | The site's brand blue, from `produkto-site/dist/styles.css` | 🔍 |
| Font | Promptwatch uses a geometric grotesk; ours is Geist (site + app) | ✅ |

## Shot 3: the answer rows (must match Kelian's capture exactly)
Prices and labels come from the capture. **No star ratings:** ChatGPT didn't show any, so none get added.
| Row | Product as ChatGPT showed it | Photo needed | Status |
|---|---|---|---|
| 1 | Ruffwear Front Range Dog Leash With Padded Handle, **teal**, €26.95, "Best overall" | Ruffwear Shopify, teal variant of the Front Range leash | 🔍 |
| 2 | Ruffwear Crag Dog Leash Everyday Lead, **Rising Wave print** (yellow/teal), €40.95 | Ruffwear Shopify `crag-leash`, Rising Wave variant (not Crag EX) | 🔍 |
| 3 | Halti Multifunctional Lead (Anatomía), **black/grey with red logo**, €34.99 | halti.com product image, full resolution | 🔍 |
| 4 | Ruffwear Knot-a-Leash, **black** rope with grey carabiner, €44.95 | Ruffwear Shopify `knot-a-leash`, black variant (not pink) | 🔍 |
| 5 | Non-stop dogwear Touring Bungee, **teal** | non-stopdogwear.com (bot-blocked, use Firecrawl) | 🔍 |
| ✕ | Wild One Lightweight Dog Leash (not in the answer) | wildone.com, full product shown, not cropped | 🔍 re-fetch an uncropped studio shot |

## Shot 6: the client site and the fix
| Asset | Source | Status |
|---|---|---|
| wildone.com Lightweight Dog Leash product page | Full-page capture of the live page (desktop + mobile) | 🔍 |
| Fix content | Only facts from Wild One's own page: 6-foot, handles 90 lbs of pulling, swivel hook clip, Reflective Black option | ✅ checked 2026-10-20 |
| Agent checklist lines | Must be things the agent really does (`mvp/content-agent/PRODUCT-PAGE-RESEARCH-2026-10-19.md`): opening line, labelled lines, feature-then-benefit bullets, no prices | 🔍 write from the research file |

## Shot 7: Produkto UI
Designed mockup in Produkto's look, not a raw screenshot (memory rule 2026-10-13). Light or dark depends on ❓1.

## Sound
| Asset | Source | Status |
|---|---|---|
| Music | Current Mixkit track (free commercial licence), or a new one closer to Promptwatch's calm electronic feel | ❓5 |
| SFX | Mixkit clicks, pops, swooshes already in `assets/audio/` | ✅ |

## Questions for Kelian
1. **Light or dark?** Promptwatch's video is white with blue. Earlier you asked for dark mode. Copy their light look?
2. **The ending.** Their shots 8–9 show the client now cited and "Increase your sales". We can't claim that: no one has shown yet that fixes get products recommended more. Use "Checked every day" + the trend instead?
3. **Trusted-by strip.** Use only brands that agreed: Wild One, Stumptown? Or leave it out?
4. **Big stat.** Use a real number from the server, e.g. how many AI answers Produkto has read, or cut the shot?
5. **Music.** Keep the current track, or find a calmer one like theirs?
6. **Skincare and magnesium.** Promptwatch tells one story. Keep only the leash story, or flash the other two questions in shot 2?

## Decisions (Kelian, 2026-10-20)
- Light mode first. Leash story only.
- Ending: "Checked every day" + visibility trend line. No "now cited" or sales claims.
- No Trusted-by strip. Instead: "Tracked across multiple language models" with ChatGPT, Google (AI Overviews / AI Mode), Perplexity, Gemini, Copilot. **No Claude logo yet.**
- Big stat: "Hundreds of thousands of data points". Source: Kelian, a second database on Gabe's computer (the app server alone has 1,476 answers / 3,493 mentions).
- Agent name asset: `assets/v3/agent-label.svg`, the pricing page's sparkle + violet-to-blue gradient "Catalog Optimization Agent" (`dist/pricing.html:136`, `dist/styles.css:1432-1436`).
- Extra animation allowed: Produkto P spinning in 3D.
- All photos in the asset board are checked ✅ (`asset-board.png`).
