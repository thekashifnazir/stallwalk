# Vision model A/B on the synthetic walk

Same 16 frames (fixtures/synthetic_walk.mp4 at 1 fps), same FRAME_PROMPT, thinking off, temperature 0, one call per frame, no retry and no fallback model. Each model's readings go through walk.merge and score.score against fixtures/synthetic_truth.json. Script: experiments/ab_models.py.

## Decision rule (written before any run)

A model that leaves more than 2 of 16 frames empty or failed is out. Of the rest, the highest price-right % wins. Ties go to the higher found %, then fewer items not in the hand count, then the shorter wall time.

## Results (2026-11-24 16:37, 16 frames)

| Model | Price right % | Found % | Wrong stall | Not in hand count | Empty | Failed | Wall s | Median frame s |
|---|---|---|---|---|---|---|---|---|
| nvidia/Nemotron-3.5-Super-VL | 100 | 100 | 0 | 0 | 0 | 0 | 3.8 | 1.7 |
| zai-org/GLM-5.3-Flash | 100 | 100 | 0 | 0 | 0 | 0 | 16.2 | 6.8 |
| google/gemma-3-27b-it | 69 | 69 | 2 | 1 | 0 | 7 | 49.0 | 24.0 |

google/gemma-3-27b-it: missed ["Patel's Fruit & Veg: Tomatoes", "Patel's Fruit & Veg: Bananas", "Patel's Fruit & Veg: Coriander", "Patel's Fruit & Veg: Avocados", "Billy's Fresh Fish: King Prawns"]; extras ['Sour Cream']

All 7 gemma failures were the 25 s timeout in tf.chat, not bad replies.

## Decision

Under the rule, gemma-3-27b-it is out because 7 of 16 frames failed. Nemotron-3.5-Super-VL and GLM-5.3-Flash tie on price-right %, found % and items not in the hand count, so the shorter wall time decides it: **Nemotron-3.5-Super-VL** wins (3.8 s against 16.2 s for the 16 frames). The current default VISION_MODEL stays, with GLM-5.3-Flash kept as the fallback.

Caveat: this is one run on a synthetic fixture where both top models score 100%. It shows speed and reliability, not which model reads real stalls better. A real phone walk with a hand count would separate them.
