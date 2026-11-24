import { describe, expect, it } from "vitest";
import {
  assignmentLabel,
  assignmentOf,
  colorsByCategory,
  evenSplit,
  FALLBACK_COLOR,
  symbolsByCategory,
  toWeights,
} from "./categories";
import { colors, config } from "../test/fixtures";
import type { ConfigSummary } from "../types";

describe("FALLBACK_COLOR", () => {
  it("is a neutral grey", () => {
    expect(FALLBACK_COLOR).toBe("#999");
  });
});

describe("colorsByCategory", () => {
  it("maps each category name to its colour", () => {
    expect(colorsByCategory(config)).toEqual(colors);
  });

  it("returns an empty map without a config", () => {
    expect(colorsByCategory(null)).toEqual({});
  });

  it("handles a config with no categories", () => {
    expect(colorsByCategory({ categories: [], assignments: {}, exclusions: [] })).toEqual({});
  });

  it("copes with a category named like an Object property", () => {
    const c: ConfigSummary = {
      categories: [{ name: "__proto__", buy_symbol: "X", target: null, color: "#111111" }],
      assignments: {},
      exclusions: [],
    };
    const map = colorsByCategory(c);
    expect(Object.hasOwn(map, "__proto__")).toBe(true);
    expect(map["__proto__"]).toBe("#111111");
  });
});

describe("symbolsByCategory", () => {
  it("lists sorted symbols under every category they are assigned to", () => {
    expect(symbolsByCategory(config)).toEqual({
      "US Stocks": ["FZROX", "ITOT", "VTI"],
      International: ["FZROX", "VXUS"],
      Bonds: ["BND"],
    });
  });

  it("omits categories without symbols", () => {
    const c: ConfigSummary = {
      ...config,
      assignments: { VTI: { "US Stocks": 1 } },
    };
    expect(symbolsByCategory(c)).toEqual({ "US Stocks": ["VTI"] });
  });

  it("does not list excluded symbols", () => {
    expect(Object.values(symbolsByCategory(config)).flat()).not.toContain("SPAXX");
  });

  it("returns an empty map without a config", () => {
    expect(symbolsByCategory(null)).toEqual({});
  });
});

describe("assignmentOf", () => {
  it("returns a direct assignment", () => {
    expect(assignmentOf(config, "VTI")).toEqual({
      kind: "assigned",
      weights: { "US Stocks": 1 },
    });
  });

  it("returns fractional weights", () => {
    expect(assignmentOf(config, "FZROX")).toEqual({
      kind: "assigned",
      weights: { "US Stocks": 0.7, International: 0.3 },
    });
  });

  it("orders weights by config category order", () => {
    const c: ConfigSummary = {
      ...config,
      assignments: { FZROX: { International: 0.3, "US Stocks": 0.7 } },
    };
    const a = assignmentOf(c, "FZROX");
    expect(a.kind).toBe("assigned");
    if (a.kind === "assigned") {
      expect(Object.keys(a.weights)).toEqual(["US Stocks", "International"]);
    }
  });

  it("returns excluded for excluded symbols", () => {
    expect(assignmentOf(config, "SPAXX")).toEqual({ kind: "excluded" });
  });

  it("lets exclusion win over an assignment", () => {
    const c: ConfigSummary = { ...config, exclusions: ["VTI"] };
    expect(assignmentOf(c, "VTI")).toEqual({ kind: "excluded" });
  });

  it("returns unassigned for unknown symbols", () => {
    expect(assignmentOf(config, "MYSTERY")).toEqual({ kind: "unassigned" });
  });

  it("does not match inherited Object properties", () => {
    expect(assignmentOf(config, "constructor")).toEqual({ kind: "unassigned" });
  });

  it("returns unassigned without a config", () => {
    expect(assignmentOf(null, "VTI")).toEqual({ kind: "unassigned" });
  });
});

