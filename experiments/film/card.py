from pathlib import Path
from playwright.sync_api import sync_playwright
D = Path(__file__).resolve().parent
html = """<html><body style="margin:0;width:1920px;height:1080px;background:radial-gradient(ellipse at 30% 20%,#1d1a14 0%,#0b0b0b 70%);
font-family:Inter,'SF Pro Display',system-ui,sans-serif;color:#fff;display:flex;align-items:center">
<div style="margin-left:150px;margin-right:150px">
<div style="display:inline-block;background:#F5B83D;color:#111;font-size:30px;font-weight:700;padding:10px 22px;border-radius:999px">stallwalk</div>
<div style="font-size:84px;font-weight:800;letter-spacing:-1.5px;line-height:1.08;margin-top:34px">Live market stock:</div>
<div style="font-size:56px;font-weight:700;line-height:1.25;margin-top:18px;color:#e9e2d4">what's on each stall, at what price,<br>and what came in this morning.</div>
<div style="font-size:56px;font-weight:800;line-height:1.25;margin-top:30px;color:#F5B83D">Like a supermarket website, for the market.</div>
</div></body></html>"""
(D / "card.html").write_text(html)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto((D / "card.html").as_uri()); pg.wait_for_timeout(300); pg.screenshot(path=str(D / "live_stock.png")); b.close()
print("ok")
