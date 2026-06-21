/**
 * Single source-of-truth for per-step Jinja output shapes (as computed
 * by typed_walker and exposed by `verify_playbook` verbose=true under
 * `evidence.per_step_jinja_shapes`).
 *
 * `playbookActions.runVerify` writes the latest shapes here; consumers
 * (VarPathPicker, future Monaco completion provider) read from here so
 * they don't each re-run verify_playbook.
 *
 * The store is intentionally tiny — a $state container plus two helpers:
 *   - `setShapes(shapes)` to publish a fresh map (call this after every
 *      verify run; pass `{}` to clear).
 *   - `shapesFor(jinjaKey)` to fetch a single ancestor's Shape, returning
 *     null when the store has no data for that step (e.g. first session,
 *     or verify hasn't been run yet).
 */
import type { Shape } from './shapeStubs';
import { fetchShapes } from './api';

type ShapeMap = Record<string, Shape>;

type NeedsVerify = { step: string; step_id: string; reason: string };

const state: {
  shapes: ShapeMap;
  topLevelVars: ShapeMap;
  needsVerify: NeedsVerify[];
} = $state({ shapes: {}, topLevelVars: {}, needsVerify: [] });

let lastYaml = '';
let inflight: Promise<void> | null = null;

export const jinjaShapesStore = {
  /** Reactive read; downstream components access via `$derived` /
   *  `$effect` to re-render when shapes change. */
  get shapes(): ShapeMap {
    return state.shapes;
  },

  /** Top-level vars created by set_variable steps — accessed via
   *  `vars.<name>` (NOT `vars.steps.<step>.<name>`). */
  get topLevelVars(): ShapeMap {
    return state.topLevelVars;
  },

  /** Steps whose shape couldn't be inferred (typed_walker returned
   *  `{kind: unknown, reason: ...}`). The picker uses this to surface
   *  a "Verify <step>" prompt instead of silently hiding fields. */
  get needsVerify(): NeedsVerify[] {
    return state.needsVerify;
  },

  /** Publish a fresh shape map. Pass `{}` to clear (e.g. on new
   *  playbook load). */
  setShapes(next: ShapeMap): void {
    state.shapes = next ?? {};
  },

  /** Look up one step's shape. Returns null if the store has no entry
   *  — callers should fall back to step-family heuristics. */
  shapesFor(jinjaKey: string): Shape | null {
    return state.shapes[jinjaKey] ?? null;
  },

  /** Refresh from the live YAML buffer via /api/yaml/shapes (typed
   *  walker, no live probe). Deduped — calling twice with the same
   *  text is a no-op. Safe to call from picker-open handlers. */
  async refresh(yamlText: string): Promise<void> {
    if (!yamlText || yamlText === lastYaml) return;
    if (inflight) return inflight;
    lastYaml = yamlText;
    inflight = (async () => {
      try {
        const r = await fetchShapes(yamlText);
        if (r.ok) {
          state.shapes = (r.shapes as ShapeMap) ?? {};
          state.topLevelVars = (r.top_level_vars as ShapeMap) ?? {};
          state.needsVerify = r.needs_verify ?? [];
        }
      } finally {
        inflight = null;
      }
    })();
    return inflight;
  },

  /** Test-only: reset the dedupe state so a re-mount starts clean. */
  _reset(): void {
    lastYaml = '';
    inflight = null;
    state.shapes = {};
    state.topLevelVars = {};
    state.needsVerify = [];
  }
};
