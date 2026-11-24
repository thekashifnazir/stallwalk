import copy
import json

import pytest

from stallwalk import pricecheck as pc

REAL_SEARCH = pc.tavily_search  # saved before the offline fixture swaps it out

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


def _res(name, n=3):
    return [{"url": f"https://www.tesco.com/{name.lower().replace(' ', '-')}/{i}", "title": name,
             "content": "..."} for i in range(n)]


# Recorded shape: Tavily results and the quotes the model lists, per item.
TAVILY = {n: _res(n) for n in ["Tomatoes", "Avocados", "Cod Fillet", "Salmon Fillet", "Mussels", "Smoked Haddock"]}
QUOTES = {
    "Tomatoes": [{"price": 1.5, "unit": "kg", "source": 0}, {"price": 3.0, "unit": "per kg", "source": 1}],
    "Avocados": [{"price": 0.8, "unit": "each", "source": 0}, {"price": 1.5, "unit": "each", "source": 2}],
    "Cod Fillet": [{"price": 15, "unit": "/KG", "source": 0}, {"price": 22, "unit": "kg", "source": 1}],
    "Salmon Fillet": [{"price": 18, "unit": "kg", "source": 0}, {"price": 25, "unit": "kg", "source": 1},
                      {"price": 4.5, "unit": "each", "source": 2}],
    "Mussels": [{"price": 4, "unit": "500g pack", "source": 0}],
    "Smoked Haddock": [{"price": 3.25, "unit": "each", "source": 0}, {"price": 0.95, "unit": "100g", "source": 0},
                       {"price": 3.75, "unit": "pack", "source": 1}],
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
        return QUOTES[name]

    monkeypatch.setattr(pc, "tavily_search", fake_search)
    monkeypatch.setattr(pc, "extract_quotes", fake_extract)
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
    assert _item(out, "Cod Fillet")["price_check"]["verdict"] == "usual"  # "/KG" counts as kg
    assert _item(out, "Salmon Fillet")["price_check"]["verdict"] == "high"
    assert _item(out, "Mussels")["price_check"]["verdict"] == "unknown"  # 500g pack vs kg


def test_range_uses_like_units_only():
    chk = _item(pc.check_prices(STOCK), "Salmon Fillet")["price_check"]
    assert (chk["typical_low"], chk["typical_high"], chk["unit"], chk["quotes"]) == (18, 25, "kg", 2)
    assert chk["sources"] == ["https://www.tesco.com/salmon-fillet/0", "https://www.tesco.com/salmon-fillet/1"]


def test_high_adds_flag_with_sources():
    salmon = _item(pc.check_prices(STOCK), "Salmon Fillet")
    assert salmon["needs_check"] == ["about 2x the usual UK price (UK supermarkets £18.00-£25.00 per kg)"]
    assert "_flag" not in salmon["price_check"]


def test_usual_adds_no_flag():
    assert _item(pc.check_prices(STOCK), "Tomatoes")["needs_check"] == []


def test_no_card_price_gets_labelled_estimate():
    out = pc.check_prices(STOCK)
    haddock = _item(out, "Smoked Haddock")
    chk = haddock["price_check"]
    assert haddock["price_gbp"] is None  # an estimate is never a price
    assert chk["verdict"] == "estimate" and chk["label"] == pc.ESTIMATE_LABEL
    assert (chk["typical_low"], chk["typical_high"], chk["unit"], chk["quotes"]) == (3.25, 3.75, "each", 2)
    assert haddock["needs_check"] == ["price not readable"]  # no flag added for an estimate


def test_no_card_query_has_no_unit(offline):
    pc.check_prices(STOCK)
    assert "Smoked Haddock price UK supermarket" in offline["tavily"]


def test_cap_prefers_carded_clean_items(offline):
    out = pc.check_prices(STOCK, max_items=4)
    assert "price_check" not in _item(out, "Cod Fillet")  # flagged card price goes after clean ones
    assert "price_check" not in _item(out, "Smoked Haddock")  # no-card items go last
    assert len(offline["tavily"]) == 4
    assert offline["tavily"][0] == "Tomatoes price per kg UK supermarket"


def test_hard_cap(offline, monkeypatch):
    monkeypatch.setattr(pc, "MAX_SEARCHES", 2)
    pc.check_prices(STOCK, max_items=100)
    assert len(offline["tavily"]) == 2


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


def test_cache_rejudges_new_price(offline):
    first = pc.check_prices(STOCK)
    cheaper = copy.deepcopy(STOCK)
    _item(cheaper, "Salmon Fillet")["price_gbp"] = 20.0
    second = pc.check_prices(cheaper)
    assert _item(first, "Salmon Fillet")["price_check"]["verdict"] == "high"
    assert _item(second, "Salmon Fillet")["price_check"]["verdict"] == "usual"
    assert offline["tavily"].count("Salmon Fillet price per kg UK supermarket") == 1


def test_old_cache_format_ignored(offline, tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"version": 2, "items": {"tomatoe|kg": {"quotes": [], "urls": []}}}))
    out = pc.check_prices(STOCK, cache_path=path)
    assert _item(out, "Tomatoes")["price_check"]["typical_high"] == 3.0
    assert json.loads(path.read_text())["version"] == pc.CACHE_VERSION


