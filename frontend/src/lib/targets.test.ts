import { describe, expect, it } from "vitest";
import { deriveTargets, inputsFromTarget } from "./targets";

const BND_ERROR = "BND target must be between 0% and 100%.";
const VXUS_ERROR = "VXUS (of stocks) target must be between 0% and 100%.";

describe("deriveTargets", () => {
  it("splits the non-bond share between VTI and VXUS", () => {
    expect(deriveTargets({ bnd: 20, vxusOfStocks: 40 })).toEqual({
      vti: 48,
      vxus: 32,
      bnd: 20,
      error: null,
    });
  });

  it.each([
    [0, 0],
    [100, 100],
    [20, 30],
    [33.3, 66.6],
    [100, 0],
  ])("sums to 100 when valid (bnd %d, vxusOfStocks %d)", (bnd, vxusOfStocks) => {
    const t = deriveTargets({ bnd, vxusOfStocks });
    expect(t.error).toBeNull();
    expect(Math.abs(t.vti + t.vxus + t.bnd - 100)).toBeLessThan(1e-9);
  });

  it("gives an all-bond portfolio no stock", () => {
    const t = deriveTargets({ bnd: 100, vxusOfStocks: 50 });
    expect(t).toMatchObject({ vti: 0, vxus: 0, bnd: 100, error: null });
  });

  it.each([
    [null, 50],
    [-1, 50],
    [100.1, 50],
    [Number.NaN, 50],
  ])("rejects bnd %j", (bnd, vxusOfStocks) => {
    expect(deriveTargets({ bnd, vxusOfStocks }).error).toBe(BND_ERROR);
  });

  it.each([[null], [-1], [100.1], [Number.NaN]])("rejects vxusOfStocks %j", (vxusOfStocks) => {
    expect(deriveTargets({ bnd: 20, vxusOfStocks }).error).toBe(VXUS_ERROR);
  });

  it("reports the BND problem first when both are invalid", () => {
    expect(deriveTargets({ bnd: -5, vxusOfStocks: 500 }).error).toBe(BND_ERROR);
  });

  it("accepts the 0 and 100 boundaries", () => {
    expect(deriveTargets({ bnd: 0, vxusOfStocks: 100 }).error).toBeNull();
    expect(deriveTargets({ bnd: 100, vxusOfStocks: 0 }).error).toBeNull();
  });

  it.each([
    [null, 50],
    [Number.NaN, 50],
  ])("shows bnd %j as 0", (bnd, vxusOfStocks) => {
    expect(deriveTargets({ bnd, vxusOfStocks }).bnd).toBe(0);
  });

  it.each([
    [120, 50],
    [-10, 500],
    [null, null],
    [100, 100],
    [0, 0],
  ])("never returns negative or -0 weights (bnd %j, vxusOfStocks %j)", (bnd, vxusOfStocks) => {
    const t = deriveTargets({ bnd, vxusOfStocks });
    for (const w of [t.vti, t.vxus]) {
      expect(w).toBeGreaterThanOrEqual(0);
      expect(Object.is(w, -0)).toBe(false);
    }
  });
});

describe("inputsFromTarget", () => {
  it.each([
    [
      { vti: 56, vxus: 24, bnd: 20 },
      { bnd: 20, vxusOfStocks: 30 },
    ],
    [
      { vti: 42, vxus: 18, bnd: 40 },
      { bnd: 40, vxusOfStocks: 30 },
    ],
    [
      { vti: 70, vxus: 30, bnd: 0 },
      { bnd: 0, vxusOfStocks: 30 },
    ],
    [
      { vti: 60, vxus: 0, bnd: 40 },
      { bnd: 40, vxusOfStocks: 0 },
    ],
  ])("derives inputs from %j", (target, expected) => {
    expect(inputsFromTarget(target)).toEqual(expected);
  });

  it("rounds vxusOfStocks to 2 decimals", () => {
    expect(inputsFromTarget({ vti: 50, vxus: 10, bnd: 40 }).vxusOfStocks).toBe(16.67);
  });

  it("returns 0 vxusOfStocks for an all-bond target", () => {
    expect(inputsFromTarget({ vti: 0, vxus: 0, bnd: 100 })).toEqual({
      bnd: 100,
      vxusOfStocks: 0,
    });
  });

  it("round-trips through deriveTargets", () => {
    const target = { vti: 48, vxus: 32, bnd: 20 };
    const t = deriveTargets(inputsFromTarget(target));
    expect(t.vti).toBeCloseTo(48, 1);
    expect(t.vxus).toBeCloseTo(32, 1);
    expect(t.bnd).toBeCloseTo(20, 1);
  });
});
