"""Check prices against what UK supermarkets charge, or estimate them when there's no card.

Runs after walk.merge. For each checked item: one Tavily search limited to UK grocer
sites, then Nemotron lists every price the snippets state (price, unit, which snippet) as
JSON. Code does the rest: keeps like-unit quotes only, takes the range, and judges.

- Item with a card price and unit: verdict usual / high / low / unknown. High or low
  needs at least MIN_QUOTES like-unit quotes, and adds a needs_check flag with sources.
- Item with no card price (e.g. branded packs on an office kitchen shelf): verdict
  "estimate", with a label saying it's a web estimate. It goes in price_check only.

It never changes price_gbp or price_text: code owns prices, and an estimate is never a price.
Units are compared like for like (kg vs kg, each vs each); there's no conversion.
"""
import copy
import json
import os
import re
import statistics
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import tf
from .walk import norm

TAVILY_URL = "https://api.tavily.com/search"
TIMEOUT = 10
HIGH_X = 2.0     # card price above 2x the highest like-unit quote -> "high"
LOW_X = 0.5      # card price below 0.5x the lowest like-unit quote -> "low"
MIN_QUOTES = 2   # a high/low flag needs at least this many like-unit quotes
GROCERS = ["tesco.com", "sainsburys.co.uk", "asda.com", "morrisons.com", "ocado.com",
           "waitrose.com", "aldi.co.uk", "trolley.co.uk"]
MAX_SEARCHES = 50   # hard cap per run, whatever max_items says, so a loop can't burn credits
CACHE_VERSION = 3   # bump when the search or prompt changes, so old lookups are dropped
FLAG_MARK = "the usual UK price"  # every flag this module adds contains this
ESTIMATE_LABEL = "web estimate of the usual UK price, not read from a price card"

EXTRACT_PROMPT = """Below are numbered web search snippets from UK supermarket sites.
List the prices they state for "{name}"{unit_clause}.
Return JSON only: {{"quotes": [{{"price": number, "unit": string, "source": number}}]}}
Rules:
- One entry per price a snippet states for this product, or for the same product from another brand or shop. Skip different products.
- price: pounds as a number (80p -> 0.8).
- unit: what that price is for, as written. A unit price like "£1.10/kg" is "kg"; "£0.83/100g" is "100g"; the shelf price of one pack, bag, bottle or tin is "each".
- source: the snippet number.
- Only prices written in the snippets. Never guess or convert. If there are none, return {{"quotes": []}}.

Snippets:
{snippets}
"""

_UNIT_ALIASES = {
    "kg": "kg", "kilo": "kg", "kilogram": "kg", "1kg": "kg",
    "each": "each", "item": "each", "piece": "each", "unit": "each", "one": "each", "ea": "each",
    "pack": "each", "bag": "each", "bottle": "each", "tin": "each", "can": "each", "box": "each",
    "bunch": "bunch", "punnet": "punnet", "loaf": "loaf", "tub": "tub",
    "g": "g", "gram": "g",
}

_CACHE: dict[tuple[str, str], dict] = {}


def _unit(u) -> str | None:
    if not u or not isinstance(u, str):
        return None
    s = re.sub(r"^(/|per\s+|a\s+|an\s+)", "", u.strip().lower()).strip()
    s = re.sub(r"^(\d+)\s*g$", r"\1g", s)
    if s not in _UNIT_ALIASES and s.endswith("s"):
        s = s[:-1]
    return _UNIT_ALIASES.get(s, s)


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


# ── network calls (mocked in tests) ──

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


def extract_quotes(name: str, unit: str | None, results: list[dict]) -> list[dict]:
    """Nemotron lists the prices the snippets state. It doesn't summarise or judge."""
    snippets = "\n".join(f"[{n}] {r.get('title', '')}: {r.get('content', '')}"[:700]
                         for n, r in enumerate(results[:5]))
    unit_clause = f" (the stall sells it per {unit})" if unit else ""
    prompt = EXTRACT_PROMPT.format(name=name, unit_clause=unit_clause, snippets=snippets or "(none)")
    reply = tf.chat(tf.TEXT_MODEL, prompt, max_tokens=500, timeout=TIMEOUT,
                    extra={"chat_template_kwargs": {"enable_thinking": False}})
    data = tf.parse_json(reply)
    quotes = data.get("quotes") if isinstance(data, dict) else data
    return quotes if isinstance(quotes, list) else []


# ── pure code: range and verdict ──

