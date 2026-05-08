<script lang="ts">
  /**
   * Tabbed inspector. Phase 1.4 = Raw view; Phase 2 adds Args
   * (schema-driven) + Examples tabs. Verify tab lands in Phase 4.
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import StepInspectorArgsTab from './StepInspectorArgsTab.svelte';
  import StepInspectorExamplesTab from './StepInspectorExamplesTab.svelte';
  import StepInspectorBranchesTab from './StepInspectorBranchesTab.svelte';

  type Props = {
    node: VisualNode | null;
    playbook: VisualPlaybook | null;
    playbookIdx: number;
  };
  let { node, playbook, playbookIdx }: Props = $props();

  type Tab = 'args' | 'examples' | 'branches' | 'raw';
  let activeTab: Tab = $state('args');

  // Reset to Args whenever the user picks a different node.
  $effect(() => {
    if (node) activeTab = 'args';
  });

  let showBranches = $derived(node?.type === 'decision' || node?.type === 'manual_input');

  let TABS = $derived<{ key: Tab; label: string }[]>([
    { key: 'args', label: 'Args' },
    { key: 'examples', label: 'Examples' },
    ...(showBranches ? [{ key: 'branches' as Tab, label: 'Branches' }] : []),
    { key: 'raw', label: 'Raw' }
  ]);
</script>

<aside class="flex h-full w-96 flex-col border-l border-[var(--border-soft)] bg-[var(--bg-canvas)]">
  {#if !node || !playbook}
    <div class="flex flex-1 items-center justify-center px-4 text-center text-sm text-[var(--text-faint)]">
      Click a node to inspect
    </div>
  {:else}
    <header class="border-b border-[var(--border-soft)] px-4 py-3">
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        {node.family} · {node.type}
      </div>
      <h2 class="mt-1 truncate text-base font-semibold text-[var(--text-default)]" title={node.name}>
        {node.name}
      </h2>
      <div class="mt-0.5 text-xs text-[var(--text-faint)]">id: {node.id}</div>
    </header>

    <nav class="flex border-b border-[var(--border-soft)] text-xs">
      {#each TABS as t}
        <button
          type="button"
          class="flex-1 px-3 py-2 font-medium transition-colors {activeTab === t.key
            ? 'border-b-2 border-[var(--brand)] text-[var(--text-default)]'
            : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
          onclick={() => (activeTab = t.key)}
        >{t.label}</button>
      {/each}
    </nav>

    <div class="flex-1 overflow-auto px-4 py-3 text-sm">
      {#if activeTab === 'args'}
        <StepInspectorArgsTab {node} {playbookIdx} />
      {:else if activeTab === 'examples'}
        <StepInspectorExamplesTab {node} {playbook} />
      {:else if activeTab === 'branches'}
        <StepInspectorBranchesTab {node} {playbook} {playbookIdx} />
      {:else}
        {#if node.comment}
          <section class="mb-3">
            <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Comment</div>
            <p class="mt-1 whitespace-pre-wrap">{node.comment}</p>
          </section>
        {/if}
        {#if node.for_each}
          <section class="mb-3">
            <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">For each</div>
            <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.for_each, null, 2)}</pre>
          </section>
        {/if}
        <section>
          <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Arguments (raw)</div>
          {#if Object.keys(node.arguments ?? {}).length === 0}
            <p class="mt-1 italic text-[var(--text-faint)]">no arguments</p>
          {:else}
            <pre class="mt-1 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.arguments, null, 2)}</pre>
          {/if}
        </section>
      {/if}
    </div>
  {/if}
</aside>
