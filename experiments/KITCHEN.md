# Kitchen: order split and restock estimates

stallwalk/kitchen.py. Live runs on 24 Nov 2026, approved by Kash. The market stock lists are fixtures/markets/*.json: **made up** test data, not real markets, stalls or prices.

## Order split, one live parse call

Order text: `10kg potatoes, 5kg lemons, 2 dozen eggs, 3kg salmon`

Nemotron (TEXT_MODEL, thinking off) parsed it in 0.6 s, and that's the only model call:

```json
[{"item": "potatoes", "qty": 10, "unit": "kg"}, {"item": "lemons", "qty": 5, "unit": "kg"},
 {"item": "eggs", "qty": 24, "unit": "each"}, {"item": "salmon", "qty": 3, "unit": "kg"}]
```

Code then matched each line, picked the cheapest priced offer in a unit that converts, and multiplied:

| Asked | Pick (market, stall) | Card price | Line total | Note |
|---|---|---|---|---|
| 10 kg potatoes | veg market (made up), Veg stall B | 90p/kg | £9.00 | |
| 5 kg lemons | none | | | only sold per each |
| 24 each eggs | veg market (made up), Veg stall B | £2.80 dozen | £5.60 | dozen = 12 each, cheaper than £3.20 at Butcher A |
| 3 kg salmon | fish market (made up), Fishmonger A | £17/kg | £51.00 | cheaper than £18.50 at Fishmonger B |

- The model turned "2 dozen eggs" into 24 each. Code converts dozen and each both ways, so the line still prices.
- Lemons by the kg get no pick, because every stall sells them each. The line says so instead of guessing a weight per lemon.

## Restock with web estimates, real office kitchen footage

restock_with_estimates on the 9 files in out/real. Every lookup was already in the shared cache (out/pricecheck/cache.json) from the app's own restock call, so this run made no new Tavily calls.

| On the shelf (as read) | Level | File | Searched as | Web estimate (UK grocers) | Quotes | Sources |
|---|---|---|---|---|---|---|
| empty dispenser | empty | 20261124_165353.jpg | (not searched, no product name) | | | |
| Yellow packet crisps | low | 20261124_165350.jpg | yellow packet crisps | £0.64 to £0.73 per 100g | 2 | trolley.co.uk |
| corn flakes | low | 20261124_165353.jpg | corn flakes | £4.35 each | 1 | tesco.com |
| Coca-Cola cans bottom right | low | 20261124_165417.mp4 | coca-cola cans | £0.58 to £12.50 each | 12 | trolley.co.uk |
| Red cartons in drawer | low | 20261124_165417.mp4 | red cartons | none found | 0 | |
| Reese's snack packets | low | 20261124_165503.mp4 | reese's snack packets | £0.88 per 100g | 1 | trolley.co.uk |
| Cadbury Heroes | low | 20261124_165526.jpg | cadbury heroes | £3.50 to £7.00 each | 5 | tesco.com, asda.com |

- 5 of the 7 restock lines got an estimate, each labelled "web estimate of the usual UK price, not read from a price card". None of them has a price_gbp.
- Branded names (Cadbury Heroes, Coca-Cola) match best. Descriptive ones ("yellow packet crisps") still find something, but the estimate is loose.
- Coca-Cola's £0.58 to £12.50 spans a single can up to a multipack: "each" means one pack of any size. A pack size in the name read off the shelf (for example "24 cans") would tighten it.
- The empty dispenser and "red cartons" are reported honestly with no estimate.
