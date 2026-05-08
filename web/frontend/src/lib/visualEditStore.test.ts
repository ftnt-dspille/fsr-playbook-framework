import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { visualStore } from './visualEditStore.svelte';
import type { VisualGraph } from './api';

function fixture(): VisualGraph {
  return {
    collection: { name: 'C', description: '', visible: true },
    playbooks: [
      {
        name: 'Demo',
        description: '',
        parameters: [],
        trigger: 'start',
        trigger_step_id: null,
        nodes: [
          { id: 'start', type: 'start', family: 'trigger', name: 'start', arguments: {}, for_each: null, comment: null, position: null },
          { id: 'do_x', type: 'set_variable', family: 'utility', name: 'do_x', arguments: { arg_list: [{ name: 'x', value: '1' }] }, for_each: null, comment: null, position: null },
          { id: 'branch', type: 'decision', family: 'decision', name: 'Branch', arguments: { conditions: [] }, for_each: null, comment: null, position: null },
          { id: 'route_a', type: 'set_variable', family: 'utility', name: 'route_a', arguments: {}, for_each: null, comment: null, position: null },
          { id: 'route_b', type: 'set_variable', family: 'utility', name: 'route_b', arguments: {}, for_each: null, comment: null, position: null }
        ],
        edges: [
          { source: 'start', target: 'do_x', label: null, branch_kind: 'next' },
          { source: 'do_x', target: 'branch', label: null, branch_kind: 'next' },
          { source: 'branch', target: 'route_a', label: 'high', branch_kind: 'branch' },
          { source: 'branch', target: 'route_b', label: 'low', branch_kind: 'branch' }
        ]
      }
    ],
    layout_present: false,
    errors: [],
    source: { path: 'demo.yaml', yaml: 'collection: C\nplaybooks:\n  - name: Demo\n' }
  };
}

beforeEach(() => {
  visualStore.load('demo.yaml', fixture());
});

