import { describe, expect, it } from "vitest";
import {
  buildTree,
  categoryTargets,
  defaultShares,
  descendantGroups,
  levelTotal,
  portfolioPercents,
  prunedTree,
  siblingErrors,
  withPairFill,
  type Shares,
  type TreeNode,
} from "./hierarchy";
import { groupedConfig } from "../test/fixtures";
import type { Category, ConfigSummary, Group } from "../types";

const cat = (name: string, target: number | null, parent: string | null = null): Category => ({
  name,
  buy_symbol: name.slice(0, 3).toUpperCase(),
  parent,
  target,
  color: "#111111",
});
const grp = (name: string, target: number | null, parent: string | null = null): Group => ({
  name,
  parent,
  target,
});
const cfg = (groups: Group[], categories: Category[]): ConfigSummary => ({
  groups,
  categories,
  assignments: {},
  exclusions: [],
});

/** Names of a tree as nested arrays: leaf -> "name", group -> [name, ...children]. */
function shape(nodes: TreeNode[]): unknown[] {
  return nodes.map((n) => (n.kind === "group" ? [n.name, ...shape(n.children)] : n.name));
}

/** Asserts two name->number records have the same keys and (float-tolerant) values. */
function expectClose(actual: Record<string, number>, expected: Record<string, number>): void {
  expect(Object.keys(actual).sort()).toEqual(Object.keys(expected).sort());
  for (const [k, v] of Object.entries(expected)) expect(actual[k]).toBeCloseTo(v, 9);
}

// Stocks 60 { US Stocks 70, International 30 }, Bonds 40
const grouped = buildTree(groupedConfig);
const groupedShares = defaultShares(grouped);

// Equity 75 { Stocks 60 { US 70, Small 30 }, Intl 40 { Dev 50, EM 50 } }, Fixed 25 { Corp 100 }
const threeLevel = cfg(
  [grp("Equity", 75), grp("Stocks", 60, "Equity"), grp("Intl", 40, "Equity"), grp("Fixed", 25)],
  [
    cat("US", 70, "Stocks"),
    cat("Small", 30, "Stocks"),
    cat("Dev", 50, "Intl"),
    cat("EM", 50, "Intl"),
    cat("Corp", 100, "Fixed"),
  ],
);

const flat = buildTree(cfg([], [cat("A", null), cat("B", null)]));

describe("buildTree", () => {
  it("nests categories under their group as typed nodes", () => {
    expect(shape(grouped)).toEqual([["Stocks", "US Stocks", "International"], "Bonds"]);
    expect(grouped[0]).toMatchObject({ kind: "group", name: "Stocks", target: 60 });
    expect(grouped[1]).toEqual({
      kind: "category",
      name: "Bonds",
      target: 40,
      color: "#1baf7a",
      buySymbol: "BND",
    });
  });

  it("puts groups before categories at every level, each in config order", () => {
    const tree = buildTree(
      cfg(
        [grp("Z", null), grp("G2", null, "Z"), grp("A", null)],
        [cat("M", null), cat("B", null, "Z")],
      ),
    );
    expect(shape(tree)).toEqual([["Z", ["G2"], "B"], ["A"], "M"]);
  });

  it("treats a parent that names no group as top level", () => {
    const tree = buildTree(cfg([grp("G", null, "Ghost")], [cat("A", null, "Nope")]));
    expect(shape(tree)).toEqual([["G"], "A"]);
  });

  it("skips groups caught in a cycle instead of looping", () => {
    const tree = buildTree(
      cfg([grp("A", null, "B"), grp("B", null, "A"), grp("C", null)], [cat("X", null, "C")]),
    );
    expect(shape(tree)).toEqual([["C", "X"]]);
  });
});

describe("defaultShares", () => {
  it("reads every node's target, keeping unset ones as null", () => {
    expect(groupedShares).toEqual({ Stocks: 60, "US Stocks": 70, International: 30, Bonds: 40 });
    expect(defaultShares(buildTree(cfg([grp("G", null)], [cat("A", null, "G")])))).toEqual({
      G: null,
      A: null,
    });
  });
});

