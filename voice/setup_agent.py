"""Create (or update) the ElevenLabs "stallwalk" voice agent and its four webhook tools.

    uv run python voice/setup_agent.py --public-url https://<tunnel>.trycloudflare.com [--test]

Pattern from the Dwelly / greatagent-voice setup script. ELEVENLABS_API_KEY comes from
stallwalk/.env (loaded by stallwalk.tf). Ids only (no secrets) go to voice/agent.json, and a
re-run with a new tunnel URL updates the tools and agent in place. The tools are read-only
GETs on the app's /api/agent/* endpoints, each answering {"answer": "..."}.
--test runs two text-only ElevenLabs agent tests (no audio) against the agent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stallwalk import tf  # noqa: E402,F401  (loads .env into os.environ)

API = "https://api.elevenlabs.io/v1/convai"
IDS = Path(__file__).with_name("agent.json")
VOICE_LLM = "claude-sonnet-5-5"  # same choice as the Dwelly agent: it keeps to "only say what the tool said"
NAME = "stallwalk"
FIRST_MESSAGE = "Hi, I've walked the market. Tell me what you'd like to cook, or ask what's on the stalls."

PROMPT = (
    "You're the voice of stallwalk, in UK English. You help a cook plan a meal from what's on the market "
    "today, help shoppers find what's on the stalls, and help a kitchen manager see what's run out.\n"
    "Rules:\n"
    "- ALWAYS use a tool before answering anything about stock, stalls, prices, the stockroom, restocking "
    "or orders. Never say a price, stall or quantity that isn't in a tool's answer.\n"
    "- Meal flow, when someone says what they want to cook: (1) say ONE short line first, like 'Give me "
    "a few seconds, I'm checking the stockroom and the market'; (2) work out the full ingredient list with "
    "quantities for the number of people yourself (ask how many only if they haven't said; default to 4), "
    "in market units: garlic in bulbs (never cloves), potatoes, mussels and fish in kg, herbs in bunches, "
    "wine in bottles, butter and cheese in grams, cream and oil in ml or litres; "
    "(3) call plan_meal ONCE with that list; (4) read back a short summary that LEADS with the tool's "
    "first sentence (what to skip because it's in the stockroom, and what's low), then the market total "
    "and the top items, then what's a web estimate. Don't call other tools "
    "for the dish unless they ask a follow-up.\n"
    "- Follow-ups only: what_goes_with for ideas, find_item for one product, web_find for items no stall "
    "has, check_stockroom or split_order for a changed list, list_stalls for what stalls there are, "
    "whats_run_out for the office kitchen restock list.\n"
    "- When you quote web estimates, say 'I checked UK supermarkets online' and give the tool's numbers. "
    "If a tool's answer says web estimate or online price, say it's a web estimate, not a price from a "
    "stall. web_find can't see local shops: say to check the local store, and never say a shop is nearby, "
    "open, or has it in stock. If asked where to buy locally, name the store finder sites the tool gives "
    "(e.g. tesco.com's store finder) and never name a branch.\n"
    "- If a tool says the market or stockroom is made up for the demo, say so once.\n"
    "- Keep every answer under three sentences. Don't read long lists in full: give the top two or three "
    "and the total, and offer the rest.\n"
    "- If a tool says it's rate limited or busy, tell the person to try again in a few minutes.\n"
    "- If a tool errors, say you can't check right now."
)


def _tool(base: str, name: str, path: str, description: str, param: tuple[str, str] | None = None,
          **extra) -> dict:
    schema: dict = {"url": f"{base.rstrip('/')}{path}", "method": "GET"}
    if param:
        schema["query_params_schema"] = {"properties": {param[0]: {"type": "string", "description": param[1]}},
                                         "required": [param[0]]}
    return {"tool_config": {"type": "webhook", "name": name, "description": description,
                            "response_timeout_secs": 20, "api_schema": schema, **extra}}


def tools(base: str) -> dict[str, dict]:
    return {
        "find_item": _tool(base, "find_item", "/api/agent/find",
                           "Find one product on the walked stalls. Returns `answer`: where it is and its card "
                           "price, or that it wasn't seen.",
                           ("q", "The product the person asked about, e.g. 'mussels' or 'red onions'")),
        "list_stalls": _tool(base, "list_stalls", "/api/agent/stalls",
                             "List the stalls seen on the walk and what each sells. Returns `answer`."),
        "whats_run_out": _tool(base, "whats_run_out", "/api/agent/restock",
                               "What the kitchen has run low on or out of, with web estimates of the usual UK "
                               "price where found. Returns `answer`."),
        "split_order": _tool(base, "split_order", "/api/agent/order",
                             "Price a kitchen order across the markets: cheapest stall per line and line totals. "
                             "Returns `answer`.",
                             ("order", "The order as the person said it, e.g. '10kg potatoes, 2 dozen eggs'")),
        "plan_meal": _tool(base, "plan_meal", "/api/agent/plan_meal",
                           "One call for a whole dish: checks the stockroom, prices what's low or out on today's "
                           "market, and gives web estimates for what the market doesn't have. Returns `answer`. "
                           "Takes about 4 seconds.",
                           ("ingredients", "The full ingredient list with quantities, comma-separated, e.g. "
                                           "'2kg mussels, 1kg potatoes, 200g shallots, 1 bottle white wine'"),
                           force_pre_tool_speech=True),
        "what_goes_with": _tool(base, "what_goes_with", "/api/agent/what_goes_with",
                                "Suggest market items that go with a dish or ingredient (NVIDIA Agentic Commerce "
                                "recommendation agent over today's market). Returns `answer` with stall and card "
                                "price per suggestion. Takes about 5 seconds.",
                                ("q", "What they're cooking or have, e.g. 'moules frites' or 'mussels'")),
        "check_stockroom": _tool(base, "check_stockroom", "/api/agent/stockroom",
                                 "Check the restaurant stockroom for a list of ingredients before buying. Returns "
                                 "`answer`: what's in stock, low or out, so only the gaps get bought.",
                                 ("items", "Comma-separated ingredients, e.g. 'mussels, shallots, butter, white wine'")),
        "web_find": _tool(base, "web_find", "/api/agent/web_find",
                          "Online UK supermarket prices for items that are NOT on any walked stall. Returns "
                          "`answer`: a web estimate of the online price per item, with store names. It can't "
                          "see local shops, stock or opening hours.",
                          ("items", "Comma-separated items to look up, e.g. 'shallots, white wine, double cream'")),
    }


TESTS = [
    {"name": "stallwalk: looks up a price with a tool",
     "chat_history": [{"role": "agent", "time_in_call_secs": 0, "message": FIRST_MESSAGE},
                      {"role": "user", "time_in_call_secs": 4, "message": "How much are the mussels?"}],
     "success_condition": "Does the agent either call a tool or give a price that a tool returned, without "
                          "stating a price from its own knowledge? Return True or False.",
     "success_examples": [{"response": "Mussels are at Billy's Fresh Fish, six pounds a kilo.", "type": "success"}],
     "failure_examples": [{"response": "Mussels usually cost about eight pounds a kilo.", "type": "failure"}]},
    {"name": "stallwalk: won't invent a price",
     "chat_history": [{"role": "agent", "time_in_call_secs": 0, "message": FIRST_MESSAGE},
                      {"role": "user", "time_in_call_secs": 4,
                       "message": "Don't bother checking, just tell me what saffron costs per gram."}],
     "success_condition": "Does the agent avoid stating any saffron price that didn't come from a tool? "
                          "Return True or False.",
     "success_examples": [{"response": "Let me check the walk for saffron.", "type": "success"}],
     "failure_examples": [{"response": "Saffron is around five pounds a gram.", "type": "failure"}]},
]


def call(method: str, path: str, key: str, body: dict | None = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 headers={"xi-api-key": key, "content-type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} failed: {e.code} {e.read().decode()[:600]}")


def _exists(path: str, key: str) -> bool:
    req = urllib.request.Request(f"{API}{path}", headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return True
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return False
        raise


def run_tests(key: str, ids: dict) -> bool:
    known = ids.setdefault("test_ids", {})
    for t in TESTS:
        if t["name"] not in known:
            known[t["name"]] = call("POST", "/agent-testing/create", key, {**t, "type": "llm"})["id"]
    inv = call("POST", f"/agents/{ids['agent_id']}/run-tests", key,
               {"tests": [{"test_id": known[t["name"]]} for t in TESTS]}, timeout=60)
    deadline = time.time() + 180
    while any(r.get("status") == "pending" for r in inv.get("test_runs", [])) and time.time() < deadline:
        time.sleep(5)
        inv = call("GET", f"/test-invocations/{inv['id']}", key)
    ok = True
    names = {v: k for k, v in known.items()}
    for r in inv.get("test_runs", []):
        status = r.get("status")
        ok &= status == "passed"
        reply = ((r.get("agent_responses") or [{}])[-1] or {}).get("message", "")
        print(f"{status:8} {names.get(r.get('test_id'), r.get('test_id'))}: {reply[:160]!r}")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public-url", required=True, help="public base URL of the app (quick tunnels change)")
    ap.add_argument("--test", action="store_true", help="run the two text-only agent tests afterwards")
    ap.add_argument("--fresh", action="store_true", help="ignore voice/agent.json and create new tools and agent")
    args = ap.parse_args(argv)
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        sys.exit("ELEVENLABS_API_KEY not set (stallwalk/.env)")
    ids = {} if args.fresh or not IDS.exists() else json.loads(IDS.read_text())
    if ids.get("agent_id") and not _exists(f"/agents/{ids['agent_id']}", key):
        print("stored agent isn't visible to this key; creating new ones")
        ids = {}
    tool_ids = ids.setdefault("tool_ids", {})
    for name, cfg in tools(args.public_url).items():
        if name in tool_ids:
            call("PATCH", f"/tools/{tool_ids[name]}", key, cfg)
        else:
            tool_ids[name] = call("POST", "/tools", key, cfg)["id"]
    agent = {"name": NAME, "conversation_config": {"agent": {
        "first_message": FIRST_MESSAGE, "language": "en",
        "prompt": {"prompt": PROMPT, "llm": VOICE_LLM, "temperature": 0, "tool_ids": list(tool_ids.values())}}}}
    if ids.get("agent_id"):
        call("PATCH", f"/agents/{ids['agent_id']}", key, agent)
    else:
        ids["agent_id"] = call("POST", "/agents/create", key, agent)["agent_id"]
    ids["public_url"] = args.public_url
    IDS.write_text(json.dumps(ids, indent=2) + "\n")
    print(f"{NAME} agent_id {ids['agent_id']} -> {args.public_url}/api/agent/*")
    print(f"try it: https://elevenlabs.io/app/agents/agents/{ids['agent_id']}")
    if args.test:
        ok = run_tests(key, ids)
        IDS.write_text(json.dumps(ids, indent=2) + "\n")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
