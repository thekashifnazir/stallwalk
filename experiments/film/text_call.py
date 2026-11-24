"""One text-only ElevenLabs conversation with the stallwalk agent: does a tool reach Cloud Run?"""
import asyncio, json, os, sys, time
sys.path.insert(0, "/Users/kash/Code/sandbox/stallwalk")
from stallwalk import tf  # noqa: loads .env
import websockets

AGENT = json.load(open("/Users/kash/Code/sandbox/stallwalk/voice/agent.json"))["agent_id"]
URL = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={AGENT}"

async def main():
    async with websockets.connect(URL, additional_headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}) as ws:
        await ws.send(json.dumps({"type": "conversation_initiation_client_data",
                                  "conversation_config_override": {"conversation": {"text_only": True}}}))
        sent = False
        t0 = time.time()
        while time.time() - t0 < 45:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            except asyncio.TimeoutError:
                break
            t = msg.get("type")
            if t == "ping":
                await ws.send(json.dumps({"type": "pong", "event_id": msg["ping_event"]["event_id"]}))
            elif t == "conversation_initiation_metadata" and not sent:
                print("conv", msg["conversation_initiation_metadata_event"]["conversation_id"])
            elif t == "agent_response":
                text = msg["agent_response_event"]["agent_response"]
                print("AGENT:", text[:300])
                if not sent:
                    await ws.send(json.dumps({"type": "user_message", "text": "What stalls are on the market today?"}))
                    sent = True
                elif "stall" in text.lower() and len(text) > 60:
                    break
            elif t in ("agent_tool_response", "agent_tool_request", "client_tool_call", "mcp_tool_call"):
                print(t.upper(), json.dumps(msg)[:300])
asyncio.run(main())
