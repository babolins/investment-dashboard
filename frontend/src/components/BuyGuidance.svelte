<script lang="ts">
  import type { RebalanceResult } from "../types";
  import { usd, formatPct } from "../lib/format";
  import { bucketColor } from "../lib/buckets";

  let { result }: { result: RebalanceResult } = $props();

  // Post-trade allocation: current + buy per bucket, divided by the new total.
  const postAlloc = $derived.by(() => {
    const total = result.recommendations.reduce((s, r) => s + r.current_value + r.buy_amount, 0);
    return result.recommendations.map((r) => ({
      bucket: r.bucket,
      pct: total > 0 ? ((r.current_value + r.buy_amount) / total) * 100 : 0,
      targetPct: r.target_percent,
    }));
  });
</script>

<div class="card guidance-card">
  <h2>Buy Guidance</h2>
  <p class="hint">
    Total to invest: <strong>{usd.format(result.investment_amount)}</strong>
  </p>

  <div class="guidance-bars">
    {#each result.recommendations as r (r.bucket)}
      <div class="guidance-row">
        <div class="guidance-label">
          <span class="bucket-dot" style:background={bucketColor(r.bucket)}></span>
          <strong>{r.symbol}</strong>
          <span class="bucket-name">({r.bucket})</span>
        </div>

        <div class="guidance-bar-wrap">
          <div
            class="guidance-bar"
            style:width="{r.buy_percent_of_investment.toFixed(1)}%"
            style:background={bucketColor(r.bucket)}
          ></div>
        </div>

        <div class="guidance-amounts">
          <span class="buy-dollars">{usd.format(r.buy_amount)}</span>
          <span class="buy-pct">{formatPct(r.buy_percent_of_investment)} of investment</span>
        </div>

        <div class="guidance-context">
          <span>Current: {formatPct(r.current_percent)}</span>
          <span>Target: {formatPct(r.target_percent)}</span>
        </div>
      </div>
    {/each}
  </div>

  <div class="post-trade">
    <h3 class="post-trade-title">Post-trade Allocation</h3>
    <p class="hint">Resulting allocation after all buys are executed (includes value only).</p>
    <div class="post-trade-rows">
      {#each postAlloc as { bucket, pct, targetPct } (bucket)}
        <div class="post-trade-row">
          <span class="bucket-dot" style:background={bucketColor(bucket)}></span>
          <span class="post-trade-label">{bucket}</span>
          <div class="post-trade-bar-wrap">
            <div
              class="post-trade-bar"
              style:width="{pct.toFixed(1)}%"
              style:background={bucketColor(bucket)}
            ></div>
            <div
              class="post-trade-target-line"
              style:left="{targetPct.toFixed(1)}%"
              title="Target: {formatPct(targetPct)}"
            ></div>
          </div>
          <span class="post-trade-pct">{formatPct(pct)}</span>
          <span class="post-trade-target">target {formatPct(targetPct)}</span>
        </div>
      {/each}
    </div>
  </div>
</div>
