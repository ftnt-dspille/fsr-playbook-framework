import { describe, it, expect, beforeEach } from 'vitest';
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
});
