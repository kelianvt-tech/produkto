# Launch film reference: Algosoup (2026-10-20)

Source: Algosoup's LinkedIn launch post (lnkd.in/p/en9jTDK4). Video, contact sheet and key frames saved in `reference/`.

## What the video is

- **13 seconds, 1280×720, no voice, no music track.** Only sound design.
- **About 20 cuts**, one every 0.5–1 s. Nothing moves smoothly; frames *switch*.
- **One typeface:** a monospace (IBM Plex Mono style), used for everything from the logo to tiny log lines.
- **Palette:** near-black (#111) and warm off-white (#f2f1ee), flipping between the two. Greys in between. One accent, a muted gold, used once (the "Data" globe).
- **Texture instead of illustration:** halftone dot gradients, ASCII art (globe, rings, logo built from characters), a wall of the brand name repeated, terminal output.

## Shot list (seconds)

| Time | Shot | Background |
|---|---|---|
| 0.0 | Logo `{algosoup}` + tiny tagline "ship in pod-time" | black |
| 0.5 | Halftone dot sphere wipes across | light |
| 1.0 | Pixelated diamond-star mark | light |
| 1.5 | Terminal: `algosoup init` … "pod ready. ship in pod-time." | black |
| 2.0 | Full-screen wall of `{algosoup}` repeated | black |
| 2.5 | `{a}` mark drawn in ASCII | black |
| 3.0 | Manifesto, small text: "you are a pod. pods ship." | black |
| 3.5 | Big word **Infrastructure**, terminal noise round it | light |
| 4.0 | Jagged ASCII waveform | black |
| 4.5 | `algosoup.ai▌` with blinking cursor | black |
| 5.0 | Big word **Data**, gold ASCII globe, live metrics, progress bar 40% | black |
| 6.0 | Big word **Intelligence**, pipeline readouts, progress bar 30% | light |
| 6.5–10.0 | Logo loop: halftone → star → logo → `{a}` → ring → star → halftone → ASCII rings | alternating |
| 10.5 | Logo + tagline | black |
| 11.0 | "Ship your vision" over `{algosoup}`, ASCII globe faint behind | black |
| 12.0 | `algosoup.ai▌` cursor blinking, fade out | black |

## The sound (measured)

- A **sub drone around 45 Hz** under the whole thing, swelling and receding in waves roughly every 3.5 s. That's the "cold" feeling.
- **Fine digital ticks/clicks** on top, like a machine working.
- **Risers into hits:** pitch climbs (≈4.0→4.7 s) then a low boom. Hits at **2.9, 4.8, 8.3, 10.0, 11.0 s**, each landing on a cut to a big word or the logo.
- Last 2 s: drone decays to silence under the URL.

## Why it feels like a big deal while being simple

1. **Restraint.** Two colours, one font, no stock footage, no product UI, no voice. Nothing to look cheap.
2. **Sound carries the scale.** The sub and the hits make each word feel like an event.
3. **Three nouns, not features.** Infrastructure / Data / Intelligence: big claims, no explanation.
4. **Speed.** Hard cuts every half second; the eye never gets to inspect anything.
5. **"System booting" fiction.** Terminal logs and progress bars imply something powerful coming online, without showing what.

## Produkto version (draft for Kelian to react to)

Same skeleton, ~14 s, dark-first, mono type. Fits our standing rules: real brands only, "AI" not "ChatGPT" in the hook, supplied logo lockup (`assets/logo.png`), the particle dot P (`p-mark.js`) on the end card, no 3D spinning icon, no question/run counts.

| Time | Produkto shot |
|---|---|
| 0.0 | Logo lockup on black, cursor |
| 0.5 | Dot P (`p-mark.js` dots) assembling out of halftone noise |
| 1.5 | Terminal: `produkto scan` … "reading catalog… asking AI… " |
| 2.0 | Wall of real buyer questions repeated ("best leash for a golden retriever"…) |
| 2.5 | P drawn in ASCII |
| 3.0 | Small text: **"Is AI recommending your products?"** (approved hook) |
| 3.5 | Big word **Visibility** (light), product names flickering in the margins |
| 4.0 | ASCII trend line rising |
| 4.5 | `getprodukto.com▌` |
| 5.0 | Big word **Opportunities** (dark), one accent colour, readout of real answer: Ruffwear Crag, Halti, Non-stop dogwear… |
| 6.0 | Big word **Optimization** (light), agent log lines ("drafting product page fix… approved… live") |
| 6.5–10 | Mark loop: dot P ↔ ASCII P ↔ halftone, on the hits |
| 10.5 | Logo lockup + tagline (to choose) |
| 12.0 | `getprodukto.com▌`, drone fades |

Accent colour: Algosoup's gold, or our logo navy brightened to read on black. One accent, used once.

Open choices: the three words (Visibility / Opportunities / Optimization is a draft), and the end tagline.

## Production method

This look is mostly typography, ASCII and dots, which is closer to what code renders well than the UI-mockup films that were scrapped. Still: per the 2026-10-20 rule, **make a 5-second test (logo → terminal → one big word, with sound) and get a yes before building the rest.** Sound: a sub drone, a riser and an impact from free libraries (Pixabay / Freesound, no cost), mixed with the existing `mix*.py` approach.
