"""Check stall prices against typical UK prices found on the web.

Runs after walk.merge. For each checked item: Tavily search for the usual UK price,
Nemotron pulls the typical low/high numbers out of the snippets as JSON, and code
does the comparison. It only ADDS a `price_check` block (and a needs_check flag when
the price looks off). It never changes price_gbp or price_text: code owns prices.

Units are compared like for like (kg vs kg, each vs each). If the web price comes back
in a different unit, the verdict is "unknown" rather than a converted guess.
"""
import copy
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import tf
from .walk import norm

TAVILY_URL = "https://api.tavily.com/search"
TIMEOUT = 10
HIGH_X = 2.0   # price above 2x typical_high -> "high"
LOW_X = 0.5    # price below 0.5x typical_low -> "low"
GROCERS = ["tesco.com", "sainsburys.co.uk", "asda.com", "morrisons.com", "ocado.com",
           "waitrose.com", "aldi.co.uk", "trolley.co.uk"]
MAX_SEARCHES = 50
CACHE_VERSION = 2  # bump when the search or prompt changes, so old lookups are dropped  # hard cap per run, whatever max_items says, so a loop can't burn credits

EXTRACT_PROMPT = """Below are web search snippets about the UK retail price of "{name}", per {unit}.
Return JSON only: {{"typical_low": number or null, "typical_high": number or null, "unit": string or null}}
Rules:
- Prices in pounds as numbers (80p -> 0.8). Only use prices stated in the snippets. Never guess.
- Only use prices quoted per {unit}. If you use them, set "unit" to exactly "{unit}".
- If the snippets only give another unit (e.g. per pack, per 500g), set "unit" to that unit as written.
- typical_low and typical_high: the lowest and highest per-{unit} prices the snippets state for ordinary UK shops.
- If no usable price is stated, all three are null.

Snippets:
{snippets}
"""

_UNIT_ALIASES = {
    "kg": "kg", "kilo": "kg", "kilogram": "kg", "1kg": "kg", "per kg": "kg",
    "each": "each", "item": "each", "piece": "each", "unit": "each", "one": "each", "ea": "each",
    "bunch": "bunch", "punnet": "punnet", "loaf": "loaf", "tub": "tub", "pack": "pack",
    "100g": "100g", "200g": "200g", "g": "g", "gram": "g",
}

_CACHE: dict[tuple[str, str], dict] = {}


def _unit(u: str | None) -> str | None:
    if not u:
        return None
    s = re.sub(r"^(/|per\s+|a\s+|an\s+)", "", u.strip().lower()).strip()
    s = re.sub(r"(\d+)\s*g$", r"\1g", s)
    if s not in _UNIT_ALIASES and s.endswith("s"):
        s = s[:-1]
    return _UNIT_ALIASES.get(s, s)


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def tavily_search(query: str, include_domains: list[str] | None = None) -> dict:
    """One Tavily search, UK grocers only by default. Bearer auth, basic depth, 5 results."""
    body = {"query": query, "max_results": 5, "search_depth": "basic",
            "include_domains": GROCERS if include_domains is None else include_domains}
    req = urllib.request.Request(
        TAVILY_URL, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY', '')}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def extract_typical(name: str, unit: str, results: list[dict]) -> dict:
    """Nemotron reads the snippets and returns the typical price range as JSON."""
    snippets = "\n".join(f"- {r.get('title', '')}: {r.get('content', '')}"[:600] for r in results[:5])
    prompt = EXTRACT_PROMPT.format(name=name, unit=unit, snippets=snippets or "(none)")
    reply = tf.chat(tf.TEXT_MODEL, prompt, max_tokens=300, timeout=TIMEOUT,
                    extra={"chat_template_kwargs": {"enable_thinking": False}})
    data = tf.parse_json(reply)
    return data if isinstance(data, dict) else {}


def judge(price: float | None, unit: str | None, typical: dict) -> tuple[str, str | None]:
    """Pure comparison. Returns (verdict, flag or None)."""
    lo, hi = _num(typical.get("typical_low")), _num(typical.get("typical_high"))
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    lo, hi = lo if lo is not None else hi, hi if hi is not None else lo
    if price is None or not unit or lo is None or hi is None or _unit(typical.get("unit")) != _unit(unit):
        return "unknown", None
    rng = f"usual £{lo:.2f}-£{hi:.2f} per {unit}"
    if price > HIGH_X * hi:
        return "high", f"about {price / hi:.0f}x the usual UK price ({rng})"
    if price < LOW_X * lo:
        return "low", f"under half the usual UK price ({rng})"
    return "usual", None


def _lookup(name: str, unit: str) -> dict | None:
    """Web range for one item name + unit. Cached; the price is judged fresh each time,
    so the same item at a different stall or a different price gets its own verdict."""
    key = (norm(name), _unit(unit) or "")
    if key in _CACHE:
        return _CACHE[key]
    try:
        res = tavily_search(f"{name} price per {unit} UK supermarket").get("results") or []
        typical = extract_typical(name, unit, res)
    except Exception:  # noqa: BLE001 - a failed lookup is "unknown", never a guess
        return None  # not cached, so a later run can retry
    found = {
        "typical_low": _num(typical.get("typical_low")),
        "typical_high": _num(typical.get("typical_high")),
        "unit": typical.get("unit"),
        "sources": [r["url"] for r in res if r.get("url")][:3],
    }
    _CACHE[key] = found
    return found


def _check_one(name: str, unit: str | None, price: float | None) -> dict:
    blank = {"typical_low": None, "typical_high": None, "unit": None, "verdict": "unknown", "sources": []}
    if not unit or price is None:
        return blank
    found = _lookup(name, unit)
    if found is None:
        return blank
    verdict, flag = judge(price, unit, found)
    return {**{k: found[k] for k in ("typical_low", "typical_high", "unit", "sources")},
            "verdict": verdict, "_flag": flag}


def check_prices(stock: dict, max_items: int = 12, workers: int = 6,
                 cache_path: Path | None = None) -> dict:
    """Copy of the stock list with `price_check` on up to max_items items.

    Picks items with a price and no flags first, then priced items with flags.
    Items with no price aren't searched. cache_path (optional) keeps results
    between runs, keyed by item name and unit.
    """
    out = copy.deepcopy(stock)
    if cache_path and Path(cache_path).exists():
        saved = json.loads(Path(cache_path).read_text())
        if isinstance(saved, dict) and saved.get("version") == CACHE_VERSION:
            for k, v in saved.get("items", {}).items():
                n, u = k.split("|", 1)
                _CACHE.setdefault((n, u), v)
    items = [i for s in out.get("stalls", []) for i in s.get("items", [])]
    priced = [i for i in items if isinstance(i.get("price_gbp"), (int, float)) and i.get("unit")]
    picked = ([i for i in priced if not i.get("needs_check")]
              + [i for i in priced if i.get("needs_check")])[:min(max_items, MAX_SEARCHES)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        checks = list(ex.map(lambda i: _check_one(i["name"], i.get("unit"), float(i["price_gbp"])), picked))
    for item, chk in zip(picked, checks):
        chk = dict(chk)
        flag = chk.pop("_flag", None)
        item["price_check"] = chk
        if flag:
            item["needs_check"] = list(item.get("needs_check") or []) + [flag]
    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps(
            {"version": CACHE_VERSION, "items": {f"{n}|{u}": v for (n, u), v in _CACHE.items()}}, indent=2))
    return out
