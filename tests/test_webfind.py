import pytest

from stallwalk import pricecheck as pc
from stallwalk import webfind as wf

# Recorded shape: Tavily results and the quotes Nemotron lists, per item.
RES = {
    "shallots": [{"url": "https://www.tesco.com/groceries/shallots", "title": "Tesco Shallots 400g"},
                 {"url": "https://www.sainsburys.co.uk/gol-ui/product/shallots", "title": "Sainsbury's Shallots"},
                 {"url": "https://www.asda.com/shallots", "title": "ASDA Shallots"}],
    "white wine": [{"url": "https://www.tesco.com/wine", "title": "Tesco White Wine"},
                   {"url": "https://www.waitrose.com/wine", "title": "Waitrose White Wine"}],
    "double cream": [{"url": "https://www.ocado.com/cream", "title": "Double Cream 300ml"}],
    "saffron": [],
}
QUOTES = {
    "shallots": [{"price": 1.10, "unit": "each", "source": 0}, {"price": 1.25, "unit": "pack", "source": 1},
                 {"price": 0.95, "unit": "each", "source": 2}],
    "white wine": [{"price": 4.50, "unit": "each", "source": 0}, {"price": 25.0, "unit": "each", "source": 1}],
    "double cream": [{"price": 1.45, "unit": "each", "source": 0}],
    "saffron": [],
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    pc._CACHE.clear()
    calls = []

    def fake_search(q):
        calls.append(q)
        return {"results": RES[next(k for k in RES if q.startswith(k))]}

    monkeypatch.setattr(pc, "tavily_search", fake_search)
    monkeypatch.setattr(pc, "extract_quotes", lambda n, u, r: QUOTES[n])
    return calls


def _by(out):
    return {r["name"]: r for r in out["items"]}


def test_split_items():
    assert wf.split_items("shallots, white wine and double cream; Shallots") == ["shallots", "white wine", "double cream"]


def test_range_stores_and_two_links():
    r = _by(wf.web_find(["shallots"]))["shallots"]
    assert (r["typical_low"], r["typical_high"], r["unit"], r["quotes"]) == (0.95, 1.25, "each", 3)
    assert r["stores"] == ["Asda", "Sainsbury's", "Tesco"]
    assert len(r["sources"]) == 2 and r["label"] == "web estimate, online price"


def test_rules_one_quote_spread_and_none():
    rows = _by(wf.web_find(["white wine", "double cream", "saffron"]))
    assert rows["white wine"]["typical_low"] is None and "too spread" in rows["white wine"]["note"]
    assert rows["double cream"]["typical_low"] is None and "only one online price" in rows["double cream"]["note"]
    assert rows["saffron"]["note"] == "no online price found"


def test_answer_is_honest_about_location():
    ans = wf.web_find(["shallots", "saffron"])["answer"]
    assert ans.startswith("Web estimate, online prices:")
    assert "shallots: 95p to £1.25 each online at Asda and Sainsbury's" in ans
    assert "Check your local store" in ans
    assert "nearby" not in ans.lower() and "open" not in ans.lower()


def test_cap_per_call(offline):
    out = wf.web_find([f"shallots {i}" for i in range(25)])
    assert len(offline) == wf.MAX_SEARCHES and len(out["skipped"]) == 5
    assert "and 21 more" in out["answer"]


def test_cache_shared_with_pricecheck(offline):
    wf.web_find(["shallots"])
    wf.web_find(["shallots"])
    assert offline.count("shallots price UK supermarket") == 1
