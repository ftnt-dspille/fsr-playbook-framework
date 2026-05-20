<script lang="ts">
  /**
   * Studio-wide playbook header. One picker, two buckets (Drafts +
   * Examples), one Save / Save-As / Revisions surface. Mounted above
   * the Design/CLI mode toggle so the active playbook follows the
   * user across both modes.
   *
   * Phase B of the playbook unification (VISUAL_EDITOR_PLAN follow-up).
   */
  import { onMount } from 'svelte';
  import { playbookStore } from '$lib/playbookStore.svelte';

  type Props = {
    /** Optional flush hook the host page provides to capture the
     * latest in-flight YAML before save. In Design mode this renders
     * the visualStore graph to YAML; in CLI mode it returns the
     * Monaco buffer. When omitted, Save uses whatever is in
     * `playbookStore.yaml` already. */
    getActiveYaml?: () => Promise<string> | string;
    /** Studio mode toggle — promoted into this header to reclaim the
     * vertical row it used to occupy on its own. Optional so the
     * component still works on pages that don't have a mode toggle. */
    mode?: 'design' | 'cli';
    onModeChange?: (m: 'design' | 'cli') => void;
    modeBusy?: boolean;
  };
  let { getActiveYaml, mode, onModeChange, modeBusy = false }: Props = $props();

  let pickerOpen = $state(false);
  let revisionsOpen = $state(false);
  let savingAs = $state(false);
  let saveAsName = $state('');
  let cloningExample: string | null = $state(null);
  let cloneDraftName = $state('');
  let actionError: string | null = $state(null);

  let active = $derived(playbookStore.state.active);
  let drafts = $derived(playbookStore.state.drafts);
  let examples = $derived(playbookStore.state.examples);
  let revisions = $derived(playbookStore.state.revisions);
  let dirty = $derived(playbookStore.dirty);
  let saving = $derived(playbookStore.state.saving);
  let isExample = $derived(playbookStore.isExample);

  onMount(() => {
    void playbookStore.refresh();
  });

  async function pick(kind: 'draft' | 'example', name: string) {
    if (dirty && active && !confirm(`Discard unsaved edits to '${active.name}'?`)) return;
    await playbookStore.open(kind, name);
    pickerOpen = false;
  }

  async function onSave() {
    actionError = null;
    if (isExample) {
      // Clicking Save on an example becomes Clone & Edit.
      cloningExample = active!.name;
      cloneDraftName = active!.name.replace(/\.ya?ml$/i, '') + '_copy';
      return;
    }
    // Flush any unsaved in-flight buffer (Design canvas edits or CLI
    // Monaco edits not yet round-tripped into the store) before save.
    if (getActiveYaml) {
      try {
        const latest = await getActiveYaml();
        if (typeof latest === 'string') playbookStore.setYaml(latest);
      } catch (e) {
        actionError = `flush failed: ${(e as Error).message}`;
        return;
      }
    }
    const r = await playbookStore.save({ reason: 'manual save' });
    if (!r.ok) actionError = r.message ?? 'save failed';
  }

  async function onSaveAs() {
    const name = saveAsName.trim();
    if (!name) return;
    const r = await playbookStore.createDraft(name, playbookStore.yaml);
    if (!r.ok) { actionError = r.message ?? 'create failed'; return; }
    savingAs = false;
    saveAsName = '';
  }

  async function onCloneCommit() {
    if (!cloningExample) return;
    const target = cloneDraftName.trim();
    if (!target) return;
    const r = await playbookStore.cloneExample(cloningExample, target);
    if (!r.ok) { actionError = r.message ?? 'clone failed'; return; }
    cloningExample = null;
    cloneDraftName = '';
  }

  async function onLoadRevision(id: number) {
    const r = await playbookStore.loadRevision(id);
    if (!r.ok) { actionError = r.message ?? 'revision load failed'; return; }
    revisionsOpen = false;
  }

  async function onDelete() {
    if (!active || active.kind !== 'draft') return;
    if (!confirm(`Delete draft '${active.name}' and all its revisions?`)) return;
    const r = await playbookStore.deleteDraft(active.name);
    if (!r.ok) actionError = r.message ?? 'delete failed';
  }

  async function onNewBlank() {
    const name = prompt('New draft name:');
    if (!name) return;
    // Scaffold new drafts with sensible defaults: active so trigger
    // pushes actually fire, debug so authors see step output without
    // flipping a knob. Both can be overridden via the inspector once
    // the playbook is in production.
    const trimmed = name.trim();
    const safe = trimmed.replace(/"/g, '\\"');
    const yaml = [
      `collection: "${safe}"`,
      'description: ""',
      '',
      'playbooks:',
      `  - name: "${safe}"`,
      '    description: ""',
      '    is_active: true',
      '    debug: true',
      '    steps:',
      '      - name: start',
      '        type: start',
      '',
    ].join('\n');
    const r = await playbookStore.createDraft(trimmed, yaml);
    if (!r.ok) actionError = r.message ?? 'create failed';
  }

  function fmtTs(ts: string): string {
    try {
      const d = new Date(ts);
      return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
    } catch { return ts; }
  }
</script>

<div class="relative flex items-center gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-4 py-1.5 text-xs">
  <button
    type="button"
    class="flex items-center gap-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2.5 py-1 font-medium hover:bg-[var(--bg-canvas)]"
    onclick={() => (pickerOpen = !pickerOpen)}
    aria-haspopup="listbox"
    aria-expanded={pickerOpen}
  >
    {#if active}
      <span class="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
        {active.kind === 'draft' ? 'Draft' : 'Example'}
      </span>
      <span class="text-[var(--text-default)]">{active.name}</span>
    {:else}
      <span class="text-[var(--text-muted)]">Select a playbook…</span>
    {/if}
    <span aria-hidden="true" class="text-[var(--text-faint)]">▾</span>
  </button>

  {#if dirty}
    <span class="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">unsaved</span>
  {/if}

  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
    onclick={onSave}
    disabled={saving || !active || (!isExample && !dirty)}
    title={isExample ? 'Examples are read-only — Clone & Edit' : (dirty ? 'Save current draft' : 'No unsaved changes')}
  >{isExample ? 'Clone & Edit' : (saving ? 'Saving…' : 'Save')}</button>

  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
    onclick={() => { savingAs = true; saveAsName = active ? `${active.name}_copy` : 'untitled'; }}
    disabled={!active}
  >Save as…</button>

  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
    onclick={() => (revisionsOpen = !revisionsOpen)}
    disabled={!active || active.kind !== 'draft' || revisions.length === 0}
  >Revisions{revisions.length ? ` (${revisions.length})` : ''}</button>

  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-medium hover:bg-[var(--bg-canvas)]"
    onclick={onNewBlank}
  >+ New</button>

  {#if active && active.kind === 'draft'}
    <button
      type="button"
      class="rounded border border-rose-300 bg-rose-50 px-2 py-1 font-medium text-rose-700 hover:bg-rose-100 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300"
      onclick={onDelete}
    >Delete</button>
  {/if}

  <!-- Studio mode toggle (Design / CLI). Lives at the right end of the
       header so the previous standalone toggle row goes away — saves
       a full row of vertical chrome on first paint. -->
  {#if mode && onModeChange}
    <div class="ml-auto inline-flex rounded border border-[var(--border-soft)] p-0.5">
      <button
        type="button"
        class="rounded px-2.5 py-0.5 font-medium {mode === 'design' ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)]'}"
        onclick={() => onModeChange?.('design')}
        disabled={modeBusy}
      >Design</button>
      <button
        type="button"
        class="rounded px-2.5 py-0.5 font-medium {mode === 'cli' ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)]'}"
        onclick={() => onModeChange?.('cli')}
        disabled={modeBusy}
      >CLI</button>
    </div>
  {/if}

  {#if actionError}
    <span class="ml-2 rounded border border-red-300 bg-red-50 px-2 py-0.5 text-[11px] text-red-800">{actionError}</span>
  {/if}
</div>

<!-- Picker dropdown — two visually distinct buckets -->
{#if pickerOpen}
  <div class="relative">
    <div class="absolute left-4 top-0 z-30 max-h-[28rem] w-[28rem] overflow-auto rounded-md border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-xl">
      <section class="border-b border-[var(--border-soft)]">
        <header class="sticky top-0 flex items-center justify-between bg-[var(--bg-elev)] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          <span>My drafts ({drafts.length})</span>
        </header>
        {#if drafts.length === 0}
          <p class="px-3 py-2 text-xs italic text-[var(--text-faint)]">No drafts yet. Clone an example or click + New.</p>
        {:else}
          <ul>
            {#each drafts as d (d.name)}
              <li>
                <button
                  type="button"
                  class="flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left text-xs hover:bg-[var(--bg-elev)] {active?.kind === 'draft' && active?.name === d.name ? 'bg-[var(--brand)]/10 font-semibold' : ''}"
                  onclick={() => pick('draft', d.name)}
                >
                  <span class="truncate font-mono">{d.name}</span>
                  <span class="flex-shrink-0 text-[10px] text-[var(--text-faint)]">{fmtTs(d.updated_ts)}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
      <section>
        <header class="sticky top-0 flex items-center justify-between bg-[var(--bg-elev)] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          <span>Examples ({examples.length})</span>
          <span class="font-normal normal-case text-[var(--text-faint)]">read-only · click to view, then Clone &amp; Edit</span>
        </header>
        {#if examples.length === 0}
          <p class="px-3 py-2 text-xs italic text-[var(--text-faint)]">No examples in examples/.</p>
        {:else}
          <ul>
            {#each examples as e (e.name)}
              <li>
                <button
                  type="button"
                  class="flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left text-xs hover:bg-[var(--bg-elev)] {active?.kind === 'example' && active?.name === e.name ? 'bg-[var(--brand)]/10 font-semibold' : ''}"
                  onclick={() => pick('example', e.name)}
                >
                  <span class="truncate font-mono">{e.name}</span>
                  <span class="flex-shrink-0 text-[10px] text-[var(--text-faint)]">{(e.size / 1024).toFixed(1)} KB</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    </div>
  </div>
{/if}

<!-- Save-As modal -->
{#if savingAs}
  <div class="absolute left-4 top-12 z-40 w-80 rounded-md border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-3 shadow-xl">
    <div class="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Save as new draft</div>
    <input
      type="text"
      bind:value={saveAsName}
      onkeydown={(e) => { if (e.key === 'Enter') onSaveAs(); if (e.key === 'Escape') savingAs = false; }}
      class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs"
      placeholder="draft name"
    />
    <div class="mt-2 flex justify-end gap-2">
      <button type="button" class="rounded border border-[var(--border-soft)] px-2 py-0.5 text-xs" onclick={() => (savingAs = false)}>Cancel</button>
      <button type="button" class="rounded bg-[var(--brand)] px-2 py-0.5 text-xs text-white" onclick={onSaveAs}>Save</button>
    </div>
  </div>
{/if}

<!-- Clone-from-example modal -->
{#if cloningExample}
  <div class="absolute left-4 top-12 z-40 w-96 rounded-md border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-3 shadow-xl">
    <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Clone example to draft</div>
    <p class="mb-2 text-[11px] text-[var(--text-faint)]">Source: <code class="font-mono">{cloningExample}</code></p>
    <input
      type="text"
      bind:value={cloneDraftName}
      onkeydown={(e) => { if (e.key === 'Enter') onCloneCommit(); if (e.key === 'Escape') cloningExample = null; }}
      class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs"
      placeholder="new draft name"
    />
    <div class="mt-2 flex justify-end gap-2">
      <button type="button" class="rounded border border-[var(--border-soft)] px-2 py-0.5 text-xs" onclick={() => (cloningExample = null)}>Cancel</button>
      <button type="button" class="rounded bg-[var(--brand)] px-2 py-0.5 text-xs text-white" onclick={onCloneCommit}>Clone &amp; Edit</button>
    </div>
  </div>
{/if}

<!-- Revisions drawer -->
{#if revisionsOpen && active?.kind === 'draft'}
  <div class="absolute right-4 top-12 z-40 max-h-[28rem] w-96 overflow-auto rounded-md border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-xl">
    <header class="sticky top-0 flex items-center justify-between border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
      <span>Revisions for {active.name}</span>
      <button type="button" class="text-[var(--text-faint)] hover:text-[var(--text-muted)]" onclick={() => (revisionsOpen = false)}>×</button>
    </header>
    <ul>
      {#each revisions as rev (rev.id)}
        <li class="border-b border-[var(--border-soft)] px-3 py-2 hover:bg-[var(--bg-elev)]">
          <div class="flex items-baseline justify-between gap-2 text-xs">
            <span class="font-mono text-[var(--text-default)]">#{rev.id}</span>
            <span class="text-[10px] text-[var(--text-faint)]">{fmtTs(rev.created_ts)}</span>
          </div>
          <div class="mt-0.5 flex items-center gap-2 text-[11px]">
            <span class={rev.is_auto ? 'text-[var(--text-faint)]' : 'text-[var(--text-default)]'}>
              {rev.is_auto ? '⟲ auto' : '◆ manual'}
            </span>
            {#if rev.reason}<span class="truncate text-[var(--text-muted)]">{rev.reason}</span>{/if}
          </div>
          <button
            type="button"
            class="mt-1 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-canvas)]"
            onclick={() => onLoadRevision(rev.id)}
          >Load into editor</button>
        </li>
      {/each}
    </ul>
  </div>
{/if}
