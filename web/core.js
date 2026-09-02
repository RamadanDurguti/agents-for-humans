/* Browser mirror of core/ — parsing, diffing and margin maths.
 *
 * The Python core is canonical: it is what the agent calls and what ships.
 * This exists so the live page runs the real pipeline in front of you with no
 * server, no key and no install. Both are held to the same test vectors
 * (tests/vectors.json), and web/parity.html runs them against this file, so a
 * drift between the two shows up as a red test rather than a wrong number on
 * screen. */

export const NOISE_PCT = 0.005;

const SKU_KEYS = ["sku","code","codigo","art","artnr","art_no","artikel","item","itemcode","item_code","product_code","ref","reference","barcode","ean","kodi","kod","artikulli","artikull"];
const NAME_KEYS = ["name","description","desc","product","article","designation","bezeichnung","emri","emertimi","pershkrimi","përshkrimi","produkti"];
const COST_KEYS = ["cost","price","unitprice","unit_price","unit cost","netprice","net_price","net","buy","buying_price","purchase","eur","preis","prix","cmimi","çmimi","cmimi_neto","furnizim"];
const PACK_KEYS = ["pack","packsize","pack_size","case","units","qty","sasia","paketimi"];

const norm = (h) => h.trim().toLowerCase().replace(/[^a-z0-9ëç_ ]/g, "").trim();

/* Read a price the way a human would. The LAST of . or , is the decimal
   point — true for both European and Anglo conventions. */
export function parseMoney(raw) {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") return raw;
  let s = String(raw).replace(/ /g, " ").replace(/[^\d,.\-]/g, "").trim();
  if (!s) return null;
  const neg = s.startsWith("-");
  s = s.replace(/^-/, "");
  const d = s.lastIndexOf("."), c = s.lastIndexOf(",");
  let v;
  if (d === -1 && c === -1) v = parseFloat(s);
  else if (c > d) v = parseFloat(s.replace(/\./g, "").replace(",", "."));
  else v = parseFloat(s.replace(/,/g, ""));
  if (Number.isNaN(v)) return null;
  return neg ? -v : v;
}

function splitRows(text, delim) {
  // Minimal CSV reader: quoted fields with doubled quotes, nothing exotic.
  const rows = []; let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; }
      else field += ch;
    } else if (ch === '"') q = true;
    else if (ch === delim) { row.push(field); field = ""; }
    else if (ch === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (ch !== "\r") field += ch;
  }
  row.push(field); rows.push(row);
  return rows.filter((r) => r.some((c) => c.trim()));
}

const pick = (headers, keys) => {
  const n = headers.map(norm);
  let i = n.findIndex((h) => keys.includes(h));
  if (i !== -1) return i;
  i = n.findIndex((h) => keys.some((k) => h.includes(k)));
  return i === -1 ? null : i;
};

function sniff(text) {
  const head = text.split("\n").slice(0, 5).join("\n");
  let best = ",", n = 0;
  for (const d of [";", "\t", ",", "|"]) {
    const c = head.split(d).length - 1;
    if (c > n) { n = c; best = d; }
  }
  return n ? best : ",";
}

export function parsePriceList(text, supplier = "") {
  text = text.replace(/\r\n/g, "\n").replace(/^\n+|\n+$/g, "");
  if (!text) return [];
  let rows = splitRows(text, sniff(text));
  if (!rows.length) return [];
  const headers = rows[0];
  let iSku = pick(headers, SKU_KEYS), iName = pick(headers, NAME_KEYS),
      iCost = pick(headers, COST_KEYS), iPack = pick(headers, PACK_KEYS);
  let body = rows.slice(1);
  if (iCost === null) { iSku = 0; iName = 1; iCost = 2; iPack = null; body = rows; }

  const out = [];
  for (const r of body) {
    if (iCost >= r.length) continue;
    const cost = parseMoney(r[iCost]);
    if (cost === null) continue;
    const sku = iSku !== null && iSku < r.length ? r[iSku].trim() : "";
    const name = iName !== null && iName < r.length ? r[iName].trim() : "";
    if (!sku && !name) continue;
    let pack = 1;
    if (iPack !== null && iPack < r.length) {
      const p = parseMoney(r[iPack]);
      if (p && p >= 1) pack = Math.trunc(p);
    }
    out.push({ sku: sku || name.toLowerCase().replace(/ /g, "-"), name: name || sku,
               unit_cost: cost, pack_size: pack, supplier, currency: "EUR" });
  }
  return out;
}

export const indexBy = (lines) => Object.fromEntries(lines.map((l) => [l.sku, l]));

