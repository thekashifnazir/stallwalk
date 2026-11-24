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
