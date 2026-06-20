<script lang="ts">
  /**
   * Floating Jinja toolbar — filter palette, snippets, and example
   * templates for any Monaco editor that hosts Jinja-bearing text
   * (YAML playbook buffer, set_variable rows, code_snippet bodies).
   *
   * Three panes, switched via a tab strip:
   *   - Filters  — searchable list grouped by category, click inserts
   *                `| name(…)` at the cursor with parameter snippet stops.
   *   - Snippets — `if`, `for`, `macro`, etc. Click inserts.
   *   - Templates— full template + input pair examples; click pastes the
   *                template into the editor. The caller may pass
   *                `onLoadTemplate` to receive (template, input) so it
   *                can also seed an input pane.
   *
   * The panel can be moved by dragging its header bar.
   *
   * Inserts go through `editor.executeEdits` so they land in Monaco's
   * undo stack (one Ctrl-Z reverts each insertion).
   */
  import { filterSignatures, filterCategoryOrder, type FilterSignature } from '$lib/jinja/jinjaFilters';
  import { snippets, type JinjaSnippet } from '$lib/jinja/jinjaSnippets';
  import { templateExamples, type JinjaTemplateExample } from '$lib/jinja/jinjaTemplates';

  type Props = {
    editor: any;
    monaco: any;
    /** Optional callback invoked when the user picks a template. The
     *  caller decides what to do with the example input JSON — e.g.
     *  seed a side preview pane, store it in jinjaShapesStore, etc. */
    onLoadTemplate?: (tpl: JinjaTemplateExample) => void;
  };
  let { editor, monaco, onLoadTemplate }: Props = $props();

  type Tab = 'filters' | 'snippets' | 'templates';
  let tab = $state<Tab>('filters');
  let open = $state(false);
  let query = $state('');

  // Drag state.
  let panel: HTMLDivElement | undefined = $state();
  let triggerBtn: HTMLButtonElement | undefined = $state();
  let pos = $state<{ x: number; y: number } | null>(null);
  let dragging = false;
  let dragOffset = { x: 0, y: 0 };

  const PANEL_W = 460;
  const PANEL_H_MAX = 520;

  // Anchor the panel near the trigger button on open. Drops downward
  // when there's room below, otherwise rises upward. Right-aligned to
  // the button so it doesn't push off the viewport's right edge.
  function anchorToTrigger() {
    if (!triggerBtn) return;
    const r = triggerBtn.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const spaceBelow = vh - r.bottom;
    const dropDown = spaceBelow >= 300;
    const x = Math.max(8, Math.min(vw - PANEL_W - 8, r.right - PANEL_W));
    const y = dropDown
      ? Math.min(vh - PANEL_H_MAX - 8, r.bottom + 6)
      : Math.max(8, r.top - PANEL_H_MAX - 6);
    pos = { x, y: Math.max(8, y) };
  }

  function toggleOpen() {
    open = !open;
    if (open) {
      // Defer to next frame so triggerBtn's rect reflects layout.
      requestAnimationFrame(anchorToTrigger);
    }
  }

  function onDragStart(e: PointerEvent) {
    if (!panel) return;
    dragging = true;
    const rect = panel.getBoundingClientRect();
    dragOffset.x = e.clientX - rect.left;
    dragOffset.y = e.clientY - rect.top;
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    window.addEventListener('pointermove', onDragMove);
    window.addEventListener('pointerup', onDragEnd, { once: true });
  }
  function onDragMove(e: PointerEvent) {
    if (!dragging) return;
    pos = { x: e.clientX - dragOffset.x, y: e.clientY - dragOffset.y };
  }
  function onDragEnd() {
    dragging = false;
    window.removeEventListener('pointermove', onDragMove);
  }

  // ── grouping for the filter pane ──────────────────────────────────
  const grouped = (() => {
    const buckets: Record<string, Array<[string, FilterSignature]>> = {};
    for (const [key, sig] of Object.entries(filterSignatures)) {
      const cat = filterCategoryOrder.includes(sig.category) ? sig.category : 'Other';
      (buckets[cat] = buckets[cat] ?? []).push([key, sig]);
    }
    for (const cat of Object.keys(buckets)) buckets[cat].sort(([a], [b]) => a.localeCompare(b));
    return buckets;
  })();

  function filteredEntries(): Array<[string, Array<[string, FilterSignature]>]> {
    const q = query.trim().toLowerCase();
    const out: Array<[string, Array<[string, FilterSignature]>]> = [];
    for (const cat of filterCategoryOrder) {
      const items = (grouped[cat] ?? []).filter(([k, sig]) =>
        !q || k.toLowerCase().includes(q) || sig.documentation.toLowerCase().includes(q)
      );
      if (items.length) out.push([cat, items]);
    }
    return out;
  }

  function filteredSnippets(): JinjaSnippet[] {
    const q = query.trim().toLowerCase();
    if (!q) return snippets;
    return snippets.filter((s) => s.label.toLowerCase().includes(q) || s.detail.toLowerCase().includes(q));
  }

  // ── insertion helpers ─────────────────────────────────────────────

  function insertText(text: string) {
    if (!editor || !monaco) return;
    const sel = editor.getSelection();
    editor.executeEdits('jinja-toolbar', [
      {
        range: new monaco.Range(
          sel.startLineNumber, sel.startColumn,
          sel.endLineNumber, sel.endColumn
        ),
        text,
        forceMoveMarkers: true
      }
    ]);
    editor.focus();
  }

  function insertSnippet(text: string) {
    if (!editor) return;
    const contrib = editor.getContribution('snippetController2');
    if (contrib && typeof contrib.insert === 'function') {
      editor.focus();
      contrib.insert(text);
    } else {
      insertText(text);
    }
  }

  function insertFilter(key: string, sig: FilterSignature) {
    // If the user is inside `{{ … }}` / `{% … %}` already, we just
    // append `| key(…)`. Otherwise we wrap the current selection in
    // `{{ ... | key(…) }}` so the toolbar still works from a fresh
    // cursor. We can't reliably detect Jinja state without re-running
    // the tokenizer; cheap heuristic: peek at the line up to the cursor.
    const model = editor.getModel();
    const pos2 = editor.getPosition();
    const line: string = model.getLineContent(pos2.lineNumber);
    const before = line.substring(0, pos2.column - 1);
    const lastOpen = Math.max(before.lastIndexOf('{{'), before.lastIndexOf('{%'));
    const lastClose = Math.max(before.lastIndexOf('}}'), before.lastIndexOf('%}'));
    const inJinja = lastOpen > lastClose;

    const params = sig.parameters.map((p, i) => {
      const placeholder = p.type === 'string' ? `'${p.name}'` : p.name;
      return `\${${i + 1}:${placeholder}}`;
    });
    const argString = params.length ? `(${params.join(', ')})` : '';
    const snippetBody = `| ${key}${argString}`;

    if (inJinja) {
      insertSnippet(' ' + snippetBody + ' $0');
    } else {
      insertSnippet(`{{ \${1:value} ${snippetBody} }}\$0`);
    }
  }

  /** Replace the editor buffer with this filter's example template —
   *  mirrors the widget's `insertFilterExample`. */
  function tryFilterExample(sig: FilterSignature) {
    if (!editor) return;
    editor.setValue(sig.example);
    editor.focus();
  }

  function pickTemplate(t: JinjaTemplateExample) {
    if (onLoadTemplate) {
      onLoadTemplate(t);
      return;
    }
    // Default: replace the editor buffer with the template body.
    editor.setValue(t.template);
    editor.focus();
  }