def price_range(quotes: list[dict], urls: list[str], unit: str | None) -> dict:
    """Like-unit quotes -> {typical_low, typical_high, unit, quotes, sources}.
    With no unit to match (no price card), use "each" quotes if any, else the commonest unit."""
    clean = [(p, _unit(q.get("unit")), q.get("source")) for q in quotes if isinstance(q, dict)
             for p in [_num(q.get("price"))] if p is not None and _unit(q.get("unit"))]
    want = _unit(unit)
    if want is None and clean:
        units = Counter(u for _, u, _ in clean)
        want = "each" if "each" in units else units.most_common(1)[0][0]
    used = [(p, s) for p, u, s in clean if u == want]
    if len(used) >= 2:  # drop stray readings (8p halloumi, a per-gram price labelled each)
        med = statistics.median(p for p, _ in used)
        used = [(p, s) for p, s in used if med / 5 <= p <= med * 5]
    sources = []
    for _, s in used:
        if isinstance(s, int) and 0 <= s < len(urls) and urls[s] not in sources:
            sources.append(urls[s])
    prices = [p for p, _ in used]
    return {"typical_low": min(prices) if prices else None,
            "typical_high": max(prices) if prices else None,
            "unit": want if prices else None,
            "quotes": len(prices),
            "sources": sources[:3]}


def judge(price: float | None, unit: str | None, rng: dict) -> tuple[str, str | None]:
    """Card price vs web range. Returns (verdict, flag or None)."""
    lo, hi = _num(rng.get("typical_low")), _num(rng.get("typical_high"))
    if price is None or not unit or lo is None or hi is None or _unit(rng.get("unit")) != _unit(unit):
        return "unknown", None
    if lo > hi:
        lo, hi = hi, lo
    if int(rng.get("quotes") or 0) < MIN_QUOTES:
        return ("usual", None) if lo / 2 <= price <= hi * 2 else ("unknown", None)
    shown = f"£{lo:.2f}" if lo == hi else f"£{lo:.2f}-£{hi:.2f}"
    where = f"UK supermarkets {shown} per {unit}"
    if price > HIGH_X * hi:
        return "high", f"about {price / hi:.0f}x the usual UK price ({where})"
    if price < LOW_X * lo:
        return "low", f"under half the usual UK price ({where})"
    return "usual", None


# ── orchestration ──

def _lookup(name: str, unit: str | None) -> dict | None:
    """Raw quotes for one item name + unit, cached. The range and verdict are worked out
    fresh each time, so the same item at another stall or price gets its own verdict."""
    key = (norm(name), _unit(unit) or "")
    if key in _CACHE:
        return _CACHE[key]
    query = f"{name} price per {unit} UK supermarket" if unit else f"{name} price UK supermarket"
    try:
        res = tavily_search(query).get("results") or []
        quotes = extract_quotes(name, unit, res)
    except Exception:  # noqa: BLE001 - a failed lookup is "unknown", never a guess
        return None  # not cached, so a later run can retry
    found = {"quotes": quotes, "urls": [r.get("url") or "" for r in res[:5]]}
    _CACHE[key] = found
    return found


def _check_one(item: dict) -> dict:
    name, unit = item["name"], item.get("unit")
    price = _num(item.get("price_gbp"))
    has_card = price is not None and bool(unit)
    blank = {"typical_low": None, "typical_high": None, "unit": None, "quotes": 0,
             "verdict": "unknown", "sources": []}
    found = _lookup(name, unit if has_card else (unit or None))
    if found is None:
        return blank
    rng = price_range(found["quotes"], found["urls"], unit)
    if has_card:
        verdict, flag = judge(price, unit, rng)
        return {**rng, "verdict": verdict, "_flag": flag}
    if not rng["quotes"]:
        return {**rng, "verdict": "unknown"}
    return {**rng, "verdict": "estimate", "label": ESTIMATE_LABEL}


def check_prices(stock: dict, max_items: int = 12, workers: int = 6,
                 cache_path: Path | None = None) -> dict:
    """Copy of the stock list with `price_check` on up to max_items items.

    Order: items with a card price and no flags, then card prices with flags, then items
    with no card price (these get a web estimate). cache_path (optional) keeps the raw
    lookups between runs, keyed by item name and unit.
    """
    out = copy.deepcopy(stock)
    if cache_path and Path(cache_path).exists():
        saved = json.loads(Path(cache_path).read_text())
        if isinstance(saved, dict) and saved.get("version") == CACHE_VERSION:
            for k, v in saved.get("items", {}).items():
                n, u = k.split("|", 1)
                _CACHE.setdefault((n, u), v)
    items = [i for s in out.get("stalls", []) for i in s.get("items", []) if i.get("name")]
    for i in items:  # re-running is safe: drop the last run's checks and flags first
        i.pop("price_check", None)
        if i.get("needs_check"):
            i["needs_check"] = [f for f in i["needs_check"] if FLAG_MARK not in f]

    def carded(i):
        return _num(i.get("price_gbp")) is not None and bool(i.get("unit"))

    ordered = ([i for i in items if carded(i) and not i.get("needs_check")]
               + [i for i in items if carded(i) and i.get("needs_check")]
               + [i for i in items if not carded(i)])
    picked = ordered[:min(max_items, MAX_SEARCHES)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        checks = list(ex.map(_check_one, picked))
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
