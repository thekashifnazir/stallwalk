# stallwalk demo: 3-minute script and claim ledger

Main flow: the **meal demo**, voice-led. A chef says what they want to cook, the agent checks the stockroom, buys only what's low or out from the walked market, and finds the rest online. The market price-card score is the evidence beat, and the "agents can buy it" export is the closer. The stock room walk flow is kept below as the fallback.

All meal demo data is **made up** (fixtures/demo/stockroom.json and fixtures/demo/meal_market.json). Say so once, at the start.

Credit, said on stage and shown on the last screen: **Inspired by Market Live, built by Team Nan at The Build Room Leicester 01.**

App: http://localhost:8787 (phone: the trycloudflare link from the stallwalk session). Blueprint on :8000 stays up and isn't restarted. Voice agent: agent_1801m87addxwfmfbaqw8kzj48qkj. Its first message: "Hi, I've walked the market. Tell me what you'd like to cook, or ask what's on the stalls."

## Script: meal demo (main)

| Time | Beat | Say (roughly) | On screen | If the voice step fails |
|---|---|---|---|---|
| 0:00 to 0:15 | Hook | "A chef decides the menu at 4pm. Then someone checks the stockroom, walks the market and phones round for the rest. We do that in one conversation. Tonight's stockroom and market are made up for the demo." | App home with the voice widget | Nothing live yet |
| 0:15 to 0:30 | Who it's for | "Restaurant and office kitchen managers. Kitchens pay; nobody wants to send a chef round three markets at 4am." | Same | Nothing live |
| 0:30 to 0:50 | Ask | Say to the agent: "I want to make moules frites tonight." It lists the ingredients: mussels, potatoes, shallots, garlic, parsley, white wine, butter. | ElevenLabs widget, agent speaking | Read the list out yourself and carry on in the browser |
| 0:50 to 1:10 | Check the stockroom | The agent calls check_stockroom and says what's low or out, so we only buy the gaps. | Widget; tool hits GET /api/agent/stockroom | Open http://localhost:8787/api/agent/stockroom?items=mussels,potatoes,shallots,garlic,parsley,white%20wine,butter in the browser, or the backup frame for this step in out/demo-backup/ |
| 1:10 to 1:40 | Buy from the market | The agent calls split_order on the 6-stall market. "Mussels 2 kg, £12.00. Potatoes 1 kg, 90p. Shallots 200 g, 48p. Garlic 50p. Parsley 80p. Market total £14.68." "Code picks the stall and does the maths, grams to kilos included. The model never says a price the code didn't give it." | Widget; tool hits GET /api/agent/order | Open http://localhost:8787/api/agent/order?order=2kg%20mussels,%201kg%20potatoes,%20200g%20shallots,%20garlic,%20parsley,%20white%20wine,%20butter in the browser, or the backup frame. Totals are in the ledger below |
| 1:40 to 2:00 | Not on the market today | "White wine and butter aren't on the market today, so it checks online UK supermarket prices. Nebius owns Tavily, so we use Tavily for the web checks." The agent says "web estimate, online price" and "check your local store". | Widget; tool hits GET /api/agent/web_find. Numbers: [TBC live] | Open http://localhost:8787/api/agent/web_find?items=white%20wine,butter in the browser (cached after the first run), or the backup frame. Don't claim any shop near here |
| 2:00 to 2:30 | Evidence | "How did the market get read? Kash hand-checked it. Kitchen: 46 of 49 listed were right on 3 photos, missed about 10 small snack packs; caught the one empty dispenser but listed it twice. On 7 English market price-card photos, 29 of 30 items were right and 11 of 13 prices it read were right. It left a price blank rather than guess. And when a price is misread, the web check catches it." | experiments/RESULTS.md, then the Mussels £60/kg flag: **Check prices on the web** on the seeded run (out/pricecheck/seeded_v3.json), backup frame 09 in out/demo-backup/ | All cached, no live call. Fall back to the PRICECHECK.md seeded table |
| 2:30 to 2:45 | Closer | "And the stock list is ready for AI shopping agents: one click turns it into ACP and UCP product records, and anything we're not sure of is marked not buyable." | **Make it buyable by AI agents** (GET /api/export) | Pure code, no live call. Fall back to the export test output |
| 2:45 to 3:00 | Next and credit | "Next: real stall walks feeding the market every morning, and the order sent to the stalls. Inspired by Market Live, built by Team Nan at The Build Room Leicester 01." | Credit line on screen | |

