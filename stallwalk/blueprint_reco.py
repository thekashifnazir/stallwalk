"""NVIDIA Retail Agentic Commerce recommendation agent, run over a stallwalk stock list.

The pipeline itself (retrieve -> user understanding + NLI alignment in parallel ->
context summary -> item ranker -> output guard) is NOT copied here: it is imported
unchanged from the blueprint's commerce_agents/recommendation.py (Apache-2.0,
Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES). The stage prompts and
model settings are loaded at runtime from the blueprint's configs/recommendation.yml.

What this file swaps in:
- the Milvus retriever -> an in-memory keyword retriever over a run's stock.json
- the ChatNVIDIA client -> plain OpenAI-style calls to Nebius Token Factory
- prices and stalls on the result are filled by code from the stock list, never by the model

  uv run python -m stallwalk.blueprint_reco "I'm making moules frites tonight, I have mussels"
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BLUEPRINT = Path(
    "/Users/kash/Code/sandbox/innovators-guild/blueprints/Retail-Agentic-Commerce/src/agents"
)
CONFIG = BLUEPRINT / "commerce_agents" / "configs" / "recommendation.yml"
RUNS = Path(__file__).resolve().parent.parent / "out"
DEFAULT_RUN = "synthetic_walk"
MODEL = os.environ.get("BLUEPRINT_RECO_MODEL", "nvidia/Nemotron-3_5-Lightning")
HERBTWIN_ENV = Path("/Users/kash/Code/sandbox/nvidia-nebius-hackathon/.env")

if str(BLUEPRINT) not in sys.path:
    sys.path.insert(0, str(BLUEPRINT))
# Pure-stdlib module: no Milvus, NAT or LangChain needed to import it.
from commerce_agents.recommendation import recommend as blueprint_recommend  # noqa: E402

from . import tf  # noqa: E402  (only for its .env loading, BASE and KEY)


# ---------------------------------------------------------------- config loading
def _scalar(v: str):
    v = v.strip()
    if v in ("true", "false"):
        return v == "true"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v.strip("'\"")


def _mini_yaml(text: str):
    """Subset YAML reader (mappings, '|' block scalars, scalar lists): enough for
    recommendation.yml, used only when PyYAML isn't installed."""
    lines = text.splitlines()

    def indent(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    def skip(i: int) -> int:
        while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
            i += 1
        return i

    def block(i: int, ind: int):
        i = skip(i)
        if i < len(lines) and lines[i].lstrip().startswith("- "):
            out = []
            while i < len(lines) and indent(lines[i]) == ind and lines[i].lstrip().startswith("- "):
                out.append(_scalar(lines[i].lstrip()[2:]))
                i = skip(i + 1)
            return out, i
        out: dict = {}
        while i < len(lines) and indent(lines[i]) == ind:
            key, _, rest = lines[i].strip().partition(":")
            rest = rest.strip()
            if rest == "|":
                j, body = i + 1, []
                while j < len(lines) and (not lines[j].strip() or indent(lines[j]) > ind):
                    body.append(lines[j])
                    j += 1
                while body and not body[-1].strip():
                    body.pop()
                base = min(indent(b) for b in body if b.strip())
                out[key] = "\n".join(b[base:] for b in body) + "\n"
                i = skip(j)
            elif rest:
                out[key] = _scalar(rest)
                i = skip(i + 1)
            else:
                j = skip(i + 1)
                out[key], i = block(j, indent(lines[j]))
        return out, i

    return block(skip(0), 0)[0]


def load_profile() -> dict:
    text = CONFIG.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(text)


# ---------------------------------------------------------------- Token Factory
def _key() -> str:
    key = os.environ.get("TOKENFACTORY_API_KEY") or tf.KEY
    if key:
        return key
    if HERBTWIN_ENV.exists():
        for line in HERBTWIN_ENV.read_text().splitlines():
            if line.startswith("HERBTWIN_NEBIUS_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("No Token Factory key (TOKENFACTORY_API_KEY or HERBTWIN_NEBIUS_API_KEY)")


def _post(body: dict, timeout: int = 60) -> str:
    req = urllib.request.Request(
        f"{tf.BASE}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"]["content"] or ""


def _make_stage(label: str, settings: dict, system_prompt: str, trace: list):
    """A blueprint TextStage: system prompt from the yml, payload as the user turn."""

    async def stage(payload: str) -> str:
        body = {
            "model": MODEL,
            "temperature": settings.get("temperature", 0.0),
            # yml budgets are tuned for NIM; give Token Factory room so JSON isn't cut off
            "max_tokens": max(int(settings.get("max_tokens", 512)) * 3, 1536),
            "chat_template_kwargs": settings.get("chat_template_kwargs", {"enable_thinking": False}),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": payload},
            ],
        }
        if settings.get("response_format"):
            body["response_format"] = settings["response_format"]
        if settings.get("guided_json"):
            body["guided_json"] = settings["guided_json"]
        t0 = time.perf_counter()
        note = None
        try:
            out = await asyncio.to_thread(_post, body)
        except urllib.error.HTTPError as e:
            # Some hosts reject guided_json/response_format: retry once without them.
            note = f"HTTP {e.code}; retried without structured-output params"
            body.pop("guided_json", None)
            body.pop("response_format", None)
            out = await asyncio.to_thread(_post, body)
        out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out.strip())
        trace.append({
            "stage": label,
            "seconds": round(time.perf_counter() - t0, 2),
            "output_chars": len(out),
            **({"note": note} if note else {}),
            "output": out,
        })
        return out

    return stage


