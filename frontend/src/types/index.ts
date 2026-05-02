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

export interface AllocationBucket {
  bucket: "VTI" | "VXUS" | "BND";
  current_value: number;
  percent_of_included: number;
}

export interface AllocationBreakdown {
  buckets: AllocationBucket[];
  included_value: number;
  excluded_value: number;
  total_value: number;
}

export interface UploadResponse {
  portfolio: PortfolioSnapshot;
  allocation: AllocationBreakdown;
}

export interface TargetAllocation {
  vti: number;
  vxus: number;
  bnd: number;
}

export interface RebalanceRequest {
  investment_amount: number;
  target: TargetAllocation;
}

export interface BuyRecommendation {
  bucket: string;
  symbol: string;
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
  direct_mappings: Record<string, string>;
  fractional_mappings: Record<string, Record<string, number>>;
  exclusions: string[];
  primary_symbols: Record<string, string>;
  default_target: TargetAllocation | null;
}
