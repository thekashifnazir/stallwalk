# Film build scripts (the 60 s submission video)

Copied from the build scratchpad on 24 Nov 2026, so paths inside point at that scratchpad. Keys are read from .env files at run time, and none are stored here.

- run_voice.sh: narration in Kash's hackathon-kit voice clone (eleven_v4, delivery tags, stability 0.4, style 0.5), via hackathon-kit/video/tts.py --timestamps.
- run_music.py: an ElevenLabs music bed via hackathon-kit's film_audio.music.
- voice_call.py / text_call.py: one real websocket conversation with the stallwalk ElevenLabs agent (audio + transcript / text only).
- infra_anim.py, transcript_anim.py, card.py: HTML scenes rendered frame-exactly by Playwright (animations paused and seeked per frame), then encoded with ffmpeg.
- capture_site.py: a Playwright screen recording of the live site.
- assemble3.py / assemble8.py: ffmpeg assembly. Clips are placed on the voice clock, music is ducked with sidechaincompress, and karaoke captions come from hackathon-kit/bin/kit-caption. v8 = assemble8.py (assemble7 timeline + split-screen voice beat).