# ---------------------------------------------------------------- stock as a catalogue
_CATEGORY_WORDS = {
    "fish & seafood": ["fish", "cod", "prawn", "mackerel", "mussel", "salmon", "haddock", "crab", "squid"],
    "fruit": ["avocado", "banana", "strawberr", "apple", "lemon", "lime", "orange", "berr", "grape"],
    "vegetables & herbs": ["onion", "tomato", "coriander", "parsley", "potato", "garlic", "pepper",
                           "carrot", "leek", "shallot", "herb", "lettuce", "veg"],
    "cheese & dairy": ["cheese", "cheddar", "feta", "halloumi", "brie", "butter", "cream", "milk"],
    "deli & bakery": ["olive", "sourdough", "bread", "loaf", "baguette", "ham", "chorizo"],
}


def _category(name: str, stall: str) -> str:
    low = name.lower()
    for cat, words in _CATEGORY_WORDS.items():
        if any(w in low for w in words):
            return cat
    return stall


def _run_path(run: str | None) -> Path:
    if run:
        p = Path(run)
        return p if p.suffix == ".json" else (p / "stock.json" if p.is_dir() else RUNS / run / "stock.json")
    return RUNS / DEFAULT_RUN / "stock.json"


def load_catalogue(run: str | None) -> dict[str, dict]:
    stock = json.loads(_run_path(run).read_text())
    cat: dict[str, dict] = {}
    for si, stall in enumerate(stock.get("stalls", [])):
        for ii, item in enumerate(stall.get("items", [])):
            pid = f"s{si}-i{ii}"
            cat[pid] = {
                "product_id": pid,
                "name": item["name"],
                "stall": stall["stall"],
                "category": _category(item["name"], stall["stall"]),
                "price_gbp": item.get("price_gbp"),
                "price_text": item.get("price_text"),
                "unit": item.get("unit"),
                "deal": item.get("deal"),
            }
    return cat


