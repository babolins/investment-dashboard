import type { RebalanceResult } from "../types";

interface Props {
  result: RebalanceResult;
}

const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

const BUCKET_COLORS: Record<string, string> = {
  VTI: "#1B3A6B",
  VXUS: "#4AACE8",
  BND: "#6B7A23",
};

export default function BuyGuidance({ result }: Props) {
  const { recommendations, investment_amount, total_buy_amount } = result;

  // Post-trade allocation: current + buy per bucket, divided by new total
  const postTotal = recommendations.reduce((s, r) => s + r.current_value + r.buy_amount, 0);
  const postAlloc = recommendations.map((r) => ({
    bucket: r.bucket,
    pct: postTotal > 0 ? ((r.current_value + r.buy_amount) / postTotal) * 100 : 0,
    targetPct: r.target_percent,
  }));

  return (
    <div className="card guidance-card">
      <h2>Buy Guidance</h2>
      <p className="hint">
        Total to invest: <strong>{fmt.format(investment_amount)}</strong>
      </p>

      <div className="guidance-bars">
        {recommendations.map((r) => (
          <div key={r.bucket} className="guidance-row">
            <div className="guidance-label">
              <span className="bucket-dot" style={{ background: BUCKET_COLORS[r.bucket] ?? "#999" }} />
              <strong>{r.symbol}</strong>
              <span className="bucket-name">({r.bucket})</span>
            </div>

            <div className="guidance-bar-wrap">
              <div
                className="guidance-bar"
                style={{
                  width: `${r.buy_percent_of_investment.toFixed(1)}%`,
                  background: BUCKET_COLORS[r.bucket] ?? "#999",
                }}
              />
            </div>

            <div className="guidance-amounts">
              <span className="buy-dollars">{fmt.format(r.buy_amount)}</span>
              <span className="buy-pct">{r.buy_percent_of_investment.toFixed(1)}% of investment</span>
            </div>

            <div className="guidance-context">
              <span>Current: {r.current_percent.toFixed(1)}%</span>
              <span>Target: {r.target_percent.toFixed(1)}%</span>
            </div>
          </div>
        ))}
      </div>

      {Math.abs(total_buy_amount - investment_amount) > 0.02 && (
        <p className="error-msg">
          Note: buy total ({fmt.format(total_buy_amount)}) differs from investment amount due
          to rounding. One bucket is overweight and absorbs less than a full share.
        </p>
      )}

      <div className="post-trade">
        <h3 className="post-trade-title">Post-trade Allocation</h3>
        <p className="hint">Resulting allocation after all buys are executed (includes value only).</p>
        <div className="post-trade-rows">
          {postAlloc.map(({ bucket, pct, targetPct }) => (
            <div key={bucket} className="post-trade-row">
              <span className="bucket-dot" style={{ background: BUCKET_COLORS[bucket] ?? "#999" }} />
              <span className="post-trade-label">{bucket}</span>
              <div className="post-trade-bar-wrap">
                <div
                  className="post-trade-bar"
                  style={{ width: `${pct.toFixed(1)}%`, background: BUCKET_COLORS[bucket] ?? "#999" }}
                />
                <div
                  className="post-trade-target-line"
                  style={{ left: `${targetPct.toFixed(1)}%` }}
                  title={`Target: ${targetPct.toFixed(1)}%`}
                />
              </div>
              <span className="post-trade-pct">{pct.toFixed(1)}%</span>
              <span className="post-trade-target">target {targetPct.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