describe("portfolioPercents", () => {
  it("multiplies shares down the tree", () => {
    expectClose(portfolioPercents(grouped, groupedShares), {
      Stocks: 60,
      "US Stocks": 42,
      International: 18,
      Bonds: 40,
    });
    const tree = buildTree(threeLevel);
    expectClose(portfolioPercents(tree, defaultShares(tree)), {
      Equity: 75,
      Stocks: 45,
      US: 31.5,
      Small: 13.5,
      Intl: 30,
      Dev: 15,
      EM: 15,
      Fixed: 25,
      Corp: 25,
    });
  });

  it("treats null, NaN and missing shares as 0 without redistributing", () => {
    expectClose(portfolioPercents(grouped, { ...groupedShares, "US Stocks": null }), {
      Stocks: 60,
      "US Stocks": 0,
      International: 18,
      Bonds: 40,
    });
    // A group at 0 zeroes its whole subtree.
    expectClose(portfolioPercents(grouped, { Stocks: NaN, Bonds: 40 }), {
      Stocks: 0,
      "US Stocks": 0,
      International: 0,
      Bonds: 40,
    });
  });
});

describe("categoryTargets", () => {
  it("returns whole-portfolio percents for categories only", () => {
    expectClose(categoryTargets(grouped, groupedShares), {
      "US Stocks": 42,
      International: 18,
      Bonds: 40,
    });
    const tree = buildTree(threeLevel);
    const total = Object.values(categoryTargets(tree, defaultShares(tree))).reduce(
      (a, b) => a + b,
      0,
    );
    expect(total).toBeCloseTo(100, 9);
  });

  it("does not round (float noise is left to the backend tolerance)", () => {
    const targets = categoryTargets(grouped, { ...groupedShares, Stocks: 33.3, Bonds: 66.7 });
    expect(targets["International"]).toBeCloseTo(9.99, 9);
  });
});

describe("levelTotal", () => {
  it("sums only the given level, counting null, NaN and missing as 0", () => {
    expect(levelTotal(grouped, { ...groupedShares, "US Stocks": 5 })).toBe(100);
    expect(levelTotal(flat, { A: null, B: 40 })).toBe(40);
    expect(levelTotal(flat, { A: NaN })).toBe(0);
  });
});

describe("siblingErrors", () => {
  const withTop = (shares: Shares) => siblingErrors(grouped, { ...groupedShares, ...shares });

  it("is empty when every level totals 100, and for an empty tree", () => {
    expect(siblingErrors(grouped, groupedShares)).toEqual({});
    const tree = buildTree(threeLevel);
    expect(siblingErrors(tree, defaultShares(tree))).toEqual({});
    expect(siblingErrors([], {})).toEqual({});
  });

  it("keys errors by parent group, or '' for the top level, reporting several at once", () => {
    expect(withTop({ Stocks: 50, "US Stocks": null })).toEqual({
      "": "Top level: must add up to 100% (currently 90.0%).",
      Stocks: "Stocks: must add up to 100% (currently 30.0%).",
    });
  });

  it("has no level for an empty group", () => {
    const tree = buildTree(cfg([grp("E", 10)], [cat("A", 90)]));
    expect(siblingErrors(tree, defaultShares(tree))).toEqual({});
  });

  it.each([49.99, 50.01, 49.995])("accepts a total within 0.01 of 100 (50 + %d)", (bonds) => {
    expect(withTop({ Stocks: 50, Bonds: bonds })).toEqual({});
  });

  it.each([
    [50.0101, "100.01"], // just outside the tolerance
    [49.98, "99.98"], // two decimals near 100, so it never reads "100.0%"
    [45, "95.0"], // one decimal further away
  ])("reports 50 + %d as currently %s%", (bonds, shown) => {
    expect(withTop({ Stocks: 50, Bonds: bonds })[""]).toBe(
      `Top level: must add up to 100% (currently ${shown}%).`,
    );
  });

  it("checks the range before the total", () => {
    expect(withTop({ Stocks: -5, Bonds: 105 })[""]).toBe(
      "Top level: each share must be between 0% and 100%.",
    );
    expect(withTop({ Stocks: NaN, Bonds: 100 })[""]).toBe(
      "Top level: each share must be between 0% and 100%.",
    );
  });
});

