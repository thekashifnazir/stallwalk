"""Kitchen ordering: split one order (or a restock list) across the markets that were walked.

Nemotron only turns free order text into lines [{item, qty, unit}]. Everything after that
is code: match each line against the stock lists (walk._same_item), keep comparable units,
pick the cheapest priced option, and group the picks by market. Prices only ever come
from a stock list; nothing is estimated, and lines that don't match are listed as
unmatched rather than forced onto something close.
"""
import re

from . import tf
from .walk import _same_item, norm

ORDER_PROMPT = """Turn this kitchen order into JSON lines. Return JSON only:
{{"lines": [{{"item": string, "qty": number or null, "unit": string or null}}]}}
Rules:
- One line per product. item: the product name only, singular or plural as written, no quantity.
- qty: the number exactly as written, else null ("2 dozen eggs" -> qty 2, unit "dozen"). unit: "kg", "g", "each", "bunch", "punnet", "dozen", "pack", "box", "litre" if written, else null.
- Don't add products that aren't in the order.

Order:
{order}
"""

# words that describe the shelf, not the product ("cereal dispenser, empty" -> "cereal")
_SHELF_WORDS = r"\b(empty|emptied|low|nearly|almost|half|full|running|out|of|dispensers?|slots?|shelf|shelves|trays?|tubs?|jars?|containers?|bins?|left|none|no|some|few)\b"

_UNITS = {"kg": "kg", "kilo": "kg", "kilos": "kg", "kgs": "kg", "each": "each", "item": "each",
          "items": "each", "bunch": "bunch", "bunches": "bunch", "punnet": "punnet", "punnets": "punnet",
          "dozen": "dozen", "pack": "pack", "packs": "pack", "box": "box", "boxes": "box",
          "litre": "litre", "litres": "litre", "l": "litre"}

_LEVEL_RANK = {"empty": 2, "low": 1}
MAX_SPREAD = 4  # web estimate high/low above this is too loose to show (a can vs a multipack)


def clean_name(name: str) -> str:
    s = re.sub(r"[^\w\s&'-]", " ", (name or "").lower())
    s = re.sub(_SHELF_WORDS, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _unit(u) -> str | None:
    if not u or not isinstance(u, str):
        return None
    s = re.sub(r"^(/|per\s+|a\s+)", "", u.strip().lower()).strip()
    return _UNITS.get(s, s)


_PER = {("dozen", "each"): 12.0, ("each", "dozen"): 1 / 12}


def _factor(asked_unit, offer_unit) -> float | None:
    """How many offer units make one asked unit (1 dozen = 12 each), or None if they don't convert."""
    a, o = _unit(asked_unit), _unit(offer_unit)
    if a is None or o is None:
        return None
    return 1.0 if a == o else _PER.get((a, o))


def _market_name(stock: dict, n: int) -> str:
    return stock.get("market") or (stock.get("source") or {}).get("video") or f"market {n + 1}"


# ── restock ──

def restock_list(stocks: list[dict]) -> list[dict]:
    """Low or empty items across one or more stock lists, worst first, one line per item."""
    best: dict[str, dict] = {}
    order: list[str] = []
    for n, stock in enumerate(stocks):
        src = (stock.get("source") or {}).get("video") or stock.get("market") or f"stock {n + 1}"
        for stall in stock.get("stalls", []):
            for it in stall.get("items", []):
                level = it.get("stock_level")
                if level not in _LEVEL_RANK or not it.get("name"):
                    continue
                key = clean_name(it["name"]) or it["name"].lower()
                same = next((k for k in order if _same_item(k, key)), None)
                line = {"name": it["name"], "match_name": key, "stock_level": level, "source_file": src}
                if same is None:
                    order.append(key)
                    best[key] = line
                elif _LEVEL_RANK[level] > _LEVEL_RANK[best[same]["stock_level"]]:
                    best[same] = line
    return sorted((best[k] for k in order), key=lambda x: -_LEVEL_RANK[x["stock_level"]])


# ── order parsing (the only model call) ──

_QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|kgs|kilos?|g|dozen|bunch(?:es)?|punnets?|packs?|box(?:es)?|litres?|l|each)?\b\s*(?:of\s+)?$")


