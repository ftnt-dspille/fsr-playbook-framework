/**
 * Tests for the Jinja typed-path completion engine:
 *   - parsePathTail tokenizes dotted/bracket segments + partial trailing word
 *   - suggestForJinjaPath walks the shape store and returns the right
 *     next-key list (or null for contexts we don't handle)
 *   - non-identifier keys insert as `['key']` (bracket-escaped)
 */
import { describe, it, expect } from 'vitest';
import {
  parsePathTail,
  suggestForJinjaPath,
  resolveJinjaPathType,
  DEFAULT_RECORD_FIELDS
} from './jinjaPathCompletions';
import type { Shape } from './shapeStubs';

const SHAPES: Record<string, Shape> = {
  Get_Alert: {
    kind: 'object',
    keys: {
      data: {
        kind: 'object',
        keys: {
          severity: { kind: 'scalar', type: 'string' },
          'odd key': { kind: 'scalar', type: 'string' },
          assignee: {
            kind: 'object',
            keys: { name: { kind: 'scalar', type: 'string' } }
          }
        }
      }
    }
  },
  Find_Tasks: {
    kind: 'list',
    item: {
      kind: 'object',
      keys: { id: { kind: 'scalar', type: 'integer' } }
    }
  }
};

describe('parsePathTail', () => {
  it('tokenizes a plain dotted tail and captures the trailing partial', () => {
    expect(parsePathTail('.data.assi')).toEqual({
      segments: ['data'],
      partial: 'assi'
    });
  });

  it('tokenizes numeric index brackets; trailing identifier is the partial', () => {
    // `[0].id` with no trailing delimiter means the user is mid-typing `id` —
    // for completion semantics, that's a partial filter, not a committed segment.
    expect(parsePathTail('[0].id')).toEqual({
      segments: [0],
      partial: 'id'
    });
    // With a trailing dot, the previous identifier is committed.
    expect(parsePathTail('[0].id.')).toEqual({
      segments: [0, 'id'],
      partial: ''
    });
  });

  it('tokenizes bracket-quoted string keys (single and double quotes)', () => {
    expect(parsePathTail(`['odd key'].name`)).toEqual({
      segments: ['odd key'],
      partial: 'name'
    });
    expect(parsePathTail(`["odd key"].`)).toEqual({
      segments: ['odd key'],
      partial: ''
    });
  });

  it('returns empty segments + empty partial for a bare dot', () => {
    expect(parsePathTail('.')).toEqual({ segments: [], partial: '' });
  });
});

