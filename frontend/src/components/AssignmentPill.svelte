<script lang="ts">
  import { tick } from "svelte";
  import { setAssignment } from "../services/api";
  import {
    assignmentLabel,
    assignmentOf,
    colorsByCategory,
    evenSplit,
    FALLBACK_COLOR,
    toWeights,
  } from "../lib/categories";
  import { leafNames } from "../lib/hierarchy";
  import type { ConfigSummary } from "../types";

  interface Props {
    symbol: string;
    config: ConfigSummary;
    onChange: (config: ConfigSummary) => void;
  }

  let { symbol, config, onChange }: Props = $props();

  const uid = $props.id();
  const panelId = `${uid}-panel`;
  const feedbackId = `${uid}-feedback`;

  let open = $state(false);
  let saving = $state(false);
  let error = $state<string | null>(null);
  // The draft is seeded each time the editor opens, so Cancel simply discards it.
  let selected = $state<string[]>([]);
  let excluded = $state(false);
  let percents = $state<Record<string, number | null>>({});
  let pill: HTMLButtonElement;
  let panel = $state<HTMLElement>();

  const current = $derived(assignmentOf(config, symbol));
  const label = $derived(assignmentLabel(current));
  // Securities are assigned to leaves only; names are unique, so a flat list is unambiguous.
  const leaves = $derived(leafNames(config));
  const colors = $derived(colorsByCategory(config));
  const dots = $derived(
    current.kind === "assigned"
      ? Object.keys(current.weights).map((name) => colors[name] ?? FALLBACK_COLOR)
      : [],
  );
  // A single category's tint tells the pill apart at a glance; splits stay neutral with several dots.
  const tint = $derived(dots.length === 1 ? dots[0] : null);

  const split = $derived(selected.length >= 2);
  const total = $derived(selected.reduce((sum, name) => sum + (percents[name] ?? 0), 0));
  const percentsValid = $derived(
    !split ||
      (selected.every((name) => {
        const p = percents[name];
        return p !== null && p !== undefined && Number.isFinite(p) && p >= 0;
      }) &&
        Math.abs(total - 100) < 0.01),
  );

  function begin() {
    excluded = current.kind === "excluded";
    selected = current.kind === "assigned" ? leaves.filter((name) => name in current.weights) : [];
    percents =
      current.kind === "assigned"
        ? Object.fromEntries(
            selected.map((name) => [name, +(current.weights[name] * 100).toFixed(2)]),
          )
        : {};
    error = null;
    open = true;
    void tick().then(() => panel?.querySelector("input")?.focus());
  }

  function close() {
    open = false;
    pill.focus();
  }

  function toggleCategory(name: string, on: boolean) {
    selected = leaves.filter((n) => (n === name ? on : selected.includes(n)));
    if (on) excluded = false;
    percents = evenSplit(selected);
  }

  function toggleExcluded(on: boolean) {
    excluded = on;
    if (on) {
      selected = [];
      percents = {};
    }
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (saving || !percentsValid) return;
    saving = true;
    error = null;
    try {
      const weights =
        selected.length === 1
          ? { [selected[0]]: 1 }
          : toWeights(Object.fromEntries(selected.map((name) => [name, percents[name] ?? 0])));
      const updated = await setAssignment(symbol, excluded ? { excluded: true } : { weights });
      onChange(updated);
      close();
    } catch (err) {
      error = err instanceof Error ? err.message : "Could not save assignment";
    } finally {
      saving = false;
    }
  }

  // A document listener (not an element handler) keeps Escape working wherever focus is, and a11y-clean.
  $effect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
</script>

<button
  bind:this={pill}
  type="button"
  class={["pill", current.kind]}
  style:background={tint ? `color-mix(in srgb, ${tint} 15%, white)` : null}
  aria-expanded={open}
  aria-controls={panelId}
  aria-label="{symbol}: {label}. Edit category"
  onclick={() => (open ? close() : begin())}
>
  {#each dots as color, i (i)}
    <span class="dot" style:background={color} aria-hidden="true"></span>
  {/each}
  <span>{label}</span>
</button>

{#if open}
  <form id={panelId} class="panel" bind:this={panel} onsubmit={save}>
    <fieldset disabled={saving}>
      <legend>Category for {symbol}</legend>
      {#each leaves as name (name)}
        <div class="option">
          <label>
            <input
              type="checkbox"
              checked={selected.includes(name)}
              onchange={(e) => toggleCategory(name, e.currentTarget.checked)}
            />
            <span class="dot" style:background={colors[name] ?? FALLBACK_COLOR} aria-hidden="true"
            ></span>
            {name}
          </label>
          {#if split && selected.includes(name)}
            <input
              type="number"
              class="percent"
              min="0"
              max="100"
              step="0.01"
              aria-label="{name} percent"
              aria-describedby={feedbackId}
              bind:value={percents[name]}
            />
            <span aria-hidden="true">%</span>
          {/if}
        </div>
      {/each}
      <label class="option">
        <input
          type="checkbox"
          checked={excluded}
          onchange={(e) => toggleExcluded(e.currentTarget.checked)}
        />
        Exclude from allocation
      </label>
    </fieldset>
    <div id={feedbackId} aria-live="polite">
      {#if split}
        <p class={["sum-indicator", percentsValid ? "ok" : "err"]}>
          Total {total.toFixed(2)}%{percentsValid ? "" : " (must be 100%)"}
        </p>
      {/if}
    </div>
    {#if error}
      <p class="error-msg" role="alert">{error}</p>
    {/if}
    <div class="actions">
      <button type="submit" class="btn-primary" disabled={saving || !percentsValid}>
        {saving ? "Saving…" : "Save"}
      </button>
      <button type="button" class="btn-secondary" disabled={saving} onclick={close}>Cancel</button>
    </div>
  </form>
{/if}

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.6rem;
    border: 1px solid transparent;
    border-radius: 999px;
    background: #eef0f3;
    color: var(--text);
    font: inherit;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }
  .pill.excluded {
    background: #e5e7eb;
  }
  /* Dashed outline plus the word "Unassigned": the warning never relies on colour alone. */
  .pill.unassigned {
    background: #fff;
    border: 1px dashed #b45309;
  }
  .pill:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }
  .dot {
    display: inline-block;
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 50%;
    flex: none;
  }
  /* Inline (not a popover): .table-wrapper clips absolutely positioned content. */
  .panel {
    margin-top: 0.5rem;
    min-width: 15rem;
    padding: 0.75rem 0.9rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
    box-shadow: 0 4px 12px rgba(16, 24, 40, 0.06);
    white-space: normal;
    font-weight: normal;
  }
  .panel fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    background: none;
  }
  .panel legend {
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 0.3rem;
  }
  .option {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.15rem 0;
    font-size: 0.85rem;
  }
  .option label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex: 1;
  }
  label.option {
    cursor: pointer;
  }
  .percent {
    width: 5rem;
    height: 1.9rem;
    text-align: right;
  }
  .actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.6rem;
  }
</style>
