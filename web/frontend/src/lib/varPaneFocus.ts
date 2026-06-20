/**
 * Helper that wires any Jinja-accepting input to the variable tree
 * pane via its focus/blur events. Each call produces a one-shot
 * `{ id, onfocus, onblur }` triple — drop the events onto the input
 * and the pane will claim/release this field as its insert target
 * automatically.
 *
 * Why a helper instead of inlining the store calls everywhere: we
 * need a stable per-binding `id` so the store's blur grace window
 * can tell "this field is gone" from "the user just tabbed to the
 * next Jinja field, keep the pane open".
 *
 * For HTML inputs:
 *   const handlers = attachVarPaneFocus({ insert, label });
 *   <input onfocus={handlers.onfocus} onblur={handlers.onblur} />
 *
 * For MonacoCode (whose editor instance isn't a DOM input), use the
 * editor's own onDidFocusEditorText / onDidBlurEditorText listeners
 * with the same `{ id, label, insert }` payload.
 */
import { varPaneStore, type VarPaneTarget } from './varPaneStore.svelte';

export type AttachOptions = {
  /** Where the picked Jinja snippet should land. Called with the
   *  wrapped `{{ … }}` form (or unwrapped when `wrap === false`). */
  insert: (snippet: string) => void;
  /** Short label shown in the pane header so the user knows which
   *  field is being targeted. Defaults to "(field)". */
  label?: string;
  /** Default true — strip the `{{ }}` wrapper before handing the
   *  snippet to `insert` when set to false. Matches VarPathPicker's
   *  `wrap` prop semantics. */
  wrap?: boolean;
};

export function attachVarPaneFocus(opts: AttachOptions) {
  const id = `vpf-${Math.random().toString(36).slice(2, 10)}`;
  const wrap = opts.wrap !== false;
  const target: VarPaneTarget = {
    id,
    label: opts.label ?? '(field)',
    insert: (snippet) => opts.insert(wrap ? snippet : snippet.replace(/^\{\{\s*|\s*\}\}$/g, ''))
  };
  return {
    id,
    target,
    onfocus: () => varPaneStore.focusField(target),
    onblur: () => varPaneStore.blurField(id)
  };
}
