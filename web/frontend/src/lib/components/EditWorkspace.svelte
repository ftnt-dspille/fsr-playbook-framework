<script lang="ts">
  /**
   * Design-mode workspace: visual canvas + step inspector + popover
   * step palette.
   *
   * The palette used to be docked permanently on the left rail; it
   * now slides in as an overlay so the canvas claims the full width
   * by default. Toggle button lives on the canvas's left edge.
   *
   * Phase B of the Studio playbook unification: this component is now
   * a pure renderer. The active YAML lives in `playbookStore`; the
   * page-level effect in `+page.svelte` pushes new playbook YAML into
   * `visualStore` via `loadFromYaml`. Save flows through PlaybookHeader.
   */
  import { type VisualNode } from '$lib/api';
  import PlaybookCanvas from '$lib/components/PlaybookCanvas.svelte';
  import StepInspector from '$lib/components/StepInspector.svelte';
  import StepPalette from '$lib/components/StepPalette.svelte';
  import VarTreePane from '$lib/components/VarTreePane.svelte';
  import { varPaneStore } from '$lib/varPaneStore.svelte';
  import EditorToolbar from '$lib/components/EditorToolbar.svelte';
  import JinjaTestModal from '$lib/components/JinjaTestModal.svelte';
  import PlaybookGuards from '$lib/components/PlaybookGuards.svelte';
  import { visualStore } from '$lib/visualEditStore.svelte';

  type Props = {
    /** Pop the bottom diagnostics drawer to a specific tab. Forwarded
     * down so the Compile button on EditorToolbar can lift the drawer
     * without EditWorkspace duplicating drawer state. */
    onShowDrawer?: (tab: 'diagnostics' | 'fixes' | 'deploy') => void;
  };
  let { onShowDrawer }: Props = $props();

  let activePbIdx: number = $state(0);
  // Track the selection by ID, not by object reference. The store
  // replaces node objects on every mutation (`pb.nodes[idx] = {...}`),
  // so caching the object means the inspector reads stale args after
  // any edit (G38: set_variable add-variable bug).
  let selectedNodeId: string | null = $state(null);
  let layoutDir: 'TB' | 'LR' = $state('TB');

  // Palette + Inspector are both popovers (closed by default) so the
  // canvas claims the full viewport width on first paint. Each remembers
  // its own open/closed state across reloads via localStorage.
  let paletteOpen: boolean = $state(
    typeof localStorage !== 'undefined' && localStorage.getItem('fsrpb.palette.open') === '1'
  );
  $effect(() => {
    try { localStorage.setItem('fsrpb.palette.open', paletteOpen ? '1' : '0'); } catch {}
  });

  // Inspector starts closed on every page load — it only pops open when
  // the user actually selects a node (effect below). No localStorage
  // persistence: a fresh canvas should never come up with an empty
  // inspector hogging the right edge.
  let inspectorOpen: boolean = $state(false);
  let jinjaTestOpen: boolean = $state(false);

  let graph = $derived(visualStore.state.graph);
  let selectedNode: VisualNode | null = $derived(
    selectedNodeId
      ? graph?.playbooks[activePbIdx]?.nodes.find((n) => n.id === selectedNodeId) ?? null
      : null
  );

  // Reset selection when the active playbook changes (e.g. user picks
  // a new doc in PlaybookHeader → page effect calls visualStore.loadFromYaml
  // → graph reference changes → previous selectedNodeId no longer exists).
  $effect(() => {
    void graph;
    if (!selectedNode) selectedNodeId = null;
  });

  // Auto-open the inspector when the user clicks a node so they don't
  // have to chase a hidden panel after every selection.
  $effect(() => {
    if (selectedNodeId) inspectorOpen = true;
  });

  // Keep the var pane's scope in sync with the selected node so
  // ancestor step shapes reflect what's actually in scope when the
  // user opens the pane from a field. Also auto-close the pane when
  // the user navigates to a different step — the previous target's
  // insert closure is no longer relevant.
  $effect(() => {
    varPaneStore.node = selectedNode;
    if (!selectedNode) varPaneStore.close();
  });

  // Drain cross-component focus signals — e.g. the diagnostics drawer
  // calling `visualStore.selectStepByName(step_id)` when the user
  // clicks a render-path diagnostic row. We mirror the pending tuple
  // into our local selection state, which auto-opens the inspector
  // via the effect above.
  $effect(() => {
    const pending = visualStore.state.pendingSelection;
    if (!pending) return;
    activePbIdx = pending.playbookIdx;
    selectedNodeId = pending.nodeId;
    visualStore.consumePendingSelection();
  });
</script>

