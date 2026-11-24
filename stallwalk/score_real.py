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


METHOD = ("fuzzy, no model: names lower-cased, punctuation and plural s removed; a match is equal names, "
          "or difflib ratio >= 0.85, or one name contained in the other (4+ chars), else difflib close match "
          "with cutoff 0.6. 'exact' counts equal normalised names only. Every pair is listed so a person can audit it.")


def score_dir(runs: Path, truth: dict) -> dict:
    per, tf_, tm, te, tx = {}, 0, 0, 0, 0
    for stem, real in truth.items():
        p = runs / stem / "stock.json"
        got = [i["name"] for s in json.loads(p.read_text())["stalls"] for i in s["items"]] if p.exists() else []
        pairs = {t: _hit(t, got) for t in real}
        found = [t for t, g in pairs.items() if g]
        exact = [t for t in real if any(norm(t) == norm(g) for g in got)]
        extras = [g for g in got if not _hit(g, real)]
        per[stem] = {"real": len(real), "found": len(found), "found_exact": len(exact),
                     "missed": [t for t in real if t not in found], "listed": len(got), "extras": extras,
                     "matched_pairs": {t: g for t, g in pairs.items() if g}}
        tf_ += len(found); tm += len(real) - len(found); te += len(extras); tx += len(exact)
    total = tf_ + tm
    return {"match_method": METHOD, "files": per, "total_real": total, "found": tf_, "found_exact": tx,
            "missed": tm, "extras": te, "found_pct": round(100 * tf_ / total) if total else 0,
            "found_exact_pct": round(100 * tx / total) if total else 0}


if __name__ == "__main__":
    print(json.dumps(score_dir(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())), indent=2))
