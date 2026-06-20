/**
 * G39: pin the handle-visibility + selection CSS gates so refactors
 * can't silently reintroduce permanently visible connection dots or
 * lose the click-to-show behaviour. Reads StepNode.svelte source as
 * a string and asserts the relevant rules live in the file.
 *
 * JSDOM doesn't run xyflow's layout, so visual gap detection is out
 * of reach for unit tests; the rules-presence check is the closest
 * defence-in-depth the suite can offer without Playwright.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const STEP_NODE = fs.readFileSync(
  path.join(__dirname, 'StepNode.svelte'),
  'utf-8'
);

describe('StepNode CSS gates', () => {
  it('hides xyflow handles by default', () => {
    expect(STEP_NODE).toMatch(/\.svelte-flow__handle\)\s*\{[^}]*opacity:\s*0/);
  });

  it('reveals handles when an edge is hovered or selected', () => {
    expect(STEP_NODE).toContain(':has(.svelte-flow__edge:hover)');
    expect(STEP_NODE).toContain(':has(.svelte-flow__edge.selected)');
  });

  it('keeps handles visible mid-drag (.connecting* states)', () => {
    expect(STEP_NODE).toContain('connectingfrom');
    expect(STEP_NODE).toContain('connectingto');
  });

  it('renders selection ring + glow on the active node', () => {
    expect(STEP_NODE).toContain('fsrpb-step-selected');
    expect(STEP_NODE).toMatch(/box-shadow:\s*[^;]+var\(--brand/);
  });

  it('G43: declares + add-next-step button + quick-type menu', () => {
    expect(STEP_NODE).toContain('aria-label="Add next step"');
    expect(STEP_NODE).toContain('fsrpb-add-next-menu');
    // Spawn handler must wire to the store with a predecessorId so the
    // new node arrives connected — that is the whole point of G43.
    expect(STEP_NODE).toMatch(/visualStore\.addNode[\s\S]*predecessorId:\s*node\.id/);
    // Quick-type list covers the common authoring shortcuts.
    for (const t of ['set_variable', 'connector', 'decision', 'manual_input', 'create_record', 'raise_exception']) {
      expect(STEP_NODE).toContain(`type: '${t}'`);
    }
  });

  it('G44: declares both source AND target handles on every side for best-path routing', () => {
    // pickHandles in PlaybookCanvas selects from these eight ids per
    // node — one per side per type — so dropping any of them would
    // silently strand edges in the wrong direction.
    for (const id of ['top-s', 'top-t', 'right-s', 'right-t', 'bottom-s', 'bottom-t', 'left-s', 'left-t']) {
      expect(STEP_NODE).toContain(`id="${id}"`);
    }
  });

  it('G41: declares secondary handles on all four sides', () => {
    // TB layout adds left/right handles; LR adds top/bottom. Both
    // pairs must exist so connect/reconnect works in either layout.
    expect(STEP_NODE).toContain('id="left-s"');
    expect(STEP_NODE).toContain('id="left-t"');
    expect(STEP_NODE).toContain('id="right-s"');
    expect(STEP_NODE).toContain('id="right-t"');
    expect(STEP_NODE).toContain('id="top-s"');
    expect(STEP_NODE).toContain('id="top-t"');
    expect(STEP_NODE).toContain('id="bottom-s"');
    expect(STEP_NODE).toContain('id="bottom-t"');
  });
});
