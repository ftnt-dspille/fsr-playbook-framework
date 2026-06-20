/**
 * Coverage for the debug runner UI. Pins:
 *  - ▶ Run is the single primary action — creates a session AND
 *    continues to done/breakpoint. No separate Start click.
 *  - ⏭ Step also creates a session on first click and advances one
 *    tile (auto-skipping the trigger entry).
 *  - Tile shift-click toggles a breakpoint; the persisted set rides
 *    on the next ▶ Run via `addBreakpoints`.
 *  - ⏹ Stop drops the session but leaves the trace visible; the
 *    primary button flips to ↺ Restart so rerun is obvious.
 *
 * MCP layer mocked at the module boundary. Assertions are on the
 * arguments the panel sends.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/svelte';

import type { DebugSessionResponse, DebugSessionStatus, DebugStepFrame } from '../api';

const startDebugSession = vi.fn();
const stepDebugSession = vi.fn();
const continueDebugSession = vi.fn();
const stopDebugSession = vi.fn();
const getDebugSession = vi.fn();

vi.mock('../api', () => ({
  startDebugSession: (...a: unknown[]) => startDebugSession(...a),
  stepDebugSession: (...a: unknown[]) => stepDebugSession(...a),
  continueDebugSession: (...a: unknown[]) => continueDebugSession(...a),
  stopDebugSession: (...a: unknown[]) => stopDebugSession(...a),
  getDebugSession: (...a: unknown[]) => getDebugSession(...a),
}));

vi.mock('../playbookStore.svelte', () => ({
  playbookStore: { get currentYaml() { return 'playbooks: [{name: P, steps: []}]'; } },
}));

import DebugPanel from './DebugPanel.svelte';

function frame(step_id: string, status = 'simulated', type = 'set_variable'): DebugStepFrame {
  return { step_id, type, status, rendered_args: {}, output: {} };
}

function makeStatus(overrides: Partial<DebugSessionStatus> = {}): DebugSessionStatus {
  return {
    session_id: 'sess-abc',
    playbook: 'P',
    done: false,
    paused_at: 't',
    steps_advanced: 0,
    trace_len: 0,
    breakpoints: [],
    trace: [],
    last_step: null,
    ...overrides,
  };
}

function ok(status: DebugSessionStatus, extras: Partial<DebugSessionResponse> = {}): DebugSessionResponse {
  return { ok: true, status, ...extras };
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  // Sensible defaults so unmocked calls during auto-advance don't
  // leak unhandled rejections. Specific tests override with
  // mockResolvedValueOnce when they need a particular shape.
  const benign = ok(makeStatus({ paused_at: 'a', steps_advanced: 1, trace: [frame('t')], last_step: frame('t'), trace_len: 1 }));
  startDebugSession.mockResolvedValue(ok(makeStatus({ paused_at: 't' })));
  stepDebugSession.mockResolvedValue(benign);
  continueDebugSession.mockResolvedValue(benign);
  stopDebugSession.mockResolvedValue(benign);
  getDebugSession.mockResolvedValue(benign);
});

describe('DebugPanel', () => {
  it('Run creates a session AND continues end-to-end in a single click', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    continueDebugSession.mockResolvedValueOnce(ok(makeStatus({
      done: true,
      paused_at: null,
      trace: [frame('t'), frame('a'), frame('b')],
      last_step: frame('b'),
      steps_advanced: 3,
      trace_len: 3,
    })));
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    expect(startDebugSession).toHaveBeenCalledOnce();
    expect(continueDebugSession).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.getByText(/done/i)).toBeInTheDocument());
  });

  it('Step creates a session on first click and advances one tile', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    stepDebugSession.mockResolvedValueOnce(ok(makeStatus({
      paused_at: 'a',
      steps_advanced: 1,
      trace_len: 1,
      trace: [frame('t', 'simulated', 'set_variable')],
      last_step: frame('t', 'simulated', 'set_variable'),
    })));
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Step/ }));
    // Session created AND stepped — one round trip each.
    expect(startDebugSession).toHaveBeenCalledOnce();
    expect(stepDebugSession).toHaveBeenCalledWith('sess-abc', undefined);
  });

  it('Step auto-skips the start trigger so the first tile is interesting', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    // First Step result is the trigger entry → component should auto-step again.
    stepDebugSession.mockResolvedValueOnce(ok(makeStatus({
      paused_at: 'a',
      steps_advanced: 1,
      trace_len: 1,
      trace: [frame('t', 'simulated', 'start')],
      last_step: frame('t', 'simulated', 'start'),
    })));
    // Second auto-step lands on the first real step.
    stepDebugSession.mockResolvedValueOnce(ok(makeStatus({
      paused_at: 'b',
      steps_advanced: 2,
      trace_len: 2,
      trace: [frame('t', 'simulated', 'start'), frame('a')],
      last_step: frame('a'),
    })));
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Step/ }));
    // Two step calls fire from one click (manual + auto-skip). The
    // auto-skip is async after the first response settles, so wait.
    await waitFor(() => expect(stepDebugSession).toHaveBeenCalledTimes(2));
  });

  it('Run with a breakpoint pauses there and surfaces the stop_reason', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    continueDebugSession.mockResolvedValueOnce(ok(
      makeStatus({
        paused_at: 'b',
        trace: [frame('t'), frame('a')],
        last_step: frame('a'),
        steps_advanced: 2,
        trace_len: 2,
      }),
      { stop_reason: 'breakpoint' },
    ));
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    await waitFor(() => expect(screen.getAllByText(/breakpoint/).length).toBeGreaterThan(0));
  });

  it('shift-click on a tile adds it as a breakpoint for the next Run', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    stepDebugSession.mockResolvedValueOnce(ok(makeStatus({
      paused_at: 'a',
      trace: [frame('t')],
      last_step: frame('t'),
      steps_advanced: 1,
      trace_len: 1,
    })));
    continueDebugSession.mockResolvedValueOnce(ok(makeStatus({
      paused_at: 'a',
      trace: [frame('t')],
      last_step: frame('t'),
      done: false,
      breakpoints: ['a'],
    }), { stop_reason: 'breakpoint' }));

    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Step/ }));
    // Wait for the tile to appear in the tape (ensureSession + step is
    // a two-promise cascade, so the tile isn't there synchronously).
    const tile = await screen.findByRole('button', { name: /1\.\s*t/ });
    await fireEvent.click(tile, { shiftKey: true });
    await fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    expect(continueDebugSession).toHaveBeenCalledWith(
      'sess-abc',
      expect.objectContaining({ addBreakpoints: expect.arrayContaining(['t']) }),
    );
  });

  it('Stop drops the session and flips Run → Restart', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    stopDebugSession.mockResolvedValueOnce(ok(makeStatus({
      done: true,
      trace: [frame('t')],
      paused_at: null,
    })));
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    await fireEvent.click(screen.getByRole('button', { name: /Stop/ }));
    expect(stopDebugSession).toHaveBeenCalledWith('sess-abc');
    await waitFor(() => screen.getByRole('button', { name: /Restart/ }));
  });

  it('Restart drops the prior session and creates a new one', async () => {
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't' })));
    stopDebugSession.mockResolvedValueOnce(ok(makeStatus({
      done: true,
      trace: [frame('t')],
      paused_at: null,
    })));
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    await fireEvent.click(screen.getByRole('button', { name: /Stop/ }));
    await waitFor(() => screen.getByRole('button', { name: /Restart/ }));
    startDebugSession.mockResolvedValueOnce(ok(makeStatus({ paused_at: 't', session_id: 'sess-2' })));
    await fireEvent.click(screen.getByRole('button', { name: /Restart/ }));
    // Old session was stopped; new one was started.
    expect(startDebugSession).toHaveBeenCalledTimes(2);
  });

  it('Stop is disabled before a session exists', () => {
    render(DebugPanel);
    expect(screen.getByRole('button', { name: /Stop/ })).toBeDisabled();
  });

  it('surfaces a server error in the error banner', async () => {
    startDebugSession.mockResolvedValueOnce({ ok: false, error: 'yaml parse failed' } as DebugSessionResponse);
    render(DebugPanel);
    await fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    await waitFor(() => expect(screen.getByText(/yaml parse failed/)).toBeInTheDocument());
  });
});
