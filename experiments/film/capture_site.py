"""Record the live site for the walk beat: load, then a slow scroll through the stock list.

    uv run --with playwright python capture_site.py [url] [seconds]
Writes capture/site.webm (1920x1080) and capture/site_*.png stills. Read-only: it doesn't
click anything that makes a paid call.
"""
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://stallwalk.kashifnazir.com/"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 9
OUT = Path(__file__).resolve().parent / "capture"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
                        record_video_dir=str(OUT / "raw"), record_video_size={"width": 1920, "height": 1080})
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "site_top.png"))
    height = page.evaluate("document.body.scrollHeight")
    steps = int(SECS * 30)
    target = min(height - 1080, 2600)
    t0 = time.time()
    for i in range(steps):
        page.evaluate(f"window.scrollTo(0, {int(target * (i + 1) / steps)})")
        page.wait_for_timeout(1000 / 30)
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "site_scrolled.png"))
    vid = page.video.path()
    ctx.close()
    b.close()
shutil.copyfile(vid, OUT / "site.webm")
print("ok", OUT / "site.webm", round(time.time() - t0, 1), "s scroll, page height", height)
