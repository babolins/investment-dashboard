<script lang="ts">
  import { useManager } from "./managerContext";
  import CategoryTreeRow from "./CategoryTreeRow.svelte";
  import LevelHint from "./LevelHint.svelte";
  import RowEditor from "./RowEditor.svelte";
  import { FALLBACK_COLOR } from "../lib/categories";
  import type { TreeNode } from "../lib/hierarchy";

  let { node }: { node: TreeNode } = $props();

  const manager = useManager();

  const isParent = $derived(node.children.length > 0);
  const editing = $derived(manager.editing === node.name);
  const parent = $derived(
    manager.config.categories.find((c) => c.name === node.name)?.parent ?? "",
  );
  const showDrop = $derived(manager.dragged !== null && manager.canDropOn(node.name));

  async function onMove(e: Event & { currentTarget: HTMLSelectElement }) {
    const select = e.currentTarget;
    // An uncontrolled select would otherwise keep showing a move that did not happen.
    if (!(await manager.move(node.name, select.value || null))) select.value = parent;
  }
</script>

<li>
  <!-- Drop handlers sit on the row, not the <li>, so a drop on a child never reaches its ancestors. -->
  <div
    class={[
      "row",
      { "drop-ok": showDrop, "drop-over": showDrop && manager.overTarget === node.name },
    ]}
    class:dragging={manager.dragged === node.name}
    class:editing
    role="group"
    aria-label={node.name}
    draggable={!editing && !manager.busy}
    ondragstart={(e) => manager.startDrag(node.name, e)}
    ondragend={manager.endDrag}
    ondragover={(e) => manager.dragOver(e, node.name)}
    ondragleave={(e) => manager.dragLeave(e, node.name)}
    ondrop={(e) => manager.drop(e, node.name)}
  >
    <span class="name-cell">
      {#if isParent}
        <span class="parent-marker" aria-hidden="true">▾</span>
      {:else}
        <span class="dot" style:background={node.color ?? FALLBACK_COLOR} aria-hidden="true"></span>
      {/if}
      <strong class="name">{node.name}</strong>
      {#if isParent && !editing}
        <span class="sub">
          {node.children.length}
          {node.children.length === 1 ? "sub-category" : "sub-categories"}
        </span>
      {/if}
    </span>
    {#if !editing}
      <span class="symbol">
        {#if !isParent && node.buySymbol}<span class="symbol-pill">{node.buySymbol}</span>{/if}
      </span>
      <span class="target">{node.target === null ? "—" : `${node.target}%`}</span>
      <select
        aria-label="Move {node.name} to"
        data-move={node.name}
        value={parent}
        disabled={manager.busy}
        onchange={onMove}
      >
        <option value="">Top level</option>
        {#each manager.moveTargets(node.name) as t (t)}
          <option value={t}>{t}</option>
        {/each}
      </select>
      <span class="actions">
        <button
          type="button"
          class="btn-ghost"
          disabled={manager.busy}
          onclick={() => manager.startEdit(node.name)}
          aria-label="Edit {node.name}"
        >
          Edit
        </button>
        <button
          type="button"
          class="btn-ghost danger"
          disabled={manager.busy}
          onclick={() => manager.remove(node.name)}
          aria-label="Delete {node.name}"
        >
          Delete
        </button>
      </span>
    {/if}
  </div>
  <!-- The form stays outside the draggable row: Firefox can't select text in inputs inside one. -->
  {#if editing}
    <RowEditor {node} />
  {/if}
  {#if manager.rowError?.name === node.name}
    <p class="error-msg" role="alert">{manager.rowError.message}</p>
  {/if}
  {#if isParent}
    <ul class="tree">
      {#each node.children as child (child.name)}
        <CategoryTreeRow node={child} />
      {/each}
    </ul>
    <LevelHint label={node.name} nodes={node.children} />
  {/if}
</li>

<style>
  li {
    border-bottom: 1px solid #f0f1f4;
  }
  li:last-child {
    border-bottom: 0;
  }
  /* Nested levels: indented, with a thin guide line. */
  .tree {
    list-style: none;
    margin: 0 0 0.35rem 0.85rem;
    padding: 0 0 0 0.9rem;
    border-left: 1px solid var(--border);
  }
  .row {
    display: grid;
    grid-template-columns: var(--tree-columns);
    column-gap: var(--tree-gap);
    align-items: center;
    min-height: 2.75rem;
    padding: 0.2rem 0.5rem;
    border-radius: var(--radius-sm);
    cursor: grab;
  }
  .row:hover {
    background: var(--surface-muted);
  }
  .row.editing {
    cursor: default;
  }
  .row.dragging {
    opacity: 0.45;
  }
  .row.drop-ok {
    outline: 1px dashed var(--focus);
    outline-offset: -1px;
  }
  .row.drop-over {
    outline-style: solid;
    background: #eef4fc;
  }
  .name-cell {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    min-width: 0;
  }
  .name {
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub {
    color: var(--text-3);
    font-size: 0.78rem;
    white-space: nowrap;
  }
  .parent-marker {
    width: 0.65rem;
    color: var(--text-3);
    font-size: 0.75rem;
    text-align: center;
    flex: none;
  }
  .dot {
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 50%;
    flex: none;
  }
  .symbol-pill {
    display: inline-block;
    padding: 0.1rem 0.45rem;
    border-radius: 6px;
    background: #eef0f3;
    color: var(--text-2);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .target {
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: var(--text-2);
    font-size: 0.88rem;
  }
  select {
    height: 2rem;
    width: 100%;
    padding: 0 1.8rem 0 0.6rem;
    background-position: right 0.55rem center;
    border-color: transparent;
    background-color: #f1f2f5;
    font-size: 0.82rem;
    color: var(--text-2);
  }
  select:hover:not(:disabled) {
    border-color: var(--border-strong);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.15rem;
  }
  .danger:hover:not(:disabled) {
    background: var(--danger-bg);
    color: var(--danger);
  }
  @media (max-width: 640px) {
    .row {
      row-gap: 0.3rem;
      padding: 0.45rem 0.5rem;
    }
    .symbol {
      display: none;
    }
    select {
      grid-column: 1;
      max-width: 12rem;
    }
  }
</style>
