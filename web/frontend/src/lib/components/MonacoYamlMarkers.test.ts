/**
 * MonacoYaml.applyMarkers — Marker[] → monaco.editor.setModelMarkers
 * mapping. Pins the contract that diagnostics line up on the *correct*
 * line in the editor (start/end line number passthrough, column +200
 * end-column trick, severity mapping, suggestion concat, source code).
 *
 * We intercept monaco.editor.setModelMarkers via the aliased mock and
 * capture every call, then drive MonacoYaml's `markers` prop from a
 * tiny harness component.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, cleanup } from '@testing-library/svelte';
import * as monaco from 'monaco-editor';
import type { Marker } from '$lib/api';

const setMarkersSpy = vi.fn();
(monaco.editor as any).setModelMarkers = (
  _model: unknown,
  owner: string,
  markers: any[]
) => setMarkersSpy(owner, markers);

import MonacoYaml from './MonacoYaml.svelte';

const MARKERS: Marker[] = [
  {
    line: 7,
    col: 3,
    severity: 'error',
    code: 'unknown_step_type',
    message: "unknown step type 'connetor'",
    path: 'playbooks[0].steps[0].type',
    suggestion: "did you mean 'connector'?"
  },
  {
    line: 12,
    col: 5,
    severity: 'warning',
    code: 'picklist_drift',
    message: 'value not in picklist',
    path: 'playbooks[0].steps[2].args.status',
    suggestion: null
  },
  {
    line: 3,
    col: 1,
    severity: 'info',
    code: 'style',
    message: 'note',
    path: '',
    suggestion: null
  }
];

describe('MonacoYaml.applyMarkers — Marker[] → setModelMarkers mapping', () => {
  beforeEach(() => setMarkersSpy.mockClear());
  afterEach(() => cleanup());

  it('passes line numbers through unchanged so diagnostics land on the right line', async () => {
    render(MonacoYaml, {
      props: { value: '', onInput: () => {}, markers: MARKERS }
    });
    await waitFor(() => expect(setMarkersSpy).toHaveBeenCalled());

    // The newest call carries the rendered markers (initial mount applies
    // them once); we read the last call to avoid racing with the empty
    // pre-mount state.
    const [owner, ms] = setMarkersSpy.mock.calls.at(-1)!;
    expect(owner).toBe('fsrpb');
    expect(ms).toHaveLength(3);

    expect(ms[0]).toMatchObject({
      startLineNumber: 7,
      endLineNumber: 7,
      startColumn: 3,
      endColumn: 203, // col + 200 — the squiggle stretches to end-of-line
      source: 'unknown_step_type'
    });
    expect(ms[1]).toMatchObject({
      startLineNumber: 12,
      endLineNumber: 12,
      startColumn: 5,
      endColumn: 205
    });
    expect(ms[2]).toMatchObject({
      startLineNumber: 3,
      endLineNumber: 3,
      startColumn: 1,
      endColumn: 201
    });
  });

  it('maps severity error/warning/info to Monaco MarkerSeverity constants', async () => {
    render(MonacoYaml, {
      props: { value: '', onInput: () => {}, markers: MARKERS }
    });
    await waitFor(() => expect(setMarkersSpy).toHaveBeenCalled());
    const ms = setMarkersSpy.mock.calls.at(-1)![1];
    const sev = (monaco as any).MarkerSeverity;
    expect(ms[0].severity).toBe(sev.Error);
    expect(ms[1].severity).toBe(sev.Warning);
    expect(ms[2].severity).toBe(sev.Info);
  });

  it('appends the suggestion to the message with a → separator', async () => {
    render(MonacoYaml, {
      props: { value: '', onInput: () => {}, markers: MARKERS }
    });
    await waitFor(() => expect(setMarkersSpy).toHaveBeenCalled());
    const ms = setMarkersSpy.mock.calls.at(-1)![1];
    expect(ms[0].message).toBe("unknown step type 'connetor'\n→ did you mean 'connector'?");
    // No suggestion → message left intact.
    expect(ms[1].message).toBe('value not in picklist');
    expect(ms[2].message).toBe('note');
  });

  it('clears markers when the prop becomes empty', async () => {
    const { rerender } = render(MonacoYaml, {
      props: { value: '', onInput: () => {}, markers: MARKERS }
    });
    await waitFor(() =>
      expect(setMarkersSpy.mock.calls.at(-1)?.[1]).toHaveLength(3)
    );
    await rerender({ value: '', onInput: () => {}, markers: [] });
    await waitFor(() =>
      expect(setMarkersSpy.mock.calls.at(-1)?.[1]).toHaveLength(0)
    );
  });
});
