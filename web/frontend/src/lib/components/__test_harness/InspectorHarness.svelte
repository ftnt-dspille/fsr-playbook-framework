<script lang="ts">
  /**
   * Test harness that mimics +page.svelte's selectedNodeId → derived
   * selectedNode flow. Used by integration tests to verify that store
   * mutations made via the inspector are reflected back into the
   * inspector's rendered DOM (regression for G38: stale node prop
   * after set_variable add/remove).
   */
  import StepInspector from '../StepInspector.svelte';
  import { visualStore } from '../../visualEditStore.svelte';

  type Props = { nodeId: string; playbookIdx: number };
  let { nodeId, playbookIdx }: Props = $props();

  let graph = $derived(visualStore.state.graph);
  let playbook = $derived(graph?.playbooks[playbookIdx] ?? null);
  let node = $derived(playbook?.nodes.find((n) => n.id === nodeId) ?? null);
</script>

<StepInspector {node} {playbook} {playbookIdx} />
