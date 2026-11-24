export interface HoldingRow {
  symbol: string;
  description: string;
  quantity: number;
  last_price: number;
  current_value: number;
  cost_basis: number | null;
  total_gain_loss: number | null;
  percent_of_account: number;
}

export interface PortfolioSnapshot {
  holdings: HoldingRow[];
  total_value: number;
  total_gain_loss: number | null;
  snapshot_date: string | null;
}

/** A user-defined category as stored in config.yaml. Categories can contain categories. */
export interface Category {
  name: string;
  /** Enclosing category, or null for the top level. */
  parent: string | null;
  /** Default target as a percent of the parent (of the portfolio at the top level). */
  target: number | null;
  /** ETF suggested when buying into this category. */
  buy_symbol: string | null;
  /** Set for every leaf (a category with no sub-categories). */
  color: string | null;
}

/** The editable fields of a category. */
export interface CategoryInput {
  name: string;
  parent?: string | null;
  buy_symbol?: string | null;
  target: number | null;
}

export interface CategoryAllocation {
  category: string;
  current_value: number;
  percent_of_included: number;
}

export interface AllocationBreakdown {
  /** In config category order, zero-value categories included. */
  categories: CategoryAllocation[];
  included_value: number;
  excluded_value: number;
  unassigned_value: number;
  total_value: number;
}

export interface UploadResponse {
  portfolio: PortfolioSnapshot;
  allocation: AllocationBreakdown;
}

/** Target percent (0-100) per category name. */
export type TargetAllocation = Record<string, number>;

export interface RebalanceRequest {
  investment_amount: number;
  target: TargetAllocation;
}

export interface BuyRecommendation {
  category: string;
  symbol: string | null;
  target_percent: number;
  current_percent: number;
  current_value: number;
  target_value: number;
  buy_amount: number;
  buy_percent_of_investment: number;
}

export interface RebalanceResult {
  recommendations: BuyRecommendation[];
  investment_amount: number;
  total_buy_amount: number;
}

export interface ConfigSummary {
  categories: Category[];
  /** SYMBOL -> {category: weight 0-1}; direct mappings appear as {category: 1}. */
  assignments: Record<string, Record<string, number>>;
  exclusions: string[];
}

/** Body of an assignment change: split across categories, or exclude from allocation. */
export type AssignmentUpdate = { weights: Record<string, number> } | { excluded: true };
