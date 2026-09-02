"""The agent's toolset.

Every number a buyer might quote back to a supplier is produced here, by code,
and never by the model. The model chooses which tool to call and writes the
email at the end; it does not do arithmetic. That split is deliberate — a
margin figure that exists only inside a model's context window cannot be
defended in a supplier meeting.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from strands import tool

from core.diff import assess, compare, margin, shelf_for_margin, totals
from core.model import Line, Product
from core.parse import index, parse_pricelist

DATA = Path(os.environ.get("RATCHET_DATA", "data"))


def _load_json(name: str, default):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _save_json(name: str, payload) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _price_book() -> dict[str, Line]:
    raw = _load_json("price_book.json", {})
    return {k: Line(**v) for k, v in raw.items()}


def _products() -> dict[str, Product]:
    raw = _load_json("products.json", {})
    return {k: Product(**v) for k, v in raw.items()}


@tool
def read_price_list(text: str, supplier: str = "") -> dict:
    """Parse a supplier price list into structured rows.

    Accepts CSV, semicolon or tab separated text, with headers in English or
    Albanian, and prices written in either decimal convention. Rows whose price
    cannot be read are reported as skipped rather than guessed at.

    Args:
        text: The raw price list as delimited text.
        supplier: Name of the supplier this list came from.

    Returns:
        A dict with the parsed rows, the row count, and how many were skipped.
    """
    total_rows = len([l for l in text.strip().splitlines() if l.strip()])
    lines = parse_pricelist(text, supplier=supplier)
    return {
        "supplier": supplier,
        "rows_parsed": len(lines),
        "rows_skipped": max(0, total_rows - 1 - len(lines)),
        "lines": [l.as_dict() for l in lines],
    }


@tool
def compare_to_price_book(text: str, supplier: str = "") -> dict:
    """Compare an incoming price list against what we are currently paying.

    Movements below half a percent are treated as noise — rounding, currency
    drift and rebate artefacts — and reported as unchanged.

    Args:
        text: The raw incoming price list as delimited text.
        supplier: Name of the supplier this list came from.

    Returns:
        Every SKU that rose, fell, appeared or was withdrawn, with the old and
        new unit cost and the percentage movement.
    """
    incoming = index(parse_pricelist(text, supplier=supplier))
    changes = compare(_price_book(), incoming)
    moved = [c for c in changes if c.kind != "unchanged"]
    return {
        "supplier": supplier,
        "skus_on_list": len(incoming),
        "skus_moved": len(moved),
        "changes": [c.as_dict() for c in moved],
    }


@tool
def price_the_damage(text: str, supplier: str = "") -> dict:
    """Rank the movements by how much money they actually cost us in a year.

    A twelve percent rise on a line bought twice a year is a footnote. A two
    percent rise on the line that moves four hundred units a month is the one
    worth a phone call. This ranks by annual euro impact, using real sales
    volume, and flags any line whose margin now falls below its target.

    Args:
        text: The raw incoming price list as delimited text.
        supplier: Name of the supplier this list came from.

    Returns:
        Findings sorted by annual cost impact, plus totals for the whole list.
    """
    incoming = index(parse_pricelist(text, supplier=supplier))
    changes = compare(_price_book(), incoming)
    findings = assess(changes, _products())
    return {
        "supplier": supplier,
        "totals": totals(findings),
        "findings": [f.as_dict() for f in findings],
    }


@tool
def check_margin(sku: str, unit_cost: float) -> dict:
    """Check what a given unit cost does to one product's margin.

    Args:
        sku: The product code.
        unit_cost: The cost per unit, excluding VAT.

    Returns:
        The resulting margin, whether it breaks the target, and the shelf price
        that would restore the target if it does.
    """
    p = _products().get(sku)
    if not p:
        return {"sku": sku, "known": False, "note": "No shelf price or target on file for this SKU."}
    m = margin(p.shelf_price, unit_cost, p.vat_rate)
    breaks = m < p.target_margin
    return {
        "sku": sku,
        "known": True,
        "shelf_price": p.shelf_price,
        "vat_rate": p.vat_rate,
        "unit_cost": unit_cost,
        "margin": round(m, 6),
        "target_margin": p.target_margin,
        "breaks_target": breaks,
        "shelf_price_needed": shelf_for_margin(unit_cost, p.target_margin, p.vat_rate) if breaks else None,
    }


@tool
def buying_history(sku: str) -> dict:
    """What we know about buying and selling one SKU.

    Args:
        sku: The product code.

    Returns:
        Current cost on the price book, shelf price, monthly volume and target
        margin, or a note that the SKU is unknown.
    """
    book, prods = _price_book(), _products()
    line, p = book.get(sku), prods.get(sku)
    if not line and not p:
        return {"sku": sku, "known": False}
    return {
        "sku": sku,
        "known": True,
        "name": line.name if line else "",
        "supplier": line.supplier if line else "",
        "current_unit_cost": line.unit_cost if line else None,
        "shelf_price": p.shelf_price if p else None,
        "monthly_units": p.monthly_units if p else None,
        "target_margin": p.target_margin if p else None,
    }


@tool
def commit_price_book(text: str, supplier: str = "") -> dict:
    """Accept an incoming list as the new baseline, once it has been reviewed.

    Call this only after the movements have been reported to the buyer.
    Committing silently would destroy the very history that makes the next
    comparison possible.

    Args:
        text: The raw incoming price list as delimited text.
        supplier: Name of the supplier this list came from.

    Returns:
        How many lines the price book now holds.
    """
    book = _price_book()
    for sku, line in index(parse_pricelist(text, supplier=supplier)).items():
        book[sku] = line
    _save_json("price_book.json", {k: v.as_dict() for k, v in book.items()})
    return {"skus_in_book": len(book), "committed": True}
