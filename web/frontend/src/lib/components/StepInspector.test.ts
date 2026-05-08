import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/svelte';
import StepInspector from './StepInspector.svelte';
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
          { id: 'fetch', type: 'connector', family: 'connector_op', name: 'fetch', arguments: { connector: 'jira', operation: 'get_ticket_details', params: { issue_key: 'JIR-1' } }, for_each: null, comment: null, position: null },
          { id: 'set_x', type: 'set_variable', family: 'utility', name: 'set_x', arguments: { arg_list: [{ name: 'x', value: '1' }] }, for_each: null, comment: null, position: null },
          { id: 'branch', type: 'decision', family: 'decision', name: 'Branch', arguments: { conditions: [] }, for_each: null, comment: null, position: null },
          { id: 'a', type: 'set_variable', family: 'utility', name: 'a', arguments: {}, for_each: null, comment: null, position: null }
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
    source: { path: 'demo.yaml', yaml: '' }
  };
}

let originalFetch: typeof fetch;
beforeEach(() => {
  originalFetch = globalThis.fetch;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith('/api/mcp/')) {
      const tool = url.replace('/api/mcp/', '');
      // The dispatcher always returns {ok, result}.
      if (tool === 'get_op_schema') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            op_name: 'get_ticket_details',
            title: 'Get Ticket Details',
            description: 'Pull a ticket',
            params: [
              { param_name: 'issue_key', title: 'Ticket ID', type: 'text', required: 1 }
            ],
            output_schema_json_keys: ['key', 'fields']
          }
        }), { status: 200 });
      }
      if (tool === 'find_operation_example') {
        return new Response(JSON.stringify({
          ok: true,
          result: { count: 1, matches: [{ op_name: 'get_ticket_details', snippet: '{"params":{"issue_key":"JIR-1"}}', notes: 'from playbook x' }] }
        }), { status: 200 });
      }
      if (tool === 'find_jinja_example') {
        return new Response(JSON.stringify({
          ok: true,
          result: { count: 1, matches: [{ raw: '{{ vars.steps.set_x.x }}', occurrences: 7, step_type: 'SetVariable' }] }
        }), { status: 200 });
      }
      if (tool === 'verification_status') {
        return new Response(JSON.stringify({ ok: true, result: { found: false, history_count: 0 } }), { status: 200 });
      }
    }
    return new Response('not found', { status: 404 });
  }) as any;

  visualStore.load('demo.yaml', makeGraph());
});
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe('StepInspector', () => {
  function pb() { return visualStore.state.graph!.playbooks[0]; }

  it('shows "click a node" placeholder when no node selected', () => {
    render(StepInspector, { props: { node: null, playbook: pb(), playbookIdx: 0 } });
    expect(screen.getByText(/click a node/i)).toBeTruthy();
  });

  it('renders the schema-driven Args tab for a connector op', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    // Default tab is Args; schema fetch happens on mount.
    await waitFor(() => screen.getByText('issue_key'));
    expect(screen.getByText('issue_key')).toBeTruthy();
    expect(screen.getByText('Get Ticket Details')).toBeTruthy();
    // Output keys chip row
    expect(screen.getByText('key')).toBeTruthy();
    expect(screen.getByText('fields')).toBeTruthy();
  });

  it('editing a connector param marks the store dirty', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('issue_key'));
    const ta = screen.getByRole('textbox');
    await fireEvent.input(ta, { target: { value: 'JIR-99' } });
    expect(visualStore.state.dirty).toBe(true);
    const fetchNode = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect((fetchNode.arguments.params as any).issue_key).toBe('JIR-99');
  });

  it('shows the set_variable arg_list editor', async () => {
    const node = pb().nodes.find((n) => n.id === 'set_x')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));
    expect(screen.getByText('x')).toBeTruthy();
  });

  it('switches to Examples tab and renders snippets', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('issue_key'));
    await fireEvent.click(screen.getByRole('button', { name: 'Examples' }));
    await waitFor(() => screen.getByText(/get_ticket_details/));
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Copy' }).length).toBeGreaterThan(0));
  });

  it('shows the Branches tab only for decision/manual_input', async () => {
    // Connector op: no Branches tab.
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    const view1 = render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    expect(view1.queryByRole('button', { name: 'Branches' })).toBeNull();
    cleanup();
    // Decision: Branches tab visible.
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    expect(screen.getByRole('button', { name: 'Branches' })).toBeTruthy();
  });

  it('renames a branch label via the Branches tab', async () => {
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Branches' }));
    const labelInput = screen.getByDisplayValue('high');
    await fireEvent.input(labelInput, { target: { value: 'critical' } });
    const after = visualStore.state.graph!.playbooks[0].edges.find(
      (e) => e.source === 'branch' && e.branch_kind === 'branch'
    );
    expect(after?.label).toBe('critical');
  });
});
