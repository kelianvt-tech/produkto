# Produkto launch film — adapted prompt

Adapted 2026-09-27 from a launch-film prompt shared on Twitter (originally for a photo-printing product). Style, build and gotchas kept as-is; inputs and story rewritten for Produkto.

<inputs>
Ask me for:
- Wordmark: **Produkto** (fixed — the brand name, not a verb).
- 9 to 12 high-res product photos from ONE catalog, all shot on a plain background so they sit well in a bento grid. Must be either a fictional catalog, or a real brand that has given permission. Never M&O Living.
- One real ChatGPT answer, captured by hand: the exact buyer question, the answer text, the date. Nothing invented goes on the ChatGPT screen.
- A royalty-free song around 120 BPM with a drop and a quiet breakdown (Mixkit, free for commercial use).
- A free stock clip of a desk or sofa with soft moving window light, no people (Pexels) — the ambient backdrop for the phone in the breakdown.
</inputs>

<direction>
An Apple-keynote launch film, 2D only, one continuous take. Every scene is made out of the previous one: nothing fades, blurs or cuts. Objects change shape instead: text rises out of a mask line, icons pop from zero on a spring, bars and chart lines draw across, pages push, and a navy shape floods the whole frame and contracts into the next scene. Warm off-white canvas, logo navy (#0b1b35) UI, iOS 26 liquid glass over the product photos. Archivo (wdth 125, weight 800) for the wordmark, Geist for UI. A cursor drives every change with real clicks, drags, typing and long-presses. The camera zooms screen-studio style so each moment fills the square, and the cursor scales with it.
Story in one line: a shopper asks ChatGPT → a store's catalog is scanned → the merchant sees, per product, how often ChatGPT recommends it.
Banned: crossfades, blur-ins, brightness "developing", 3D flips, particles, glows, holds longer than 1s, anything that looks like a template. Also banned: invented brands or products inside a ChatGPT answer, a stated number of questions or runs per scan, and any uplift claim ("get recommended more", a line shooting up after "fixes").
</direction>

<structure>
120 BPM, 54 beats, something happens on every beat.

Open: the wordmark "Produkto" squeezes into its own period like an accordion, the dot grows into a navy pill, a label rises inside it: "Is ChatGPT recommending your products?". Click: six iris blades close over the label and snap open onto one product photo. The circle becomes a square, shrinks, and the catalog grid unfolds from behind it like a paper map (center, plus, corners), reflows into a bento, and a click zooms into one tile, landing exactly on the drop.

Ask: a glass word "Ask" pops in letter by letter, melts into a droplet that stretches into a glass ChatGPT prompt bar. The cursor types the captured buyer question. Enter: the answer streams in as glass cards, one recommended product per card, taken verbatim from the real capture. The zoomed product tile is not among them — its tile dims to an outline beside the stack. The outline lifts into a glass orb.

Scan: the orb drops onto a glass URL bar; the cursor pastes a store URL, and the orb expands into the Produkto catalog screen — the bento re-forms as a product grid. One navy shape keeps morphing: Reading catalog ✓ → Asking buyer questions % → Reading answers % → Scan complete ✓.

Dashboard: the ✓ circle stretches into the KPI strip — Visibility, Average position, Share of voice, Competing products — each number counts up from zero. The strip's bottom edge pulls down into the visibility chart; its first point springs in with a dashed "not measured" lead-in, then the line draws across the weeks as further scans land (keep it flat/mixed, not a hockey stick). Click a product row: the page pushes into the product view, the product photo sits beside "Mentioned in X% of answers" and "Position vs competitors" bars drawing across, each bar wearing its brand logo.

Phone: the product view pulls back into a phone (the bezel grows out of the screen edge). The Dynamic Island stretches like liquid, pinches off and grows into the ChatGPT prompt bar again — the same question, asked on a phone.

Breakdown: the send button floods the frame navy edge to edge, holds for a beat, and contracts into the phone lying on the real desk footage, the answer on screen. The same iris opens onto the product tile, closes again, the frame floods navy and contracts into the pill → the dot → the letters spring back out, landing on the beat return. Last frame = first frame. Optional tagline rising under the wordmark on the last beat: "See where your products stand in AI answers."
</structure>

<build>
1. One HTML file, square 1440x1440. Every style is computed from time inside an async seek(t): no CSS transitions, no timers, no state between frames.
2. Springs are closed-form step responses. A value with many targets is the sum of one spring per change, so it stays a pure function of time.
3. Liquid glass: each glass element holds its own clone of the scene behind it, filtered with an SVG feImage displacement map (a rounded-rect distance field) through three feDisplacementMaps at slightly different scales for chromatic edges, plus a rim light. Glass letters: a canvas distance field per glyph gives the map, mask and highlights.
4. Goo: blur + alpha threshold, then composite the source atop it so the glass stays sharp inside.
5. Iris: 6 blades around a hexagonal aperture. Each blade is its two vertices, both edge extensions and the SHORT arc between them.
6. Wordmark squeeze: every letter moves toward the dot by the same factor and its drawn width follows (narrow the wdth axis, scale the rest), so the letters stay touching.
7. Footage: re-encode all-intra (ffmpeg -g 1), load it as a blob URL, await 'seeked' before drawing each frame.
8. Sound: a downloaded SFX for every event (Mixkit), never synthesized, each placed by its measured peak. Typing gets real key clicks. The song starts on a downbeat: the zoom lands on the drop, the phone-on-desk sits in the breakdown, the wordmark returns with the beat. Loudnorm to -14 LUFS.
9. Render with Playwright: 4 subframes per frame blended with ffmpeg tmix, 60fps. Check one frame per beat, then scan for single-frame pops (frame-difference spikes 3x their neighbours).
10. Dashboard numbers and chart shapes are illustrative unless taken from a real scan of the catalog in the film; label nothing as a real result that isn't.
</build>

<gotchas>
backdrop-filter: url() misreads displacement maps in Chromium, so clone the scene instead. A flood must overscale past the corners and take about 0.3s, or half the screen changes in one frame. A child with visibility: visible shows through a hidden parent, so use inherit. Text that swaps inside a morphing shape needs its own mask. python http.server can't range-seek video, so use the blob URL.
</gotchas>

<start>
Ask me for the inputs, then show me the beat map and 4 stills (open, ask, dashboard, breakdown) before you write the full film.
</start>
