"""Walk-through video -> per-stall stock list.

frames (ffmpeg, ~1 fps) -> vision model reads each frame -> merge repeats -> group by stall.
Code owns the stock list: the model only reports what it can read in a frame, and
prices that disagree across frames are flagged, never averaged.
"""
import difflib
import json
import re
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import tf

FRAME_PROMPT = """You are reading ONE frame from a phone video of someone walking past market stalls.

Return JSON only, in this shape:
{"signs": [string],
 "items": [{"name": string, "stall_sign": string or null, "price_text": string or null,
            "price_gbp": number or null, "currency": "GBP"|"EUR"|"USD"|"CAD"|"TWD"|other ISO code or null,
            "unit": string or null, "deal": string or null,
            "stock_level": "full"|"low"|"empty"|"unknown", "confidence": "high"|"medium"|"low"}]}

Rules:
- signs: every stall name sign visible in this frame, left to right, exactly as written.
- items: one entry per product whose label you can read. Skip any label cut off by the edge of the frame.
- stall_sign: the sign the item sits under (the nearest sign above or behind it), else null.
- price_text: the price exactly as written (e.g. "£1.50/kg", "3 for £2", "80p bunch").
- price_gbp: the price as a number in the currency shown (field name kept for history), and set currency (80p -> 0.8; "3 for £2" -> 0.67; "£4 per 200g" -> 4), else null.
- unit: "kg", "each", "bunch", "punnet", "100g", "200g", "tub", "loaf", if written.
- deal: multi-buy or offer text if written, else null.
- If you can't read a price, set price_text and price_gbp to null. Never guess a price.
- If one card shows two units (e.g. "£2.65 kg £1.20 lb"), keep both in price_text and set price_gbp and unit to the per-kg one.
- For an empty slot, tray or dispenser, name the product it holds or is labelled for if you can tell, and set stock_level "empty".
- stock_level: how much is left on its shelf, tray, dispenser or slot. "empty" if the labelled slot or dispenser has none left.
- Products with no price card still count: list them with price_text and price_gbp null.
- name: brand and product as printed on the pack (e.g. "Walkers Ready Salted crisps"). If no brand is readable, describe it briefly and set confidence low.
- confidence low = partly hidden or blurry.
"""

NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}


def extract_frames(video: Path, out_dir: Path, fps: float = 1.0, width: int = 1280) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f_*.jpg"):
        old.unlink()
    if is_photo(video):  # a photo: read it whole, then as 4 overlapping tiles at full detail
        from PIL import Image
        img = Image.open(video).convert("RGB")
        W, H = img.size
        whole = img.copy()
        whole.thumbnail((1600, 1600))
        whole.save(out_dir / "f_0001.jpg", quality=88)
        tw, th = int(W * 0.58), int(H * 0.58)
        for k, (x, y) in enumerate([(0, 0), (W - tw, 0), (0, H - th), (W - tw, H - th)], start=2):
            tile = img.crop((x, y, x + tw, y + th))
            tile.thumbnail((1600, 1600))
            tile.save(out_dir / f"f_{k:04d}.jpg", quality=88)
        return sorted(out_dir.glob("f_*.jpg"))
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
         "-vf", f"fps={fps},scale={width}:-2", "-q:v", "3", str(out_dir / "f_%04d.jpg")],
        check=True,
    )
    return sorted(out_dir.glob("f_*.jpg"))


def is_photo(path: Path) -> bool:
    return path.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic", ".webp")


def read_frame(frame: Path) -> dict:
    content = [{"type": "text", "text": FRAME_PROMPT}, tf.image_part(frame)]
    attempts = [(tf.VISION_MODEL, 0.0), (tf.VISION_MODEL, 0.3), (tf.VISION_FALLBACK, 0.0)]
    err = "no model tried"
    for model, temp in attempts:
        try:
            data = tf.parse_json(tf.chat(model, content, temperature=temp, extra=NO_THINKING))
            if isinstance(data, dict):
                data.setdefault("items", [])
                data.setdefault("signs", [])
                data["frame"] = frame.name
                data["model"] = model
                return data
        except Exception as e:  # noqa: BLE001 - retry, then fall back, then record the failure
            err = f"{model}: {e}"
    return {"frame": frame.name, "signs": [], "items": [], "error": err}


