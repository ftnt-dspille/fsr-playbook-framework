/**
 * Tests for the Monaco completion *provider* registered by
 * registerYamlCompletions — context-sensitive trigger regexes,
 * findConnectorAbove walk semantics, and result shape (insertText,
 * snippet rule, kind, range).
 *
 * Strategy: vi.mock the './api' module to control connector / op /
 * step-type / jinja-filter responses, then call the provider directly
 * against a hand-rolled fake `model` / `position`. The fake monaco
 * object exposes only the constants the provider reads.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./api', () => ({
  getStepTypes: vi.fn(async () => [
    { name: 'connector', detail: 'Call a connector op' },
    { name: 'decision', detail: 'Branch on conditions' },
    { name: 'weird_type', detail: 'no snippet' }
  ]),
  searchConnectors: vi.fn(async () => [
    { name: 'fortimanager', label: 'FortiManager' },
    { name: 'jira', label: 'Jira' }
  ]),
  listOperations: vi.fn(async (connector: string) => {
    if (connector === 'fortimanager')
      return [
        { op_name: 'get_devices', title: 'Get Devices' },
        { op_name: 'add_address', title: null }
      ];
    return [];
  }),
  listJinjaFilters: vi.fn(async () => [
    { name: 'upper', signature: 'upper()', description: 'Uppercase' },
    { name: 'default', signature: 'default(v)', description: null }
  ]),
  fetchShapes: vi.fn(async () => ({ ok: true, shapes: {}, needs_verify: [] }))
}));

import { registerYamlCompletions } from './yamlCompletions';
import { jinjaShapesStore } from './jinjaShapesStore.svelte';
import type { Shape } from './shapeStubs';

/** Build a fake monaco object that captures the provider passed to
 *  registerCompletionItemProvider so we can invoke it directly. */
function captureProvider() {
  const captured: { provider?: any } = {};
  const monaco = {
    languages: {
      registerCompletionItemProvider: (_lang: string, p: any) => {
        captured.provider = p;
        return { dispose: () => {} };
      },
      CompletionItemKind: {
        Snippet: 27,
        Module: 8,
        Function: 1,
        EnumMember: 16,
        Field: 4
      },
      CompletionItemInsertTextRule: { InsertAsSnippet: 4 }
    }
  };
  registerYamlCompletions(monaco);
  return { monaco, provider: captured.provider! };
}

/** Minimal Monaco model stub: hands back lines from an array and
 *  produces a word-range for the trailing word of the current line. */
function modelFromLines(lines: string[]) {
  return {
    getLineContent: (n: number) => lines[n - 1] ?? '',
    getWordUntilPosition: (pos: { lineNumber: number; column: number }) => {
      const line = lines[pos.lineNumber - 1] ?? '';
      const before = line.slice(0, pos.column - 1);
      const m = before.match(/[A-Za-z0-9_]*$/);
      const word = m ? m[0] : '';
      return {
        word,
        startColumn: pos.column - word.length,
        endColumn: pos.column
      };
    }
  };
}

function eolPosition(lines: string[], lineNumber: number) {
  return { lineNumber, column: (lines[lineNumber - 1] ?? '').length + 1 };
}

