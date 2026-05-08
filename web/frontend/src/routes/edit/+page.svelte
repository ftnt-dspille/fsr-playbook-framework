<script lang="ts">
  /**
   * Phase 1 (read-only canvas) + Phase 2 (inspector reads) +
   * Phase 3.4 (arg-level edits with Save) of VISUAL_EDITOR_PLAN.
   */
  import { onMount } from 'svelte';
  import {
    listVisualFiles,
    getVisualFile,
    type VisualNode
  } from '$lib/api';
  import PlaybookCanvas from '$lib/components/PlaybookCanvas.svelte';
  import StepInspector from '$lib/components/StepInspector.svelte';
  import StepPalette from '$lib/components/StepPalette.svelte';
  import { visualStore } from '$lib/visualEditStore.svelte';

  let files: { name: string; size: number }[] = $state([]);
  let selectedFile: string = $state('');
  let loadError: string | null = $state(null);
  let activePbIdx: number = $state(0);
  let selectedNode: VisualNode | null = $state(null);
  let viewMode: 'visual' | 'yaml' = $state('visual');

  let graph = $derived(visualStore.state.graph);
  let dirty = $derived(visualStore.state.dirty);
  let saving = $derived(visualStore.state.saving);
  let saveError = $derived(visualStore.state.saveError);

  onMount(async () => {
    try {
      const r = await listVisualFiles();
      files = r.files;
      if (files.length > 0) {
        selectedFile = files[0].name;
        await loadFile(selectedFile);
      }
    } catch (e) {
      loadError = (e as Error).message;
    }
  });

  async function loadFile(name: string) {
    selectedNode = null;
    activePbIdx = 0;
    loadError = null;
    try {
      const g = await getVisualFile(name);
      visualStore.load(name, g);
    } catch (e) {
      loadError = (e as Error).message;
    }
  }

  function onPickFile(e: Event) {
    if (dirty && !confirm('Discard unsaved edits and switch playbook?')) return;
    const v = (e.currentTarget as HTMLSelectElement).value;
    selectedFile = v;
    loadFile(v);
  }

  async function onSave() {
    const r = await visualStore.save();
    if (r.ok) {
      // Re-resolve selected node from the refreshed graph (its
      // arguments may have been re-shaped by the round-trip).
      if (selectedNode) {
        const id = selectedNode.id;
        selectedNode = graph?.playbooks[activePbIdx]?.nodes.find((n) => n.id === id) ?? null;
      }
    }
  }

  async function onDiscard() {
    selectedNode = null;
    await loadFile(selectedFile);
  }
</script>

<div class="flex h-[calc(100vh-3.5rem)] flex-col">
  <header class="flex items-center gap-3 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-4 py-2">
    <span class="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Playbook</span>
    <select
      aria-label="Playbook"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-sm"
      value={selectedFile}
      onchange={onPickFile}
    >
      {#each files as f}
        <option value={f.name}>{f.name}</option>
      {/each}
    </select>

    {#if graph && graph.playbooks.length > 1}
      <select
        aria-label="Sub-playbook"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-sm"
        bind:value={activePbIdx}
      >
        {#each graph.playbooks as pb, i}
          <option value={i}>{pb.name}</option>
        {/each}
      </select>
    {/if}

    <div class="ml-auto inline-flex rounded border border-[var(--border-soft)] p-0.5 text-xs">
      <button
        type="button"
        class="rounded px-2 py-0.5 font-medium {viewMode === 'visual' ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)]'}"
        onclick={() => (viewMode = 'visual')}
      >Visual</button>
      <button
        type="button"
        class="rounded px-2 py-0.5 font-medium {viewMode === 'yaml' ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)]'}"
        onclick={() => (viewMode = 'yaml')}
      >YAML</button>
    </div>

    {#if dirty}
      <span class="text-xs text-amber-600">unsaved</span>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs font-medium text-[var(--text-default)] hover:bg-[var(--bg-canvas)]"
        onclick={onDiscard}
        disabled={saving}
      >Discard</button>
      <button
        type="button"
        class="rounded bg-[var(--brand)] px-2 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        onclick={onSave}
        disabled={saving}
      >{saving ? 'Saving…' : 'Save'}</button>
    {:else if graph}
      <span class="text-xs text-[var(--text-faint)]">
        {graph.layout_present ? 'layout: saved' : 'layout: auto'}
      </span>
    {/if}
  </header>

  {#if loadError}
    <div class="m-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
      {loadError}
    </div>
  {/if}
  {#if saveError}
    <div class="m-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
      Save failed: {saveError}
    </div>
  {/if}

  <div class="flex flex-1 overflow-hidden">
    {#if viewMode === 'visual'}
      <StepPalette />
    {/if}

    <main class="flex-1 overflow-hidden">
      {#if graph && graph.playbooks[activePbIdx] && viewMode === 'visual'}
        <PlaybookCanvas
          playbook={graph.playbooks[activePbIdx]}
          playbookIdx={activePbIdx}
          onSelect={(n) => (selectedNode = n)}
        />
      {:else if graph && viewMode === 'yaml'}
        <pre class="h-full overflow-auto bg-[var(--bg-canvas)] p-4 font-mono text-xs leading-relaxed text-[var(--text-default)]">{graph.source.yaml}</pre>
      {:else if !loadError}
        <div class="flex h-full items-center justify-center text-sm text-[var(--text-faint)]">
          {files.length === 0 ? 'No playbooks found in examples/' : 'Loading…'}
        </div>
      {/if}
    </main>

    {#if viewMode === 'visual'}
      <StepInspector
        node={selectedNode}
        playbook={graph?.playbooks[activePbIdx] ?? null}
        playbookIdx={activePbIdx}
      />
    {/if}
  </div>
</div>
