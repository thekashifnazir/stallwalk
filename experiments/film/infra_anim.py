import subprocess, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, "/private/tmp/claude-501/-Users-kash-Code-sandbox-hackathonideas/a7ec0457-3ecf-4043-b961-1f10169feee7/scratchpad/video/cards")
from make_cards import FONT, AMBER, bg

D = Path(__file__).resolve().parent
FR = D / "infra_frames"
FPS, DUR = 30, 17.4

def box(cls, title, sub, accent=False, w=300, extra=""):
    border = AMBER if accent else "rgba(255,255,255,.35)"
    fill = "rgba(244,182,63,.13)" if accent else "rgba(255,255,255,.08)"
    return (f'<div class="{cls} in" style="width:{w}px;box-sizing:border-box;background:{fill};border:2px solid {border};'
            f'border-radius:20px;padding:22px 24px">'
            f'<div style="font-size:34px;font-weight:800;line-height:1.15">{title}</div>'
            f'<div style="font-size:24px;opacity:.9;margin-top:8px;line-height:1.3">{sub}</div>{extra}</div>')

def arrow(cls):
    return (f'<div class="{cls} in arr" style="position:relative;width:74px;height:60px;margin:0 6px">'
            f'<div style="position:absolute;left:6px;right:14px;top:28px;height:4px;background:{AMBER};border-radius:2px"></div>'
            f'<div style="position:absolute;right:4px;top:18px;width:0;height:0;border-top:12px solid transparent;'
            f'border-bottom:12px solid transparent;border-left:16px solid {AMBER}"></div>'
            f'<div class="{cls}t tok" style="position:absolute;left:0;top:21px;width:18px;height:18px;border-radius:50%;'
            f'background:{AMBER};box-shadow:0 0 18px 6px rgba(244,182,63,.75)"></div></div>')

nebius_sub = ('NVIDIA Nemotron VL reads the frames<br>'
              '<span class="bp" style="display:inline-block;border-radius:8px;padding:2px 6px;margin-left:-6px">'
              'NVIDIA Retail Catalog Enrichment + Agentic Commerce blueprints</span>')

T = {"b": 0.3, "a1": 0.9, "c": 1.2, "a2": 1.75, "r": 2.0, "a3": 3.1, "n": 3.5, "a4": 11.45, "t": 11.85, "title": 0.0}
css = f"""
@keyframes inK {{ from {{opacity:0; transform:translateY(34px) scale(.96)}} to {{opacity:1; transform:none}} }}
@keyframes tokK {{ 0% {{left:0; opacity:0}} 10% {{opacity:1}} 85% {{left:56px; opacity:1}} 100% {{left:56px; opacity:0}} }}
@keyframes bpK {{ from {{background:rgba(244,182,63,0); color:#fff}} to {{background:rgba(244,182,63,.95); color:#111}} }}
@keyframes glowK {{ 0% {{box-shadow:0 0 0 0 rgba(244,182,63,0)}} 40% {{box-shadow:0 0 0 10px rgba(244,182,63,.45)}} 100% {{box-shadow:0 0 0 0 rgba(244,182,63,0)}} }}
.in {{ opacity:0; animation: inK .55s cubic-bezier(.16,1,.3,1) both; }}
.tok {{ opacity:0; animation: tokK .7s cubic-bezier(.45,0,.55,1) both; }}
.bp {{ animation: bpK .5s ease-out both; animation-delay:{T['n'] + 4.8}s; }}
"""
for k, t in T.items():
    css += f".{k} {{ animation-delay:{t}s; }}\n.{k}t {{ animation-delay:{t + 0.15}s; }}\n"
css += f".n {{ animation: inK .55s cubic-bezier(.16,1,.3,1) {T['n']}s both, glowK 1.2s ease-out {T['n']+0.5}s 1; }}\n"
css += f".t {{ animation: inK .55s cubic-bezier(.16,1,.3,1) {T['t']}s both, glowK 1.2s ease-out {T['t']+0.5}s 1; }}\n"

left = (f'<div style="display:flex;flex-direction:column;gap:18px">'
        f'{box("b", "Browser", "phone or laptop", w=270)}{box("b", "ElevenLabs", "voice agent, 8 tools", w=270)}</div>')
row = (f'<div style="display:flex;align-items:center">{left}{arrow("a1")}'
       f'{box("c", "Cloudflare", "stallwalk.kashifnazir.com", w=300)}{arrow("a2")}'
       f'{box("r", "Google Cloud Run", "the stallwalk app, London", w=290, accent=True)}{arrow("a3")}'
       f'<div style="display:flex;flex-direction:column;gap:18px">'
       f'{box("n", "Nebius Token Factory", nebius_sub, w=520, accent=True)}'
       f'{box("t", "Tavily", "web check on UK supermarket sites", w=520)}</div></div>')
back = (f'<div style="position:absolute;inset:0;background:url(\'{bg}\') center/cover;'
        f'display:none"></div>')
html = (f'<!doctype html><meta charset="utf-8"><style>{css}</style>'
        f'<body style="margin:0;width:1920px;height:1080px;overflow:hidden;{FONT};background:radial-gradient(ellipse at 30% 20%,#1d1a14 0%,#0b0b0b 70%);color:#fff">{back}'
        f'<div class="title in" style="position:absolute;left:100px;top:90px">'
        f'<div style="display:inline-block;background:{AMBER};color:#111;font-size:26px;font-weight:700;padding:10px 20px;border-radius:999px">How it\'s built</div>'
        f'<div style="font-size:58px;font-weight:800;margin-top:22px;letter-spacing:-1px">NVIDIA on Nebius Token Factory,<br><span style="color:{AMBER}">hosted on Google Cloud Run</span></div></div>'
        f'<div style="position:absolute;left:60px;right:20px;top:360px;zoom:1.06">{row}</div><div class="t in" style="position:absolute;left:100px;right:100px;top:790px;font-size:30px;line-height:1.35;color:#e9e2d4"><b style="color:#F5B83D">Why this works:</b> no GPU to run. All the AI runs on Nebius Token Factory, so the app itself is a small Google Cloud Run service. Prices come from stall cards, checked by code.</div></body>')
(D / "infra_anim.html").write_text(html)

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto((D / "infra_anim.html").as_uri()); pg.wait_for_timeout(500)
    n = int(DUR * FPS)
    for i in range(n):
        t = i / FPS * 1000
        pg.evaluate(f"document.getAnimations().forEach(a => {{a.pause(); a.currentTime = {t};}})")
        pg.screenshot(path=str(FR / f"f{i:04d}.png"))
    b.close()
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(FR / "f%04d.png"),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(D / "infra.mp4")], check=True)
print("ok")
