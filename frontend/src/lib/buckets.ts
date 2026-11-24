/** Bucket colours and the config-derived symbol/label lookups used by the UI. */
import type { ConfigSummary } from "../types";

const BUCKET_COLORS: Record<string, string> = {
  VTI: "#1B3A6B",
  VXUS: "#4AACE8",
  BND: "#6B7A23",
};

const FALLBACK_COLOR = "#999";

export function bucketColor(bucket: string): string {
  return Object.hasOwn(BUCKET_COLORS, bucket) ? BUCKET_COLORS[bucket] : FALLBACK_COLOR;
}

/** Maps each bucket to the (sorted) symbols that feed it; fractional symbols appear under every bucket they split into. */
export function symbolsByBucket(config: ConfigSummary | null): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  if (!config) return result;
  const add = (bucket: string, symbol: string) => (result[bucket] ??= []).push(symbol);

  for (const [symbol, bucket] of Object.entries(config.direct_mappings)) add(bucket, symbol);
  for (const [symbol, weights] of Object.entries(config.fractional_mappings)) {
    for (const bucket of Object.keys(weights)) add(bucket, symbol);
  }
  for (const symbols of Object.values(result)) symbols.sort();
  return result;
}

/** Maps each symbol to its display label: a bucket, "A/B" for fractional symbols, or "Excl.". */
export function bucketLabelBySymbol(config: ConfigSummary | null): Record<string, string> {
  const result: Record<string, string> = {};
  if (!config) return result;

  for (const [symbol, bucket] of Object.entries(config.direct_mappings)) result[symbol] = bucket;
  for (const [symbol, weights] of Object.entries(config.fractional_mappings)) {
    result[symbol] = Object.keys(weights).sort().join("/");
  }
  for (const symbol of config.exclusions) result[symbol] = "Excl.";
  return result;
}

/** CSS classes for a bucket badge, e.g. "VTI/VXUS" -> "bucket-badge bucket-badge--vti-vxus". */
export function bucketBadgeClass(label: string | undefined): string {
  const modifier = (label ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return modifier ? `bucket-badge bucket-badge--${modifier}` : "bucket-badge";
}
