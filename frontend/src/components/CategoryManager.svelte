<script lang="ts">
  import { createCategory, deleteCategory, updateCategory } from "../services/api";
  import { targetTotal } from "../lib/targets";
  import type { CategoryInput, ConfigSummary } from "../types";

  interface Props {
    config: ConfigSummary;
    onChange: (config: ConfigSummary) => void;
  }

  let { config, onChange }: Props = $props();

  const MAX_CATEGORIES = 8;
  const RESERVED = ["excluded", "unassigned"];

  const uid = $props.id();

  // Mirrors the server's rules for quick feedback; the server stays authoritative.
  function validate(name: string, symbol: string, target: number | null): string | null {
    if (!name) return "Enter a category name.";
    if (name.length > 40) return "Name must be at most 40 characters.";
    if (name.includes("/")) return 'Name must not contain "/".';
    if (RESERVED.includes(name.toLowerCase())) return `"${name}" is a reserved name.`;
    if (!/^[A-Z0-9.-]{1,10}$/.test(symbol)) {
      return "Buy symbol must be 1-10 letters, digits, dots or dashes.";
    }
    if (target !== null && !(target >= 0 && target <= 100)) {
      return "Default target must be between 0 and 100.";
    }
    return null;
  }

  /** An empty number input binds to null. */
  const parseTarget = (value: number | null) => (value === null ? null : Number(value));

  const total = $derived(
    targetTotal(Object.fromEntries(config.categories.map((c) => [c.name, c.target]))),
  );
  const totalOk = $derived(Math.abs(total - 100) < 0.01);
  const full = $derived(config.categories.length >= MAX_CATEGORIES);

  // Add form
  let newName = $state("");
  let newSymbol = $state("");
  let newTarget = $state<number | null>(null);
  let addError = $state<string | null>(null);
  let adding = $state(false);

  async function add(event: SubmitEvent) {
    event.preventDefault();
    const input: CategoryInput = {
      name: newName.trim(),
      buy_symbol: newSymbol.trim().toUpperCase(),
      target: parseTarget(newTarget),
    };
    const lower = input.name.toLowerCase();
    // Only for add: a rename's collisions are left to the server (case-only renames are legal).
    const duplicate = config.categories.some((c) => c.name.toLowerCase() === lower);
    addError = duplicate
      ? `A category named "${input.name}" already exists.`
      : validate(input.name, input.buy_symbol, input.target);
    if (addError) return;
    adding = true;
    try {
      onChange(await createCategory(input));
      newName = "";
      newSymbol = "";
      newTarget = null;
    } catch (err) {
      addError = err instanceof Error ? err.message : "Could not add category";
    } finally {
      adding = false;
    }
  }

  // Row editor: one row at a time, keyed by the category's original name.
  let editing = $state<string | null>(null);
  let draftName = $state("");
  let draftSymbol = $state("");
  let draftTarget = $state<number | null>(null);
  let busy = $state(false);
  let rowError = $state<{ name: string; message: string } | null>(null);

  function startEdit(name: string) {
    const c = config.categories.find((cat) => cat.name === name);
    if (!c) return;
    editing = name;
    draftName = c.name;
    draftSymbol = c.buy_symbol;
    draftTarget = c.target;
    rowError = null;
  }

  function cancelEdit() {
    editing = null;
    rowError = null;
  }

  async function saveEdit(event: SubmitEvent, name: string) {
    event.preventDefault();
    const original = config.categories.find((c) => c.name === name);
    if (!original) return;
    const next: CategoryInput = {
      name: draftName.trim(),
      buy_symbol: draftSymbol.trim().toUpperCase(),
      target: parseTarget(draftTarget),
    };
    const invalid = validate(next.name, next.buy_symbol, next.target);
    if (invalid) {
      rowError = { name, message: invalid };
      return;
    }
    const patch: Partial<CategoryInput> = {};
    if (next.name !== original.name) patch.name = next.name;
    if (next.buy_symbol !== original.buy_symbol) patch.buy_symbol = next.buy_symbol;
    if (next.target !== original.target) patch.target = next.target;
    if (Object.keys(patch).length === 0) return cancelEdit();

    await run(name, async () => {
      onChange(await updateCategory(name, patch));
      editing = null;
    });
  }

  async function remove(name: string) {
    await run(name, async () => onChange(await deleteCategory(name)));
  }

  async function run(name: string, action: () => Promise<void>) {
    busy = true;
    rowError = null;
    try {
      await action();
    } catch (err) {
      rowError = { name, message: err instanceof Error ? err.message : "Request failed" };
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h2>Categories</h2>
  <p class="hint">
    Group your holdings into categories, then assign each holding in the table below.
  </p>

  {#if config.categories.length > 0}
    <ul class="cat-list">
      {#each config.categories as c (c.name)}
        <li>
          <div class="row">
            <span class="dot" style:background={c.color} aria-hidden="true"></span>
            <strong class="name">{c.name}</strong>
            {#if editing !== c.name}
              <span class="meta">{c.buy_symbol}</span>
              <span class="meta">{c.target === null ? "—" : `${c.target}%`}</span>
              <button
                type="button"
                class="secondary"
                disabled={busy}
                onclick={() => startEdit(c.name)}
                aria-label="Edit {c.name}"
              >
                Edit
              </button>
              <button
                type="button"
                class="secondary"
                disabled={busy}
                onclick={() => remove(c.name)}
                aria-label="Delete {c.name}"
              >
                Delete
              </button>
            {/if}
          </div>
          {#if editing === c.name}
            <!-- novalidate: validate() gives one consistent inline message instead of native bubbles. -->
            <form class="row edit" novalidate onsubmit={(e) => saveEdit(e, c.name)}>
              <input aria-label="Name for {c.name}" bind:value={draftName} disabled={busy} />
              <input
                aria-label="Buy symbol for {c.name}"
                class="short"
                bind:value={draftSymbol}
                disabled={busy}
              />
              <input
                aria-label="Default target for {c.name}"
                class="short"
                type="number"
                min="0"
                max="100"
                step="any"
                bind:value={draftTarget}
                disabled={busy}
              />
              <button type="submit" class="btn-primary" disabled={busy}>Save</button>
              <button type="button" class="secondary" disabled={busy} onclick={cancelEdit}>
                Cancel
              </button>
            </form>
          {/if}
          {#if rowError?.name === c.name}
            <p class="error-msg" role="alert">{rowError.message}</p>
          {/if}
        </li>
      {/each}
    </ul>
    <p class={["sum-indicator", totalOk ? "ok" : "err"]}>
      {#if totalOk}
        Default targets total 100%
      {:else}
        Default targets total {+total.toFixed(2)}% (not 100%) — you can still set targets in the
        rebalance form
      {/if}
    </p>
  {/if}

  <form class="add" novalidate onsubmit={add} aria-label="Add category">
    <div class="field">
      <label for="{uid}-name">Name</label>
      <input id="{uid}-name" bind:value={newName} disabled={full || adding} />
    </div>
    <div class="field">
      <label for="{uid}-symbol">Buy symbol</label>
      <input id="{uid}-symbol" class="short" bind:value={newSymbol} disabled={full || adding} />
    </div>
    <div class="field">
      <label for="{uid}-target">Default target (%)</label>
      <input
        id="{uid}-target"
        class="short"
        type="number"
        min="0"
        max="100"
        step="any"
        bind:value={newTarget}
        disabled={full || adding}
      />
    </div>
    <button type="submit" class="btn-primary" disabled={full || adding}>Add category</button>
  </form>
  {#if full}
    <p class="hint">Maximum of {MAX_CATEGORIES} categories reached.</p>
  {/if}
  {#if addError}
    <p class="error-msg" role="alert">{addError}</p>
  {/if}
</div>

<style>
  .cat-list {
    list-style: none;
    margin: 0 0 0.5rem;
    padding: 0;
  }
  .cat-list li {
    padding: 0.4rem 0;
    border-bottom: 1px solid #eef0f4;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .name {
    min-width: 8rem;
  }
  .meta {
    min-width: 3.5rem;
    color: #555;
    font-size: 0.9rem;
  }
  .dot {
    width: 0.8rem;
    height: 0.8rem;
    border-radius: 50%;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
    flex: none;
  }
  .edit {
    margin-top: 0.4rem;
  }
  input {
    padding: 0.4rem 0.6rem;
    border: 1px solid #ccc;
    border-radius: 6px;
    font-size: 0.9rem;
  }
  input.short {
    width: 6.5rem;
  }
  .secondary {
    padding: 0.3rem 0.7rem;
    border: 1px solid #ccc;
    border-radius: 7px;
    background: #fff;
    color: #1a1a2e;
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .secondary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .secondary:focus-visible {
    outline: 2px solid #1b3a6b;
    outline-offset: 2px;
  }
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
</style>
