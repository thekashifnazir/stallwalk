"""stallwalk CLI.

  uv run python -m stallwalk walk VIDEO [--out out/run] [--fps 1] [--truth truth.json]
"""
import argparse
import json
import time
from pathlib import Path

from . import walk
from .score import score


def main() -> None:
    p = argparse.ArgumentParser(prog="stallwalk")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("walk", help="video -> per-stall stock list")
    w.add_argument("video", type=Path)
    w.add_argument("--out", type=Path, default=None)
    w.add_argument("--fps", type=float, default=1.0)
    w.add_argument("--truth", type=Path, default=None, help="hand count JSON to score against")
    a = p.parse_args()

    out = a.out or Path("out") / a.video.stem
    t0 = time.time()
    stock = walk.run(a.video, out, fps=a.fps)
    secs = round(time.time() - t0, 1)
    for s in stock["stalls"]:
        print(f'\n== {s["stall"]}')
        for i in s["items"]:
            flag = f'  !! {"; ".join(i["needs_check"])}' if i["needs_check"] else ""
            print(f'  {i["name"]:<28} {i.get("price_text") or "-":<14} seen {i["seen_in_frames"]}{flag}')
    print(f'\n{stock["source"]["frames"]} frames in {secs}s, errors: {stock["source"]["errors"] or "none"}')
    if a.truth:
        sc = score(stock, json.loads(a.truth.read_text()))
        sc["seconds"] = secs
        (out / "score.json").write_text(json.dumps(sc, indent=2))
        print(json.dumps(sc, indent=2))


if __name__ == "__main__":
    main()
