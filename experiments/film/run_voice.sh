cd /Users/kash/Code/tools/hackathon-kit/video
export KIT_ELEVENLABS_VOICE=$(grep "^KIT_ELEVENLABS_VOICE=" ~/.config/hackathon-kit/env | cut -d= -f2- | tr -d '"'"'")
export ELEVENLABS_API_KEY=$(grep "^ELEVENLABS_API_KEY=" /Users/kash/Code/sandbox/stallwalk/.env | cut -d= -f2- | tr -d '"'"'")
export ELEVENLABS_MODEL=eleven_v4
export KIT_ELEVENLABS_SETTINGS='{"stability":0.4,"similarity_boost":0.8,"style":0.5,"use_speaker_boost":true}'
D=$1
for x in a k b; do python3 tts.py $D/$x.txt $D/$x.mp3 --timestamps || echo "FAIL $x"; done
echo VOICE_DONE
