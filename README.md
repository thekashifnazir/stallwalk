# stallwalk

Walk a market with your phone. Get every stall's stock and prices.

Built at the Innovators Guild hackathon (Fresha × Nebius), Retail Commerce track, 24 Nov 2026. Inspired by Market Live, built by Team Nan at The Build Room Leicester 01.

## How it works

1. **Frames:** ffmpeg takes about one frame a second from the walk video.
2. **Read:** a vision model on Nebius Token Factory (Nemotron 3.5 Super VL, GLM-5.3-Flash as backup) lists each item, its price card and the stall sign it sits under. It never guesses a price it can't read.
3. **Merge:** code joins the same item seen in several frames, fixes cut-off stall signs, and flags anything unclear: prices that differ across frames, items only seen blurry.
4. **Score:** compare against a hand count: items found, prices right, wrong stall, made-up items.

## Run

```
uv run python fixtures/make_fixture.py        # synthetic 3-stall walk + hand count
uv run python -m stallwalk walk fixtures/synthetic_walk.mp4 --truth fixtures/synthetic_truth.json
```

Needs `.env` with `TOKENFACTORY_API_KEY` (and optionally `TOKENFACTORY_BASE_URL`, `VISION_MODEL`).

The synthetic stalls, items and prices are made up.

## Data

- `fixtures/real_kitchen/`: item lists the pipeline produced from phone footage of the event venue's office kitchen (24 Nov 2026). Text only; the footage itself is not in this repo.
- `fixtures/demo/`, `fixtures/markets/`, `fixtures/synthetic_*`: made-up stalls, prices and stockroom for the demo.
- `fixtures/commons/`: Wikimedia Commons photos, see `CREDITS.md`.
