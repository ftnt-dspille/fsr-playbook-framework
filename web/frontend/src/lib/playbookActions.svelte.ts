/**
 * Shared validate / compile / push / push-and-run pipeline.
 *
 * Both Design (visual canvas) and CLI (Monaco + chat) used to drive
 * these themselves — Design's "Live play" was a stub `alert()`, CLI
 * had a fully wired Push & Run. Consolidated here so the unified
 * BuildBar can call into one code path and both modes get parity.
 *
 * State lives on a singleton store: markers + fixes from the latest
 * validate/compile, the compile JSON output, run-time logs/exit code,
 * and a coarse status pill (`idle / busy / ok / err`). Both the
 * BuildBar (action triggers) and the diagnostics drawer (read-only
 * surface) bind to this store.
 *
 * Source-of-truth YAML comes from `playbookStore.yaml`; callers
 * never pass YAML in — that avoids stale-buffer bugs where Design
 * had unsaved canvas edits but CLI ran against the on-disk text.
 */
import {
  validateYaml,
  compileYaml,
  pushPlaybook,
  type Marker,
  type Fix
} from './api';
import { playbookStore } from './playbookStore.svelte';
import { runStore } from './runStore.svelte';
import { postSse } from './sse';

export type ActionStatus =
  | { kind: 'idle'; msg: string }
  | { kind: 'busy'; msg: string }
  | { kind: 'ok'; msg: string }
  | { kind: 'err'; msg: string };

type State = {
  markers: Marker[];
  fixes: Fix[];
  compileJson: string | null;
  status: ActionStatus;
};

const state = $state<State>({
  markers: [],
  fixes: [],
  compileJson: null,
  status: { kind: 'idle', msg: 'editing' }
});

function extractCollectionName(text: string): string | null {
  const m = text.match(/^\s*collection:\s*(.+?)\s*$/m);
  return m?.[1]?.replace(/^["']|["']$/g, '') ?? null;
}

function firstPlaybookName(text: string): string | null {
  const m = text.match(/playbooks:[\s\S]*?-\s*name:\s*(.+?)\s*$/m);
  return m?.[1]?.replace(/^["']|["']$/g, '') ?? null;
}

export const playbookActions = {
  get state() { return state; },
  get markers() { return state.markers; },
  get fixes() { return state.fixes; },
  get compileJson() { return state.compileJson; },
  get status() { return state.status; },
  get errorCount() { return state.markers.filter((m) => m.severity === 'error').length; },
  get warningCount() { return state.markers.filter((m) => m.severity === 'warning').length; },

  /** Validate the current playbook buffer. Cheap and idempotent;
   * called on a debounce in the page-level effect so the diagnostics
   * panel stays current without manual triggers. */
  async validate(): Promise<void> {
    const yaml = playbookStore.yaml;
    if (!yaml) {
      state.markers = [];
      state.fixes = [];
      state.status = { kind: 'idle', msg: 'no playbook loaded' };
      return;
    }
    try {
      const r = await validateYaml(yaml);
      state.markers = r.markers;
      state.fixes = r.fixes ?? [];
      const errs = r.markers.filter((m) => m.severity === 'error').length;
      const warns = r.markers.filter((m) => m.severity === 'warning').length;
      state.status = r.ok
        ? { kind: 'ok', msg: warns ? `valid · ${warns} warning${warns > 1 ? 's' : ''}` : 'valid' }
        : { kind: 'err', msg: `${errs} error${errs !== 1 ? 's' : ''}` };
    } catch (e: any) {
      state.status = { kind: 'err', msg: e?.message ?? String(e) };
    }
  },

  /** Compile to FSR JSON. Updates markers + the compile-JSON pane. */
  async compile(): Promise<void> {
    const yaml = playbookStore.yaml;
    state.status = { kind: 'busy', msg: 'compiling…' };
    try {
      const r = await compileYaml(yaml);
      state.markers = r.markers;
      state.compileJson = r.fsr_json ? JSON.stringify(r.fsr_json, null, 2) : null;
      state.status = r.ok
        ? { kind: 'ok', msg: 'compiled' }
        : { kind: 'err', msg: 'compile failed' };
    } catch (e: any) {
      state.status = { kind: 'err', msg: e?.message ?? String(e) };
    }
  },

  /** Push the current YAML to the configured FSR. Returns true on
   * success so callers chaining (push → run) can short-circuit. */
  async push(): Promise<boolean> {
    const yaml = playbookStore.yaml;
    runStore.reset();
    runStore.status = 'pushing';
    try {
      const r = await pushPlaybook(yaml);
      const out = (r.stdout || '').trim();
      const errBlock = (r.stderr || '').trim();
      runStore.pushOutput = [out, errBlock].filter(Boolean).join('\n');
      if (!r.ok) {
        runStore.status = 'error';
        runStore.errorMsg = `push failed (exit ${r.exit_code})`;
        state.status = { kind: 'err', msg: runStore.errorMsg };
        return false;
      }
      state.status = { kind: 'ok', msg: 'pushed' };
      runStore.status = 'idle';
      return true;
    } catch (e: any) {
      runStore.status = 'error';
      runStore.errorMsg = e?.message ?? String(e);
      state.status = { kind: 'err', msg: runStore.errorMsg ?? 'push error' };
      return false;
    }
  },

  /** Push, then trigger an FSR run; stream logs / task_id / exit_code
   * back into runStore. Used by both Design's "Live play" and CLI's
   * "Push & Run" so they stay in lockstep. */
  async pushAndRun(): Promise<void> {
    const ok = await this.push();
    if (!ok) return;
    const yaml = playbookStore.yaml;
    const coll = extractCollectionName(yaml);
    const pb = firstPlaybookName(yaml);
    if (!coll || !pb) {
      state.status = { kind: 'err', msg: 'cannot infer collection / playbook name' };
      return;
    }
    runStore.status = 'running';
    try {
      for await (const frame of postSse('/api/playbook/run', { name: `${coll}:${pb}` })) {
        if (frame.event === 'log') {
          const { line } = JSON.parse(frame.data);
          runStore.logs = [...runStore.logs, line];
        } else if (frame.event === 'task_id') {
          runStore.taskId = JSON.parse(frame.data).task_id;
        } else if (frame.event === 'done') {
          const { exit_code } = JSON.parse(frame.data);
          runStore.exitCode = exit_code;
          runStore.status = exit_code === 0 ? 'done' : 'error';
        } else if (frame.event === 'error') {
          runStore.errorMsg = JSON.parse(frame.data).message;
          runStore.status = 'error';
        }
      }
    } catch (e: any) {
      runStore.errorMsg = e?.message ?? String(e);
      runStore.status = 'error';
    }
  }
};
