/**
 * extractTriggerModule — YAML scan that finds the first trigger step's
 * `arguments.module` value. Used by the Monaco provider + JinjaVarPicker
 * to upgrade `vars.input.records[0].*` suggestions to module-aware fields.
 *
 * triggerModuleFieldsStore — async, deduped, cached fetch from
 * /api/ref/modules/<m>/fields.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  extractTriggerModule,
  triggerModuleFieldsStore,
  extractGlobalVarNames,
  globalVarsStore
} from './triggerModuleFields.svelte';

describe('extractTriggerModule', () => {
  it('finds module under start_on_create trigger', () => {
    const y = [
      'collection: T',
      'playbooks:',
      '  - name: P',
      '    steps:',
      '      - name: trig',
      '        type: start_on_create',
      '        arguments:',
      '          module: alerts'
    ].join('\n');
    expect(extractTriggerModule(y)).toBe('alerts');
  });

  it('finds module under start_on_update trigger', () => {
    const y = [
      '      - type: start_on_update',
      '        arguments:',
      '          module: incidents'
    ].join('\n');
    expect(extractTriggerModule(y)).toBe('incidents');
  });

  it('strips ?$limit= and trailing tails', () => {
    const y = [
      '      - type: start_on_create',
      '        arguments:',
      '          module: alerts?$limit=30'
    ].join('\n');
    expect(extractTriggerModule(y)).toBe('alerts');
  });

  it('strips surrounding quotes', () => {
    const y = [
      '      - type: start_on_create',
      '        arguments:',
      '          module: "alerts"'
    ].join('\n');
    expect(extractTriggerModule(y)).toBe('alerts');
  });

  it('returns null when no trigger step is present', () => {
    const y = 'collection: T\nplaybooks: []';
    expect(extractTriggerModule(y)).toBeNull();
  });

  it('returns null when the trigger has no module key', () => {
    const y = [
      '      - type: start_on_create',
      '        arguments:',
      '          something_else: foo'
    ].join('\n');
    expect(extractTriggerModule(y)).toBeNull();
  });

  it('does NOT consume module: from a later non-trigger step', () => {
    const y = [
      '      - type: start',
      '        next: x',
      '      - type: find_record',
      '        arguments:',
      '          module: tasks'
    ].join('\n');
    // The first `start` had no `module:` in its block; we must NOT
    // leak into the next sibling step's module.
    expect(extractTriggerModule(y)).toBeNull();
  });
});

describe('triggerModuleFieldsStore', () => {
  beforeEach(() => {
    triggerModuleFieldsStore._reset();
    (globalThis as any).fetch = vi.fn();
  });

  it('fetches /api/ref/modules/<m>/fields and returns name strings', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ fields: [{ name: 'sourceIp' }, { name: 'destIp' }] })
    });
    const fs = await triggerModuleFieldsStore.fieldsFor('alerts');
    expect(fs).toEqual(['sourceIp', 'destIp']);
    expect((globalThis.fetch as any)).toHaveBeenCalledWith('/api/ref/modules/alerts/fields');
  });

  it('handles bare-string field entries', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ fields: ['name', 'severity'] })
    });
    expect(await triggerModuleFieldsStore.fieldsFor('alerts')).toEqual(['name', 'severity']);
  });

  it('returns [] on non-ok response', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({ ok: false, json: async () => ({}) });
    expect(await triggerModuleFieldsStore.fieldsFor('alerts')).toEqual([]);
  });

  it('dedupes concurrent calls for the same module', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ fields: [{ name: 'x' }] })
    });
    const [a, b] = await Promise.all([
      triggerModuleFieldsStore.fieldsFor('alerts'),
      triggerModuleFieldsStore.fieldsFor('alerts')
    ]);
    expect(a).toEqual(['x']);
    expect(b).toEqual(['x']);
    expect((globalThis.fetch as any).mock.calls.length).toBe(1);
  });

  it('returns [] for empty module name without fetching', async () => {
    expect(await triggerModuleFieldsStore.fieldsFor('')).toEqual([]);
    expect((globalThis.fetch as any)).not.toHaveBeenCalled();
  });
});

describe('extractGlobalVarNames', () => {
  it('returns sorted unique names referenced in the YAML', () => {
    const yaml = [
      'arguments:',
      "  url: '{{ globalVars.fortimanager_url }}'",
      "  token: '{{ globalVars.api_token }}'",
      'condition: \'{{ globalVars.fortimanager_url and globalVars.api_token }}\''
    ].join('\n');
    expect(extractGlobalVarNames(yaml)).toEqual(['api_token', 'fortimanager_url']);
  });

  it('returns [] when no globalVars references exist', () => {
    expect(extractGlobalVarNames('collection: T')).toEqual([]);
    expect(extractGlobalVarNames('')).toEqual([]);
  });

  it('ignores non-identifier-looking suffixes', () => {
    // `globalVars.123abc` should not match (must start with letter/_).
    expect(extractGlobalVarNames("'{{ globalVars.123 }}'")).toEqual([]);
  });
});

describe('globalVarsStore', () => {
  beforeEach(() => {
    globalVarsStore._reset();
    (globalThis as any).fetch = vi.fn();
  });

  it('fetches /api/ref/global-vars and returns {name,value} pairs', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { name: 'Current_Date', value: '{{arrow.utcnow().timestamp}}' },
        { name: 'API_Token', value: 'secret' }
      ]
    });
    const out = await globalVarsStore.list();
    expect(out).toEqual([
      { name: 'Current_Date', value: '{{arrow.utcnow().timestamp}}' },
      { name: 'API_Token', value: 'secret' }
    ]);
  });

  it('drops entries with missing names', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'OK', value: '1' }, { value: '2' }, { name: '', value: '3' }]
    });
    const out = await globalVarsStore.list();
    expect(out.map((g) => g.name)).toEqual(['OK']);
  });

  it('returns [] on non-ok / network error', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({ ok: false, json: async () => [] });
    expect(await globalVarsStore.list()).toEqual([]);
  });

  it('dedupes concurrent calls into one fetch', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'X', value: null }]
    });
    const [a, b] = await Promise.all([globalVarsStore.list(), globalVarsStore.list()]);
    expect(a).toEqual([{ name: 'X', value: null }]);
    expect(b).toEqual([{ name: 'X', value: null }]);
    expect((globalThis.fetch as any).mock.calls.length).toBe(1);
  });
});