def norm(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    n = re.sub(r"\s+", " ", n)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in n.split()]
    return " ".join(words)


def canonical_signs(readings: list[dict]) -> dict[str, str]:
    """Map each sign as read (often cut off: "lly's Fresh Fish", "& Veg") to the fullest version seen."""
    seen = Counter()
    for r in readings:
        for s in r.get("signs", []):
            if s and s.strip():
                seen[s.strip()] += 1
    full = sorted(seen, key=lambda s: (-len(s), -seen[s]))
    mapping: dict[str, str] = {}
    canon: list[str] = []
    for s in full:
        ns = norm(s)
        target = None
        for c in canon:
            nc = norm(c)
            if ns and (ns in nc or difflib.SequenceMatcher(None, ns, nc).ratio() > 0.6
                       or (len(ns) >= 4 and nc.endswith(ns[-8:]))):
                target = c
                break
        if target is None:
            canon.append(s)
            target = s
        mapping[s] = target
    return mapping


def _same_item(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    if difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85:
        return True
    return len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na)


def merge(readings: list[dict], drop_one_offs: bool = True) -> dict:
    signs = canonical_signs(readings)
    current = "Unknown stall"
    order: list[str] = []
    groups: dict[str, list[list[dict]]] = defaultdict(list)  # stall -> list of item groups
    for r in readings:
        frame_signs = [signs.get(s.strip(), s.strip()) for s in r.get("signs", []) if s and s.strip()]
        for it in r.get("items", []):
            if not it.get("name"):
                continue
            own = signs.get((it.get("stall_sign") or "").strip())
            stall: str = own or (frame_signs[0] if len(frame_signs) == 1 else current)
            if stall not in order:
                order.append(stall)
            for g in groups[stall]:
                if any(_same_item(it["name"], x["name"]) for x in g):
                    g.append({**it, "frame": r["frame"]})
                    break
            else:
                groups[stall].append([{**it, "frame": r["frame"]}])
        if frame_signs:
            current = frame_signs[-1]
            if current not in order:
                order.append(current)

    rank = {"high": 3, "medium": 2, "low": 1}
    out = {"stalls": []}
    for s in order:
        items = []
        for seen in groups[s]:
            prices = [round(x["price_gbp"], 2) for x in seen if isinstance(x.get("price_gbp"), (int, float))]
            counts = Counter(prices)
            flags = []
            price = counts.most_common(1)[0][0] if counts else None
            if len(counts) > 1:
                flags.append(f"price differs across frames: {sorted(counts)}")
            if not counts:
                flags.append("price not readable")
            if all(x.get("confidence") == "low" for x in seen):
                flags.append("only seen blurry or partly hidden")
            # the name: most common full-length reading, preferring confident ones
            best = max(seen, key=lambda x: (rank.get(x.get("confidence"), 0), len(x["name"])))
            items.append({
                "name": best["name"],
                "price_gbp": price,
                "price_text": max((x["price_text"] for x in seen if x.get("price_text") and (price is None or round(x.get("price_gbp") or -1, 2) == price)), key=len, default=best.get("price_text")),
                "unit": best.get("unit"),
                "currency": next((x["currency"] for x in seen if x.get("currency")), None),
                "deal": next((x["deal"] for x in seen if x.get("deal")), None),
                "stock_level": Counter(x.get("stock_level") or "unknown" for x in seen).most_common(1)[0][0],
                "seen_in_frames": len({x["frame"] for x in seen}),
                "needs_check": flags,
            })
        keep = [i for i in items if not (drop_one_offs and i["seen_in_frames"] == 1
                                         and "only seen blurry or partly hidden" in i["needs_check"])]
        out.setdefault("possible", []).extend({**i, "stall": s} for i in items if i not in keep)
        if keep:
            out["stalls"].append({"stall": s, "items": sorted(keep, key=lambda i: i["name"].lower())})
    _dedupe_across_stalls(out)
    return out


