"""Data shapes shared by every part of Ratchet.

Deliberately plain: dataclasses and stdlib only, so the whole decision layer
can be tested without a model, a network, or an SDK.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

Kind = Literal["increase", "decrease", "new", "withdrawn", "unchanged"]


@dataclass(frozen=True)
class Line:
    """One row of a supplier price list."""

    sku: str
    name: str
    unit_cost: float  # what we pay per unit, excluding VAT
    currency: str = "EUR"
    pack_size: int = 1  # units per case; unit_cost stays per unit
    supplier: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Product:
    """What we know about selling the thing, independent of any price list."""

    sku: str
    shelf_price: float  # what the customer pays, including VAT
    vat_rate: float = 0.18  # Kosovo standard rate; overridable per product
    monthly_units: float = 0.0
    target_margin: float = 0.25  # gross margin we intend to hold, ex-VAT


@dataclass(frozen=True)
class Change:
    """A single line's movement between two price lists."""

    sku: str
    name: str
    kind: Kind
    old_cost: Optional[float]
    new_cost: Optional[float]
    supplier: str = ""
    currency: str = "EUR"

    @property
    def delta_abs(self) -> Optional[float]:
        if self.old_cost is None or self.new_cost is None:
            return None
        return round(self.new_cost - self.old_cost, 6)

    @property
    def delta_pct(self) -> Optional[float]:
        if not self.old_cost or self.new_cost is None:
            return None
        return round((self.new_cost - self.old_cost) / self.old_cost, 6)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["delta_abs"] = self.delta_abs
        d["delta_pct"] = self.delta_pct
        return d


@dataclass(frozen=True)
class Finding:
    """A change, priced against how much of it we actually buy."""

    change: Change
    annual_units: float
    annual_cost_delta: float  # positive means it costs us more per year
    margin_before: Optional[float]
    margin_after: Optional[float]
    breaks_target: bool
    # True when the line was already below its target before this list arrived.
    # Without this the buyer cannot tell a fresh problem from an old one, and
    # would take the wrong complaint to the supplier.
    already_below: bool
    shelf_price_needed: Optional[float]
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            **self.change.as_dict(),
            "annual_units": self.annual_units,
            "annual_cost_delta": self.annual_cost_delta,
            "margin_before": self.margin_before,
            "margin_after": self.margin_after,
            "breaks_target": self.breaks_target,
            "already_below": self.already_below,
            "newly_broken": self.breaks_target and not self.already_below,
            "shelf_price_needed": self.shelf_price_needed,
            "reasons": list(self.reasons),
        }
