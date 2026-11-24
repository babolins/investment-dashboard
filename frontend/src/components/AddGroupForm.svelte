<script lang="ts">
  import { createGroup } from "../services/api";
  import {
    duplicateName,
    parseTarget,
    validateName,
    validateTarget,
  } from "../lib/categoryValidation";
  import type { ConfigSummary } from "../types";

  interface Props {
    config: ConfigSummary;
    onChange: (config: ConfigSummary) => void;
  }

  let { config, onChange }: Props = $props();

  const uid = $props.id();

  let name = $state("");
  let parent = $state("");
  let target = $state<number | null>(null);
  let error = $state<string | null>(null);
  let adding = $state(false);

  async function add(event: SubmitEvent) {
    event.preventDefault();
    const input = { name: name.trim(), parent: parent || null, target: parseTarget(target) };
    error =
      validateName(input.name, "group") ??
      duplicateName(config, input.name) ??
      validateTarget(input.target);
    if (error) return;
    adding = true;
    try {
      onChange(await createGroup(input));
      name = "";
      parent = "";
      target = null;
    } catch (err) {
      error = err instanceof Error ? err.message : "Could not add group";
    } finally {
      adding = false;
    }
  }
</script>

<form class="add" novalidate onsubmit={add} aria-label="Add group">
  <div class="field">
    <label for="{uid}-name">Name</label>
    <input id="{uid}-name" bind:value={name} disabled={adding} />
  </div>
  <div class="field">
    <label for="{uid}-parent">Parent group</label>
    <select id="{uid}-parent" bind:value={parent} disabled={adding}>
      <option value="">Top level</option>
      {#each config.groups as g (g.name)}
        <option value={g.name}>{g.name}</option>
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
  <button type="submit" class="btn-primary" disabled={adding}>Add group</button>
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
