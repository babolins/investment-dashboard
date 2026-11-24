/** Display formatters shared by the table, chart and buy guidance. */

export const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** Formats a percentage value (12.345 -> "12.3%"). */
export function formatPct(n: number, digits = 1): string {
  return `${n.toFixed(digits)}%`;
}

/** Formats a gain/loss in dollars with an explicit "+" for gains; null (unknown) shows an em dash. */
export function formatGain(n: number | null): string {
  if (n === null) return "—";
  // `n || 0` turns -0 into 0 so it doesn't render as "+-$0.00".
  const value = n || 0;
  return (value >= 0 ? "+" : "") + usd.format(value);
}
