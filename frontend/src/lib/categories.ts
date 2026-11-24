/** Category colours, symbol assignments and the helpers the assignment editor uses. */
import type { ConfigSummary } from "../types";
import { leafNames } from "./hierarchy";

export const FALLBACK_COLOR = "#999";

export type Assignment =
  | { kind: "unassigned" }
  | { kind: "excluded" }
  | { kind: "assigned"; weights: Record<string, number> };

/** Colour of each leaf category that has one (parents have none). */
export function colorsByCategory(config: ConfigSummary | null): Record<string, string> {
  if (!config) return {};
  const leaves = new Set(leafNames(config));
  return Object.fromEntries(
    config.categories.flatMap((c) => (leaves.has(c.name) && c.color ? [[c.name, c.color]] : [])),
  );
}

/** Maps each category to the (sorted) symbols assigned to it; split symbols appear under every category they split into. */
export function symbolsByCategory(config: ConfigSummary | null): Record<string, string[]> {
  const result = new Map<string, string[]>();
  for (const [symbol, weights] of Object.entries(config?.assignments ?? {})) {
    for (const category of Object.keys(weights)) {
      result.set(category, [...(result.get(category) ?? []), symbol]);
    }
  }
  return Object.fromEntries([...result].map(([category, symbols]) => [category, symbols.sort()]));
}

/** How a symbol is treated: excluded (wins over any assignment), assigned (weights in config category order) or unassigned. */
export function assignmentOf(config: ConfigSummary | null, symbol: string): Assignment {
  if (!config) return { kind: "unassigned" };
  if (config.exclusions.includes(symbol)) return { kind: "excluded" };
  if (!Object.hasOwn(config.assignments, symbol)) return { kind: "unassigned" };

  const weights = config.assignments[symbol];
  const order = config.categories.map((c) => c.name);
  const rank = (name: string) => (order.includes(name) ? order.indexOf(name) : order.length);
  const entries = Object.entries(weights).sort(([a], [b]) => rank(a) - rank(b));
  return entries.length > 0
    ? { kind: "assigned", weights: Object.fromEntries(entries) }
    : { kind: "unassigned" };
}

/** E.g. "US Stocks", "US Stocks 60% · International 40%", "Excluded" or "Unassigned". */
export function assignmentLabel(a: Assignment): string {
  if (a.kind === "unassigned") return "Unassigned";
  if (a.kind === "excluded") return "Excluded";

  const entries = Object.entries(a.weights);
  if (entries.length === 1) return entries[0][0];

  const percents = entries.map(([, w]) => w * 100);
  // Tolerance, not Number.isInteger: 0.07 * 100 is 7.000000000000001.
  const wholeNumbers = percents.every((p) => Math.abs(p - Math.round(p)) < 1e-9);
  return entries
    .map(([name], i) => `${name} ${percents[i].toFixed(wholeNumbers ? 0 : 1)}%`)
    .join(" · ");
}

/** Splits 100% evenly (2 dp); the last name absorbs the rounding remainder so the sum is exactly 100. */
export function evenSplit(names: string[]): Record<string, number> {
  // Integer cents avoid floating-point drift.
  const baseCents = Math.floor(10000 / Math.max(names.length, 1));
  const lastCents = 10000 - baseCents * (names.length - 1);
  return Object.fromEntries(
    names.map((name, i) => [name, (i === names.length - 1 ? lastCents : baseCents) / 100]),
  );
}

/** Turns percents into fractions that sum to 1; all zeros when the total is not a positive number. */
export function toWeights(percents: Record<string, number>): Record<string, number> {
  const total = Object.values(percents).reduce((sum, v) => sum + v, 0);
  const valid = Number.isFinite(total) && total > 0;
  return Object.fromEntries(
    Object.entries(percents).map(([name, v]) => [name, valid ? v / total : 0]),
  );
}