The live calls on stage are the voice conversation (ElevenLabs plus the app's tool endpoints through the tunnel) and, the first time only, the web_find search. Every other beat is a file, a fixture or a cached result.

## Fallback flow: stock room walk

Use this if the voice agent won't start. Same evidence and closer.

| Time | Beat | Say (roughly) | On screen | If the live call fails |
|---|---|---|---|---|
| 0:00 to 0:20 | Hook | "Someone in this building checks the kitchen every morning, by eye, then types up an order. We turned that walk into the order." | App home | Nothing live yet |
| 0:20 to 0:40 | Problem and who it's for | "Office and restaurant kitchen managers. The stock check is a walk, the order is a spreadsheet, and the prices are a guess." | Same | Nothing live |
| 0:40 to 1:10 | Replay of footage filmed tonight | "We filmed the kitchen downstairs at 16:53. Here it is going through the app. Each frame went to Nemotron Super VL on Nebius Token Factory, and code merged the frames into one list and marked what's low or empty." | The recorded kitchen footage replayed through the app: the stock list for out/real-frozen-v3 (the 9 Fresha kitchen files) | Not live, so nothing to fail. If the app won't load, show the stock list screenshots in out/demo-backup/ |
| 1:10 to 1:35 | What's run out, with prices | "Here's what's low or empty, with a usual UK price. Nebius owns Tavily, so we use Tavily for the web checks: UK supermarket sites only, labelled as a web estimate, never written in as a price." | **Kitchen: restock and order** panel, **What's run out (office kitchen walk)**, then **...with web price estimates** (GET /api/restock?estimates=true) | The estimates come from the cache (out/pricecheck/cache.json), so no live search is needed. If the endpoint fails, show the restock table in experiments/KITCHEN.md |
| 1:35 to 1:55 | Ask, and split the order | Type "10kg potatoes, 2 dozen eggs" into **Split across markets**. "The model only reads the order. Code picks the cheapest stall in the same unit and does the maths, dozens included." | Order lines with stall, card price and line total: potatoes £9.00, eggs £5.60 | One Nemotron parse call. If it fails, show the KITCHEN.md order table (potatoes £9.00, eggs £5.60). Say the market lists are made up |
| 1:55 to 2:20 | Evidence | "Kash hand-checked it. Kitchen: 46 of 49 listed were right on 3 photos, missed about 10 small snack packs; caught the one empty dispenser but listed it twice. On 7 English market price-card photos, 29 of 30 items were right and 11 of 13 prices it read were right. It left a price blank rather than guess. And when a price is misread, the web check catches it." | experiments/RESULTS.md, then the Mussels £60/kg flag: **Check prices on the web** on the seeded run (out/pricecheck/seeded_v3.json), backup frame 09 in out/demo-backup/ | All cached, no live call. Fall back to the PRICECHECK.md seeded table |
| 2:20 to 2:35 | Voice | Ask the ElevenLabs agent out loud: "What's run out in the kitchen?" "It always calls the app for the answer, so it can't make a price up, and it says web estimate when that's all there is." | ElevenLabs widget on the page (agent agent_1801m87addxwfmfbaqw8kzj48qkj); its whats_run_out tool calls GET /api/agent/restock on the same kitchen run as the replay | One live call through the tunnel. If it hesitates or the webhook fails, show frame 12 in out/demo-backup/ (the agent restock tool output) and move on |
| 2:35 to 2:50 | Closer | "And the stock list is ready for AI shopping agents: one click turns it into ACP and UCP product records, and anything we're not sure of is marked not buyable." | **Make it buyable by AI agents** (GET /api/export) | Pure code, no live call. Fall back to experiments/PRICECHECK.md or export test output |
| 2:50 to 3:00 | Next and credit | "Next: read pack sizes off the shelf so the estimates tighten, and send the order to real suppliers. Inspired by Market Live, built by Team Nan at The Build Room Leicester 01." | Credit line on screen | |

### Backup

- Screenshots and a recording of every beat on the frozen runs: out/demo-backup/ (being made by token-extra).
- Every fallback above is a file or a cached result. None of them needs a live Token Factory or Tavily call. The live calls on stage are the order parse and the voice ask.

## Claim ledger

Every number or claim said on stage, and what backs it. Hashes are stallwalk commits unless marked.

| Claim on stage | Backed by | Commit |
|---|---|---|
| Meal demo data is made up | fixtures/demo/meal_market.json and fixtures/demo/stockroom.json (made_up: true) | 01e2873 |
| Agent first message and meal flow: stockroom first, buy only the gaps, web find for what the market lacks | voice setup prompt and tools (check_stockroom, web_find) | ab37e57 |
| Stockroom check says have, low or out per ingredient | GET /api/agent/stockroom on fixtures/demo/stockroom.json | 01e2873, ab37e57 |
| Market lines: mussels 2 kg £12.00, potatoes 1 kg £0.90, shallots 200 g £0.48, garlic £0.50, parsley £0.80, market total £14.68 (made-up prices) | kitchen.split_order on fixtures/demo/meal_market.json (mussels £6/kg at Billy's Fresh Fish; potatoes 90p/kg, shallots £2.40/kg, garlic 50p a bulb, parsley 80p bunch at Green's Veg); re-run offline from the fixture with the same lines, sum £14.68 | 01e2873, c41a587, 8f44b28 |
| Shallots 200 g priced from a per-kg card (g to kg conversion) | kitchen.py g/kg and ml/litre conversion | c41a587 |
| White wine and butter "not on the market today" (left out of the fixture on purpose, and the lines still come back unmatched) | meal_market.json note; kitchen.py keeps every ordered item as a line | 01e2873, c41a587 |
| White wine and butter online prices, labelled "web estimate, online price" and "check your local store", no location claims | stallwalk/webfind.py via GET /api/agent/web_find (2-quote rule, spread check, 20-search cap) | b0321f2, 8f44b28; numbers [TBC live] |
| Frames are read by Nemotron Super VL on Nebius Token Factory | stallwalk/tf.py (VISION_MODEL default nvidia/Nemotron-3.5-Super-VL), stallwalk/walk.py | 6f2c7b5 |
| Nemotron Super VL picked over GLM-5.3-Flash and gemma-3-27b-it, with the rule written before the run | experiments/AB.md (100% on synthetic, 3.8 s for 16 frames; GLM 16.2 s; gemma 7 of 16 timed out) | 52eabe3 (rule), f07605c (results) |
| The kitchen footage was filmed tonight, downstairs, at 16:53, and replayed on stage (not live) | out/real-frozen-v3 file names (20261124_165350 to 165526) | [TBC] frozen-run commit, out/ is gitignored |
| Code merges frames and owns the list; disputed prices are flagged, never averaged | stallwalk/walk.py merge() | 6f2c7b5 |
| Low and empty items found per item | stock_level in walk.py; restock_list in kitchen.py | 8e83429, 84a14cc |
| Office kitchen: 46 of 49 listed were right on 3 photos, missed about 10 small snack packs; caught the one empty dispenser but listed it twice (hand-checked by Kash) | experiments/RESULTS.md, raw ticks in experiments/ticks-2026-11-24.json | 834702a, 28d9b60 |
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
| Voice agent answers from the app's tools, so it can't make a price up | voice/agent.json (agent_1801m87addxwfmfbaqw8kzj48qkj, 2 text tests passed); /api/agent/restock reads the kitchen folder (real-frozen-v3); /api/agent/find and /stalls default to the synthetic_walk market run (env STALLWALK_AGENT_RUN), not the loaded run. **The webhook is unverified until one spoken test** | 939fd94, b273226, e2a73c7 |
| Spoken on the voice beat: "Restock about £9.60: one each of Corn flakes and Cadbury Heroes, the middle of UK supermarket web prices." **Web estimate, not a card price** | £9.60 = £4.35 corn flakes (1 tesco.com quote) + £5.25 Cadbury Heroes (midpoint of £3.50 to £7.00, 5 quotes, Tesco/Asda), per experiments/KITCHEN.md restock table; per-weight prices (crisps, Reese's per 100g) left out | 5aee2c0, 67edefa, 91ca0d9 |
| Who it's for: office and restaurant kitchen managers; kitchens pay, shoppers don't | Event log pitch notes | [TBC] Kash's lead angle pick |
| Next: pack sizes off the shelf, orders to real suppliers | KITCHEN.md note on Coca-Cola spread | [TBC] Kash to confirm what's next |
