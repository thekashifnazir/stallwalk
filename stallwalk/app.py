"""Local web app: upload a walk video, see the stock list, ask questions.

  uv run uvicorn stallwalk.app:app --port 8787
"""
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from . import walk
from .ask import ask
from .export import export_stock
from .facts import item_facts
from .enrich import enrich_item
from .pricecheck import check_prices
from . import kitchen

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "out"
STATIC = ROOT / "static"
app = FastAPI(title="stallwalk")


def _latest() -> Path | None:
    runs = sorted((p for p in RUNS.glob("*/stock.json")), key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/walk")
async def api_walk(video: UploadFile = File(...)):
    name = f"walk-{time.strftime('%H%M%S')}"
    out = RUNS / name
    out.mkdir(parents=True, exist_ok=True)
    path = out / (Path(video.filename or "walk.mp4").name)
    with path.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    t0 = time.time()
    stock = walk.run(path, out)
    stock["source"]["seconds"] = round(time.time() - t0, 1)
    stock["run"] = name
    (out / "stock.json").write_text(json.dumps(stock, indent=2))
    return stock


@app.get("/api/stock")
def api_stock(run: str | None = None):
    p = RUNS / run / "stock.json" if run else _latest()
    if not p or not p.exists():
        return JSONResponse({"stalls": [], "source": None})
    stock = json.loads(p.read_text())
    stock["run"] = p.parent.name
    score = p.parent / "score.json"
    if score.exists():
        stock["score"] = json.loads(score.read_text())
    return stock


@app.post("/api/ask")
def api_ask(question: str = Form(...), run: str | None = Form(None)):
    p = RUNS / run / "stock.json" if run else _latest()
    if not p or not p.exists():
        return JSONResponse({"error": "no stock list yet"}, status_code=400)
    return ask(json.loads(p.read_text()), question)


@app.get("/api/export")
def api_export(run: str | None = None):
    """The stock list in the agent-shopping formats (ACP and UCP), shaped like the Catalog Enrichment blueprint's export."""
    p = RUNS / run / "stock.json" if run else _latest()
    if not p or not p.exists():
        return JSONResponse({"error": "no stock list yet"}, status_code=400)
    return export_stock(json.loads(p.read_text()))


@app.get("/api/facts")
def api_facts(name: str, stall: str = ""):
    """Web facts for one item (Tavily + Nemotron), with sources. Cached per item."""
    return item_facts(name, stall)


def _stock_path(run: str | None) -> Path | None:
    return RUNS / run / "stock.json" if run else _latest()


@app.post("/api/enrich")
def api_enrich(stall: str = Form(...), name: str = Form(...), run: str | None = Form(None)):
    """One item's catalogue entry from the NVIDIA Catalog Enrichment blueprint (crop of the item, card price kept)."""
    p = _stock_path(run)
    if not p or not p.exists():
        return JSONResponse({"error": "no stock list yet"}, status_code=400)
    stock = json.loads(p.read_text())
    item = next((i for s in stock["stalls"] if s["stall"] == stall for i in s["items"] if i["name"] == name), None)
    if not item:
        return JSONResponse({"error": "item not in stock list"}, status_code=404)
    out = enrich_item(p.parent, stall, item)
    out["run"] = p.parent.name
    return out


@app.post("/api/pricecheck")
def api_pricecheck(run: str | None = Form(None)):
    """Tavily + Nemotron: flag prices far from the usual UK price. Adds flags only; prices stay the card's."""
    p = _stock_path(run)
    if not p or not p.exists():
        return JSONResponse({"error": "no stock list yet"}, status_code=400)
    checked = check_prices(json.loads(p.read_text()), max_items=12, cache_path=RUNS / "pricecheck" / "cache.json")
    p.write_text(json.dumps(checked, indent=2))
    checked["run"] = p.parent.name
    return checked


MARKETS = ROOT / "fixtures" / "markets"


def _market_stocks() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(MARKETS.glob("*.json"))]


@app.post("/api/order")
def api_order(order: str = Form(...)):
    """Kitchen order text -> split across the (made-up) market stock lists, cheapest comparable priced offer."""
    return kitchen.split_order(order, _market_stocks())


@app.get("/api/restock")
def api_restock(folder: str = "real-frozen-v3", estimates: bool = False):
    """Low and empty items across a folder of runs (e.g. the office kitchen footage)."""
    base = (RUNS / Path(folder).name)
    stocks = [json.loads(p.read_text()) for p in sorted(base.glob("*/stock.json"))]
    if estimates and hasattr(kitchen, "restock_with_estimates"):
        r = kitchen.restock_with_estimates(stocks, cache_path=RUNS / "pricecheck" / "cache.json")
    else:
        r = {"lines": kitchen.restock_list(stocks)}
    return _present_restock(r, stocks)


