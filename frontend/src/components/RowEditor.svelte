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
  <input aria-label="Name for {original.name}" bind:value={name} disabled={manager.busy} />
  <input
    aria-label="Buy symbol for {original.name}"
    aria-describedby="{uid}-symbol-hint"
    class="short"
    bind:value={symbol}
    disabled={manager.busy}
  />
  <span id="{uid}-symbol-hint" class="hint">Used when this category holds securities.</span>
  <input
    aria-label="Default target for {original.name}"
    class="short"
    type="number"
    min="0"
    max="100"
    step="any"
    bind:value={target}
    disabled={manager.busy}
  />
  <button type="submit" class="btn-primary" disabled={manager.busy}>Save</button>
  <button type="button" class="secondary" disabled={manager.busy} onclick={manager.cancelEdit}>
    Cancel
  </button>
</form>

<style>
  .edit {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
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
</style>
