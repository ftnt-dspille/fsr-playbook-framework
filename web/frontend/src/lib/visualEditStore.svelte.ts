/**
 * Shared editable-graph state for the visual editor.
 *
 * Phase 3.4 introduces inline edits in the inspector. We keep one
 * "draft" graph + the original YAML behind it; Save sends both to
 * `/api/visual/write_file` and refreshes from the response.
 *
 * Anything that mutates the draft should call `markDirty()` so the
 * Save button surfaces and ⌘S works (Phase 7.4).
 */
import type { VisualGraph, VisualNode, VisualPlaybook } from './api';

type State = {
  filePath: string | null;
  graph: VisualGraph | null;
  dirty: boolean;
  saving: boolean;
  saveError: string | null;
};

const state = $state<State>({
  filePath: null,
  graph: null,
  dirty: false,
  saving: false,
  saveError: null
});

export const visualStore = {
  get state() { return state; },

  load(filePath: string, graph: VisualGraph) {
    state.filePath = filePath;
    state.graph = graph;
    state.dirty = false;
    state.saveError = null;
  },

  /** Mutate a single node's args — most common edit shape. */
  patchNode(playbookIdx: number, nodeId: string, patch: Partial<VisualNode>) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const idx = pb.nodes.findIndex((n) => n.id === nodeId);
    if (idx < 0) return;
    pb.nodes[idx] = { ...pb.nodes[idx], ...patch };
    state.dirty = true;
  },

  /** Replace a node's arguments wholesale. */
  setArgs(playbookIdx: number, nodeId: string, args: Record<string, unknown>) {
    this.patchNode(playbookIdx, nodeId, { arguments: args });
  },

  /**
   * Stage a brand-new node on the canvas (Phase 3.2 drop handler).
   * `predecessorId` (when given) gets a `next: → newId` edge appended.
   * `splice` true → the new node sits between predecessor and the
   * predecessor's existing target (Phase 3.3 splice).
   */
  addNode(
    playbookIdx: number,
    template: { type: string; name: string; arguments?: Record<string, unknown>; family?: VisualNode['family'] },
    options?: { predecessorId?: string; splice?: boolean; position?: { x: number; y: number } }
  ): string | null {
    if (!state.graph) return null;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return null;
    const newId = uniqueId(template.name, pb.nodes);
    const newNode: VisualNode = {
      id: newId,
      type: template.type,
      family: template.family ?? familyFor(template.type),
      name: template.name,
      arguments: template.arguments ?? {},
      for_each: null,
      comment: null,
      position: options?.position ?? null
    };
    pb.nodes.push(newNode);

    const pred = options?.predecessorId;
    if (pred) {
      if (options?.splice) {
        // Find the predecessor's existing outbound `next` edge and
        // re-target it through the new node.
        const out = pb.edges.find((e) => e.source === pred && e.branch_kind === 'next');
        if (out) {
          pb.edges.push({ source: newId, target: out.target, label: null, branch_kind: 'next' });
          out.target = newId;
        } else {
          pb.edges.push({ source: pred, target: newId, label: null, branch_kind: 'next' });
        }
      } else {
        pb.edges.push({ source: pred, target: newId, label: null, branch_kind: 'next' });
      }
    }
    state.dirty = true;
    return newId;
  },

  /** Phase 3.5 — retarget an existing edge to a new target node. */
  retargetEdge(playbookIdx: number, edgeKey: { source: string; target: string; label: string | null }, newTarget: string) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const edge = pb.edges.find((e) =>
      e.source === edgeKey.source && e.target === edgeKey.target && (e.label ?? null) === (edgeKey.label ?? null)
    );
    if (!edge) return;
    edge.target = newTarget;
    state.dirty = true;
  },

  /** Phase 3.5 — delete an edge (right-click flow). */
  removeEdge(playbookIdx: number, edgeKey: { source: string; target: string; label: string | null }) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    pb.edges = pb.edges.filter((e) =>
      !(e.source === edgeKey.source && e.target === edgeKey.target && (e.label ?? null) === (edgeKey.label ?? null))
    );
    state.dirty = true;
  },

  /** Phase 3.6 — rename a decision/manual_input branch label. */
  renameBranchLabel(playbookIdx: number, source: string, oldLabel: string | null, newLabel: string) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const edge = pb.edges.find((e) =>
      e.source === source && (e.label ?? null) === (oldLabel ?? null) && e.branch_kind === 'branch'
    );
    if (!edge) return;
    edge.label = newLabel || null;
    state.dirty = true;
  },

  removeNode(playbookIdx: number, nodeId: string) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    pb.nodes = pb.nodes.filter((n) => n.id !== nodeId);
    pb.edges = pb.edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
    state.dirty = true;
  },

  markDirty() { state.dirty = true; },

  discard(reload: () => Promise<void>) {
    state.dirty = false;
    state.saveError = null;
    return reload();
  },

  async save(): Promise<{ ok: boolean; message?: string }> {
    if (!state.graph || !state.filePath) {
      return { ok: false, message: 'no file loaded' };
    }
    state.saving = true;
    state.saveError = null;
    try {
      const r = await fetch('/api/visual/write_file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: state.filePath, graph: state.graph })
      });
      const data = await r.json();
      if (!data.ok) {
        state.saveError = data.message ?? `write failed (${data.code})`;
        return { ok: false, message: state.saveError ?? undefined };
      }
      state.graph = data.graph as VisualGraph;
      state.dirty = false;
      return { ok: true };
    } catch (e) {
      state.saveError = (e as Error).message;
      return { ok: false, message: state.saveError };
    } finally {
      state.saving = false;
    }
  }
};

export function getActivePlaybook(idx: number): VisualPlaybook | null {
  return state.graph?.playbooks[idx] ?? null;
}

const SLUG_RE = /[^a-z0-9]+/g;
function slugify(name: string): string {
  return (name.toLowerCase().replace(SLUG_RE, '_').replace(/^_|_$/g, '') || 'step');
}

function uniqueId(name: string, nodes: VisualNode[]): string {
  const base = slugify(name);
  if (!nodes.some((n) => n.id === base)) return base;
  let i = 2;
  while (nodes.some((n) => n.id === `${base}_${i}`)) i++;
  return `${base}_${i}`;
}

function familyFor(stepType: string): VisualNode['family'] {
  const t = stepType.toLowerCase();
  if (t.startsWith('start') || t === 'manual_action' || t === 'api_call') return 'trigger';
  if (t === 'connector') return 'connector_op';
  if (t === 'decision') return 'decision';
  if (t === 'manual_input') return 'manual_input';
  if (t === 'workflow_reference') return 'workflow_ref';
  if (t === 'stop' || t === 'end') return 'terminal';
  if (['find_record', 'create_record', 'insert_record', 'update_record', 'delete_record', 'ingest_bulk_feed'].includes(t)) return 'record_crud';
  return 'utility';
}
