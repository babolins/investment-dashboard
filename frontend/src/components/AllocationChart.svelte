<script lang="ts">
  import type { AllocationBreakdown } from "../types";
  import { usd, formatPct } from "../lib/format";
  import { FALLBACK_COLOR } from "../lib/categories";

  interface Props {
    breakdown: AllocationBreakdown;
    colors: Record<string, string>;
    symbolsByCategory?: Record<string, string[]>;
  }

  let { breakdown, colors, symbolsByCategory = {} }: Props = $props();

  const colorOf = (name: string) => colors[name] ?? FALLBACK_COLOR;

  const CX = 110;
  const CY = 110;
  const INNER_R = 60;
  const OUTER_R = 100;
  // An arc whose start and end points coincide is degenerate and draws nothing, so a
  // lone 100% category is capped just under a full turn.
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
    const total = breakdown.categories.reduce((s, b) => s + b.current_value, 0);
    let angle = 0;
    return breakdown.categories.map((b) => {
      const sweep = total > 0 ? Math.min((b.current_value / total) * 360, MAX_SWEEP) : 0;
      const start = angle;
      angle += sweep;
      return { ...b, start, end: angle };
    });
  });

  const hoveredCategory = $derived(
    hovered ? breakdown.categories.find((b) => b.category === hovered) : undefined,
  );
  const tickers = $derived(hovered ? (symbolsByCategory[hovered] ?? []) : []);

  function track(e: MouseEvent) {
    const svg = (e.currentTarget as SVGElement).closest("svg")!;
    const r = svg.getBoundingClientRect();
    tip = { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function enter(e: MouseEvent, category: string) {
    hovered = category;
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
        {#each slices as s (s.category)}
          <path
            role="presentation"
            d={donutSlice(s.start, s.end)}
            fill={colorOf(s.category)}
            stroke="#fff"
            stroke-width="2"
            opacity={hovered && hovered !== s.category ? 0.6 : 1}
            style:cursor="pointer"
            onmouseenter={(e) => enter(e, s.category)}
            onmousemove={track}
          />
        {/each}
      </svg>

      {#if hoveredCategory && tip}
        <div
          class="chart-tooltip"
          style:position="absolute"
          style:left="{tip.x + 12}px"
          style:top="{tip.y - 10}px"
          style:pointer-events="none"
        >
          <strong>{hoveredCategory.category}</strong>
          <div>{usd.format(hoveredCategory.current_value)}</div>
          <div>{formatPct(hoveredCategory.percent_of_included)}</div>
          {#if tickers.length > 0}
            <div class="tooltip-tickers">{tickers.join(", ")}</div>
          {/if}
        </div>
      {/if}
    </div>

    <div class="chart-legend">
      {#each breakdown.categories as b (b.category)}
        <div class="legend-row">
          <span class="legend-dot" style:background={colorOf(b.category)}></span>
          <span class="legend-label">{b.category}</span>
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

  {#if breakdown.unassigned_value > 0}
    <p class="hint unassigned-note">
      {usd.format(breakdown.unassigned_value)} in unassigned securities not shown — assign them in Holdings.
    </p>
  {/if}
</div>
