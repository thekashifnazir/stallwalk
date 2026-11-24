import json
from pathlib import Path

import pytest

from stallwalk import kitchen

ROOT = Path(__file__).resolve().parent.parent
MARKETS = [json.loads((ROOT / "fixtures" / "markets" / f).read_text()) for f in ("meat.json", "fish.json", "veg.json")]


def test_fixtures_are_labelled_made_up():
    for m in MARKETS:
        assert m["made_up"] is True and "made up" in m["market"].lower()
        assert all("made up" in s["stall"].lower() for s in m["stalls"])


def test_cheapest_comparable_pick_across_markets():
    out = kitchen.split_order([{"item": "lemons", "qty": 10, "unit": "each"},
                               {"item": "chicken thighs", "qty": 5, "unit": "kg"}], MARKETS)
    lemons, thighs = out["lines"]
    assert lemons["pick"]["market"].startswith("New Covent Garden") and lemons["pick"]["price_gbp"] == 0.20
    assert lemons["line_total_gbp"] == 2.0
    assert [a["price_gbp"] for a in lemons["alternatives"]] == [0.30]
    assert thighs["pick"]["stall"] == "Butcher B (made up)" and thighs["line_total_gbp"] == 29.0
    assert set(out["by_market"]) == {"New Covent Garden-style veg market (made up)", "Smithfield-style meat market (made up)"}


def test_unit_mismatch_not_picked():
    out = kitchen.split_order([{"item": "king prawns", "qty": 1, "unit": "kg"}], MARKETS)
    line = out["lines"][0]
    assert line["pick"] is None and line["note"] == "only sold per 200g"
    assert "king prawns" not in out["unmatched"]  # it exists, just not per kg


def test_no_unit_means_any_unit_but_no_total():
    line = kitchen.split_order([{"item": "eggs", "qty": 2, "unit": None}], MARKETS)["lines"][0]
    assert line["pick"]["price_gbp"] == 2.80
    assert "line_total_gbp" not in line


def test_unpriced_offer_never_gets_a_price():
    line = kitchen.split_order([{"item": "chicken breast", "qty": 2, "unit": "kg"}], MARKETS)["lines"][0]
    assert line["pick"] is None and line["note"] == "on a stock list, but no price was read"
    assert line["alternatives"][0]["price_gbp"] is None


def test_unmatched_is_honest():
    out = kitchen.split_order([{"item": "saffron", "qty": 1, "unit": "g"}], MARKETS)
    assert out["unmatched"] == ["saffron"] and out["lines"][0]["pick"] is None
    assert out["by_market"] == {}


def test_other_currency_skipped():
    eur = {"market": "Somewhere abroad", "stalls": [{"stall": "X", "items": [
        {"name": "Lemons", "price_gbp": 0.05, "price_text": "5c", "unit": "each", "currency": "EUR"}]}]}
    line = kitchen.split_order([{"item": "lemons", "qty": 1, "unit": "each"}], MARKETS + [eur])["lines"][0]
    assert line["pick"]["price_gbp"] == 0.20


def test_free_text_goes_through_parse_only(monkeypatch):
    monkeypatch.setattr(kitchen.tf, "chat", lambda *a, **k: json.dumps({"lines": [
        {"item": "Red onions", "qty": 3, "unit": "kg"}, {"item": "saffron", "qty": None, "unit": None},
        {"item": "", "qty": 1, "unit": "kg"}, {"item": "Tomatoes", "qty": "lots", "unit": "kg"}]}))
    out = kitchen.split_order("3kg red onions, some saffron, tomatoes", MARKETS)
    assert [l["asked"] for l in out["lines"]] == ["Red onions", "saffron", "Tomatoes"]
    assert out["lines"][0]["line_total_gbp"] == 3.6
    assert out["lines"][2]["qty"] is None  # "lots" isn't a number


@pytest.mark.parametrize("raw,want", [("cereal dispenser, empty", "cereal"), ("Yellow snack packets", "yellow snack packets"),
                                      ("Bananas (low)", "bananas"), ("milk, nearly out", "milk")])
def test_clean_name(raw, want):
    assert kitchen.clean_name(raw) == want


def _stock(video, items):
    return {"stalls": [{"stall": "Unknown stall", "items": items}], "source": {"video": video}}


def _i(name, level):
    return {"name": name, "price_gbp": None, "price_text": None, "unit": None, "currency": None,
            "stock_level": level, "seen_in_frames": 1, "needs_check": ["price not readable"]}


def test_restock_list_low_and_empty_only_worst_first():
    stocks = [_stock("a.jpg", [_i("cereal dispenser, empty", "empty"), _i("bananas", "full"), _i("milk", "low")]),
              _stock("b.jpg", [_i("Milk, nearly out", "empty"), _i("tea bags", "unknown")])]
    out = kitchen.restock_list(stocks)
    assert [(r["name"], r["stock_level"], r["source_file"]) for r in out] == [
        ("cereal dispenser, empty", "empty", "a.jpg"), ("Milk, nearly out", "empty", "b.jpg")]


def test_restock_feeds_split_order():
    stocks = [_stock("k.jpg", [_i("Bananas, low", "low"), _i("cereal dispenser, empty", "empty")])]
    out = kitchen.split_order(kitchen.restock_list(stocks), MARKETS)
    by = {l["asked"]: l for l in out["lines"]}
    assert by["Bananas, low"]["pick"]["name"] == "Bananas" and by["Bananas, low"]["source_file"] == "k.jpg"
    assert by["cereal dispenser, empty"]["pick"] is None and out["unmatched"] == ["cereal dispenser, empty"]


REAL = sorted((ROOT / "out" / "real").glob("*/stock.json")) if (ROOT / "out" / "real").exists() else []


