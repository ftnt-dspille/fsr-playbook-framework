/**
 * MonacoCode — the slim wrapper used for code_snippet's Python/Jinja
 * editor (and any future non-YAML inspector field). Mirrors
 * MonacoYaml's prop-sync semantics but without YAML completion/hover.
 *
 * Covered:
 *   - `language` prop forwarded to monaco.editor.create (defaults to 'python').
 *   - `readOnly`, `height` plumbing.
 *   - Parent-driven value sync, internalUpdate guard, redundant-setValue no-op.
 *   - Placeholder ghost element shown only when value is empty.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, cleanup } from '@testing-library/svelte';
import * as monaco from 'monaco-editor';
import MonacoCode from './MonacoCode.svelte';

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

describe('MonacoCode — prop wiring', () => {
  beforeEach(() => {
    createSpy.mockClear();
    setValueSpy.mockClear();
  });
  afterEach(() => cleanup());

  it('defaults language to python', async () => {
    render(MonacoCode, { props: { value: '', onInput: () => {} } });
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    expect(createSpy.mock.calls.at(-1)![0].language).toBe('python');
  });

  it('forwards explicit language (e.g., json)', async () => {
    render(MonacoCode, {
      props: { value: '{}', onInput: () => {}, language: 'json' }
    });
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    expect(createSpy.mock.calls.at(-1)![0].language).toBe('json');
  });

  it('forwards readOnly=true', async () => {
    render(MonacoCode, {
      props: { value: 'x', onInput: () => {}, readOnly: true }
    });
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    expect(createSpy.mock.calls.at(-1)![0].readOnly).toBe(true);
  });

  it('renders host element with the height style', async () => {
    const { container } = render(MonacoCode, {
      props: { value: '', onInput: () => {}, height: '20rem' }
    });
    const wrapper = container.querySelector('div.relative') as HTMLDivElement;
    expect(wrapper).toBeTruthy();
    expect(wrapper.style.height).toBe('20rem');
  });

  it('placeholder is shown when value is empty and hidden once value present', async () => {
    const { container, rerender } = render(MonacoCode, {
      props: { value: '', onInput: () => {}, placeholder: 'enter code…' }
    });
    expect(container.textContent).toContain('enter code…');
    await rerender({ value: 'x = 1', onInput: () => {}, placeholder: 'enter code…' });
    expect(container.textContent).not.toContain('enter code…');
  });

  it('programmatic value change does not echo back through onInput', async () => {
    const onInput = vi.fn();
    const { rerender } = render(MonacoCode, {
      props: { value: 'one', onInput }
    });
    // Mock seeds value via create() opts — no setValue at mount.
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    onInput.mockClear();
    setValueSpy.mockClear();
    await rerender({ value: 'two', onInput });
    await waitFor(() => expect(setValueSpy).toHaveBeenCalledWith('two'));
    expect(onInput).not.toHaveBeenCalled();
  });

  it('skips setValue when prop value matches current editor value', async () => {
    const { rerender } = render(MonacoCode, {
      props: { value: 'same', onInput: () => {} }
    });
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
    setValueSpy.mockClear();
    await rerender({ value: 'same', onInput: () => {} });
    expect(setValueSpy).not.toHaveBeenCalled();
  });
});
