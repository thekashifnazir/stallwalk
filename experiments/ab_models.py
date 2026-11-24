"""A/B the vision model on the synthetic walk: same frames, same prompt, one model each.

No retry and no fallback model, so each row measures that model alone.
Usage: uv run python experiments/ab_models.py [model ...]
Writes out/ab/<model>/readings.json and appends a results table to experiments/AB.md.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stallwalk import score, tf, walk  # noqa: E402

MODELS = ["nvidia/Nemotron-3.5-Super-VL", "zai-org/GLM-5.3-Flash", "google/gemma-3-27b-it"]
FRAMES_DIR = ROOT / "out" / "synthetic_walk" / "frames"
TRUTH = json.loads((ROOT / "fixtures" / "synthetic_truth.json").read_text())
MAX_FRAMES = 50


def read_one(model: str, frame: Path) -> dict:
    content = [{"type": "text", "text": walk.FRAME_PROMPT}, tf.image_part(frame)]
    t0 = time.time()
    try:
        reply = tf.chat(model, content, temperature=0.0, extra=walk.NO_THINKING)
    except Exception as e:  # noqa: BLE001 - record the failure, score what's left
        return {"frame": frame.name, "signs": [], "items": [], "error": str(e)[:200],
                "empty": False, "secs": round(time.time() - t0, 1)}
    out = {"frame": frame.name, "signs": [], "items": [], "empty": not reply.strip(),
           "secs": round(time.time() - t0, 1)}
    try:
        data = tf.parse_json(reply)
        if isinstance(data, dict):
            out["signs"] = data.get("signs") or []
            out["items"] = data.get("items") or []
        else:
            out["error"] = "reply JSON not an object"
    except ValueError as e:
        out["error"] = str(e)[:200]
    return out


def run_model(model: str, frames: list[Path]) -> dict:
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        readings = list(ex.map(lambda f: read_one(model, f), frames))
    wall = round(time.time() - t0, 1)
    dest = ROOT / "out" / "ab" / model.replace("/", "__")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "readings.json").write_text(json.dumps(readings, indent=2))
    s = score.score(walk.merge(readings), TRUTH)
    return {
        "model": model, "frames": len(frames), "wall_s": wall,
        "median_frame_s": sorted(r["secs"] for r in readings)[len(readings) // 2],
        "empty": sum(r["empty"] for r in readings),
        "failed": sum(1 for r in readings if r.get("error")),
        **{k: s[k] for k in ("found_pct", "price_pct", "on_wrong_stall", "not_in_hand_count")},
        "missed": s["missed"], "extras": s["extras"],
    }


def main() -> None:
    models = sys.argv[1:] or MODELS
    frames = sorted(FRAMES_DIR.glob("f_*.jpg"))
    if not frames:
        frames = walk.extract_frames(ROOT / "fixtures" / "synthetic_walk.mp4", FRAMES_DIR)
    frames = frames[:MAX_FRAMES]
    rows = []
    for m in models:
        print(f"{m}: {len(frames)} frames...", flush=True)
        r = run_model(m, frames)
        print(json.dumps(r), flush=True)
        rows.append(r)
    lines = ["", f"## Results ({time.strftime('%Y-%m-%d %H:%M')}, {len(frames)} frames)", "",
             "| Model | Price right % | Found % | Wrong stall | Not in hand count | Empty | Failed | Wall s | Median frame s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f'| {r["model"]} | {r["price_pct"]} | {r["found_pct"]} | {r["on_wrong_stall"]} | '
                     f'{r["not_in_hand_count"]} | {r["empty"]} | {r["failed"]} | {r["wall_s"]} | {r["median_frame_s"]} |')
    for r in rows:
        if r["missed"] or r["extras"]:
            lines.append(f'\n{r["model"]}: missed {r["missed"] or "none"}; extras {r["extras"] or "none"}')
    with (ROOT / "experiments" / "AB.md").open("a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
