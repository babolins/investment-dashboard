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
  <p class="title">Add a category</p>
  <div class="field">
    <label for="{uid}-name">Name</label>
    <input id="{uid}-name" placeholder="e.g. US Stocks" bind:value={name} disabled={adding} />
  </div>
  <div class="field">
    <label for="{uid}-symbol">Buy symbol</label>
    <input id="{uid}-symbol" placeholder="Optional" bind:value={symbol} disabled={adding} />
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
    display: grid;
    grid-template-columns:
      minmax(10rem, 2fr) minmax(6rem, 1fr) minmax(8rem, 1.2fr) minmax(7rem, 1fr)
      auto;
    gap: 0.75rem;
    align-items: end;
    margin-top: 1rem;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface-muted);
  }
  .title {
    grid-column: 1 / -1;
    font-size: 0.85rem;
    font-weight: 650;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    min-width: 0;
  }
  .field label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-2);
  }
  input,
  select {
    width: 100%;
  }
  .error-msg {
    grid-column: 1 / -1;
    margin: 0;
  }
  @media (max-width: 720px) {
    .add {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
  }
</style>
