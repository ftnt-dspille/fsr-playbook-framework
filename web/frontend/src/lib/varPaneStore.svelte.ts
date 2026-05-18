/**
 * State for the variable tree pane that flies in next to the step
 * inspector. Each Jinja-accepting field (set_variable values, decision
 * conditions, args inputs, filter-tree value cells, …) registers an
 * `insert(snippet)` closure here when the user clicks its `{x}` button
 * (Phase 1) or focuses the input (Phase 2). The pane reads `target`
 * to know where to splice the picked path.
 *
 * `focusField` / `blurField` use a short grace window so tabbing
 * between two Jinja fields doesn't flicker the pane shut.
 */
import type { VisualNode } from './api';

export type VarPaneTarget = {
  /** Stable identity — used to no-op blurs after a refocus. */
  id: string;
  /** Short label rendered in the pane header so the user knows which
   *  field they're targeting (e.g. "set_variable severity"). */
  label: string;
  /** Splice a Jinja snippet (already wrapped in `{{ }}` if the caller
   *  wanted wrapping) into the target field. */
  insert: (snippet: string) => void;
};

const BLUR_GRACE_MS = 150;

class VarPaneStore {
  open = $state(false);
  target = $state<VarPaneTarget | null>(null);
  /** Optional: which step the user is inspecting. The pane uses this
   *  to scope ancestor step shapes. Updated by EditWorkspace. */
  node = $state<VisualNode | null>(null);

  #blurTimer: ReturnType<typeof setTimeout> | null = null;

  /** Mark a field as the current insert target and ensure the pane is
   *  open. Cancels any pending blur close. */
  focusField(t: VarPaneTarget) {
    if (this.#blurTimer) {
      clearTimeout(this.#blurTimer);
      this.#blurTimer = null;
    }
    this.target = t;
    this.open = true;
  }

  /** Schedule a close if no other field claims focus within the grace
   *  window. Only closes when the blurred field is still the active
   *  target (avoids racing with a quick refocus that already swapped
   *  targets). */
  blurField(id: string) {
    if (this.#blurTimer) clearTimeout(this.#blurTimer);
    this.#blurTimer = setTimeout(() => {
      this.#blurTimer = null;
      if (this.target?.id === id) {
        this.open = false;
        this.target = null;
      }
    }, BLUR_GRACE_MS);
  }

  /** {x} button click: if this field is already the active target,
   *  toggle the pane closed; otherwise claim focus + open. */
  toggle(t: VarPaneTarget) {
    if (this.open && this.target?.id === t.id) {
      this.open = false;
      this.target = null;
      return;
    }
    this.focusField(t);
  }

  /** User dismissed the pane explicitly (Esc / close button). */
  close() {
    if (this.#blurTimer) {
      clearTimeout(this.#blurTimer);
      this.#blurTimer = null;
    }
    this.open = false;
    this.target = null;
  }

  /** Forward a picked path to the active target. No-op when nothing
   *  is focused — the pane button row is hidden in that state anyway. */
  insert(snippet: string) {
    this.target?.insert(snippet);
  }
}

export const varPaneStore = new VarPaneStore();
