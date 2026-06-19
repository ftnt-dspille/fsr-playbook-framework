/**
 * Convert typed_walker Shape → JSON stub value for Jinja preview.
 *
 * Shapes come from `verify_playbook` (verbose=true) under
 * `evidence.per_step_jinja_shapes`. The Verify tab uses the stubs as
 * the `context` arg of `render_jinja` so cross-step references like
 * `vars.steps.Get_Org.records[0].name` resolve against a deterministic
 * placeholder instead of erroring out as "undefined variable."
 *
 * Stub conventions match the plan's §"Open questions" note: type-driven
 * sentinels (`"_stub_text_"`, `0`, `false`, `"/api/3/<module>/stub"`).
 */
export type Shape =
  | { kind: 'object'; keys: Record<string, Shape> }
  | { kind: 'list'; item: Shape }
  | { kind: 'scalar'; type?: 'string' | 'integer' | 'boolean' | 'any' }
  | { kind: 'unknown'; reason?: string }
  | { kind: 'none' };

export function shapeToStub(shape: Shape | null | undefined): unknown {
  if (!shape) return null;
  switch (shape.kind) {
    case 'object': {
      const out: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(shape.keys ?? {})) {
        out[k] = shapeToStub(v);
      }
      // Universal keys FSR exposes on every step's vars.steps.<key>
      // envelope. Mirrors typed_walker._UNIVERSAL_OUTPUT_KEYS so the
      // preview doesn't fail on `.status` / `.result` / etc.
      if (!('status' in out)) out.status = 'ok';
      if (!('result' in out)) out.result = '_stub_result_';
      if (!('@id' in out)) out['@id'] = '/api/3/_stub/00000000-0000-0000-0000-000000000000';
      return out;
    }
    case 'list':
      return [shapeToStub(shape.item)];
    case 'scalar': {
      switch (shape.type) {
        case 'integer': return 0;
        case 'boolean': return false;
        case 'string':
        case 'any':
        default: return '_stub_text_';
      }
    }
    case 'unknown':
      // Permissive object so chained attribute access in Jinja doesn't
      // throw — Jinja will return ``Undefined`` only for *missing*
      // keys, but a JSON `null` triggers `'NoneType' has no attribute…`.
      return {};
    case 'none':
      return null;
    default:
      return null;
  }
}

/** Build the full `context` arg for `render_jinja` from a map of
 * jinja-key → Shape (as returned by verify_playbook verbose evidence).
 * Adds an empty `vars.input.params` so steps that read input still
 * resolve to a defined value. */
export function buildJinjaContext(
  jinjaShapes: Record<string, Shape>,
  simulatedInput: Record<string, unknown> = {}
): Record<string, unknown> {
  const steps: Record<string, unknown> = {};
  for (const [jkey, shape] of Object.entries(jinjaShapes ?? {})) {
    steps[jkey] = shapeToStub(shape);
  }
  return {
    vars: {
      steps,
      input: { params: { ...simulatedInput }, records: [{}] }
    }
  };
}
