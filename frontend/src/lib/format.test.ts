import { describe, expect, it } from "vitest";
import { formatGain, formatPct, usd } from "./format";

describe("usd", () => {
  it("formats as en-US currency", () => {
    expect(usd.format(1234.5)).toBe("$1,234.50");
  });
});

describe("formatPct", () => {
  it("defaults to one decimal digit", () => {
    expect(formatPct(12.345)).toBe("12.3%");
  });

  it.each([
    [12.345, 0, "12%"],
    [12.345, 2, "12.35%"],
    [0, 1, "0.0%"],
  ])("formats %d with %d digits as %s", (n, digits, expected) => {
    expect(formatPct(n, digits)).toBe(expected);
  });
});

describe("formatGain", () => {
  it.each([
    [5, "+$5.00"],
    [-5, "-$5.00"],
    [1234.5, "+$1,234.50"],
    [0, "+$0.00"],
  ])("formats %d as %s", (n, expected) => {
    expect(formatGain(n)).toBe(expected);
  });

  it("shows an em dash for null", () => {
    expect(formatGain(null)).toBe("—");
  });

  it("treats negative zero as zero", () => {
    expect(formatGain(-0)).toBe("+$0.00");
  });
});
