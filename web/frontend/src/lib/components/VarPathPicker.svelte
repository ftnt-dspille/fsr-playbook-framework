<script lang="ts">
  /**
   * Jinja var-path picker. Renders a small `{x}` button that opens a
   * popover listing the variables in scope at the current step:
   *
   *  - `vars.input.records[0].*` — the trigger record's fields (uses
   *     the trigger's `resource` module's catalog when available).
   *  - `vars.input.params['<name>']` — playbook input parameters.
   *  - `vars.steps.<Predecessor>.*` — every upstream step's outputs,
   *     keyed by name-with-underscores (FSR's runtime convention).
   *  - `globalVars.*` — environment globals (free-text, no catalog).
   *
   * Click an entry → emit `onInsert(path)` so the parent can splice
   * it into a textarea / input. Wraps the path in `{{ … }}` unless
   * the parent disables wrapping.
   */
  import type { VisualNode, VisualPlaybook } from '../api';

  type Props = {
    node: VisualNode;
    playbook: VisualPlaybook | null;
    /** Wrap the inserted path in `{{ … }}` braces. Decision conditions
     * already render inside braces in some contexts; the caller can
     * disable. */
    wrap?: boolean;
    /** Receives the (optionally wrapped) Jinja string the user picked. */
    onInsert: (jinja: string) => void;
  };

  let { node, playbook, wrap = true, onInsert }: Props = $props();

  let open = $state(false);
  let filter = $state('');

  /** Step name → variable key. FSR converts spaces to underscores in
   * the runtime's `vars.steps.<key>` lookup. Mirror that here. */
  function stepKey(name: string): string {
    return name.replace(/\s+/g, '_');
  }

  /** All steps that flow into `node` directly OR transitively. We
   * walk inbound edges breadth-first; ordering matches the runtime's
   * "what variables can I see right now" question. */
  function collectAncestors(): VisualNode[] {
    if (!playbook) return [];
    const byId = new Map(playbook.nodes.map((n) => [n.id, n]));
    const out: VisualNode[] = [];
    const seen = new Set<string>();
    const stack = playbook.edges
      .filter((e) => e.target === node.id)
      .map((e) => e.source);
    while (stack.length) {
      const id = stack.shift()!;
      if (seen.has(id)) continue;
      seen.add(id);
      const n = byId.get(id);
      if (!n) continue;
      out.push(n);
      for (const e of playbook.edges) {
        if (e.target === id && !seen.has(e.source)) stack.push(e.source);
      }
    }
    return out;
  }

  type Suggestion = { path: string; group: string; hint?: string };

  function suggestionsFor(): Suggestion[] {
    const out: Suggestion[] = [];
    // Common record / params globals — always available; the user
    // doesn't need predecessors for these.
    for (const path of [
      "vars.input.records[0]['@id']",
      'vars.input.records[0].name',
      "vars.input.records[0].id",
      "vars.input.params['<name>']",
      'vars.input.params',
    ]) {
      out.push({ path, group: 'input' });
    }
    out.push({ path: 'globalVars.<name>', group: 'globals',
               hint: 'environment / tenant globals' });

    // Per-ancestor outputs. We don't know each step's actual output
    // shape without running it, so suggest two common access patterns:
    // the bracketed-list form (find_record / connector list ops) and
    // the dotted form (single-record / scalar ops).
    for (const a of collectAncestors()) {
      const k = stepKey(a.name || a.id);
      if (a.type === 'find_record') {
        out.push({ path: `vars.steps.${k}[0]['@id']`, group: a.name,
                   hint: 'first matched record IRI' });
        out.push({ path: `vars.steps.${k}[0]`, group: a.name,
                   hint: 'first matched record' });
      } else if (a.family === 'connector_op') {
        out.push({ path: `vars.steps.${k}.data`, group: a.name,
                   hint: `${a.type} output` });
      } else if (a.family === 'manual_input') {
        out.push({ path: `vars.steps.${k}.input`, group: a.name,
                   hint: 'analyst-supplied form values' });
      } else {
        out.push({ path: `vars.steps.${k}`, group: a.name });
      }
    }
    return out;
  }

  let allSuggestions = $derived(suggestionsFor());
  let visibleSuggestions = $derived(
    !filter ? allSuggestions
            : allSuggestions.filter((s) =>
                s.path.toLowerCase().includes(filter.toLowerCase())
                || s.group.toLowerCase().includes(filter.toLowerCase()))
  );

  function pick(s: Suggestion) {
    onInsert(wrap ? `{{ ${s.path} }}` : s.path);
    open = false;
    filter = '';
  }
</script>

<div class="relative inline-block">
  <button
    type="button"
    title="Insert a Jinja variable path"
    aria-label="Insert variable"
    onclick={() => (open = !open)}
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)] hover:bg-[var(--bg-canvas)]"
  >{`{x}`}</button>
  {#if open}
    <div
      role="dialog"
      aria-label="Variable picker"
      class="absolute right-0 z-30 mt-1 max-h-72 w-80 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-lg"
    >
      <input
        type="text"
        bind:value={filter}
        placeholder="filter…"
        onkeydown={(e) => { if (e.key === 'Escape') open = false; }}
        class="sticky top-0 block w-full border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px]"
      />
      {#if visibleSuggestions.length === 0}
        <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">no matches</p>
      {:else}
        <ul>
          {#each visibleSuggestions as s, idx (s.path + idx)}
            <li>
              <button
                type="button"
                onclick={() => pick(s)}
                class="block w-full px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
              >
                <div class="font-mono text-[11px] text-[var(--text-default)]">{s.path}</div>
                <div class="text-[10px] text-[var(--text-faint)]">
                  {s.group}{s.hint ? ` — ${s.hint}` : ''}
                </div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>
