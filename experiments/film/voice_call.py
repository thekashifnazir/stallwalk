"""One real conversation with the stallwalk agent, recording the agent's own audio and transcript."""
import asyncio, base64, json, os, sys, time
sys.path.insert(0, "/Users/kash/Code/sandbox/stallwalk")
from stallwalk import tf  # noqa: loads .env
import websockets

OUT = os.path.dirname(os.path.abspath(__file__))
AGENT = json.load(open("/Users/kash/Code/sandbox/stallwalk/voice/agent.json"))["agent_id"]
URL = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={AGENT}"
LINE = "I'm making moules frites for four tonight."

async def main():
    audio, log, fmt = bytearray(), [], None
    async with websockets.connect(URL, additional_headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, max_size=None) as ws:
        await ws.send(json.dumps({"type": "conversation_initiation_client_data"}))
        sent, t_sent, last_audio, final = False, None, None, False
        t0 = time.time()
        while time.time() - t0 < 90:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
            except asyncio.TimeoutError:
                if final:
                    break
                continue
            t = msg.get("type")
            if t == "ping":
                await ws.send(json.dumps({"type": "pong", "event_id": msg["ping_event"]["event_id"]}))
            elif t == "conversation_initiation_metadata":
                m = msg["conversation_initiation_metadata_event"]
                fmt = m.get("agent_output_audio_format"); print("conv", m["conversation_id"], fmt)
            elif t == "audio" and sent:
                audio += base64.b64decode(msg["audio_event"]["audio_base_64"]); last_audio = time.time()
            elif t == "agent_response":
                text = msg["agent_response_event"]["agent_response"]
                log.append({"role": "agent", "t": round(time.time() - (t_sent or time.time()), 2), "text": text})
                print("AGENT:", text)
                if not sent:
                    await asyncio.sleep(1.0)
                    await ws.send(json.dumps({"type": "user_message", "text": LINE}))
                    sent, t_sent = True, time.time()
                    log.append({"role": "user", "t": 0, "text": LINE})
                elif any(log_e.get("tool") for log_e in log):
                    final = True
            elif t == "agent_tool_response":
                r = msg["agent_tool_response"]; log.append({"role": "tool", "tool": r["tool_name"], "status": r.get("status"), "is_error": r.get("is_error")})
                print("TOOL", r["tool_name"], r.get("status"), r.get("is_error"))
            if final and last_audio and time.time() - last_audio > 3:
                break
    open(os.path.join(OUT, "agent_reply.raw"), "wb").write(audio)
    json.dump({"format": fmt, "log": log}, open(os.path.join(OUT, "agent_reply.json"), "w"), indent=1)
    print("bytes", len(audio))
asyncio.run(main())
