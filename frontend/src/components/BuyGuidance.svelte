<script lang="ts">
  import type { RebalanceResult } from "../types";
  import { usd, formatPct } from "../lib/format";
  import { FALLBACK_COLOR } from "../lib/categories";

  let { result, colors }: { result: RebalanceResult; colors: Record<string, string> } = $props();

  const colorOf = (name: string) => colors[name] ?? FALLBACK_COLOR;

  // Post-trade allocation: current + buy per category, divided by the new total.
  const postAlloc = $derived.by(() => {
    const total = result.recommendations.reduce((s, r) => s + r.current_value + r.buy_amount, 0);
    return result.recommendations.map((r) => ({
      category: r.category,
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
    {#each result.recommendations as r (r.category)}
      <div class="guidance-row">
        <div class="guidance-label">
          <span class="bucket-dot" style:background={colorOf(r.category)}></span>
          <strong>{r.symbol}</strong>
          <span class="bucket-name">({r.category})</span>
        </div>

        <div class="guidance-bar-wrap">
          <div
            class="guidance-bar"
            style:width="{r.buy_percent_of_investment.toFixed(1)}%"
            style:background={colorOf(r.category)}
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
      {#each postAlloc as { category, pct, targetPct } (category)}
        <div class="post-trade-row">
          <span class="bucket-dot" style:background={colorOf(category)}></span>
          <span class="post-trade-label">{category}</span>
          <div class="post-trade-bar-wrap">
            <div
              class="post-trade-bar"
              style:width="{pct.toFixed(1)}%"
              style:background={colorOf(category)}
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
