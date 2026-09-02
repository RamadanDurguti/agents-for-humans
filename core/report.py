"""Produce the full review of one incoming price list.

This is the deterministic half of Ratchet and it runs on the standard library
alone — no SDK, no model, no network. The agent calls into the same functions.
Keeping this runnable on its own is what makes the numbers testable.
"""
from __future__ import annotations

import json
from pathlib import Path

from .diff import assess, compare, totals
from .model import Line, Product
from .parse import index, parse_pricelist


def load_products(path: str | Path) -> dict[str, Product]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: Product(sku=k, **v) for k, v in raw.items()}


def review(
    baseline_csv: str,
    incoming_csv: str,
    products: dict[str, Product],
    supplier: str = "",
) -> dict:
    """Compare two price lists and price every movement."""
    old = index(parse_pricelist(baseline_csv, supplier=supplier))
    new = index(parse_pricelist(incoming_csv, supplier=supplier))
    changes = compare(old, new)
    findings = assess(changes, products)
    return {
        "supplier": supplier,
        "baseline_skus": len(old),
        "incoming_skus": len(new),
        "totals": totals(findings),
        "findings": [f.as_dict() for f in findings],
    }


def draft_note(report: dict, top_n: int = 4) -> str:
    """A plain, factual supplier message built from the findings alone.

    The agent writes a better one, but this exists so the tool still produces a
    usable draft with no model available at all — and so there is something to
    compare the model's version against.
    """
    ups = [f for f in report["findings"] if f["kind"] == "increase"][:top_n]
    if not ups:
        return "No price increases on this list."
    t = report["totals"]
    lines = [
        f"Subject: Price changes on your {report['supplier'] or 'latest'} list",
        "",
        "Hello,",
        "",
        f"Comparing your new list against the one we have been buying on, "
        f"{t['increases']} of {report['incoming_skus']} lines have gone up. "
        f"At our current volumes that is {t['annual_exposure']:,.2f} EUR a year.",
        "",
        "The largest by value:",
    ]
    for f in ups:
        pct = (f["delta_pct"] or 0) * 100
        piece = (
            f"  - {f['sku']} {f['name']}: {f['old_cost']:.2f} to {f['new_cost']:.2f} "
            f"({pct:+.1f}%)"
        )
        if f["annual_units"]:
            piece += f", {f['annual_units']:,.0f} units a year, {f['annual_cost_delta']:,.2f} EUR"
        lines.append(piece)
    lines += [
        "",
        "Can you tell us what is driving these, and whether the previous prices "
        "can be held on the lines above for the next quarter?",
        "",
        "Thank you,",
    ]
    return "\n".join(lines)
