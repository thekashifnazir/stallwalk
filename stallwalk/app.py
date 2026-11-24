"""Local web app: upload a walk video, see the stock list, ask questions.

  uv run uvicorn stallwalk.app:app --port 8787
"""
import json
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
        return kitchen.restock_with_estimates(stocks, cache_path=RUNS / "pricecheck" / "cache.json")
    return {"lines": kitchen.restock_list(stocks)}


@app.get("/api/agent/id")
def agent_id():
    f = ROOT / "voice" / "agent.json"
    return json.loads(f.read_text()) if f.exists() else {"agent_id": None}


# ---- voice agent tools (ElevenLabs webhook tools call these; short plain answers it can speak)
@app.get("/api/agent/find")
def agent_find(q: str, run: str | None = None):
    p = _stock_path(run)
    if not p or not p.exists():
        return {"answer": "I haven't walked a market yet."}
    r = ask(json.loads(p.read_text()), q)
    if not r["matches"]:
        return {"answer": r.get("note") or "Nothing on today's stalls matches that."}
    parts = [f'{m["name"]} at {m["stall"]}, {m["price_text"] or "price not on the card"}' for m in r["matches"][:4]]
    return {"answer": "; ".join(parts), "note": r.get("note", "")}


@app.get("/api/agent/stalls")
def agent_stalls(run: str | None = None):
    p = _stock_path(run)
    if not p or not p.exists():
        return {"answer": "No walk yet."}
    st = json.loads(p.read_text())
    return {"answer": "; ".join(f'{s["stall"]}: {len(s["items"])} items, e.g. ' +
                                ", ".join(i["name"] for i in s["items"][:4]) for s in st["stalls"])}


@app.get("/api/agent/restock")
def agent_restock(folder: str = "real-frozen-v3"):
    base = RUNS / Path(folder).name
    stocks = [json.loads(p.read_text()) for p in sorted(base.glob("*/stock.json"))]
    r = kitchen.restock_with_estimates(stocks, cache_path=RUNS / "pricecheck" / "cache.json")
    out = []
    for l in r["lines"]:
        e = l.get("estimate") or {}
        est = (f', usually about £{e["typical_low"]:.2f} to £{e["typical_high"]:.2f} at UK supermarkets (web estimate)'
               if e.get("typical_low") is not None and e.get("quotes", 0) >= 2 else "")
        out.append(f'{l["name"]} is {l["stock_level"]}{est}')
    return {"answer": "; ".join(out) or "Nothing has run out."}


@app.get("/api/agent/order")
def agent_order(order: str):
    r = kitchen.split_order(order, _market_stocks())
    parts = []
    for l in r["lines"]:
        pk = l.get("pick")
        tot = f', £{l["line_total_gbp"]:.2f}' if l.get("line_total_gbp") is not None else ""
        parts.append(f'{l["asked"]}: {pk["stall"]} at {pk["market"]}, {pk["price_text"]}{tot}' if pk
                     else f'{l["asked"]}: {l.get("note") or "no match"}')
    return {"answer": "; ".join(parts) + ". These market stock lists are made up for the demo."}


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
