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

  let newLabel = $state('');
  let newTarget = $state('');

  function addBranch() {
    const lbl = newLabel.trim();
    const tgt = newTarget;
    if (!lbl || !tgt) return;
    // Reject collisions on (label) — FSR's runtime keys branches by label.
    const dup = playbook.edges.find(
      (e) => e.source === node.id && e.branch_kind === 'branch' && (e.label ?? '') === lbl
    );
    if (dup) return;
    visualStore.addEdge(playbookIdx, {
      source: node.id,
      target: tgt,
      label: lbl,
      branch_kind: 'branch'
    });
    newLabel = '';
    newTarget = '';
  }
</script>

{#if branches.length === 0}
  <p class="text-xs italic text-[var(--text-faint)]">No branches yet. Use the form below to add one, or drag from this node on the canvas.</p>
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

<section class="mt-3 rounded border border-dashed border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Add branch</div>
  <input
    type="text"
    placeholder="label (e.g. matched)"
    bind:value={newLabel}
    class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
  />
  <select
    aria-label="New branch target"
    bind:value={newTarget}
    class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
  >
    <option value="">— pick target —</option>
    {#each allTargets as t (t.id)}
      <option value={t.id}>{t.name} ({t.id})</option>
    {/each}
  </select>
  <button
    type="button"
    class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
    onclick={addBranch}
    disabled={!newLabel.trim() || !newTarget}
  >+ Add branch</button>
</section>
