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
import { config, groupedConfig } from "../test/fixtures";
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

const grouped = buildTree(groupedConfig);
const groupedShares = defaultShares(grouped);
const flat = buildTree(cfg([], [cat("A", null), cat("B", null)]));

describe("buildTree", () => {
  it("nests categories under their group and keeps top-level categories", () => {
    expect(shape(grouped)).toEqual([["Stocks", "US Stocks", "International"], "Bonds"]);
  });

  it("builds typed nodes", () => {
    const [stocks, bonds] = grouped;
    expect(stocks).toMatchObject({ kind: "group", name: "Stocks", target: 60 });
    expect(bonds).toEqual({
      kind: "category",
      name: "Bonds",
      target: 40,
      color: "#1baf7a",
      buySymbol: "BND",
    });
    if (stocks.kind !== "group") throw new Error("expected a group");
    expect(stocks.children[0]).toEqual({
      kind: "category",
      name: "US Stocks",
      target: 70,
      color: "#2a78d6",
      buySymbol: "VTI",
    });
  });

  it("puts groups before categories at every level, each in config order", () => {
    const tree = buildTree(
      cfg([grp("G1", null), grp("G2", null, "G1")], [cat("A", null), cat("B", null, "G1")]),
    );
    expect(shape(tree)).toEqual([["G1", ["G2"], "B"], "A"]);
  });

  it("keeps config order among siblings", () => {
    const tree = buildTree(cfg([grp("Z", 1), grp("A", 1)], [cat("M", 1), cat("B", 1)]));
    expect(shape(tree)).toEqual([["Z"], ["A"], "M", "B"]);
  });

  it("returns the categories in order for a flat config", () => {
    const tree = buildTree(config);
    expect(shape(tree)).toEqual(["US Stocks", "International", "Bonds"]);
    expect(tree.every((n) => n.kind === "category")).toBe(true);
  });

  it("keeps empty groups", () => {
    expect(shape(buildTree(cfg([grp("Empty", null)], [])))).toEqual([["Empty"]]);
  });

  it("returns [] for an empty config", () => {
    expect(buildTree(cfg([], []))).toEqual([]);
  });

  it("treats a parent that names no group as top level", () => {
    const tree = buildTree(cfg([grp("G", null, "Ghost")], [cat("A", null, "Nope")]));
    expect(shape(tree)).toEqual([["G"], "A"]);
  });

  it("does not loop on a group cycle", () => {
    const tree = buildTree(
      cfg([grp("A", null, "B"), grp("B", null, "A"), grp("C", null)], [cat("X", null, "C")]),
    );
    expect(shape(tree)).toEqual([["C", "X"]]);
  });

  it("does not loop on a group that is its own parent", () => {
    expect(() => buildTree(cfg([grp("A", null, "A")], [cat("X", null)]))).not.toThrow();
  });
});

describe("defaultShares", () => {
  it("reads every node's target, groups included", () => {
    expect(groupedShares).toEqual({ Stocks: 60, "US Stocks": 70, International: 30, Bonds: 40 });
  });

  it("keeps missing targets as null", () => {
    expect(
      defaultShares(buildTree(cfg([grp("G", null)], [cat("A", null, "G"), cat("B", 100)]))),
    ).toEqual({ G: null, A: null, B: 100 });
  });

  it("returns an empty record for no nodes", () => {
    expect(defaultShares([])).toEqual({});
  });

  it("reads a flat config's targets", () => {
    expect(defaultShares(buildTree(config))).toEqual({
      "US Stocks": 48,
      International: 32,
      Bonds: 20,
    });
  });
});