describe('suggestForJinjaPath', () => {
  it('returns null for unhandled contexts (globalVars, free text)', () => {
    expect(suggestForJinjaPath('{{ globalVars.foo', SHAPES)).toBeNull();
    expect(suggestForJinjaPath('{{ random text', SHAPES)).toBeNull();
  });

  it('lists known step jinja-keys at `vars.steps.`', () => {
    const out = suggestForJinjaPath('{{ vars.steps.', SHAPES)!;
    expect(out.map((s) => s.label).sort()).toEqual(['Find_Tasks', 'Get_Alert']);
    // Step-level detail mirrors the root shape's kind.
    expect(out.find((s) => s.label === 'Get_Alert')?.detail).toBe('object');
    expect(out.find((s) => s.label === 'Find_Tasks')?.detail).toBe('list<object>');
  });

  it('filters step names by the partial prefix the user has typed', () => {
    const out = suggestForJinjaPath('{{ vars.steps.Get', SHAPES)!;
    expect(out.map((s) => s.label)).toEqual(['Get_Alert']);
  });

  it('descends into an object Shape on `<step>.`', () => {
    const out = suggestForJinjaPath('{{ vars.steps.Get_Alert.', SHAPES)!;
    expect(out.map((s) => s.label).sort()).toEqual(['data']);
  });

  it('walks nested object keys', () => {
    const out = suggestForJinjaPath('{{ vars.steps.Get_Alert.data.', SHAPES)!;
    const labels = out.map((s) => s.label).sort();
    expect(labels).toEqual(['assignee', 'odd key', 'severity']);
  });

  it('bracket-escapes non-identifier keys in insertText', () => {
    const out = suggestForJinjaPath('{{ vars.steps.Get_Alert.data.', SHAPES)!;
    const odd = out.find((s) => s.label === 'odd key')!;
    expect(odd.insertText).toBe("['odd key']");
    // Identifier keys insert bare so the user's leading `.` lines up.
    const sev = out.find((s) => s.label === 'severity')!;
    expect(sev.insertText).toBe('severity');
  });

  it('descends through list index into the item shape', () => {
    const out = suggestForJinjaPath('{{ vars.steps.Find_Tasks[0].', SHAPES)!;
    expect(out.map((s) => s.label)).toEqual(['id']);
    expect(out[0].detail).toBe('integer');
  });

  it('filters by partial on nested levels', () => {
    const out = suggestForJinjaPath('{{ vars.steps.Get_Alert.data.sev', SHAPES)!;
    expect(out.map((s) => s.label)).toEqual(['severity']);
  });

  it('returns null when the step has no shape in the store', () => {
    expect(suggestForJinjaPath('{{ vars.steps.Unknown.', SHAPES)).toBeNull();
  });

  it('returns null when descending past a scalar', () => {
    // severity is a string; nothing dotted off of it should suggest.
    expect(suggestForJinjaPath('{{ vars.steps.Get_Alert.data.severity.', SHAPES)).toBeNull();
  });

  describe('globalVars.<name> autocomplete', () => {
    it('returns null when no globalVarNames are supplied', () => {
      expect(suggestForJinjaPath('{{ globalVars.', { shapes: SHAPES })).toBeNull();
    });

    it('lists buffer-derived names', () => {
      const out = suggestForJinjaPath('{{ globalVars.', {
        globalVarNames: ['api_token', 'base_url']
      })!;
      expect(out.map((s) => s.label)).toEqual(['api_token', 'base_url']);
      expect(out[0].detail).toBe('globalVar');
    });

    it('filters by partial', () => {
      const out = suggestForJinjaPath('{{ globalVars.api', {
        globalVarNames: ['api_token', 'base_url']
      })!;
      expect(out.map((s) => s.label)).toEqual(['api_token']);
    });
  });

  describe('vars.<name> (set_variable top-level)', () => {
    it('returns null when no topLevelVars are supplied', () => {
      expect(suggestForJinjaPath('{{ vars.s', { shapes: SHAPES })).toBeNull();
    });

    it('lists top-level vars at `vars.`', () => {
      const out = suggestForJinjaPath('{{ vars.', {
        topLevelVars: {
          severity: { kind: 'scalar', type: 'any' },
          assignee: { kind: 'scalar', type: 'any' }
        }
      })!;
      expect(out.map((s) => s.label).sort()).toEqual(['assignee', 'severity']);
      expect(out[0].detail).toBe('any');
    });

    it('filters by partial', () => {
      const out = suggestForJinjaPath('{{ vars.sev', {
        topLevelVars: { severity: { kind: 'scalar', type: 'any' }, other: { kind: 'scalar', type: 'any' } }
      })!;
      expect(out.map((s) => s.label)).toEqual(['severity']);
    });

    it('does NOT shadow vars.steps or vars.input', () => {
      // `vars.steps` and `vars.input` are reserved roots — the
      // top-level-vars branch must yield to the steps branch.
      expect(suggestForJinjaPath('{{ vars.steps', { topLevelVars: { steps: { kind: 'scalar', type: 'any' } } })).toBeNull();
      expect(suggestForJinjaPath('{{ vars.input', { topLevelVars: { input: { kind: 'scalar', type: 'any' } } })).toBeNull();
    });
  });

  describe('vars.input.records[N].* fallback', () => {
    it('lists default record fields when no module catalog is supplied', () => {
      const out = suggestForJinjaPath('{{ vars.input.records[0].', { shapes: SHAPES })!;
      const labels = out.map((s) => s.label);
      expect(labels).toEqual(DEFAULT_RECORD_FIELDS);
      expect(out[0].detail).toBe('record field');
    });

    it('filters record fields by the partial prefix', () => {
      const out = suggestForJinjaPath('{{ vars.input.records[0].na', { shapes: SHAPES })!;
      expect(out.map((s) => s.label)).toEqual(['name']);
    });

    it('uses caller-supplied module-aware fields when provided', () => {
      const out = suggestForJinjaPath(
        '{{ vars.input.records[0].',
        { shapes: SHAPES, inputRecordFields: ['sourceIp', 'destinationIp'] }
      )!;
      expect(out.map((s) => s.label)).toEqual(['sourceIp', 'destinationIp']);
    });

    it('bracket-escapes non-identifier record field names', () => {
      const out = suggestForJinjaPath(
        '{{ vars.input.records[0].',
        { shapes: SHAPES, inputRecordFields: ['@id', 'weird key'] }
      )!;
      expect(out.find((s) => s.label === '@id')?.insertText).toBe("['@id']");
      expect(out.find((s) => s.label === 'weird key')?.insertText).toBe("['weird key']");
    });
  });
});

describe('resolveJinjaPathType', () => {
  it('returns the root step Shape for `vars.steps.<key>`', () => {
    const t = resolveJinjaPathType('vars.steps.Get_Alert', SHAPES);
    expect(t?.kind).toBe('object');
  });

  it('walks dotted path and returns scalar with type', () => {
    const t = resolveJinjaPathType('vars.steps.Get_Alert.data.severity', SHAPES);
    expect(t).toEqual({ kind: 'scalar', type: 'string' });
  });

  it('walks through a list index', () => {
    const t = resolveJinjaPathType('vars.steps.Find_Tasks[0].id', SHAPES);
    expect(t).toEqual({ kind: 'scalar', type: 'integer' });
  });

  it('returns null when the path does not exist in the shape', () => {
    expect(resolveJinjaPathType('vars.steps.Get_Alert.data.missing', SHAPES)).toBeNull();
  });

  it('returns null when the step has no shape', () => {
    expect(resolveJinjaPathType('vars.steps.Unknown.data', SHAPES)).toBeNull();
  });

  it('returns null for non-vars.steps paths', () => {
    expect(resolveJinjaPathType('vars.input.records[0].name', SHAPES)).toBeNull();
  });
});
