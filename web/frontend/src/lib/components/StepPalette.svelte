<script lang="ts">
  /**
   * Left rail palette — Steps / Connectors / Recipes.
   * Drag rows onto the canvas, or click to stage via Save flow.
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
  import ConnectorIcon from './ConnectorIcon.svelte';

  type PaletteItem =
    | { kind: 'step_type'; type: string; label: string; detail?: string }
    | { kind: 'connector_op'; connector: string; operation: string; title?: string }
    | { kind: 'recipe'; name: string; recipe_kind: string };

  type Props = { onPick?: (item: PaletteItem) => void };
  let { onPick }: Props = $props();

  type Section = 'steps' | 'connectors' | 'recipes';
  const SECTIONS: { id: Section; label: string }[] = [
    { id: 'steps', label: 'Steps' },
    { id: 'connectors', label: 'Connectors' },
    { id: 'recipes', label: 'Recipes' }
  ];

  let activeSection: Section = $state('steps');
  let stepTypes: StepTypeHint[] = $state([]);
  let connectors: ConnectorRef[] = $state([]);
  let recipes: RecipeRef[] = $state([]);
  let query = $state('');
  let expandedConnector: string | null = $state(null);
  let connectorOps: OperationRef[] = $state([]);
  let connectorOpsLoading = $state(false);

  onMount(async () => {
    try { stepTypes = await getStepTypes(); } catch {}
    try { connectors = await searchConnectors('', 100); } catch {}
    try { recipes = await listRecipes(); } catch {}
  });

  const norm = (s: string) => s.toLowerCase();

  let filteredSteps = $derived(
    query
      ? stepTypes.filter((s) => norm(s.name + ' ' + (s.detail ?? '')).includes(norm(query)))
      : stepTypes
  );
  let filteredConnectors = $derived(
    query
      ? connectors.filter((c) => norm(c.name + ' ' + (c.label ?? '')).includes(norm(query)))
      : connectors
  );
  let filteredRecipes = $derived(
    query
      ? recipes.filter((r) => norm(r.name + ' ' + r.kind + ' ' + (r.when_to_use ?? '')).includes(norm(query)))
      : recipes
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

  function dragStart(e: DragEvent, item: PaletteItem) {
    if (!e.dataTransfer) return;
    e.dataTransfer.setData('application/x-fsrpb-step', JSON.stringify(item));
    e.dataTransfer.effectAllowed = 'copy';
  }

  function placeholder(s: Section) {
    return s === 'steps' ? 'Search step types…' : s === 'connectors' ? 'Search connectors…' : 'Search recipes…';
  }

  /** Map a step type name to one of the 8 canvas families used by
   *  StepNode.svelte so palette rows match the node colors on drop. */
  type Family =
    | 'trigger' | 'connector_op' | 'decision' | 'record_crud'
    | 'utility' | 'manual_input' | 'workflow_ref' | 'terminal';

  function stepFamily(name: string): Family {
    const n = name.toLowerCase();
    if (n.includes('trigger') || n.includes('start_on_create') || n.includes('start_on_update')) return 'trigger';
    if (n.includes('decision') || n.includes('condition') || n.includes('branch')) return 'decision';
    if (n.includes('manual_input') || n.includes('approval') || n.includes('input')) return 'manual_input';
    if (n.includes('record') || n.includes('module') || n.includes('ingest')) return 'record_crud';
    if (n.includes('reference') || n.includes('execute_playbook') || n.includes('subroutine')) return 'workflow_ref';
    if (n.includes('raise') || n.includes('exception') || n.includes('terminate')) return 'terminal';
    if (n.includes('connector') || n.includes('http') || n.includes('rest')) return 'connector_op';
    return 'utility';
  }
</script>

