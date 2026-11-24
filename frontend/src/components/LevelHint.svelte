<script lang="ts">
  import { defaultShares, levelTotal, type TreeNode } from "../lib/hierarchy";

  interface Props {
    /** "Top level" or the parent category's name. */
    label: string;
    nodes: TreeNode[];
  }

  let { label, nodes }: Props = $props();

  const total = $derived(levelTotal(nodes, defaultShares(nodes)));
  const ok = $derived(Math.abs(total - 100) < 0.01);
</script>

<p class={["sum-indicator", ok ? "ok" : "err"]}>
  {#if ok}
    {label} targets total 100%
  {:else}
    {label} targets total {+total.toFixed(2)}% (not 100%), but you can still set targets in the
    rebalance form
  {/if}
</p>
