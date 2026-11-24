"""Per-item catalogue entries from the NVIDIA Catalog Enrichment blueprint.

The blueprint's /vlm/analyze expects one product per image, so we:
1. find the best frame the item was seen in (from the walk's readings),
2. ask the vision model for the item's box in that frame, and crop it,
3. send the crop to the blueprint (running locally on Token Factory models) with the name and
   the card's price as product_data, so the blueprint can't change them.
"""
import io
import json
import os
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

from . import tf
from .walk import NO_THINKING, _same_item

BLUEPRINT = os.environ.get("CATALOG_ENRICHMENT_URL", "http://127.0.0.1:8000").rstrip("/")
RANK = {"high": 3, "medium": 2, "low": 1}

BOX_PROMPT = """Find "{name}" in this market stall photo: the produce or product AND its price card.
Return JSON only: {{"box": [x0, y0, x1, y1]}} in 0-1000 coordinates (0,0 top-left, 1000,1000 bottom-right).
If it isn't in the photo, return {{"box": null}}."""


def best_frame(run_dir: Path, stall: str, name: str) -> Path | None:
    readings = json.loads((run_dir / "readings.json").read_text())
    best, score = None, -1
    for r in readings:
        for it in r.get("items", []):
            if it.get("name") and _same_item(it["name"], name):
                s = RANK.get(it.get("confidence"), 0) * 10 + (5 if stall.lower() in (it.get("stall_sign") or "").lower() else 0)
                if s > score:
                    best, score = r["frame"], s
    return (run_dir / "frames" / best) if best else None


def crop_item(frame: Path, name: str) -> bytes | None:
    data = tf.parse_json(tf.chat(tf.VISION_MODEL, [{"type": "text", "text": BOX_PROMPT.format(name=name)},
                                                   tf.image_part(frame)], max_tokens=200, extra=NO_THINKING))
    box = data.get("box") if isinstance(data, dict) else None
    img = Image.open(frame).convert("RGB")
    if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
        return None
    W, H = img.size
    x0, y0, x1, y1 = (box[0] * W / 1000, box[1] * H / 1000, box[2] * W / 1000, box[3] * H / 1000)
    pad_x, pad_y = (x1 - x0) * 0.15, (y1 - y0) * 0.15
    x0, y0 = max(0, x0 - pad_x), max(0, y0 - pad_y)
    x1, y1 = min(W, x1 + pad_x), min(H, y1 + pad_y)
    if x1 - x0 < 40 or y1 - y0 < 40:
        return None
    buf = io.BytesIO()
    img.crop((int(x0), int(y0), int(x1), int(y1))).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _multipart(fields: dict, file_field: str, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: image/jpeg\r\n\r\n".encode() + file_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def blueprint_analyze(image: bytes, name: str, price: float | None, stall: str) -> dict:
    product = {"title": name, "tags": [stall]}
    if isinstance(price, (int, float)):
        product["price"] = price
    body, ctype = _multipart({
        "locale": "en-GB",
        "product_data": json.dumps(product),
        "brand_instructions": "UK street market stall. Plain, friendly words. Don't invent origin, brand or "
                              "certifications that aren't visible. Keep the title close to the stall's own name for it.",
    }, "image", "item.jpg", image)
    req = urllib.request.Request(f"{BLUEPRINT}/vlm/analyze", data=body, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def enrich_item(run_dir: Path, stall: str, item: dict) -> dict:
    cache_path = run_dir / "enriched.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    key = f"{stall}|{item['name']}"
    if key in cache:
        return {**cache[key], "cached": True}
    frame = best_frame(run_dir, stall, item["name"])
    if not frame:
        return {"error": "item not found in any frame"}
    try:
        crop = crop_item(frame, item["name"])
    except Exception as e:  # noqa: BLE001
        crop, crop_err = None, str(e)
    else:
        crop_err = None
    image = crop or frame.read_bytes()
    try:
        entry = blueprint_analyze(image, item["name"], item.get("price_gbp"), stall)
    except Exception as e:  # noqa: BLE001
        return {"error": f"blueprint call failed: {e}", "frame": frame.name}
    crop_file = None
    if crop:
        crop_file = f"crop-{abs(hash(key)) % 10**8}.jpg"
        (run_dir / "frames" / crop_file).write_bytes(crop)
    out = {
        "stall": stall, "name": item["name"],
        "price_gbp": item.get("price_gbp"), "price_text": item.get("price_text"),  # always the card's, never the blueprint's
        "title": entry.get("title"), "description": entry.get("description"),
        "categories": entry.get("categories", []), "tags": entry.get("tags", []), "colors": entry.get("colors", []),
        "frame": frame.name, "crop": crop_file, "cropped": bool(crop), "crop_error": crop_err,
        "by": "NVIDIA Retail Catalog Enrichment blueprint (/vlm/analyze) on Token Factory models",
    }
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    cache[key] = out
    cache_path.write_text(json.dumps(cache, indent=2))
    return out
