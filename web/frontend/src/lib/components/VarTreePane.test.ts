import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/svelte';
import { waitFor } from '@testing-library/svelte';
import VarTreePane from './VarTreePane.svelte';
import type { VisualPlaybook, VisualNode } from '../api';
import { varPaneStore } from '../varPaneStore.svelte';
import { jinjaShapesStore } from '../jinjaShapesStore.svelte';
import { sampleRecordsStore, triggerModuleFieldsStore, globalVarsStore } from '../triggerModuleFields.svelte';

// Mock runVarsStore so we can dictate observedAt's return values
// without driving the (already tested) fetch flow. Reactivity still
// works — $state inside the stub re-renders the pane on change.
// Plain (non-reactive) mock — sufficient because all tests seed
// observed values BEFORE render. If we ever need post-render updates,
// move the factory into a `.svelte.ts` helper so $state can be used.
vi.mock('../runVarsStore.svelte', () => {
  const state = {
    runs: [{ id: 1, status: 'success', created: '2026-05-17T10:00:00', name: 'demo', records: [] }] as any[],
    selectedRunId: null as number | null,
    observed: new Map<string, unknown>()
  };
  return {
    runVarsStore: {
      get runs() { return state.runs; },
      get runsLoading() { return false; },
      get runsError() { return null; },
      get selectedRunId() { return state.selectedRunId; },
      get detailLoading() { return false; },
      get detailError() { return null; },
      get stepOutputs() { return {}; },
      get inputRecord() { return null; },
      get topLevelVars() { return {}; },
      loadRuns: vi.fn(async () => {}),
      selectRun: vi.fn(async (id: number | null) => { state.selectedRunId = id; }),
      observedAt(path: string): { found: true; value: unknown } | { found: false } {
        if (state.observed.has(path)) {
          return { found: true, value: state.observed.get(path) };
        }
        return { found: false };
      },
      _setObserved(map: Record<string, unknown>) {
        state.observed = new Map(Object.entries(map));
      },
      _reset() {
        state.selectedRunId = null;
        state.observed = new Map();
      }
    }
  };
});
import { runVarsStore } from '../runVarsStore.svelte';

beforeEach(() => {
  varPaneStore.close();
  jinjaShapesStore._reset();
  triggerModuleFieldsStore._reset();
  sampleRecordsStore._reset();
  (runVarsStore as any)._reset();
  // Stub fetch so the pane's $effect doesn't hit the network.
  (globalThis as any).fetch = vi.fn(async (url: string) => {
    if (url.includes('global-vars')) {
      return { ok: true, json: async () => ({ globals: [{ name: 'tenant_id', value: 'acme' }] }) };
    }
    if (url.includes('/fields')) {
      return { ok: true, json: async () => ({ fields: [{ name: 'severity' }, { name: 'name' }] }) };
    }
    if (url.includes('sample-record')) {
      return { ok: true, json: async () => ({ records: [{ name: 'Alert A', severity: 'high' }] }) };
    }
    return { ok: false, json: async () => ({}) };
  });
});
afterEach(cleanup);

function makePlaybook(): VisualPlaybook {
  return {
    name: 'Demo', description: '', parameters: [],
    trigger: 'start_on_create', trigger_step_id: 'trig',
    nodes: [
      { id: 'trig', type: 'start_on_create', family: 'trigger', name: 'On Create',
        arguments: { module: 'alerts' }, for_each: null, comment: null, position: null },
      { id: 'fetch', type: 'find_record', family: 'record_crud', name: 'Find Issue',
        arguments: { module: 'tasks' }, for_each: null, comment: null, position: null },
      { id: 'me', type: 'set_variable', family: 'utility', name: 'Read Sev',
        arguments: { variables: [] }, for_each: null, comment: null, position: null }
    ],
    edges: [
      { source: 'trig', target: 'fetch', label: null, branch_kind: 'next' },
      { source: 'fetch', target: 'me', label: null, branch_kind: 'next' }
    ]
  };
}
const meNode: VisualNode = {
  id: 'me', type: 'set_variable', family: 'utility', name: 'Read Sev',
  arguments: { variables: [] }, for_each: null, comment: null, position: null
};

