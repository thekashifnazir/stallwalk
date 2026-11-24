"""Web find: online UK supermarket prices for items that aren't on any walked stall.

For the voice agent's gaps ("the market has no shallots"). Reuses pricecheck: one Tavily
search per item on UK grocer sites, Nemotron lists the quoted prices, code takes the
like-unit range, and the per-item cache is shared with the price check.

Rules on top of the price check:
- a range needs at least pricecheck.MIN_QUOTES quotes, and one wider than MAX_SPREAD is dropped;
- everything is labelled "web estimate, online price": it's what a supermarket website
  shows, not a card price, and not a promise about any local shop;
- no location, distance or opening hours: Tavily can't see them, so the answer says to
  check your local store.
"""
import re
from urllib.parse import urlparse

from . import pricecheck as pc

LABEL = "web estimate, online price"
MAX_SEARCHES = 20  # per call, on top of pricecheck's own hard cap
MAX_SPREAD = 4     # high/low above this is too loose to say (a single vs a multipack)
STORES = {"tesco.com": "Tesco", "sainsburys.co.uk": "Sainsbury's", "asda.com": "Asda",
          "morrisons.com": "Morrisons", "ocado.com": "Ocado", "waitrose.com": "Waitrose",
          "aldi.co.uk": "Aldi", "trolley.co.uk": "Trolley (price comparison)"}


def split_items(text: str) -> list[str]:
    """"shallots, white wine and double cream" -> ["shallots", "white wine", "double cream"]."""
    parts = re.split(r",|;|\n|\band\b|\+", text or "")
    seen, out = set(), []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .")
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def _store(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    return next((name for dom, name in STORES.items() if host == dom or host.endswith("." + dom)), None)


def _money(v: float) -> str:
    return f"£{v:.2f}" if v >= 1 else f"{round(v * 100)}p"


def web_find(items: list[str], cache_path=None, max_searches: int = MAX_SEARCHES) -> dict:
    """Per item: online UK supermarket price range, store names and up to 2 links, or a reason
    there isn't one. Returns {"items": [...], "answer": "<short spoken summary>"}."""
    names = items[:min(max_searches, pc.MAX_SEARCHES)]
    stock = {"stalls": [{"stall": "web find", "items": [
        {"name": n, "price_gbp": None, "price_text": None, "unit": None, "needs_check": []} for n in names]}]}
    checked = pc.check_prices(stock, max_items=len(names), cache_path=cache_path)["stalls"][0]["items"]
    out = []
    for it in checked:
        chk = it.get("price_check") or {}
        lo, hi, n = chk.get("typical_low"), chk.get("typical_high"), int(chk.get("quotes") or 0)
        row = {"name": it["name"], "typical_low": None, "typical_high": None, "unit": None,
               "quotes": n, "stores": [], "sources": [], "label": LABEL, "note": None}
        if chk.get("verdict") != "estimate" or not lo or not hi:
            row["note"] = "no online price found"
        elif n < pc.MIN_QUOTES:
            row["note"] = "only one online price found, not enough to estimate"
        elif hi / lo > MAX_SPREAD:
            row["note"] = "online prices too spread to estimate (pack sizes differ?)"
        else:
            row.update(typical_low=lo, typical_high=hi, unit=chk.get("unit"),
                       sources=chk.get("sources", [])[:2])
            row["stores"] = sorted({s for s in map(_store, chk.get("sources", [])) if s})
        out.append(row)
    skipped = items[len(names):]
    return {"items": out, "skipped": skipped, "answer": answer_text(out, skipped)}


def answer_text(rows: list[dict], skipped: list[str] | None = None, top: int = 4) -> str:
    """Short enough to speak. Says "online price" and "check your local store"; never "nearby"."""
    parts = []
    for r in rows[:top]:
        if r["typical_low"] is None:
            parts.append(f"{r['name']}: {r['note']}")
            continue
        rng = (_money(r["typical_low"]) if r["typical_low"] == r["typical_high"]
               else f"{_money(r['typical_low'])} to {_money(r['typical_high'])}")
        unit = f" {r['unit']}" if r["unit"] == "each" else f" per {r['unit']}" if r["unit"] else ""
        at = f" at {' and '.join(r['stores'][:2])}" if r["stores"] else ""
        parts.append(f"{r['name']}: {rng}{unit} online{at}")
    more = len(rows) - top + len(skipped or [])
    tail = f", and {more} more" if more > 0 else ""
    return ("Web estimate, online prices: " + "; ".join(parts) + tail +
            ". Check your local store, prices and stock there may differ.")
