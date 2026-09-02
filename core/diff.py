"""Compare two price lists and price the difference against what we buy.

Everything here is arithmetic. No model is involved and none is wanted: a
buyer challenging a supplier has to be able to point at the rule that fired,
and "the model thought so" does not survive that conversation.
"""
from __future__ import annotations

from .model import Change, Finding, Line, Product

# Below this the movement is rounding, currency drift, or a rebate artefact.
NOISE_PCT = 0.005


def compare(old: dict[str, Line], new: dict[str, Line]) -> list[Change]:
    """Every SKU that moved, appeared, or vanished between two lists."""
    changes: list[Change] = []
    for sku in sorted(set(old) | set(new)):
        a, b = old.get(sku), new.get(sku)
        if a and b:
            if abs(b.unit_cost - a.unit_cost) < 1e-9:
                kind = "unchanged"
            else:
                pct = (b.unit_cost - a.unit_cost) / a.unit_cost if a.unit_cost else 0.0
                if abs(pct) < NOISE_PCT:
                    kind = "unchanged"
                else:
                    kind = "increase" if b.unit_cost > a.unit_cost else "decrease"
            changes.append(
                Change(sku, b.name or a.name, kind, a.unit_cost, b.unit_cost,
                       b.supplier or a.supplier, b.currency)
            )
        elif b:
            changes.append(Change(sku, b.name, "new", None, b.unit_cost, b.supplier, b.currency))
        else:
            changes.append(Change(sku, a.name, "withdrawn", a.unit_cost, None, a.supplier, a.currency))
    return changes


def net_shelf(shelf_price: float, vat_rate: float) -> float:
    """Shelf price with VAT stripped out — the number margin is measured on."""
    return shelf_price / (1.0 + vat_rate)


def margin(shelf_price: float, unit_cost: float, vat_rate: float) -> float:
    """Gross margin as a fraction of the ex-VAT selling price."""
    net = net_shelf(shelf_price, vat_rate)
    if net <= 0:
        return 0.0
    return (net - unit_cost) / net


def shelf_for_margin(unit_cost: float, target: float, vat_rate: float) -> float:
    """The shelf price, VAT included, that restores the target margin.

    Rounded up to the nearest cent — rounding down would quietly re-open the
    same margin hole the tool exists to close.
    """
    if target >= 1.0:
        raise ValueError("target margin must be below 1.0")
    net_needed = unit_cost / (1.0 - target)
    gross = net_needed * (1.0 + vat_rate)
    return _ceil_cents(gross)


def _ceil_cents(x: float) -> float:
    cents = x * 100.0
    whole = int(cents)
    if cents - whole > 1e-9:
        whole += 1
    return round(whole / 100.0, 2)


def assess(changes: list[Change], products: dict[str, Product]) -> list[Finding]:
    """Turn raw movements into findings ranked by money, not by percentage.

    A 12% rise on something bought twice a year is a footnote. A 2% rise on the
    line that moves 400 units a month is the one worth a phone call. Sorting by
    annual euro impact is the whole point of this step.
    """
    findings: list[Finding] = []
    for ch in changes:
        if ch.kind in ("unchanged", "withdrawn"):
            continue
        p = products.get(ch.sku)
        annual_units = (p.monthly_units * 12.0) if p else 0.0
        delta = ch.delta_abs or 0.0
        annual_delta = round(delta * annual_units, 2)

        m_before = m_after = shelf_needed = None
        breaks = already_below = False
        reasons: list[str] = []

        if ch.kind == "increase":
            reasons.append(
                f"Unit cost rose from {ch.old_cost:.4f} to {ch.new_cost:.4f} "
                f"({(ch.delta_pct or 0) * 100:+.1f}%)."
            )
        elif ch.kind == "decrease":
            reasons.append(
                f"Unit cost fell from {ch.old_cost:.4f} to {ch.new_cost:.4f} "
                f"({(ch.delta_pct or 0) * 100:+.1f}%)."
            )
        else:
            reasons.append(f"New line on this list at {ch.new_cost:.4f}.")

        if p and p.shelf_price > 0 and ch.new_cost is not None:
            m_after = round(margin(p.shelf_price, ch.new_cost, p.vat_rate), 6)
            if ch.old_cost is not None:
                m_before = round(margin(p.shelf_price, ch.old_cost, p.vat_rate), 6)
            breaks = m_after < p.target_margin
            already_below = m_before is not None and m_before < p.target_margin
            if breaks:
                shelf_needed = shelf_for_margin(ch.new_cost, p.target_margin, p.vat_rate)
                if already_below:
                    # Worth separating: this is a pricing problem the shop
                    # already had, not something the supplier just did. Taking
                    # the wrong one of those to a supplier wastes the meeting.
                    reasons.append(
                        f"Already below the {p.target_margin * 100:.0f}% target before this list "
                        f"({m_before * 100:.1f}%), and this change takes it to {m_after * 100:.1f}%. "
                        f"Shelf price would need {shelf_needed:.2f} to reach target."
                    )
                else:
                    reasons.append(
                        f"This change breaks the {p.target_margin * 100:.0f}% target: margin falls "
                        f"from {m_before * 100:.1f}% to {m_after * 100:.1f}%. "
                        f"Shelf price would need {shelf_needed:.2f} to restore it."
                    )
            if m_after is not None and m_after < 0:
                reasons.append("This line is now sold below cost.")

        if annual_units and ch.kind == "increase":
            reasons.append(
                f"At {annual_units:,.0f} units a year that is {annual_delta:,.2f} "
                f"{ch.currency} of extra cost."
            )
        elif not annual_units and ch.kind != "new":
            reasons.append("No sales volume on file, so the annual impact is unknown.")

        findings.append(
            Finding(
                change=ch,
                annual_units=annual_units,
                annual_cost_delta=annual_delta,
                margin_before=m_before,
                margin_after=m_after,
                breaks_target=breaks,
                already_below=already_below,
                shelf_price_needed=shelf_needed,
                reasons=reasons,
            )
        )

    findings.sort(key=lambda f: (-f.annual_cost_delta, -(f.change.delta_pct or 0)))
    return findings


def totals(findings: list[Finding]) -> dict:
    """The three numbers a shop owner actually asks for."""
    up = [f for f in findings if f.change.kind == "increase"]
    down = [f for f in findings if f.change.kind == "decrease"]
    return {
        "lines_reviewed": len(findings),
        "increases": len(up),
        "decreases": len(down),
        "new_lines": len([f for f in findings if f.change.kind == "new"]),
        "annual_exposure": round(sum(f.annual_cost_delta for f in up), 2),
        "annual_savings": round(sum(f.annual_cost_delta for f in down), 2),
        "net_annual": round(sum(f.annual_cost_delta for f in findings), 2),
        "margin_breaks": len([f for f in findings if f.breaks_target]),
        "newly_broken": len([f for f in findings if f.breaks_target and not f.already_below]),
        "already_below": len([f for f in findings if f.already_below]),
    }
