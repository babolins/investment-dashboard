<script lang="ts">
  import { targetTotal, validateTargets } from "../lib/targets";
  import { fetchRebalance } from "../services/api";
  import type { AllocationBreakdown, Category, RebalanceResult } from "../types";

  interface Props {
    allocation: AllocationBreakdown;
    categories: Category[];
    onResult: (result: RebalanceResult) => void;
  }

  let { allocation, categories, onResult }: Props = $props();

  let amount: number | null = $state(null);
  let loading = $state(false);
  let error: string | null = $state(null);

  // Only the user's edits are state; each target is `edits[name]` if present, else the
  // category's default. With no prefill effect there is nothing to clobber when categories
  // change identity, and new categories simply appear with their defaults.
  let edits = $state<Record<string, number | null>>({});
  const targets = $derived(
    Object.fromEntries(
      categories.map((c) => [c.name, c.name in edits ? edits[c.name] : c.target]),
    ) as Record<string, number | null>,
  );
  const targetError = $derived(validateTargets(targets));
  const total = $derived(targetTotal(targets));

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    error = null;

    if (!amount || amount <= 0) {
      error = "Enter a positive investment amount.";
      return;
    }
    if (targetError) {
      error = targetError;
      return;
    }

    loading = true;
    try {
      // Empty inputs count as 0.
      const target = Object.fromEntries(Object.entries(targets).map(([k, v]) => [k, v ?? 0]));
      onResult(await fetchRebalance(allocation, { investment_amount: amount, target }));
    } catch (err: unknown) {
      error = err instanceof Error ? err.message : "Unknown error";
    } finally {
      loading = false;
    }
  }
</script>

<div class="card rebalance-card">
  <h2>Rebalance Calculator</h2>
  <p class="hint">Set a target percentage for each category; they must add up to 100%.</p>

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

    <fieldset>
      <legend>Targets (%)</legend>
      <div class="alloc-inputs">
        {#each categories as c, i (c.name)}
          {@const id = `target-${i}`}
          <div class="alloc-row">
            <label for={id}>{c.name} ({c.buy_symbol})</label>
            <input
              {id}
              type="number"
              min="0"
              max="100"
              step="0.1"
              bind:value={() => targets[c.name], (v) => (edits[c.name] = v)}
            />
            <span>%</span>
          </div>
        {/each}
      </div>
      <p class="sum-indicator" class:ok={!targetError} class:err={targetError}>
        Total: {total.toFixed(1)}%
      </p>
    </fieldset>

    {#if error}
      <p class="error-msg" role="alert">{error}</p>
    {/if}

    <button type="submit" disabled={loading} class="btn-primary">
      {loading ? "Calculating…" : "Calculate Buy Guidance"}
    </button>
  </form>
</div>