describe('VarTreePane', () => {
  it('renders the top-level groups', async () => {
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose: vi.fn() } });
    // Groups are rendered as header buttons.
    expect(await screen.findByRole('button', { name: /input/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /globalVars/i })).toBeTruthy();
    // Step outputs group exists because we have ancestor steps (Find Issue).
    expect(screen.getByRole('button', { name: /step outputs/i })).toBeTruthy();
  });

  /** records[0] is collapsed by default — open it so the field rows
   *  are visible. Wait for the trigger-module fields to hydrate first
   *  (otherwise we'd expand into the 3-entry default placeholder set
   *  and miss the catalog-driven `severity` row). */
  async function expandRecords() {
    await waitFor(() => expect(screen.getByText(/alerts record/i)).toBeTruthy());
    // The label button calls `pick(n)` (insert). The expand caret next
    // to it is a separate button with aria-label "Expand"/"Collapse".
    // We need the records[0] row's caret specifically — find the
    // <div> that contains the records[0] label, then its Expand button.
    const recordsLabel = screen.getByText(/^records\[0\]$/);
    const row = recordsLabel.closest('div');
    expect(row).not.toBeNull();
    const caret = within(row as HTMLElement).getByRole('button', { name: /expand/i });
    await fireEvent.click(caret);
  }

  it('hydrates record fields from the trigger module', async () => {
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose: vi.fn() } });
    await waitFor(() => expect(screen.getByRole('button', { name: /records\[0\]/i })).toBeTruthy());
    await expandRecords();
    await waitFor(() => expect(screen.getByRole('button', { name: /^severity$/i })).toBeTruthy());
    // The sample provides `name = "Alert A"` so the row hint shows that preview.
    await waitFor(() => expect(screen.getByText(/= Alert A/)).toBeTruthy());
  });

  it('clicking a leaf inserts {{ path }} via the active target', async () => {
    const insert = vi.fn();
    varPaneStore.focusField({ id: 't1', label: 'field', insert });
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose: vi.fn() } });
    await expandRecords();
    const leaf = await screen.findByRole('button', { name: /^severity$/i });
    await fireEvent.click(leaf);
    expect(insert).toHaveBeenCalledExactlyOnceWith('{{ vars.input.records[0].severity }}');
  });

  it('disables leaf inserts when no field has focus', async () => {
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose: vi.fn() } });
    await expandRecords();
    const leaf = await screen.findByRole('button', { name: /^severity$/i });
    expect((leaf as HTMLButtonElement).disabled).toBe(true);
  });

  it('Real-run tab shows the run picker after switching', async () => {
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose: vi.fn() } });
    await fireEvent.click(screen.getByRole('button', { name: /^real run$/i }));
    expect(await screen.findByRole('combobox')).toBeTruthy();
  });

  it('Real-run mode renders observed values in green and dims unobserved rows', async () => {
    (runVarsStore as any)._setObserved({
      'vars.input.records[0].severity': 'critical'
    });
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose: vi.fn() } });
    await fireEvent.click(screen.getByRole('button', { name: /^real run$/i }));
    await expandRecords();
    // Observed leaf shows the value with emerald text.
    const observedHint = await screen.findByText('= critical');
    expect(observedHint.className).toMatch(/emerald/);
    // A leaf without observed data is wrapped in an opacity-40 row.
    const otherLeaf = await screen.findByRole('button', { name: /^name$/i });
    const row = otherLeaf.closest('div');
    expect(row?.className).toMatch(/opacity-40/);
  });

  it('Esc fires onClose', async () => {
    const onClose = vi.fn();
    render(VarTreePane, { props: { node: meNode, playbook: makePlaybook(), onClose } });
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
