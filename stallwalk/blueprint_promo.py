"""End-of-day stall deals, using NVIDIA's Agentic Commerce blueprint promotion agent.

Source: NVIDIA-AI-Blueprints/Retail-Agentic-Commerce (Apache-2.0)
  - src/merchant/services/promotion.py: the 3-layer design, signal rules, action map,
    margin filter and margin check below are copied from it (Layers 1 and 3).
  - src/agents/commerce_agents/configs/promotion.yml: the agent's system prompt (Layer 2)
    is loaded from the blueprint file at runtime, not retyped.

What changed for a market stall:
  - Prices are in pence, not cents. GBP throughout.
  - "Competitor price" is the low end of the UK supermarket web estimate from the Tavily
    price check (price_check.typical_low), only when its unit matches the card's unit.
  - Stock count is what the stallholder says is left; STOCK_THRESHOLD is a parameter
    (a stall with 15 kg of mackerel at 4pm is under pressure; 50 units is a web-shop number).
  - FREE_SHIPPING makes no sense on a stall, so it's removed from allowed_actions.
  - Model: the blueprint's LLM, nvidia/Nemotron-3_5-Lightning, on Nebius Token Factory.

Code owns every price: the model only picks an action from the allowed list, and the
discount is applied and checked against the margin floor here, never by the model.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from stallwalk import tf

BLUEPRINT = Path(os.environ.get(
    "AGENTIC_COMMERCE_DIR",
    "/Users/kash/Code/sandbox/innovators-guild/blueprints/Retail-Agentic-Commerce",
))
PROMPT_YML = BLUEPRINT / "src/agents/commerce_agents/configs/promotion.yml"
MODEL = os.environ.get("PROMO_MODEL", "nvidia/Nemotron-3_5-Lightning")

# --- copied from promotion.py (Apache-2.0) -------------------------------------------
ACTION_DISCOUNT_MAP = {
    "NO_PROMO": 0.0,
    "DISCOUNT_5_PCT": 0.05,
    "DISCOUNT_10_PCT": 0.10,
    "DISCOUNT_15_PCT": 0.15,
    "FREE_SHIPPING": 0.0,
}
RETAIL_EVENTS = [
    ("valentines_day", 2, 14), ("easter", 4, 20), ("mothers_day", 5, 11), ("memorial_day", 5, 26),
    ("fathers_day", 6, 15), ("independence_day", 7, 4), ("labor_day", 9, 1), ("back_to_school", 8, 15),
    ("halloween", 10, 31), ("black_friday", 11, 28), ("cyber_monday", 12, 1), ("christmas", 12, 25),
    ("new_years", 1, 1),
]
_PEAK_WINDOW, _PRE_SEASON_WINDOW, _POST_SEASON_WINDOW = 3, 14, 14


def compute_inventory_pressure(stock_count: float, threshold: float) -> str:
    return "high" if stock_count > threshold else "low"


def compute_competition_position(base_price: int, lowest_competitor_price: int | None) -> str:
    if lowest_competitor_price is None:
        return "below_market"
    if base_price > lowest_competitor_price:
        return "above_market"
    if base_price == lowest_competitor_price:
        return "at_market"
    return "below_market"


def compute_seasonal_urgency(today: date | None = None) -> str:
    today = today or date.today()
    for _name, month, day in RETAIL_EVENTS:
        try:
            delta = (today - date(today.year, month, day)).days
        except ValueError:
            continue
        if abs(delta) <= _PEAK_WINDOW:
            return "peak"
        if -(_PEAK_WINDOW + _PRE_SEASON_WINDOW) <= delta < -_PEAK_WINDOW:
            return "pre_season"
        if _PEAK_WINDOW < delta <= _PEAK_WINDOW + _POST_SEASON_WINDOW:
            return "post_season"
    return "off_season"


def filter_allowed_actions_by_margin(min_margin: float) -> list[str]:
    max_discount = 1.0 - min_margin
    allowed = [a for a, d in ACTION_DISCOUNT_MAP.items() if d < max_discount]
    if "NO_PROMO" not in allowed:
        allowed.insert(0, "NO_PROMO")
    return allowed


def apply_promotion_action(base_price: int, action: str) -> int:
    return int(base_price * ACTION_DISCOUNT_MAP.get(action, 0.0))


def validate_discount_against_margin(base_price: int, discount: int, min_margin: float) -> bool:
    return base_price - discount >= int(base_price * min_margin)
# --- end of copied code --------------------------------------------------------------


TIERS = ["NO_PROMO", "FREE_SHIPPING", "DISCOUNT_5_PCT", "DISCOUNT_10_PCT", "DISCOUNT_15_PCT"]


def expected_actions(signals: dict, allowed: list[str]) -> set[str]:
    """What the prompt's own decision table says, worked out in code.

    Used to check the agent (a "definition of done" for Layer 2), never to replace it.
    Returns every action that follows the table; ties in "closest available" all count.
    """
    inv, comp = signals["inventory_pressure"], signals["competition_position"]
    if inv == "low":
        starts = [0]
    elif comp == "below_market":
        starts = [0, 1]
    elif comp == "at_market":
        starts = [2]
    else:
        starts = [3]
    results = set()
    for t in starts:
        season, life, vel = signals["seasonal_urgency"], signals["product_lifecycle"], signals["demand_velocity"]
        if season in ("peak", "post_season"):
            t += 1
        if season == "pre_season" and t == 0:
            t = 1
        if life == "clearance":
            t += 1
        if life == "new_arrival":
            t = 1
        if vel == "decelerating":
            t += 1
        if vel == "accelerating":
            t = max(1, t - 1)
        t = min(t, len(TIERS) - 1)
        if TIERS[t] in allowed:
            results.add(TIERS[t])
        else:
            idx = [TIERS.index(a) for a in allowed]
            best = min(abs(i - t) for i in idx)
            results |= {TIERS[i] for i in idx if abs(i - t) == best}
    return results


def load_system_prompt() -> str:
    """Read stages.main.system_prompt from the blueprint's promotion.yml.

    It's a YAML single-quoted scalar: '' is a quote, a blank line is a newline,
    other line breaks fold to spaces. Small parser so stallwalk needs no YAML dependency.
    """
    text = PROMPT_YML.read_text()
    m = re.search(r"system_prompt: '(.*?)'\n(?! )", text, re.S)
    if not m:
        raise RuntimeError(f"system_prompt not found in {PROMPT_YML}")
    lines = [ln.strip() for ln in m.group(1).split("\n")]
    out, buf = [], []
    for ln in lines:
        if ln == "":
            out.append(" ".join(buf)); buf = []
        else:
            buf.append(ln)
    out.append(" ".join(buf))
    return "\n".join(out).replace("''", "'").strip()


def _agent(system: str, context: dict) -> dict:
    body = {
        "model": MODEL,
        "temperature": 0.1,
        "max_tokens": 1024,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context)},
        ],
    }
    req = urllib.request.Request(
        f"{tf.BASE}/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tf.KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        reply = json.load(r)["choices"][0]["message"]["content"] or ""
    return tf.parse_json(reply)


def stall_deal(item: dict, stall: str, stock_left: float, *, threshold: float = 10,
               min_margin: float = 0.85, lifecycle: str = "mature", velocity: str = "flat",
               today: date | None = None, system: str | None = None) -> dict:
    """One item's end-of-day deal decision, blueprint-style.

    min_margin follows the blueprint's meaning: the final price must stay at or above
    base_price * min_margin (0.85 lets at most a 15% cut).
    """
    base = round(float(item["price_gbp"]) * 100)
    pc = item.get("price_check") or {}
    competitor = None
    if pc.get("typical_low") and pc.get("unit") == item.get("unit"):
        competitor = round(float(pc["typical_low"]) * 100)
    allowed = [a for a in filter_allowed_actions_by_margin(min_margin) if a != "FREE_SHIPPING"]
    context = {
        "product_id": f"{stall}:{item['name']}",
        "product_name": item["name"],
        "base_price_cents": base,
        "stock_count": stock_left,
        "min_margin": min_margin,
        "lowest_competitor_price_cents": competitor or base,
        "signals": {
            "inventory_pressure": compute_inventory_pressure(stock_left, threshold),
            "competition_position": compute_competition_position(base, competitor),
            "seasonal_urgency": compute_seasonal_urgency(today),
            "product_lifecycle": lifecycle,
            "demand_velocity": velocity,
        },
        "allowed_actions": allowed,
    }
    t0 = time.time()
    try:
        decision = _agent(system or load_system_prompt(), context)
        action = decision.get("action", "NO_PROMO")
    except Exception as e:  # the stall still trades if the agent is down
        decision, action = {"error": str(e)}, "NO_PROMO"
    if action not in allowed:  # Layer 3 guard: never trust an action outside the list
        decision["rejected_action"] = action
        action = "NO_PROMO"
    expected = expected_actions(context["signals"], allowed)
    follows_table = action in expected
    discount = apply_promotion_action(base, action)
    if not validate_discount_against_margin(base, discount, min_margin):
        decision["margin_blocked"] = action
        action, discount = "NO_PROMO", 0
    final = base - discount
    return {
        "stall": stall,
        "item": item["name"],
        "unit": item.get("unit"),
        "card_price_gbp": base / 100,
        "deal_price_gbp": final / 100,
        "action": action,
        "reason_codes": decision.get("reason_codes", []),
        "reasoning": decision.get("reasoning", ""),
        "signals": context["signals"],
        "supermarket_low_gbp": competitor / 100 if competitor else None,
        "stock_left": stock_left,
        "follows_table": follows_table,
        "table_expects": sorted(expected, key=TIERS.index),
        "model": MODEL,
        "seconds": round(time.time() - t0, 2),
        "guard": {k: decision[k] for k in ("rejected_action", "margin_blocked", "error") if k in decision},
    }


def stall_deals(run_dir: Path, stall: str, stock_left: dict[str, float], **kw) -> list[dict]:
    stock = json.loads((run_dir / "stock.json").read_text())
    system = load_system_prompt()
    out = []
    for s in stock["stalls"]:
        if s["stall"] != stall:
            continue
        for item in s["items"]:
            if item["name"] in stock_left and item.get("price_gbp"):
                out.append(stall_deal(item, stall, stock_left[item["name"]], system=system, **kw))
    return out


if __name__ == "__main__":
    # Demo and check: made-up end-of-day counts for every stall on the synthetic walk,
    # each decision asked 3 times, scored against the prompt's own decision table.
    root = Path(__file__).resolve().parent.parent
    run = root / "out" / (sys.argv[1] if len(sys.argv) > 1 else "synthetic_walk")
    repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    stock = json.loads((run / "stock.json").read_text())
    counts = [30, 4, 12, 25, 2, 18, 40, 6]
    deals = []
    for r in range(repeats):
        for s in stock["stalls"]:
            left = {it["name"]: counts[(i + r) % len(counts)] for i, it in enumerate(s["items"])}
            for d in stall_deals(run, s["stall"], left):
                d["repeat"] = r
                deals.append(d)
    res = {"note": "made-up end-of-day stock counts; each item asked %d times" % repeats,
           "run": run.name, "deals": deals}
    (root / "out" / "blueprint_promo_sample.json").write_text(json.dumps(res, indent=1))
    for d in deals[: len(deals) // repeats]:
        print(f"{d['stall'][:16]:<16} {d['item']:<14} left {d['stock_left']:>3}  £{d['card_price_gbp']:.2f} -> £{d['deal_price_gbp']:.2f}"
              f"  {d['action']:<15} {d['signals']['inventory_pressure']}/{d['signals']['competition_position']:<12}"
              f" table {'OK' if d['follows_table'] else 'BROKE (' + '/'.join(d['table_expects']) + ')'}")
    n, ok = len(deals), sum(d["follows_table"] for d in deals)
    secs = sorted(d["seconds"] for d in deals)
    print(f"{ok} of {n} decisions follow the blueprint's own decision table; median {secs[len(secs)//2]}s; "
          f"{sum(1 for d in deals if d['guard'])} hit a code guard")
