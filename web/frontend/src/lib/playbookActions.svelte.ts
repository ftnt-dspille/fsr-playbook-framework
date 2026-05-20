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
 * Source-of-truth YAML comes from `playbookStore.currentYaml`; callers
 * never pass YAML in — that avoids stale-buffer bugs where Design
 * had unsaved canvas edits but CLI ran against the on-disk text.
 */
import {
  validateYaml,
  compileYaml,
  pushPlaybook,
  analyzePlaybook,
  verifyPlaybook,
  type Marker,
  type Fix,
  type Diagnostic,
  type VerifyFix,
  type VerifyResult
} from './api';
import { jinjaShapesStore } from './jinjaShapesStore.svelte';
import type { Shape } from './shapeStubs';
import { playbookStore } from './playbookStore.svelte';
import { visualStore } from './visualEditStore.svelte';
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
  diagnostics: Diagnostic[];
  analyzeBusy: boolean;
  verify: VerifyResult | null;
  verifyBusy: boolean;
};

const state = $state<State>({
  markers: [],
  fixes: [],
  compileJson: null,
  status: { kind: 'idle', msg: 'editing' },
  diagnostics: [],
  analyzeBusy: false,
  verify: null,
  verifyBusy: false
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
  get diagnostics() { return state.diagnostics; },
  get analyzeBusy() { return state.analyzeBusy; },
  get analyzeErrorCount() { return state.diagnostics.filter((d) => d.severity === 'error').length; },
  get analyzeWarningCount() { return state.diagnostics.filter((d) => d.severity === 'warning').length; },
  /** Worst-severity diagnostic per step jkey, for canvas badges.
   * Step `name` with spaces→underscores is the canonical jkey. */
  get diagnosticsByStep(): Map<string, Diagnostic[]> {
    const m = new Map<string, Diagnostic[]>();
    for (const d of state.diagnostics) {
      const key = (d.step_id || '').replace(/\s+/g, '_');
      const arr = m.get(key) ?? [];
      arr.push(d);
      m.set(key, arr);
    }
    return m;
  },

  /** Validate the current playbook buffer. Cheap and idempotent;
   * called on a debounce in the page-level effect so the diagnostics
   * panel stays current without manual triggers. */
  async validate(): Promise<void> {
    await this.flushVisual();
    const yaml = playbookStore.currentYaml;
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

  /** Render-path validator — simulates the playbook offline and
   * surfaces data-access bugs (`vars.steps.X.Y` typos, missing keys,
   * required-empty fields) that `validate_yaml` can't see. Pass
   * `executeSafeOps: true` to also run C4 picklist drift against
   * the live FSR. */
  async analyze(opts: { executeSafeOps?: boolean } = {}): Promise<void> {
    await this.flushVisual();
    const yaml = playbookStore.currentYaml;
    if (!yaml) {
      state.diagnostics = [];
      return;
    }
    state.analyzeBusy = true;
    try {
      const r = await analyzePlaybook(yaml, opts);
      state.diagnostics = r.diagnostics;
      const errs = r.error_count;
      const warns = r.warning_count;
      state.status = errs === 0
        ? { kind: 'ok', msg: warns
            ? `analyzed · ${warns} render warning${warns > 1 ? 's' : ''}`
            : 'analyzed · no issues' }
        : { kind: 'err', msg: `analyzed · ${errs} render error${errs !== 1 ? 's' : ''}` };
    } catch (e: any) {
      state.status = { kind: 'err', msg: e?.message ?? String(e) };
    } finally {
      state.analyzeBusy = false;
    }
  },

  /** Compile to FSR JSON. Updates markers + the compile-JSON pane. */
  async compile(): Promise<void> {
    await this.flushVisual();
    const yaml = playbookStore.currentYaml;
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

  get verify() { return state.verify; },
  get verifyBusy() { return state.verifyBusy; },
  get verifyReady() { return !!state.verify?.ready_to_push; },
  get verifyFixCount() { return state.verify?.required_fixes.length ?? 0; },
  /** Worst severity per step jkey from the latest verify run.
   * Returns 'error' | 'warning' | null per step name (with spaces→underscores
   * because that's how the typed walker emits step ids — matches the
   * canvas's jkey scheme). */
  get verifyByStep(): Map<string, 'error' | 'warning'> {
    const m = new Map<string, 'error' | 'warning'>();
    const tag = (s: string, sev: 'error' | 'warning') => {
      const cur = m.get(s);
      if (cur === 'error') return;
      m.set(s, sev);
    };
    if (!state.verify) return m;
    for (const f of state.verify.required_fixes) {
      if (f.step) tag(f.step.replace(/\s+/g, '_'), 'error');
    }
    for (const w of state.verify.warnings) {
      if (w.step) tag(w.step.replace(/\s+/g, '_'), 'warning');
    }
    return m;
  },
  /** Run verify_playbook on the current buffer. Idempotent. Updates
   * `verify` state which the canvas reads to color step badges. */
  async runVerify(opts: { livePrope?: boolean } = {}): Promise<void> {
    await this.flushVisual();
    const yaml = playbookStore.currentYaml;
    if (!yaml) {
      state.verify = null;
      jinjaShapesStore.setShapes({});
      state.status = { kind: 'idle', msg: 'no playbook loaded' };
      return;
    }
    state.verifyBusy = true;
    state.status = { kind: 'busy', msg: 'verifying…' };
    try {
      // verbose:true so evidence.per_step_jinja_shapes comes back —
      // VarPathPicker + future Monaco completions consume this for
      // type-aware var-path suggestions. The marginal cost over a
      // non-verbose verify is negligible (just extra payload bytes).
      const r = await verifyPlaybook(yaml, { ...opts, verbose: true });
      state.verify = r;
      const shapes = (r.evidence?.per_step_jinja_shapes ?? {}) as Record<string, Shape>;
      jinjaShapesStore.setShapes(shapes);
      const n = r.required_fixes.length;
      const w = r.warnings.length;
      state.status = r.ready_to_push
        ? { kind: 'ok', msg: w ? `verified · ${w} warning${w === 1 ? '' : 's'}` : 'verified' }
        : { kind: 'err', msg: `${n} required fix${n === 1 ? '' : 'es'}` };
    } catch (e: any) {
      state.status = { kind: 'err', msg: e?.message ?? String(e) };
    } finally {
      state.verifyBusy = false;
    }
  },

  /** Flush any in-flight visual-canvas edits back into `playbookStore.currentYaml`
   * before an action reads it. Without this, Push / Push & Run / Validate
   * etc. operate on the last-loaded YAML even when the canvas has newer
   * edits (e.g. an AI-generated draft sitting on the canvas dirty but not
   * yet round-tripped through the emitter). No-op when the canvas is
   * clean or absent. */
  async flushVisual(): Promise<void> {
    if (!visualStore.state.graph || !visualStore.state.dirty) return;
    const rendered = await visualStore.renderToYaml();
    if (typeof rendered === 'string') playbookStore.replaceYaml(rendered);
  },

  /** Push the current YAML to the configured FSR. Returns true on
   * success so callers chaining (push → run) can short-circuit. */
  async push(): Promise<boolean> {
    await this.flushVisual();
    const yaml = playbookStore.currentYaml;
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
    // `push()` already flushed; re-read the buffer it persisted.
    const yaml = playbookStore.currentYaml;
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
