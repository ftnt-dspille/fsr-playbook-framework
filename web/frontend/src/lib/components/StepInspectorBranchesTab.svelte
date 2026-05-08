<script lang="ts">
  /**
   * Phase 3.6 — branch label editing for decision / manual_input nodes.
   *
   * Lists every outgoing `branch_kind: 'branch'` edge from the
   * selected step; each row lets the user rename the label or
   * retarget via dropdown. Backed by the same store mutators the
   * canvas uses, so changes survive Save the same way.
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import { visualStore } from '../visualEditStore.svelte';

  type Props = { node: VisualNode; playbook: VisualPlaybook; playbookIdx: number };
  let { node, playbook, playbookIdx }: Props = $props();

  let branches = $derived(playbook.edges.filter((e) => e.source === node.id && e.branch_kind === 'branch'));

  let allTargets = $derived(playbook.nodes.filter((n) => n.id !== node.id));

  function rename(oldLabel: string | null, e: Event) {
    const v = (e.currentTarget as HTMLInputElement).value;
    visualStore.renameBranchLabel(playbookIdx, node.id, oldLabel, v);
  }

  function retarget(label: string | null, oldTarget: string, e: Event) {
    const v = (e.currentTarget as HTMLSelectElement).value;
    visualStore.retargetEdge(
      playbookIdx,
      { source: node.id, target: oldTarget, label },
      v
    );
  }

  function remove(label: string | null, target: string) {
    if (!confirm(`Delete branch '${label ?? '(default)'}'?`)) return;
    visualStore.removeEdge(playbookIdx, { source: node.id, target, label });
  }
</script>

{#if branches.length === 0}
  <p class="text-xs italic text-[var(--text-faint)]">No branches yet. Add one by drawing an edge from this node.</p>
{:else}
  <ul class="space-y-2">
    {#each branches as br (br.label + '|' + br.target)}
      <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
        <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Label</div>
        <input
          type="text"
          value={br.label ?? ''}
          placeholder={br.label === null ? '(default)' : ''}
          oninput={(e) => rename(br.label, e)}
          class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
        />
        <div class="mt-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Target</div>
        <select
          aria-label="Branch target"
          value={br.target}
          onchange={(e) => retarget(br.label, br.target, e)}
          class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
        >
          {#each allTargets as t (t.id)}
            <option value={t.id}>{t.name} ({t.id})</option>
          {/each}
        </select>
        <button
          type="button"
          class="mt-2 text-[10px] text-red-600 underline hover:text-red-700"
          onclick={() => remove(br.label, br.target)}
        >Delete branch</button>
      </li>
    {/each}
  </ul>
{/if}
