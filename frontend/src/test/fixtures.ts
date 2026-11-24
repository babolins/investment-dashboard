/**
 * Shared test fixtures shaped like real API responses.
 *
 * The numbers are internally consistent: `rebalance` is what the backend returns for
 * `allocation` with a $1,000 investment and the `config` category targets.
 * `nestedConfig` is the same leaves nested under Stocks (42/18/40 of the portfolio).
 */
import type {
  AllocationBreakdown,
  ConfigSummary,
  HoldingRow,
  PortfolioSnapshot,
  RebalanceResult,
} from "../types";

export const portfolio: PortfolioSnapshot = {
  holdings: [
    {
      symbol: "VTI",
      description: "VANGUARD TOTAL STOCK MARKET ETF",
      quantity: 20,
      last_price: 300,
      current_value: 6000,
      cost_basis: 5000,
      total_gain_loss: 1000,
      percent_of_account: 54.5455,
    },
    {
      symbol: "VXUS",
      description: "VANGUARD TOTAL INTL STOCK ETF",
      quantity: 50,
      last_price: 60,
      current_value: 3000,
      cost_basis: 3200,
      total_gain_loss: -200,
      percent_of_account: 27.2727,
    },
    {
      symbol: "BND",
      description: "VANGUARD TOTAL BOND MARKET ETF",
      quantity: 1234.5,
      last_price: 0.81,
      current_value: 1000,
      cost_basis: null,
      total_gain_loss: null,
      percent_of_account: 9.0909,
    },
    {
      symbol: "SPAXX",
      description: "FIDELITY GOVERNMENT MONEY MARKET",
      quantity: 1000,
      last_price: 1,
      current_value: 1000,
      cost_basis: null,
      total_gain_loss: 0,
      percent_of_account: 9.0909,
    },
  ],
  total_value: 11000,
  total_gain_loss: 800,
  snapshot_date: null,
};

// A holding that `config` does not map; add it with `[...portfolio.holdings, unassignedHolding]`.
export const unassignedHolding: HoldingRow = {
  symbol: "MYSTERY",
  description: "MYSTERY FUND",
  quantity: 10,
  last_price: 50,
  current_value: 500,
  cost_basis: null,
  total_gain_loss: null,
  percent_of_account: 4.3478,
};

export const colors: Record<string, string> = {
  "US Stocks": "#2a78d6",
  International: "#eb6834",
  Bonds: "#1baf7a",
};

// Categories come back in config order, zero-value ones included.
export const allocation: AllocationBreakdown = {
  categories: [
    { category: "US Stocks", current_value: 6000, percent_of_included: 60 },
    { category: "International", current_value: 3000, percent_of_included: 30 },
    { category: "Bonds", current_value: 1000, percent_of_included: 10 },
  ],
  included_value: 10000,
  excluded_value: 1000,
  unassigned_value: 0,
  total_value: 11000,
};

// `allocation` plus the unassigned holding: total = included + excluded + unassigned.
export const allocationWithUnassigned: AllocationBreakdown = {
  ...allocation,
  unassigned_value: 500,
  total_value: 11500,
};

// colorsByCategory(config)   -> `colors`
// symbolsByCategory(config)  -> { "US Stocks": ["FZROX", "ITOT", "VTI"],
//                                 International: ["FZROX", "VXUS"], Bonds: ["BND"] }
// assignmentLabel(assignmentOf(config, symbol)): FZROX -> "US Stocks 70% · International 30%",
//   SPAXX -> "Excluded", MYSTERY -> "Unassigned"
export const config: ConfigSummary = {
  categories: [
    { name: "US Stocks", buy_symbol: "VTI", parent: null, target: 48, color: "#2a78d6" },
    { name: "International", buy_symbol: "VXUS", parent: null, target: 32, color: "#eb6834" },
    { name: "Bonds", buy_symbol: "BND", parent: null, target: 20, color: "#1baf7a" },
  ],
  assignments: {
    VTI: { "US Stocks": 1 },
    ITOT: { "US Stocks": 1 },
    VXUS: { International: 1 },
    BND: { Bonds: 1 },
    FZROX: { "US Stocks": 0.7, International: 0.3 },
  },
  exclusions: ["SPAXX"],
};

// Stocks 60% of the portfolio, split US 70 / International 30; Bonds 40% at top level.
// Whole-portfolio percents: Stocks 60, US Stocks 42, International 18, Bonds 40.
export const nestedConfig: ConfigSummary = {
  categories: [
    { name: "Stocks", parent: null, target: 60, buy_symbol: null, color: null },
    { name: "US Stocks", parent: "Stocks", target: 70, buy_symbol: "VTI", color: "#2a78d6" },
    { name: "International", parent: "Stocks", target: 30, buy_symbol: "VXUS", color: "#eb6834" },
    { name: "Bonds", parent: null, target: 40, buy_symbol: "BND", color: "#1baf7a" },
  ],
  assignments: config.assignments,
  exclusions: ["SPAXX"],
};

// Post-trade allocation (new total 11,000): US Stocks 54.5%, International 30.0%, Bonds 15.4%.
export const rebalance: RebalanceResult = {
  recommendations: [
    {
      category: "US Stocks",
      symbol: "VTI",
      target_percent: 48,
      current_percent: 60,
      current_value: 6000,
      target_value: 5280,
      buy_amount: 0,
      buy_percent_of_investment: 0,
    },
    {
      category: "International",
      symbol: "VXUS",
      target_percent: 32,
      current_percent: 30,
      current_value: 3000,
      target_value: 3520,
      buy_amount: 302.33,
      buy_percent_of_investment: 30.233,
    },
    {
      category: "Bonds",
      symbol: "BND",
      target_percent: 20,
      current_percent: 10,
      current_value: 1000,
      target_value: 2200,
      buy_amount: 697.67,
      buy_percent_of_investment: 69.767,
    },
  ],
  investment_amount: 1000,
  total_buy_amount: 1000,
};
