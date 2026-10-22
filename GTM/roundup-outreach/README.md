# Roundup outreach

**Goal:** get Produkto listed in the "best AI visibility tools" articles that AI already cites when buyers ask for tools. Our 856-answer data says AI reads other sites far more than brand sites, and that applies to Produkto too.

**The list:** `roundups.csv`, built by `python3 build_list.py` from every page cited in our weekly visibility readings (`produkto-site/aeo-case-study/results/`). Re-run it after each Monday reading: new cited roundups get added.

- **priority 1**: publishers, directories, agencies, independent writers. Best odds. Start here.
- **priority 2**: adjacent software blogs (Debutify, Trustmary, Elementor...) and Shopify's blog. Worth a try.
- **priority 3**: articles by companies that sell a competing tool. They rank themselves first; skip unless they already list several rivals.
- Each site's type was read from its own homepage, not guessed from the name. A new site shows as `UNCHECKED` until someone does the same.
- `status` and `notes` columns are for tracking: sent / replied / listed / declined.

## How to send

- **Not from kelian@getprodukto.com.** The rule is no cold email from that domain. Use one of the lookalike inboxes (tryprodukto.com etc.), the site's contact form, or a LinkedIn message to the author.
- One by one, by hand. These are editors, not a batch.
- Where a directory has a "submit a tool" form (agentvisibilitytools.com, ecommerceguide.com, fritz.ai), use the form instead of email.

## Pitch (edit the bracketed parts per article)

**Subject:** A product-level tool for your [article title] list

Hi [first name],

I read your [article title]. It's one of the pages ChatGPT and Perplexity cite when someone asks for AI visibility tools for ecommerce, which is how I found it.

I'm building Produkto. It measures every product in a Shopify catalog on the questions buyers ask, daily, in ChatGPT, Google AI Overviews and Perplexity, and shows the competing products AI picks instead. Plans start at $99 a month.

If it's useful for your readers, here's what's different, in one line: it covers the whole catalog at product level rather than a capped number of products or prompts.

We also published original data from 856 AI answers (how often AI names products at all, how much answers change between runs, which sites it reads): getprodukto.com/how-ai-recommends-products-856-answers. Happy for you to use any of it.

Descriptions, screenshots and logos: getprodukto.com/press

Glad to give you a free account to try it, or a 15-minute walkthrough.

Kelian
Founder, Produkto

## Notes

- Copy follows `skills/produkto-copy/SKILL.md`: no promised results, no knocking other tools, no "nobody does X".
- The "whole catalog vs capped" line is checkable: Glara's Starter tracks up to 20 products and its Advanced plan 50+ (glara.ai/pricing, checked 2026-10-20).

## Log

- **2026-10-20:** 9 LinkedIn connection requests sent from Kelian's account (see `linkedin-messages.csv`). Notes went to Matt Payne, Steve Merrill and Itamar Haim; the free plan allows 3 personalised notes a month and caps notes at 200 characters. The other 6 went without a note. Mostafa ElBermawy skipped: he works on Goodie, a competing tool. **Next:** when someone accepts, send them `message_after_accept` from the CSV (each is personalised), then mark the row.
- **2026-10-21:** press kit live at getprodukto.com/press (descriptions, facts, real-app screenshots of the fictional Scarnhill demo store, logos, data). Directory forms: agentvisibilitytools.com (free) and fritz.ai (contact form) filled, waiting for Kelian's OK. ecommerceguide.com charges $250 one-off to list a tool: not done, needs Kelian's OK.
