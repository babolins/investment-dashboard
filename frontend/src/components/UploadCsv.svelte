<script lang="ts">
  interface Props {
    onUpload: (file: File) => void;
    loading: boolean;
    error: string | null;
  }

  let { onUpload, loading, error }: Props = $props();

  let input: HTMLInputElement | undefined = $state();
  let dragOver = $state(false);
  let rejection: string | null = $state(null);

  function handleFile(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv") && file.type !== "text/csv") {
      rejection = "Please upload a CSV file exported from Fidelity.";
      return;
    }
    rejection = null;
    onUpload(file);
  }
</script>

<div class="card upload-card">
  <h2>Upload Portfolio</h2>
  <p class="hint">
    In Fidelity, go to <strong>Accounts &amp; Trade → Portfolio → Positions</strong>, then click
    <strong>Download</strong> to export a CSV.
  </p>

  <button
    type="button"
    class="drop-zone"
    class:drag-over={dragOver}
    onclick={() => input?.click()}
    ondragover={(e) => {
      e.preventDefault();
      dragOver = true;
    }}
    ondragleave={() => (dragOver = false)}
    ondrop={(e) => {
      e.preventDefault();
      dragOver = false;
      handleFile(e.dataTransfer?.files[0]);
    }}
  >
    {#if loading}
      <span class="uploading">Parsing portfolio…</span>
    {:else}
      <span class="drop-icon" aria-hidden="true">📂</span>
      <span>Drop your Fidelity CSV here, or click to browse</span>
    {/if}
  </button>

  <input
    bind:this={input}
    type="file"
    accept=".csv,text/csv"
    hidden
    aria-label="Fidelity CSV file"
    onchange={(e) => handleFile(e.currentTarget.files?.[0])}
  />

  {#if rejection ?? error}
    <p class="error-msg" role="alert">{rejection ?? error}</p>
  {/if}
</div>

<style>
  /* The drop zone is a <button> for keyboard access; undo the UA button look.
     :where() keeps specificity at zero so the global hover/drag-over background still wins. */
  :where(.drop-zone) {
    width: 100%;
    background: none;
    font-family: inherit;
  }
</style>
