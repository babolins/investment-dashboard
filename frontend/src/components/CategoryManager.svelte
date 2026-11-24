<script lang="ts">
  import { tick } from "svelte";
  import { deleteCategory, updateCategory } from "../services/api";
  import { buildTree, descendants, leafNames } from "../lib/hierarchy";
  import type { ConfigSummary } from "../types";
  import AddCategoryForm from "./AddCategoryForm.svelte";
  import CategoryTreeRow from "./CategoryTreeRow.svelte";
  import LevelHint from "./LevelHint.svelte";
  import { provideManager, type Patch } from "./managerContext";

  interface Props {
    config: ConfigSummary;
    onChange: (config: ConfigSummary) => void;
  }

  let { config, onChange }: Props = $props();

  const MAX_LEAVES = 8;

  const tree = $derived(buildTree(config));
  // The cap is on leaves, which adding or moving can change either way, so the server enforces it.
  const atLeafCap = $derived(leafNames(config).length >= MAX_LEAVES);
  // Categories holding securities are leaves for good: nothing can be put inside them.
  const held = $derived(new Set(Object.values(config.assignments).flatMap((w) => Object.keys(w))));
  const containers = $derived(config.categories.map((c) => c.name).filter((n) => !held.has(n)));

  let dragged = $state<string | null>(null);
  let overTarget = $state<string | null>(null); // category name, or "" for the Top level zone
  let editing = $state<string | null>(null);
  let busy = $state(false);
  let rowError = $state<{ name: string; message: string } | null>(null);
  let status = $state("");

  const parentOf = (name: string) => config.categories.find((c) => c.name === name)?.parent ?? "";

  const moveTargets = (name: string) => {
    const blocked = new Set([name, ...descendants(config, name)]);
    return containers.filter((n) => !blocked.has(n));
  };

  // One rule for highlighting, accepting a drop and ignoring one. "" is the top level.
  function canDropOn(target: string): boolean {
    if (!dragged) return false;
    if (target === parentOf(dragged)) return false; // already there
    return moveTargets(dragged).includes(target) || target === "";
  }

  async function run(name: string, action: () => Promise<void>): Promise<boolean> {
    busy = true;
    rowError = null;
    try {
      await action();
      return true;
    } catch (err) {
      rowError = { name, message: err instanceof Error ? err.message : "Request failed" };
      return false;
    } finally {
      busy = false;
    }
  }

  async function move(name: string, parent: string | null): Promise<boolean> {
    status = "";
    const ok = await run(name, async () => {
      onChange(await updateCategory(name, { parent }));
    });
    if (!ok) return false;
    status = `Moved "${name}" to ${parent ?? "the top level"}.`;
    // The keyed row is recreated under its new parent, which drops keyboard focus.
    await tick();
    document.querySelector<HTMLElement>(`[data-move="${CSS.escape(name)}"]`)?.focus();
    return true;
  }

  const manager = {
    get config() {
      return config;
    },
    get busy() {
      return busy;
    },
    get editing() {
      return editing;
    },
    get rowError() {
      return rowError;
    },
    get dragged() {
      return dragged;
    },
    get overTarget() {
      return overTarget;
    },
    moveTargets,
    canDropOn,
    startDrag(name: string, e: DragEvent) {
      dragged = name;
      // Firefox won't start a drag without data; jsdom has no dataTransfer at all.
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", name);
      }
    },
    endDrag() {
      dragged = null;
      overTarget = null;
    },
    dragOver(e: DragEvent, target: string) {
      // Cancelling dragover is what marks a target as droppable, so only do it for valid ones.
      if (!canDropOn(target)) return;
      e.preventDefault();
      overTarget = target;
    },
    dragLeave(e: DragEvent, target: string) {
      // dragleave also fires when the pointer crosses a child element of the target.
      if (overTarget === target && !(e.currentTarget as Node).contains(e.relatedTarget as Node)) {
        overTarget = null;
      }
    },
    async drop(e: DragEvent, target: string) {
      if (!canDropOn(target)) return;
      e.preventDefault();
      const name = dragged!;
      // Reset here: re-parenting recreates the dragged row, so its dragend may never arrive.
      dragged = null;
      overTarget = null;
      await move(name, target || null);
    },
    move,
    async remove(name: string) {
      status = "";
      await run(name, async () => {
        onChange(await deleteCategory(name));
      });
    },
    startEdit(name: string) {
      editing = name;
      rowError = null;
    },
    cancelEdit() {
      editing = null;
      rowError = null;
    },
    fail(name: string, message: string) {
      rowError = { name, message };
    },
    async save(name: string, patch: Patch) {
      await run(name, async () => {
        onChange(await updateCategory(name, patch));
        editing = null;
      });
    },
  };
  provideManager(manager);
</script>

<div class="card">
  <h2>Categories</h2>
  <p class="hint">
    Group your holdings into categories, then assign each holding in the table below. Targets are a
    share of the parent category, or of the portfolio at the top level. Securities are assigned to
    categories with no sub-categories. Drag a row onto a category to move it, or use its "Move to"
    menu.
  </p>

  <div
    class={[
      "top-zone",
      { "drop-ok": dragged !== null && canDropOn(""), "drop-over": overTarget === "" },
    ]}
    role="group"
    aria-label="Top level"
    ondragover={(e) => manager.dragOver(e, "")}
    ondragleave={(e) => manager.dragLeave(e, "")}
    ondrop={(e) => manager.drop(e, "")}
  >
    Drop here to move to the top level
  </div>

  {#if tree.length > 0}
    <ul class="tree">
      {#each tree as node (node.name)}
        <CategoryTreeRow {node} />
      {/each}
    </ul>
    <LevelHint label="Top level" nodes={tree} />
  {/if}
  {#if config.categories.some((c) => c.parent)}
    <p class="hint">Deleting a category: its children move up a level.</p>
  {/if}
  <p role="status" class="hint">{status}</p>

  <AddCategoryForm {config} parents={containers} {onChange} />
  {#if atLeafCap}
    <p class="hint">
      Maximum of {MAX_LEAVES} leaf categories (categories with no sub-categories).
    </p>
  {/if}
</div>

<style>
  .tree {
    list-style: none;
    margin: 0 0 0.5rem;
    padding: 0;
  }
  .top-zone {
    margin: 0.5rem 0;
    padding: 0.3rem 0.6rem;
    border: 1px dashed transparent;
    border-radius: 6px;
    font-size: 0.85rem;
    color: transparent; /* kept in the DOM always: inserting nodes during dragstart cancels the drag */
  }
  .top-zone.drop-ok {
    border-color: #7a9bd1;
    color: #555;
  }
  .top-zone.drop-over {
    border-style: solid;
    background: #eef3fb;
  }
</style>
