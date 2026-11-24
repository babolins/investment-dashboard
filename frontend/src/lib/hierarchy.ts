/**
 * Target planning over the category tree.
 *
 * Categories contain categories. A category with sub-categories is a planning level; one without is a
 * leaf, which is where investments are assigned. Every node's target is a "% of parent" share:
 * top-level nodes are a % of the portfolio, nested nodes a % of their parent. A leaf's
 * whole-portfolio percent is the product of the shares down its path (US Stocks 70% of Stocks,
 * Stocks 60% of the portfolio -> 42%). Each level's shares should total 100, which guarantees the
 * leaves total 100 too.
 *
 * Everything here is pure and keyed by category name (unique across the config).
 */
import type { ConfigSummary } from "../types";

export interface TreeNode {
  name: string;
  target: number | null;
  buySymbol: string | null;
  color: string | null;
  /** Empty for a leaf. */
  children: TreeNode[];
}

/** Node name -> share (% of parent); null means unset and counts as 0. */
export type Shares = Record<string, number | null>;

/** Permitted distance from 100 for a level's total (matches the backend). */
const TOTAL_TOLERANCE = 0.01;

const num = (v: number | null | undefined): number =>
  typeof v === "number" && Number.isFinite(v) ? v : 0;

/**
 * The config as a tree, in config order within each parent. A parent naming no category is treated
 * as top level, and categories caught in a cycle are skipped rather than recursing forever (the
 * backend rejects both, so this only guards against malformed input).
 */
export function buildTree(config: ConfigSummary): TreeNode[] {
  const names = new Set(config.categories.map((c) => c.name));
  const parentOf = (parent: string | null): string | null =>
    parent !== null && names.has(parent) ? parent : null;

  const build = (parent: string | null, seen: Set<string>): TreeNode[] =>
    config.categories
      .filter((c) => parentOf(c.parent) === parent && !seen.has(c.name))
      .map((c) => ({
        name: c.name,
        target: c.target,
        buySymbol: c.buy_symbol,
        color: c.color,
        children: build(c.name, new Set([...seen, c.name])),
      }));
  return build(null, new Set());
}

/** Names of the categories no other category is inside, in config order. */
export function leafNames(config: ConfigSummary): string[] {
  const parents = new Set(config.categories.map((c) => c.parent));
  return config.categories.map((c) => c.name).filter((name) => !parents.has(name));
}

/** Names of every category below `name` (not itself), in config order: invalid "Move to" targets. */
export function descendants(config: ConfigSummary, name: string): string[] {
  const found = new Set<string>();
  const pending = [name];
  while (pending.length > 0) {
    const parent = pending.pop();
    for (const c of config.categories) {
      if (c.parent === parent && c.name !== name && !found.has(c.name)) {
        found.add(c.name);
        pending.push(c.name);
      }
    }
  }
  return config.categories.map((c) => c.name).filter((n) => found.has(n));
}

/** The configured default target of every node. */
export function defaultShares(nodes: TreeNode[]): Shares {
  const shares: Shares = {};
  const visit = (level: TreeNode[]) => {
    for (const node of level) {
      shares[node.name] = node.target;
      visit(node.children);
    }
  };
  visit(nodes);
  return shares;
}

/** Every node's percent of the whole portfolio (a null share counts as 0). Not rounded. */
export function portfolioPercents(nodes: TreeNode[], shares: Shares): Record<string, number> {
  const percents: Record<string, number> = {};
  const visit = (level: TreeNode[], parentPercent: number) => {
    for (const node of level) {
      const percent = (parentPercent * num(shares[node.name])) / 100;
      percents[node.name] = percent;
      visit(node.children, percent);
    }
  };
  visit(nodes, 100);
  return percents;
}

/** Whole-portfolio percent of each leaf only (the rebalance payload). Not rounded. */
export function leafTargets(nodes: TreeNode[], shares: Shares): Record<string, number> {
  const percents = portfolioPercents(nodes, shares);
  const targets: Record<string, number> = {};
  const visit = (level: TreeNode[]) => {
    for (const node of level) {
      if (node.children.length === 0) targets[node.name] = percents[node.name];
      else visit(node.children);
    }
  };
  visit(nodes);
  return targets;
}

/** Sum of one level's shares (a null share counts as 0). */
export function levelTotal(nodes: TreeNode[], shares: Shares): number {
  return nodes.reduce((sum, node) => sum + num(shares[node.name]), 0);
}

function levelError(label: string, nodes: TreeNode[], shares: Shares): string | null {
  const outOfRange = nodes.some((node) => {
    const share = shares[node.name];
    return share != null && (!Number.isFinite(share) || share < 0 || share > 100);
  });
  if (outOfRange) return `${label}: each share must be between 0% and 100%.`;

  const total = levelTotal(nodes, shares);
  const off = Math.abs(total - 100);
  if (off <= TOTAL_TOLERANCE + 1e-9) return null;
  // Two decimals near 100 so a failing total never reads "100.0%".
  return `${label}: must add up to 100% (currently ${total.toFixed(off < 0.05 ? 2 : 1)}%).`;
}

/**
 * Problems per level, keyed by the parent category's name ("" for the top level). Only levels whose
 * shares are out of range or don't total 100 appear. Empty levels are ignored.
 */
export function siblingErrors(nodes: TreeNode[], shares: Shares): Record<string, string> {
  const errors: Record<string, string> = {};
  const check = (level: TreeNode[], key: string, label: string) => {
    if (level.length === 0) return;
    const error = levelError(label, level, shares);
    if (error) errors[key] = error;
    for (const node of level) check(node.children, node.name, node.name);
  };
  check(nodes, "", "Top level");
  return errors;
}

function findLevel(nodes: TreeNode[], name: string): TreeNode[] | null {
  if (nodes.some((node) => node.name === name)) return nodes;
  for (const node of nodes) {
    const found = findLevel(node.children, name);
    if (found) return found;
  }
  return null;
}

/**
 * Sets `name`'s share. If it has exactly one sibling and the value is within 0-100, the sibling
 * gets the remainder (2 dp).
 */
export function withPairFill(
  nodes: TreeNode[],
  shares: Shares,
  name: string,
  value: number | null,
): Shares {
  const next: Shares = { ...shares, [name]: value };
  const siblings = (findLevel(nodes, name) ?? []).filter((node) => node.name !== name);
  if (
    siblings.length === 1 &&
    value !== null &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 100
  ) {
    next[siblings[0].name] = Math.round((100 - value) * 100) / 100;
  }
  return next;
}
