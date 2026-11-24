"""Make a synthetic market walk: a wide strip of 3 stalls with price cards, panned into a video.

Made-up stalls and prices, for testing the pipeline before real footage exists.
Writes fixtures/synthetic_strip.png, fixtures/synthetic_walk.mp4 and fixtures/synthetic_truth.json.
"""
import json
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT2 = "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"

STALLS = [
    ("Patel's Fruit & Veg", (46, 125, 50), [
        ("Tomatoes", "£1.80/kg", 1.80), ("Bananas", "5 for £1", 0.20), ("Red Onions", "£1.20/kg", 1.20),
        ("Coriander", "80p bunch", 0.80), ("Avocados", "£1 each", 1.00), ("Strawberries", "£2.50 punnet", 2.50),
    ]),
    ("Billy's Fresh Fish", (21, 101, 192), [
        ("Cod Fillet", "£14.99/kg", 14.99), ("Salmon Fillet", "£18.50/kg", 18.50), ("King Prawns", "£4 per 200g", 4.00),
        ("Mackerel", "£3 each", 3.00), ("Mussels", "£6/kg", 6.00),
    ]),
    ("Rosa's Cheese & Deli", (173, 20, 87), [
        ("Mature Cheddar", "£2.20 per 100g", 2.20), ("Halloumi", "£3.50 each", 3.50), ("Olives", "£2 per tub", 2.00),
        ("Sourdough", "£4.20 loaf", 4.20), ("Feta", "£2.80 each", 2.80),
    ]),
]

W_STALL, H = 1400, 900


def main() -> None:
    random.seed(7)
    img = Image.new("RGB", (W_STALL * len(STALLS), H), (235, 225, 210))
    d = ImageDraw.Draw(img)
    sign_font = ImageFont.truetype(FONT, 64)
    truth = {"stalls": []}
    for si, (name, colour, items) in enumerate(STALLS):
        x0 = si * W_STALL
        d.rectangle([x0 + 40, 30, x0 + W_STALL - 40, 150], fill=colour)
        d.text((x0 + 80, 55), name, font=sign_font, fill="white")
        d.rectangle([x0 + 20, 560, x0 + W_STALL - 20, 600], fill=(120, 80, 50))  # table edge
        truth["stalls"].append({"stall": name, "items": []})
        for ii, (item, price_text, price) in enumerate(items):
            col, row = ii % 3, ii // 3
            cx, cy = x0 + 90 + col * 430, 200 + row * 330
            # produce blob
            for _ in range(14):
                bx, by = cx + random.randint(0, 300), cy + 170 + random.randint(-20, 60)
                d.ellipse([bx, by, bx + 70, by + 55], fill=tuple(random.randint(60, 220) for _ in range(3)))
            # price card, slightly varied
            f = ImageFont.truetype(FONT2 if (ii % 2) else FONT, 40)
            d.rectangle([cx, cy, cx + 330, cy + 150], fill="white", outline="black", width=4)
            d.text((cx + 18, cy + 18), item, font=f, fill="black")
            d.text((cx + 18, cy + 80), price_text, font=f, fill=(200, 0, 0))
            truth["stalls"][-1]["items"].append({"name": item, "price_text": price_text, "price_gbp": price})
    strip = HERE / "synthetic_strip.png"
    img.save(strip)
    (HERE / "synthetic_truth.json").write_text(json.dumps(truth, indent=2))
    # Pan a 1280-wide window across the strip over 16 s, like walking past.
    total = img.width - 1280
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", str(strip), "-t", "16",
        "-vf", f"crop=1280:{H}:x='min(t*{total / 16:.1f},{total})':y=0,format=yuv420p", "-r", "25",
        str(HERE / "synthetic_walk.mp4"),
    ], check=True)
    print("wrote", strip.name, "synthetic_walk.mp4", "synthetic_truth.json")


if __name__ == "__main__":
    main()
