<script lang="ts">
  /**
   * Phase 3.1 — left rail palette.
   *
   * Three collapsible sections:
   *  - Step types (curated friendly shortnames the resolver knows).
   *  - Connectors (searchable; click to expand its operations).
   *  - Recipes (multi-step subgraphs).
   *
   * Each row is a HTML5 drag source carrying a JSON payload the
   * canvas decodes in Phase 3.2's drop handler. Until that lands,
   * clicking a row also fires `onPick` so the user can stage an
   * insert via the Save flow.
   */
  import { onMount } from 'svelte';
  import {
    getStepTypes,
    searchConnectors,
    listOperations,
    listRecipes,
    type StepTypeHint,
    type ConnectorRef,
    type OperationRef,
    type RecipeRef
  } from '../api';

  type PaletteItem =
    | { kind: 'step_type'; type: string; label: string; detail?: string }
    | { kind: 'connector_op'; connector: string; operation: string; title?: string }
    | { kind: 'recipe'; name: string; recipe_kind: string };

  type Props = { onPick?: (item: PaletteItem) => void };
  let { onPick }: Props = $props();

  let activeSection: 'steps' | 'connectors' | 'recipes' = $state('steps');
  let stepTypes: StepTypeHint[] = $state([]);
  let connectors: ConnectorRef[] = $state([]);
  let recipes: RecipeRef[] = $state([]);
  let connectorQuery = $state('');
  let expandedConnector: string | null = $state(null);
  let connectorOps: OperationRef[] = $state([]);
  let connectorOpsLoading = $state(false);

  onMount(async () => {
    try { stepTypes = await getStepTypes(); } catch {}
    try { connectors = await searchConnectors('', 100); } catch {}
    try { recipes = await listRecipes(); } catch {}
  });

  let filteredConnectors = $derived(
    connectorQuery
      ? connectors.filter((c) =>
          (c.name + ' ' + (c.label ?? '')).toLowerCase().includes(connectorQuery.toLowerCase())
        )
      : connectors
  );

  async function expandConnector(name: string) {
    if (expandedConnector === name) {
      expandedConnector = null;
      connectorOps = [];
      return;
    }
    expandedConnector = name;
    connectorOpsLoading = true;
    connectorOps = [];
    try { connectorOps = await listOperations(name, '', 50); }
    finally { connectorOpsLoading = false; }
  }

  /** Begin a drag with a payload Phase 3.2 will decode on drop. */
  function dragStart(e: DragEvent, item: PaletteItem) {
    if (!e.dataTransfer) return;
    e.dataTransfer.setData('application/x-fsrpb-step', JSON.stringify(item));
    e.dataTransfer.effectAllowed = 'copy';
  }
</script>

<aside class="flex h-full w-72 flex-col border-r border-[var(--border-soft)] bg-[var(--bg-canvas)]">
  <nav class="flex border-b border-[var(--border-soft)] text-xs">
    {#each ['steps', 'connectors', 'recipes'] as s}
      {@const k = s as typeof activeSection}
      <button
        type="button"
        class="flex-1 px-3 py-2 font-medium capitalize transition-colors {activeSection === k
          ? 'border-b-2 border-[var(--brand)] text-[var(--text-default)]'
          : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
        onclick={() => (activeSection = k)}
      >{s}</button>
    {/each}
  </nav>

  <div class="flex-1 overflow-auto p-2 text-sm">
    {#if activeSection === 'steps'}
      <ul class="space-y-1">
        {#each stepTypes as st}
          <li>
            <button
              type="button"
              draggable="true"
              ondragstart={(e) => dragStart(e, { kind: 'step_type', type: st.name, label: st.name, detail: st.detail })}
              onclick={() => onPick?.({ kind: 'step_type', type: st.name, label: st.name, detail: st.detail })}
              class="block w-full cursor-grab rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-canvas)] active:cursor-grabbing"
            >
              <div class="font-mono text-[11px] font-semibold text-[var(--text-default)]">{st.name}</div>
              {#if st.detail}<div class="text-[10px] text-[var(--text-faint)]">{st.detail}</div>{/if}
            </button>
          </li>
        {/each}
      </ul>
    {:else if activeSection === 'connectors'}
      <input
        type="search"
        placeholder="filter connectors…"
        bind:value={connectorQuery}
        class="mb-2 w-full rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs"
      />
      <ul class="space-y-1">
        {#each filteredConnectors as c (c.name)}
          <li>
            <button
              type="button"
              onclick={() => expandConnector(c.name)}
              class="flex w-full items-center justify-between rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-left text-xs hover:bg-[var(--bg-canvas)]"
            >
              <span class="font-mono text-[11px]">{c.name}</span>
              {#if c.category}<span class="text-[10px] text-[var(--text-faint)]">{c.category}</span>{/if}
            </button>
            {#if expandedConnector === c.name}
              <ul class="mt-1 space-y-0.5 pl-3">
                {#if connectorOpsLoading}
                  <li class="text-[10px] italic text-[var(--text-faint)]">loading ops…</li>
                {:else if connectorOps.length === 0}
                  <li class="text-[10px] italic text-[var(--text-faint)]">no operations indexed</li>
                {:else}
                  {#each connectorOps as op (op.op_name)}
                    <li>
                      <button
                        type="button"
                        draggable="true"
                        ondragstart={(e) => dragStart(e, { kind: 'connector_op', connector: c.name, operation: op.op_name, title: op.title ?? undefined })}
                        onclick={() => onPick?.({ kind: 'connector_op', connector: c.name, operation: op.op_name, title: op.title ?? undefined })}
                        class="block w-full cursor-grab rounded px-1.5 py-0.5 text-left text-[11px] text-[var(--text-default)] hover:bg-[var(--bg-elev)] active:cursor-grabbing"
                      >
                        <span class="font-mono">{op.op_name}</span>
                        {#if op.title}<span class="ml-1 text-[10px] text-[var(--text-faint)]">{op.title}</span>{/if}
                      </button>
                    </li>
                  {/each}
                {/if}
              </ul>
            {/if}
          </li>
        {/each}
      </ul>
    {:else if activeSection === 'recipes'}
      <ul class="space-y-1">
        {#each recipes as r (r.name)}
          <li>
            <button
              type="button"
              draggable="true"
              ondragstart={(e) => dragStart(e, { kind: 'recipe', name: r.name, recipe_kind: r.kind })}
              onclick={() => onPick?.({ kind: 'recipe', name: r.name, recipe_kind: r.kind })}
              class="block w-full cursor-grab rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-canvas)] active:cursor-grabbing"
            >
              <div class="font-mono text-[11px] font-semibold text-[var(--text-default)]">{r.name}</div>
              <div class="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{r.kind}</div>
              {#if r.when_to_use}<div class="mt-0.5 truncate text-[10px] text-[var(--text-faint)]" title={r.when_to_use}>{r.when_to_use}</div>{/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</aside>
