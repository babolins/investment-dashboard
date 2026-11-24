<script lang="ts">
  import { onMount } from "svelte";
  import { fetchConfig } from "./services/api";

  // Placeholder shell: team T6 completes this (upload, table, chart, rebalance, guidance)
  // and will keep the fetched config in state.
  onMount(() => {
    fetchConfig().catch(() => {
      // config fetch failure is non-fatal
    });
  });
</script>

<div class="app">
  <header class="app-header">
    <h1>Investment Portfolio Rebalancer</h1>
    <p>Quarterly allocation analysis · VTI · VXUS · BND</p>
  </header>

  <main class="app-main"></main>
</div>
