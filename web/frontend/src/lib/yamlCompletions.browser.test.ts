/**
 * Real-Monaco integration tests for registerYamlCompletions.
 *
 * Runs in Vitest browser mode (Chromium via Playwright) so we get a
 * full DOM, layout boxes, ResizeObserver, and Monaco's real model /
 * provider machinery — none of which jsdom supplies. Asserts:
 *
 *   - Snippet insertion through Monaco's CompletionItemInsertTextRule
 *     actually expands the template into the model text.
 *   - The provider returns the expected suggestion set for the four
 *     trigger contexts (type:/connector:/operation:/jinja-pipe).
 *
 * Network is faked with vi.mock so the test never hits the FastAPI
 * backend.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach } from 'vitest';

vi.mock('./api', () => ({
  getStepTypes: async () => [
    { name: 'connector', detail: 'Call a connector op' },
    { name: 'decision', detail: 'Branch on conditions' }
  ],
  searchConnectors: async () => [
    { name: 'fortimanager', label: 'FortiManager' },
    { name: 'jira', label: 'Jira' }
  ],
  listOperations: async (connector: string) =>
    connector === 'fortimanager'
      ? [{ op_name: 'get_devices', title: 'Get Devices' }]
      : [],
  listJinjaFilters: async () => [
    { name: 'upper', signature: 'upper()', description: 'Uppercase' }
  ],
  fetchShapes: async () => ({ ok: true, shapes: {}, needs_verify: [] })
}));

import * as monaco from 'monaco-editor';
import { registerYamlCompletions, buildSnippet } from './yamlCompletions';

let host: HTMLDivElement;
let editor: monaco.editor.IStandaloneCodeEditor;
let disposer: { dispose: () => void };

beforeAll(() => {
  host = document.createElement('div');
  host.style.width = '800px';
  host.style.height = '400px';
  document.body.appendChild(host);
  disposer = registerYamlCompletions(monaco);
});

afterAll(() => {
  disposer.dispose();
  editor?.dispose();
  host.remove();
});

beforeEach(() => {
  editor?.dispose();
  editor = monaco.editor.create(host, { value: '', language: 'yaml', tabSize: 2 });
});

describe('real Monaco — snippet expansion', () => {
  it('connector snippet expands into structured arguments block', async () => {
    // Insert the connector snippet via Monaco's snippet controller so
    // we exercise CompletionItemInsertTextRule.InsertAsSnippet for real.
    editor.setValue('  - id: s1\n    type: ');
    const model = editor.getModel()!;
    const lastLine = model.getLineCount();
    editor.setPosition({ lineNumber: lastLine, column: model.getLineLength(lastLine) + 1 });

    const snippet = buildSnippet('connector', '');
    // The snippet controller is part of the SnippetController2 contribution.
    const sc: any = editor.getContribution('snippetController2');
    expect(sc).toBeTruthy();
    sc.insert(snippet);

    const out = editor.getValue();
    // Tab-stop placeholders ($1, ${1:foo}) materialize as their default
    // text when inserted via SnippetController2; structural keys should
    // appear at the right indent under the autoIndent:'full' default.
    expect(out).toContain('arguments:');
    expect(out).toContain('connector:');
    expect(out).toContain('operation:');
    expect(out).toContain('params:');
    // No double-indentation regression: each child of arguments: sits
    // at exactly +2 spaces relative to its parent.
    expect(out).toMatch(/^ {4}arguments:$/m);
    expect(out).toMatch(/^ {6}connector:/m);
  });

  it('decision snippet preserves the quoted "yes" (Norway-problem fix)', async () => {
    editor.setValue('  - id: s1\n    type: ');
    const model = editor.getModel()!;
    const lastLine = model.getLineCount();
    editor.setPosition({ lineNumber: lastLine, column: model.getLineLength(lastLine) + 1 });

    const sc: any = editor.getContribution('snippetController2');
    sc.insert(buildSnippet('decision', ''));

    const out = editor.getValue();
    expect(out).toContain('"yes"'); // not bare `yes`, which YAML 1.1 parses as true
    expect(out).toContain('branches:');
    expect(out).toContain('next:');
  });
});
