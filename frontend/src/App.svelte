<script lang="ts">
  import { onMount } from "svelte";
  import UploadCsv from "./components/UploadCsv.svelte";
  import AllocationChart from "./components/AllocationChart.svelte";
  import RebalanceForm from "./components/RebalanceForm.svelte";
  import BuyGuidance from "./components/BuyGuidance.svelte";
  import PortfolioTable from "./components/PortfolioTable.svelte";
  import { uploadPortfolio, fetchConfig } from "./services/api";
  import { symbolsByBucket, bucketLabelBySymbol } from "./lib/buckets";
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

  const defaultTarget = $derived(config?.default_target ?? null);
  const bucketSymbols = $derived(symbolsByBucket(config)); // for chart tooltips
  const symbolBucket = $derived(bucketLabelBySymbol(config)); // for the holdings table
</script>

<div class="app">
  <header class="app-header">
    <h1>Investment Portfolio Rebalancer</h1>
    <p>Quarterly allocation analysis · VTI · VXUS · BND</p>
  </header>

  <main class="app-main">
    <UploadCsv onUpload={handleUpload} loading={uploading} error={uploadError} />

    {#if portfolio && allocation}
      <div class="top-row">
        <AllocationChart breakdown={allocation} {bucketSymbols} />
        <RebalanceForm {allocation} {defaultTarget} onResult={(r) => (result = r)} />
      </div>

      {#if result}
        <BuyGuidance {result} />
      {/if}

      <PortfolioTable
        holdings={portfolio.holdings}
        totalValue={portfolio.total_value}
        {symbolBucket}
      />
    {/if}
  </main>
</div>
