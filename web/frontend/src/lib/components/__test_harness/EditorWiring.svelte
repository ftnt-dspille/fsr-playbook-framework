<script lang="ts">
  /**
   * Mini integration harness for the prop → MonacoYaml setValue path.
   *
   * Originally validated the ExamplesMenu → page → Monaco data flow.
   * That menu was retired when PlaybookHeader took over playbook
   * loading; this harness now exercises the same mechanic through a
   * plain "Load YAML" button so the assertion (parent-state change
   * triggers Monaco.setValue) still has coverage without depending on
   * a deleted component.
   */
  import MonacoYaml from '../MonacoYaml.svelte';

  let yaml = $state('initial');
  function loadFixture() {
    yaml = 'collection: A\nplaybooks: []\n';
  }
</script>

<div data-testid="yaml-mirror">{yaml}</div>
<button type="button" onclick={loadFixture}>Load YAML</button>
<MonacoYaml value={yaml} onInput={(v) => (yaml = v)} />
