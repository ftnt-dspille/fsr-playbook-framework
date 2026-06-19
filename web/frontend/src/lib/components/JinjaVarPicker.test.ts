/**
 * JinjaVarPicker — the visual {x} selector that lives next to Monaco.
 * Drives editor.executeEdits on click so insertion lands in the undo
 * stack. Covers: opens popover, lists rows from the shape store +
 * input.records defaults, filter, click → executeEdits with the right
 * `{{ … }}` template, and module-aware record fields when the YAML
 * has a recognizable trigger.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, waitFor } from '@testing-library/svelte';
import JinjaVarPicker from './JinjaVarPicker.svelte';
import { jinjaShapesStore } from '../jinjaShapesStore.svelte';
import { triggerModuleFieldsStore, globalVarsStore } from '../triggerModuleFields.svelte';
import type { Shape } from '../shapeStubs';

const SHAPE: Shape = {
  kind: 'object',
  keys: {
    data: {
      kind: 'object',
      keys: { severity: { kind: 'scalar', type: 'string' } }
    }
  }
};

/** Minimal editor stub: getValue/getSelection/executeEdits/focus. */
function makeEditor(value = '') {
  const executeEdits = vi.fn();
  const focus = vi.fn();
  return {
    spy: { executeEdits, focus },
    instance: {
      getValue: () => value,
      getSelection: () => ({
        startLineNumber: 1, startColumn: 1, endLineNumber: 1, endColumn: 1
      }),
      executeEdits,
      focus
    }
  };
}

beforeEach(() => {
  triggerModuleFieldsStore._reset();
  globalVarsStore._reset();
  jinjaShapesStore.setShapes({ Get_Alert: SHAPE });
  // Default fetch mock: return empty for global-vars (so existing
  // tests that don't care about globals don't see live entries leaking
  // into the picker).
  (globalThis as any).fetch = vi.fn().mockImplementation((url: string) => {
    if (url === '/api/ref/global-vars') {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    return Promise.resolve({ ok: false, json: async () => ({}) });
  });
});

afterEach(cleanup);

describe('JinjaVarPicker', () => {
  it('opens a popover with the {x} button', async () => {
    const { instance } = makeEditor();
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    expect(screen.queryByRole('dialog')).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('lists typed step paths from the shape store', async () => {
    const { instance } = makeEditor();
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('vars.steps.Get_Alert')).toBeTruthy();
    expect(within(dialog).getByText('vars.steps.Get_Alert.data')).toBeTruthy();
    expect(within(dialog).getByText('vars.steps.Get_Alert.data.severity')).toBeTruthy();
  });

  it('lists default input.records fields when YAML lacks a trigger', async () => {
    const { instance } = makeEditor('collection: T\nplaybooks: []');
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText("vars.input.records[0].name")).toBeTruthy();
    expect(within(dialog).getByText("vars.input.records[0]['@id']")).toBeTruthy();
  });

  it('upgrades to module-aware fields when the YAML has a trigger', async () => {
    (globalThis.fetch as any).mockImplementation((url: string) => {
      if (url === '/api/ref/global-vars') {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ fields: [{ name: 'sourceIp' }, { name: 'destinationIp' }] })
      });
    });
    const yaml = [
      'playbooks:',
      '  - name: P',
      '    steps:',
      '      - type: start_on_create',
      '        arguments:',
      '          module: alerts'
    ].join('\n');
    const { instance } = makeEditor(yaml);
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByText('vars.input.records[0].sourceIp')).toBeTruthy()
    );
    expect(within(dialog).getByText('vars.input.records[0].destinationIp')).toBeTruthy();
    // Defaults no longer present once the module fields took over.
    expect(within(dialog).queryByText('vars.input.records[0].severity')).toBeNull();
  });

  it('insert wraps the path in {{ }} and calls executeEdits on the editor selection', async () => {
    const { instance, spy } = makeEditor();
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    await fireEvent.click(within(dialog).getByText('vars.steps.Get_Alert.data.severity'));
    expect(spy.executeEdits).toHaveBeenCalledTimes(1);
    const [source, edits] = spy.executeEdits.mock.calls[0];
    expect(source).toBe('jinja-picker');
    expect(edits[0].text).toBe('{{ vars.steps.Get_Alert.data.severity }}');
    expect(spy.focus).toHaveBeenCalled();
  });

  it('lists live FSR globalVars when /api/ref/global-vars returns names', async () => {
    (globalThis.fetch as any).mockImplementation((url: string) => {
      if (url === '/api/ref/global-vars') {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { name: 'Current_Date', value: '{{arrow.utcnow().timestamp}}' },
            { name: 'API_Token', value: 'secret' }
          ]
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });
    const { instance } = makeEditor('# no globalVars referenced in buffer');
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByText('globalVars.API_Token')).toBeTruthy()
    );
    expect(within(dialog).getByText('globalVars.Current_Date')).toBeTruthy();
    // The `<name>` placeholder should be gone once we have real names.
    expect(within(dialog).queryByText('globalVars.<name>')).toBeNull();
  });

  it('falls back to buffer-scrape when the FSR catalog is empty', async () => {
    // Default mock already returns [] for /api/ref/global-vars; supply
    // a YAML that references a globalVar so the scrape finds something.
    const { instance } = makeEditor("v: '{{ globalVars.from_buffer }}'");
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByText('globalVars.from_buffer')).toBeTruthy()
    );
  });

  it('filters by the search input', async () => {
    const { instance } = makeEditor();
    render(JinjaVarPicker, { props: { editor: instance, monaco: {} } });
    await fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    const dialog = screen.getByRole('dialog');
    await fireEvent.input(within(dialog).getByPlaceholderText('filter…'), {
      target: { value: 'severity' }
    });
    expect(within(dialog).getByText('vars.steps.Get_Alert.data.severity')).toBeTruthy();
    expect(within(dialog).queryByText('vars.input.records[0].name')).toBeNull();
  });
});
