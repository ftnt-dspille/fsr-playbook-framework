<script lang="ts">
  /**
   * Thin harness for integration tests in `src/routes/page-wiring.test.ts`.
   * Registers the same `playbookStore.bindAutosave()` effects the real
   * page does and exposes a small handle so tests can read the canonical
   * YAML and simulate Monaco input without dragging in Monaco, Chat,
   * PlaybookHeader, or SvelteKit navigation.
   */
  import { playbookStore } from '$lib/playbookStore.svelte';

  type HarnessAPI = { getYaml: () => string; typeIntoEditor: (v: string) => void };
  let { onReady }: { onReady?: (api: HarnessAPI) => void } = $props();

  playbookStore.bindAutosave();

  $effect(() => {
    onReady?.({
      getYaml: () => playbookStore.currentYaml,
      typeIntoEditor: (v: string) => playbookStore.replaceYaml(v, 'monaco')
    });
  });
</script>
