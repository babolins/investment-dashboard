<script lang="ts">
  import type { TreeNode } from "../lib/hierarchy";
  import {
    parseTarget,
    validateName,
    validateSymbol,
    validateTarget,
  } from "../lib/categoryValidation";
  import { useManager, type Patch } from "./managerContext";

  let { node }: { node: TreeNode } = $props();

  const manager = useManager();
  const uid = $props.id();

  // Drafts start from the node as it was when editing began; the editor is remounted per edit.
  // svelte-ignore state_referenced_locally
  const original = node;
  let name = $state(original.name);
  let symbol = $state(original.buySymbol ?? "");
  let target = $state<number | null>(original.target);

  function submit(event: SubmitEvent) {
    event.preventDefault();
    const next = {
      name: name.trim(),
      buy_symbol: symbol.trim().toUpperCase(),
      target: parseTarget(target),
    };
    const invalid =
      validateName(next.name) ?? validateSymbol(next.buy_symbol) ?? validateTarget(next.target);
    if (invalid) return manager.fail(original.name, invalid);

    const patch: Patch = {};
    if (next.name !== original.name) patch.name = next.name;
    if (next.buy_symbol !== (original.buySymbol ?? "")) patch.buy_symbol = next.buy_symbol || null;
    if (next.target !== original.target) patch.target = next.target;
    if (Object.keys(patch).length === 0) return manager.cancelEdit();
    return manager.save(original.name, patch);
  }
</script>

<!-- novalidate: the validators give one consistent inline message instead of native bubbles. -->
<form class="edit" novalidate onsubmit={submit}>
  <span class="field wide">
    <span class="caption" aria-hidden="true">Name</span>
    <input aria-label="Name for {original.name}" bind:value={name} disabled={manager.busy} />
  </span>
  <span class="field">
    <span class="caption" aria-hidden="true">Buy symbol</span>
    <input
      aria-label="Buy symbol for {original.name}"
      aria-describedby="{uid}-symbol-hint"
      placeholder="Optional"
      bind:value={symbol}
      disabled={manager.busy}
    />
  </span>
  <span class="field">
    <span class="caption" aria-hidden="true">Default % of parent</span>
    <input
      aria-label="Default target for {original.name}"
      type="number"
      min="0"
      max="100"
      step="any"
      bind:value={target}
      disabled={manager.busy}
    />
  </span>
  <span class="buttons">
    <button type="submit" class="btn-primary" disabled={manager.busy}>Save</button>
    <button
      type="button"
      class="btn-secondary"
      disabled={manager.busy}
      onclick={manager.cancelEdit}
    >
      Cancel
    </button>
  </span>
  <span id="{uid}-symbol-hint" class="symbol-hint">Used when this category holds securities.</span>
</form>

<style>
  .edit {
    display: grid;
    grid-template-columns: minmax(10rem, 2fr) minmax(6rem, 1fr) minmax(7rem, 1fr) auto;
    gap: 0.4rem 0.75rem;
    align-items: end;
    margin: 0.25rem 0 0.6rem;
    padding: 0.85rem 1rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface-muted);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    min-width: 0;
  }
  .caption {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-2);
  }
  input {
    width: 100%;
  }
  .buttons {
    display: flex;
    gap: 0.5rem;
  }
  .symbol-hint {
    grid-column: 1 / -1;
    font-size: 0.75rem;
    color: var(--text-3);
  }
  @media (max-width: 640px) {
    .edit {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
