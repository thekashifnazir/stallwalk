import json
from pathlib import Path

import pytest

from stallwalk.export import export_stock, to_acp, to_ucp

# Same shape as out/synthetic_walk/stock.json (out/ isn't committed, so a copy lives here).
STOCK = {
    "stalls": [
        {"stall": "Patel's Fruit & Veg", "items": [
            {"name": "Bananas", "price_gbp": 0.2, "price_text": "5 for £1", "unit": "each",
             "deal": "5 for £1", "seen_in_frames": 3, "needs_check": []},
            {"name": "Red Onions", "price_gbp": 1.2, "price_text": "£1.20/kg", "unit": "kg",
             "deal": None, "seen_in_frames": 3, "needs_check": []},
        ]},
        {"stall": "Billy's Fresh Fish", "items": [
            {"name": "Cod Fillet", "price_gbp": 14.99, "price_text": "£14.99/kg", "unit": "kg",
             "deal": None, "seen_in_frames": 7,
             "needs_check": ["price differs across frames: [4.99, 14.99]"]},
            {"name": "Smoked Haddock", "price_gbp": None, "price_text": None, "unit": None,
             "deal": None, "seen_in_frames": 1, "needs_check": ["price not readable"]},
        ]},
    ],
    "possible": [],
    "source": {"video": "synthetic_walk.mp4", "frames": 16},
}


def test_every_item_exported_in_order():
    out = export_stock(STOCK)
    assert [r["product"]["title"] for r in out["acp"]] == ["Bananas", "Red Onions", "Cod Fillet", "Smoked Haddock"]
    assert [r["title"] for r in out["ucp"]] == ["Bananas", "Red Onions", "Cod Fillet", "Smoked Haddock"]


def test_clean_item_is_buyable_in_gbp():
    item = STOCK["stalls"][0]["items"][1]
    acp, ucp = to_acp("Patel's Fruit & Veg", item), to_ucp("Patel's Fruit & Veg", item)
    assert acp["pricing"]["currency"] == "GBP"
    assert acp["pricing"]["price"] == 1.2
    assert acp["pricing"]["unit_pricing"]["measure"] == {"value": 1, "unit": "kg"}
    assert acp["agent_actions"]["buyable"] is True
    assert acp["pricing"]["price_status"] == "confirmed"
    assert ucp["price"] == {"amount": 1.2, "currency": "GBP"}
    assert ucp["buyable"] is True and ucp["needs_check"] == []
    assert acp["product"]["id"] == ucp["id"] == "patel-s-fruit-veg/red-onions"
    assert acp["marketplace"]["seller_name"] == "Patel's Fruit & Veg"


def test_deal_carried():
    item = STOCK["stalls"][0]["items"][0]
    assert to_acp("Patel's Fruit & Veg", item)["pricing"]["deal"] == "5 for £1"
    assert to_ucp("Patel's Fruit & Veg", item)["custom_label_0"] == "5 for £1"


def test_disputed_price_kept_but_not_buyable():
    item = STOCK["stalls"][1]["items"][0]
    acp, ucp = to_acp("Billy's Fresh Fish", item), to_ucp("Billy's Fresh Fish", item)
    assert acp["pricing"]["price"] == 14.99
    assert acp["agent_actions"]["buyable"] is False
    assert acp["pricing"]["price_status"] == "needs_check"
    assert ucp["needs_check"] == ["price differs across frames: [4.99, 14.99]"]


def test_missing_price_kept_and_flagged():
    item = STOCK["stalls"][1]["items"][1]
    acp, ucp = to_acp("Billy's Fresh Fish", item), to_ucp("Billy's Fresh Fish", item)
    assert acp["pricing"]["price"] is None
    assert acp["pricing"]["price_status"] == "unreadable"
    assert acp["agent_actions"]["buyable"] is False
    assert acp["agent_actions"]["comparable"] is False
    assert ucp["price"] == {"amount": None, "currency": None}
    assert ucp["availability"] == "in_stock"


def test_missing_price_flag_added_when_absent():
    item = {"name": "Leeks", "price_gbp": None, "price_text": None, "unit": None,
            "deal": None, "seen_in_frames": 2, "needs_check": []}
    assert to_ucp("Stall", item)["needs_check"] == ["price not readable"]


def test_deterministic_and_json_safe():
    a, b = export_stock(STOCK), export_stock(STOCK)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


REAL = Path(__file__).resolve().parent.parent / "out" / "synthetic_walk" / "stock.json"


@pytest.mark.skipif(not REAL.exists(), reason="no local walk output")
def test_real_walk_output():
    stock = json.loads(REAL.read_text())
    out = export_stock(stock)
    n = sum(len(s["items"]) for s in stock["stalls"])
    assert len(out["acp"]) == len(out["ucp"]) == n
    assert all(r["pricing"]["currency"] == "GBP" for r in out["acp"])
    flagged = [r for r in out["ucp"] if r["needs_check"]]
    assert all(r["buyable"] is False for r in flagged)
