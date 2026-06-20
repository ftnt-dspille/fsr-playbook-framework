/**
 * Parent-state → MonacoYaml setValue wiring.
 *
 * Originally tested ExamplesMenu → onLoad → state → MonacoYaml. The
 * menu was retired when PlaybookHeader took over playbook loading;
 * the underlying prop-propagation contract is what this test now
 * pins (any state change pushed to MonacoYaml's `value` prop calls
 * editor.setValue).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/svelte';
import * as monaco from 'monaco-editor';

const setValueSpy = vi.fn();
const valueByEditor: { current: string } = { current: '' };

const realCreate = monaco.editor.create;
(monaco.editor as any).create = (host: HTMLElement, opts: { value?: string }) => {
  const inst = realCreate(host, opts);
  valueByEditor.current = opts?.value ?? '';
  const realSet = inst.setValue.bind(inst);
  inst.setValue = (v: string) => {
    valueByEditor.current = v;
    setValueSpy(v);
    realSet(v);
  };
  inst.getValue = () => valueByEditor.current;
  return inst;
};

describe('Parent-state → MonacoYaml wiring', () => {
  beforeEach(() => {
    setValueSpy.mockClear();
    valueByEditor.current = '';
  });

  afterEach(() => cleanup());

  it('a state mutation in the parent triggers Monaco setValue', async () => {
    const Harness = (await import('./__test_harness/EditorWiring.svelte')).default;
    render(Harness);

    expect(screen.getByTestId('yaml-mirror').textContent).toBe('initial');

    // MonacoYaml.onMount does an async import of `monaco-editor` before
    // calling editor.create — so the click below MUST happen after the
    // editor exists, otherwise the harness state mutates before
    // editor.setValue is even hookable. Spin until the constructor has
    // recorded the initial value through our instrumented stub.
    await waitFor(() => expect(valueByEditor.current).toBe('initial'));

    fireEvent.click(screen.getByRole('button', { name: 'Load YAML' }));

    await waitFor(() => {
      expect(screen.getByTestId('yaml-mirror').textContent).toContain('collection: A');
    });
    await waitFor(() => {
      expect(setValueSpy).toHaveBeenCalledWith(expect.stringContaining('collection: A'));
    });
    expect(valueByEditor.current).toBe('collection: A\nplaybooks: []\n');
  });
});