def _words(s: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", s.lower()):
        out.add(w)
        if len(w) > 3 and w.endswith("s"):
            out.add(w[:-1])
    return out


def _document(c: dict) -> dict:
    """Shape the blueprint's _normalize_candidate reads (metadata.id/name/category, page_content)."""
    desc = f"{c['price_text'] or ''} at {c['stall']}".strip()
    return {
        "document_id": c["product_id"],
        "page_content": desc,
        "metadata": {"id": c["product_id"], "name": c["name"], "category": c["category"],
                     "brand": c["stall"], "price": c["price_gbp"], "currency": "GBP"},
    }


# Meal-pairing words: an ingredient or dish in the query pulls in what goes with it.
_PAIRINGS = {
    "mussel": ["bread", "sourdough", "baguette", "shallot", "onion", "garlic", "parsley", "butter",
               "wine", "lemon", "potato", "chip", "cream"],
    "moule": ["bread", "sourdough", "shallot", "garlic", "parsley", "butter", "wine", "lemon",
              "potato", "chip"],
    "frite": ["potato", "chip", "mayonnaise"],
    "fish": ["lemon", "potato", "chip", "parsley", "butter", "bread", "tomato"],
    "salmon": ["lemon", "dill", "potato", "butter", "avocado"],
    "prawn": ["garlic", "lemon", "chilli", "avocado", "bread", "sourdough"],
    "curry": ["coriander", "onion", "tomato", "garlic", "rice", "chilli"],
    "salad": ["tomato", "feta", "olive", "onion", "avocado", "lettuce", "cucumber"],
    "taco": ["avocado", "coriander", "onion", "tomato", "lime", "prawn"],
    "cheese": ["sourdough", "bread", "olive", "tomato", "grape"],
    "bbq": ["halloumi", "onion", "tomato", "mackerel", "prawn"],
}


def _expand(words: set[str]) -> set[str]:
    extra: set[str] = set()
    for w in words:
        for key, pairs in _PAIRINGS.items():
            if w.startswith(key):
                extra.update(pairs)
    return extra


def make_retriever(catalogue: dict[str, dict], trace: dict, user_query: str = ""):
    """In-memory stand-in for retrieval.CatalogRetriever.

    Scores each item by word overlap with the shopper's own words (x2), plus
    meal-pairing words those imply (x2), plus the blueprint's generated search query.
    A market stock list is a couple of dozen items, so every item stays a candidate;
    the score only decides order (the blueprint keeps the first top_k=10)."""

    async def retrieve(query: str) -> list[dict]:
        uq = _words(user_query)
        q = _words(query)
        pair = _expand(uq | q)
        scored = []
        for order, c in enumerate(catalogue.values()):
            words = _words(c["name"]) | _words(c["category"])
            name_low = c["name"].lower()
            hits = (2 * len(uq & words)
                    + 2 * sum(1 for p in pair if p in name_low)
                    + len(q & words))
            scored.append((-hits, order, c))
        scored.sort(key=lambda t: (t[0], t[1]))
        trace["search_query"] = query
        trace["retrieved"] = [{"product_id": c["product_id"], "name": c["name"], "hits": -h}
                              for h, _, c in scored]
        return [_document(c) for _, _, c in scored]

    return retrieve


def _cart_from_query(query: str, catalogue: dict[str, dict]) -> list[dict]:
    q = _words(query)
    return [{"product_id": c["product_id"], "name": c["name"], "category": c["category"]}
            for c in catalogue.values() if _words(c["name"]) <= q or (_words(c["name"]) & q and
            len(_words(c["name"])) == 1)]


# ---------------------------------------------------------------- public entry point
async def recommend_async(query: str, run: str | None = None) -> dict:
    profile = load_profile()
    catalogue = load_catalogue(run)
    stage_trace: list = []
    retrieval_trace: dict = {}
    stages = {
        label: _make_stage(label, profile["models"][spec["model"]], spec["system_prompt"], stage_trace)
        for label, spec in profile["stages"].items()
    }
    cart = _cart_from_query(query, catalogue)
    # The blueprint's own input contract: {"query", "cart_items", "session_context"}.
    payload = json.dumps({"query": query, "cart_items": cart})
    t0 = time.perf_counter()
    raw = await blueprint_recommend(
        payload,
        retrieve=make_retriever(catalogue, retrieval_trace, query),
        understand_user=stages["user_understanding_agent"],
        score_alignment=stages["nli_agent"],
        summarize_context=stages["context_summary_agent"],
        rank_items=stages["item_ranker_agent"],
    )
    total = round(time.perf_counter() - t0, 2)
    result = json.loads(raw)

    # Stall and price come from the stock list by product_id. The model's names are not trusted.
    kept, dropped = [], []
    for rec in result.get("recommendations", []):
        item = catalogue.get(rec["product_id"])
        if item is None:
            dropped.append(rec)
            continue
        kept.append({
            "rank": rec["rank"],
            "product_id": item["product_id"],
            "name": item["name"],
            "stall": item["stall"],
            "category": item["category"],
            "price_gbp": item["price_gbp"],
            "price_text": item["price_text"],
            "unit": item["unit"],
            "deal": item["deal"],
            "reasoning": rec["reasoning"],
            **({"model_said_name": rec["product_name"]} if rec["product_name"] != item["name"] else {}),
        })
    for i, rec in enumerate(kept, start=1):
        rec["rank"] = i
    result["recommendations"] = kept
    result["query"] = query
    result["run"] = str(_run_path(run).parent.name)
    result["cart_items"] = cart
    result["pipeline_trace"].update({
        "source": "NVIDIA Retail-Agentic-Commerce commerce_agents/recommendation.py (imported) "
                  "+ configs/recommendation.yml (loaded at runtime)",
        "model": MODEL,
        "endpoint": tf.BASE,
        "retriever": "in-memory keyword over stock.json (replaces Milvus CatalogRetriever)",
        "catalogue_size": len(catalogue),
        "seconds_total": total,
        "dropped_unknown_ids": dropped,
        **retrieval_trace,
        "stages": stage_trace,
    })
    return result


def recommend(query: str, run: str | None = None) -> dict:
    return asyncio.run(recommend_async(query, run))


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("query")
    ap.add_argument("--run", default=None, help="run name under out/ (default synthetic_walk)")
    ap.add_argument("--save", default=None, help="write the JSON here as well")
    a = ap.parse_args(argv)
    out = recommend(a.query, a.run)
    text = json.dumps(out, indent=2, ensure_ascii=False)
    if a.save:
        Path(a.save).write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
