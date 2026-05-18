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
        return new Response(JSON.stringify({
          ok: true,
          result: {
            found: true,
            status: 'tested_pass',
            method: 'live_op_exec',
            ts: '2026-05-08T12:00:00',
            notes_excerpt: 'ran clean',
            history_count: 3
          }
        }), { status: 200 });
      }
      if (tool === 'precheck_picklist_value') {
        return new Response(JSON.stringify({
          ok: true,
          result: { ok: false, message: 'value not in picklist', suggestions: ['Open', 'Closed'] }
        }), { status: 200 });
      }
      if (tool === 'render_jinja') {
        return new Response(JSON.stringify({ ok: true, result: { output: 'JIR-1' } }), { status: 200 });
      }
      if (tool === 'step_test') {
        return new Response(JSON.stringify({
          ok: true,
          result: { ok: true, status: 'executed', rendered_args: {}, output: { key: 'JIR-1' }, note: '' }
        }), { status: 200 });
      }
      if (tool === 'run_op') {
        return new Response(JSON.stringify({
          ok: true,
          result: { ok: true, data: { ticket: { key: 'JIR-1', summary: 'demo' } }, output_shape: 'dict' }
        }), { status: 200 });
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
    const ta = screen.getAllByRole('textbox').find((el) => el.tagName === 'TEXTAREA') as HTMLTextAreaElement;
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

  it('shows the inline Branches section only for decision/manual_input', async () => {
    // Connector op: no Branches section in Args.
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    // Branches is no longer a tab — it's folded into Args. The
    // "Branches" heading is absent for connector_op nodes.
    expect(
      Array.from(document.querySelectorAll('.uppercase'))
        .map((e) => e.textContent?.trim())
    ).not.toContain('Branches');
    cleanup();
    // Decision: Branches heading appears inline under Args.
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    const headings = Array.from(document.querySelectorAll('.uppercase')).map((e) => e.textContent?.trim());
    expect(headings).toContain('Branches');
  });

  it('renders the Verify tab and resolves args via render_jinja', async () => {
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    // Inject a templated arg so we exercise the rendered branch.
    (fetchNode.arguments.params as any).issue_key = '{{ vars.steps.set_x.x }}';
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Render' }));
    await waitFor(() => expect(screen.getAllByText('rendered').length).toBeGreaterThan(0));
    expect(screen.getByText('JIR-1')).toBeTruthy();
    // Non-template strings are shown as literals (no "rendered" label needed).
    expect(screen.getByText('jira')).toBeTruthy();
  });

  it('Args tab runs picklist precheck on blur and surfaces suggestions', async () => {
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('issue_key'));
    const ta = screen.getAllByRole('textbox').find((el) => el.tagName === 'TEXTAREA') as HTMLTextAreaElement;
    await fireEvent.input(ta, { target: { value: "{{ 'In Progress' | picklist('AlertStatus') }}" } });
    await fireEvent.blur(ta);
    await waitFor(() => screen.getByText('AlertStatus'));
    expect(screen.getByText(/value not in picklist/)).toBeTruthy();
    expect(screen.getByText(/Open, Closed/)).toBeTruthy();
  });

  it('Verify tab "Past test runs" Load button shows verification_status results', async () => {
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    // History button was renamed to "Load" so the action verb matches
    // what the user is doing (loading past runs).
    await fireEvent.click(screen.getByRole('button', { name: 'Load' }));
    await waitFor(() => screen.getByText('tested_pass'));
    expect(screen.getByText(/live_op_exec/)).toBeTruthy();
    expect(screen.getByText(/ran clean/)).toBeTruthy();
  });

  it('Verify tab Test step button calls step_test and shows status', async () => {
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Test step' }));
    await waitFor(() => screen.getByText('executed'));
    expect(screen.getByText(/JIR-1/)).toBeTruthy();
  });

  it('Verify tab Run (safe) button executes read-only run_op and shows output', async () => {
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    const runBtn = screen.getByRole('button', { name: 'Run' });
    expect((runBtn as HTMLButtonElement).disabled).toBe(false);
    await fireEvent.click(runBtn);
    await waitFor(() => screen.getByText('ok'));
    expect(screen.getByText(/JIR-1/)).toBeTruthy();
  });

  it('Verify tab Run button is locked for non-safe op names', async () => {
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    // Decision node is not connector_op — Run section absent entirely.
    expect(screen.queryByRole('button', { name: 'Run' })).toBeNull();
  });

  it('renames a branch label via the inline Branches section', async () => {
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    // Branches now renders inline beneath Args — no tab click needed.
    const labelInput = screen.getByDisplayValue('high');
    await fireEvent.input(labelInput, { target: { value: 'critical' } });
    const after = visualStore.state.graph!.playbooks[0].edges.find(
      (e) => e.source === 'branch' && e.branch_kind === 'branch'
    );
    expect(after?.label).toBe('critical');
  });

  it('inline Branches section can add a new branch with a label + target', async () => {
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    const labelInput = screen.getByPlaceholderText('label (e.g. matched)') as HTMLInputElement;
    await fireEvent.input(labelInput, { target: { value: 'extra' } });
    const targetSelect = screen.getByLabelText('New branch target') as HTMLSelectElement;
    await fireEvent.change(targetSelect, { target: { value: 'a' } });
    await fireEvent.click(screen.getByRole('button', { name: '+ Add branch' }));
    const edges = visualStore.state.graph!.playbooks[0].edges;
    expect(edges.some((e) => e.source === 'branch' && e.target === 'a' && e.label === 'extra' && e.branch_kind === 'branch')).toBe(true);
  });

  it('set_variable Args tab adds a new variable', async () => {
    const node = pb().nodes.find((n) => n.id === 'set_x')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));
    const nameInput = screen.getByPlaceholderText('new variable name') as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'y' } });
    await fireEvent.click(screen.getByRole('button', { name: '+ Add variable' }));
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'set_x')!;
    const list = (after.arguments.arg_list as { name: string; value: unknown }[]);
    expect(list.map((v) => v.name)).toEqual(['x', 'y']);
  });

  it('set_variable Args tab removes a variable via the × button', async () => {
    const node = pb().nodes.find((n) => n.id === 'set_x')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Variables'));
    await fireEvent.click(screen.getByLabelText('Remove variable x'));
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'set_x')!;
    expect(after.arguments.arg_list).toEqual([]);
  });

  it('connector Args tab can swap operation and clears params', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('issue_key'));
    const opInput = screen.getByLabelText('Operation') as HTMLInputElement;
    // OperationPicker commits on Enter / blur — not on every keystroke
    // — so the schema $effect doesn't fire mid-type. Type, then blur.
    await fireEvent.input(opInput, { target: { value: 'list_tickets' } });
    await fireEvent.blur(opInput);
    await waitFor(() => {
      const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
      expect(after.arguments.operation).toBe('list_tickets');
    });
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect(after.arguments.params).toEqual({});
  });

  it('connector Args tab adds a freeform param', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('Extra params (not in schema)'));
    const nameInput = screen.getByPlaceholderText('new param name') as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'expand' } });
    await fireEvent.click(screen.getByRole('button', { name: '+ Add param' }));
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect((after.arguments.params as Record<string, unknown>).expand).toBe('');
  });

  it('inspector header lets the user rename a step', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    const nameInput = screen.getByLabelText('Step name') as HTMLInputElement;
    await fireEvent.input(nameInput, { target: { value: 'Pull issue' } });
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect(after.name).toBe('Pull issue');
  });

  it('inspector Delete button removes the node and notifies parent', async () => {
    const node = pb().nodes.find((n) => n.id === 'a')!;
    const onDelete = vi.fn();
    const cs = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0, onDelete } });
    await fireEvent.click(screen.getByRole('button', { name: 'Delete step' }));
    expect(onDelete).toHaveBeenCalledWith('a');
    expect(visualStore.state.graph!.playbooks[0].nodes.some((n) => n.id === 'a')).toBe(false);
    cs.mockRestore();
  });

  it('Decision node shows Args (with inline Branches) as the default tab', async () => {
    const branchNode = pb().nodes.find((n) => n.id === 'branch')!;
    render(StepInspector, { props: { node: branchNode, playbook: pb(), playbookIdx: 0 } });
    // Args is back for decision — it owns the inline Branches editor.
    expect(screen.getByRole('button', { name: 'Args' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Examples' })).toBeTruthy();
    // Default-active tab is Args; the rename input for label "high" comes from the inline branches editor.
    expect(screen.getByDisplayValue('high')).toBeTruthy();
  });

  it('Connector node still shows Args + Examples + Verify', async () => {
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    expect(screen.getByRole('button', { name: 'Args' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Examples' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Verify' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Branches' })).toBeNull();
  });

  it('Examples tab "Use" button applies the snippet to the current step', async () => {
    // Override the operation-example response so we can assert the merge.
    const prev = globalThis.fetch as any;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/mcp/find_operation_example') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            count: 1,
            matches: [{
              op_name: 'get_ticket_details',
              snippet: JSON.stringify({
                connector: 'jira',
                operation: 'get_ticket_details',
                params: { issue_key: 'ABC-9', expand: 'changelog' }
              }),
              notes: 'from playbook x'
            }]
          }
        }), { status: 200 });
      }
      return prev(input, init);
    }) as any;

    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('issue_key'));
    await fireEvent.click(screen.getByRole('button', { name: 'Examples' }));
    await waitFor(() => screen.getByRole('button', { name: 'Use' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Use' }));

    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect(after.arguments.connector).toBe('jira');
    expect(after.arguments.operation).toBe('get_ticket_details');
    expect(after.arguments.params).toEqual({ issue_key: 'ABC-9', expand: 'changelog' });
    expect(visualStore.state.dirty).toBe(true);
  });

  it('Args tab unhides params gated by a parent\'s default value', async () => {
    // Schema: parent `method` has default "Quarantine Based"; child
    // `policy` is gated on that exact value. Without the default-aware
    // visibility fix, `policy` stays in the Hidden bucket.
    const prev = globalThis.fetch as any;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/mcp/get_op_schema') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            op_name: 'block_ip',
            title: 'Block IP',
            params: [
              {
                param_name: 'method',
                title: 'Block Method',
                type: 'select',
                required: 1,
                default_value: 'Quarantine Based',
                options_json: ['Quarantine Based', 'Policy Based']
              },
              {
                param_name: 'policy',
                title: 'Quarantine policy',
                type: 'text',
                parent_param_name: 'method',
                condition_value: 'Quarantine Based'
              },
              {
                param_name: 'rule',
                title: 'Policy rule',
                type: 'text',
                parent_param_name: 'method',
                condition_value: 'Policy Based'
              }
            ],
            output_schema_json_keys: []
          }
        }), { status: 200 });
      }
      return prev(input, init);
    }) as any;

    // Connector op with NO `method` set in args — pure default territory.
    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    fetchNode.arguments.operation = 'block_ip';
    fetchNode.arguments.params = {};
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('method'));
    // Default-gated child must be visible.
    await waitFor(() => screen.getByText('policy'));
    expect(screen.getByText('policy')).toBeTruthy();
    // The non-matching branch's child stays in the hidden block.
    const hiddenSummary = screen.getByText(/Hidden \(/);
    expect(hiddenSummary.textContent).toContain('1');
  });

  it('Args tab unwraps JSON-quoted default_value (server returns "\\"X\\"")', async () => {
    // The verbose `get_op_schema` response leaves default_value JSON-
    // encoded (e.g. `"\"Quarantine Based\""`). Without the unwrap, the
    // select shows the empty placeholder and conditional children stay
    // hidden — exactly the screenshot the user reported.
    const prev = globalThis.fetch as any;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/mcp/get_op_schema') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            op_name: 'block_ip',
            params: [
              {
                param_name: 'method',
                type: 'select',
                required: 1,
                default_value: '"Quarantine Based"',  // JSON-quoted as in DB
                options_json: ['Quarantine Based', 'Policy Based']
              },
              {
                param_name: 'policy',
                type: 'text',
                parent_param_name: 'method',
                condition_value: 'Quarantine Based'
              }
            ],
            output_schema_json_keys: []
          }
        }), { status: 200 });
      }
      return prev(input, init);
    }) as any;

    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    fetchNode.arguments.operation = 'block_ip';
    fetchNode.arguments.params = {};
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('method'));
    // Select should be on the unwrapped value, not the empty placeholder.
    const sel = screen.getAllByRole('combobox').find(
      (el) => (el as HTMLSelectElement).value === 'Quarantine Based'
    ) as HTMLSelectElement | undefined;
    expect(sel).toBeTruthy();
    // Conditional child must be visible since the parent's default matches.
    expect(screen.getByText('policy')).toBeTruthy();
  });

  it('Args tab hides children whose gating parent is itself hidden (transitive)', async () => {
    // Mirrors the real fortigate-firewall:block_ip shape: `ip_type` is
    // gated on method=Policy Based but declares default_value="IPv4".
    // Under method=Quarantine Based, `ip_type` itself must be hidden,
    // and its default must NOT leak — so `ip` (gated on ip_type=IPv4)
    // also stays hidden.
    const prev = globalThis.fetch as any;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/mcp/get_op_schema') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            op_name: 'block_ip',
            params: [
              {
                param_name: 'method',
                type: 'select',
                required: 1,
                default_value: '"Quarantine Based"',
                options_json: ['Quarantine Based', 'Policy Based']
              },
              {
                param_name: 'ip_addresses',
                type: 'text',
                applies_when: [{ parent: 'method', value: 'Quarantine Based' }]
              },
              {
                param_name: 'ip_type',
                type: 'select',
                default_value: '"IPv4"',
                options_json: ['IPv4', 'IPv6'],
                applies_when: [{ parent: 'method', value: 'Policy Based' }]
              },
              {
                param_name: 'ip',
                type: 'text',
                applies_when: [
                  { parent: 'ip_type', value: 'IPv4' },
                  { parent: 'ip_type', value: 'IPv6' }
                ]
              }
            ],
            output_schema_json_keys: []
          }
        }), { status: 200 });
      }
      return prev(input, init);
    }) as any;

    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    fetchNode.arguments.operation = 'block_ip';
    fetchNode.arguments.params = {};
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('method'));
    // method=Quarantine Based is the default → ip_addresses visible.
    expect(screen.getByText('ip_addresses')).toBeTruthy();
    // ip_type is gated on method=Policy Based → hidden, default doesn't leak.
    // `ip` would only render if ip_type's "IPv4" default leaked — must NOT.
    // ip + ip_type both gated on Policy-Based path → both in Hidden bucket.
    const hiddenSummary = screen.getByText(/Hidden \(/);
    expect(hiddenSummary.textContent).toMatch(/Hidden \(2\)/);
  });

  it('Args tab pre-selects the default option for a select param', async () => {
    const prev = globalThis.fetch as any;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/mcp/get_op_schema') {
        return new Response(JSON.stringify({
          ok: true,
          result: {
            op_name: 'block_ip',
            title: 'Block IP',
            params: [{
              param_name: 'method',
              type: 'select',
              required: 1,
              default_value: 'Quarantine Based',
              options_json: ['Quarantine Based', 'Policy Based']
            }],
            output_schema_json_keys: []
          }
        }), { status: 200 });
      }
      return prev(input, init);
    }) as any;

    const fetchNode = pb().nodes.find((n) => n.id === 'fetch')!;
    fetchNode.arguments.operation = 'block_ip';
    fetchNode.arguments.params = {};
    render(StepInspector, { props: { node: fetchNode, playbook: pb(), playbookIdx: 0 } });
    await waitFor(() => screen.getByText('method'));
    const sel = screen.getAllByRole('combobox').find(
      (el) => (el as HTMLSelectElement).value === 'Quarantine Based'
    ) as HTMLSelectElement | undefined;
    expect(sel).toBeTruthy();
    expect(sel!.value).toBe('Quarantine Based');
  });

  it('Raw tab edits the comment via the textarea', async () => {
    const node = pb().nodes.find((n) => n.id === 'fetch')!;
    render(StepInspector, { props: { node, playbook: pb(), playbookIdx: 0 } });
    await fireEvent.click(screen.getByRole('button', { name: 'Raw' }));
    const ta = screen.getByLabelText('Step comment') as HTMLTextAreaElement;
    await fireEvent.input(ta, { target: { value: 'note about the step' } });
    const after = visualStore.state.graph!.playbooks[0].nodes.find((n) => n.id === 'fetch')!;
    expect(after.comment).toBe('note about the step');
  });
});