_LOCATION = re.compile(r"\s*[,(]?\s*\b((?:top|bottom|middle)\s+(?:left|right|shelf)|(?:in|on|behind|under)\s+(?:the\s+)?"
                       r"(?:drawer|shelf|fridge|door|counter|tray|wire shelf))\b\)?", re.I)


def _present_restock(r: dict, stocks: list[dict]) -> dict:
    """Display tidy-up only: location out of the name, plain names for empty dispensers, a labelled total."""
    names_by_file = {st.get("source", {}).get("video"): " ".join(i["name"].lower() for s in st["stalls"] for i in s["items"])
                     for st in stocks}
    total, priced, summed = 0.0, 0, []
    for l in r.get("lines", []):
        name = l["name"]
        m = _LOCATION.search(name)
        if m:
            l["location"] = m.group(1)
            name = _LOCATION.sub("", name).strip(" ,")
        if re.search(r"dispenser", name, re.I) and l.get("stock_level") == "empty":
            kind = "Cereal dispenser" if "cereal" in names_by_file.get(l.get("source_file"), "") else "Dispenser"
            name = f"{kind} (empty)"
        l["display_name"] = name[:1].upper() + name[1:]
        e = l.get("estimate") or {}
        if e.get("typical_low") is not None:
            hi = e.get("typical_high") if e.get("typical_high") is not None else e["typical_low"]
            e["display"] = (f'£{e["typical_low"]:.2f}' if abs(hi - e["typical_low"]) < 0.005 else f'£{e["typical_low"]:.2f}–£{hi:.2f}') + \
                (f' {e["unit"]}' if e.get("unit") == "each" else (f' per {e["unit"]}' if e.get("unit") else ""))
            if e.get("unit") in (None, "each"):  # only whole items add up; a per-100g price isn't a pack price
                total += (e["typical_low"] + hi) / 2
                priced += 1
                summed.append(l["display_name"])
    n = len(r.get("lines", []))
    r["total"] = {"gbp": round(total, 2), "priced": priced, "of": n, "items": summed,
                  "label": f"web estimate for {priced} of {n} items, one of each, midpoint of UK supermarket quotes; items priced per weight not added"}
    return r


@app.get("/api/agent/id")
def agent_id():
    f = ROOT / "voice" / "agent.json"
    return json.loads(f.read_text()) if f.exists() else {"agent_id": None}


# ---- voice agent tools (ElevenLabs webhook tools call these; short plain answers it can speak)
AGENT_RUN = os.environ.get("STALLWALK_AGENT_RUN", "meal")  # "meal" = fixtures/demo/meal_market.json, else a run name
DEMO = ROOT / "fixtures" / "demo"


def _agent_stock(run: str | None = None) -> dict | None:
    """The ONE stock list the voice agent's find, stalls and order tools all read, so prices can't disagree."""
    run = run or AGENT_RUN
    if run == "meal":
        return json.loads((DEMO / "meal_market.json").read_text())
    p = _stock_path(run)
    return json.loads(p.read_text()) if p and p.exists() else None


@app.get("/api/agent/find")
def agent_find(q: str, run: str | None = None):
    stock = _agent_stock(run)
    if not stock:
        return {"answer": "I haven't walked a market yet."}
    r = ask(stock, q)
    if not r["matches"]:
        return {"answer": r.get("note") or "Nothing on today's stalls matches that."}
    parts = [f'{m["name"]} at {m["stall"]}, {m["price_text"] or "price not on the card"}' for m in r["matches"][:4]]
    return {"answer": "; ".join(parts), "note": r.get("note", "")}


@app.get("/api/agent/stalls")
def agent_stalls(run: str | None = None):
    st = _agent_stock(run)
    if not st:
        return {"answer": "No walk yet."}
    return {"answer": "; ".join(f'{s["stall"]}: {len(s["items"])} items, e.g. ' +
                                ", ".join(i["name"] for i in s["items"][:4]) for s in st["stalls"])}


@app.get("/api/agent/restock")
def agent_restock(folder: str = "real-frozen-v3"):
    r = api_restock(folder=folder, estimates=True)  # same tidy names, locations and total as the screen
    lines = r.get("lines", [])
    said = []
    for l in lines[:5]:
        e = l.get("estimate") or {}
        where = f' ({l["location"]})' if l.get("location") else ""
        price = f', about {e["display"].replace("–", " to ")} (web estimate)' if e.get("display") else ""  # spoken: no dash
        level = "" if "(empty)" in l["display_name"] else f' is {l["stock_level"]}'
        said.append(f'{l["display_name"]}{where}{level}{price}')
    more = f", and {len(lines) - 5} more" if len(lines) > 5 else ""
    t = r.get("total") or {}
    names = " and ".join(t.get("items") or [])
    total = (f'. Restock about £{t["gbp"]:.2f}: one each of {names}, the middle of UK supermarket web prices'
             if t.get("priced") else "")
    return {"answer": ("; ".join(said) + more + total + ".") if said else "Nothing has run out."}


