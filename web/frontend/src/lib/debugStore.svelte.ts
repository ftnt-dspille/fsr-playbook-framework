/**
 * Shared debug-runner state: breakpoints + watch paths + trigger input.
 *
 * Lives in its own module (not just inside DebugPanel) because:
 *  - PlaybookCanvas needs to read `breakpoints` to render a red dot
 *    on canvas nodes (VISUAL_EDITOR_PLAN 5.4 / 5.5 / 5.7 closeout).
 *  - The trigger payload editor + watch paths persist across panel
 *    re-mounts (drawer collapse/expand) without losing state.
 *
 * Nothing here talks to the server — DebugPanel still owns the actual
 * start/step/continue/stop calls and reads `breakpoints` off this
 * store when assembling the `addBreakpoints` arg.
 */
class DebugStore {
  /** Step ids the runner should pause BEFORE executing. */
  breakpoints = $state<Set<string>>(new Set());

  /** `vars.steps.<jkey>.<...>` paths the watch panel resolves on every tick. */
  watchPaths = $state<string[]>([]);

  /** JSON-shaped trigger payload editor input. Lives here so it survives
   * drawer collapse, and the canvas can show a glance-banner when a
   * playbook is "armed" with a non-default input. */
  triggerInputJson = $state<string>('{}');

  toggleBreakpoint(stepId: string) {
    if (this.breakpoints.has(stepId)) {
      const next = new Set(this.breakpoints);
      next.delete(stepId);
      this.breakpoints = next;
    } else {
      const next = new Set(this.breakpoints);
      next.add(stepId);
      this.breakpoints = next;
    }
  }

  addWatch(path: string) {
    const p = path.trim();
    if (!p || this.watchPaths.includes(p)) return;
    this.watchPaths = [...this.watchPaths, p];
  }

  removeWatch(path: string) {
    this.watchPaths = this.watchPaths.filter((p) => p !== path);
  }

  /** Parse `triggerInputJson` to a payload object. Returns `{}` for
   *  empty / invalid input — callers that need to surface the parse
   *  error can call `parseTriggerInputStrict()` instead. */
  get triggerInput(): Record<string, unknown> {
    try {
      const v = JSON.parse(this.triggerInputJson || '{}');
      return v && typeof v === 'object' && !Array.isArray(v) ? v : {};
    } catch {
      return {};
    }
  }

  parseTriggerInputStrict(): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
    const txt = (this.triggerInputJson || '').trim();
    if (!txt) return { ok: true, value: {} };
    try {
      const v = JSON.parse(txt);
      if (!v || typeof v !== 'object' || Array.isArray(v)) {
        return { ok: false, error: 'trigger input must be a JSON object' };
      }
      return { ok: true, value: v as Record<string, unknown> };
    } catch (e) {
      return { ok: false, error: (e as Error).message };
    }
  }
}

export const debugStore = new DebugStore();

/** Walk a dotted path (e.g. `vars.steps.Foo.input.ip_address`) against
 *  a vars-context tree. Used by the Watch panel and any future
 *  preview. Returns `undefined` when any segment is missing. */
export function resolvePath(root: unknown, path: string): unknown {
  if (!path) return undefined;
  const parts = path.replace(/^vars\./, '').split('.');
  let cur: unknown = root;
  for (const seg of parts) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[seg];
  }
  return cur;
}

/** Build a synthetic `vars` tree from a trace by stitching each step's
 *  output under `steps.<jkey>` — same shape FSR exposes at runtime
 *  (see `debug_session._execute_one_step`). The runner mirrors under
 *  both the step id and `name.replace(' ', '_')`; we mirror here too
 *  so a watch path can use either form. */
export function varsFromTrace(
  trace: Array<{ step_id: string; output: unknown }>,
): { steps: Record<string, unknown> } {
  const steps: Record<string, unknown> = {};
  for (const f of trace) {
    if (f.step_id) steps[f.step_id] = f.output;
    const jkey = f.step_id?.replace(/ /g, '_');
    if (jkey && jkey !== f.step_id) steps[jkey] = f.output;
  }
  return { steps };
}
