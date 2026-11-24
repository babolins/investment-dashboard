/**
 * Client-side checks for category names, buy symbols and default targets. They mirror the
 * server's rules for quick feedback; the server stays authoritative. Each returns a message or null.
 */
import type { ConfigSummary } from "../types";

const RESERVED = ["excluded", "unassigned"];

export function validateName(name: string): string | null {
  if (!name) return "Enter a category name.";
  if (name.length > 40) return "Name must be at most 40 characters.";
  if (name.includes("/")) return 'Name must not contain "/".';
  if (RESERVED.includes(name.toLowerCase())) return `"${name}" is a reserved name.`;
  return null;
}

/** The buy symbol is optional: blank is fine. */
export function validateSymbol(symbol: string): string | null {
  return symbol === "" || /^[A-Z0-9.-]{1,10}$/.test(symbol)
    ? null
    : "Buy symbol must be 1-10 letters, digits, dots or dashes.";
}

export function validateTarget(target: number | null): string | null {
  return target === null || (target >= 0 && target <= 100)
    ? null
    : "Default target must be between 0 and 100.";
}

/** Names are unique ignoring case. */
export function duplicateName(config: ConfigSummary, name: string): string | null {
  const lower = name.toLowerCase();
  const taken = config.categories.some((c) => c.name.toLowerCase() === lower);
  return taken ? `A category named "${name}" already exists.` : null;
}

/** An empty number input binds to null (or ""); anything else is coerced to a number. */
export const parseTarget = (value: number | string | null): number | null =>
  value === null || value === "" ? null : Number(value);
