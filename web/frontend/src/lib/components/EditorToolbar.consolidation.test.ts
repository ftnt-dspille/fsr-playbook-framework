/**
 * Coverage for the consolidated Design-mode toolbar — companion to
 * EditorToolbar.test.ts (which pins undo/redo + layout + Jinja).
 * Here we pin the chrome trim: no Validate / Compile / Analyze / Verify
 * buttons, no separate verify pill, single combined err/warn chip,
 * and an overflow with Re-validate / Re-analyze.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import EditorToolbar from './EditorToolbar.svelte';
import { playbookActions } from '../playbookActions.svelte';
import { visualStore } from '../visualEditStore.svelte';
import type { VisualGraph } from '../api';

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
          { id: 'a', type: 'start', family: 'trigger', name: 'a', arguments: {}, for_each: null, comment: null, position: null }
        ],
        edges: []
      }
    ],
    layout_present: false,
    errors: [],
    source: { path: 'demo.yaml', yaml: '' }
  };
}

beforeEach(() => {
  cleanup();
  visualStore.load('demo.yaml', fixture());
  playbookActions.state.markers = [];
  playbookActions.state.diagnostics = [];
  playbookActions.state.verify = null;
});

describe('EditorToolbar consolidation', () => {
  it('does not render Validate / Compile / Analyze / Verify buttons', () => {
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    expect(screen.queryByRole('button', { name: 'Validate' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Compile' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Analyze/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Verify' })).toBeNull();
  });

  it('does not render the standalone verify ✓ / ✗ pill', () => {
    playbookActions.state.verify = {
      ready_to_push: true,
      required_fixes: [],
      warnings: [],
      evidence: {}
    } as any;
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    expect(screen.queryByText('verify ✓')).toBeNull();
  });

  it('combines markers + render-path counts into a single chip', () => {
    playbookActions.state.markers = [
      { line: 1, col: 1, severity: 'error', code: 'E1', message: 'm1', path: 'p', suggestion: null },
      { line: 2, col: 1, severity: 'warning', code: 'W1', message: 'm2', path: 'p', suggestion: null }
    ];
    playbookActions.state.diagnostics = [
      { kind: 'k', severity: 'error', step_id: 's', message: 'render-err' } as any,
      { kind: 'k', severity: 'warning', step_id: 's', message: 'render-warn' } as any
    ];
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    // 2 errors total (1 marker + 1 diagnostic), 2 warnings total.
    expect(screen.getByText('2 err')).toBeTruthy();
    expect(screen.getByText('2 warn')).toBeTruthy();
    // Old per-source render chip should not exist anymore.
    expect(screen.queryByText('render')).toBeNull();
  });

  it('overflow menu Re-validate, Re-analyze, Re-verify fire playbookActions', async () => {
    const vSpy = vi.spyOn(playbookActions, 'validate').mockResolvedValue();
    const aSpy = vi.spyOn(playbookActions, 'analyze').mockResolvedValue();
    const verSpy = vi.spyOn(playbookActions, 'runVerify').mockResolvedValue();
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Re-validate' }));
    await fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: /Re-analyze/ }));
    await fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: /Re-verify/ }));
    expect(vSpy).toHaveBeenCalledOnce();
    expect(aSpy).toHaveBeenCalledOnce();
    expect(verSpy).toHaveBeenCalledOnce();
    vSpy.mockRestore();
    aSpy.mockRestore();
    verSpy.mockRestore();
  });
});
