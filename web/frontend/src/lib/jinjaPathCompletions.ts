/**
 * Typed value-path completions for Jinja `{{ ... }}` expressions.
 *
 * Backed by `jinjaShapesStore` (populated by the most recent
 * verify_playbook run). When the cursor is inside an unclosed `{{ }}`
 * and the partial expression starts with `vars.steps.`, we walk the
 * typed_walker Shape for that step along the dotted/bracket path and
 * return the next available keys with type hints.
 *
 * Trigger contexts:
 *   - `vars.steps.`              -> list every step that has a shape.
 *   - `vars.steps.<key>.`        -> object keys at that level.
 *   - `vars.steps.<key>[0].`     -> list-item object keys.
 *   - `vars.steps.<key>.foo.`    -> nested object keys.
 *
 * Not yet handled (Phase 3): `vars.input.records[0].*` (needs trigger
 * module catalog), `globalVars.*` (no static catalog).
 */
import type { Shape } from './shapeStubs';
import { jinjaShapesStore } from './jinjaShapesStore.svelte';

export type PathSuggestion = {
  label: string;
  detail: string;
  insertText: string;
};

export function shapeLabel(s: Shape | null | undefined): string {
  if (!s) return '';
  switch (s.kind) {
    case 'object': return 'object';
    case 'list': return `list<${shapeLabel(s.item) || 'any'}>`;
    case 'scalar': return s.type ?? 'any';
    case 'none': return 'none';
    case 'unknown': return 'unknown';
  }
}

function walkShape(root: Shape, path: Array<string | number>): Shape | null {
  let cur: Shape | null = root;
  for (const seg of path) {
    if (!cur) return null;
    if (typeof seg === 'number') {
      if (cur.kind !== 'list') return null;
      cur = cur.item;
    } else {
      if (cur.kind !== 'object') return null;
      cur = cur.keys?.[seg] ?? null;
    }
  }
  return cur;
}

/** Default field names common to FSR records — used when no
 *  module-aware catalog is supplied for `vars.input.records[0]`.
 *  These are the keys present on (almost) every entity in the
 *  reference store, plus the universal envelope key `@id`. */
export const DEFAULT_RECORD_FIELDS = [
  '@id', 'id', 'uuid', 'name', 'description',
  'status', 'severity', 'owner', 'assignee', 'type',
  'createDate', 'modifyDate', 'tags', 'source'
];

/** Parse segments AFTER `vars.steps.<key>`. Returns the resolved
 *  segments and the trailing partial identifier the user is mid-typing. */
export function parsePathTail(tail: string): {
  segments: Array<string | number>;
  partial: string;
} {
  const m = tail.match(/([A-Za-z_][\w]*)?$/);
  const partial = m?.[1] ?? '';
  const consumed = tail.slice(0, tail.length - partial.length);
  const body = consumed.replace(/\.$/, '');
  const segments: Array<string | number> = [];
  const re = /\.([A-Za-z_][\w]*)|\[(\d+)\]|\['([^']+)'\]|\["([^"]+)"\]/g;
  let mm: RegExpExecArray | null;
  while ((mm = re.exec(body)) !== null) {
    if (mm[1] !== undefined) segments.push(mm[1]);
    else if (mm[2] !== undefined) segments.push(Number(mm[2]));
    else if (mm[3] !== undefined) segments.push(mm[3]);
    else if (mm[4] !== undefined) segments.push(mm[4]);
  }
  return { segments, partial };
}

/** Walk a complete `vars.steps.<key>...` path (no trailing partial)
 *  and return its resolved Shape, or null if the path doesn't exist
 *  in the store. Powers the hover provider. */
export function resolveJinjaPathType(
  fullPath: string,
  shapes: Record<string, Shape> = jinjaShapesStore.shapes
): Shape | null {
  const m = fullPath.match(/^vars\.steps\.([A-Za-z_][\w]*)(.*)$/);
  if (!m) return null;
  const [, stepKey, tail] = m;
  const root = shapes[stepKey];
  if (!root) return null;
  // Treat the entire tail as committed segments — no partial.
  const { segments, partial } = parsePathTail(tail + '.'); // trailing dot commits
  void partial;
  return walkShape(root, segments);
}

function keysOf(shape: Shape): PathSuggestion[] {
  if (shape.kind !== 'object') return [];
  const out: PathSuggestion[] = [];
  for (const [k, v] of Object.entries(shape.keys ?? {})) {
    const safe = /^[A-Za-z_][\w]*$/.test(k);
    out.push({
      label: k,
      detail: shapeLabel(v),
      insertText: safe ? k : `['${k}']`
    });
  }
  return out;
}