<aside class="palette">
  <div class="palette-header">
    <div class="seg" role="tablist">
      {#each SECTIONS as s}
        <button
          type="button"
          role="tab"
          aria-selected={activeSection === s.id}
          class="seg-btn"
          class:active={activeSection === s.id}
          onclick={() => (activeSection = s.id)}
        >{s.label}</button>
      {/each}
    </div>
    <div class="search">
      <svg class="search-icon" viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.5"/>
        <path d="M10.5 10.5 L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <input
        type="search"
        placeholder={placeholder(activeSection)}
        bind:value={query}
      />
      {#if query}
        <button class="clear" type="button" aria-label="Clear" onclick={() => (query = '')}>×</button>
      {/if}
    </div>
  </div>

  <div class="palette-body">
    {#if activeSection === 'steps'}
      {#if filteredSteps.length === 0}
        <p class="empty">No matching step types.</p>
      {:else}
        <ul class="rows">
          {#each filteredSteps as st}
            <li>
              <button
                type="button"
                draggable="true"
                ondragstart={(e) => dragStart(e, { kind: 'step_type', type: st.name, label: st.name, detail: st.detail })}
                onclick={() => onPick?.({ kind: 'step_type', type: st.name, label: st.name, detail: st.detail })}
                class="row fam-{stepFamily(st.name)}"
              >
                <span class="row-stripe" aria-hidden="true"></span>
                <span class="row-glyph" aria-hidden="true">⊞</span>
                <span class="row-body">
                  <span class="row-title">{st.name}</span>
                  {#if st.detail}<span class="row-sub">{st.detail}</span>{/if}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    {:else if activeSection === 'connectors'}
      {#if filteredConnectors.length === 0}
        <p class="empty">No matching connectors.</p>
      {:else}
        <ul class="rows">
          {#each filteredConnectors as c (c.name)}
            <li>
              <button
                type="button"
                onclick={() => expandConnector(c.name)}
                class="row fam-connector_op"
                class:open={expandedConnector === c.name}
              >
                <span class="row-stripe" aria-hidden="true"></span>
                <span class="row-glyph"><ConnectorIcon name={c.name} size="sm" /></span>
                <span class="row-body">
                  <span class="row-title">{c.label ?? c.name}</span>
                  {#if c.label && c.label !== c.name}<span class="row-sub">{c.name}</span>{/if}
                </span>
                {#if c.category}<span class="chip chip-tinted">{c.category}</span>{/if}
                <span class="caret" class:open={expandedConnector === c.name} aria-hidden="true">▸</span>
              </button>
              {#if expandedConnector === c.name}
                <ul class="ops">
                  {#if connectorOpsLoading}
                    <li class="ops-empty">Loading operations…</li>
                  {:else if connectorOps.length === 0}
                    <li class="ops-empty">No operations indexed.</li>
                  {:else}
                    {#each connectorOps as op (op.op_name)}
                      <li>
                        <button
                          type="button"
                          draggable="true"
                          ondragstart={(e) => dragStart(e, { kind: 'connector_op', connector: c.name, operation: op.op_name, title: op.title ?? undefined })}
                          onclick={() => onPick?.({ kind: 'connector_op', connector: c.name, operation: op.op_name, title: op.title ?? undefined })}
                          class="op"
                        >
                          <span class="op-name">{op.title ?? op.op_name}</span>
                          {#if op.title}<span class="op-id">{op.op_name}</span>{/if}
                        </button>
                      </li>
                    {/each}
                  {/if}
                </ul>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    {:else}
      {#if filteredRecipes.length === 0}
        <p class="empty">No matching recipes.</p>
      {:else}
        <ul class="rows">
          {#each filteredRecipes as r (r.name)}
            <li>
              <button
                type="button"
                draggable="true"
                ondragstart={(e) => dragStart(e, { kind: 'recipe', name: r.name, recipe_kind: r.kind })}
                onclick={() => onPick?.({ kind: 'recipe', name: r.name, recipe_kind: r.kind })}
                class="row fam-workflow_ref"
              >
                <span class="row-stripe" aria-hidden="true"></span>
                <span class="row-glyph" aria-hidden="true">★</span>
                <span class="row-body">
                  <span class="row-title">{r.name}</span>
                  {#if r.when_to_use}<span class="row-sub" title={r.when_to_use}>{r.when_to_use}</span>{/if}
                </span>
                <span class="chip chip-tinted">{r.kind}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    {/if}
  </div>
</aside>

<style>
  .palette {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 18rem;
    background: var(--bg-canvas);
    border-right: 1px solid var(--border-soft);
  }

  .palette-header {
    padding: 10px 10px 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    border-bottom: 1px solid var(--border-soft);
  }

  .seg {
    display: flex;
    padding: 2px;
    background: var(--bg-elev, var(--bg-elevated));
    border: 1px solid var(--border-soft);
    border-radius: 8px;
    gap: 2px;
  }
  .seg-btn {
    flex: 1;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.01em;
    color: var(--text-muted);
    border-radius: 6px;
    background: transparent;
    border: none;
    cursor: pointer;
    transition: background 120ms, color 120ms;
  }
  .seg-btn:hover { color: var(--text-default); }
  .seg-btn.active {
    background: var(--bg-canvas);
    color: var(--text-default);
    box-shadow: 0 1px 0 0 var(--border-soft), 0 0 0 1px var(--border-soft);
  }

  .search {
    position: relative;
    display: flex;
    align-items: center;
  }
  .search input {
    width: 100%;
    padding: 6px 24px 6px 26px;
    font-size: 12px;
    color: var(--text-default);
    background: var(--bg-elev, var(--bg-elevated));
    border: 1px solid var(--border-soft);
    border-radius: 6px;
    outline: none;
    transition: border-color 120ms, box-shadow 120ms;
  }
  .search input::placeholder { color: var(--text-faint); }
  .search input:focus {
    border-color: var(--brand);
    box-shadow: 0 0 0 2px var(--brand-ring);
  }
  .search-icon {
    position: absolute;
    left: 8px;
    width: 12px;
    height: 12px;
    color: var(--text-faint);
    pointer-events: none;
  }
  .clear {
    position: absolute;
    right: 4px;
    width: 18px;
    height: 18px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-faint);
    font-size: 14px;
    line-height: 1;
    cursor: pointer;
  }
  .clear:hover { color: var(--text-default); background: var(--bg-canvas); }

  .palette-body {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }
  .palette-body::-webkit-scrollbar { width: 8px; }
  .palette-body::-webkit-scrollbar-thumb {
    background: var(--border-soft);
    border-radius: 4px;
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 8px 7px 12px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--text-default);
    text-align: left;
    cursor: grab;
    transition: background 100ms, border-color 100ms, transform 60ms;
    --hue: var(--brand);
    --hue-soft: var(--brand-soft);
    --hue-ring: var(--brand-ring);
  }
  .row:hover {
    background: var(--hue-soft);
    border-color: var(--hue-ring);
  }
  .row:hover .row-glyph { color: var(--hue); }
  .row:active { cursor: grabbing; transform: translateY(1px); }
  .row.open {
    background: var(--hue-soft);
    border-color: var(--hue-ring);
  }
  .row.open .row-glyph { color: var(--hue); }

  .row-stripe {
    position: absolute;
    left: 3px;
    top: 7px;
    bottom: 7px;
    width: 2px;
    border-radius: 2px;
    background: var(--hue);
    opacity: 0.55;
  }
  .row:hover .row-stripe,
  .row.open .row-stripe { opacity: 1; }

  /* Family palette — colors mirror StepNode.svelte's FAMILY_STYLE so
     a row in the palette matches the node it spawns on the canvas. */
  .fam-trigger      { --hue: #d97706; --hue-soft: rgba(217,119,6,0.12);   --hue-ring: rgba(217,119,6,0.45); }
  .fam-connector_op { --hue: #2563eb; --hue-soft: rgba(37,99,235,0.13);   --hue-ring: rgba(37,99,235,0.45); }
  .fam-decision     { --hue: #7c3aed; --hue-soft: rgba(124,58,237,0.13);  --hue-ring: rgba(124,58,237,0.45); }
  .fam-record_crud  { --hue: #16a34a; --hue-soft: rgba(22,163,74,0.13);   --hue-ring: rgba(22,163,74,0.45); }
  .fam-utility      { --hue: #6b7280; --hue-soft: rgba(107,114,128,0.14); --hue-ring: rgba(107,114,128,0.45); }
  .fam-manual_input { --hue: #ca8a04; --hue-soft: rgba(202,138,4,0.13);   --hue-ring: rgba(202,138,4,0.45); }
  .fam-workflow_ref { --hue: #a21caf; --hue-soft: rgba(162,28,175,0.13);  --hue-ring: rgba(162,28,175,0.45); }
  .fam-terminal     { --hue: #b91c1c; --hue-soft: rgba(185,28,28,0.13);   --hue-ring: rgba(185,28,28,0.45); }

  .row-glyph {
    flex: 0 0 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .row-body {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .row-title {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-default);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .row-sub {
    font-size: 10.5px;
    color: var(--text-faint);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .chip {
    flex: 0 0 auto;
    padding: 1px 6px;
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-muted);
    background: var(--bg-canvas);
    border: 1px solid var(--border-soft);
    border-radius: 4px;
  }

  .caret {
    flex: 0 0 auto;
    font-size: 9px;
    color: var(--text-faint);
    transition: transform 120ms;
  }
  .caret.open { transform: rotate(90deg); color: var(--brand); }

  .ops {
    list-style: none;
    margin: 2px 0 4px;
    padding: 2px 0 2px 22px;
    border-left: 1px solid var(--border-soft);
    margin-left: 16px;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .op {
    display: flex;
    align-items: baseline;
    gap: 6px;
    width: 100%;
    padding: 4px 8px;
    background: transparent;
    border: none;
    border-radius: 4px;
    color: var(--text-default);
    text-align: left;
    cursor: grab;
    transition: background 100ms;
  }
  .op:hover { background: var(--bg-elev, var(--bg-elevated)); }
  .op:active { cursor: grabbing; }
  .op-name {
    flex: 1 1 auto;
    font-size: 11.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .op-id {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 10px;
    color: var(--text-faint);
    white-space: nowrap;
  }
  .ops-empty {
    padding: 4px 8px;
    font-size: 10.5px;
    font-style: italic;
    color: var(--text-faint);
  }

  .empty {
    padding: 16px 8px;
    margin: 0;
    text-align: center;
    font-size: 11.5px;
    color: var(--text-faint);
  }
</style>