export function compare(oldIx, newIx) {
  const skus = [...new Set([...Object.keys(oldIx), ...Object.keys(newIx)])].sort();
  return skus.map((sku) => {
    const a = oldIx[sku], b = newIx[sku];
    const mk = (kind, oc, nc, nm, sup) => {
      const delta_abs = oc === null || nc === null ? null : +(nc - oc).toFixed(6);
      const delta_pct = !oc || nc === null ? null : +((nc - oc) / oc).toFixed(6);
      return { sku, name: nm, kind, old_cost: oc, new_cost: nc, supplier: sup || "", currency: "EUR", delta_abs, delta_pct };
    };
    if (a && b) {
      let kind;
      if (Math.abs(b.unit_cost - a.unit_cost) < 1e-9) kind = "unchanged";
      else {
        const pct = a.unit_cost ? (b.unit_cost - a.unit_cost) / a.unit_cost : 0;
        kind = Math.abs(pct) < NOISE_PCT ? "unchanged" : (b.unit_cost > a.unit_cost ? "increase" : "decrease");
      }
      return mk(kind, a.unit_cost, b.unit_cost, b.name || a.name, b.supplier || a.supplier);
    }
    if (b) return mk("new", null, b.unit_cost, b.name, b.supplier);
    return mk("withdrawn", a.unit_cost, null, a.name, a.supplier);
  });
}

export const netShelf = (shelf, vat) => shelf / (1 + vat);
export const margin = (shelf, cost, vat) => {
  const net = netShelf(shelf, vat);
  return net <= 0 ? 0 : (net - cost) / net;
};
const ceilCents = (x) => {
  const c = x * 100, w = Math.trunc(c);
  return +(((c - w > 1e-9 ? w + 1 : w)) / 100).toFixed(2);
};
export function shelfForMargin(cost, target, vat) {
  if (target >= 1) throw new Error("target margin must be below 1.0");
  return ceilCents((cost / (1 - target)) * (1 + vat));
}

export function assess(changes, products) {
  const out = [];
  for (const ch of changes) {
    if (ch.kind === "unchanged" || ch.kind === "withdrawn") continue;
    const p = products[ch.sku];
    const annual_units = p ? p.monthly_units * 12 : 0;
    const annual_cost_delta = +(((ch.delta_abs || 0) * annual_units).toFixed(2));

    let margin_before = null, margin_after = null, shelf_price_needed = null;
    let breaks_target = false, already_below = false;
    const reasons = [];
    const pct = (ch.delta_pct || 0) * 100;

    if (ch.kind === "increase") reasons.push(`Unit cost rose from ${ch.old_cost.toFixed(4)} to ${ch.new_cost.toFixed(4)} (${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%).`);
    else if (ch.kind === "decrease") reasons.push(`Unit cost fell from ${ch.old_cost.toFixed(4)} to ${ch.new_cost.toFixed(4)} (${pct.toFixed(1)}%).`);
    else reasons.push(`New line on this list at ${ch.new_cost.toFixed(4)}.`);

    if (p && p.shelf_price > 0 && ch.new_cost !== null) {
      margin_after = +margin(p.shelf_price, ch.new_cost, p.vat_rate).toFixed(6);
      if (ch.old_cost !== null) margin_before = +margin(p.shelf_price, ch.old_cost, p.vat_rate).toFixed(6);
      breaks_target = margin_after < p.target_margin;
      already_below = margin_before !== null && margin_before < p.target_margin;
      if (breaks_target) {
        shelf_price_needed = shelfForMargin(ch.new_cost, p.target_margin, p.vat_rate);
        reasons.push(already_below
          ? `Already below the ${(p.target_margin * 100).toFixed(0)}% target before this list (${(margin_before * 100).toFixed(1)}%), and this change takes it to ${(margin_after * 100).toFixed(1)}%. Shelf price would need ${shelf_price_needed.toFixed(2)} to reach target.`
          : `This change breaks the ${(p.target_margin * 100).toFixed(0)}% target: margin falls from ${(margin_before * 100).toFixed(1)}% to ${(margin_after * 100).toFixed(1)}%. Shelf price would need ${shelf_price_needed.toFixed(2)} to restore it.`);
      }
      if (margin_after < 0) reasons.push("This line is now sold below cost.");
    }

    if (annual_units && ch.kind === "increase")
      reasons.push(`At ${annual_units.toLocaleString("en-US")} units a year that is ${annual_cost_delta.toLocaleString("en-US", { minimumFractionDigits: 2 })} ${ch.currency} of extra cost.`);
    else if (!annual_units && ch.kind !== "new")
      reasons.push("No sales volume on file, so the annual impact is unknown.");

    out.push({ ...ch, annual_units, annual_cost_delta, margin_before, margin_after,
               breaks_target, already_below, newly_broken: breaks_target && !already_below,
               shelf_price_needed, reasons });
  }
  out.sort((a, b) => (b.annual_cost_delta - a.annual_cost_delta) || ((b.delta_pct || 0) - (a.delta_pct || 0)));
  return out;
}

export function totals(f) {
  const up = f.filter((x) => x.kind === "increase"), down = f.filter((x) => x.kind === "decrease");
  const sum = (a) => +a.reduce((s, x) => s + x.annual_cost_delta, 0).toFixed(2);
  return {
    lines_reviewed: f.length, increases: up.length, decreases: down.length,
    new_lines: f.filter((x) => x.kind === "new").length,
    annual_exposure: sum(up), annual_savings: sum(down), net_annual: sum(f),
    margin_breaks: f.filter((x) => x.breaks_target).length,
    newly_broken: f.filter((x) => x.newly_broken).length,
    already_below: f.filter((x) => x.already_below).length,
  };
}
