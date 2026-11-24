"""Stock list -> agent-buyable product records (ACP and UCP shapes).

Pure, deterministic mapping: no model calls, no server. Every item on the stock list
comes out, including ones whose price couldn't be read or disagreed across frames.
Those keep their place but are marked `buyable: False` with the reasons in
`needs_check`, so a shopping agent can see the item exists without trusting the price.

The record shapes follow the ACP and UCP builders (_build_acp_schema,
_build_ucp_schema and helpers) in NVIDIA's Retail Catalog Enrichment blueprint,
src/backend/main.py. That file is
  SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES.
  SPDX-License-Identifier: Apache-2.0
We kept the field layout and cut the fields a market stall never has (GTIN,
shipping dimensions, energy class, installments). No code from it is copied unchanged.
"""
import re

CURRENCY = "GBP"
SOURCE = "stallwalk"


# ── helpers (same shape as the blueprint's _empty_money / _empty_measurement) ──

def _money(amount: float | None) -> dict:
    return {"amount": round(amount, 2) if amount is not None else None,
            "currency": CURRENCY if amount is not None else None}


def _measure(unit: str | None) -> dict:
    return {"value": 1 if unit else None, "unit": unit or None}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "unknown"


def _short_text(text: str, max_length: int = 65) -> str:
    if len(text) <= max_length:
        return text
    trimmed = text[:max_length].rstrip()
    return trimmed.rsplit(" ", 1)[0].rstrip() if " " in trimmed else trimmed


def _context(stall_name: str, item: dict) -> dict:
    """Normalise one stock item before shaping it for either protocol."""
    name = (item.get("name") or "").strip() or "Unnamed item"
    price = item.get("price_gbp")
    price = float(price) if isinstance(price, (int, float)) else None
    flags = list(item.get("needs_check") or [])
    if price is None and not any("price" in f for f in flags):
        flags.append("price not readable")
    deal = item.get("deal") or None
    unit = item.get("unit") or None
    price_text = item.get("price_text") or None
    highlights = [h for h in (price_text, deal) if h]
    seller = _slug(stall_name)
    return {
        "id": f"{seller}/{_slug(name)}",
        "title": name,
        "description": f"{name} from {stall_name}" + (f", {price_text}" if price_text else ""),
        "stall": stall_name,
        "seller_id": seller,
        "price": price,
        "price_text": price_text,
        "unit": unit,
        "deal": deal,
        "highlights": highlights,
        "seen_in_frames": int(item.get("seen_in_frames") or 0),
        "needs_check": flags,
        "buyable": price is not None and not flags,
        "price_status": "confirmed" if price is not None and not flags
                        else ("unreadable" if price is None else "needs_check"),
    }


# ── public API ──

def to_acp(stall_name: str, item: dict) -> dict:
    """One stock item as an ACP-shaped product record."""
    c = _context(stall_name, item)
    return {
        "product": {
            "id": c["id"],
            "title": c["title"],
            "description": c["description"],
            "brand": None,
            "attributes": {"condition": "new", "size": None, "weight": _measure(None)},
            "categories": [],
            "tags": [],
            "identifiers": {"gtin": None, "mpn": None, "sku": c["id"]},
            "highlights": c["highlights"],
        },
        "pricing": {
            "currency": CURRENCY,
            "price": c["price"],
            "price_text": c["price_text"],
            "sale_price": None,
            "deal": c["deal"],
            "availability": "in_stock",
            "price_status": c["price_status"],
            "unit_pricing": {"measure": _measure(c["unit"]), "base_measure": _measure(c["unit"])},
        },
        "agent_actions": {
            "discoverable": True,
            "buyable": c["buyable"],
            "returnable": False,
            "comparable": c["price"] is not None,
            "subscribable": False,
        },
        "fulfillment": {
            "shipping": {"eligible": False},
            "pickup_eligible": True,
            "digital_delivery": False,
        },
        "needs_check": c["needs_check"],
        "marketplace": {"external_seller_id": c["seller_id"], "seller_name": c["stall"]},
        "metadata": {
            "locale": "en-GB",
            "enrichment_source": SOURCE,
            "seen_in_frames": c["seen_in_frames"],
        },
    }


def to_ucp(stall_name: str, item: dict) -> dict:
    """One stock item as a UCP-shaped (flat, feed-style) product record."""
    c = _context(stall_name, item)
    return {
        "id": c["id"],
        "title": c["title"],
        "description": c["description"],
        "link": None,
        "image_link": None,
        "availability": "in_stock",
        "price": _money(c["price"]),
        "price_text": c["price_text"],
        "price_status": c["price_status"],
        "sale_price": _money(None),
        "unit_pricing_measure": _measure(c["unit"]),
        "unit_pricing_base_measure": _measure(c["unit"]),
        "product_type": None,
        "brand": None,
        "gtin": None,
        "mpn": None,
        "identifier_exists": False,
        "condition": "new",
        "product_highlight": c["highlights"],
        "custom_label_0": c["deal"],
        "short_title": _short_text(c["title"]),
        "external_seller_id": c["seller_id"],
        "seller_name": c["stall"],
        "buyable": c["buyable"],
        "needs_check": c["needs_check"],
        "shipping": [],
        "pickup_eligible": True,
        "seen_in_frames": c["seen_in_frames"],
    }


def export_stock(stock: dict) -> dict[str, list[dict]]:
    """Whole stock list (walk.merge output) -> {"acp": [...], "ucp": [...]}, stall order kept."""
    acp, ucp = [], []
    for stall in stock.get("stalls", []):
        name = stall.get("stall") or "Unknown stall"
        for item in stall.get("items", []):
            acp.append(to_acp(name, item))
            ucp.append(to_ucp(name, item))
    return {"acp": acp, "ucp": ucp}