<div class="flex h-full min-h-0 flex-1 flex-col">
  {#if graph && graph.playbooks.length > 1}
    <header class="flex items-center gap-3 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-4 py-1">
      <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Sub-playbook</span>
      <select
        aria-label="Sub-playbook"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-xs"
        bind:value={activePbIdx}
      >
        {#each graph.playbooks as pb, i}
          <option value={i}>{pb.name}</option>
        {/each}
      </select>
    </header>
  {/if}

  <div class="flex flex-1 overflow-hidden">
    <main class="relative flex flex-1 flex-col overflow-hidden">
      {#if graph}
        <EditorToolbar
          playbookIdx={activePbIdx}
          direction={layoutDir}
          onDirectionChange={(d) => (layoutDir = d)}
          onJinjaTest={() => (jinjaTestOpen = true)}
          {onShowDrawer}
        />
      {/if}
      {#if graph && graph.playbooks[activePbIdx]}
        <PlaybookGuards playbook={graph.playbooks[activePbIdx]} />
        <PlaybookCanvas
          playbook={graph.playbooks[activePbIdx]}
          playbookIdx={activePbIdx}
          direction={layoutDir}
          onSelect={(n) => (selectedNodeId = n?.id ?? null)}
        />
      {:else}
        <div class="flex h-full items-center justify-center text-sm text-[var(--text-faint)]">
          Pick a playbook from the header to start designing.
        </div>
      {/if}

      <!-- Palette toggle: a thin left-edge button that pops the palette
           out as an overlay. Always visible so the user can reach the
           Steps / Connectors / Recipes drag sources without surrendering
           a permanent rail of horizontal space. -->
      {#if !paletteOpen}
        <button
          type="button"
          class="absolute left-0 top-16 z-20 flex items-center gap-1 rounded-r-md border border-l-0 border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] shadow-sm hover:bg-[var(--bg-canvas)] hover:text-[var(--text-default)]"
          onclick={() => (paletteOpen = true)}
          title="Open the step / connector / recipe palette"
          aria-expanded="false"
        >
          <span aria-hidden="true">▸</span>
          <span>Steps</span>
        </button>
      {/if}

      {#if paletteOpen}
        <div
          class="absolute inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-xl"
          role="dialog"
          aria-label="Step palette"
        >
          <header class="flex items-center justify-between border-b border-[var(--border-soft)] px-3 py-1.5">
            <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Palette</span>
            <button
              type="button"
              class="rounded px-1 text-[var(--text-faint)] hover:text-[var(--text-default)]"
              onclick={() => (paletteOpen = false)}
              aria-label="Close palette"
              title="Close palette"
            >×</button>
          </header>
          <div class="flex-1 overflow-hidden">
            <StepPalette />
          </div>
        </div>
      {/if}
      <!-- Inspector edge-tab: only surfaces when there is something
           selected to inspect AND the panel was manually dismissed.
           A no-selection tab is just chrome — the auto-open effect
           pops the inspector when the user clicks a node, so the tab
           exists purely to re-open after an explicit close. -->
      {#if !inspectorOpen && selectedNode}
        <button
          type="button"
          class="absolute right-0 top-16 z-20 flex items-center gap-1 rounded-l-md border border-r-0 border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] shadow-sm hover:bg-[var(--bg-canvas)] hover:text-[var(--text-default)]"
          onclick={() => (inspectorOpen = true)}
          title="Reopen inspector for the selected step"
          aria-expanded="false"
        >
          <span>Inspector</span>
          <span aria-hidden="true">◂</span>
        </button>
      {/if}

      {#if inspectorOpen && varPaneStore.open && selectedNode}
        <!-- Variable tree pane — flies in to the immediate left of
             the inspector when a Jinja-accepting field is focused or
             its {x} button is clicked. Width matches the inspector
             so the two panes feel like a single inspector cluster. -->
        <div
          class="absolute inset-y-0 z-30 flex w-80 flex-col border-l border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-xl"
          style:right="24rem"
          role="dialog"
          aria-label="Variable tree pane"
        >
          <VarTreePane
            node={selectedNode}
            playbook={graph?.playbooks[activePbIdx] ?? null}
            onClose={() => varPaneStore.close()}
          />
        </div>
      {/if}

      {#if inspectorOpen}
        <div
          class="absolute inset-y-0 right-0 z-30 flex w-96 flex-col border-l border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-xl"
          role="dialog"
          aria-label="Step inspector"
        >
          <header class="flex items-center justify-between border-b border-[var(--border-soft)] px-3 py-1.5">
            <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Inspector</span>
            <button
              type="button"
              class="rounded px-1 text-[var(--text-faint)] hover:text-[var(--text-default)]"
              onclick={() => (inspectorOpen = false)}
              aria-label="Close inspector"
              title="Close inspector"
            >×</button>
          </header>
          <div class="flex-1 overflow-hidden">
            <StepInspector
              node={selectedNode}
              playbook={graph?.playbooks[activePbIdx] ?? null}
              playbookIdx={activePbIdx}
              onDelete={() => (selectedNodeId = null)}
            />
          </div>
        </div>
      {/if}
    </main>
  </div>
</div>

{#if jinjaTestOpen}
  <JinjaTestModal onClose={() => (jinjaTestOpen = false)} />
{/if}
