<script lang="ts">
  import {
    buildTree,
    defaultShares,
    leafTargets,
    portfolioPercents,
    siblingErrors,
    withPairFill,
    type TreeNode,
  } from "../lib/hierarchy";
  import { formatPct } from "../lib/format";
  import { fetchRebalance } from "../services/api";
  import type { AllocationBreakdown, ConfigSummary, RebalanceResult } from "../types";

  interface Props {
    allocation: AllocationBreakdown;
    config: ConfigSummary;
    onResult: (result: RebalanceResult) => void;
  }

  let { allocation, config, onResult }: Props = $props();

  let amount: number | null = $state(null);
  let loading = $state(false);
  let error: string | null = $state(null);

  // State design: only the user's edits are state (node name -> "% of parent"); each share is
  // `edits[name]` if present, else the node's configured default. With no prefill effect there is
  // nothing to clobber when the config changes identity, and new nodes simply appear with their
  // defaults. Edits are keyed by name, so a moved node keeps its edit (now read as % of its new
  // parent). Pair fill writes only the sibling it actually changed, so untouched rows keep
  // following their defaults.
  let edits = $state<Record<string, number | null>>({});
  const tree = $derived(buildTree(config));
  const shares = $derived({ ...defaultShares(tree), ...edits });
  const percents = $derived(portfolioPercents(tree, shares));
  const errors = $derived(siblingErrors(tree, shares));

  // Ids are built from positions, never names (names contain spaces; aria-describedby is a list).
  const indexes = $derived.by(() => {
    const map: Record<string, number> = {};
    const visit = (nodes: TreeNode[]) => {
      for (const n of nodes) {
        map[n.name] = Object.keys(map).length;
        if (n.children.length > 0) visit(n.children);
      }
    };
    visit(tree);
    return map;
  });

  function setShare(name: string, value: number | null) {
    const next = withPairFill(tree, shares, name, value);
    edits[name] = value;
    for (const key in next) if (key !== name && next[key] !== shares[key]) edits[key] = next[key];
  }

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    error = null;

    if (!amount || amount <= 0) {
      error = "Enter a positive investment amount.";
      return;
    }
    const levelErrors = Object.values(errors);
    if (levelErrors.length > 0) {
      error = levelErrors[0];
      return;
    }

    loading = true;
    try {
      // Whole-portfolio % per category; empty inputs count as 0.
      const target = leafTargets(tree, shares);
      onResult(await fetchRebalance(allocation, { investment_amount: amount, target }));
    } catch (err: unknown) {
      error = err instanceof Error ? err.message : "Unknown error";
    } finally {
      loading = false;
    }
  }
</script>

{#snippet level(nodes: TreeNode[], parent: string | null)}
  {@const key = parent ?? ""}
  {@const errId = `level-error-${parent === null ? "top" : indexes[parent]}`}
  {#each nodes as n (n.name)}
    {@const id = `target-${indexes[n.name]}`}
    <div class="alloc-node">
      <div class="alloc-row" class:alloc-row-parent={n.children.length > 0}>
        <label for={id}><strong>{n.name}</strong> % of <span>{parent ?? "portfolio"}</span></label>
        <input
          {id}
          type="number"
          min="0"
          max="100"
          step="0.1"
          aria-invalid={errors[key] ? "true" : undefined}
          aria-describedby={errors[key] ? errId : undefined}
          bind:value={() => shares[n.name], (v) => setShare(n.name, v)}
        />
        <span>%</span>
        {#if n.children.length === 0 && n.buySymbol}
          <span class="alloc-symbol">{n.buySymbol}</span>
        {/if}
        {#if parent !== null}
          <span class="alloc-readout">= {formatPct(percents[n.name])} of portfolio</span>
        {/if}
      </div>
      {#if n.children.length > 0}
        <div class="alloc-children" role="group" aria-label={n.name}>
          {@render level(n.children, n.name)}
        </div>
      {/if}
    </div>
  {/each}
  {#if errors[key]}
    <p class="sum-indicator err" id={errId}>{errors[key]}</p>
  {/if}
{/snippet}

<div class="card rebalance-card">
  <h2>Rebalance Calculator</h2>
  {#if tree.length === 0}
    <p class="hint">Add a category to set targets.</p>
  {:else}
    <p class="hint">Each level's percentages are of its parent and must add up to 100%.</p>
  {/if}

  <!-- novalidate: show our inline messages instead of the browser's validation bubbles. -->
  <form onsubmit={handleSubmit} class="rebalance-form" novalidate>
    <div class="form-row">
      <label for="investment-amount">Investment Amount ($)</label>
      <input
        id="investment-amount"
        type="number"
        min="0.01"
        step="0.01"
        placeholder="e.g. 5000"
        bind:value={amount}
        required
      />
    </div>

    {#if tree.length > 0}
      <fieldset>
        <legend>Targets (%)</legend>
        <div class="alloc-inputs">
          {@render level(tree, null)}
        </div>
      </fieldset>
    {/if}

    {#if error}
      <p class="error-msg" role="alert">{error}</p>
    {/if}

    {#if tree.length > 0}
      <button type="submit" disabled={loading} class="btn-primary">
        {loading ? "Calculating…" : "Calculate Buy Guidance"}
      </button>
    {/if}
  </form>
</div>

<style>
  .alloc-children {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin: 0.5rem 0 0 1.25rem;
    padding-left: 0.75rem;
    border-left: 2px solid #e0e0e0;
  }
  .alloc-row-parent > label {
    font-weight: 700;
  }
  .alloc-symbol {
    font-size: 0.78rem;
    color: #777;
  }
  .alloc-readout {
    min-width: 9.5rem;
    font-size: 0.78rem;
    color: #666;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
</style>
