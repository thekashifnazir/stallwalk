import json, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
D = Path(__file__).resolve().parent
FPS, DUR = 30, 30.1
user = "I'm making moules frites for four tonight.".split()
U = [[w, 0.6 + i * (1.8 / (len(user) - 1)), False] for i, w in enumerate(user)]
A1 = [["You", 2.95, False], ["can", 3.093, False], ["skip", 3.236, True], ["the", 3.45, False], ["shallots", 3.521, False], ["and", 4.021, False], ["double", 4.2, False], ["cream,", 4.379, False], ["they're", 4.986, False], ["in", 5.129, False], ["the", 5.2, False], ["stockroom,", 5.379, False], ["but", 6.2, False], ["butter,", 6.45, False], ["sunflower", 6.986, False], ["oil", 7.45, False], ["and", 7.736, False], ["lemons", 7.95, False], ["are", 8.379, False], ["low.", 8.521, True], ["Go", 9.307, False], ["to", 9.414, False], ["Billy's", 9.521, True], ["Fresh", 9.879, True], ["Fish", 10.164, True], ["for", 10.379, False], ["the", 10.486, False], ["mussels,", 10.593, False], ["then", 11.271, False], ["Green's", 11.45, True], ["Veg", 11.807, True], ["for", 12.093, False], ["the", 12.2, False], ["potatoes,", 12.343, False], ["garlic,", 13.021, False], ["parsley", 13.557, False], ["and", 13.879, False], ["lemon.", 14.021, False], ["The", 14.807, False], ["market", 14.879, False], ["total", 15.164, False], ["is", 15.521, False], ["\u00a314.90.", 15.736, True]]
A2 = [["Pick", 17.1, False], ["up", 17.314, False], ["wine", 17.457, False], ["from", 17.85, False], ["Aldi", 18.029, True], ["or", 18.457, False], ["Waitrose,", 18.6, True], ["at", 19.457, False], ["roughly", 19.636, False], ["\u00a34.29", 20.029, True], ["to", 21.1, False], ["\u00a312.50,", 21.279, True], ["and", 22.707, False], ["butter", 22.957, False], ["from", 23.314, False], ["Tesco,", 23.529, True], ["at", 24.136, False], ["about", 24.243, False], ["\u00a31.95", 24.529, True], ["to", 25.671, False], ["\u00a34.50.", 25.886, True], ["That's", 27.243, False], ["from", 27.457, False], ["a", 27.564, False], ["Tavily", 27.636, True], ["web", 28.029, False], ["search", 28.243, False], ["of", 28.6, False], ["UK", 28.743, False], ["supermarkets.", 29.1, False]]
BG = (D / "bg_site.png").as_uri()
html = f"""<html><head><style>
*{{box-sizing:border-box}}body{{margin:0;width:960px;height:1080px;overflow:hidden;font-family:Inter,'SF Pro Display',system-ui,sans-serif;position:relative;background:#111}}
.bg{{display:none}}
.dim{{position:absolute;inset:0;background:#141210}}
.tag{{position:absolute;left:40px;top:60px;background:#f5b83d;color:#111;font-weight:700;font-size:28px;padding:7px 18px;border-radius:9px}}
.b{{position:absolute;border-radius:24px;padding:22px 28px;font-size:33px;line-height:1.3;color:#fff}}
.who{{font-size:23px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#bbb;margin-bottom:10px}}
#u{{left:40px;top:130px;width:880px;background:#2a2a2a}}
.a{{left:40px;width:880px;background:#000;border:3px solid #f5b83d}}.a .who{{color:#f5b83d}}
#a1{{top:290px}}#a2{{top:290px}}
.w{{opacity:0}}.hl{{color:#f5b83d;font-weight:700}}
#pulse{{position:absolute;left:40px;top:300px;font-size:26px;color:#f5b83d;padding:12px 22px;border:2px dashed #f5b83d;border-radius:40px;opacity:0}}
.foot{{position:absolute;left:40px;right:40px;bottom:50px;font-size:19px;color:#aaa}}
</style></head><body><div class=bg></div><div class=dim></div>
<div class=tag id=tag>Real conversation with the stallwalk voice agent</div>
<div class=b id=u><div class=who>You (voice)</div><span id=ut></span></div>
<div id=pulse>checking the stockroom and the market…</div>
<div class='b a' id=a1><div class=who>stallwalk</div><span id=a1t></span></div>
<div class='b a' id=a2><div class=who>stallwalk <span style="margin-left:14px;background:#f5b83d;color:#111;border-radius:6px;padding:2px 10px;letter-spacing:.02em">Tavily web search</span></div><span id=a2t></span></div>
<div class=foot>Real reply from the stallwalk agent, excerpted and voiced in its own voice. Stalls and prices made up for the demo. Web estimates are online prices, not stall prices.</div>
<script>
const U={json.dumps(U)},A1={json.dumps(A1)},A2={json.dumps(A2)};
function fill(id,arr){{document.getElementById(id).innerHTML=arr.map((x,i)=>`<span class="w${{x[2]?' hl':''}}" id="${{id}}_${{i}}">${{x[0]}}</span>`).join(' ')}}
fill('ut',U);fill('a1t',A1);fill('a2t',A2);
const c=(x)=>Math.max(0,Math.min(1,x));const ease=(x)=>1-Math.pow(1-c(x),3);
function words(id,arr,t){{arr.forEach((x,i)=>{{const e=document.getElementById(id+'_'+i);const k=c((t-x[1])/0.12);e.style.opacity=k;}})}}
window.render=function(t){{
 const tag=document.getElementById('tag');tag.style.opacity=c(t/0.3);
 const u=document.getElementById('u');let k=ease((t-0.3)/0.4);
 let uo=k, uy=(1-k)*40;
 // second phase: user bubble out, a1 up and dim, a2 in
 const p2=ease((t-16.8)/0.5);
 uo=uo*(1-p2); u.style.opacity=uo; u.style.transform=`translateY(${{uy - p2*60}}px)`;
 words('ut',U,t);
 const pu=document.getElementById('pulse');pu.style.opacity=(t>=2.8&&t<3.45)?(0.55+0.45*Math.sin((t-2.8)*14)):0;
 const a1=document.getElementById('a1');const k1=ease((t-3.3)/0.35);
 a1.style.opacity=k1*(1-0.55*p2);a1.style.transform=`translateY(${{(1-k1)*40 - p2*180}}px)`;
 words('a1t',A1,t);
 const a2=document.getElementById('a2');const k2=ease((t-16.9)/0.4);
 a2.style.opacity=k2;a2.style.transform=`translateY(${{(1-k2)*40 + 260}}px)`;
 words('a2t',A2,t);
}};render(0);
</script></body></html>"""
(D / "anim.html").write_text(html)
frames = D / "frames"; frames.mkdir(exist_ok=True)
n = int(round(DUR * FPS))
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 960, "height": 1080})
    pg.goto((D / "anim.html").as_uri()); pg.wait_for_timeout(500)
    for i in range(n):
        pg.evaluate(f"render({i / FPS})")
        pg.screenshot(path=str(frames / f"f{i:04d}.png"))
    b.close()
subprocess.run(["ffmpeg","-loglevel","error","-y","-framerate",str(FPS),"-i",str(frames/"f%04d.png"),"-c:v","libx264","-preset","veryfast",
                "-crf","18","-pix_fmt","yuv420p",str(D/"transcript.mp4")],check=True)
print("ok", n)
