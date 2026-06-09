/**
 * Per-run observed-variable extractor for the Variable Tree pane's
 * "Real run" mode.
 *
 * FSR's workflow-execution detail includes step traces, but the field
 * name + shape vary by version — we probe `wf_step_logs`, `step_logs`,
 * and `stepInstances` in that order and pull whichever has data. Each
 * trace entry is normalized into `{ stepKey: observedOutput }` so the
 * pane can look up a Jinja path like `vars.steps.Find_Issue.data[0].id`
 * and walk into the real value the run produced.
 *
 * Also extracts the trigger record (`vars.input.records[0]`) from the
 * run detail when present, plus any top-level `vars.<name>` written
 * by set_variable-shaped step outputs.
 *
 * Observed values feed the pane via `observedAt(path)` which returns
 * `{ found: true, value }` for paths the run actually populated, or
 * `{ found: false }` so leaves with no data can render dimmed.
 */
import {
  type RecentRun,
  fetchRecentRuns,
  fetchRunDetail,
  fetchRecordByIri
} from './api';

type StepKey = string;

class RunVarsStore {
  runs = $state<RecentRun[]>([]);
  runsLoading = $state(false);
  runsError = $state<string | null>(null);

  selectedRunId = $state<number | null>(null);
  detailLoading = $state(false);
  detailError = $state<string | null>(null);

  stepOutputs = $state<Record<StepKey, unknown>>({});
  inputRecord = $state<Record<string, unknown> | null>(null);
  topLevelVars = $state<Record<string, unknown>>({});

  async loadRuns(playbookIri?: string): Promise<void> {
    this.runsLoading = true;
    this.runsError = null;
    try {
      const rs = await fetchRecentRuns(playbookIri, 10);
      this.runs = rs;
    } catch (e: any) {
      this.runsError = e?.message ?? String(e);
      this.runs = [];
    } finally {
      this.runsLoading = false;
    }
  }

  async selectRun(runId: number | null): Promise<void> {
    if (runId === this.selectedRunId) return;
    this.selectedRunId = runId;
    this.detailError = null;
    this.stepOutputs = {};
    this.inputRecord = null;
    this.topLevelVars = {};
    if (runId == null) return;
    this.detailLoading = true;
    try {
      const detail = await fetchRunDetail(runId);
      if (!detail.ok) {
        this.detailError = detail.error ?? 'fetch failed';
        return;
      }
      const traces = pickFirstNonEmpty([
        detail.wf_step_logs,
        detail.step_logs,
        detail.stepInstances
      ]);
      const outs: Record<StepKey, unknown> = {};
      const topLevel: Record<string, unknown> = {};
      for (const t of traces) {
        const name = pickStepName(t);
        if (!name) continue;
        const out = pickStepOutput(t);
        if (out === undefined) continue;
        outs[stepKey(name)] = out;
        if (out && typeof out === 'object' && !Array.isArray(out)) {
          for (const [k, v] of Object.entries(out as Record<string, unknown>)) {
            if (/^[A-Za-z_]\w*$/.test(k) && topLevel[k] === undefined) {
              topLevel[k] = v;
            }
          }
        }
      }
      this.stepOutputs = outs;
      this.topLevelVars = topLevel;

      const recs = detail.records ?? [];
      if (recs.length && typeof recs[0] === 'string') {
        try {
          const body = await fetchRecordByIri(recs[0]);
          if (body) this.inputRecord = body;
        } catch {
          /* leave inputRecord null */
        }
      }
    } catch (e: any) {
      this.detailError = e?.message ?? String(e);
    } finally {
      this.detailLoading = false;
    }
  }

  observedAt(path: string): { found: true; value: unknown } | { found: false } {
    const m1 = path.match(/^vars\.input\.records\[(\d+)\](.*)$/);
    if (m1) {
      const idx = Number(m1[1]);
      if (idx !== 0 || !this.inputRecord) return { found: false };
      return walk(this.inputRecord, m1[2]);
    }
    if (path.startsWith('vars.input.params')) return { found: false };
    const m2 = path.match(/^vars\.steps\.([A-Za-z_]\w*)(.*)$/);
    if (m2) {
      const key = m2[1];
      if (!(key in this.stepOutputs)) return { found: false };
      return walk(this.stepOutputs[key], m2[2]);
    }
    const m3 = path.match(/^vars\.([A-Za-z_]\w*)(.*)$/);
    if (m3 && m3[1] !== 'input' && m3[1] !== 'steps') {
      const key = m3[1];
      if (!(key in this.topLevelVars)) return { found: false };
      return walk(this.topLevelVars[key], m3[2]);
    }
    return { found: false };
  }

  _reset(): void {
    this.runs = [];
    this.runsLoading = false;
    this.runsError = null;
    this.selectedRunId = null;
    this.detailLoading = false;
    this.detailError = null;
    this.stepOutputs = {};
    this.inputRecord = null;
    this.topLevelVars = {};
  }
}

export const runVarsStore = new RunVarsStore();

function pickFirstNonEmpty(candidates: unknown[]): Array<Record<string, unknown>> {
  for (const c of candidates) {
    if (Array.isArray(c) && c.length) {
      return c.filter((x) => x && typeof x === 'object') as Array<Record<string, unknown>>;
    }
  }
  return [];
}

function pickStepName(t: Record<string, unknown>): string | null {
  const candidates = ['name', 'stepName', 'step_name', 'step', 'title', 'label'];
  for (const k of candidates) {
    const v = t[k];
    if (typeof v === 'string' && v.trim()) return v.trim();
    if (v && typeof v === 'object' && typeof (v as any).name === 'string') {
      return (v as any).name;
    }
  }
  return null;
}

function pickStepOutput(t: Record<string, unknown>): unknown {
  for (const k of ['result', 'output', 'data', 'step_variables', 'vars', 'value']) {
    if (k in t) return t[k];
  }
  const meta = new Set([
    'name', 'stepName', 'step_name', 'step', 'title', 'label',
    'id', 'uuid', 'status', 'created', 'modified', 'order'
  ]);
  const rest: Record<string, unknown> = {};
  let any = false;
  for (const [k, v] of Object.entries(t)) {
    if (meta.has(k)) continue;
    rest[k] = v;
    any = true;
  }
  return any ? rest : undefined;
}

function stepKey(name: string): string {
  return name.replace(/\s+/g, '_');
}

function walk(root: unknown, suffix: string): { found: true; value: unknown } | { found: false } {
  if (suffix === '') return { found: true, value: root };
  const re = /\.([A-Za-z_]\w*)|\[(\d+)\]|\['([^']+)'\]|\["([^"]+)"\]/g;
  let cur: unknown = root;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(suffix)) !== null) {
    if (m.index !== lastIdx) return { found: false };
    lastIdx = re.lastIndex;
    if (cur == null) return { found: false };
    if (m[1] !== undefined) {
      cur = (cur as Record<string, unknown>)[m[1]];
    } else if (m[2] !== undefined) {
      const idx = Number(m[2]);
      cur = Array.isArray(cur) ? cur[idx] : undefined;
    } else if (m[3] !== undefined) {
      cur = (cur as Record<string, unknown>)[m[3]];
    } else if (m[4] !== undefined) {
      cur = (cur as Record<string, unknown>)[m[4]];
    }
    if (cur === undefined) return { found: false };
  }
  if (lastIdx !== suffix.length) return { found: false };
  return { found: true, value: cur };
}