export type SuggestOptions = {
  /** Per-step typed Shapes (from jinjaShapesStore). */
  shapes?: Record<string, Shape>;
  /** Field names for `vars.input.records[N]`. Caller supplies module-
   *  aware fields by fetching /api/ref/modules/<m>/fields; we fall
   *  back to DEFAULT_RECORD_FIELDS when omitted. */
  inputRecordFields?: string[];
  /** Known globalVars names — typically derived from a YAML buffer
   *  scan (extractGlobalVarNames). Empty/undefined → no globalVars
   *  suggestions (since we have no static catalog). */
  globalVarNames?: string[];
  /** Top-level vars produced by set_variable steps. Accessed as
   *  `vars.<name>` (real FSR semantics; confirmed against corpus). */
  topLevelVars?: Record<string, Shape>;
};

export function suggestForJinjaPath(
  exprBeforeCursor: string,
  optsOrShapes: SuggestOptions | Record<string, Shape> = {}
): PathSuggestion[] | null {
  // Back-compat: callers used to pass a plain `shapes` map as the 2nd arg.
  // An empty object is treated as "no opts" so the store fallback fires —
  // otherwise the default param value would shadow store-driven calls.
  const isOptions =
    optsOrShapes &&
    ('shapes' in optsOrShapes ||
      'inputRecordFields' in optsOrShapes ||
      'globalVarNames' in optsOrShapes ||
      'topLevelVars' in optsOrShapes ||
      Object.keys(optsOrShapes).length === 0);
  const opts: SuggestOptions = isOptions
    ? (optsOrShapes as SuggestOptions)
    : { shapes: optsOrShapes as Record<string, Shape> };
  const shapes = opts.shapes ?? jinjaShapesStore.shapes;
  const inputFields = opts.inputRecordFields ?? DEFAULT_RECORD_FIELDS;
  const after = exprBeforeCursor.replace(/^\{\{\s*/, '');

  // `globalVars.<partial>` -> buffer-derived globalVars names.
  const globalMatch = after.match(/^globalVars\.([A-Za-z_][\w]*)?$/);
  if (globalMatch) {
    const partial = globalMatch[1] ?? '';
    const names = opts.globalVarNames ?? [];
    if (!names.length) return null;
    return names
      .filter((n) => n.startsWith(partial))
      .map((n) => ({ label: n, detail: 'globalVar', insertText: n }));
  }

  // `vars.input.records[N].<partial>` -> static / module-aware record fields.
  const inputMatch = after.match(/^vars\.input\.records\[\d+\]\.([A-Za-z_][\w]*)?$/);
  if (inputMatch) {
    const partial = inputMatch[1] ?? '';
    return inputFields
      .filter((f) => f.startsWith(partial))
      .map((f) => {
        const safe = /^[A-Za-z_][\w]*$/.test(f);
        return {
          label: f,
          detail: 'record field',
          insertText: safe ? f : `['${f}']`
        };
      });
  }

  // `vars.<setvarname>` — top-level vars from set_variable steps.
  // Match BEFORE the vars.steps check so we don't shadow.
  const topMatch = after.match(/^vars\.([A-Za-z_][\w]*)?$/);
  if (topMatch && !/^vars\.(input|steps)$/.test(after)) {
    const partial = topMatch[1] ?? '';
    const top = opts.topLevelVars ?? {};
    const names = Object.keys(top).filter((n) => n.startsWith(partial));
    if (names.length === 0) return null;
    return names.map((n) => ({ label: n, detail: shapeLabel(top[n]), insertText: n }));
  }

  if (!/^vars\.steps(\.|$)/.test(after)) return null;

  const headOnly = after.match(/^vars\.steps\.([A-Za-z_][\w]*)?$/);
  if (headOnly) {
    const partial = headOnly[1] ?? '';
    const keys = Object.keys(shapes).filter((k) => k.startsWith(partial));
    return keys.map((k) => ({
      label: k,
      detail: shapeLabel(shapes[k]),
      insertText: k
    }));
  }

  const stepMatch = after.match(/^vars\.steps\.([A-Za-z_][\w]*)(.*)$/);
  if (!stepMatch) return null;
  const [, stepKey, tail] = stepMatch;
  const root = shapes[stepKey];
  if (!root) return null;
  const { segments, partial } = parsePathTail(tail);
  const cur = walkShape(root, segments);
  if (!cur || cur.kind !== 'object') return null;
  return keysOf(cur).filter((s) => s.label.startsWith(partial));
}
