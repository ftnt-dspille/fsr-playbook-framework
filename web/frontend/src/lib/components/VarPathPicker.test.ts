import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import VarPathPicker from './VarPathPicker.svelte';
import type { VisualPlaybook, VisualNode } from '../api';
import { varPaneStore } from '../varPaneStore.svelte';

afterEach(cleanup);
beforeEach(() => varPaneStore.close());

function makePlaybook(): VisualPlaybook {
  return {
    name: 'Demo', description: '', parameters: [],
    trigger: 'start', trigger_step_id: null,
    nodes: [
      { id: 'trig', type: 'start', family: 'trigger', name: 'On Start', arguments: {}, for_each: null, comment: null, position: null },
      { id: 'me', type: 'decision', family: 'decision', name: 'Branch', arguments: { conditions: [] }, for_each: null, comment: null, position: null }
    ],
    edges: [{ source: 'trig', target: 'me', label: null, branch_kind: 'next' }]
  };
}
const meNode: VisualNode = {
  id: 'me', type: 'decision', family: 'decision', name: 'Branch',
  arguments: { conditions: [] }, for_each: null, comment: null, position: null
};

describe('VarPathPicker (pane-driver)', () => {
  // The popover-based picker was replaced by VarTreePane — this
  // component is now a thin {x} button that toggles the global pane
  // and registers its onInsert closure as the active target.

  it('renders an {x} insert-variable button', () => {
    render(VarPathPicker, { props: { node: meNode, playbook: makePlaybook(), onInsert: vi.fn() } });
    expect(screen.getByRole('button', { name: /insert variable/i })).toBeTruthy();
  });

  it('opens the var pane on click and claims the insert target', async () => {
    const onInsert = vi.fn();
    render(VarPathPicker, { props: { node: meNode, playbook: makePlaybook(), onInsert } });
    expect(varPaneStore.open).toBe(false);
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    expect(varPaneStore.open).toBe(true);
    expect(varPaneStore.target).not.toBeNull();
    expect(varPaneStore.target?.label).toBe('Branch');
  });

  it('routes inserts through onInsert wrapped in {{ }} by default', async () => {
    const onInsert = vi.fn();
    render(VarPathPicker, { props: { node: meNode, playbook: makePlaybook(), onInsert } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    varPaneStore.insert('{{ vars.input.records[0].name }}');
    expect(onInsert).toHaveBeenCalledExactlyOnceWith('{{ vars.input.records[0].name }}');
  });

  it('strips wrapping braces from inserts when wrap=false', async () => {
    const onInsert = vi.fn();
    render(VarPathPicker, { props: { node: meNode, playbook: makePlaybook(), wrap: false, onInsert } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    varPaneStore.insert('{{ vars.input.records[0].name }}');
    expect(onInsert).toHaveBeenCalledExactlyOnceWith('vars.input.records[0].name');
  });

  it('clicking the same button again toggles the pane closed', async () => {
    render(VarPathPicker, { props: { node: meNode, playbook: makePlaybook(), onInsert: vi.fn() } });
    const btn = screen.getByRole('button', { name: /insert variable/i });
    await fireEvent.click(btn);
    expect(varPaneStore.open).toBe(true);
    await fireEvent.click(btn);
    expect(varPaneStore.open).toBe(false);
    expect(varPaneStore.target).toBeNull();
  });

  it('uses the provided label when set, otherwise the step name', async () => {
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), label: 'condition #1', onInsert: vi.fn() }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    expect(varPaneStore.target?.label).toBe('condition #1');
  });
});
