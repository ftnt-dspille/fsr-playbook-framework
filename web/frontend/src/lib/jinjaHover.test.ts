/**
 * Jinja hover provider — extracts the path under the cursor, resolves
 * its type via the shapes store, renders a markdown popup. Covers both
 * the path-extraction helper and the registered provider's contract.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { extractPathAtCursor, registerJinjaHover } from './jinjaHover';
import { jinjaShapesStore } from './jinjaShapesStore.svelte';
import type { Shape } from './shapeStubs';

const SHAPE: Shape = {
  kind: 'object',
  keys: {
    data: {
      kind: 'object',
      keys: {
        severity: { kind: 'scalar', type: 'string' },
        assignee: {
          kind: 'object',
          keys: { name: { kind: 'scalar', type: 'string' } }
        }
      }
    }
  }
};

function captureProvider() {
  const captured: { p?: any } = {};
  const monaco = {
    languages: {
      registerHoverProvider: (_lang: string, p: any) => {
        captured.p = p;
        return { dispose: () => {} };
      }
    }
  };
  registerJinjaHover(monaco);
  return captured.p!;
}

function modelFromLines(lines: string[], yamlText?: string) {
  return {
    getLineContent: (n: number) => lines[n - 1] ?? '',
    getValue: () => yamlText ?? lines.join('\n')
  };
}

describe('extractPathAtCursor', () => {
  it('returns the full path under the cursor inside `{{ }}`', () => {
    const line = '  value: "{{ vars.steps.Get_Alert.data.severity }}"';
    // Cursor on the `s` of `severity`.
    const col = line.indexOf('severity') + 2;
    expect(extractPathAtCursor(line, col)).toBe('vars.steps.Get_Alert.data.severity');
  });

  it('returns the path even when the cursor is at the trailing identifier', () => {
    const line = '  v: "{{ vars.steps.X.data }}"';
    const col = line.indexOf('data') + 1; // on the `d`
    expect(extractPathAtCursor(line, col)).toBe('vars.steps.X.data');
  });

  it('returns null when the cursor is outside any {{ }} expression', () => {
    const line = '  name: vars.steps.X.data  # not a template';
    const col = line.indexOf('data') + 2;
    expect(extractPathAtCursor(line, col)).toBeNull();
  });

  it('returns null when the cursor is after a closing }}', () => {
    const line = '  v: "{{ vars.steps.X.data }} and more vars.steps.Y";';
    const col = line.indexOf('vars.steps.Y') + 2;
    expect(extractPathAtCursor(line, col)).toBeNull();
  });

  it('returns null for non-vars paths', () => {
    const line = '  v: "{{ globalVars.foo.bar }}"';
    const col = line.indexOf('foo') + 1;
    expect(extractPathAtCursor(line, col)).toBeNull();
  });
});

describe('registerJinjaHover — integration with shapes store', () => {
  beforeEach(() => {
    jinjaShapesStore.setShapes({ Get_Alert: SHAPE });
  });

  it('shows the resolved type for a typed path', () => {
    const provider = captureProvider();
    const lines = ['  value: "{{ vars.steps.Get_Alert.data.severity }}"'];
    const col = lines[0].indexOf('severity') + 2;
    const r = provider.provideHover(modelFromLines(lines), {
      lineNumber: 1, column: col
    });
    expect(r).toBeTruthy();
    const md = r.contents[0].value as string;
    expect(md).toContain('vars.steps.Get_Alert.data.severity');
    expect(md).toContain('`string`');
  });

  it('shows `object` for an intermediate object key', () => {
    const provider = captureProvider();
    const lines = ['  value: "{{ vars.steps.Get_Alert.data.assignee }}"'];
    const col = lines[0].indexOf('assignee') + 2;
    const r = provider.provideHover(modelFromLines(lines), {
      lineNumber: 1, column: col
    });
    expect((r.contents[0].value as string)).toContain('`object`');
  });

  it('lists the keys of an object shape in the hover body', () => {
    const provider = captureProvider();
    const lines = ['  value: "{{ vars.steps.Get_Alert.data }}"'];
    const col = lines[0].indexOf('data') + 2;
    const r = provider.provideHover(modelFromLines(lines), {
      lineNumber: 1, column: col
    });
    const md = r.contents[0].value as string;
    expect(md).toContain('**keys:**');
    expect(md).toContain('`severity`');
    expect(md).toContain('`assignee`');
  });

  it('lists item keys for a list-of-objects shape', () => {
    jinjaShapesStore.setShapes({
      Tasks: {
        kind: 'list',
        item: {
          kind: 'object',
          keys: { id: { kind: 'scalar', type: 'integer' } }
        }
      }
    });
    const provider = captureProvider();
    const lines = ['  value: "{{ vars.steps.Tasks }}"'];
    const col = lines[0].indexOf('Tasks') + 2;
    const r = provider.provideHover(modelFromLines(lines), {
      lineNumber: 1, column: col
    });
    const md = r.contents[0].value as string;
    expect(md).toContain('**item keys:**');
    expect(md).toContain('`id`');
  });

  it('returns null when the path does not resolve in the store', () => {
    const provider = captureProvider();
    const lines = ['  value: "{{ vars.steps.Get_Alert.data.missing }}"'];
    const col = lines[0].indexOf('missing') + 2;
    const r = provider.provideHover(modelFromLines(lines), {
      lineNumber: 1, column: col
    });
    expect(r).toBeNull();
  });

  it('shows the module name for vars.input.records[0].<field>', () => {
    const yaml = [
      'playbooks:',
      '  - steps:',
      '      - type: start_on_create',
      '        arguments:',
      '          module: alerts',
      '  value: "{{ vars.input.records[0].severity }}"'
    ].join('\n');
    const provider = captureProvider();
    const lines = yaml.split('\n');
    const lineIdx = lines.findIndex((l) => l.includes('severity'));
    const col = lines[lineIdx].indexOf('severity') + 2;
    const r = provider.provideHover(modelFromLines(lines, yaml), {
      lineNumber: lineIdx + 1, column: col
    });
    const md = r.contents[0].value as string;
    expect(md).toContain('vars.input.records[0].severity');
    expect(md).toContain('`alerts`');
  });

  it('falls back to "trigger record" when no trigger module is present', () => {
    const yaml = '  value: "{{ vars.input.records[0].name }}"';
    const provider = captureProvider();
    const lines = [yaml];
    const col = lines[0].indexOf('name') + 2;
    const r = provider.provideHover(modelFromLines(lines, yaml), {
      lineNumber: 1, column: col
    });
    expect((r.contents[0].value as string)).toContain('trigger record');
  });

  it('returns null outside any {{ }} expression', () => {
    const provider = captureProvider();
    const lines = ['  description: just plain text vars.steps.X'];
    const r = provider.provideHover(modelFromLines(lines), {
      lineNumber: 1, column: lines[0].indexOf('X') + 1
    });
    expect(r).toBeNull();
  });
});
