/**
 * Auto-layout helper for the visual editor canvas.
 *
 * Used when the YAML has no `# fsrpb:layout` block (or a node hasn't
 * been positioned yet). Nodes already carrying a `position` from the
 * server are passed through; missing positions are filled in by dagre.
 *
 * Phase 1.2 of VISUAL_EDITOR_PLAN.
 */
import dagre from 'dagre';
import type { VisualEdge, VisualNode } from './api';

export type PositionedNode = VisualNode & { position: { x: number; y: number } };

const NODE_WIDTH = 240;
const NODE_HEIGHT = 84;

export type LayoutDirection = 'TB' | 'LR';

export function autoLayout(
  nodes: VisualNode[],
  edges: VisualEdge[],
  direction: LayoutDirection = 'TB'
): PositionedNode[] {
  const g = new dagre.graphlib.Graph();
  // LR (left-to-right) wants more horizontal breathing room; TB
  // (top-to-bottom) wants more vertical. Numbers tuned to match the
  // visual density users see in FSR's own designer.
  const opts = direction === 'LR'
    ? { rankdir: 'LR', nodesep: 40, ranksep: 110, marginx: 24, marginy: 24 }
    : { rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 24, marginy: 24 };
  g.setGraph(opts);
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of edges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }
  dagre.layout(g);

  return nodes.map((n) => {
    if (n.position) {
      // Honor server-provided positions verbatim (from the layout
      // sidecar comment block); auto-layout only fills gaps.
      return { ...n, position: n.position };
    }
    const meta = g.node(n.id);
    if (!meta) return { ...n, position: { x: 0, y: 0 } };
    // dagre returns center coords; xyflow expects top-left.
    return {
      ...n,
      position: {
        x: Math.round(meta.x - NODE_WIDTH / 2),
        y: Math.round(meta.y - NODE_HEIGHT / 2)
      }
    };
  });
}

/**
 * Force-relayout: re-runs dagre and OVERRIDES every node's existing
 * position. Used by the toolbar's auto-layout button so the user can
 * tidy the canvas after a long authoring session, even when nodes
 * already have hand-edited positions.
 */
export function forceLayout(
  nodes: VisualNode[],
  edges: VisualEdge[],
  direction: LayoutDirection = 'TB'
): PositionedNode[] {
  const stripped = nodes.map((n) => ({ ...n, position: null }));
  return autoLayout(stripped, edges, direction);
}
