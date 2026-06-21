import { describe, it, expect } from 'vitest';
import { autoLayout, forceLayout } from './visualLayout';
import type { VisualEdge, VisualNode } from './api';

const baseNode = (id: string, position: VisualNode['position'] = null): VisualNode => ({
  id,
  type: 'set_variable',
  family: 'utility',
  name: id,
  arguments: {},
  for_each: null,
  comment: null,
  position
});

describe('autoLayout', () => {
  it('fills missing positions via dagre and preserves order', () => {
    const nodes: VisualNode[] = [baseNode('a'), baseNode('b'), baseNode('c')];
    const edges: VisualEdge[] = [
      { source: 'a', target: 'b', label: null, branch_kind: 'next' },
      { source: 'b', target: 'c', label: null, branch_kind: 'next' }
    ];
    const out = autoLayout(nodes, edges);
    expect(out).toHaveLength(3);
    expect(out.map((n) => n.id)).toEqual(['a', 'b', 'c']);
    for (const n of out) {
      expect(n.position).toBeDefined();
      expect(typeof n.position.x).toBe('number');
      expect(typeof n.position.y).toBe('number');
    }
    // Top-down layout: b should be below a, c below b.
    expect(out[0].position.y).toBeLessThan(out[1].position.y);
    expect(out[1].position.y).toBeLessThan(out[2].position.y);
  });

  it('honors server-provided positions verbatim', () => {
    const nodes: VisualNode[] = [
      baseNode('a', { x: 99, y: 11 }),
      baseNode('b')
    ];
    const out = autoLayout(nodes, [{ source: 'a', target: 'b', label: null, branch_kind: 'next' }]);
    expect(out[0].position).toEqual({ x: 99, y: 11 });
    // b still gets a synthesized position from dagre.
    expect(out[1].position.y).toBeGreaterThan(0);
  });

  it('LR direction lays nodes left-to-right', () => {
    const nodes: VisualNode[] = [baseNode('a'), baseNode('b'), baseNode('c')];
    const edges: VisualEdge[] = [
      { source: 'a', target: 'b', label: null, branch_kind: 'next' },
      { source: 'b', target: 'c', label: null, branch_kind: 'next' }
    ];
    const out = autoLayout(nodes, edges, 'LR');
    expect(out[0].position.x).toBeLessThan(out[1].position.x);
    expect(out[1].position.x).toBeLessThan(out[2].position.x);
  });

  it('forceLayout overrides existing positions', () => {
    const nodes: VisualNode[] = [
      baseNode('a', { x: 9999, y: 9999 }),  // user-set, far away
      baseNode('b')
    ];
    const edges: VisualEdge[] = [{ source: 'a', target: 'b', label: null, branch_kind: 'next' }];
    const out = forceLayout(nodes, edges, 'TB');
    expect(out[0].position).not.toEqual({ x: 9999, y: 9999 });
    // both should sit near the dagre origin
    expect(Math.abs(out[0].position.x)).toBeLessThan(500);
  });

  it('handles edges that reference missing nodes without crashing', () => {
    const nodes: VisualNode[] = [baseNode('a')];
    const edges: VisualEdge[] = [
      { source: 'a', target: 'orphan', label: null, branch_kind: 'next' }
    ];
    const out = autoLayout(nodes, edges);
    expect(out).toHaveLength(1);
    expect(out[0].position).toBeDefined();
  });
});