@app.get("/api/agent/order")
def agent_order(order: str, run: str | None = None):
    stock = _agent_stock(run)
    r = kitchen.split_order(order, [stock] if stock else [])
    parts = []
    for l in r["lines"]:
        pk = l.get("pick")
        tot = f', £{l["line_total_gbp"]:.2f}' if l.get("line_total_gbp") is not None else ""
        parts.append(f'{l["asked"]}: {pk["stall"]}, {pk["price_text"]}{tot}' if pk
                     else f'{l["asked"]}: {l.get("note") or "not on the market today"}'.replace("not on any stock list", "not on the market today"))
    total = sum(l["line_total_gbp"] for l in r["lines"] if l.get("line_total_gbp") is not None)
    tail = f". Market total £{total:.2f}" if total else ""
    made_up = " These stalls and prices are made up for the demo." if (stock or {}).get("made_up") else ""
    return {"answer": "; ".join(parts) + tail + "." + made_up,
            "missing": [l["asked"] for l in r["lines"] if not l.get("pick") and "not on any stock list" in (l.get("note") or "not on any stock list")]}


@app.get("/api/agent/stockroom")
def agent_stockroom(items: str):
    """Check the (made-up) restaurant stockroom before buying: have, low or out, so we don't overbuy."""
    from .walk import _same_item
    room = json.loads((DEMO / "stockroom.json").read_text())
    asked = [x.strip() for x in re.split(r",|\band\b", items) if x.strip()]
    said, need = [], []
    for a in asked:
        hit = next((i for i in room["items"] if _same_item(a, i["name"]) or _same_item(kitchen.clean_name(a), i["name"])), None)
        if not hit:
            said.append(f"{a}: not something we stock"); need.append(a)
        elif hit["status"] == "have":
            said.append(f'{hit["name"]}: have {hit["qty"]} {hit["unit"]}')
        else:
            said.append(f'{hit["name"]}: {hit["status"]}' + (f' ({hit["qty"]} {hit["unit"]} left)' if hit["qty"] else ""))
            need.append(hit["name"])
    return {"answer": "; ".join(said) + (f". Buy: {', '.join(need)}." if need else ". Nothing to buy.")
                      + " Stockroom is made up for the demo.", "need": need}


@app.get("/api/frame/{run}/{frame}")
def api_frame(run: str, frame: str):
    p = (RUNS / run / "frames" / Path(frame).name)
    return FileResponse(p) if p.exists() else JSONResponse({"error": "no frame"}, status_code=404)


# ---- live mode: the phone sends a frame every second or so, the stock list fills in as you walk
_live_lock = threading.Lock()
_live: dict[str, list[dict]] = {}


@app.post("/api/live/frame")
async def api_live_frame(session: str = Form(...), seq: int = Form(...), image: UploadFile = File(...)):
    session = "".join(c for c in session if c.isalnum() or c in "-_")[:40] or "live"
    out = RUNS / f"live-{session}"
    (out / "frames").mkdir(parents=True, exist_ok=True)
    frame = out / "frames" / f"f_{seq:04d}.jpg"
    frame.write_bytes(await image.read())
    t0 = time.time()
    reading = await run_in_threadpool(walk.read_frame, frame)
    reading["seq"] = seq
    reading["seconds"] = round(time.time() - t0, 2)
    with _live_lock:
        readings = _live.setdefault(session, [])
        readings.append(reading)
        readings.sort(key=lambda r: r["seq"])
        stock = walk.merge(readings)
        stock["source"] = {"video": "live", "frames": len(readings), "fps": None,
                           "errors": [r["frame"] for r in readings if r.get("error")]}
        stock["run"] = out.name
        (out / "readings.json").write_text(json.dumps(readings, indent=2))
        (out / "stock.json").write_text(json.dumps(stock, indent=2))
    stock["last_frame"] = {"seq": seq, "seconds": reading["seconds"], "items": len(reading.get("items", [])),
                           "signs": reading.get("signs", []), "error": reading.get("error")}
    return stock


@app.post("/api/live/reset")
def api_live_reset(session: str = Form(...)):
    with _live_lock:
        _live.pop(session, None)
    return {"ok": True}
