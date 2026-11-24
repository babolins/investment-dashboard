import { describe, expect, it } from "vitest";
import { defaultTargets, targetTotal, validateTargets } from "./targets";
import { config } from "../test/fixtures";

const RANGE_ERROR = "Each target must be between 0% and 100%.";

describe("defaultTargets", () => {
  it("reads each category's default target", () => {
    expect(defaultTargets(config.categories)).toEqual({
      "US Stocks": 48,
      International: 32,
      Bonds: 20,
    });
  });

  it("keeps missing targets as null", () => {
    const cats = [
      { name: "A", buy_symbol: "AAA", parent: null, target: null, color: "#111111" },
      { name: "B", buy_symbol: "BBB", parent: null, target: 100, color: "#222222" },
    ];
    expect(defaultTargets(cats)).toEqual({ A: null, B: 100 });
  });

  it("returns an empty record for no categories", () => {
    expect(defaultTargets([])).toEqual({});
  });
});

describe("targetTotal", () => {
  it("sums the targets", () => {
    expect(targetTotal({ a: 48, b: 32, c: 20 })).toBe(100);
  });

  it("counts null as 0", () => {
    expect(targetTotal({ a: null, b: 40 })).toBe(40);
  });

  it("counts NaN as 0", () => {
    expect(targetTotal({ a: NaN, b: 40 })).toBe(40);
  });

  it("is 0 when empty", () => {
    expect(targetTotal({})).toBe(0);
  });
});

describe("validateTargets", () => {
  it.each([
    [{ a: 48, b: 32, c: 20 }],
    [{ a: null, b: 100 }],
    [{ a: 100 }],
    [{ a: 33.33, b: 33.33, c: 33.34 }],
    [{ a: 50, b: 49.995 }],
    [{ a: 50, b: 49.99 }],
    [{ a: 50, b: 50.01 }],
  ])("accepts %j", (targets) => {
    expect(validateTargets(targets)).toBeNull();
  });

  it("rejects totals that are not 100", () => {
    expect(validateTargets({ a: 50, b: 45 })).toBe(
      "Targets must add up to 100% (currently 95.0%).",
    );
  });

  it("rejects a total just outside the tolerance", () => {
    expect(validateTargets({ a: 50, b: 50.0101 })).toMatch(/^Targets must add up to 100%/);
  });

  it("shows two decimals when the total is close to 100", () => {
    expect(validateTargets({ a: 50, b: 49.98 })).toBe(
      "Targets must add up to 100% (currently 99.98%).",
    );
  });

  it("treats all-empty targets as a total of 0", () => {
    expect(validateTargets({ a: null, b: null })).toBe(
      "Targets must add up to 100% (currently 0.0%).",
    );
  });

  it("rejects no categories", () => {
    expect(validateTargets({})).toBe("Targets must add up to 100% (currently 0.0%).");
  });

  it.each([
    [{ a: -1, b: 101 }],
    [{ a: 101, b: -1 }],
    [{ a: NaN, b: 100 }],
    [{ a: Infinity, b: 0 }],
  ])("rejects out-of-range values %j before checking the sum", (targets) => {
    expect(validateTargets(targets)).toBe(RANGE_ERROR);
  });
});
