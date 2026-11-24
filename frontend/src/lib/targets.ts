/** Helpers for the rebalance form's per-category target percentages. */
import type { Category } from "../types";

type Targets = Record<string, number | null>;

/** Each category's default target (null when unset), used to pre-fill the form. */
export function defaultTargets(categories: Category[]): Targets {
  return Object.fromEntries(categories.map((c) => [c.name, c.target]));
}

/** Sum of the targets; empty (null) and NaN entries count as 0. */
export function targetTotal(targets: Targets): number {
  return Object.values(targets).reduce<number>(
    (sum, v) => sum + (typeof v === "number" && Number.isFinite(v) ? v : 0),
    0,
  );
}

/** null when the targets are valid, otherwise a user-facing message for the first problem. */
export function validateTargets(targets: Targets): string | null {
  const outOfRange = Object.values(targets).some(
    (v) => v !== null && (!Number.isFinite(v) || v < 0 || v > 100),
  );
  if (outOfRange) return "Each target must be between 0% and 100%.";

  const total = targetTotal(targets);
  // Same ±0.01 tolerance as the backend; the epsilon absorbs float noise (50 + 50.01).
  if (Math.abs(total - 100) <= 0.01 + 1e-9) return null;

  // Two decimals near 100 so a failing total never reads "100.0%".
  const shown = total.toFixed(Math.abs(total - 100) < 0.05 ? 2 : 1);
  return `Targets must add up to 100% (currently ${shown}%).`;
}
