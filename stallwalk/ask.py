"""Shopper questions over the stock list.

The model only picks which listed items match; code fills in stall, price and freshness from
the stock list, so an answer can't contain a price that isn't on a card.
"""
import json

from . import tf

ASK_PROMPT = """You help a shopper find things on market stalls. Here is today's stock list as JSON
(each item has an id):

{stock}

Shopper asks: "{question}"

Return JSON only: {{"ids": [item ids that match, best first, max 6, include every reasonable match], "note": one short sentence for the shopper}}
Rules: only use ids from the list. Respect price limits in the question using price_gbp.
If nothing matches, return an empty ids list and say so in the note. Never mention a price yourself.
"""


def _flatten(stock: dict) -> list[dict]:
    flat = []
    for s in stock.get("stalls", []):
        for i in s["items"]:
            flat.append({"id": len(flat), "stall": s["stall"], **i})
    return flat


def ask(stock: dict, question: str) -> dict:
    flat = _flatten(stock)
    slim = [{k: v for k, v in x.items() if k in ("id", "stall", "name", "price_gbp", "unit", "deal")} for x in flat]
    reply = tf.chat(tf.TEXT_MODEL, ASK_PROMPT.format(stock=json.dumps(slim), question=question),
                    max_tokens=800, extra={"chat_template_kwargs": {"enable_thinking": False}})
    data = tf.parse_json(reply)
    ids = [i for i in data.get("ids", []) if isinstance(i, int) and 0 <= i < len(flat)]
    return {
        "question": question,
        "note": data.get("note", ""),
        "matches": [{k: flat[i][k] for k in ("stall", "name", "price_gbp", "price_text", "unit", "deal", "needs_check")} for i in ids],
        "ignored_ids": [i for i in data.get("ids", []) if i not in ids],
    }
