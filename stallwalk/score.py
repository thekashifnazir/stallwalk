"""Score a stock list against a hand count: items found, prices right, wrong stall, made-up items."""
import difflib
import json
import sys
from pathlib import Path

from .walk import norm


def _match(name: str, candidates: list[str]) -> str | None:
    best = difflib.get_close_matches(norm(name), [norm(c) for c in candidates], n=1, cutoff=0.75)
    if not best:
        return None
    return next(c for c in candidates if norm(c) == best[0])


def score(stock: dict, truth: dict) -> dict:
    got = {(s["stall"], i["name"]): i for s in stock["stalls"] for i in s["items"]}
    got_names = [n for _, n in got]
    found = price_ok = wrong_stall = 0
    misses = []
    for st in truth["stalls"]:
        for t in st["items"]:
            m = _match(t["name"], got_names)
            if not m:
                misses.append(f'{st["stall"]}: {t["name"]}')
                continue
            found += 1
            stalls = [s for (s, n) in got if n == m]
            if not any(_match(st["stall"], [s]) for s in stalls):
                wrong_stall += 1
            item = next(v for (s, n), v in got.items() if n == m)
            if item.get("price_gbp") is not None and abs(item["price_gbp"] - t["price_gbp"]) < 0.005:
                price_ok += 1
    truth_names = [t["name"] for st in truth["stalls"] for t in st["items"]]
    extras = [n for n in got_names if not _match(n, truth_names)]
    total = len(truth_names)
    return {
        "items_in_hand_count": total,
        "items_found": found,
        "prices_right": price_ok,
        "on_wrong_stall": wrong_stall,
        "not_in_hand_count": len(extras),
        "found_pct": round(100 * found / total) if total else 0,
        "price_pct": round(100 * price_ok / total) if total else 0,
        "missed": misses,
        "extras": extras,
    }


if __name__ == "__main__":
    s = json.loads(Path(sys.argv[1]).read_text())
    t = json.loads(Path(sys.argv[2]).read_text())
    print(json.dumps(score(s, t), indent=2))
