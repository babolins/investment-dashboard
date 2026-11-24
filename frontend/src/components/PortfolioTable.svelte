<script lang="ts">
  import type { ConfigSummary, HoldingRow } from "../types";
  import AssignmentPill from "./AssignmentPill.svelte";
  import { usd, formatPct, formatGain } from "../lib/format";

  interface Props {
    holdings: HoldingRow[];
    totalValue: number;
    config: ConfigSummary | null;
    onConfigChange: (config: ConfigSummary) => void;
  }

  type SortKey = keyof HoldingRow;
  type SortDir = "asc" | "desc";

  let { holdings, totalValue, config, onConfigChange }: Props = $props();

  let sortKey = $state<SortKey>("current_value");
  let sortDir = $state<SortDir>("desc");

  // The Category column sits between Symbol and Description and is not sortable.
  const columns: { key: SortKey | null; label: string }[] = [
    { key: "symbol", label: "Symbol" },
    { key: null, label: "Category" },
    { key: "description", label: "Description" },
    { key: "quantity", label: "Quantity" },
    { key: "current_value", label: "Current Value" },
    { key: "total_gain_loss", label: "Total Gain/Loss" },
    { key: "percent_of_account", label: "% of Account" },
  ];

  function compare(a: HoldingRow, b: HoldingRow): number {
    // Nulls sort as the lowest value; comparing explicitly keeps two nulls equal
    // (-Infinity - -Infinity would be NaN).
    const av = a[sortKey] ?? -Infinity;
    const bv = b[sortKey] ?? -Infinity;
    let cmp: number;
    if (typeof av === "string" && typeof bv === "string") cmp = av.localeCompare(bv);
    else cmp = av === bv ? 0 : (av as number) < (bv as number) ? -1 : 1;
    return sortDir === "asc" ? cmp : -cmp;
  }

  // Sort a copy: the holdings prop must not be mutated.
  const sorted = $derived([...holdings].sort(compare));

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortKey = key;
      sortDir = "desc";
    }
  }

  const arrow = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "");
  const ariaSort = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none";
</script>

<div class="card">
  <h2>Holdings</h2>
  <p class="hint">Total portfolio value: <strong>{usd.format(totalValue)}</strong></p>
  <div class="table-wrapper">
    <table class="holdings-table">
      <thead>
        <tr>
          {#each columns as { key, label } (label)}
            {#if key}
              <th aria-sort={ariaSort(key)}>
                <button type="button" onclick={() => toggleSort(key)}>{label}{arrow(key)}</button>
              </th>
            {:else}
              <th>{label}</th>
            {/if}
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each sorted as h (h.symbol)}
          <tr>
            <td class="symbol">{h.symbol}</td>
            <td>
              {#if config}
                <AssignmentPill symbol={h.symbol} {config} onChange={onConfigChange} />
              {:else}
                —
              {/if}
            </td>
            <td class="desc">{h.description}</td>
            <td class="num">{h.quantity.toLocaleString()}</td>
            <td class="num">{usd.format(h.current_value)}</td>
            <td
              class={[
                "num",
                h.total_gain_loss !== null && (h.total_gain_loss >= 0 ? "gain" : "loss"),
              ]}
            >
              {formatGain(h.total_gain_loss)}
            </td>
            <td class="num">{formatPct(h.percent_of_account, 2)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  /* Sortable headers are real buttons for keyboard access; make them look like the bare th text. */
  .holdings-table th button {
    font: inherit;
    color: inherit;
    text-transform: inherit;
    letter-spacing: inherit;
    background: none;
    border: 0;
    padding: 0;
    text-align: inherit;
    cursor: pointer;
    white-space: nowrap;
  }
  .holdings-table th button:focus-visible {
    outline: 2px solid #1b3a6b;
    outline-offset: 2px;
  }
</style>
