<script lang="ts">
  /**
   * Read-only @xyflow/svelte canvas for a single playbook.
   *
   * Phase 1.1–1.4: renders nodes for the seven step-type families,
   * shows verification status badges (1.3), and emits a `select`
   * event so the host page can render the right-hand inspector
   * panel (1.4). Editing comes in Phase 3.
   */
  import { SvelteFlow, Background, Controls, MiniMap, type Node, type Edge } from '@xyflow/svelte';
  import '@xyflow/svelte/dist/style.css';
  import { onMount, untrack } from 'svelte';
  import type { VisualPlaybook, VisualNode } from '../api';
  import { callMcpTool } from '../api';
  import { autoLayout } from '../visualLayout';
  import StepNode from './StepNode.svelte';

  import { visualStore } from '../visualEditStore.svelte';

  type DropPayload =
    | { kind: 'step_type'; type: string; label: string; detail?: string }
    | { kind: 'connector_op'; connector: string; operation: string; title?: string }
    | { kind: 'recipe'; name: string; recipe_kind: string };

  type Props = {
    playbook: VisualPlaybook;
    playbookIdx: number;
    onSelect?: (node: VisualNode | null) => void;
  };
  let { playbook, playbookIdx, onSelect }: Props = $props();

  const nodeTypes = { step: StepNode };

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

  let positioned = $derived(autoLayout(playbook.nodes, playbook.edges));

  let nodes = $derived<Node[]>(
    positioned.map((n) => ({
      id: n.id,
      type: 'step',
      position: n.position,
      data: {
        node: n,
        verification: verifs[n.id] ?? null
      }
    }))
  );

  let edges = $derived<Edge[]>(
    playbook.edges.map((e, idx) => ({
      id: `${e.source}->${e.target}#${e.label ?? ''}#${idx}`,
      source: e.source,
      target: e.target,
      label: e.label ?? undefined,
      reconnectable: true,
      data: { label: e.label, branch_kind: e.branch_kind },
      animated: false,
      style: e.branch_kind === 'branch' ? 'stroke: var(--color-accent-amber)' : undefined
    }))
  );

  function handleEdgeContextMenu({ edge, event }: { edge: Edge; event: MouseEvent }) {
    event.preventDefault();
    const label = (edge.data?.label as string | null) ?? null;
    if (!confirm(`Delete edge ${edge.source} → ${edge.target}${label ? ` (${label})` : ''}?`)) return;
    visualStore.removeEdge(playbookIdx, { source: edge.source, target: edge.target, label });
  }

  function handleReconnect({ oldEdge, newConnection }: any) {
    const label = (oldEdge.data?.label as string | null) ?? null;
    if (newConnection.source !== oldEdge.source) {
      // Source-side reconnects aren't supported in Phase 3 — would
      // require moving the edge between source steps. Skip silently.
      return;
    }
    if (newConnection.target && newConnection.target !== oldEdge.target) {
      visualStore.retargetEdge(
        playbookIdx,
        { source: oldEdge.source, target: oldEdge.target, label },
        newConnection.target
      );
    }
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

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    const payload = decode(e);
    if (!payload) return;
    const tpl = templateFor(payload);
    const predecessorId = findClosestNodeId(e.clientX, e.clientY);
    // Position the new node near the drop point in canvas coords
    // (xyflow handles its own viewport transform — we pass a hint
    // and let auto-layout adjust for free if no precise drop pos).
    const newId = visualStore.addNode(playbookIdx, tpl, {
      predecessorId: predecessorId ?? undefined,
      splice: false
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
    fitView
    nodesDraggable={false}
    nodesConnectable={false}
    onnodeclick={handleNodeClick}
    onpaneclick={() => onSelect?.(null)}
    onedgecontextmenu={handleEdgeContextMenu}
    onreconnect={handleReconnect}
  >
    <Background />
    <MiniMap />
    <Controls />
  </SvelteFlow>
</div>
