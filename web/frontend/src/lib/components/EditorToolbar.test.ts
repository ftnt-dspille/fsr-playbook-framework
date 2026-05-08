import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import EditorToolbar from './EditorToolbar.svelte';
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
          { id: 'a', type: 'start', family: 'trigger', name: 'a', arguments: {}, for_each: null, comment: null, position: null },
          { id: 'b', type: 'set_variable', family: 'utility', name: 'b', arguments: {}, for_each: null, comment: null, position: null },
          { id: 'c', type: 'set_variable', family: 'utility', name: 'c', arguments: {}, for_each: null, comment: null, position: null }
        ],
        edges: [
          { source: 'a', target: 'b', label: null, branch_kind: 'next' },
          { source: 'b', target: 'c', label: null, branch_kind: 'next' }
        ]
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
});

describe('EditorToolbar', () => {
  it('Undo / Redo are disabled until there is history', () => {
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    const undo = screen.getByRole('button', { name: 'Undo' }) as HTMLButtonElement;
    const redo = screen.getByRole('button', { name: 'Redo' }) as HTMLButtonElement;
    expect(undo.disabled).toBe(true);
    expect(redo.disabled).toBe(true);
  });

  it('Undo button enables after a mutation, then fires the store undo', async () => {
    visualStore.setArgs(0, 'b', { arg_list: [{ name: 'x', value: '1' }] });
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    const undo = screen.getByRole('button', { name: 'Undo' });
    expect((undo as HTMLButtonElement).disabled).toBe(false);
    await fireEvent.click(undo);
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'b')!;
    expect(after.arguments).toEqual({});
    expect(visualStore.canRedo).toBe(true);
  });

  it('TB layout button assigns top-down positions to every node', async () => {
    render(EditorToolbar, { props: { playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Layout top to bottom' }));
    const ns = visualStore.state.graph!.playbooks[0].nodes;
    expect(ns.every((n) => n.position !== null)).toBe(true);
    // Top-to-bottom: y(b) > y(a) and y(c) > y(b).
    const a = ns.find((n) => n.id === 'a')!.position!;
    const b = ns.find((n) => n.id === 'b')!.position!;
    const c = ns.find((n) => n.id === 'c')!.position!;
    expect(b.y).toBeGreaterThan(a.y);
    expect(c.y).toBeGreaterThan(b.y);
  });

  it('LR layout button assigns left-to-right positions and notifies parent', async () => {
    const onDirectionChange = vi.fn();
    render(EditorToolbar, { props: { playbookIdx: 0, onDirectionChange } });
    await fireEvent.click(screen.getByRole('button', { name: 'Layout left to right' }));
    expect(onDirectionChange).toHaveBeenCalledWith('LR');
    const ns = visualStore.state.graph!.playbooks[0].nodes;
    const a = ns.find((n) => n.id === 'a')!.position!;
    const b = ns.find((n) => n.id === 'b')!.position!;
    const c = ns.find((n) => n.id === 'c')!.position!;
    expect(b.x).toBeGreaterThan(a.x);
    expect(c.x).toBeGreaterThan(b.x);
  });

  it('Jinja button fires its callback', async () => {
    // Mock / Live used to be standalone buttons; they now live inside
    // the unified `RunButton` split-control on the toolbar (one menu
    // backed by playbookActions). RunButton has its own coverage in
    // playbookActions.test.ts; here we only pin the Jinja affordance
    // since it still routes through a separate parent callback.
    const onJinjaTest = vi.fn();
    render(EditorToolbar, { props: { playbookIdx: 0, onJinjaTest } });
    await fireEvent.click(screen.getByRole('button', { name: 'Test Jinja' }));
    expect(onJinjaTest).toHaveBeenCalledOnce();
  });
});
