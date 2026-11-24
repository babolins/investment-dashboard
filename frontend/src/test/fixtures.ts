/**
 * Shared test fixtures shaped like real API responses.
 *
 * The numbers are internally consistent: `rebalance` is what the backend returns for
 * `allocation` with a $1,000 investment and the `config.default_target` weights.
 */
import type {
  AllocationBreakdown,
  ConfigSummary,
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

// The API returns buckets in alphabetical order.
export const allocation: AllocationBreakdown = {
  buckets: [
    { bucket: "BND", current_value: 1000, percent_of_included: 10 },
    { bucket: "VTI", current_value: 6000, percent_of_included: 60 },
    { bucket: "VXUS", current_value: 3000, percent_of_included: 30 },
  ],
  included_value: 10000,
  excluded_value: 1000,
  total_value: 11000,
};

// symbolsByBucket(config)     -> { VTI: ["FZROX", "ITOT", "VTI"], VXUS: ["FZROX", "VXUS"], BND: ["BND"] }
// bucketLabelBySymbol(config) -> { VTI: "VTI", VXUS: "VXUS", BND: "BND", ITOT: "VTI",
//                                  FZROX: "VTI/VXUS", SPAXX: "Excl." }
export const config: ConfigSummary = {
  direct_mappings: { VTI: "VTI", VXUS: "VXUS", BND: "BND", ITOT: "VTI" },
  fractional_mappings: { FZROX: { VTI: 0.7, VXUS: 0.3 } },
  exclusions: ["SPAXX"],
  primary_symbols: { VTI: "VTI", VXUS: "VXUS", BND: "BND" },
  default_target: { vti: 48, vxus: 32, bnd: 20 },
};

// Post-trade allocation (new total 11,000): VTI 54.5%, VXUS 30.0%, BND 15.4%.
export const rebalance: RebalanceResult = {
  recommendations: [
    {
      bucket: "VTI",
      symbol: "VTI",
      target_percent: 48,
      current_percent: 60,
      current_value: 6000,
      target_value: 5280,
      buy_amount: 0,
      buy_percent_of_investment: 0,
    },
    {
      bucket: "VXUS",
      symbol: "VXUS",
      target_percent: 32,
      current_percent: 30,
      current_value: 3000,
      target_value: 3520,
      buy_amount: 302.33,
      buy_percent_of_investment: 30.233,
    },
    {
      bucket: "BND",
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