</script>

<div class="relative">
  <button
    bind:this={triggerBtn}
    type="button"
    class="whitespace-nowrap rounded border px-2 py-0.5 text-[11px] font-medium leading-none shadow-sm"
    style="background: var(--bg-panel, #0c0c0f); border-color: var(--border-soft, #1d1d22); color: var(--text-default, #e4e4e7); height: 24px;"
    onclick={toggleOpen}
    title="Jinja toolbar — filters, snippets, templates"
  >
    {open ? '✕' : 'ƒ'} Jinja
  </button>

  {#if open}
    <div
      bind:this={panel}
      class="flex flex-col rounded-md border shadow-2xl"
      style="position: fixed; left: {pos?.x ?? 16}px; top: {pos?.y ?? 64}px; width: {PANEL_W}px; height: {PANEL_H_MAX}px; max-height: calc(100vh - 16px); z-index: 1100; background: var(--bg-panel, #0c0c0f); border-color: var(--border-soft, #1d1d22); color: var(--text-default, #e4e4e7);"
    >
      <!-- drag handle / header -->
      <div
        role="toolbar"
        aria-label="Drag to move"
        tabindex="-1"
        class="flex cursor-move items-center justify-between rounded-t-md border-b border-[var(--border-soft)] bg-[var(--bg-elevated)] px-3 py-2 select-none"
        onpointerdown={onDragStart}
      >
        <span class="text-[12px] font-semibold text-[var(--text-default)]">Jinja toolbar</span>
        <button type="button" class="text-[14px] text-[var(--text-muted)] hover:text-[var(--text-default)]" onclick={() => (open = false)}>✕</button>
      </div>

      <!-- tabs -->
      <div class="flex border-b border-[var(--border-soft)] text-[12px]">
        {#each ['filters', 'snippets', 'templates'] as t}
          <button
            type="button"
            class="flex-1 px-3 py-1.5 {tab === t ? 'bg-[var(--bg-elevated)] font-semibold text-[var(--text-default)]' : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
            onclick={() => (tab = t as Tab)}
          >{t}</button>
        {/each}
      </div>

      {#if tab !== 'templates'}
        <div class="border-b border-[var(--border-soft)] px-3 py-1.5">
          <input
            class="w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-[12px] text-[var(--text-default)] focus:outline-none focus:ring-1 focus:ring-[var(--brand-ring)]"
            placeholder="Search…"
            bind:value={query}
          />
        </div>
      {/if}

      <div class="overflow-auto px-2 py-2 text-[12px] text-[var(--text-default)]" style:flex="1 1 0">
        {#if tab === 'filters'}
          {#each filteredEntries() as [cat, items]}
            <div class="mb-2">
              <div class="px-1 pb-1 text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{cat}</div>
              <ul>
                {#each items as [key, sig]}
                  <li class="group relative">
                    <button
                      type="button"
                      class="flex w-full flex-col gap-0.5 rounded px-2 py-1 pr-12 text-left hover:bg-[var(--bg-elevated)]"
                      title={sig.documentation}
                      onclick={() => insertFilter(key, sig)}
                    >
                      <span class="font-mono text-[12px]"
                        ><span class="text-[var(--brand)]">| {key}</span>
                        {#if sig.parameters.length}<span class="text-[var(--text-muted)]">(
                          {#each sig.parameters as p, i}{i ? ', ' : ''}{p.name}{/each})</span>{/if}
                        <span class="text-[var(--text-faint)]"> → {sig.returnValue.type}</span>
                      </span>
                      <span class="text-[11px] text-[var(--text-muted)]">{sig.documentation}</span>
                      {#if sig.example}
                        <span class="mt-0.5 font-mono text-[10px] text-[var(--text-faint)] line-clamp-1">{sig.example}</span>
                      {/if}
                    </button>
                    {#if sig.example}
                      <button
                        type="button"
                        class="absolute right-1 top-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1.5 py-0.5 text-[10px] text-[var(--text-default)] opacity-0 hover:bg-[var(--bg-elevated)] group-hover:opacity-100"
                        title="Replace the template with this example"
                        onclick={(ev) => { ev.stopPropagation(); tryFilterExample(sig); }}
                      >→ try</button>
                    {/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/each}
          {#if !filteredEntries().length}
            <div class="px-2 py-3 text-[var(--text-muted)]">No filters match “{query}”.</div>
          {/if}
        {:else if tab === 'snippets'}
          <ul>
            {#each filteredSnippets() as s}
              <li>
                <button
                  type="button"
                  class="flex w-full flex-col gap-0.5 rounded px-2 py-1 text-left hover:bg-[var(--bg-elevated)]"
                  title={s.detail}
                  onclick={() => insertSnippet(s.insertText)}
                >
                  <span class="font-mono text-[12px] text-[var(--brand)]">{s.label}</span>
                  <span class="text-[11px] text-[var(--text-muted)]">{s.detail}</span>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <ul>
            {#each templateExamples as t}
              <li>
                <button
                  type="button"
                  class="flex w-full flex-col gap-0.5 rounded px-2 py-1 text-left hover:bg-[var(--bg-elevated)]"
                  onclick={() => pickTemplate(t)}
                >
                  <span class="text-[12px] font-semibold text-[var(--text-default)]">{t.label}</span>
                  <span class="text-[11px] text-[var(--text-muted)]">{t.description}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  {/if}
</div>
