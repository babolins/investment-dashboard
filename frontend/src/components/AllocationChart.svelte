<script lang="ts">
  import type { AllocationBreakdown } from "../types";
  import { usd, formatPct } from "../lib/format";
  import { bucketColor } from "../lib/buckets";

  interface Props {
    breakdown: AllocationBreakdown;
    bucketSymbols?: Record<string, string[]>;
  }

  let { breakdown, bucketSymbols = {} }: Props = $props();

  const CX = 110;
  const CY = 110;
  const INNER_R = 60;
  const OUTER_R = 100;
  // An arc whose start and end points coincide is degenerate and draws nothing, so a
  // lone 100% bucket is capped just under a full turn.
  const MAX_SWEEP = 359.99;

  function polar(r: number, deg: number) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
  }

  function donutSlice(startDeg: number, endDeg: number): string {
    const s = polar(OUTER_R, startDeg);
    const e = polar(OUTER_R, endDeg);
    const si = polar(INNER_R, endDeg);
    const ei = polar(INNER_R, startDeg);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return [
      `M ${s.x} ${s.y}`,
      `A ${OUTER_R} ${OUTER_R} 0 ${large} 1 ${e.x} ${e.y}`,
      `L ${si.x} ${si.y}`,
      `A ${INNER_R} ${INNER_R} 0 ${large} 0 ${ei.x} ${ei.y}`,
      "Z",
    ].join(" ");
  }

  let hovered = $state<string | null>(null);
  let tip = $state<{ x: number; y: number } | null>(null);

  const slices = $derived.by(() => {
    const total = breakdown.buckets.reduce((s, b) => s + b.current_value, 0);
    let angle = 0;
    return breakdown.buckets.map((b) => {
      const sweep = total > 0 ? Math.min((b.current_value / total) * 360, MAX_SWEEP) : 0;
      const start = angle;
      angle += sweep;
      return { ...b, start, end: angle };
    });
  });

  const hoveredBucket = $derived(
    hovered ? breakdown.buckets.find((b) => b.bucket === hovered) : undefined,
  );
  const tickers = $derived(hovered ? (bucketSymbols[hovered] ?? []) : []);

  function track(e: MouseEvent) {
    const svg = (e.currentTarget as SVGElement).closest("svg")!;
    const r = svg.getBoundingClientRect();
    tip = { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function enter(e: MouseEvent, bucket: string) {
    hovered = bucket;
    track(e);
  }

  function leave() {
    hovered = null;
    tip = null;
  }
</script>

<div class="card allocation-card">
  <h2>Asset Allocation</h2>
  <p class="hint">As of today · included value {usd.format(breakdown.included_value)}</p>

  <div class="chart-layout">
    <div style:position="relative" style:width="220px" style:height="220px">
      <!-- Presentational: the legend carries the same data for keyboard/screen-reader users. -->
      <svg width={220} height={220} role="presentation" onmouseleave={leave}>
        {#each slices as s (s.bucket)}
          <path
            role="presentation"
            d={donutSlice(s.start, s.end)}
            fill={bucketColor(s.bucket)}
            stroke="#fff"
            stroke-width="2"
            opacity={hovered && hovered !== s.bucket ? 0.6 : 1}
            style:cursor="pointer"
            onmouseenter={(e) => enter(e, s.bucket)}
            onmousemove={track}
          />
        {/each}
      </svg>

      {#if hoveredBucket && tip}
        <div
          class="chart-tooltip"
          style:position="absolute"
          style:left="{tip.x + 12}px"
          style:top="{tip.y - 10}px"
          style:pointer-events="none"
        >
          <strong>{hoveredBucket.bucket}</strong>
          <div>{usd.format(hoveredBucket.current_value)}</div>
          <div>{formatPct(hoveredBucket.percent_of_included)}</div>
          {#if tickers.length > 0}
            <div class="tooltip-tickers">{tickers.join(", ")}</div>
          {/if}
        </div>
      {/if}
    </div>

    <div class="chart-legend">
      {#each breakdown.buckets as b (b.bucket)}
        <div class="legend-row">
          <span class="legend-dot" style:background={bucketColor(b.bucket)}></span>
          <span class="legend-label">{b.bucket}</span>
          <span class="legend-pct">{formatPct(b.percent_of_included)}</span>
        </div>
      {/each}
    </div>
  </div>

  {#if breakdown.excluded_value > 0}
    <p class="hint excluded-note">
      {usd.format(breakdown.excluded_value)} in excluded symbols (cash / money-market) not shown.
    </p>
  {/if}
</div>
