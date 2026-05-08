<script lang="ts">
  /**
   * Custom xyflow node template for a playbook step.
   *
   * Collapses the 43 FSR step types into seven visual families
   * (driven by `node.family` from the backend). Color/icon scheme is
   * intentionally distinct so the canvas can be skimmed at a glance.
   */
  import { Handle, Position, type NodeProps } from '@xyflow/svelte';
  import type { VisualNode } from '../api';
  import { visualStore } from '../visualEditStore.svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';

  let props: NodeProps = $props();
  let node = $derived(props.data.node as VisualNode);
  let verification = $derived(props.data.verification as { status: string } | null);
  let direction = $derived((props.data.direction as 'TB' | 'LR' | undefined) ?? 'TB');
  let playbookIdx = $derived((props.data.playbookIdx as number | undefined) ?? 0);

  /** G43: + add-next-step popover. Shown next to the source handle so
   * the user can spawn a connected downstream node without dragging
   * from the left palette + drawing an edge. Common step types only;
   * the palette stays the source of truth for the long tail. */
  let menuOpen = $state(false);

  type QuickType = { type: string; label: string; family?: VisualNode['family'] };
  const QUICK_TYPES: QuickType[] = [
    { type: 'set_variable', label: 'Set Variable', family: 'utility' },
    { type: 'connector', label: 'Connector Action', family: 'connector_op' },
    { type: 'decision', label: 'Decision', family: 'decision' },
    { type: 'manual_input', label: 'Manual Input', family: 'manual_input' },
    { type: 'create_record', label: 'Create Record', family: 'record_crud' },
    { type: 'update_record', label: 'Update Record', family: 'record_crud' },
    { type: 'find_records', label: 'Find Records', family: 'record_crud' },
    { type: 'utils_delay', label: 'Delay', family: 'utility' },
    { type: 'code_snippet', label: 'Code Snippet', family: 'utility' },
    { type: 'raise_exception', label: 'Raise Exception', family: 'terminal' }
  ];

  function spawn(t: QuickType) {
    menuOpen = false;
    const pos = node.position;
    const offset = direction === 'LR' ? { x: 320, y: 0 } : { x: 0, y: 160 };
    const nextPos = pos ? { x: pos.x + offset.x, y: pos.y + offset.y } : undefined;
    visualStore.addNode(
      playbookIdx,
      {
        type: t.type,
        name: t.label,
        family: t.family,
        arguments: t.type === 'connector' ? { connector: '', operation: '', params: {} } : {}
      },
      { predecessorId: node.id, splice: false, position: nextPos }
    );
  }

  function toggleMenu(e: MouseEvent) {
    e.stopPropagation();
    menuOpen = !menuOpen;
  }
  // xyflow flips `selected` true on the NodeProps when the user clicks
  // the node. We use it to brighten the border + add a ring so the
  // selection is unmistakable on the canvas (G34).
  let selected = $derived(!!(props as any).selected);

  const FAMILY_STYLE: Record<VisualNode['family'], { bg: string; border: string; label: string }> = {
    trigger:        { bg: '#fef3c7', border: '#d97706', label: 'Trigger' },
    connector_op:   { bg: '#dbeafe', border: '#2563eb', label: 'Connector' },
    decision:       { bg: '#ede9fe', border: '#7c3aed', label: 'Decision' },
    record_crud:    { bg: '#dcfce7', border: '#16a34a', label: 'Record' },
    utility:        { bg: '#f3f4f6', border: '#6b7280', label: 'Utility' },
    manual_input:   { bg: '#fef9c3', border: '#ca8a04', label: 'Manual Input' },
    workflow_ref:   { bg: '#fae8ff', border: '#a21caf', label: 'Workflow Ref' },
    terminal:       { bg: '#fee2e2', border: '#b91c1c', label: 'Terminal' }
  };

  let style = $derived(FAMILY_STYLE[node.family] ?? FAMILY_STYLE.utility);

  // Pull a couple of leading args to render in the body so the user
  // doesn't have to open the inspector to see what the step does.
  let summary = $derived(buildSummary(node));

  function buildSummary(n: VisualNode): string {
    if (n.family === 'connector_op') {
      const c = n.arguments?.connector as string | undefined;
      const op = (n.arguments?.operation as string | undefined) ?? n.type;
      return `${c ?? '?'} · ${op}`;
    }
    if (n.family === 'decision') {
      const conds = (n.arguments?.conditions as unknown[]) ?? [];
      return `${conds.length} branch${conds.length === 1 ? '' : 'es'}`;
    }
    if (n.family === 'record_crud') {
      const m = (n.arguments?.module as string | undefined) ?? (n.arguments?.collection as string | undefined);
      return m ? `module: ${m}` : '';
    }
    if (n.family === 'utility' && n.type === 'set_variable') {
      const al = n.arguments?.arg_list as { name?: string }[] | undefined;
      const names = al?.map((a) => a.name).filter(Boolean) ?? [];
      return names.length ? names.slice(0, 3).join(', ') + (names.length > 3 ? '…' : '') : '';
    }
    return '';
  }

  const VERIF_DOT: Record<string, string> = {
    tested_pass: '#16a34a',
    tested_fail: '#dc2626',
    seen: '#9ca3af'
  };
