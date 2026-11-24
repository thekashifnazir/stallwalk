"""stallwalk v5: eleven_v4 narration (sped 1.08), Kash line, real agent excerpts, ducked music, motion clips."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

S = Path(__file__).resolve().parent; V5 = S / "v5"; SH = V5 / "shots"; AGW = S.parent / "ws" / "agent_reply.wav"
sys.path.insert(0, "/Users/kash/Code/tools/hackathon-kit/remotion/patterns")
W, H, FPS, TEMPO, END = 1920, 1080, 30, 1.08, 59.5
def words(n): return [w for w in json.loads((V5 / f"{n}.words.json").read_text())["words"] if not w[0].startswith("[")]
# audio: (file, src_from, src_to, film_at, tempo, words, caption)
AUD = [(V5 / "a.mp3", 0.10, 29.95, 0.25, TEMPO, words("a"), True),
       (V5 / "k.mp3", 0.10, 2.75, 28.00, 1.0, words("k"), True),
       (AGW, 8.85, 17.85, 30.90, 1.0, None, False),
       (AGW, 30.00, 39.85, 40.10, 1.0, None, False),
       (V5 / "b.mp3", 0.02, 8.10, 50.10, TEMPO, words("b"), True)]
def f_a(t): return 0.25 + (t - 0.10) / TEMPO
def pick(p, fb): return p if Path(p).exists() else fb
VIS = [("img", S / "A" / "A1_hook.png", 0, 4.2),
       ("vid", pick(SH / "hero.mp4", S / "capture" / "site_top.png"), 4.2, round(f_a(6.7), 2)),
       ("vid", pick(SH / "infra.mp4", S / "cards" / "infra.png"), round(f_a(6.7), 2), round(f_a(25.4), 2)),
       ("vid", pick(SH / "market.mp4", S / "capture" / "site_scrolled.png"), round(f_a(25.4), 2), 27.5),
       ("vid", pick(SH / "transcript.mp4", S / "transcript" / "t2.png"), 27.5, 50.0),
       ("img", S / "cards" / "proof.png", 50.0, round(50.10 + (4.6 - 0.02) / TEMPO, 2)),
       ("img", S / "cards" / "end.png", round(50.10 + (4.6 - 0.02) / TEMPO, 2), END)]
def run(c): subprocess.run(c, check=True)
def main(out):
    b = S / "build5"; b.mkdir(exist_ok=True); parts = []
    for i, (kind, src, a, z) in enumerate(VIS):
        dur = round(z - a, 3); p = b / f"v{i:02d}.mp4"; src = Path(src)
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x111111,"
              f"setsar=1,fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.18,fade=t=out:st={max(dur-0.18,0)}:d=0.18")
        if src.suffix in (".png", ".jpg"):
            run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-t", str(dur), "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(p)])
        else:
            run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf", vf.replace("fade=t=in", "tpad=stop_mode=clone:stop_duration=40,fade=t=in"), "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(p)])
        parts.append(p)
    (b / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(b / "list.txt"), "-c", "copy", str(b / "silent.mp4")])
    ins, fl = [], []
    for k, (f, s0, s1, at, tempo, _, _) in enumerate(AUD):
        ins += ["-i", str(f)]
        fl.append(f"[{k}:a]atrim={s0}:{s1},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo,"
                  f"atempo={tempo},loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=0.03,adelay={int(at*1000)}|{int(at*1000)}[v{k}]")
    vmix = "".join(f"[v{k}]" for k in range(len(AUD))) + f"amix=inputs={len(AUD)}:normalize=0,apad,atrim=0:{END},asplit=2[voice][sc]"
    import film_audio as fa
    fa.fit_music(str(V5 / "music_raw.mp3"), str(b / "music.wav"), total=END, bpm=120)
    ins += ["-i", str(b / "music.wav")]; m = len(AUD)
    music = (f"[{m}:a]aresample=44100,aformat=channel_layouts=stereo,loudnorm=I=-20:TP=-3,volume=0.55,"
             f"afade=t=out:st={END-1.5}:d=1.5[bed];[bed][sc]sidechaincompress=threshold=0.03:ratio=10:attack=25:release=350:makeup=1[duck];"
             f"[voice][duck]amix=inputs=2:normalize=0,alimiter=limit=0.9[aout]")
    run(["ffmpeg", "-loglevel", "error", "-y", *ins, "-filter_complex", ";".join(fl) + ";" + vmix + ";" + music,
         "-map", "[aout]", "-t", str(END), "-c:a", "pcm_s16le", str(b / "audio.wav")])
    run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(b / "silent.mp4"), "-i", str(b / "audio.wav"), "-map", "0:v", "-map", "1:a",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(END), str(b / "mixed.mp4")])
    cues = []
    for f, s0, s1, at, tempo, wl, cap in AUD:
        if not cap:
            continue  # the agent's words are on the animated transcript, so no caption there
        ws = [[w, round(at + (a0 - s0) / tempo, 3), round(at + (a1 - s0) / tempo, 3)] for w, a0, a1 in wl if s0 <= a0 < s1]
        cur = []
        for w in ws:  # cues never cross a clip boundary
            cur.append(w)
            if len(cur) >= 6 or w[0].endswith((".", "?", "!", ":", ",")) and len(cur) >= 3:
                cues.append({"text": " ".join(x[0] for x in cur), "start": cur[0][1], "end": cur[-1][2], "words": cur}); cur = []
        if cur: cues.append({"text": " ".join(x[0] for x in cur), "start": cur[0][1], "end": cur[-1][2], "words": cur})
    (b / "cues.json").write_text(json.dumps(cues, indent=1))
    run(["/Users/kash/Code/tools/hackathon-kit/bin/kit-caption", "--video", str(b / "mixed.mp4"), "--out", str(out), "--cues", str(b / "cues.json"),
         "--size", "46", "--highlight", "#F5B83D", "--overwrite"])
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
    print(out, f"{d:.2f}s"); assert d <= 60.0
if __name__ == "__main__": main(Path(sys.argv[1]))