describe("withPairFill", () => {
  it("fills the only sibling with the remainder, rounded to 2 decimals", () => {
    expect(withPairFill(flat, { A: 1, B: 7 }, "A", 33.33)).toEqual({ A: 33.33, B: 66.67 });
    expect(withPairFill(flat, {}, "B", (1 / 3) * 100).A).toBe(66.67);
    expect(withPairFill(flat, {}, "A", 100).B).toBe(0);
  });

  it.each([[150], [-1], [null], [NaN]])("leaves the sibling alone for %s", (value) => {
    expect(withPairFill(flat, { A: 1, B: 7 }, "A", value)).toEqual({ A: value, B: 7 });
  });

  it("does not fill a level with more or fewer than two nodes, or an unknown name", () => {
    const three = buildTree(cfg([], [cat("A", null), cat("B", null), cat("C", null)]));
    expect(withPairFill(three, { B: 1, C: 2 }, "A", 30)).toEqual({ A: 30, B: 1, C: 2 });
    expect(withPairFill(buildTree(cfg([], [cat("A", null)])), {}, "A", 30)).toEqual({ A: 30 });
    expect(withPairFill(flat, { A: 1 }, "Zed", 5)).toEqual({ A: 1, Zed: 5 });
  });

  it("fills a group/category pair at the top level and pairs inside a group", () => {
    // The stocks/bonds case: Stocks 30 -> Bonds 70.
    expect(withPairFill(grouped, groupedShares, "Stocks", 30)).toMatchObject({ Bonds: 70 });
    expect(withPairFill(grouped, groupedShares, "International", 25)).toEqual({
      ...groupedShares,
      "US Stocks": 75,
      International: 25,
    });
    const tree = buildTree(threeLevel); // a pair two levels down, past a group without it
    expect(withPairFill(tree, defaultShares(tree), "Dev", 20)).toMatchObject({ Dev: 20, EM: 80 });
  });

  it("returns a new object", () => {
    const shares = { A: 1, B: 7 };
    withPairFill(flat, shares, "A", 40);
    expect(shares).toEqual({ A: 1, B: 7 });
  });
});

describe("prunedTree", () => {
  it("drops groups with no category below, recursively", () => {
    const tree = buildTree(
      cfg(
        [
          grp("Empty", null),
          grp("Outer", null),
          grp("InnerEmpty", null, "Outer"),
          grp("Full", null),
          grp("Sub", null, "Full"),
          grp("Deep", null, "Sub"),
        ],
        [cat("X", null, "Full"), cat("Z", null, "Deep"), cat("Y", null)],
      ),
    );
    expect(shape(prunedTree(tree))).toEqual([["Full", ["Sub", ["Deep", "Z"]], "X"], "Y"]);
  });
});

describe("descendantGroups", () => {
  it("lists every group below, transitively, in config order, excluding itself", () => {
    const c = cfg(
      [grp("C", null, "B"), grp("A", null), grp("B", null, "A"), grp("D", null, "A")],
      [],
    );
    expect(descendantGroups(c, "A")).toEqual(["C", "B", "D"]);
    expect(descendantGroups(c, "D")).toEqual([]);
    expect(descendantGroups(c, "Nope")).toEqual([]);
  });

  it("terminates on a cycle", () => {
    const c = cfg([grp("A", null, "B"), grp("B", null, "A")], []);
    expect(descendantGroups(c, "A")).toEqual(["B"]);
  });
});
