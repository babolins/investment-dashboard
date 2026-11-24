/** Converts the rebalance form's two inputs into whole-portfolio target weights, and back. */
import type { TargetAllocation } from "../types";

export interface TargetInputs {
  /** BND as a % of the whole portfolio. */
  bnd: number | null;
  /** VXUS as a % of the stock portion (everything that isn't BND). */
  vxusOfStocks: number | null;
}

export interface DerivedTargets {
  vti: number;
  vxus: number;
  bnd: number;
  /** null when the inputs are valid, otherwise a user-facing message for the first problem. */
  error: string | null;
}

function inRange(n: number | null): n is number {
  return n !== null && Number.isFinite(n) && n >= 0 && n <= 100;
}

/** Derives whole-portfolio VTI/VXUS/BND percentages; weights are never negative, even when `error` is set. */
export function deriveTargets({ bnd, vxusOfStocks }: TargetInputs): DerivedTargets {
  const hasBnd = bnd !== null && Number.isFinite(bnd);
  const hasVxus = vxusOfStocks !== null && Number.isFinite(vxusOfStocks);

  let error: string | null = null;
  if (!inRange(bnd)) error = "BND target must be between 0% and 100%.";
  else if (!inRange(vxusOfStocks)) error = "VXUS (of stocks) target must be between 0% and 100%.";

  const stockPct = hasBnd ? 100 - bnd : 0;
  const vxus = hasBnd && hasVxus ? (stockPct * vxusOfStocks) / 100 : 0;
  const vti = hasBnd && hasVxus ? stockPct - vxus : 0;

  // `|| 0` turns -0 into 0 so nothing renders as "-0.0%".
  return {
    vti: Math.max(0, vti) || 0,
    vxus: Math.max(0, vxus) || 0,
    bnd: hasBnd ? bnd : 0,
    error,
  };
}

/** Inverse of deriveTargets: recovers the form inputs from a whole-portfolio target. */
export function inputsFromTarget(target: TargetAllocation): { bnd: number; vxusOfStocks: number } {
  const stockPct = 100 - target.bnd;
  const share = stockPct > 0 ? (target.vxus / stockPct) * 100 : 0;
  // Round so the input shows 16.67 rather than 16.666666666666664.
  return { bnd: target.bnd, vxusOfStocks: Math.round(share * 100) / 100 };
}
