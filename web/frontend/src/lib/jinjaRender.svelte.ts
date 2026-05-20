/**
 * Shared Jinja render helper — used by both the Verify tab and inline
 * preview widgets (the set_variable value rows, etc.).
 *
 * One render context per call. Callers that need many renders against
 * the same context should batch via getJinjaContext() once then
 * renderJinja() per template.
 */
import { callMcpTool, verifyPlaybook } from './api';
import { jinjaShapesStore } from './jinjaShapesStore.svelte';
import { sampleRecordsStore } from './triggerModuleFields.svelte';
import { buildJinjaContext, type Shape } from './shapeStubs';
import { playbookStore } from './playbookStore.svelte';

export type RenderOutcome =
  | { kind: 'literal'; value: string }
  | { kind: 'pending' }
  | { kind: 'rendered'; value: unknown }
  | { kind: 'error'; message: string };

export function isTemplateString(v: unknown): v is string {
  return typeof v === 'string' && v.includes('{{');
}

let cachedContext: Record<string, unknown> | null = null;
let cachedFor = '';

/** Build (and cache, per YAML buffer) the render context used by every
 *  Jinja call from the editor. Combines typed_walker shapes (stubs)
 *  with the user's pinned sample record so previews show real values.
 *  Refresh() the shapes store first if you want the freshest snapshot. */
export async function getJinjaContext(force = false): Promise<Record<string, unknown>> {
  const yaml = playbookStore.currentYaml ?? '';
  if (!force && cachedContext && cachedFor === yaml) return cachedContext;
  try {
    // Use the lighter /api/yaml/shapes path the store already has loaded
    // when available; fall back to verifyPlaybook(verbose) when shapes
    // haven't been populated yet.
    let shapes = jinjaShapesStore.shapes as Record<string, Shape>;
    if (!shapes || Object.keys(shapes).length === 0) {
      const res = await verifyPlaybook(yaml, { verbose: true });
      shapes = (res.evidence?.per_step_jinja_shapes ?? {}) as Record<string, Shape>;
    }
    const ctx = buildJinjaContext(shapes);
    // Layer the user-pinned trigger sample into vars.input.records[0]
    // so previews evaluate against a real record instead of stubs.
    if (sampleRecordsStore.picked) {
      const vars = (ctx as any).vars ?? ((ctx as any).vars = {});
      const input = vars.input ?? (vars.input = {});
      input.records = [sampleRecordsStore.picked, ...(input.records?.slice(1) ?? [])];
    }
    // Layer in known top-level vars (from set_variable) so previews of
    // expressions like `{{ vars.severity | upper }}` resolve.
    const top = jinjaShapesStore.topLevelVars;
    if (top && Object.keys(top).length) {
      const vars = (ctx as any).vars ?? ((ctx as any).vars = {});
      for (const k of Object.keys(top)) {
        if (vars[k] === undefined) vars[k] = '_stub_text_';
      }
    }
    cachedContext = ctx;
    cachedFor = yaml;
    return ctx;
  } catch {
    return {};
  }
}

/** Render a single Jinja template through the live FSR engine.
 *  Returns a `RenderOutcome` — callers bind it to UI state directly. */
export async function renderJinja(template: string): Promise<RenderOutcome> {
  if (!isTemplateString(template)) return { kind: 'literal', value: String(template ?? '') };
  try {
    const ctx = await getJinjaContext();
    const res = await callMcpTool<{ output?: unknown; error?: string }>(
      'render_jinja', { template, context: ctx }
    );
    if (!res.ok || res.result?.error) {
      return { kind: 'error', message: res.error ?? res.result?.error ?? 'render failed' };
    }
    return { kind: 'rendered', value: res.result?.output };
  } catch (e: any) {
    return { kind: 'error', message: e?.message ?? String(e) };
  }
}

/** Invalidate the cached context — call when the YAML buffer or the
 *  pinned sample changes and you want the next render to refetch. */
export function invalidateJinjaContext(): void {
  cachedContext = null;
  cachedFor = '';
}
