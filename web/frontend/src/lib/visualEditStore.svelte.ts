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
  /** Snapshots of `graph` *before* each structural mutation. */
  undoStack: VisualGraph[];
  /** Snapshots restored to `graph` by undo, available for redo. */
  redoStack: VisualGraph[];
};

const state = $state<State>({
  filePath: null,
  graph: null,
  dirty: false,
  saving: false,
  saveError: null,
  undoStack: [],
  redoStack: []
});

const MAX_HISTORY = 50;

function deepClone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v));
}

/** Push current graph onto undoStack and clear redoStack. Called by
 * every mutator before it mutates. No-op if graph is null. */
function snapshot() {
  if (!state.graph) return;
  // Drop the redo stack on every fresh mutation. A new branch of edits
  // invalidates anything we'd previously rolled back to.
  state.redoStack = [];
  // Skip pushing if the top is byte-identical (e.g. a rapid stream of
  // keystrokes that don't actually change the graph yet).
  const top = state.undoStack[state.undoStack.length - 1];
  const cur = deepClone(state.graph);
  if (top && JSON.stringify(top) === JSON.stringify(cur)) return;
  state.undoStack.push(cur);
  if (state.undoStack.length > MAX_HISTORY) state.undoStack.shift();
}

export const visualStore = {
  get state() { return state; },

  load(filePath: string, graph: VisualGraph) {
    state.filePath = filePath;
    state.graph = graph;
    state.dirty = false;
    state.saveError = null;
    state.undoStack = [];
    state.redoStack = [];
  },

  /** Pop one undo snapshot back into `graph`, pushing the current state
   * onto the redo stack. No-op when stack is empty. */
  undo() {
    if (!state.graph || state.undoStack.length === 0) return;
    state.redoStack.push(deepClone(state.graph));
    state.graph = state.undoStack.pop()!;
    state.dirty = true;
  },

  /** Inverse of undo. */
  redo() {
    if (!state.graph || state.redoStack.length === 0) return;
    state.undoStack.push(deepClone(state.graph));
    state.graph = state.redoStack.pop()!;
    state.dirty = true;
  },

  get canUndo() { return state.undoStack.length > 0; },
  get canRedo() { return state.redoStack.length > 0; },

  /** Mutate a single node's args — most common edit shape. */
  patchNode(playbookIdx: number, nodeId: string, patch: Partial<VisualNode>) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const idx = pb.nodes.findIndex((n) => n.id === nodeId);
    if (idx < 0) return;
    snapshot();
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
    snapshot();
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

  /** Persist a node's canvas position. Position-only edits round-trip
   * through the `# fsrpb:layout` block on save, leaving step bodies
   * byte-identical. */
  setPosition(playbookIdx: number, nodeId: string, position: { x: number; y: number }) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const idx = pb.nodes.findIndex((n) => n.id === nodeId);
    if (idx < 0) return;
    snapshot();
    pb.nodes[idx] = { ...pb.nodes[idx], position };
    state.dirty = true;
  },

  /** Add a fresh edge (e.g., from drag-connect). Idempotent on
   * (source,target,label); duplicates are ignored. branch_kind is
   * inferred from the source step type unless overridden. */
  addEdge(
    playbookIdx: number,
    edge: { source: string; target: string; label?: string | null; branch_kind?: 'next' | 'branch' | 'unlabeled' }
  ) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const label = edge.label ?? null;
    const dup = pb.edges.find(
      (e) => e.source === edge.source && e.target === edge.target && (e.label ?? null) === label
    );
    if (dup) return;
    let bk = edge.branch_kind;
    if (!bk) {
      const src = pb.nodes.find((n) => n.id === edge.source);
      bk = src && (src.type === 'decision' || src.type === 'manual_input') ? 'branch' : 'next';
    }
    snapshot();
    pb.edges.push({ source: edge.source, target: edge.target, label, branch_kind: bk });
    state.dirty = true;
  },

  /** Retarget an edge's source side (drag the edge handle off one
   * step onto another). Pairs with retargetEdge for target-side. */
  retargetEdgeSource(
    playbookIdx: number,
    edgeKey: { source: string; target: string; label: string | null },
    newSource: string
  ) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const edge = pb.edges.find(
      (e) => e.source === edgeKey.source && e.target === edgeKey.target && (e.label ?? null) === (edgeKey.label ?? null)
    );
    if (!edge) return;
    snapshot();
    edge.source = newSource;
    state.dirty = true;
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
    snapshot();
    edge.target = newTarget;
    state.dirty = true;
  },

  /** Phase 3.5 — delete an edge (right-click flow). */
  removeEdge(playbookIdx: number, edgeKey: { source: string; target: string; label: string | null }) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    const before = pb.edges.length;
    const filtered = pb.edges.filter((e) =>
      !(e.source === edgeKey.source && e.target === edgeKey.target && (e.label ?? null) === (edgeKey.label ?? null))
    );
    if (filtered.length === before) return;
    snapshot();
    pb.edges = filtered;
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
    snapshot();
    edge.label = newLabel || null;
    state.dirty = true;
  },

  removeNode(playbookIdx: number, nodeId: string) {
    if (!state.graph) return;
    const pb = state.graph.playbooks[playbookIdx];
    if (!pb) return;
    if (!pb.nodes.some((n) => n.id === nodeId)) return;
    snapshot();
    pb.nodes = pb.nodes.filter((n) => n.id !== nodeId);
    pb.edges = pb.edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
    state.dirty = true;
  },

  markDirty() { state.dirty = true; },

  /** Round-trip the current graph through the emitter to get fresh YAML
   * matching any pending visual edits. Used when toggling Visual→YAML
   * so the Monaco buffer reflects unsaved canvas changes instead of
   * the stale on-disk source. Returns null on failure (caller should
   * fall back to `state.graph.source.yaml`). */
  async renderToYaml(): Promise<string | null> {
    if (!state.graph) return null;
    try {
      const r = await fetch('/api/visual/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original_yaml: state.graph.source.yaml,
          graph: state.graph
        })
      });
      const data = await r.json();
      return data.ok ? (data.yaml as string) : null;
    } catch { return null; }
  },

  /** Toggle direction YAML→Visual: parse the Monaco buffer back into a
   * graph and replace the current draft. Marks dirty when the YAML
   * differs from the on-disk source so Save stays available. Returns
   * `{ok, message?}` so the page can surface parse errors inline. */
  async loadFromYaml(yamlText: string): Promise<{ ok: boolean; message?: string }> {
    try {
      const r = await fetch('/api/visual/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: yamlText })
      });
      if (!r.ok) return { ok: false, message: `parse failed (${r.status})` };
      const graph = await r.json() as VisualGraph;
      snapshot();
      state.graph = graph;
      // Dirty whenever the buffer no longer matches the on-disk source.
      // We don't have the on-disk yaml stashed separately, but graph.source.yaml
      // is updated to whatever was just parsed — so compare against the
      // pre-snapshot top of the undo stack via a structural marker: any
      // change in YAML text vs the previous load means dirty.
      state.dirty = true;
      return { ok: true };
    } catch (e) {
      return { ok: false, message: (e as Error).message };
    }
  },

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