def test_seeded_misread_flags_with_sources(monkeypatch):
    """The demo moment: £1.20/kg onions misread as £12/kg get flagged, with where the usual price came from."""
    res = [{"url": "https://www.tesco.com/groceries/en-GB/products/red-onions", "title": "Tesco Red Onions",
            "content": "Tesco Red Onions Loose £1.10/kg"},
           {"url": "https://www.sainsburys.co.uk/gol-ui/product/red-onions", "title": "Sainsbury's Red Onions",
            "content": "£1.25 / kg"}]
    monkeypatch.setattr(pc, "tavily_search", lambda q: {"results": res})
    monkeypatch.setattr(pc, "extract_quotes", lambda n, u, r: [{"price": 1.10, "unit": "kg", "source": 0},
                                                               {"price": 1.25, "unit": "kg", "source": 1}])
    stock = {"stalls": [{"stall": "Patel's Fruit & Veg", "items": [
        {"name": "Red Onions", "price_gbp": 12.0, "price_text": "£12/kg", "unit": "kg",
         "deal": None, "seen_in_frames": 1, "needs_check": []}]}]}
    onions = pc.check_prices(stock)["stalls"][0]["items"][0]
    assert onions["price_gbp"] == 12.0  # flagged, never corrected
    assert onions["price_check"]["verdict"] == "high"
    assert onions["needs_check"] == ["about 10x the usual UK price (UK supermarkets £1.10-£1.25 per kg)"]
    assert onions["price_check"]["sources"] == [r["url"] for r in res]


def test_search_body_limits_to_grocers(monkeypatch):
    sent = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"results": []}'

    def fake_urlopen(req, timeout):
        sent["body"] = json.loads(req.data)
        sent["auth"] = req.get_header("Authorization")
        sent["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(pc.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    REAL_SEARCH("Red Onions price per kg UK supermarket")
    assert sent["body"]["include_domains"] == pc.GROCERS
    assert sent["auth"] == "Bearer test-key" and sent["timeout"] == pc.TIMEOUT


@pytest.mark.parametrize("price,rng,want", [
    (10, {"typical_low": 2, "typical_high": 4, "unit": "kg", "quotes": 2}, "high"),
    (0.5, {"typical_low": 2, "typical_high": 4, "unit": "kg", "quotes": 2}, "low"),
    (8, {"typical_low": 2, "typical_high": 4, "unit": "kg", "quotes": 2}, "usual"),
    (10, {"typical_low": 4, "typical_high": 4, "unit": "kg", "quotes": 1}, "unknown"),  # one quote can't flag
    (5, {"typical_low": 4, "typical_high": 4, "unit": "kg", "quotes": 1}, "usual"),
    (3, {"typical_low": None, "typical_high": None, "unit": None, "quotes": 0}, "unknown"),
    (3, {"typical_low": 2, "typical_high": 4, "unit": "each", "quotes": 2}, "unknown"),
    (3, {"typical_low": 4, "typical_high": 2, "unit": "kg", "quotes": 2}, "usual"),
])
def test_judge(price, rng, want):
    assert pc.judge(price, "kg", rng)[0] == want


@pytest.mark.parametrize("raw,want", [("per kg", "kg"), ("KG", "kg"), ("kgs", "kg"), ("/KG", "kg"),
                                      ("200 g", "200g"), ("each", "each"), ("pack", "each"),
                                      ("500g pack", "500g pack"), (None, None), ("£", "£")])
def test_unit(raw, want):
    assert pc._unit(raw) == want


def test_halloumi_style_junk_quote_cannot_flag():
    """Last live run: one junk 8p quote made a false 'about 44x' flag. One quote can't flag now."""
    rng = pc.price_range([{"price": 0.08, "unit": "each", "source": 0}], ["https://x"], "each")
    assert pc.judge(3.5, "each", rng) == ("unknown", None)


def test_rerun_is_idempotent():
    once = pc.check_prices(STOCK)
    twice = pc.check_prices(once)
    assert _item(twice, "Salmon Fillet")["needs_check"] == _item(once, "Salmon Fillet")["needs_check"]
    assert _item(twice, "Cod Fillet")["needs_check"] == ["price differs across frames: [4.99, 14.99]"]


def test_stale_check_dropped_when_not_rechecked():
    stale = copy.deepcopy(STOCK)
    _item(stale, "Smoked Haddock")["price_check"] = {"verdict": "high"}
    out = pc.check_prices(stale, max_items=1)
    assert "price_check" not in _item(out, "Smoked Haddock")


def test_stray_quote_trimmed():
    q = [{"price": 0.08, "unit": "each", "source": 0}, {"price": 3.65, "unit": "each", "source": 1}]
    rng = pc.price_range(q, ["https://a", "https://b"], None)
    assert (rng["typical_low"], rng["typical_high"], rng["quotes"], rng["sources"]) == (3.65, 3.65, 1, ["https://b"])
    wide = [{"price": p, "unit": "kg", "source": 0} for p in (0.8, 1.5, 2.0, 3.0, 8.88)]
    assert pc.price_range(wide, ["https://a"], "kg")["quotes"] == 5  # a real wide range is kept
