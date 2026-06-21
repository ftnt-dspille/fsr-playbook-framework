/**
 * MonacoYaml lifecycle/prop wiring tests beyond the parent→setValue
 * path covered in EditorWiring.test.ts. Specifically:
 *
 *   - `readOnly` prop forwarded to monaco.editor.create options.
 *   - `onEditor` callback invoked with the editor + monaco namespace.
 *   - Programmatic value sync does NOT echo back through `onInput`
 *     (the `internalUpdate` guard prevents render-loops).
 *   - Identical value prop is a no-op (no redundant setValue).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, cleanup } from '@testing-library/svelte';
import * as monaco from 'monaco-editor';
import MonacoYaml from './MonacoYaml.svelte';

const createSpy = vi.fn();
const setValueSpy = vi.fn();
const realCreate = monaco.editor.create;
(monaco.editor as any).create = (host: HTMLElement, opts: any) => {
  createSpy(opts);
  const inst = realCreate(host, opts);
  const realSet = inst.setValue.bind(inst);
  inst.setValue = (v: string) => {
    setValueSpy(v);
    realSet(v);
  };
  return inst;
};

describe('MonacoYaml — prop wiring & internalUpdate guard', () => {
  beforeEach(() => {
    createSpy.mockClear();
    setValueSpy.mockClear();
  });
  afterEach(() => cleanup());

  it('forwards readOnly=true to monaco.editor.create options', async () => {
    render(MonacoYaml, {
      props: { value: 'x', onInput: () => {}, readOnly: true }
    });
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    const opts = createSpy.mock.calls.at(-1)![0];
    expect(opts.readOnly).toBe(true);
    expect(opts.language).toBe('yaml');
  });

  it('defaults readOnly to false when not provided', async () => {
    render(MonacoYaml, { props: { value: '', onInput: () => {} } });
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    expect(createSpy.mock.calls.at(-1)![0].readOnly).toBe(false);
  });

  it('invokes onEditor with the editor + monaco namespace once mounted', async () => {
    const onEditor = vi.fn();
    render(MonacoYaml, {
      props: { value: '', onInput: () => {}, onEditor }
    });
    await waitFor(() => expect(onEditor).toHaveBeenCalled());
    const [editor, monacoArg] = onEditor.mock.calls[0];
    expect(typeof editor.getValue).toBe('function');
    expect(typeof editor.setValue).toBe('function');
    expect(monacoArg.editor).toBeDefined();
    expect(monacoArg.languages).toBeDefined();
  });

  it('programmatic value change does NOT echo back through onInput', async () => {
    const onInput = vi.fn();
    const { rerender } = render(MonacoYaml, {
      props: { value: 'one', onInput }
    });
    // Mock seeds the editor's value via create() opts, so no mount-time
    // setValue fires; wait for the editor instance to exist instead.
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    onInput.mockClear();
    setValueSpy.mockClear();
    await rerender({ value: 'two', onInput });
    await waitFor(() => expect(setValueSpy).toHaveBeenCalledWith('two'));
    // The mock's setValue fires the change handler synchronously; if
    // internalUpdate weren't suppressing the echo, onInput would have
    // been called here.
    expect(onInput).not.toHaveBeenCalled();
  });

  it('skips redundant setValue when prop value matches editor value', async () => {
    const { rerender } = render(MonacoYaml, {
      props: { value: 'same', onInput: () => {} }
    });
    // Mock seeds value via create() opts, so no setValue at mount.
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    setValueSpy.mockClear();
    await rerender({ value: 'same', onInput: () => {} });
    // Same value → effect early-returns, no setValue.
    expect(setValueSpy).not.toHaveBeenCalled();
  });
});