def _qty_from_text(order_text: str, item: str) -> tuple[float | None, str | None] | None:
    """Code owns quantities: find "<number> <unit>" written just before the item in the order
    text ("2 dozen eggs" -> (2, "dozen"), "30 lemons" -> (30, None)). None if not found."""
    words = [w for w in re.findall(r"[a-z]+", item.lower()) if len(w) > 2]
    if not words:
        return None
    text = order_text.lower()
    for m in re.finditer(re.escape(words[0][:-1] if words[0].endswith("s") else words[0]), text):
        before = re.split(r"[,;\n]| and ", text[:m.start()])[-1]
        q = _QTY_RE.search(before.strip() + " ") or _QTY_RE.search(before.strip())
        if q:
            n = float(q.group(1))
            return (int(n) if n.is_integer() else n), (q.group(2) or None)
    return None


def parse_order(order_text: str) -> list[dict]:
    reply = tf.chat(tf.TEXT_MODEL, ORDER_PROMPT.format(order=order_text), max_tokens=800,
                    extra={"chat_template_kwargs": {"enable_thinking": False}})
    data = tf.parse_json(reply)
    lines = data.get("lines") if isinstance(data, dict) else data
    out = []
    for ln in lines if isinstance(lines, list) else []:
        if isinstance(ln, dict) and isinstance(ln.get("item"), str) and ln["item"].strip():
            qty = ln.get("qty")
            line = {"item": ln["item"].strip(),
                    "qty": qty if isinstance(qty, (int, float)) and not isinstance(qty, bool) else None,
                    "unit": ln.get("unit") if isinstance(ln.get("unit"), str) else None}
            written = _qty_from_text(order_text, line["item"])
            if written:  # the order text wins over the model's reading ("2 dozen", not "24 dozen")
                line["qty"], line["unit"] = written[0], written[1] or line["unit"]
            out.append(line)
    return out


def _as_lines(order) -> list[dict]:
    if isinstance(order, str):
        return parse_order(order)
    lines = []
    for ln in order or []:  # a restock list, or lines already parsed
        if "item" in ln:
            lines.append({"item": ln["item"], "qty": ln.get("qty"), "unit": ln.get("unit")})
        else:
            lines.append({"item": ln.get("match_name") or clean_name(ln["name"]), "qty": None, "unit": None,
                          "asked": ln["name"], "stock_level": ln.get("stock_level"),
                          "source_file": ln.get("source_file")})
    return lines


# ── matching and splitting (pure code) ──

def _offers(stocks: list[dict]) -> list[dict]:
    out = []
    for n, stock in enumerate(stocks):
        market = _market_name(stock, n)
        for stall in stock.get("stalls", []):
            for it in stall.get("items", []):
                if not it.get("name"):
                    continue
                if (it.get("currency") or "GBP") != "GBP":
                    continue  # never compare across currencies
                out.append({"market": market, "stall": stall.get("stall") or "Unknown stall",
                            "name": it["name"], "price_gbp": it.get("price_gbp"),
                            "price_text": it.get("price_text"), "unit": it.get("unit")})
    return out


def _matches(item: str, offer_name: str) -> bool:
    """Same item (walk._same_item), or every asked word is in the offer and the last word,
    the thing itself, is the same: "eggs" -> "Free Range Eggs", but not "chicken" -> "Chicken Thighs"."""
    if _same_item(item, offer_name) or _same_item(clean_name(item), clean_name(offer_name)):
        return True
    a, b = norm(clean_name(item)).split(), norm(clean_name(offer_name)).split()
    return bool(a) and bool(b) and a[-1] == b[-1] and set(a) <= set(b)


