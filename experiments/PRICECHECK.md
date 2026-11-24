# Price check, first live run

One run of stallwalk/pricecheck.py on out/synthetic_walk/stock.json, 24 Nov 2026: 12 items, 12 Tavily searches (basic depth, 5 results) plus 12 Nemotron text calls, 5.6 s wall time in parallel. Kash approved the run. The table was then re-judged from the cache after two code fixes (a "/KG" unit wasn't recognised, and the cache had stored verdicts instead of the web range). No extra calls.

| Stall | Item | Stall price | Web range | Web unit | Verdict | Sources |
|---|---|---|---|---|---|---|
| Patel's Fruit & Veg | Avocados | £1.00 per each | £0.69 to £1.50 | each | usual | agro-market24.eu, ons.gov.uk, westpakavocado.com |
| Patel's Fruit & Veg | Bananas | £0.20 per each | £0.13 to £0.16 | each | usual | smartshelf.org.uk, uk.finance.yahoo.com, gov.uk |
| Patel's Fruit & Veg | Coriander | £0.80 per bunch | - | - | unknown | uk.investing.com, investing.com, investing.com |
| Patel's Fruit & Veg | Red Onions | £1.20 per kg | £0.73 to £1.23 | £ | unknown | agro-market24.eu, themissinggraph.wordpress.com, businessinsider.com |
| Patel's Fruit & Veg | Tomatoes | £1.80 per kg | £0.20 to £3.20 | £ | unknown | ons.gov.uk, finance.yahoo.com, businessinsider.com |
| Billy's Fresh Fish | King Prawns | £4.00 per 200g | - | - | unknown | tavily.com, finance.yahoo.com, finance.yahoo.com |
| Billy's Fresh Fish | Mackerel | £3.00 per each | - | - | unknown | seafish.org, find-and-update.company-information.service.gov.uk, finance.yahoo.com |
| Billy's Fresh Fish | Mussels | £6.00 per kg | £12.00 to £12.00 | per kg | usual | thefreshfishshop.com, mapquest.com, rocketreach.co |
| Billy's Fresh Fish | Salmon Fillet | £18.50 per kg | £11.80 to £25.24 | /KG | usual | aldi.co.uk, trolley.co.uk, finance.yahoo.com |
| Billy's Fresh Fish | Strawberries | £2.50 per punnet | £2.75 to £4.00 | punnet | usual | allsupers.co.uk, waitrose.com, businessinsider.com |
| Rosa's Cheese & Deli | Feta | £2.80 per each | - | - | unknown | coinmarketcap.com, businessinsider.com, mapquest.com |
| Rosa's Cheese & Deli | Halloumi | £3.50 per each | - | - | unknown | finance.yahoo.com, finance.yahoo.com, find-and-update.company-information.service.gov.uk |

## What it shows

- 5 of 12 got a verdict, all "usual". 0 high, 0 low, which is expected: the synthetic prices were set to be realistic.
- 7 of 12 came back "unknown", and none of them got a flag. That's the safe failure: no item gets a flag it can't back up.
- Red Onions and Tomatoes found a range but the model gave the unit as "£", so the like-units rule called them unknown. Fix: tell the model to return the unit as exactly "kg" (the asked unit) when the prices are per kg.
- Search quality is the weak part. About half the sources are off topic (coriander futures, a crypto token called FETA, 200G networking news, company records). Fix: add "supermarket" to the query, or pass Tavily `include_domains` for UK grocers (trolley.co.uk, tesco.com, sainsburys.co.uk, waitrose.com, aldi.co.uk).
- Mussels: the one source said £12/kg and the stall says £6/kg, exactly half, so it isn't flagged. The 0.5x bar is strict.
- Bananas at 5 for £1 (£0.20 each) against £0.13 to £0.16 is 1.25x to 1.5x, under the 2x bar for "high".

Neither fix is applied yet. Each needs one more live run of 12 + 12 calls to check.

## Run 2: UK grocer sites only (12ca03a)

Same 12 items, 12 Tavily searches plus 12 Nemotron calls, 6.4 s. Changes: Tavily `include_domains` set to Tesco, Sainsbury's, Asda, Morrisons, Ocado, Waitrose, Aldi and Trolley, "supermarket" added to the query, and the model told to return the asked unit exactly.

- 8 of 12 got a verdict (up from 5): 7 usual, 1 high. 4 unknown. Every source was a UK grocer page.
- The one "high" was wrong: Halloumi, "about 44x the usual UK price". The model's range was £0.08 to £0.08, from one stray reading. A false flag like that would undercut the demo, so run 3 changed how the range is built.

## Run 3: code builds the range from quotes (88d0cd0 and after)

Same 12 items, 12 Tavily searches plus 12 Nemotron calls, 3.2 s. The model now only lists each price the snippets state (price, unit, which snippet). Code keeps the like-unit quotes, drops stray ones (under a fifth or over 5x the median), and takes the range. A high or low flag needs at least 2 like-unit quotes. The table below is re-judged from run 3's cached lookups with the final code, so no extra calls.

| Item | Card price | UK supermarket range | Unit | Quotes | Verdict | Sources | Flag added |
|---|---|---|---|---|---|---|---|
| Avocados | £1.00 per each | £0.32 to £0.88 | each | 3 | usual | asda.com | - |
| Bananas | £0.20 per each | £0.17 to £0.20 | each | 2 | usual | trolley.co.uk, waitrose.com | - |
| Coriander | £0.80 per bunch | - | - | 0 | unknown | - | - |
| Red Onions | £1.20 per kg | £0.99 | kg | 1 | usual | morrisons.com | - |
| Tomatoes | £1.80 per kg | £0.80 to £8.88 | kg | 5 | usual | asda.com, tesco.com, trolley.co.uk | - |
| King Prawns | £4.00 per 200g | - | - | 0 | unknown | - | - |
| Mackerel | £3.00 per each | - | - | 0 | unknown | - | - |
| Mussels | £6.00 per kg | £4.50 to £9.00 | kg | 5 | usual | morrisons.com, tesco.com | - |
| Salmon Fillet | £18.50 per kg | £13.32 to £43.44 | kg | 11 | usual | aldi.co.uk, tesco.com, waitrose.com | - |
| Strawberries | £2.50 per punnet | - | - | 0 | unknown | - | - |
| Feta | £2.80 per each | £2.04 to £3.25 | each | 4 | usual | ocado.com, trolley.co.uk | - |
| Halloumi | £3.50 per each | £3.65 | each | 1 | usual | trolley.co.uk | - |

- 8 of 12 got a verdict, all usual, and none of them got a flag. The 4 unknown (Coriander, King Prawns, Mackerel, Strawberries) had no like-unit price in the snippets.
- Halloumi is now "usual" with no flag. Its stray 8p quote is gone.
- The ranges are wide for loose produce (Tomatoes £0.80 to £8.88/kg covers loose to cherry vine). A wide range can only hide a flag, never invent one.

## Seeded misreads and no-card estimates

Re-judged from run 3's cache with no extra calls. Mussels £6/kg changed to £60/kg and Red Onions £1.20/kg to £12/kg, as if the model misread the card. Feta and Halloumi had their card prices removed, to stand in for office-kitchen items that have no card.

| Item | Card price | UK supermarket range | Unit | Quotes | Verdict | Sources | Flag added |
|---|---|---|---|---|---|---|---|
| Red Onions | £12.00 per kg | £0.99 | kg | 1 | unknown | morrisons.com | - |
| Mussels | £60.00 per kg | £4.50 to £9.00 | kg | 5 | high | morrisons.com, tesco.com | about 7x the usual UK price (UK supermarkets £4.50-£9.00 per kg) |
| Feta | - (no card) | £2.04 to £3.25 | each | 4 | estimate | ocado.com, trolley.co.uk | - |
| Halloumi | - (no card) | £3.65 | each | 1 | estimate | trolley.co.uk | - |

- **Mussels at £60/kg fires the flag**, with 5 quotes and Tesco and Morrisons links. That's the live demo moment. The test `test_seeded_misread_flags_with_sources` covers the same case without network.
- Red Onions at £12/kg does NOT flag: the grocer search gave only one like-unit quote, and one quote isn't enough to accuse a stall. It's the cost of the Halloumi fix, and the right trade for a demo.
- Feta and Halloumi get verdict "estimate" with the label "web estimate of the usual UK price, not read from a price card". price_gbp stays empty.
