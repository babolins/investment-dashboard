<script lang="ts">
  import { onMount } from "svelte";
  import UploadCsv from "./components/UploadCsv.svelte";
  import AllocationChart from "./components/AllocationChart.svelte";
  import RebalanceForm from "./components/RebalanceForm.svelte";
  import BuyGuidance from "./components/BuyGuidance.svelte";
  import PortfolioTable from "./components/PortfolioTable.svelte";
  import CategoryManager from "./components/CategoryManager.svelte";
  import { uploadPortfolio, fetchConfig, fetchAllocation } from "./services/api";
  import { colorsByCategory, symbolsByCategory } from "./lib/categories";
  import type {
    AllocationBreakdown,
    ConfigSummary,
    PortfolioSnapshot,
    RebalanceResult,
  } from "./types";

  let portfolio = $state<PortfolioSnapshot | null>(null);
  let allocation = $state<AllocationBreakdown | null>(null);
  let result = $state<RebalanceResult | null>(null);
  let config = $state<ConfigSummary | null>(null);
  let uploading = $state(false);
  let uploadError = $state<string | null>(null);
  let refreshError = $state<string | null>(null);
  // Bumped by every refresh and upload so a stale in-flight response is ignored.
  let allocationSeq = 0;

  onMount(() => {
    fetchConfig()
      .then((c) => (config = c))
      .catch(() => {
        // config fetch failure is non-fatal
      });
  });

  async function handleUpload(file: File) {
    uploading = true;
    uploadError = null;
    refreshError = null;
    allocationSeq++;
    // Clear previous data up front so a failed upload never leaves stale results.
    portfolio = null;
    allocation = null;
    result = null;
    try {
      const res = await uploadPortfolio(file);
      portfolio = res.portfolio;
      allocation = res.allocation;
    } catch (err: unknown) {
      uploadError = err instanceof Error ? err.message : "Upload failed.";
    } finally {
      uploading = false;
    }
  }

  // Any config change invalidates the rebalance result and the allocation, which the
  // backend computes from the config. Keep showing the old allocation until the new one
  // arrives; if the refresh fails, drop it rather than show numbers that are now wrong.
  // Not async: the editors await their onChange, and must not stay busy during the refresh.
  function handleConfigChange(next: ConfigSummary) {
    config = next;
    result = null;
    refreshError = null;
    if (portfolio) void refreshAllocation(portfolio);
  }

  async function refreshAllocation(snapshot: PortfolioSnapshot) {
    const seq = ++allocationSeq;
    try {
      const fresh = await fetchAllocation(snapshot);
      if (seq === allocationSeq) allocation = fresh;
    } catch (err: unknown) {
      if (seq !== allocationSeq) return;
      allocation = null;
      refreshError = err instanceof Error ? err.message : "Unknown error";
    }
  }

  const colors = $derived(colorsByCategory(config));
  const symbolsByCat = $derived(symbolsByCategory(config)); // for chart tooltips
</script>

<div class="app">
  <header class="app-header">
    <h1>Investment Portfolio Rebalancer</h1>
    <p>Quarterly allocation analysis</p>
  </header>

  <main class="app-main">
    <UploadCsv onUpload={handleUpload} loading={uploading} error={uploadError} />

    {#if config}
      <CategoryManager {config} onChange={handleConfigChange} />
    {/if}

    {#if refreshError}
      <p class="error-msg" role="alert">Could not refresh allocation: {refreshError}</p>
    {/if}

    {#if portfolio}
      {#if allocation}
        <div class="top-row">
          <AllocationChart breakdown={allocation} {colors} symbolsByCategory={symbolsByCat} />
          {#if config}
            <RebalanceForm {allocation} {config} onResult={(r) => (result = r)} />
          {/if}
        </div>

        {#if result}
          <BuyGuidance {result} {colors} />
        {/if}
      {/if}

      <PortfolioTable
        holdings={portfolio.holdings}
        totalValue={portfolio.total_value}
        {config}
        onConfigChange={handleConfigChange}
      />
    {/if}
  </main>
</div>
