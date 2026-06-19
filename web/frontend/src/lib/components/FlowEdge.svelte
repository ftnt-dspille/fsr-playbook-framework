<script lang="ts">
  /**
   * Custom edge component (G32 + G33).
   *
   * - Always renders an arrowhead (`markerEnd`) so the user can read
   *   flow direction at a glance.
   * - Adds visible `EdgeReconnectAnchor` dots at the source and target
   *   ends so dragging an endpoint to a different node is discoverable.
   *   Default xyflow edges have no visible reconnect handles.
   * - Picks bezier vs smoothstep path based on direction (LR uses
   *   smoothstep, TB uses bezier — matches the canvas's per-direction
   *   `type` hint we used to pass at the edge level).
   */
  import {
    BaseEdge,
    EdgeLabel,
    EdgeReconnectAnchor,
    getBezierPath,
    type EdgeProps
  } from '@xyflow/svelte';
  import { visualStore } from '../visualEditStore.svelte';

  let props: EdgeProps = $props();
  let isBranch = $derived((props.data as { branch_kind?: string } | undefined)?.branch_kind === 'branch');
  let edgeData = $derived(props.data as { label?: string | null; branch_kind?: string; playbookIdx?: number } | undefined);
  // xyflow flips `selected` on the EdgeProps when the user clicks the
  // edge. We use it to gate every interactive overlay (delete × +
  // reconnect anchors) since EdgeReconnectAnchor is portaled OUT of
  // `.svelte-flow__edge` — descendant CSS gates don't reach it.
  let isSelected = $derived(!!(props as any).selected);

  function deleteEdge() {
    const idx = edgeData?.playbookIdx ?? 0;
    visualStore.removeEdge(idx, {
      source: props.source,
      target: props.target,
      label: edgeData?.label ?? null
    });
  }

  // Bezier curves naturally between any pair of handle positions, so it
  // looks clean in both TB and LR layouts and when the user has dragged
  // nodes off the auto-layout grid. Smoothstep only beats it when the
  // source/target are perfectly orthogonal — which is rarely the case
  // after a few hand-edits.
  let pathInfo = $derived(
    getBezierPath({
      sourceX: props.sourceX,
      sourceY: props.sourceY,
      sourcePosition: props.sourcePosition,
      targetX: props.targetX,
      targetY: props.targetY,
      targetPosition: props.targetPosition
    })
  );
  let path = $derived(pathInfo[0]);
  let labelX = $derived(pathInfo[1]);
  let labelY = $derived(pathInfo[2]);

  // Stroke color drives both the line AND the arrowhead (we set
  // `color` on `markerEnd` to match). Branch edges = amber, default
  // edges = slate so the arrow is always visible against any theme.
  const STROKE_DEFAULT = '#94a3b8';   // slate-400
  const STROKE_BRANCH = '#f59e0b';    // amber-500
  let stroke = $derived(isBranch ? STROKE_BRANCH : STROKE_DEFAULT);
</script>

<BaseEdge
  id={props.id}
  {path}
  {labelX}
  {labelY}
  label={props.label}
  labelStyle={props.labelStyle}
  style={`stroke: ${stroke}; stroke-width: 1.75;`}
  markerEnd={props.markerEnd}
  interactionWidth={props.interactionWidth ?? 20}
/>

{#if isSelected}
  <!--
    Mid-edge delete button — visible only when the edge is selected.
    Saves a trip to the right-click context menu for the most common
    edit (drop a connection).
  -->
  <EdgeLabel x={labelX} y={labelY} transparent>
    <button
      type="button"
      class="fsrpb-edge-delete"
      aria-label="Delete edge"
      title="Delete edge"
      onclick={deleteEdge}
    >×</button>
  </EdgeLabel>

  <!--
    Reconnect handles at source + target endpoints. xyflow portals
    these out of the .svelte-flow__edge element, so descendant CSS
    can't gate them — we conditionally render instead.
  -->
  <EdgeReconnectAnchor
    type="source"
    position={{ x: props.sourceX, y: props.sourceY }}
    size={14}
  >
    <div class="fsrpb-edge-anchor"></div>
  </EdgeReconnectAnchor>
  <EdgeReconnectAnchor
    type="target"
    position={{ x: props.targetX, y: props.targetY }}
    size={14}
  >
    <div class="fsrpb-edge-anchor fsrpb-edge-anchor--target"></div>
  </EdgeReconnectAnchor>
{/if}

<style>
  /* Drag-an-edge-end dot. Only rendered while the edge is selected
     (see `{#if isSelected}` above), so a single visible style is enough. */
  :global(.fsrpb-edge-anchor) {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--brand, #6366f1);
    border: 2px solid var(--bg-canvas, #fff);
    opacity: 0.95;
    cursor: grab;
    transition: transform 120ms ease;
  }
  :global(.fsrpb-edge-anchor:hover) {
    transform: scale(1.3);
  }
  :global(.fsrpb-edge-anchor:active) {
    cursor: grabbing;
  }
  :global(.fsrpb-edge-anchor--target) {
    background: #f59e0b;            /* amber-500 — matches branch arrow */
  }

  /* Mid-edge × delete button. Same selection-only conditional render. */
  :global(.fsrpb-edge-delete) {
    width: 22px;
    height: 22px;
    line-height: 18px;
    border-radius: 50%;
    background: #1f2937;            /* slate-800 */
    border: 1.5px solid #ef4444;    /* red-500 */
    color: #fca5a5;                 /* red-300 */
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 120ms ease, background 120ms ease, color 120ms ease;
  }
  :global(.fsrpb-edge-delete:hover) {
    background: #ef4444;
    color: #fff;
    transform: scale(1.1);
  }
</style>
