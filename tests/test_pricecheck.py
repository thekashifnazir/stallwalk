import copy

import pytest

from stallwalk import pricecheck as pc

STOCK = {"stalls": [
    {"stall": "Patel's Fruit & Veg", "items": [
        {"name": "Tomatoes", "price_gbp": 1.8, "price_text": "£1.80/kg", "unit": "kg",
         "deal": None, "seen_in_frames": 1, "needs_check": []},
        {"name": "Avocados", "price_gbp": 1, "price_text": "£1 each", "unit": "each",
         "deal": None, "seen_in_frames": 2, "needs_check": []},
    ]},
    {"stall": "Billy's Fresh Fish", "items": [
        {"name": "Cod Fillet", "price_gbp": 14.99, "price_text": "£14.99/kg", "unit": "kg",
         "deal": None, "seen_in_frames": 7, "needs_check": ["price differs across frames: [4.99, 14.99]"]},
        {"name": "Salmon Fillet", "price_gbp": 60.0, "price_text": "£60/kg", "unit": "kg",
         "deal": None, "seen_in_frames": 3, "needs_check": []},
        {"name": "Mussels", "price_gbp": 6, "price_text": "£6/kg", "unit": "kg",
         "deal": None, "seen_in_frames": 2, "needs_check": []},
        {"name": "Smoked Haddock", "price_gbp": None, "price_text": None, "unit": None,
         "deal": None, "seen_in_frames": 1, "needs_check": ["price not readable"]},
    ]},
]}

# Recorded-shape replies: Tavily results and the model's extracted range, per search query.
TAVILY = {
    "Tomatoes": [{"url": "https://a.example/tom", "title": "Tomatoes", "content": "£1.50-£3.00 per kg"}],
    "Avocados": [{"url": "https://a.example/avo", "title": "Avocado", "content": "£0.80 each"}],
    "Cod Fillet": [{"url": "https://a.example/cod", "title": "Cod", "content": "£15-£22/kg"}],
    "Salmon Fillet": [{"url": f"https://a.example/salmon{i}", "title": "Salmon", "content": "£18-£25/kg"} for i in range(5)],
    "Mussels": [{"url": "https://a.example/mussels", "title": "Mussels", "content": "£4 per 500g pack"}],
}
TYPICAL = {
    "Tomatoes": {"typical_low": 1.5, "typical_high": 3.0, "unit": "kg"},
    "Avocados": {"typical_low": 0.8, "typical_high": 1.5, "unit": "each"},
    "Cod Fillet": {"typical_low": 15, "typical_high": 22, "unit": "per kg"},
    "Salmon Fillet": {"typical_low": 18, "typical_high": 25, "unit": "kg"},
    "Mussels": {"typical_low": 4, "typical_high": 4, "unit": "500g pack"},
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    pc._CACHE.clear()
    calls = {"tavily": [], "model": []}

    def fake_search(query):
        calls["tavily"].append(query)
        name = next(n for n in TAVILY if query.startswith(n))
        return {"results": TAVILY[name]}

    def fake_extract(name, unit, results):
        calls["model"].append(name)
        return TYPICAL[name]

    monkeypatch.setattr(pc, "tavily_search", fake_search)
    monkeypatch.setattr(pc, "extract_typical", fake_extract)
    return calls


def _item(stock, name):
    return next(i for s in stock["stalls"] for i in s["items"] if i["name"] == name)


def test_prices_never_change_and_input_untouched():
    before = copy.deepcopy(STOCK)
    out = pc.check_prices(STOCK)
    assert STOCK == before
    for s0, s1 in zip(before["stalls"], out["stalls"]):
        for a, b in zip(s0["items"], s1["items"]):
            assert (a["price_gbp"], a["price_text"]) == (b["price_gbp"], b["price_text"])


def test_verdicts():
    out = pc.check_prices(STOCK)
    assert _item(out, "Tomatoes")["price_check"]["verdict"] == "usual"
    assert _item(out, "Avocados")["price_check"]["verdict"] == "usual"
    assert _item(out, "Cod Fillet")["price_check"]["verdict"] == "usual"  # "per kg" counts as kg
    assert _item(out, "Salmon Fillet")["price_check"]["verdict"] == "high"
    assert _item(out, "Mussels")["price_check"]["verdict"] == "unknown"  # 500g pack vs kg


def test_high_adds_flag_with_sources():
    salmon = _item(pc.check_prices(STOCK), "Salmon Fillet")
    assert salmon["needs_check"] == ["about 2x the usual UK price (usual £18.00-£25.00 per kg)"]
    assert len(salmon["price_check"]["sources"]) == 3
    assert "_flag" not in salmon["price_check"]


def test_usual_adds_no_flag():
    assert _item(pc.check_prices(STOCK), "Tomatoes")["needs_check"] == []


def test_unpriced_item_not_searched(offline):
    out = pc.check_prices(STOCK)
    assert "price_check" not in _item(out, "Smoked Haddock")
    assert not any(q.startswith("Smoked Haddock") for q in offline["tavily"])


def test_cap_prefers_clean_items(offline):
    out = pc.check_prices(STOCK, max_items=4)
    assert "price_check" not in _item(out, "Cod Fillet")  # the only flagged priced item goes last
    assert len(offline["tavily"]) == 4
    assert offline["tavily"][0] == "Tomatoes price per kg UK"


def test_failure_is_unknown(monkeypatch):
    def boom(query):
        raise TimeoutError("slow")
    monkeypatch.setattr(pc, "tavily_search", boom)
    out = pc.check_prices(STOCK)
    chk = _item(out, "Salmon Fillet")["price_check"]
    assert chk["verdict"] == "unknown" and chk["sources"] == []
    assert _item(out, "Salmon Fillet")["needs_check"] == []


def test_cache_per_item(offline, tmp_path):
    path = tmp_path / "cache.json"
    pc.check_prices(STOCK, cache_path=path)
    n = len(offline["tavily"])
    pc._CACHE.clear()
    pc.check_prices(STOCK, cache_path=path)
    assert len(offline["tavily"]) == n  # second run served from the file


@pytest.mark.parametrize("price,typ,want", [
    (10, {"typical_low": 2, "typical_high": 4, "unit": "kg"}, "high"),
    (0.5, {"typical_low": 2, "typical_high": 4, "unit": "kg"}, "low"),
    (8, {"typical_low": 2, "typical_high": 4, "unit": "kg"}, "usual"),
    (3, {"typical_low": None, "typical_high": None, "unit": None}, "unknown"),
    (3, {"typical_low": 2, "typical_high": 4, "unit": "each"}, "unknown"),
    (3, {"typical_low": 4, "typical_high": 2, "unit": "kg"}, "usual"),
])
def test_judge(price, typ, want):
    assert pc.judge(price, "kg", typ)[0] == want


def test_hard_cap(offline, monkeypatch):
    monkeypatch.setattr(pc, "MAX_SEARCHES", 2)
    pc.check_prices(STOCK, max_items=100)
    assert len(offline["tavily"]) == 2


@pytest.mark.parametrize("raw,want", [("per kg", "kg"), ("KG", "kg"), ("kgs", "kg"), ("200 g", "200g"),
                                      ("each", "each"), ("500g pack", "500g pack"), (None, None)])
def test_unit(raw, want):
    assert pc._unit(raw) == want
