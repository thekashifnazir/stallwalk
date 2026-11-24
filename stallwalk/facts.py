"""Item facts from the web, for shoppers: what it is, how to use it, what to look for. With sources.

Tavily search (Nebius bought Tavily; the open-source Catalog Enrichment repo itself uses Exa for web research),
then Nemotron writes 2-3 short facts only from the snippets it was given. Cached per item name.
Never touches prices: those come from the stall's own card.
"""
import json
import os
import threading
import urllib.request
from pathlib import Path

from . import tf

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
CACHE = Path(__file__).resolve().parent.parent / "out" / "facts_cache.json"
_lock = threading.Lock()

FACTS_PROMPT = """A market shopper is looking at "{name}" on a stall ({stall}). Using ONLY these web snippets:

{snippets}

Return JSON only: {{"facts": [2 or 3 short, useful facts for a shopper: what it is, how to cook or use it,
how to pick a good one or store it], "source_ids": [ids of the snippets you used]}}
Don't mention prices. If the snippets are about something else, return {{"facts": [], "source_ids": []}}.
"""


def _search(query: str, n: int = 5, timeout: int = 10) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return []
    req = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=json.dumps({"query": query, "max_results": n, "search_depth": "basic"}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return [{"url": h.get("url"), "title": h.get("title"), "content": (h.get("content") or "")[:600]}
            for h in data.get("results", []) if h.get("url")]


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def item_facts(name: str, stall: str = "") -> dict:
    key = name.strip().lower()
    with _lock:
        cache = _load_cache()
    if key in cache:
        return {**cache[key], "cached": True}
    try:
        hits = _search(f"{name} buying guide how to cook store UK")
    except Exception as e:  # noqa: BLE001 - search down: say so, don't block the shopper
        return {"name": name, "facts": [], "sources": [], "error": f"search failed: {e}"}
    if not hits:
        return {"name": name, "facts": [], "sources": []}
    snippets = "\n".join(f"[{i}] {h['title']}: {h['content']}" for i, h in enumerate(hits))
    try:
        data = tf.parse_json(tf.chat(tf.TEXT_MODEL, FACTS_PROMPT.format(name=name, stall=stall or "a market stall",
                                                                        snippets=snippets),
                                     max_tokens=500, extra={"chat_template_kwargs": {"enable_thinking": False}}))
    except Exception as e:  # noqa: BLE001
        return {"name": name, "facts": [], "sources": [], "error": f"summary failed: {e}"}
    ids = [i for i in data.get("source_ids", []) if isinstance(i, int) and 0 <= i < len(hits)]
    out = {"name": name, "facts": [f for f in data.get("facts", []) if isinstance(f, str)][:3],
           "sources": [{"title": hits[i]["title"], "url": hits[i]["url"]} for i in ids][:3]}
    if out["facts"] and not out["sources"]:
        out["sources"] = [{"title": h["title"], "url": h["url"]} for h in hits[:2]]
    with _lock:
        cache = _load_cache()
        cache[key] = out
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=2))
    return out
