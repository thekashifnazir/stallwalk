"""Score runs on footage with no price cards: items found, missed and extra, against a hand-written truth.

  uv run python -m stallwalk.score_real out/real fixtures/real_truth.json
truth: {"<file stem>": ["product as it really is", ...]}
"""
import difflib
import json
import sys
from pathlib import Path

from .walk import _same_item, norm


def _hit(name: str, names: list[str]) -> str | None:
    for n in names:
        if _same_item(name, n):
            return n
    m = difflib.get_close_matches(norm(name), [norm(n) for n in names], n=1, cutoff=0.6)
    return next((n for n in names if norm(n) == m[0]), None) if m else None


def score_dir(runs: Path, truth: dict) -> dict:
    per, tf_, tm, te = {}, 0, 0, 0
    for stem, real in truth.items():
        p = runs / stem / "stock.json"
        got = [i["name"] for s in json.loads(p.read_text())["stalls"] for i in s["items"]] if p.exists() else []
        found = [t for t in real if _hit(t, got)]
        extras = [g for g in got if not _hit(g, real)]
        per[stem] = {"real": len(real), "found": len(found), "missed": [t for t in real if t not in found],
                     "listed": len(got), "extras": extras}
        tf_ += len(found); tm += len(real) - len(found); te += len(extras)
    total = tf_ + tm
    return {"files": per, "total_real": total, "found": tf_, "missed": tm, "extras": te,
            "found_pct": round(100 * tf_ / total) if total else 0}


if __name__ == "__main__":
    print(json.dumps(score_dir(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())), indent=2))
