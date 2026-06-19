<script lang="ts">
  /**
   * Thin `{x}` button. Clicking it toggles the global `VarTreePane`
   * (rendered once by EditWorkspace) and registers this field's
   * `onInsert` closure as the active insert target.
   *
   * The popover-style picker this component used to host has been
   * replaced by the pane — see VarTreePane.svelte + varPaneStore.
   * Props kept the same so call sites don't churn (`node` / `playbook`
   * / `shapes` are unused here now but consumed by the pane via
   * varPaneStore.node + the playbook store).
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import type { Shape } from '../shapeStubs';
  import { varPaneStore, type VarPaneTarget } from '../varPaneStore.svelte';

  type Props = {
    node: VisualNode;
    playbook: VisualPlaybook | null;
    /** Wrap the picked path in `{{ … }}`. Decision conditions render
     *  inside braces in some contexts; caller can disable. */
    wrap?: boolean;
    /** Unused now (the pane reads typed shapes from jinjaShapesStore
     *  directly). Kept so existing call sites compile unchanged. */
    shapes?: Record<string, Shape>;
    /** Optional short label shown in the pane header so the user
     *  knows which field will receive the insert. Defaults to the
     *  step name. */
    label?: string;
    /** Receives the (optionally wrapped) Jinja string picked from
     *  the pane. */
    onInsert: (jinja: string) => void;
  };

  let { node, playbook, wrap = true, shapes: _shapes, label, onInsert }: Props = $props();

  // Stable identity for this picker instance — lets the store decide
  // whether a blur event should close the pane or whether a refocus
  // already swapped targets. Cheap; created once per mount.
  const id = `vpp-${Math.random().toString(36).slice(2, 10)}`;

  function target(): VarPaneTarget {
    return {
      id,
      label: label ?? node.name ?? node.id,
      insert: (snippet) => onInsert(wrap ? snippet : snippet.replace(/^\{\{\s*|\s*\}\}$/g, ''))
    };
  }

  function onClick() {
    // Keep the inspector's node in sync so the pane scopes ancestors
    // correctly — clicking the button is a hard signal we want THIS
    // step's scope, even if a focus event hasn't fired.
    varPaneStore.node = node;
    varPaneStore.toggle(target());
  }
</script>

<button
  type="button"
  title="Pick a variable (opens the variable pane)"
  aria-label="Insert variable"
  onclick={onClick}
  class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)] hover:bg-[var(--bg-canvas)] {varPaneStore.open && varPaneStore.target?.id === id ? 'ring-1 ring-[var(--brand)]' : ''}"
>{`{x}`}</button>
