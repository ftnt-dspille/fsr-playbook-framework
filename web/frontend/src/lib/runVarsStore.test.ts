import { describe, it, expect, beforeEach, vi } from 'vitest';
import { runVarsStore } from './runVarsStore.svelte';

// Mock the api module so selectRun reads canned run-detail payloads
// instead of hitting the backend. Each test reseats the mock.
vi.mock('./api', () => ({
  fetchRecentRuns: vi.fn(async () => []),
  fetchRunDetail: vi.fn(),
  fetchRecordByIri: vi.fn(async () => null)
}));
import { fetchRunDetail, fetchRecordByIri } from './api';

beforeEach(() => {
  runVarsStore._reset();
  vi.clearAllMocks();
});

describe('runVarsStore — trace probing', () => {
  it('prefers wf_step_logs when populated', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      wf_step_logs: [{ name: 'Find Issue', result: { id: 1 } }],
      step_logs: [{ name: 'WRONG', result: { id: 999 } }]
    });
    await runVarsStore.selectRun(42);
    expect(runVarsStore.stepOutputs).toEqual({ Find_Issue: { id: 1 } });
  });

  it('falls back to step_logs when wf_step_logs is empty', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      wf_step_logs: [],
      step_logs: [{ stepName: 'Decide', output: 'matched' }]
    });
    await runVarsStore.selectRun(43);
    expect(runVarsStore.stepOutputs).toEqual({ Decide: 'matched' });
  });

  it('falls back to stepInstances last', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      stepInstances: [{ step_name: 'A B C', data: { ok: true } }]
    });
    await runVarsStore.selectRun(44);
    // FSR collapses spaces in step names to underscores in vars.steps.<key>.
    expect(runVarsStore.stepOutputs).toEqual({ A_B_C: { ok: true } });
  });

  it('falls back to non-metadata fields as output when no known output key matches', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      wf_step_logs: [{ name: 'Weird', status: 'success', payload: { x: 1 }, extra: 2 }]
    });
    await runVarsStore.selectRun(45);
    // status is metadata; payload + extra survive as the synthetic output.
    expect(runVarsStore.stepOutputs).toEqual({ Weird: { payload: { x: 1 }, extra: 2 } });
  });

  it('skips trace entries with no resolvable step name', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      wf_step_logs: [
        { result: { x: 1 } },                           // no name → skip
        { name: 'Good', result: 'kept' }
      ]
    });
    await runVarsStore.selectRun(46);
    expect(Object.keys(runVarsStore.stepOutputs)).toEqual(['Good']);
  });

  it('mines flat-dict step outputs as candidate top-level vars', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      wf_step_logs: [{ name: 'set vars', result: { severity: 'high', tally: 7 } }]
    });
    await runVarsStore.selectRun(47);
    expect(runVarsStore.topLevelVars).toEqual({ severity: 'high', tally: 7 });
  });

  it('hydrates inputRecord from the first record IRI', async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      records: ['/api/3/alerts/abc-123']
    });
    (fetchRecordByIri as any).mockResolvedValue({ name: 'Alert A', severity: 'high' });
    await runVarsStore.selectRun(48);
    expect(fetchRecordByIri).toHaveBeenCalledWith('/api/3/alerts/abc-123');
    expect(runVarsStore.inputRecord).toEqual({ name: 'Alert A', severity: 'high' });
  });

  it('surfaces detailError when fetch fails', async () => {
    (fetchRunDetail as any).mockResolvedValue({ ok: false, error: 'HTTP 500' });
    await runVarsStore.selectRun(49);
    expect(runVarsStore.detailError).toBe('HTTP 500');
    expect(runVarsStore.stepOutputs).toEqual({});
  });

  it('selecting the same run id again is a no-op (avoids refetch churn)', async () => {
    (fetchRunDetail as any).mockResolvedValue({ ok: true, wf_step_logs: [] });
    await runVarsStore.selectRun(50);
    await runVarsStore.selectRun(50);
    expect(fetchRunDetail).toHaveBeenCalledTimes(1);
  });
});

describe('runVarsStore.observedAt — path resolution', () => {
  beforeEach(async () => {
    (fetchRunDetail as any).mockResolvedValue({
      ok: true,
      records: ['/api/3/alerts/x'],
      wf_step_logs: [
        { name: 'Fetch', result: { data: [{ id: 1, name: 'first' }, { id: 2 }] } },
        { name: 'set vars', result: { severity: 'high' } }
      ]
    });
    (fetchRecordByIri as any).mockResolvedValue({
      name: 'Alert A',
      'weird-key': 42,
      severity: { itemValue: 'High' }
    });
    await runVarsStore.selectRun(100);
  });

  it('resolves vars.input.records[0].<field>', () => {
    expect(runVarsStore.observedAt('vars.input.records[0].name'))
      .toEqual({ found: true, value: 'Alert A' });
  });

  it("resolves vars.input.records[0]['quoted-key']", () => {
    expect(runVarsStore.observedAt("vars.input.records[0]['weird-key']"))
      .toEqual({ found: true, value: 42 });
  });

  it('returns not-found for records[N] where N != 0', () => {
    expect(runVarsStore.observedAt('vars.input.records[1].name'))
      .toEqual({ found: false });
  });

  it('resolves vars.steps.<key> at any depth', () => {
    expect(runVarsStore.observedAt('vars.steps.Fetch.data[0].id'))
      .toEqual({ found: true, value: 1 });
    expect(runVarsStore.observedAt('vars.steps.Fetch.data[1].id'))
      .toEqual({ found: true, value: 2 });
  });

  it('returns not-found when a step key is missing', () => {
    expect(runVarsStore.observedAt('vars.steps.Missing.data'))
      .toEqual({ found: false });
  });

  it('returns not-found when a path segment misses', () => {
    expect(runVarsStore.observedAt('vars.steps.Fetch.data[0].nonexistent'))
      .toEqual({ found: false });
  });

  it('resolves vars.<topLevel> from mined set_variable-shaped outputs', () => {
    expect(runVarsStore.observedAt('vars.severity'))
      .toEqual({ found: true, value: 'high' });
  });

  it('always returns not-found for vars.input.params (params aren\'t mined)', () => {
    expect(runVarsStore.observedAt("vars.input.params['foo']"))
      .toEqual({ found: false });
  });

  it('always returns not-found for globalVars (tenant-scoped, not run-scoped)', () => {
    expect(runVarsStore.observedAt('globalVars.tenant_id'))
      .toEqual({ found: false });
  });
});
