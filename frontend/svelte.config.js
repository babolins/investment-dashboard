import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

export default {
  // Lets <script lang="ts"> (and <style lang="...">) be processed by Vite.
  preprocess: vitePreprocess(),
};
