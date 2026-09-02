import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parse import parse_money, parse_pricelist, index
from core.diff import compare, margin, shelf_for_margin, assess, totals, net_shelf
from core.model import Product

fails = []
def eq(label, got, want, tol=1e-6):
    ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    print(("  ok  " if ok else "  FAIL") + f"  {label}: got {got!r} want {want!r}")
    if not ok: fails.append(label)

print("money parsing")
eq("euro thousands comma-decimal", parse_money("€ 1.234,56"), 1234.56)
eq("anglo thousands", parse_money("1,234.56"), 1234.56)
eq("plain comma decimal", parse_money("4,20"), 4.20)
eq("plain dot decimal", parse_money("4.20"), 4.20)
eq("suffix currency + nbsp", parse_money("2 199,00 EUR"), 2199.00)
eq("integer", parse_money("7"), 7.0)
eq("negative", parse_money("-3,50"), -3.5)
eq("blank is None", parse_money("  "), None)
eq("already numeric", parse_money(2.5), 2.5)

print("\nparsing a semicolon list with Albanian headers")
alb = "Kodi;Emri;Cmimi;Paketimi\n4471;Vaj luledielli 1L;2,10;12\n4472;Miell T400 1kg;0,58;10\n"
rows = parse_pricelist(alb, supplier="Alfa")
eq("row count", len(rows), 2)
eq("sku", rows[0].sku, "4471")
eq("cost", rows[0].unit_cost, 2.10)
eq("pack", rows[0].pack_size, 12)
eq("supplier carried", rows[1].supplier, "Alfa")

print("\nparsing tab-pasted english list")
eng = "SKU\tDescription\tNet Price (EUR)\n4471\tSunflower oil 1L\t2.28\n9001\tOlive oil 750ml\t6.40\n"
rows2 = parse_pricelist(eng)
eq("row count", len(rows2), 2)
eq("cost read", rows2[0].unit_cost, 2.28)

print("\nheaderless list falls back to position")
raw = "4471,Sunflower oil 1L,2.28\n4472,Flour T400,0.58\n"
eq("headerless rows", len(parse_pricelist(raw)), 2)

print("\nunreadable cost rows are dropped, not guessed")
junk = "Kodi;Emri;Cmimi\n4471;Vaj;2,10\n4472;Miell;\n4473;Sheqer;n/a\n"
eq("only the readable row survives", len(parse_pricelist(junk)), 1)

print("\nmargin maths")
eq("net of 18pc vat", net_shelf(2.95, 0.18), 2.5, 1e-9)
eq("margin at 2.10 cost", round(margin(2.95, 2.10, 0.18), 4), 0.16)
eq("shelf needed for 25pc", shelf_for_margin(2.10, 0.25, 0.18), 3.31)
eq("shelf rounds up not down", shelf_for_margin(1.00, 0.25, 0.18), 1.58)

print("\ndiff + assess")
old = index(parse_pricelist(alb, supplier="Alfa"))
new = index(parse_pricelist("Kodi;Emri;Cmimi;Paketimi\n4471;Vaj luledielli 1L;2,28;12\n4472;Miell T400 1kg;0,58;10\n9001;Vaj ulliri 750ml;6,40;6\n", supplier="Alfa"))
ch = compare(old, new)
kinds = {c.sku: c.kind for c in ch}
eq("4471 flagged as increase", kinds["4471"], "increase")
eq("4472 unchanged", kinds["4472"], "unchanged")
eq("9001 is new", kinds["9001"], "new")

prods = {
  "4471": Product("4471", shelf_price=2.95, vat_rate=0.18, monthly_units=340, target_margin=0.25),
  "4472": Product("4472", shelf_price=0.85, vat_rate=0.18, monthly_units=900, target_margin=0.25),
}
f = assess(ch, prods)
eq("unchanged lines are not findings", all(x.change.kind != "unchanged" for x in f), True)
top = f[0]
eq("top finding is the money one", top.change.sku, "4471")
eq("annual units", top.annual_units, 4080.0)
eq("annual cost delta", top.annual_cost_delta, 734.40)
eq("breaks target", top.breaks_target, True)
eq("shelf needed", top.shelf_price_needed, 3.59)

t = totals(f)
eq("increases counted", t["increases"], 1)
eq("annual exposure", t["annual_exposure"], 734.40)
eq("margin breaks", t["margin_breaks"], 1)

print("\nnoise below half a percent is ignored")
o2 = index(parse_pricelist("sku,name,price\nA,Thing,10.00\n"))
n2 = index(parse_pricelist("sku,name,price\nA,Thing,10.02\n"))
eq("0.2pc is noise", compare(o2, n2)[0].kind, "unchanged")
n3 = index(parse_pricelist("sku,name,price\nA,Thing,10.10\n"))
eq("1pc is a real increase", compare(o2, n3)[0].kind, "increase")


print("\nalready-below vs newly-broken is distinguished")
from core.model import Product as P
# same increase, two shops: one healthy before, one already under target
healthy = {"4471": P("4471", shelf_price=3.35, vat_rate=0.18, monthly_units=340, target_margin=0.25)}
struggling = {"4471": P("4471", shelf_price=2.95, vat_rate=0.18, monthly_units=340, target_margin=0.25)}
inc = [c for c in ch if c.sku == "4471"]
fh = assess(inc, healthy)[0]
fs = assess(inc, struggling)[0]
eq("healthy shop: broken by this list", (fh.breaks_target, fh.already_below), (True, False))
eq("struggling shop: was already under", (fs.breaks_target, fs.already_below), (True, True))
eq("reasons say so", "Already below" in " ".join(fs.reasons), True)
eq("healthy reasons say breaks", "breaks the" in " ".join(fh.reasons), True)

print("\ntotals split the two cases")
t2 = totals(assess(inc, struggling))
eq("counted as already below", t2["already_below"], 1)
eq("not counted as newly broken", t2["newly_broken"], 0)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}"))
sys.exit(1 if fails else 0)
