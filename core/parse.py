"""Turn whatever the supplier actually sent into rows we can compare.

Price lists arrive as CSV exported from Excel, tab-pasted text, or a table
copied out of a PDF. Headers are in whatever language the supplier uses and
the decimal separator is a comma about half the time. None of that is
interesting, but all of it has to work before anything else can.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Iterable, Optional

from .model import Line

# Header aliases. Albanian included because that is what the lists in this
# market actually say, and a tool that cannot read "Cmimi" is a tool nobody here
# can use.
SKU_KEYS = {
    "sku", "code", "codigo", "art", "artnr", "art_no", "artikel", "item",
    "itemcode", "item_code", "product_code", "ref", "reference", "barcode",
    "ean", "kodi", "kod", "artikulli", "artikull",
}
NAME_KEYS = {
    "name", "description", "desc", "product", "article", "designation",
    "bezeichnung", "emri", "emertimi", "pershkrimi", "përshkrimi", "produkti",
}
COST_KEYS = {
    "cost", "price", "unitprice", "unit_price", "unit cost", "netprice",
    "net_price", "net", "buy", "buying_price", "purchase", "eur", "preis",
    "prix", "cmimi", "çmimi", "cmimi_neto", "furnizim",
}
PACK_KEYS = {"pack", "packsize", "pack_size", "case", "units", "qty", "sasia", "paketimi"}

_MONEY_CHARS = re.compile(r"[^\d,.\-]")
_NUM = re.compile(r"-?\d+(?:[.,]\d+)*")


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9ëç_ ]", "", header.strip().lower()).strip()


def parse_money(raw: str | float | int | None) -> Optional[float]:
    """Read a price the way a human would, not the way a parser wants.

    Handles "€ 1.234,56", "1,234.56", "4,20", "4.20", "2 199,00 EUR".
    The rule that decides between the two conventions is the *last* separator:
    whichever of . or , appears last is the decimal point. That is true for
    every European and Anglo format we have seen, and it degrades sanely when
    only one separator is present.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = _MONEY_CHARS.sub("", str(raw).replace(" ", " ")).strip()
    if not s:
        return None
    neg = s.startswith("-")
    s = s.lstrip("-")
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot == -1 and last_comma == -1:
        val = float(s)
    elif last_comma > last_dot:
        val = float(s.replace(".", "").replace(",", "."))
    else:
        val = float(s.replace(",", ""))
    return -val if neg else val


def _pick(headers: list[str], keys: set[str]) -> Optional[int]:
    normed = [_norm(h) for h in headers]
    for i, h in enumerate(normed):
        if h in keys:
            return i
    # second pass: substring match, so "net price (eur)" still lands
    for i, h in enumerate(normed):
        if any(k in h for k in keys):
            return i
    return None


def _sniff(text: str) -> str:
    head = "\n".join(text.splitlines()[:5])
    counts = {d: head.count(d) for d in [";", "\t", ",", "|"]}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def parse_pricelist(text: str, supplier: str = "") -> list[Line]:
    """Parse a delimited price list into Lines, skipping anything unusable.

    Rows without a readable cost are dropped rather than guessed at. A price
    list that silently invents numbers is worse than one that admits a gap.
    """
    text = text.replace("\r\n", "\n").strip("\n")
    if not text:
        return []
    delim = _sniff(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []

    headers = rows[0]
    i_sku = _pick(headers, SKU_KEYS)
    i_name = _pick(headers, NAME_KEYS)
    i_cost = _pick(headers, COST_KEYS)
    i_pack = _pick(headers, PACK_KEYS)
    body = rows[1:]

    # No recognisable header row: fall back to position, which is the shape
    # every hand-typed list ends up in anyway.
    if i_cost is None:
        i_sku, i_name, i_cost, i_pack = 0, 1, 2, None
        body = rows

    out: list[Line] = []
    for r in body:
        if i_cost >= len(r):
            continue
        cost = parse_money(r[i_cost])
        if cost is None:
            continue
        sku = (r[i_sku].strip() if i_sku is not None and i_sku < len(r) else "")
        name = (r[i_name].strip() if i_name is not None and i_name < len(r) else "")
        if not sku and not name:
            continue
        pack = 1
        if i_pack is not None and i_pack < len(r):
            p = parse_money(r[i_pack])
            if p and p >= 1:
                pack = int(p)
        out.append(
            Line(
                sku=sku or name.lower().replace(" ", "-"),
                name=name or sku,
                unit_cost=round(cost, 6),
                pack_size=pack,
                supplier=supplier,
            )
        )
    return out


def index(lines: Iterable[Line]) -> dict[str, Line]:
    return {ln.sku: ln for ln in lines}