@pytest.mark.skipif(not REAL, reason="no local real footage output")
def test_real_footage_restock_runs():
    stocks = [json.loads(p.read_text()) for p in REAL]
    rl = kitchen.restock_list(stocks)
    assert all(r["stock_level"] in ("low", "empty") and r["source_file"] for r in rl)
    out = kitchen.split_order(rl, MARKETS)
    assert len(out["lines"]) == len(rl)


@pytest.mark.parametrize("asked,offer,want", [("eggs", "Free Range Eggs", True), ("bread", "Sourdough Loaf", False),
                                             ("onions", "Red Onions", True), ("lemon", "Lemons", True)])
def test_matches(asked, offer, want):
    assert kitchen._matches(asked, offer) is want


def test_restock_with_estimates(monkeypatch):
    from stallwalk import pricecheck as pc
    pc._CACHE.clear()
    queries = []

    def fake_search(q):
        queries.append(q)
        return {"results": [{"url": "https://www.tesco.com/coke", "title": "Coca-Cola", "content": "..."},
                            {"url": "https://www.asda.com/coke", "title": "Coca-Cola", "content": "..."}]}

    monkeypatch.setattr(pc, "tavily_search", fake_search)
    monkeypatch.setattr(pc, "extract_quotes", lambda n, u, r: [{"price": 8.5, "unit": "pack", "source": 0},
                                                               {"price": 9.0, "unit": "each", "source": 1}]
                        if "coca" in n.lower() else [])
    stocks = [_stock("k.mp4", [_i("Coca-Cola cans bottom right", "low"), _i("empty dispenser", "empty"),
                               _i("corn flakes", "low"), _i("milk", "full")])]
    out = kitchen.restock_with_estimates(stocks)["lines"]
    by = {l["name"]: l for l in out}
    assert set(by) == {"Coca-Cola cans bottom right", "empty dispenser", "corn flakes"}
    coke = by["Coca-Cola cans bottom right"]
    assert coke["search_name"] == "coca-cola cans" and coke["source_file"] == "k.mp4"
    assert coke["estimate"] == {"typical_low": 8.5, "typical_high": 9.0, "unit": "each", "quotes": 2,
                                "sources": ["https://www.tesco.com/coke", "https://www.asda.com/coke"],
                                "label": "web estimate of the usual UK price, not read from a price card"}
    assert by["empty dispenser"]["estimate"] is None and by["empty dispenser"]["search_name"] is None
    assert by["corn flakes"]["estimate"] is None  # searched, no quotes
    assert "price_gbp" not in coke  # an estimate is never a price
    assert sorted(queries) == ["coca-cola cans price UK supermarket", "corn flakes price UK supermarket"]


def test_dozen_converts_both_ways():
    out = kitchen.split_order([{"item": "eggs", "qty": 24, "unit": "each"},
                               {"item": "eggs", "qty": 2, "unit": "dozen"},
                               {"item": "lemons", "qty": 2, "unit": "dozen"}], MARKETS)
    by_each, by_dozen, lemons = out["lines"]
    assert by_each["pick"]["price_gbp"] == 2.80 and by_each["line_total_gbp"] == 5.6
    assert by_dozen["line_total_gbp"] == 5.6
    assert lemons["pick"]["price_gbp"] == 0.20 and lemons["line_total_gbp"] == 4.8


def test_count_with_no_unit_totals_per_each_multibuy():
    line = kitchen.split_order([{"item": "lemons", "qty": 30, "unit": None}], MARKETS)["lines"][0]
    assert line["pick"]["price_text"] == "5 for £1" and line["line_total_gbp"] == 6.0


def test_agent_order_text_dozen_eggs(monkeypatch):
    """/api/agent/order?order=10kg potatoes, 2 dozen eggs once came back £67.20: the model read 24 dozen."""
    monkeypatch.setattr(kitchen.tf, "chat", lambda *a, **k: json.dumps({"lines": [
        {"item": "potatoes", "qty": 10, "unit": "kg"}, {"item": "eggs", "qty": 24, "unit": "dozen"}]}))
    out = kitchen.split_order("10kg potatoes, 2 dozen eggs", MARKETS)
    potatoes, eggs = out["lines"]
    assert potatoes["line_total_gbp"] == 9.0
    assert (eggs["qty"], eggs["unit"]) == (2, "dozen") and eggs["line_total_gbp"] == 5.6


@pytest.mark.parametrize("text,item,want", [("10kg potatoes, 2 dozen eggs", "eggs", (2, "dozen")),
                                           ("10kg potatoes, 2 dozen eggs", "potatoes", (10, "kg")),
                                           ("30 lemons and 3 kg salmon", "lemons", (30, None)),
                                           ("30 lemons and 3 kg salmon", "salmon", (3, "kg")),
                                           ("some saffron", "saffron", None)])
def test_qty_from_text(text, item, want):
    assert kitchen._qty_from_text(text, item) == want


def test_restock_spread_estimate_dropped(monkeypatch):
    from stallwalk import pricecheck as pc
    pc._CACHE.clear()
    monkeypatch.setattr(pc, "tavily_search", lambda q: {"results": [{"url": "https://a"}, {"url": "https://b"}]})
    monkeypatch.setattr(pc, "extract_quotes", lambda n, u, r: [{"price": 0.6, "unit": "each", "source": 0},
                                                               {"price": 2.9, "unit": "each", "source": 1}])
    out = kitchen.restock_with_estimates([_stock("k.mp4", [_i("Coca-Cola cans", "low")])])["lines"][0]
    assert out["estimate"] is None and out["estimate_note"] == "quotes too spread (can vs multipack?)"
