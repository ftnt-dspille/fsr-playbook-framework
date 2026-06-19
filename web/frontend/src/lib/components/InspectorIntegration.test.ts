/**
 * Integration tests for the inspector + store loop, matching the
 * +page.svelte pattern of "selectedNodeId → derived node".
 *
 * Catches the G38-class bug where mutations in the store don't
 * propagate to the rendered inspector because the parent page was
 * caching `selectedNode` by reference instead of deriving it from
 * the live graph. Every test here renders the inspector through a
 * harness that re-derives the node from `visualStore.state.graph`,
 * so the DOM assertions exercise the same data path the real UI uses.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/svelte';
import InspectorHarness from './__test_harness/InspectorHarness.svelte';
import { visualStore } from '../visualEditStore.svelte';
import type { VisualGraph } from '../api';

function makeGraph(): VisualGraph {
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
          { id: 'fetch', type: 'connector', family: 'connector_op', name: 'fetch',
            arguments: { connector: 'jira', operation: 'get_ticket_details', params: { issue_key: 'JIR-1' } },
            for_each: null, comment: null, position: null },
          { id: 'set_x', type: 'set_variable', family: 'utility', name: 'set_x',
            arguments: { arg_list: [{ name: 'x', value: '1' }] },
            for_each: null, comment: null, position: null },
          { id: 'branch', type: 'decision', family: 'decision', name: 'Branch',
            arguments: { conditions: [] }, for_each: null, comment: null, position: null },
          { id: 'a', type: 'set_variable', family: 'utility', name: 'a',
            arguments: {}, for_each: null, comment: null, position: null }
        ],
        edges: [
          { source: 'fetch', target: 'set_x', label: null, branch_kind: 'next' },
          { source: 'set_x', target: 'branch', label: null, branch_kind: 'next' },
          { source: 'branch', target: 'a', label: 'high', branch_kind: 'branch' }
        ]
      }
    ],
    layout_present: false,
    errors: [],
    source: { path: 'demo.yaml', yaml: 'playbooks: []' }
  };
}

let originalFetch: typeof fetch;
beforeEach(() => {
  originalFetch = globalThis.fetch;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/mcp/')) {
      const tool = url.replace('/api/mcp/', '');
      if (tool === 'get_op_schema') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            op_name: 'get_ticket_details',
            params: [{ param_name: 'issue_key', type: 'text', required: 1 }],
            output_schema_json_keys: ['key']
          }
        }), { status: 200 });
      }
      // Default empty payload for tools we don't care about here.
      return new Response(JSON.stringify({ ok: true, result: {} }), { status: 200 });
    }
    return new Response('not found', { status: 404 });
  }) as any;

  visualStore.load('demo.yaml', makeGraph());
});
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe('Inspector integration with derived node', () => {
  it('adding a variable shows the new row in the rendered DOM', async () => {
    render(InspectorHarness, { props: { nodeId: 'set_x', playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));

    // Type the new variable name + click Add. This mimics a real user
    // pressing keys then clicking — fireEvent.input drives the
    // bind:value, click fires the addVar handler.
    const nameInput = screen.getByPlaceholderText('new variable name') as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'y' } });
    await fireEvent.click(screen.getByRole('button', { name: '+ Add variable' }));

    // The DOM now shows BOTH variables. Pre-fix, the inspector still
    // showed only `x` because the parent's selectedNode reference
    // didn't refresh after the store mutation.
    await waitFor(() => screen.getByText('y'));
    expect(screen.getByText('x')).toBeTruthy();
    expect(screen.getByText('y')).toBeTruthy();
    // Input clears after a successful add.
    expect(nameInput.value).toBe('');
  });

  it('adding two variables in a row both appear', async () => {
    render(InspectorHarness, { props: { nodeId: 'set_x', playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));
    const nameInput = screen.getByPlaceholderText('new variable name') as HTMLInputElement;
    const addBtn = screen.getByRole('button', { name: '+ Add variable' });

    for (const name of ['y', 'z']) {
      await fireEvent.input(nameInput, { target: { value: name } });
      await fireEvent.click(addBtn);
    }
    await waitFor(() => screen.getByText('z'));
    expect(screen.getByText('x')).toBeTruthy();
    expect(screen.getByText('y')).toBeTruthy();
    expect(screen.getByText('z')).toBeTruthy();
  });

  it('removing a variable hides its row in the rendered DOM', async () => {
    render(InspectorHarness, { props: { nodeId: 'set_x', playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));
    expect(screen.getByText('x')).toBeTruthy();

    await fireEvent.click(screen.getByLabelText('Remove variable x'));

    // After removal, the variable row is gone and the empty-state
    // copy is shown.
    await waitFor(() => screen.getByText(/No variables defined yet/i));
    expect(screen.queryByText('x')).toBeNull();
  });

  it('adding then removing a variable leaves the original list', async () => {
    render(InspectorHarness, { props: { nodeId: 'set_x', playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));
    const nameInput = screen.getByPlaceholderText('new variable name') as HTMLInputElement;

    await fireEvent.input(nameInput, { target: { value: 'tmp' } });
    await fireEvent.click(screen.getByRole('button', { name: '+ Add variable' }));
    await waitFor(() => screen.getByText('tmp'));

    await fireEvent.click(screen.getByLabelText('Remove variable tmp'));
    await waitFor(() => expect(screen.queryByText('tmp')).toBeNull());
    expect(screen.getByText('x')).toBeTruthy();
  });

  it('renaming the step via header input updates the heading text', async () => {
    render(InspectorHarness, { props: { nodeId: 'set_x', playbookIdx: 0 } });
    const nameInput = screen.getByLabelText('Step name') as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'Renamed step' } });
    // Re-read the live input value from the derived node.
    await waitFor(() => {
      const live = screen.getByLabelText('Step name') as HTMLInputElement;
      expect(live.value).toBe('Renamed step');
    });
  });

  it('Decision node "Add branch" form appends a row to the rendered Branches list', async () => {
    render(InspectorHarness, { props: { nodeId: 'branch', playbookIdx: 0 } });
    // Decision node lands on Branches by default.
    await waitFor(() => screen.getByDisplayValue('high'));
    const labelInput = screen.getByPlaceholderText('label (e.g. matched)') as HTMLInputElement;
    await fireEvent.input(labelInput, { target: { value: 'low' } });
    const targetSelect = screen.getByLabelText('New branch target') as HTMLSelectElement;
    await fireEvent.change(targetSelect, { target: { value: 'a' } });
    await fireEvent.click(screen.getByRole('button', { name: '+ Add branch' }));
    await waitFor(() => screen.getByDisplayValue('low'));
    expect(screen.getByDisplayValue('high')).toBeTruthy();
    expect(screen.getByDisplayValue('low')).toBeTruthy();
  });

  it('get_op_schema is called with the {connector, op, verbose} contract (G46)', async () => {
    // Regression: the tool's pydantic schema rejects `op_name`; the
    // arg must be `op`. We capture the actual fetch body sent for the
    // get_op_schema call and assert the keys.
    let capturedBody: any = null;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/mcp/get_op_schema') {
        capturedBody = init?.body ? JSON.parse(String(init.body)) : null;
        return new Response(JSON.stringify({
          ok: true,
          result: { op_name: 'get_ticket_details', params: [], output_schema_json_keys: [] }
        }), { status: 200 });
      }
      return new Response(JSON.stringify({ ok: true, result: {} }), { status: 200 });
    }) as any;

    render(InspectorHarness, { props: { nodeId: 'fetch', playbookIdx: 0 } });
    // The $effect that calls get_op_schema fires after mount.
    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({ connector: 'jira', op: 'get_ticket_details' });
    // Crucially, NO `op_name` key — the backend rejects that.
    expect(Object.keys(capturedBody)).not.toContain('op_name');
  });

  it('comment textarea updates write through to the store', async () => {
    render(InspectorHarness, { props: { nodeId: 'fetch', playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Raw' }));
    const ta = screen.getByLabelText('Step comment') as HTMLTextAreaElement;
    await fireEvent.input(ta, { target: { value: 'hello' } });
    // Read the store directly — JSDOM's controlled-textarea reflection
    // can lag the user's input, but the store is authoritative.
    const live = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect(live.comment).toBe('hello');
  });
});
