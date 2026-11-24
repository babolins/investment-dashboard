<script lang="ts">
  import { deriveTargets, inputsFromTarget } from "../lib/targets";
  import { fetchRebalance } from "../services/api";
  import type { AllocationBreakdown, RebalanceResult, TargetAllocation } from "../types";

  interface Props {
    allocation: AllocationBreakdown;
    defaultTarget: TargetAllocation | null;
    onResult: (result: RebalanceResult) => void;
  }

  let { allocation, defaultTarget, onResult }: Props = $props();

  let amount: number | null = $state(null);
  let bnd: number | null = $state(null);
  let vxusOfStocks: number | null = $state(null);
  let loading = $state(false);
  let error: string | null = $state(null);

  // Prefill when the default target loads or changes. The effect only depends on `target`
  // (assigning bnd/vxusOfStocks adds no dependency), so user edits are never overwritten.
  // The $derived hop matters: it only notifies when the object identity changes, so
  // re-renders that touch other props (or reassign the whole props object) don't re-prefill.
  const target = $derived(defaultTarget);
  $effect(() => {
    if (target) ({ bnd, vxusOfStocks } = inputsFromTarget(target));
  });

  const targets = $derived(deriveTargets({ bnd, vxusOfStocks }));

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    error = null;

    if (!amount || amount <= 0) {
      error = "Enter a positive investment amount.";
      return;
    }
    if (targets.error) {
      error = targets.error;
      return;
    }

    loading = true;
    try {
      const { vti, vxus, bnd: bndTarget } = targets;
      onResult(
        await fetchRebalance(allocation, {
          investment_amount: amount,
          target: { vti, vxus, bnd: bndTarget },
        }),
      );
    } catch (err: unknown) {
      error = err instanceof Error ? err.message : "Unknown error";
    } finally {
      loading = false;
    }
  }
</script>

<div class="card rebalance-card">
  <h2>Rebalance Calculator</h2>
  <p class="hint">Enter BND as a whole-portfolio target, then VXUS as a share of stocks.</p>

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
      <legend>Inputs (%)</legend>
      <div class="alloc-inputs">
        <div class="alloc-row">
          <label for="bnd-target">BND (of total portfolio)</label>
          <input
            id="bnd-target"
            type="number"
            min="0"
            max="100"
            step="0.1"
            bind:value={bnd}
            required
          />
          <span>%</span>
        </div>
        <div class="alloc-row">
          <label for="vxus-target">VXUS (of stocks only)</label>
          <input
            id="vxus-target"
            type="number"
            min="0"
            max="100"
            step="0.1"
            bind:value={vxusOfStocks}
            required
          />
          <span>%</span>
        </div>
      </div>
      <p class="sum-indicator" class:ok={!targets.error} class:err={targets.error}>
        {`Derived Targets: VTI ${targets.vti.toFixed(1)}% · VXUS ${targets.vxus.toFixed(1)}% · BND ${targets.bnd.toFixed(1)}%`}
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
