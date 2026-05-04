<script lang="ts">
  /**
   * Mini integration harness: mirrors the data flow on the Design page —
   * ExamplesMenu calls onLoad → page sets `yaml` → MonacoYaml receives
   * new `value` prop → Monaco's setValue is called.
   *
   * Used by EditorWiring.test.ts. Exposes `yaml` via a getter so tests
   * can read the current state, and renders the literal yaml in a div
   * so jsdom queries can assert against the post-update value without
   * caring about Monaco internals.
   */
  import ExamplesMenu from '../ExamplesMenu.svelte';
  import MonacoYaml from '../MonacoYaml.svelte';

  let yaml = $state('initial');
</script>

<div data-testid="yaml-mirror">{yaml}</div>
<ExamplesMenu onLoad={(text, _name) => (yaml = text)} />
<MonacoYaml value={yaml} onInput={(v) => (yaml = v)} />