def _dedupe_across_stalls(out: dict) -> None:
    """Same item at the same price on two stalls is usually a frame straddling the boundary:
    keep it where it was seen most. Different prices = genuinely two stalls, keep both."""
    flat = [(s, i) for s in out["stalls"] for i in s["items"]]
    for s1, i1 in flat:
        for s2, i2 in flat:
            if s1 is s2 or i1 is i2 or not _same_item(i1["name"], i2["name"]):
                continue
            if i1["price_gbp"] != i2["price_gbp"]:
                continue
            loser, lose_stall = (i1, s1) if i1["seen_in_frames"] < i2["seen_in_frames"] else (i2, s2)
            if loser in lose_stall["items"]:
                lose_stall["items"].remove(loser)
    out["stalls"] = [s for s in out["stalls"] if s["items"]]


DEDUPE_PROMPT = """These product names were read from overlapping photos of the same shelves, so some are the
same product named differently (e.g. "Alpro almond drink carton" and "Alpro Deliciously Fresh Taste almond drink").

{names}

Return JSON only: {{"groups": [[ids of names that are the SAME product], ...]}}. Only group true duplicates:
different flavours, sizes or brands stay separate. Leave singletons out."""


def dedupe(stock: dict) -> dict:
    """One text-model pass per stall to merge near-duplicate names the string match missed.
    The model only groups ids; code does the merge and keeps the card prices it already had."""
    for st in stock["stalls"]:
        items = st["items"]
        if len(items) < 3:
            continue
        names = "\n".join(f"{k}: {i['name']}" for k, i in enumerate(items))
        try:
            data = tf.parse_json(tf.chat(tf.TEXT_MODEL, DEDUPE_PROMPT.format(names=names), max_tokens=600,
                                         extra=NO_THINKING))
        except Exception:  # noqa: BLE001 - dedupe is a nicety; keep the list as it is
            continue
        drop = set()
        for g in data.get("groups", []) if isinstance(data, dict) else []:
            ids = sorted({k for k in g if isinstance(k, int) and 0 <= k < len(items) and k not in drop})
            if len(ids) < 2:
                continue
            prices = {items[k]["price_gbp"] for k in ids if items[k]["price_gbp"] is not None}
            if len(prices) > 1:
                continue  # different prices: not safe to merge
            keep = max(ids, key=lambda k: (items[k]["price_gbp"] is not None, items[k]["seen_in_frames"], len(items[k]["name"])))
            for k in ids:
                if k != keep:
                    items[keep]["seen_in_frames"] += items[k]["seen_in_frames"]
                    items[keep].setdefault("also_read_as", []).append(items[k]["name"])
                    drop.add(k)
            levels = [items[k].get("stock_level") for k in ids]
            for lv in ("empty", "low"):
                if lv in levels:
                    items[keep]["stock_level"] = lv
                    break
        st["items"] = [i for k, i in enumerate(items) if k not in drop]
    return stock


def run(video: Path, out: Path, fps: float = 1.0, workers: int = 8) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    frames = extract_frames(video, out / "frames", fps=fps)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        readings = list(ex.map(read_frame, frames))
    (out / "readings.json").write_text(json.dumps(readings, indent=2))
    stock = dedupe(merge(readings, drop_one_offs=not is_photo(video)))
    stock["source"] = {"video": video.name, "frames": len(frames), "fps": fps,
                       "errors": [r["frame"] for r in readings if r.get("error")]}
    (out / "stock.json").write_text(json.dumps(stock, indent=2))
    return stock
