<script lang="ts">
  /**
   * Read-only @xyflow/svelte canvas for a single playbook.
   *
   * Phase 1.1–1.4: renders nodes for the seven step-type families,
   * shows verification status badges (1.3), and emits a `select`
   * event so the host page can render the right-hand inspector
   * panel (1.4). Editing comes in Phase 3.
   */
  import { SvelteFlow, Background, Controls, MiniMap, MarkerType, type Node, type Edge } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';
  import { onMount, untrack } from 'svelte';
  import type { VisualPlaybook, VisualNode } from '../api';
  import { callMcpTool } from '../api';
  import { autoLayout } from '../visualLayout';
  import StepNode from './StepNode.svelte';
  import FlowEdge from './FlowEdge.svelte';

  import { visualStore } from '../visualEditStore.svelte';

  type DropPayload =
    | { kind: 'step_type'; type: string; label: string; detail?: string }
    | { kind: 'connector_op'; connector: string; operation: string; title?: string }
    | { kind: 'recipe'; name: string; recipe_kind: string };

  type Props = {
    playbook: VisualPlaybook;
    playbookIdx: number;
    direction?: 'TB' | 'LR';
    onSelect?: (node: VisualNode | null) => void;
  };
  let { playbook, playbookIdx, direction = 'TB', onSelect }: Props = $props();

  const nodeTypes = { step: StepNode };
  const edgeTypes = { default: FlowEdge, smoothstep: FlowEdge, bezier: FlowEdge };

  // Verification badges keyed by node id, hydrated post-mount via the
  // generic /api/mcp dispatcher (Phase 0.1).
  let verifs: Record<string, { status: string } | null> = $state({});

  function verificationKey(n: VisualNode): { kind: string; key: string } | null {
    if (n.family === 'connector_op') {
      const c = n.arguments?.connector as string | undefined;
      const op = (n.arguments?.operation as string | undefined) ?? n.type;
      if (c && op) return { kind: 'operation', key: `${c}:${op}` };
    }
    return null;
  }

  async function hydrateVerifications(nodes: VisualNode[]) {
    const tasks = nodes.map(async (n) => {
      const k = verificationKey(n);
      if (!k) return [n.id, null] as const;
      try {
        const r = await callMcpTool<{ found: boolean; status?: string }>('verification_status', k);
        if (r.ok && r.result?.found) return [n.id, { status: r.result.status! }] as const;
      } catch {}
      return [n.id, null] as const;
    });
    const out = await Promise.all(tasks);
    verifs = Object.fromEntries(out);
  }

  let positioned = $derived(autoLayout(playbook.nodes, playbook.edges, direction));

  /** G44: pick the source/target handle pair that gives the shortest
   * connection between two laid-out nodes. Each node carries handles
   * on all four sides; we compare node-center deltas and route via
   * the dominant axis so edges no longer all leave from one fixed
   * side and have to wrap around the node. */
  function pickHandles(srcId: string, tgtId: string): { sourceHandle: string; targetHandle: string } {
    const a = positioned.find((n) => n.id === srcId);
    const b = positioned.find((n) => n.id === tgtId);
    if (!a || !b) return { sourceHandle: 'bottom-s', targetHandle: 'top-t' };
    const ax = a.position.x + NODE_WIDTH / 2;
    const ay = a.position.y + NODE_HEIGHT / 2;
    const bx = b.position.x + NODE_WIDTH / 2;
    const by = b.position.y + NODE_HEIGHT / 2;
    const dx = bx - ax;
    const dy = by - ay;
    if (Math.abs(dy) >= Math.abs(dx)) {
      return dy >= 0
        ? { sourceHandle: 'bottom-s', targetHandle: 'top-t' }
        : { sourceHandle: 'top-s', targetHandle: 'bottom-t' };
    }
    return dx >= 0
      ? { sourceHandle: 'right-s', targetHandle: 'left-t' }
      : { sourceHandle: 'left-s', targetHandle: 'right-t' };
  }

  let nodes = $derived<Node[]>(
    positioned.map((n) => ({
      id: n.id,
      type: 'step',
      position: n.position,
      data: {
        node: n,
        verification: verifs[n.id] ?? null,
        direction,
        playbookIdx
      }
    }))
  );

  // Single arrow marker for every edge so flow direction is obvious.
  // Branch edges get the amber accent; ordinary `next` edges get the
  // CSS-driven default stroke (resolved against the active theme).
  let edges = $derived<Edge[]>(
    playbook.edges.map((e, idx) => {
      const { sourceHandle, targetHandle } = pickHandles(e.source, e.target);
      return ({
      id: `${e.source}->${e.target}#${e.label ?? ''}#${idx}`,
      source: e.source,
      target: e.target,
      sourceHandle,
      targetHandle,
      label: e.label ?? undefined,
      reconnectable: true,
      // FlowEdge always renders a bezier, which curves cleanly between
      // any pair of handle positions (TB or LR, post-hand-edit drift,
      // etc). No need to switch edge types per direction.
      type: 'default',
      data: { label: e.label, branch_kind: e.branch_kind, direction, playbookIdx },
      animated: false,
      // Explicit hex (not CSS var) — SVG markers don't inherit
      // `currentColor` and a missing color renders the arrowhead
      // invisible. Match the stroke palette in FlowEdge so the
      // arrow blends cleanly into the line.
      // No explicit width/height — xyflow's defaults position the
      // arrow tip flush with the target handle. Setting custom sizes
      // pushes the line endpoint inward and creates a visible gap
      // between the line and the node border.
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: e.branch_kind === 'branch' ? '#f59e0b' : '#94a3b8'
      }
    });
    })
  );

  function handleEdgeContextMenu({ edge, event }: { edge: Edge; event: MouseEvent }) {
    event.preventDefault();
    const label = (edge.data?.label as string | null) ?? null;
    if (!confirm(`Delete edge ${edge.source} → ${edge.target}${label ? ` (${label})` : ''}?`)) return;
    visualStore.removeEdge(playbookIdx, { source: edge.source, target: edge.target, label });
  }

  function handleReconnect({ oldEdge, newConnection }: any) {
    const label = (oldEdge.data?.label as string | null) ?? null;
    const targetChanged = newConnection.target && newConnection.target !== oldEdge.target;
    const sourceChanged = newConnection.source && newConnection.source !== oldEdge.source;
    if (!targetChanged && !sourceChanged) return;
    if (sourceChanged) {
      visualStore.retargetEdgeSource(
        playbookIdx,
        { source: oldEdge.source, target: oldEdge.target, label },
        newConnection.source
      );
    }
    if (targetChanged) {
      const srcKey = sourceChanged ? newConnection.source : oldEdge.source;
      visualStore.retargetEdge(
        playbookIdx,
        { source: srcKey, target: oldEdge.target, label },
        newConnection.target
      );
    }
  }

  function handleConnect({ source, target }: { source: string; target: string }) {
    if (!source || !target || source === target) return;
    visualStore.addEdge(playbookIdx, { source, target });
  }

  function handleNodeDragStop({ targetNode }: { targetNode: Node | null }) {
    if (!targetNode) return;
    visualStore.setPosition(playbookIdx, targetNode.id, {
      x: Math.round(targetNode.position.x),
      y: Math.round(targetNode.position.y)
    });
  }

  onMount(() => {
    untrack(() => hydrateVerifications(playbook.nodes));
  });

  function handleNodeClick({ node }: { node: Node }) {
    onSelect?.(node.data.node as VisualNode);
  }

  // ---- Phase 3.2/3.3 drag/drop handling ---------------------------

  let dropTargetEl: HTMLDivElement | null = $state(null);

  function decode(e: DragEvent): DropPayload | null {
    const raw = e.dataTransfer?.getData('application/x-fsrpb-step');
    if (!raw) return null;
    try { return JSON.parse(raw) as DropPayload; } catch { return null; }
  }

  function nameForPayload(p: DropPayload): string {
    if (p.kind === 'step_type') return p.label || p.type;
    if (p.kind === 'connector_op') return p.title || p.operation;
    return p.name;
  }

  function templateFor(p: DropPayload) {
    if (p.kind === 'connector_op') {
      return {
        type: 'connector',
        name: nameForPayload(p),
        arguments: { connector: p.connector, operation: p.operation, params: {} },
        family: 'connector_op' as const
      };
    }
    if (p.kind === 'recipe') {
      // Recipes drop as a placeholder for now — Phase 3.2 inserts a
      // single annotated node and leaves expansion to a follow-up
      // (full subgraph expansion is tracked under Phase 3.3 follow-ups).
      return {
        type: 'set_variable',
        name: `Recipe: ${p.name}`,
        arguments: {},
        family: 'utility' as const
      };
    }
    return {
      type: p.type,
      name: nameForPayload(p),
      arguments: {}
    };
  }

  function findClosestNodeId(clientX: number, clientY: number): string | null {
    if (!dropTargetEl) return null;
    const elements = dropTargetEl.querySelectorAll('[data-id]');
    let best: { id: string; d: number } | null = null;
    for (const el of Array.from(elements)) {
      const r = (el as HTMLElement).getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const d = Math.hypot(clientX - cx, clientY - cy);
      const id = (el as HTMLElement).dataset.id;
      if (id && (best === null || d < best.d)) best = { id, d };
    }
    return best && best.d < 220 ? best.id : null;
  }

  /**
   * Convert a screen-space (clientX, clientY) drop point into xyflow's
   * flow-coordinate space by reading the canvas wrapper rect and
   * inverting the `.svelte-flow__viewport` CSS transform.
   *
   * We avoid `useSvelteFlow()` here because it requires the call site
   * to live INSIDE the SvelteFlow provider; PlaybookCanvas hosts the
   * provider, so the hook isn't available at this scope.
   */
  function dropPointToFlow(clientX: number, clientY: number): { x: number; y: number } | null {
    if (!dropTargetEl) return null;
    const wrapper = dropTargetEl.getBoundingClientRect();
    const viewport = dropTargetEl.querySelector('.svelte-flow__viewport') as HTMLElement | null;
    let tx = 0, ty = 0, scale = 1;
    if (viewport) {
      const m = new DOMMatrixReadOnly(window.getComputedStyle(viewport).transform);
      tx = m.m41; ty = m.m42; scale = m.a || 1;
    }
    return {
      x: Math.round((clientX - wrapper.left - tx) / scale - NODE_WIDTH / 2),
      y: Math.round((clientY - wrapper.top - ty) / scale - NODE_HEIGHT / 2)
    };
  }

  // Match the autoLayout constants so the cursor lands on the node's center.
  const NODE_WIDTH = 240;
  const NODE_HEIGHT = 84;

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    const payload = decode(e);
    if (!payload) return;
    const tpl = templateFor(payload);
    const predecessorId = findClosestNodeId(e.clientX, e.clientY);
    const position = dropPointToFlow(e.clientX, e.clientY) ?? undefined;
    const newId = visualStore.addNode(playbookIdx, tpl, {
      predecessorId: predecessorId ?? undefined,
      splice: false,
      position
    });
    if (newId) {
      const inserted = playbook.nodes.find((n) => n.id === newId);
      if (inserted) onSelect?.(inserted);
    }
  }

  function handleDragOver(e: DragEvent) {
    if (e.dataTransfer?.types.includes('application/x-fsrpb-step')) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }
  }
</script>

<div
  class="h-full w-full"
  bind:this={dropTargetEl}
  ondrop={handleDrop}
  ondragover={handleDragOver}
  role="presentation"
>
  <SvelteFlow
    {nodes}
    {edges}
    {nodeTypes}
    {edgeTypes}
    fitView
    nodesDraggable
    nodesConnectable
    connectionRadius={140}
    onnodeclick={handleNodeClick}
    onpaneclick={() => onSelect?.(null)}
    onedgecontextmenu={handleEdgeContextMenu}
    onreconnect={handleReconnect}
    onconnect={handleConnect}
    onnodedragstop={handleNodeDragStop}
  >
    <Background />
    <MiniMap />
    <Controls />
  </SvelteFlow>
</div>