describe("assignmentLabel", () => {
  it("labels unassigned and excluded", () => {
    expect(assignmentLabel({ kind: "unassigned" })).toBe("Unassigned");
    expect(assignmentLabel({ kind: "excluded" })).toBe("Excluded");
  });

  it("shows just the name for a single category", () => {
    expect(assignmentLabel({ kind: "assigned", weights: { "US Stocks": 1 } })).toBe("US Stocks");
  });

  it.each([
    [{ A: 0.6, B: 0.4 }, "A 60% · B 40%"],
    [{ A: 0.7, B: 0.3 }, "A 70% · B 30%"],
    [{ A: 0.07, B: 0.29, C: 0.64 }, "A 7% · B 29% · C 64%"],
    [{ A: 0.7, B: 0.25, C: 0.05 }, "A 70% · B 25% · C 5%"],
    [{ A: 1 / 3, B: 1 / 3, C: 1 / 3 }, "A 33.3% · B 33.3% · C 33.3%"],
    [{ A: 0.625, B: 0.375 }, "A 62.5% · B 37.5%"],
  ])("formats %j as %s", (weights, label) => {
    expect(assignmentLabel({ kind: "assigned", weights })).toBe(label);
  });

  it("follows the order of the weights", () => {
    expect(assignmentLabel({ kind: "assigned", weights: { B: 0.4, A: 0.6 } })).toBe(
      "B 40% · A 60%",
    );
  });
});

describe("evenSplit", () => {
  const cents = (r: Record<string, number>) =>
    Object.values(r).reduce((sum, v) => sum + Math.round(v * 100), 0);

  it("returns an empty split for no names", () => {
    expect(evenSplit([])).toEqual({});
  });

  it("gives a single name 100", () => {
    expect(evenSplit(["A"])).toEqual({ A: 100 });
  });

  it("splits evenly when it divides cleanly", () => {
    expect(evenSplit(["A", "B"])).toEqual({ A: 50, B: 50 });
    expect(evenSplit(["A", "B", "C", "D"])).toEqual({ A: 25, B: 25, C: 25, D: 25 });
  });

  it("lets the last name absorb the remainder", () => {
    const r = evenSplit(["A", "B", "C"]);
    expect(r.A).toBeCloseTo(33.33, 10);
    expect(r.B).toBeCloseTo(33.33, 10);
    expect(r.C).toBeCloseTo(33.34, 10);
  });

  it.each([1, 2, 3, 4, 5, 6, 7, 8])("sums to exactly 100 cents for %d names", (n) => {
    const names = Array.from({ length: n }, (_, i) => `C${i}`);
    const r = evenSplit(names);
    expect(Object.keys(r)).toEqual(names);
    expect(cents(r)).toBe(10000);
  });
});

describe("toWeights", () => {
  it("normalises percents to fractions", () => {
    const w = toWeights({ a: 60, b: 40 });
    expect(w.a).toBeCloseTo(0.6, 12);
    expect(w.b).toBeCloseTo(0.4, 12);
  });

  it("normalises when the percents do not total 100", () => {
    const w = toWeights({ a: 33.33, b: 33.33, c: 33.33 });
    for (const v of Object.values(w)) expect(v).toBeCloseTo(1 / 3, 12);
    expect(Object.values(w).reduce((s, v) => s + v, 0)).toBeCloseTo(1, 12);
  });

  it("keeps zero entries as zero", () => {
    expect(toWeights({ a: 100, b: 0 })).toEqual({ a: 1, b: 0 });
  });

  it("returns all zeros when the total is zero", () => {
    expect(toWeights({ a: 0, b: 0 })).toEqual({ a: 0, b: 0 });
  });

  it("returns all zeros when the total is not finite", () => {
    expect(toWeights({ a: Infinity, b: 1 })).toEqual({ a: 0, b: 0 });
  });

  it("returns an empty object for no input", () => {
    expect(toWeights({})).toEqual({});
  });
});
