# stallwalk demo: 3-minute script and claim ledger

Lead angle (pending Kash's pick): walk a stock room, get a stock list and what's run out, then a priced restock order. The market price-card score is the second piece of evidence, and the "agents can buy it" export is the closer.

Credit, said on stage and shown on the last screen: **Inspired by Market Live, built by Team Nan at The Build Room Leicester 01.**

App: http://localhost:8787 (phone: the trycloudflare link from the stallwalk session). Blueprint on :8000 stays up and isn't restarted.

## Script

| Time | Beat | Say (roughly) | On screen | If the live call fails |
|---|---|---|---|---|
| 0:00 to 0:20 | Hook | "Someone in this building checks the kitchen every morning, by eye, then types up an order. We turned that walk into the order." | App home, phone in hand | Nothing live yet |
| 0:20 to 0:40 | Problem and who it's for | "Office and restaurant kitchen managers. The stock check is a walk, the order is a spreadsheet, and the prices are a guess." | Same | Nothing live |
| 0:40 to 1:20 | Live walk | Film the snack shelf or fridge for about 20 seconds. "Each frame goes to Nemotron Super VL on Nebius Token Factory. Code merges the frames into one list and marks what's low or empty." | **Walk live** panel, list filling in about every 1.4 s | Switch to the frozen office kitchen run, out/real-frozen-v3 (the 9 Fresha kitchen files), through the stock list view. Say "here's the same walk from earlier" |
| 1:20 to 1:50 | What's run out, with prices | "Here's what's low or empty, with a usual UK price. Nebius owns Tavily, so we use Tavily for the web checks: UK supermarket sites only, labelled as a web estimate, never written in as a price." | **Kitchen: restock and order** panel, **What's run out (office kitchen walk)**, then **...with web price estimates** (GET /api/restock?estimates=true) | The estimates come from the cache (out/pricecheck/cache.json), so no live search is needed. If the endpoint fails, show the restock table in experiments/KITCHEN.md |
| 1:50 to 2:10 | Ask, and split the order | Type "10kg potatoes, 2 dozen eggs" into **Split across markets**. "The model only reads the order. Code picks the cheapest stall in the same unit and does the maths, dozens included." | Order lines with stall, card price and line total: potatoes £9.00, eggs £5.60 | One Nemotron parse call. If it fails, show the KITCHEN.md order table (potatoes £9.00, eggs £5.60). Say the market lists are made up |
| 2:10 to 2:35 | Evidence | "Kash hand-checked it: on 3 kitchen photos, 47 of 49 listed were right, and it missed about 10 small snack packs. On 7 English market price-card photos, 29 of 30 items were right and 11 of 13 prices it read were right. It left a price blank rather than guess. And when a price is misread, the web check catches it." | experiments/RESULTS.md, then the Mussels £60/kg flag: **Check prices on the web** on the seeded run (out/pricecheck/seeded_v3.json) | All cached, no live call. Fall back to the PRICECHECK.md seeded table |
| 2:35 to 2:50 | Closer | "And the stock list is ready for AI shopping agents: one click turns it into ACP and UCP product records, and anything we're not sure of is marked not buyable." | **Make it buyable by AI agents** (GET /api/export) | Pure code, no live call. Fall back to experiments/PRICECHECK.md or export test output |
| 2:50 to 3:00 | Next and credit | "Next: read pack sizes off the shelf so the estimates tighten, and send the order to real suppliers. Inspired by Market Live, built by Team Nan at The Build Room Leicester 01." | Credit line on screen | |

Optional, only if the widget is up and there's time: ask the ElevenLabs voice agent "what's run out in the kitchen?" It answers from GET /api/agent/restock. Skip it if it hesitates.

### Backup

- Screenshots and a recording of every beat on the frozen runs: out/demo-backup/ (being made by token-extra).
- Every fallback above is a file or a cached result. None of them needs a live Token Factory or Tavily call.

## Claim ledger

Every number or claim said on stage, and what backs it. Hashes are stallwalk commits unless marked.

| Claim on stage | Backed by | Commit |
|---|---|---|
| Frames are read by Nemotron Super VL on Nebius Token Factory | stallwalk/tf.py (VISION_MODEL default nvidia/Nemotron-3.5-Super-VL), stallwalk/walk.py | 6f2c7b5 |
| Nemotron Super VL picked over GLM-5.3-Flash and gemma-3-27b-it, with the rule written before the run | experiments/AB.md (100% on synthetic, 3.8 s for 16 frames; GLM 16.2 s; gemma 7 of 16 timed out) | 52eabe3 (rule), f07605c (results) |
| Live walk adds a frame about every 1.4 s | Live walk mode commit message | 462a4c3 |
| Code merges frames and owns the list; disputed prices are flagged, never averaged | stallwalk/walk.py merge() | 6f2c7b5 |
| Low and empty items found per item | stock_level in walk.py; restock_list in kitchen.py | 8e83429, 84a14cc |
| Office kitchen: 47 of 49 listed were right on 3 photos, hand-checked by Kash | experiments/RESULTS.md, raw ticks in experiments/ticks-2026-11-24.json | da2be01, 28d9b60 |
| Both empty cereal dispensers caught (don't say it on stage yet) | being checked with Kash | [TBC] |
| Missed about 10 small snack packs | experiments/RESULTS.md | da2be01 |
| Price cards: 29 of 30 items right, 11 of 13 prices read right (7 English Commons photos) | experiments/RESULTS.md | da2be01 |
| Price card photos are Wikimedia Commons, with credits | 17-photo test set with CREDITS | 5035ad4 |
| "It leaves a price blank rather than guess" | FRAME_PROMPT "Never guess a price" in walk.py; RESULTS.md note on ½ lines | 6f2c7b5, da2be01 |
| Nebius owns Tavily | Event log, Tavily line (SEC 6-K, 19 Feb 2026, checked 24 Nov) | hackathonideas repo, event log |
| Web check uses UK supermarket sites only | GROCERS in stallwalk/pricecheck.py | 12ca03a |
| A web estimate is labelled and never becomes a price | ESTIMATE_LABEL, price_gbp untouched; tests/test_pricecheck.py | 88d0cd0 |
| A flag needs 2 or more web prices (no false flags in run 3) | MIN_QUOTES in pricecheck.py; PRICECHECK.md run 3 | 88d0cd0, 72d3151 |
| Mussels misread as £60/kg flagged "about 7x the usual UK price (£4.50 to £9.00 per kg)" with Tesco and Morrisons links | experiments/PRICECHECK.md seeded table; out/pricecheck/seeded_v3.json (gitignored); test_seeded_misread_flags_with_sources | 72d3151 |
| Restock estimates on the real kitchen footage: 5 of 7 low items got one, e.g. Cadbury Heroes £3.50 to £7.00 | experiments/KITCHEN.md restock table | 91ca0d9 |
| Order split: 10 kg potatoes £9.00, 2 dozen eggs £5.60, cheapest comparable stall | experiments/KITCHEN.md order table; kitchen.split_order; dozen fix checked live through the app at £5.60 | 91ca0d9, 5fd774f, b8bda30 |
| The model only parses the order; code picks and multiplies | kitchen.py docstring and split_order | 84a14cc |
| The market stock lists are made up | fixtures/markets/*.json (made_up: true) | 84a14cc |
| ACP and UCP records, shape from NVIDIA's Catalog Enrichment blueprint (Apache-2.0) | stallwalk/export.py | 4187bf3 |
| Unsure items are marked not buyable | export.py buyable rule; 15 of 16 synthetic items buyable (Cod held back) | 4187bf3, 0e25fb1 |
| Catalogue entry per item via the Catalog Enrichment blueprint on Token Factory models | app /api/enrich; event log (blueprint on :8000 with Super-VL) | 0f75997 |
| Voice agent answers from the app's tools | /api/agent/* endpoints; widget | b273226, e2a73c7 |
| Who it's for: office and restaurant kitchen managers; kitchens pay, shoppers don't | Event log pitch notes | [TBC] Kash's lead angle pick |
| Next: pack sizes off the shelf, orders to real suppliers | KITCHEN.md note on Coca-Cola spread | [TBC] Kash to confirm what's next |
| Numbers from any walk filmed live on the night | not logged yet, don't quote | [TBC] |
