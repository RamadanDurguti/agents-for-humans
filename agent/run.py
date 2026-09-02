"""Command line entry point.

    python -m agent.run review samples/alfa-june.csv samples/alfa-september.csv
    python -m agent.run ask "what did the coffee do and should I push back?"

`review` runs the deterministic pipeline only — no model, no network, no key.
`ask` hands the same tools to a Strands agent and lets it decide what to call.
Both read the same data directory, so the agent and the report can never
disagree about the numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.report import draft_note, load_products, review  # noqa: E402

DATA = Path(os.environ.get("RATCHET_DATA", "data"))


def _fmt(n: float) -> str:
    return f"{n:,.2f}"


def cmd_review(args: argparse.Namespace) -> int:
    products = load_products(DATA / "products.json")
    baseline = Path(args.baseline).read_text(encoding="utf-8")
    incoming = Path(args.incoming).read_text(encoding="utf-8")
    rep = review(baseline, incoming, products, supplier=args.supplier)
    t = rep["totals"]

    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0

    print(f"\n{args.supplier or 'Supplier'} — {rep['incoming_skus']} lines on the new list\n")
    print(f"  Annual exposure   {_fmt(t['annual_exposure']):>12} EUR   ({t['increases']} lines up)")
    print(f"  Recovered         {_fmt(abs(t['annual_savings'])):>12} EUR   ({t['decreases']} down)")
    print(f"  Net effect        {_fmt(t['net_annual']):>12} EUR   per year at current volumes")
    print(f"  Margin broken     {t['newly_broken']:>12}         ({t['already_below']} were already under)\n")

    head = f"  {'SKU':<7}{'ITEM':<26}{'WAS':>7}{'NOW':>7}{'MOVE':>8}{'EUR/YR':>11}  MARGIN"
    print(head)
    print("  " + "-" * (len(head) + 6))
    for f in rep["findings"]:
        old = f"{f['old_cost']:.2f}" if f["old_cost"] is not None else "-"
        pct = f"{f['delta_pct'] * 100:+.1f}%" if f["delta_pct"] is not None else "-"
        eur = f"{f['annual_cost_delta']:+,.2f}" if f["annual_cost_delta"] else "-"
        if f["newly_broken"]:
            flag = "BROKEN"
        elif f["already_below"]:
            flag = "was already under"
        elif f["margin_after"] is None:
            flag = "no shelf data"
        else:
            flag = f"{f['margin_after'] * 100:.1f}%"
        print(f"  {f['sku']:<7}{f['name'][:25]:<26}{old:>7}{f['new_cost']:>7.2f}{pct:>8}{eur:>11}  {flag}")

    print("\n" + "-" * 72)
    print(draft_note(rep))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    # Imported lazily so `review` keeps working with no SDK installed.
    from agent.ratchet import build_agent

    agent = build_agent()
    result = agent(args.question)
    print(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ratchet", description="Catch supplier price drift before it eats the year.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("review", help="Deterministic review of one incoming price list.")
    r.add_argument("baseline", help="CSV of what you are paying today")
    r.add_argument("incoming", help="CSV the supplier just sent")
    r.add_argument("--supplier", default="", help="Supplier name for the report")
    r.add_argument("--json", action="store_true", help="Emit the full report as JSON")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("ask", help="Put the question to the agent and let it pick tools.")
    a.add_argument("question")
    a.set_defaults(func=cmd_ask)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
