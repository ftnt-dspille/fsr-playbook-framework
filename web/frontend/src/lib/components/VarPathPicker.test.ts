import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/svelte';
import VarPathPicker from './VarPathPicker.svelte';
import type { VisualPlaybook, VisualNode } from '../api';

afterEach(cleanup);

function makePlaybook(): VisualPlaybook {
  // A linear graph:  trigger → fetch (connector_op) → find (find_record) → me (target).
  // Picker is opened on `me`, so all three earlier steps are ancestors.
  return {
    name: 'Demo',
    description: '',
    parameters: [],
    trigger: 'start',
    trigger_step_id: null,
    nodes: [
      { id: 'trig', type: 'start', family: 'trigger', name: 'On Start', arguments: {}, for_each: null, comment: null, position: null },
      { id: 'fetch', type: 'connector', family: 'connector_op', name: 'Get Issue Details', arguments: { connector: 'jira' }, for_each: null, comment: null, position: null },
      { id: 'find', type: 'find_record', family: 'record_crud', name: 'Find Linked Tasks', arguments: { module: 'tasks?$limit=30' }, for_each: null, comment: null, position: null },
      { id: 'me', type: 'decision', family: 'decision', name: 'Branch', arguments: { conditions: [] }, for_each: null, comment: null, position: null },
    ],
    edges: [
      { source: 'trig', target: 'fetch', label: null, branch_kind: 'next' },
      { source: 'fetch', target: 'find', label: null, branch_kind: 'next' },
      { source: 'find', target: 'me', label: null, branch_kind: 'next' },
    ],
  };
}

const meNode: VisualNode = {
  id: 'me', type: 'decision', family: 'decision', name: 'Branch',
  arguments: { conditions: [] }, for_each: null, comment: null, position: null,
};

describe('VarPathPicker', () => {
  it('opens a popover with the {x} button', async () => {
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), onInsert: vi.fn() }
    });
    const btn = screen.getByRole('button', { name: /insert variable/i });
    expect(screen.queryByRole('dialog', { name: /variable picker/i })).toBeNull();
    await fireEvent.click(btn);
    expect(screen.getByRole('dialog', { name: /variable picker/i })).toBeTruthy();
  });

  it('always offers vars.input.records[0] / params + globalVars', async () => {
    render(VarPathPicker, {
      props: { node: meNode, playbook: null, onInsert: vi.fn() }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText("vars.input.records[0]['@id']")).toBeTruthy();
    expect(within(dialog).getByText("vars.input.params['<name>']")).toBeTruthy();
    expect(within(dialog).getByText('globalVars.<name>')).toBeTruthy();
  });

  it('lists every ancestor with a step-type-aware suggestion', async () => {
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), onInsert: vi.fn() }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    // connector_op → vars.steps.<name>.data
    expect(within(dialog).getByText('vars.steps.Get_Issue_Details.data')).toBeTruthy();
    // find_record → vars.steps.<name>[0]['@id']
    expect(within(dialog).getByText("vars.steps.Find_Linked_Tasks[0]['@id']")).toBeTruthy();
    // generic ancestor (start trigger)
    expect(within(dialog).getByText('vars.steps.On_Start')).toBeTruthy();
  });

  it('emits the path wrapped in {{ … }} on click', async () => {
    const onInsert = vi.fn();
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), onInsert }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    await fireEvent.click(within(dialog).getByText("vars.input.records[0]['@id']"));
    expect(onInsert).toHaveBeenCalledExactlyOnceWith("{{ vars.input.records[0]['@id'] }}");
  });

  it('emits unwrapped path when wrap=false', async () => {
    const onInsert = vi.fn();
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), wrap: false, onInsert }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    await fireEvent.click(screen.getByText('vars.input.records[0].name'));
    expect(onInsert).toHaveBeenCalledExactlyOnceWith('vars.input.records[0].name');
  });

  it('filters suggestions by the search input', async () => {
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), onInsert: vi.fn() }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    const filter = within(dialog).getByPlaceholderText('filter…');
    await fireEvent.input(filter, { target: { value: 'Find' } });
    expect(within(dialog).queryByText('vars.steps.Get_Issue_Details.data')).toBeNull();
    expect(within(dialog).getByText("vars.steps.Find_Linked_Tasks[0]['@id']")).toBeTruthy();
  });

  it('walks transitive ancestors (not just direct predecessors)', async () => {
    // `me` has only `find` as a direct predecessor, but `fetch` and
    // `trig` should still appear in the suggestions because they
    // flow into `me` transitively.
    render(VarPathPicker, {
      props: { node: meNode, playbook: makePlaybook(), onInsert: vi.fn() }
    });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('vars.steps.On_Start')).toBeTruthy();
    expect(within(dialog).getByText('vars.steps.Get_Issue_Details.data')).toBeTruthy();
    expect(within(dialog).getByText("vars.steps.Find_Linked_Tasks[0]['@id']")).toBeTruthy();
  });
});