def split_order(order, stocks: list[dict]) -> dict:
    """order: free text (parsed by the model), a restock_list(), or [{item, qty, unit}].

    Returns {"lines": [...], "by_market": {market: [lines]}, "unmatched": [asked, ...]}.
    Each line: asked, qty, unit, pick (cheapest priced comparable offer, or None) and
    alternatives (the other matching offers). line_total_gbp is only set when the order's
    unit is the offer's unit or converts exactly (dozen = 12 each; a count with no unit
    is "each"), so it's a straight multiply of a price read off a card. Multi-buys
    ("5 for £1") are already a per-each price_gbp from walk.merge.
    """
    offers = _offers(stocks)
    lines, by_market, unmatched = [], {}, []
    for ln in _as_lines(order):
        asked = ln.get("asked") or ln["item"]
        found = [o for o in offers if _matches(ln["item"], o["name"])]
        want = _unit(ln.get("unit"))
        if want is None:  # "30 lemons": any unit can be picked, totals only for "each"
            comparable = found
            per_asked = {id(o): (1.0 if _unit(o["unit"]) == "each" else None) for o in found}
        else:
            comparable = [o for o in found if _factor(want, o["unit"]) is not None]
            per_asked = {id(o): _factor(want, o["unit"]) for o in comparable}
        priced = sorted((o for o in comparable if isinstance(o["price_gbp"], (int, float))),
                        key=lambda o: o["price_gbp"] * (per_asked[id(o)] or 1))
        pick = priced[0] if priced else None
        line = {"asked": asked, "qty": ln.get("qty"), "unit": ln.get("unit"), "pick": pick,
                "alternatives": [o for o in found if o is not pick]}
        for k in ("stock_level", "source_file"):
            if ln.get(k):
                line[k] = ln[k]
        f = per_asked.get(id(pick)) if pick else None
        if pick and isinstance(line["qty"], (int, float)) and f is not None:
            line["line_total_gbp"] = round(line["qty"] * f * pick["price_gbp"], 2)
        if not found:
            line["note"] = "not on any stock list"
            unmatched.append(asked)
        elif not pick and comparable:
            line["note"] = "on a stock list, but no price was read"
        elif not pick:
            units = sorted({o["unit"] or "unknown unit" for o in found})
            line["note"] = f"only sold per {', '.join(units)}"
        lines.append(line)
        if pick:
            by_market.setdefault(pick["market"], []).append(line)
    return {"lines": lines, "by_market": by_market, "unmatched": unmatched}


# ── restock with web estimates (no card prices on an office kitchen shelf) ──

# where on the shelf, not what it is ("Coca-Cola cans bottom right" -> "Coca-Cola cans")
_PLACE_WORDS = r"\b(top|bottom|left|right|middle|centre|center|back|front|in|on|the|drawer|fridge|cupboard|counter|corner|row|rack)\b"


def _search_name(match_name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(_PLACE_WORDS, " ", match_name)).strip()


def restock_with_estimates(stocks: list[dict], cache_path=None, max_items: int = 12) -> dict:
    """restock_list() plus a web estimate of the usual UK price for each line, via
    pricecheck.check_prices on UK grocer sites. Lines whose name is only shelf words
    ("empty dispenser") aren't searched and get estimate None. Nothing here is a price."""
    from .pricecheck import ESTIMATE_LABEL, check_prices

    lines = restock_list(stocks)
    search = [(ln, _search_name(clean_name(ln["name"]))) for ln in lines]
    items = [{"name": q, "price_gbp": None, "price_text": None, "unit": None, "needs_check": [], "_line": n}
             for n, (ln, q) in enumerate(search) if q]
    checked = check_prices({"stalls": [{"stall": "restock", "items": items}]},
                           max_items=max_items, cache_path=cache_path)
    by_line = {i["_line"]: i.get("price_check") for i in checked["stalls"][0]["items"]}
    out = []
    for n, ln in enumerate(lines):
        chk = by_line.get(n)
        est = None
        note = None
        if chk and chk.get("verdict") == "estimate":
            lo, hi = chk.get("typical_low"), chk.get("typical_high")
            if lo and hi and hi / lo > MAX_SPREAD:
                note = "quotes too spread (can vs multipack?)"
            else:
                est = {k: chk.get(k) for k in ("typical_low", "typical_high", "unit", "quotes", "sources")}
                est["label"] = ESTIMATE_LABEL
        out.append({**ln, "search_name": search[n][1] or None, "estimate": est, "estimate_note": note})
    return {"lines": out}
