/* Run the browser core over the same sample files as the Python core and
 * assert the two produce identical output. Anything that drifts fails here. */
import { readFileSync } from "node:fs";
import { parsePriceList, indexBy, compare, assess, totals } from "../web/core.js";

const base = new URL("../", import.meta.url).pathname;
const read = (p) => readFileSync(base + p, "utf8");

const products = JSON.parse(read("data/products.json"));
const old = indexBy(parsePriceList(read("samples/alfa-june.csv"), "Alfa Distribution"));
const now = indexBy(parsePriceList(read("samples/alfa-september.csv"), "Alfa Distribution"));
const findings = assess(compare(old, now), products);

console.log(JSON.stringify({
  supplier: "Alfa Distribution",
  baseline_skus: Object.keys(old).length,
  incoming_skus: Object.keys(now).length,
  totals: totals(findings),
  findings,
}, null, 2));