</script>

<div
  class="rounded-lg border-2 px-3 py-2 shadow-sm transition-all hover:shadow-md {selected ? 'fsrpb-step-selected' : ''}"
  style="background: {style.bg}; border-color: {style.border}; min-width: 200px; max-width: 240px;"
  data-selected={selected}
>
  <!-- G41 + G44: source AND target handles on all four sides. Edges
       pick which pair to use per-edge based on the relative positions
       of source/target nodes (computed in PlaybookCanvas), so each
       line takes the shortest path instead of forcing every line to
       leave from one fixed side of the node. -->
  <Handle type="target" position={Position.Top}    id="top-t" />
  <Handle type="source" position={Position.Top}    id="top-s" />
  <Handle type="target" position={Position.Right}  id="right-t" />
  <Handle type="source" position={Position.Right}  id="right-s" />
  <Handle type="target" position={Position.Bottom} id="bottom-t" />
  <Handle type="source" position={Position.Bottom} id="bottom-s" />
  <Handle type="target" position={Position.Left}   id="left-t" />
  <Handle type="source" position={Position.Left}   id="left-s" />
  <div class="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wide" style="color: {style.border}">
    <span>{style.label}</span>
    {#if verification}
      <span
        class="inline-block h-2 w-2 rounded-full"
        title="verification: {verification.status}"
        style="background: {VERIF_DOT[verification.status] ?? '#9ca3af'}"
        aria-label="verification {verification.status}"
      ></span>
    {/if}
  </div>
  <div class="mt-1 flex items-center gap-2">
    {#if node.family === 'connector_op' && node.arguments?.connector}
      <ConnectorIcon name={node.arguments.connector as string} size="sm" />
    {/if}
    <div class="truncate text-sm font-medium text-gray-900">{node.name}</div>
  </div>
  {#if summary}
    <div class="mt-0.5 truncate text-xs text-gray-600">{summary}</div>
  {/if}
  <!-- G43: + add-next-step button + menu. Positioned just past the
       source handle so it sits between this node and where the next
       one will land. Visible on hover or selection. -->
  <button
    type="button"
    class="fsrpb-add-next nodrag nopan"
    class:fsrpb-add-next--lr={direction === 'LR'}
    class:fsrpb-add-next--tb={direction !== 'LR'}
    aria-label="Add next step"
    title="Add next step"
    onclick={toggleMenu}
  >+</button>
  {#if menuOpen}
    <div
      class="fsrpb-add-next-menu nodrag nopan"
      class:fsrpb-add-next-menu--lr={direction === 'LR'}
      class:fsrpb-add-next-menu--tb={direction !== 'LR'}
      role="menu"
    >
      {#each QUICK_TYPES as qt}
        <button
          type="button"
          class="fsrpb-add-next-item"
          role="menuitem"
          onclick={(e) => { e.stopPropagation(); spawn(qt); }}
        >{qt.label}</button>
      {/each}
    </div>
  {/if}
</div>

<style>
  /* Selection highlight: thicker ring + glow so the active step is
     unmistakable even on a dense canvas. */
  :global(.fsrpb-step-selected) {
    box-shadow:
      0 0 0 3px var(--brand, #6366f1),
      0 0 12px rgba(99, 102, 241, 0.5),
      0 4px 12px rgba(0, 0, 0, 0.18);
    transform: translateY(-1px);
  }

  /* xyflow's Handle circles are the "drag-an-edge-end-here" dots. The
     user only wants them visible while they're engaging with a LINE
     (hovering or selected) — not whenever a node is touched. So we
     hide them at rest and show them globally whenever any edge in the
     flow is hovered or selected. The handle's hit area is invisible
     but still receives drops for the in-progress reconnect drag. */
  :global(.svelte-flow__handle) {
    opacity: 0;
    transition: opacity 120ms ease, transform 120ms ease;
    /* Bigger hit area for drag-out — small dots are awkward targets. */
    width: 12px !important;
    height: 12px !important;
    background: var(--brand, #6366f1) !important;
    border: 2px solid white !important;
  }
  /* G52: surface handles whenever the user hovers ANY node so starting
     a new edge is discoverable. Previously handles were hidden until
     an existing edge was hovered/selected — that worked for reconnect
     but not for first-time edge creation. */
  :global(.svelte-flow__node:hover .svelte-flow__handle),
  :global(.svelte-flow:has(.svelte-flow__edge:hover) .svelte-flow__handle),
  :global(.svelte-flow:has(.svelte-flow__edge.selected) .svelte-flow__handle),
  :global(.svelte-flow__handle.connecting),
  :global(.svelte-flow__handle.connectingfrom),
  :global(.svelte-flow__handle.connectingto) {
    opacity: 1;
  }
  /* Center handles ON the node border so edge endpoints connect
     flush to the node — pushing them fully outside (translate 100%)
     creates a visible gap because xyflow draws the edge line to the
     handle center. Half-in / half-out is xyflow's default and is the
     only configuration that doesn't leave a stranded line endpoint. */
  :global(.svelte-flow__handle:hover) {
    cursor: crosshair;
    box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.25);
  }

  /* G43: + button to spawn a connected downstream node. Hidden at
     rest, surfaced on hover/selection of the host node. Sized so it
     overlaps the source handle slightly without obscuring it. */
  .fsrpb-add-next {
    position: absolute;
    width: 22px;
    height: 22px;
    border-radius: 999px;
    border: 1.5px solid #6366f1;
    background: white;
    color: #6366f1;
    font-size: 16px;
    line-height: 1;
    font-weight: 600;
    cursor: pointer;
    opacity: 0;
    transition: opacity 120ms ease, transform 120ms ease;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }
  /* Far enough out that the + clears the bottom/right connection
     handle (which sits ~12 px outside the node border) instead of
     overlapping it. Stays centered on the source axis. */
  .fsrpb-add-next--tb {
    bottom: -42px;
    left: 50%;
    transform: translateX(-50%);
  }
  .fsrpb-add-next--lr {
    right: -42px;
    top: 50%;
    transform: translateY(-50%);
  }
  /* Show on host-node hover, on selection, or when the menu is open. */
  div:hover > .fsrpb-add-next,
  div[data-selected="true"] > .fsrpb-add-next,
  .fsrpb-add-next:focus,
  .fsrpb-add-next:hover {
    opacity: 1;
  }
  .fsrpb-add-next:hover {
    background: #6366f1;
    color: white;
  }

  .fsrpb-add-next-menu {
    position: absolute;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    padding: 4px;
    min-width: 180px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .fsrpb-add-next-menu--tb {
    top: calc(100% + 36px);
    left: 50%;
    transform: translateX(-50%);
  }
  .fsrpb-add-next-menu--lr {
    left: calc(100% + 36px);
    top: 50%;
    transform: translateY(-50%);
  }
  .fsrpb-add-next-item {
    text-align: left;
    background: transparent;
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    color: #1f2937;
  }
  .fsrpb-add-next-item:hover {
    background: #eef2ff;
    color: #4338ca;
  }

  /* Hoist the host xyflow node above its siblings while the menu is
     open so the popover isn't covered by the next node's body. xyflow
     stamps a per-node z-index inline, so we have to win on the
     wrapper, not just on .fsrpb-add-next-menu. */
  :global(.svelte-flow__node:has(.fsrpb-add-next-menu)) {
    z-index: 1000 !important;
  }
</style>
