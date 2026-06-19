/**
 * Real-Monaco integration: assert that markers passed to MonacoYaml
 * actually result in decoration ranges Monaco knows about, anchored
 * to the correct line. The jsdom unit test (MonacoYamlMarkers.test.ts)
 * verifies the marker-payload shape; this one verifies Monaco actually
 * accepts and registers them against the live model.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import * as monaco from 'monaco-editor';
import MonacoYaml from './MonacoYaml.svelte';
import type { Marker } from '$lib/api';

const YAML = [
  'collection: T',
  'playbooks:',
  '  - name: P',
  '    steps:',
  '      - id: s1',
  '        type: connetor',
  '        arguments: {}'
].join('\n');

const MARKERS: Marker[] = [
  {
    line: 6,
    col: 9,
    severity: 'error',
    code: 'unknown_step_type',
    message: "unknown step type 'connetor'",
    path: 'playbooks[0].steps[0].type',
    suggestion: "did you mean 'connector'?"
  },
  {
    line: 3,
    col: 5,
    severity: 'warning',
    code: 'style',
    message: 'consider quoting the name',
    path: 'playbooks[0].name',
    suggestion: null
  }
];

let unmount: () => void;

beforeAll(async () => {
  const { unmount: u } = render(MonacoYaml, {
    props: { value: YAML, onInput: () => {}, markers: MARKERS }
  });
  unmount = u;
  // Wait for Monaco onMount to register the model with markers. There's
  // no public "ready" event — poll the model registry until our owner
  // shows up.
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const models = monaco.editor.getModels();
    if (models.length && monaco.editor.getModelMarkers({ owner: 'fsrpb' }).length) break;
    await new Promise((r) => setTimeout(r, 50));
  }
});

afterAll(() => {
  unmount?.();
  cleanup();
});

describe('MonacoYaml + real Monaco — diagnostics land on the correct line', () => {
  it('registers exactly the markers we passed under owner "fsrpb"', () => {
    const ms = monaco.editor.getModelMarkers({ owner: 'fsrpb' });
    expect(ms).toHaveLength(2);
  });

  it("error marker anchors on line 6 (the `type: connetor` line)", () => {
    const ms = monaco.editor.getModelMarkers({ owner: 'fsrpb' });
    const err = ms.find((m) => m.severity === monaco.MarkerSeverity.Error)!;
    expect(err).toBeTruthy();
    expect(err.startLineNumber).toBe(6);
    expect(err.endLineNumber).toBe(6);
    expect(err.startColumn).toBe(9);
    expect(err.source).toBe('unknown_step_type');
  });

  it('warning marker anchors on line 3 (the playbook name line)', () => {
    const ms = monaco.editor.getModelMarkers({ owner: 'fsrpb' });
    const warn = ms.find((m) => m.severity === monaco.MarkerSeverity.Warning)!;
    expect(warn.startLineNumber).toBe(3);
    expect(warn.source).toBe('style');
  });

  it('appends the suggestion to the error message with → separator', () => {
    const ms = monaco.editor.getModelMarkers({ owner: 'fsrpb' });
    const err = ms.find((m) => m.severity === monaco.MarkerSeverity.Error)!;
    expect(err.message).toBe(
      "unknown step type 'connetor'\n→ did you mean 'connector'?"
    );
  });
});
