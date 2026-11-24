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
    role="group"
    aria-label={node.name}
    draggable={!editing && !manager.busy}
    ondragstart={(e) => manager.startDrag(node.name, e)}
    ondragend={manager.endDrag}
    ondragover={(e) => manager.dragOver(e, node.name)}
    ondragleave={(e) => manager.dragLeave(e, node.name)}
    ondrop={(e) => manager.drop(e, node.name)}
  >
    {#if isParent}
      <span class="parent-marker" aria-hidden="true">▸</span>
    {:else}
      <span class="dot" style:background={node.color ?? FALLBACK_COLOR} aria-hidden="true"></span>
    {/if}
    <strong class="name">{node.name}</strong>
    {#if !editing}
      <span class="meta">
        {#if isParent}
          {node.children.length} {node.children.length === 1 ? "sub-category" : "sub-categories"}
        {:else}
          {node.buySymbol ?? ""}
        {/if}
      </span>
      <span class="meta">{node.target === null ? "—" : `${node.target}%`}</span>
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
      <button
        type="button"
        class="secondary"
        disabled={manager.busy}
        onclick={() => manager.startEdit(node.name)}
        aria-label="Edit {node.name}"
      >
        Edit
      </button>
      <button
        type="button"
        class="secondary"
        disabled={manager.busy}
        onclick={() => manager.remove(node.name)}
        aria-label="Delete {node.name}"
      >
        Delete
      </button>
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
    padding: 0.4rem 0;
    border-bottom: 1px solid #eef0f4;
  }
  .tree {
    list-style: none;
    margin: 0.4rem 0 0;
    padding: 0 0 0 1.5rem;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
    border-radius: 6px;
  }
  .row.dragging {
    opacity: 0.5;
  }
  .row.drop-ok {
    outline: 2px dashed #7a9bd1;
    outline-offset: 2px;
  }
  .row.drop-over {
    outline-style: solid;
    background: #eef3fb;
  }
  .name {
    min-width: 8rem;
  }
  .meta {
    min-width: 3.5rem;
    color: #555;
    font-size: 0.9rem;
  }
  .parent-marker {
    width: 0.8rem;
    color: #555;
    flex: none;
  }
  .dot {
    width: 0.8rem;
    height: 0.8rem;
    border-radius: 50%;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
    flex: none;
  }
  select {
    padding: 0.25rem 0.4rem;
    border: 1px solid #ccc;
    border-radius: 6px;
    font-size: 0.85rem;
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
</style>
