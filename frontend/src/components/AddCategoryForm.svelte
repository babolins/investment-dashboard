<script lang="ts">
  import { createCategory } from "../services/api";
  import {
    duplicateName,
    parseTarget,
    validateName,
    validateSymbol,
    validateTarget,
  } from "../lib/categoryValidation";
  import type { ConfigSummary } from "../types";

  interface Props {
    config: ConfigSummary;
    /** Categories that can hold others: every category except leaves holding securities. */
    parents: string[];
    onChange: (config: ConfigSummary) => void;
  }

  let { config, parents, onChange }: Props = $props();

  const uid = $props.id();

  let name = $state("");
  let symbol = $state("");
  let parent = $state("");
  let target = $state<number | null>(null);
  let error = $state<string | null>(null);
  let adding = $state(false);

  async function add(event: SubmitEvent) {
    event.preventDefault();
    const input = {
      name: name.trim(),
      buy_symbol: symbol.trim().toUpperCase() || null,
      target: parseTarget(target),
      parent: parent || null,
    };
    // Only for add: a rename's collisions are left to the server (case-only renames are legal).
    error =
      validateName(input.name) ??
      duplicateName(config, input.name) ??
      validateSymbol(input.buy_symbol ?? "") ??
      validateTarget(input.target);
    if (error) return;
    adding = true;
    try {
      onChange(await createCategory(input));
      name = "";
      symbol = "";
      target = null;
    } catch (err) {
      error = err instanceof Error ? err.message : "Could not add category";
    } finally {
      adding = false;
    }
  }
</script>

<form class="add" novalidate onsubmit={add} aria-label="Add category">
  <div class="field">
    <label for="{uid}-name">Name</label>
    <input id="{uid}-name" bind:value={name} disabled={adding} />
  </div>
  <div class="field">
    <label for="{uid}-symbol">Buy symbol</label>
    <input
      id="{uid}-symbol"
      class="short"
      placeholder="Optional"
      bind:value={symbol}
      disabled={adding}
    />
  </div>
  <div class="field">
    <label for="{uid}-parent">Inside</label>
    <select id="{uid}-parent" bind:value={parent} disabled={adding}>
      <option value="">Top level</option>
      {#each parents as p (p)}
        <option value={p}>{p}</option>
      {/each}
    </select>
  </div>
  <div class="field">
    <label for="{uid}-target">Default % of parent</label>
    <input
      id="{uid}-target"
      class="short"
      type="number"
      min="0"
      max="100"
      step="any"
      bind:value={target}
      disabled={adding}
    />
  </div>
  <button type="submit" class="btn-primary" disabled={adding}>Add category</button>
  {#if error}
    <p class="error-msg" role="alert">{error}</p>
  {/if}
</form>

<style>
  .add {
    display: flex;
    align-items: flex-end;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-top: 0.75rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .field label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #333;
  }
  input,
  select {
    padding: 0.4rem 0.6rem;
    border: 1px solid #ccc;
    border-radius: 6px;
    font-size: 0.9rem;
  }
  input.short {
    width: 6.5rem;
  }
  .error-msg {
    flex-basis: 100%;
    margin: 0;
  }
</style>
