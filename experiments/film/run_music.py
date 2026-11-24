import sys
sys.path.insert(0, "/Users/kash/Code/tools/hackathon-kit/remotion/patterns")
import film_audio as fa
out = sys.argv[1]
p = fa.music("Warm, upbeat, major-key indie electronic bed for a product demo: plucked synth, light claps and shaker, soft bass, optimistic and bright, steady 120 BPM, no vocals, no build-up, consistent energy throughout", out + "/music_raw.mp3", seconds=64)
print("lead silence", fa.lead_silence(p)); print("MUSIC_DONE", p)