describe('registerYamlCompletions — trigger regexes', () => {
  let provider: any;
  beforeEach(() => {
    provider = captureProvider().provider;
  });

  it('type: trigger returns step-type snippets with InsertAsSnippet rule', async () => {
    const lines = ['  - id: s1', '    type: '];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 2)
    );
    const names = r.suggestions.map((s: any) => s.label);
    expect(names).toEqual(expect.arrayContaining(['connector', 'decision', 'weird_type']));

    const connector = r.suggestions.find((s: any) => s.label === 'connector');
    expect(connector.kind).toBe(27); // Snippet
    expect(connector.insertTextRules).toBe(4); // InsertAsSnippet
    expect(connector.insertText).toContain('arguments:');
    expect(connector.insertText).toContain('connector:');

    // Types without a snippet still appear and just insert the bare name.
    const weird = r.suggestions.find((s: any) => s.label === 'weird_type');
    expect(weird.insertText).toBe('weird_type');
    expect(weird.documentation).toBeUndefined();
  });

  it('range startColumn matches getWordUntilPosition (partial word)', async () => {
    const lines = ['    type: con'];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 1)
    );
    expect(r.suggestions.length).toBeGreaterThan(0);
    // 'con' is 3 chars; line length 13; column at EOL is 14 → startColumn 11.
    expect(r.suggestions[0].range.startColumn).toBe(11);
    expect(r.suggestions[0].range.endColumn).toBe(14);
  });

  it('connector: trigger returns module-kind connector suggestions', async () => {
    const lines = ['    arguments:', '      connector: ', '      operation: '];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 2)
    );
    const labels = r.suggestions.map((s: any) => s.label);
    expect(labels).toContain('fortimanager');
    expect(r.suggestions[0].kind).toBe(8); // Module
    // detail comes from `label` field of the connector record.
    expect(r.suggestions.find((s: any) => s.label === 'fortimanager').detail).toBe('FortiManager');
  });

  it('operation: trigger walks up to the nearest connector: line', async () => {
    const lines = [
      '  - id: s1',
      '    type: connector',
      '    arguments:',
      '      connector: fortimanager',
      '      operation: '
    ];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 5)
    );
    const labels = r.suggestions.map((s: any) => s.label);
    expect(labels).toEqual(expect.arrayContaining(['get_devices', 'add_address']));
    expect(r.suggestions[0].kind).toBe(1); // Function
  });

  it('operation: with quoted connector value strips the quotes', async () => {
    const lines = [
      '      connector: "fortimanager"',
      '      operation: '
    ];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 2)
    );
    expect(r.suggestions.map((s: any) => s.label)).toContain('get_devices');
  });

  it('operation: with no connector: above returns empty', async () => {
    const lines = ['      operation: '];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 1)
    );
    expect(r.suggestions).toEqual([]);
  });

  it('operation: stops walking at an outdent (different step)', async () => {
    // The walk in findConnectorAbove breaks at a line with no leading
    // whitespace. A top-level `connector:` MUST NOT be picked up for an
    // indented operation in a later step.
    const lines = [
      'connector: leaking_value', // column-0; walk-stops trigger here
      '  - id: other',
      '    arguments:',
      '      operation: '
    ];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 4)
    );
    expect(r.suggestions).toEqual([]);
  });

  it('jinja filter trigger fires inside an unclosed {{ ... |', async () => {
    const lines = ['  value: "{{ vars.x | "'];
    // Position right after the `|` and the space, before the closing `"}}`.
    const col = '  value: "{{ vars.x | '.length + 1;
    const r = await provider.provideCompletionItems(modelFromLines(lines), {
      lineNumber: 1,
      column: col
    });
    const labels = r.suggestions.map((s: any) => s.label);
    expect(labels).toEqual(expect.arrayContaining(['upper', 'default']));
    expect(r.suggestions[0].kind).toBe(1); // Function
  });

  it('jinja filter trigger does NOT fire when {{ is already closed before cursor', async () => {
    // `{{ foo }}` on the same line; the `|` after that is NOT in a jinja
    // expression. Provider should fall through to empty (or some other branch).
    const lines = ['  value: "{{ foo }} something | "'];
    const col = lines[0].length; // before closing quote
    const r = await provider.provideCompletionItems(modelFromLines(lines), {
      lineNumber: 1,
      column: col
    });
    // Filters must not be returned.
    const labels = r.suggestions.map((s: any) => s.label);
    expect(labels).not.toContain('upper');
  });

  describe('typed jinja path inside {{ ... }}', () => {
    const fetchShape: Shape = {
      kind: 'object',
      keys: {
        data: {
          kind: 'object',
          keys: { severity: { kind: 'scalar', type: 'string' } }
        }
      }
    };

    beforeEach(() => {
      jinjaShapesStore.setShapes({ Get_Alert: fetchShape });
    });

    it('suggests step keys at `{{ vars.steps.`', async () => {
      const lines = ['  value: "{{ vars.steps."'];
      const col = '  value: "{{ vars.steps.'.length + 1;
      const r = await provider.provideCompletionItems(modelFromLines(lines), {
        lineNumber: 1,
        column: col
      });
      expect(r.suggestions.map((s: any) => s.label)).toContain('Get_Alert');
      expect(r.suggestions[0].kind).toBe(4); // Field
    });

    it('suggests nested object keys with type hints', async () => {
      const lines = ['  value: "{{ vars.steps.Get_Alert.data."'];
      const col = '  value: "{{ vars.steps.Get_Alert.data.'.length + 1;
      const r = await provider.provideCompletionItems(modelFromLines(lines), {
        lineNumber: 1,
        column: col
      });
      const sev = r.suggestions.find((s: any) => s.label === 'severity');
      expect(sev).toBeTruthy();
      expect(sev.detail).toBe('string');
      expect(sev.kind).toBe(4); // Field
    });

    it('falls through to the filter branch once a `|` appears', async () => {
      // After `|`, the typed-path branch must NOT shadow filter completions.
      const lines = ['  value: "{{ vars.steps.Get_Alert.data | "'];
      const col = '  value: "{{ vars.steps.Get_Alert.data | '.length + 1;
      const r = await provider.provideCompletionItems(modelFromLines(lines), {
        lineNumber: 1,
        column: col
      });
      // Filters list — `upper` / `default` from the mock; NOT `data` / `severity`.
      const labels = r.suggestions.map((s: any) => s.label);
      expect(labels).toContain('upper');
      expect(labels).not.toContain('severity');
    });

    it('returns empty suggestions when no shapes are loaded', async () => {
      jinjaShapesStore.setShapes({});
      const lines = ['  value: "{{ vars.steps.Get_Alert.data."'];
      const col = '  value: "{{ vars.steps.Get_Alert.data.'.length + 1;
      const r = await provider.provideCompletionItems(modelFromLines(lines), {
        lineNumber: 1,
        column: col
      });
      expect(r.suggestions).toEqual([]);
    });
  });

  it('non-matching context returns empty suggestions', async () => {
    const lines = ['  description: hello world'];
    const r = await provider.provideCompletionItems(
      modelFromLines(lines),
      eolPosition(lines, 1)
    );
    expect(r.suggestions).toEqual([]);
  });
});
