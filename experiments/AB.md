# Vision model A/B on the synthetic walk

Same 16 frames (fixtures/synthetic_walk.mp4 at 1 fps), same FRAME_PROMPT, thinking off, temperature 0, one call per frame, no retry and no fallback model. Each model's readings go through walk.merge and score.score against fixtures/synthetic_truth.json. Script: experiments/ab_models.py.

## Decision rule (written before any run)

A model that leaves more than 2 of 16 frames empty or failed is out. Of the rest, the highest price-right % wins. Ties go to the higher found %, then fewer items not in the hand count, then the shorter wall time.