describe('visualStore', () => {
  it('load() resets dirty + saveError', () => {
    expect(visualStore.state.filePath).toBe('demo.yaml');
    expect(visualStore.state.dirty).toBe(false);
    expect(visualStore.state.saveError).toBeNull();
  });

  it('setArgs marks dirty and updates the node', () => {
    visualStore.setArgs(0, 'do_x', { arg_list: [{ name: 'x', value: '99' }] });
    expect(visualStore.state.dirty).toBe(true);
    const n = visualStore.state.graph!.playbooks[0].nodes.find((m) => m.id === 'do_x')!;
    expect(n.arguments).toEqual({ arg_list: [{ name: 'x', value: '99' }] });
  });

  it('addNode appends a node, attaches edge to predecessor, returns new id', () => {
    const id = visualStore.addNode(
      0,
      { type: 'set_variable', name: 'log it', arguments: {} },
      { predecessorId: 'do_x' }
    );
    expect(id).toBe('log_it');
    const pb = visualStore.state.graph!.playbooks[0];
    expect(pb.nodes.map((n) => n.id)).toContain('log_it');
    expect(pb.edges.some((e) => e.source === 'do_x' && e.target === 'log_it')).toBe(true);
    expect(visualStore.state.dirty).toBe(true);
  });

  it('addNode persists an explicit drop position on the new node', () => {
    const id = visualStore.addNode(
      0,
      { type: 'set_variable', name: 'placed', arguments: {} },
      { position: { x: 320, y: 180 } }
    );
    const n = visualStore.state.graph!.playbooks[0].nodes.find((m) => m.id === id)!;
    expect(n.position).toEqual({ x: 320, y: 180 });
  });

  it('addNode disambiguates colliding ids', () => {
    // Fixture already has `do_x`; first add gets _2, second _3.
    const first = visualStore.addNode(0, { type: 'set_variable', name: 'do x', arguments: {} });
    const second = visualStore.addNode(0, { type: 'set_variable', name: 'do x', arguments: {} });
    expect(first).toBe('do_x_2');
    expect(second).toBe('do_x_3');
  });

  it('addNode with splice rewires the predecessor through the new node', () => {
    const id = visualStore.addNode(
      0,
      { type: 'set_variable', name: 'middle', arguments: {} },
      { predecessorId: 'start', splice: true }
    );
    const pb = visualStore.state.graph!.playbooks[0];
    expect(pb.edges.some((e) => e.source === 'start' && e.target === id)).toBe(true);
    expect(pb.edges.some((e) => e.source === id && e.target === 'do_x')).toBe(true);
    // Original `start -> do_x` edge is now `start -> middle`
    expect(pb.edges.find((e) => e.source === 'start' && e.target === 'do_x')).toBeUndefined();
  });

  it('removeNode drops node + all incident edges', () => {
    visualStore.removeNode(0, 'do_x');
    const pb = visualStore.state.graph!.playbooks[0];
    expect(pb.nodes.find((n) => n.id === 'do_x')).toBeUndefined();
    expect(pb.edges.some((e) => e.source === 'do_x' || e.target === 'do_x')).toBe(false);
    expect(visualStore.state.dirty).toBe(true);
  });

  it('retargetEdge swaps the target on an existing edge', () => {
    visualStore.retargetEdge(
      0,
      { source: 'start', target: 'do_x', label: null },
      'branch'
    );
    const pb = visualStore.state.graph!.playbooks[0];
    const e = pb.edges.find((x) => x.source === 'start');
    expect(e?.target).toBe('branch');
    expect(visualStore.state.dirty).toBe(true);
  });

  it('retargetEdge ignores unknown edge keys', () => {
    visualStore.retargetEdge(
      0,
      { source: 'nope', target: 'also_nope', label: null },
      'branch'
    );
    expect(visualStore.state.dirty).toBe(false);
  });

  it('removeEdge drops only the matching label/source/target tuple', () => {
    visualStore.removeEdge(0, { source: 'branch', target: 'route_a', label: 'high' });
    const pb = visualStore.state.graph!.playbooks[0];
    const branches = pb.edges.filter((e) => e.source === 'branch');
    expect(branches).toHaveLength(1);
    expect(branches[0].label).toBe('low');
  });

  it('setPosition writes the new x/y and marks dirty', () => {
    visualStore.setPosition(0, 'do_x', { x: 120, y: 240 });
    const n = visualStore.state.graph!.playbooks[0].nodes.find((m) => m.id === 'do_x')!;
    expect(n.position).toEqual({ x: 120, y: 240 });
    expect(visualStore.state.dirty).toBe(true);
  });

  it('setPosition is a no-op for unknown ids', () => {
    visualStore.setPosition(0, 'ghost', { x: 1, y: 2 });
    expect(visualStore.state.dirty).toBe(false);
  });

  it('addEdge appends a `next` edge from non-decision sources', () => {
    visualStore.addEdge(0, { source: 'route_a', target: 'route_b' });
    const pb = visualStore.state.graph!.playbooks[0];
    const e = pb.edges.find((x) => x.source === 'route_a' && x.target === 'route_b');
    expect(e?.branch_kind).toBe('next');
    expect(e?.label).toBeNull();
  });

  it('addEdge infers `branch` kind for decision sources', () => {
    visualStore.addEdge(0, { source: 'branch', target: 'route_a', label: 'maybe' });
    const pb = visualStore.state.graph!.playbooks[0];
    const e = pb.edges.find((x) => x.source === 'branch' && x.label === 'maybe');
    expect(e?.branch_kind).toBe('branch');
  });

  it('addEdge respects an explicit branch_kind override', () => {
    visualStore.addEdge(0, { source: 'route_a', target: 'route_b', label: 'pinned', branch_kind: 'branch' });
    const pb = visualStore.state.graph!.playbooks[0];
    const e = pb.edges.find((x) => x.source === 'route_a' && x.label === 'pinned');
    expect(e?.branch_kind).toBe('branch');
  });

  it('addEdge ignores duplicate (source,target,label) tuples', () => {
    const before = visualStore.state.graph!.playbooks[0].edges.length;
    visualStore.addEdge(0, { source: 'start', target: 'do_x' });  // already exists
    expect(visualStore.state.graph!.playbooks[0].edges).toHaveLength(before);
  });

  it('retargetEdgeSource moves the source side of an edge', () => {
    visualStore.retargetEdgeSource(
      0,
      { source: 'start', target: 'do_x', label: null },
      'route_a'
    );
    const pb = visualStore.state.graph!.playbooks[0];
    expect(pb.edges.some((e) => e.source === 'start' && e.target === 'do_x')).toBe(false);
    expect(pb.edges.some((e) => e.source === 'route_a' && e.target === 'do_x')).toBe(true);
  });

  it('undo restores the previous graph and stacks the redo', () => {
    visualStore.setArgs(0, 'do_x', { arg_list: [{ name: 'x', value: '99' }] });
    expect(visualStore.canUndo).toBe(true);
    visualStore.undo();
    const x = (visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'do_x')!.arguments.arg_list as any)[0].value;
    expect(x).toBe('1');
    expect(visualStore.canRedo).toBe(true);
  });

  it('redo replays the undone change', () => {
    visualStore.setArgs(0, 'do_x', { arg_list: [{ name: 'x', value: '42' }] });
    visualStore.undo();
    visualStore.redo();
    const x = (visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'do_x')!.arguments.arg_list as any)[0].value;
    expect(x).toBe('42');
  });

  it('a fresh mutation after undo clears the redo stack', () => {
    visualStore.setArgs(0, 'do_x', { arg_list: [{ name: 'x', value: 'A' }] });
    visualStore.undo();
    expect(visualStore.canRedo).toBe(true);
    visualStore.setArgs(0, 'do_x', { arg_list: [{ name: 'x', value: 'B' }] });
    expect(visualStore.canRedo).toBe(false);
  });

  it('undo is a no-op when stack is empty', () => {
    expect(visualStore.canUndo).toBe(false);
    visualStore.undo();
    expect(visualStore.state.dirty).toBe(false);
  });

  it('load() clears undo + redo stacks', () => {
    visualStore.setArgs(0, 'do_x', { arg_list: [{ name: 'x', value: 'C' }] });
    visualStore.undo();
    expect(visualStore.canRedo).toBe(true);
    visualStore.load('demo.yaml', fixture());
    expect(visualStore.canUndo).toBe(false);
    expect(visualStore.canRedo).toBe(false);
  });

  it('renameBranchLabel updates only the matching branch edge', () => {
    visualStore.renameBranchLabel(0, 'branch', 'high', 'critical');
    const pb = visualStore.state.graph!.playbooks[0];
    const labels = pb.edges
      .filter((e) => e.source === 'branch' && e.branch_kind === 'branch')
      .map((e) => e.label);
    expect(labels).toContain('critical');
    expect(labels).not.toContain('high');
    // 'low' branch untouched
    expect(labels).toContain('low');
  });

  describe('YAML round-trip (Studio Design/Edit toggle)', () => {
    let originalFetch: typeof fetch;
    beforeEach(() => { originalFetch = globalThis.fetch; });
    afterEach(() => { globalThis.fetch = originalFetch; });

    it('renderToYaml posts the current graph to /api/visual/write and returns yaml', async () => {
      visualStore.load('demo.yaml', fixture());
      const calls: { url: string; body: any }[] = [];
      globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
        return new Response(JSON.stringify({
          ok: true, yaml: 'playbooks: []\n',
          graph: visualStore.state.graph
        }), { status: 200 });
      }) as any;

      const out = await visualStore.renderToYaml();
      expect(out).toBe('playbooks: []\n');
      expect(calls[0].url).toBe('/api/visual/write');
      expect(calls[0].body.graph).toBeDefined();
      expect(calls[0].body.original_yaml).toBeDefined();
    });

    it('renderToYaml returns null when the server reports !ok', async () => {
      visualStore.load('demo.yaml', fixture());
      globalThis.fetch = vi.fn(async () =>
        new Response(JSON.stringify({ ok: false, code: 'unsupported_edit', message: 'no' }), { status: 200 })
      ) as any;
      expect(await visualStore.renderToYaml()).toBeNull();
    });

    it('loadFromYaml replaces the graph and marks dirty', async () => {
      visualStore.load('demo.yaml', fixture());
      const replacement: VisualGraph = {
        ...fixture(),
        playbooks: [{
          ...fixture().playbooks[0],
          name: 'After'
        }],
        source: { path: 'demo.yaml', yaml: 'playbooks:\n  - name: After\n' }
      };
      globalThis.fetch = vi.fn(async () =>
        new Response(JSON.stringify(replacement), { status: 200 })
      ) as any;

      const r = await visualStore.loadFromYaml('playbooks:\n  - name: After\n');
      expect(r.ok).toBe(true);
      expect(visualStore.state.graph!.playbooks[0].name).toBe('After');
      expect(visualStore.state.dirty).toBe(true);
      // Snapshot should have been pushed so undo restores the prior graph.
      expect(visualStore.canUndo).toBe(true);
    });

    it('loadFromYaml surfaces parse errors and leaves graph untouched', async () => {
      visualStore.load('demo.yaml', fixture());
      const before = JSON.stringify(visualStore.state.graph);
      globalThis.fetch = vi.fn(async () =>
        new Response('bad', { status: 422 })
      ) as any;

      const r = await visualStore.loadFromYaml(': : :');
      expect(r.ok).toBe(false);
      expect(r.message).toMatch(/422/);
      expect(JSON.stringify(visualStore.state.graph)).toBe(before);
    });
  });
});