describe("portfolioPercents", () => {
  it("multiplies shares down one level", () => {
    expectClose(portfolioPercents(grouped, groupedShares), {
      Stocks: 60,
      "US Stocks": 42,
      International: 18,
      Bonds: 40,
    });
  });

  it("multiplies through three levels", () => {
    const tree = buildTree(threeLevel);
    const pct = portfolioPercents(tree, defaultShares(tree));
    expectClose(pct, {
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

  it("is the share itself for a flat config", () => {
    const tree = buildTree(config);
    expectClose(portfolioPercents(tree, defaultShares(tree)), {
      "US Stocks": 48,
      International: 32,
      Bonds: 20,
    });
  });

  it("treats a null share as 0 without redistributing", () => {
    expectClose(portfolioPercents(grouped, { ...groupedShares, "US Stocks": null }), {
      Stocks: 60,
      "US Stocks": 0,
      International: 18,
      Bonds: 40,
    });
  });

  it("zeroes a whole subtree when its group share is null", () => {
    expectClose(portfolioPercents(grouped, { ...groupedShares, Stocks: null }), {
      Stocks: 0,
      "US Stocks": 0,
      International: 0,
      Bonds: 40,
    });
  });

  it("treats NaN and missing shares as 0", () => {
    expectClose(portfolioPercents(grouped, { Stocks: NaN }), {
      Stocks: 0,
      "US Stocks": 0,
      International: 0,
      Bonds: 0,
    });
  });

  it("is all zeros for empty shares", () => {
    const pct = portfolioPercents(grouped, {});
    expect(Object.values(pct)).toEqual([0, 0, 0, 0]);
  });

  it("includes empty groups at 0 children", () => {
    const tree = buildTree(cfg([grp("E", 50)], [cat("A", 50)]));
    expectClose(portfolioPercents(tree, defaultShares(tree)), { E: 50, A: 50 });
  });

  it("does not mutate its inputs", () => {
    const shares = { ...groupedShares };
    const before = JSON.stringify(grouped);
    portfolioPercents(grouped, shares);
    expect(shares).toEqual(groupedShares);
    expect(JSON.stringify(grouped)).toBe(before);
  });
});

describe("categoryTargets", () => {
  it("returns only categories, as whole-portfolio percents", () => {
    expectClose(categoryTargets(grouped, groupedShares), {
      "US Stocks": 42,
      International: 18,
      Bonds: 40,
    });
  });

  it("lists categories in depth-first tree order", () => {
    expect(Object.keys(categoryTargets(grouped, groupedShares))).toEqual([
      "US Stocks",
      "International",
      "Bonds",
    ]);
  });

  it("sums the leaves to 100 for a valid three-level tree", () => {
    const tree = buildTree(threeLevel);
    const targets = categoryTargets(tree, defaultShares(tree));
    expect(Object.keys(targets)).toEqual(["US", "Small", "Dev", "EM", "Corp"]);
    expect(Object.values(targets).reduce((a, b) => a + b, 0)).toBeCloseTo(100, 9);
  });

  it("matches the flat config targets", () => {
    const tree = buildTree(config);
    expectClose(categoryTargets(tree, defaultShares(tree)), {
      "US Stocks": 48,
      International: 32,
      Bonds: 20,
    });
  });

  it("includes null-share categories as 0", () => {
    expectClose(categoryTargets(grouped, { ...groupedShares, "US Stocks": null }), {
      "US Stocks": 0,
      International: 18,
      Bonds: 40,
    });
  });

  it("is all zeros for empty shares and {} for no nodes", () => {
    expect(Object.values(categoryTargets(grouped, {}))).toEqual([0, 0, 0]);
    expect(categoryTargets([], {})).toEqual({});
  });

  it("gives the same result on the pruned tree when groups are empty", () => {
    const tree = buildTree(cfg([grp("E", 10)], [cat("A", 90)]));
    const shares = defaultShares(tree);
    expect(categoryTargets(prunedTree(tree), shares)).toEqual(categoryTargets(tree, shares));
    expect(Object.keys(categoryTargets(tree, shares))).toEqual(["A"]);
  });

  it("does not round (float noise is left to the backend tolerance)", () => {
    const targets = categoryTargets(grouped, { ...groupedShares, Stocks: 33.3, Bonds: 66.7 });
    expect(targets["International"]).toBeCloseTo(9.99, 9);
    expect(targets["Bonds"]).toBeCloseTo(66.7, 9);
  });
});

describe("levelTotal", () => {
  it("sums one level's shares", () => {
    expect(levelTotal(grouped, groupedShares)).toBe(100);
    if (grouped[0].kind !== "group") throw new Error("expected a group");
    expect(levelTotal(grouped[0].children, groupedShares)).toBe(100);
  });

  it("only counts the given level", () => {
    expect(levelTotal(grouped, { ...groupedShares, "US Stocks": 5 })).toBe(100);
  });

  it("counts null, NaN and missing shares as 0", () => {
    expect(levelTotal(flat, { A: null, B: 40 })).toBe(40);
    expect(levelTotal(flat, { A: NaN, B: 40 })).toBe(40);
    expect(levelTotal(flat, { B: 40 })).toBe(40);
  });

  it("sums the flat config's targets", () => {
    const tree = buildTree(config);
    expect(levelTotal(tree, defaultShares(tree))).toBe(100);
  });

  it("is 0 for an empty level", () => {
    expect(levelTotal([], {})).toBe(0);
  });
});

describe("siblingErrors", () => {
  const TOP_OK = (shares: Shares) => siblingErrors(grouped, { ...groupedShares, ...shares });

  it("is empty when every level totals 100", () => {
    expect(siblingErrors(grouped, groupedShares)).toEqual({});
  });

  it("is empty for the flat config and the three-level tree", () => {
    const flatTree = buildTree(config);
    expect(siblingErrors(flatTree, defaultShares(flatTree))).toEqual({});
    const tree = buildTree(threeLevel);
    expect(siblingErrors(tree, defaultShares(tree))).toEqual({});
  });

  it("is empty for no nodes", () => {
    expect(siblingErrors([], {})).toEqual({});
  });

  it("reports a failing group level under the group's name", () => {
    expect(TOP_OK({ "US Stocks": null })).toEqual({
      Stocks: "Stocks: must add up to 100% (currently 30.0%).",
    });
  });

  it("reports a failing top level under the empty key", () => {
    expect(TOP_OK({ Stocks: 50 })).toEqual({
      "": "Top level: must add up to 100% (currently 90.0%).",
    });
  });

  it("treats all-empty shares as 0 at every level", () => {
    expect(siblingErrors(grouped, {})).toEqual({
      "": "Top level: must add up to 100% (currently 0.0%).",
      Stocks: "Stocks: must add up to 100% (currently 0.0%).",
    });
  });

  it("reports several levels at once", () => {
    const tree = buildTree(threeLevel);
    const errors = siblingErrors(tree, {
      ...defaultShares(tree),
      Fixed: 30,
      Stocks: 50,
    });
    expect(errors).toEqual({
      "": "Top level: must add up to 100% (currently 105.0%).",
      Equity: "Equity: must add up to 100% (currently 90.0%).",
    });
  });

  it("has no level for an empty group", () => {
    const tree = buildTree(cfg([grp("E", 10)], [cat("A", 90)]));
    expect(siblingErrors(tree, defaultShares(tree))).toEqual({});
  });

  it.each([
    [{ Stocks: 60, Bonds: 40 }],
    [{ Stocks: null, Bonds: 100 }],
    [{ Stocks: 33.33, Bonds: 66.67 }],
    [{ Stocks: 50, Bonds: 49.995 }],
    [{ Stocks: 50, Bonds: 49.99 }],
    [{ Stocks: 50, Bonds: 50.01 }],
    [{ Stocks: 50, Bonds: 49.999 }],
  ])("accepts a top level of %j (within the 0.01 tolerance)", (top) => {
    expect(TOP_OK(top)).toEqual({});
  });

  it("accepts a single node at 100", () => {
    expect(siblingErrors(buildTree(cfg([], [cat("A", 100)])), { A: 100 })).toEqual({});
  });

  it("rejects a total just outside the tolerance", () => {
    expect(TOP_OK({ Stocks: 50, Bonds: 50.0101 })[""]).toBe(
      "Top level: must add up to 100% (currently 100.01%).",
    );
  });

  it("shows two decimals when the total is close to 100", () => {
    expect(TOP_OK({ Stocks: 50, Bonds: 49.98 })[""]).toBe(
      "Top level: must add up to 100% (currently 99.98%).",
    );
  });

  it("shows one decimal when the total is further from 100", () => {
    expect(TOP_OK({ Stocks: 50, Bonds: 45 })[""]).toBe(
      "Top level: must add up to 100% (currently 95.0%).",
    );
  });

  it("never reads a failing total as 100.0%", () => {
    for (const bonds of [49.96, 50.04, 49.951]) {
      expect(TOP_OK({ Stocks: 50, Bonds: bonds })[""]).not.toMatch(/\(currently 100\.0%\)/);
    }
  });

  it("flags out-of-range shares before checking the total", () => {
    expect(TOP_OK({ Stocks: -5, Bonds: 105, "US Stocks": 80, International: 30 })).toEqual({
      "": "Top level: each share must be between 0% and 100%.",
      Stocks: "Stocks: must add up to 100% (currently 110.0%).",
    });
  });

  it.each([
    [{ Stocks: -1, Bonds: 101 }],
    [{ Stocks: 101, Bonds: -1 }],
    [{ Stocks: NaN, Bonds: 100 }],
    [{ Stocks: Infinity, Bonds: 0 }],
  ])("reports the range error for %j", (top) => {
    expect(TOP_OK(top)[""]).toBe("Top level: each share must be between 0% and 100%.");
  });

  it("reports the range error under a group's name", () => {
    expect(TOP_OK({ International: 130, "US Stocks": -30 }).Stocks).toBe(
      "Stocks: each share must be between 0% and 100%.",
    );
  });

  it("does not mutate its inputs", () => {
    const shares = { ...groupedShares };
    siblingErrors(grouped, shares);
    expect(shares).toEqual(groupedShares);
  });
});

describe("withPairFill", () => {
  it("fills the only sibling with the remainder", () => {
    expect(withPairFill(flat, { A: null, B: null }, "A", 33.33)).toEqual({ A: 33.33, B: 66.67 });
  });

  it("fills in both directions", () => {
    expect(withPairFill(flat, {}, "B", 25)).toEqual({ A: 75, B: 25 });
  });

  it("rounds the sibling to 2 decimals", () => {
    expect(withPairFill(flat, {}, "A", 33.333).B).toBe(66.67);
    expect(withPairFill(flat, {}, "A", (1 / 3) * 100).B).toBe(66.67);
  });

  it.each([
    [0.1, 99.9],
    [57.14, 42.86],
    [99.99, 0.01],
    [0, 100],
    [100, 0],
  ])("fills %d -> %d", (value, expected) => {
    expect(withPairFill(flat, {}, "A", value).B).toBe(expected);
  });

  it("overwrites an existing sibling value", () => {
    expect(withPairFill(flat, { A: 1, B: 7 }, "A", 40)).toEqual({ A: 40, B: 60 });
  });

  it.each([[150], [-1], [null], [NaN], [Infinity]])(
    "sets the value but leaves the sibling alone for %s",
    (value) => {
      const result = withPairFill(flat, { A: 1, B: 7 }, "A", value);
      expect(result.B).toBe(7);
      expect(result.A).toBe(value);
    },
  );

  it("does not fill when there are two or more siblings", () => {
    const three = buildTree(cfg([], [cat("A", null), cat("B", null), cat("C", null)]));
    expect(withPairFill(three, { B: 1, C: 2 }, "A", 30)).toEqual({ A: 30, B: 1, C: 2 });
  });

  it("does not fill when there are no siblings", () => {
    const one = buildTree(cfg([], [cat("A", null)]));
    expect(withPairFill(one, {}, "A", 30)).toEqual({ A: 30 });
  });

  it("just sets an unknown name", () => {
    expect(withPairFill(flat, { A: 1, B: 7 }, "Zed", 5)).toEqual({ A: 1, B: 7, Zed: 5 });
  });

  it("fills a top-level pair made of a group and a category", () => {
    expect(withPairFill(grouped, groupedShares, "Stocks", 30)).toEqual({
      ...groupedShares,
      Stocks: 30,
      Bonds: 70,
    });
    expect(withPairFill(grouped, groupedShares, "Bonds", 10)).toEqual({
      ...groupedShares,
      Stocks: 90,
      Bonds: 10,
    });
  });

  it("fills within a group's level only", () => {
    expect(withPairFill(grouped, groupedShares, "International", 25)).toEqual({
      ...groupedShares,
      "US Stocks": 75,
      International: 25,
    });
  });

  it("fills within a deeper level", () => {
    const tree = buildTree(threeLevel);
    const shares = defaultShares(tree);
    expect(withPairFill(tree, shares, "Dev", 20)).toEqual({ ...shares, Dev: 20, EM: 80 });
  });

  it("does not mutate the given shares", () => {
    const shares = { A: 1, B: 7 };
    const result = withPairFill(flat, shares, "A", 40);
    expect(shares).toEqual({ A: 1, B: 7 });
    expect(result).not.toBe(shares);
  });
});

describe("prunedTree", () => {
  const messy = buildTree(
    cfg(
      [
        grp("Empty", null),
        grp("Outer", null),
        grp("InnerEmpty", null, "Outer"),
        grp("Full", null),
        grp("Sub", null, "Full"),
      ],
      [cat("X", null, "Full"), cat("Y", null)],
    ),
  );

  it("drops groups with no category below, recursively", () => {
    expect(shape(messy)).toEqual([
      ["Empty"],
      ["Outer", ["InnerEmpty"]],
      ["Full", ["Sub"], "X"],
      "Y",
    ]);
    expect(shape(prunedTree(messy))).toEqual([["Full", "X"], "Y"]);
  });

  it("keeps a nested chain that ends in a category", () => {
    const tree = buildTree(
      cfg(
        [grp("Outer", null), grp("In", null, "Outer"), grp("Deep", null, "In")],
        [cat("Z", null, "Deep")],
      ),
    );
    expect(shape(prunedTree(tree))).toEqual([["Outer", ["In", ["Deep", "Z"]]]]);
  });

  it("returns [] when there are only empty groups", () => {
    expect(prunedTree(buildTree(cfg([grp("E", null)], [])))).toEqual([]);
  });

  it("returns an equal tree when nothing is empty", () => {
    expect(prunedTree(grouped)).toEqual(grouped);
  });

  it("does not mutate its input", () => {
    const before = JSON.stringify(messy);
    prunedTree(messy);
    expect(JSON.stringify(messy)).toBe(before);
  });
});

describe("descendantGroups", () => {
  it("lists every group below a group, excluding itself", () => {
    expect(descendantGroups(threeLevel, "Equity")).toEqual(["Stocks", "Intl"]);
  });

  it("follows nesting transitively", () => {
    const deep = cfg(
      [grp("A", null), grp("B", null, "A"), grp("C", null, "B"), grp("D", null)],
      [],
    );
    expect(descendantGroups(deep, "A")).toEqual(["B", "C"]);
    expect(descendantGroups(deep, "B")).toEqual(["C"]);
  });

  it("returns config group order", () => {
    const c = cfg([grp("C", null, "A"), grp("A", null), grp("B", null, "A")], []);
    expect(descendantGroups(c, "A")).toEqual(["C", "B"]);
  });

  it("is empty for a leaf group and an unknown group", () => {
    expect(descendantGroups(threeLevel, "Fixed")).toEqual([]);
    expect(descendantGroups(threeLevel, "Nope")).toEqual([]);
  });

  it("is empty for a flat config", () => {
    expect(descendantGroups(config, "Stocks")).toEqual([]);
  });

  it("terminates on a cycle", () => {
    const c = cfg([grp("A", null, "B"), grp("B", null, "A")], []);
    const result = descendantGroups(c, "A");
    expect(result).toContain("B");
    expect(result.length).toBeLessThanOrEqual(2);
  });
});
