<script lang="ts">
  /**
   * Visual Jinja variable picker for the Monaco YAML editor.
   *
   * Unlike VarPathPicker (which is step-scoped and walks a Visual
   * playbook's ancestor edges), this picker is purely data-driven: it
   * lists everything reachable from `jinjaShapesStore` — all known
   * `vars.steps.<key>` shapes with their typed fields — plus the
   * always-available `vars.input.records[0].*` fields (module-aware
   * when the YAML carries a recognizable trigger).
   *
   * Insertion uses `editor.executeEdits` so it lands in Monaco's undo
   * stack (one Ctrl-Z reverts the insert). Caller passes the editor +
   * monaco instances down from MonacoYaml.svelte.
   */
  import { onMount } from 'svelte';
  import { jinjaShapesStore } from '../jinjaShapesStore.svelte';
  import type { Shape } from '../shapeStubs';
  import { shapeLabel, DEFAULT_RECORD_FIELDS } from '../jinjaPathCompletions';
  import {
    extractTriggerModule,
    triggerModuleFieldsStore,
    extractGlobalVarNames,
    globalVarsStore
  } from '../triggerModuleFields.svelte';

  type Props = {
    editor: any;
    monaco: any;
  };
  let { editor, monaco }: Props = $props();

  let open = $state(false);
  let filter = $state('');
  let recordFields = $state<string[]>(DEFAULT_RECORD_FIELDS);
  let globalNames = $state<string[]>([]);

  // When the picker opens, sniff the current YAML for a trigger module
  // and upgrade record-field suggestions to module-aware ones. We don't
  // do this on every keystroke — the picker open is a deliberate user
  // action, perfect moment to spend a fetch.
  $effect(() => {
    if (!open || !editor) return;
    const yaml = editor.getValue?.() ?? '';
    // Always refresh typed shapes from the buffer so the picker shows
    // current step outputs without waiting for the user to click Verify.
    jinjaShapesStore.refresh(yaml);
    // Live FSR catalog first; buffer-scrape fallback if offline.
    globalVarsStore.list().then((live) => {
      if (live.length) {
        globalNames = live.map((g) => g.name).sort();
      } else {
        globalNames = extractGlobalVarNames(yaml);
      }
    });
    const mod = extractTriggerModule(yaml);
    if (!mod) { recordFields = DEFAULT_RECORD_FIELDS; return; }
    triggerModuleFieldsStore.fieldsFor(mod).then((fs) => {
      recordFields = fs.length ? fs : DEFAULT_RECORD_FIELDS;
    });
  });

  type Row = { path: string; group: string; hint: string };

  /** Flatten a Shape into rows under `root` (e.g. `vars.steps.X`).
   *  Depth-2 cap matches VarPathPicker so the popup stays scannable. */
  function expand(shape: Shape, root: string, group: string, depth = 2): Row[] {
    const out: Row[] = [{ path: root, group, hint: shapeLabel(shape) }];
    if (depth <= 0) return out;
    if (shape.kind === 'object') {
      for (const [k, v] of Object.entries(shape.keys ?? {})) {
        const seg = /^[A-Za-z_][\w]*$/.test(k) ? `.${k}` : `['${k}']`;
        out.push({ path: root + seg, group, hint: shapeLabel(v) });
        for (const r of expand(v, root + seg, group, depth - 1).slice(1)) out.push(r);
      }
    } else if (shape.kind === 'list') {
      out.push({ path: root + '[0]', group, hint: shapeLabel(shape.item) });
      for (const r of expand(shape.item, root + '[0]', group, depth - 1).slice(1)) out.push(r);
    }
    return out;
  }

  let rows = $derived.by(() => {
    const out: Row[] = [];
    // 1. Trigger-record fields — always available.
    for (const f of recordFields) {
      const safe = /^[A-Za-z_][\w]*$/.test(f);
      const seg = safe ? `.${f}` : `['${f}']`;
      out.push({
        path: `vars.input.records[0]${seg}`,
        group: 'input',
        hint: 'record field'
      });
    }
    out.push({
      path: "vars.input.params['<name>']",
      group: 'input',
      hint: 'playbook parameter'
    });
    // Buffer-derived globalVars names — show actual names the user
    // already referenced; fall back to the placeholder when none.
    if (globalNames.length) {
      for (const n of globalNames) {
        out.push({
          path: `globalVars.${n}`,
          group: 'globals',
          hint: 'referenced in this playbook'
        });
      }
    } else {
      out.push({
        path: 'globalVars.<name>',
        group: 'globals',
        hint: 'environment / tenant'
      });
    }
    // 2. Top-level vars from set_variable steps. FSR exposes these as
    //    `vars.<name>` directly, NOT under `vars.steps.<step>` (confirmed
    //    against the production corpus: vars.cicd_env, vars.source_control_base_url).
    for (const [k, shape] of Object.entries(jinjaShapesStore.topLevelVars)) {
      out.push({ path: `vars.${k}`, group: 'vars (set_variable)', hint: shapeLabel(shape) });
    }
    // 3. Typed step outputs from the shape store. set_variable steps
    //    don't get a `vars.steps.<step>` entry (their output IS the
    //    top-level vars above; emitting both would mislead authors).
    for (const [k, shape] of Object.entries(jinjaShapesStore.shapes)) {
      // Detect set_variable shapes: object whose keys are exactly the
      // top-level var names — those are surfaced above already.
      const isSetVar = shape.kind === 'object' &&
        Object.keys(shape.keys ?? {}).every((kk) => kk in jinjaShapesStore.topLevelVars);
      if (isSetVar && Object.keys(shape.keys ?? {}).length > 0) continue;
      for (const r of expand(shape, `vars.steps.${k}`, `${k} (typed)`)) out.push(r);
    }
    return out;
  });

  let visible = $derived(
    !filter
      ? rows
      : rows.filter(
          (r) =>
            r.path.toLowerCase().includes(filter.toLowerCase()) ||
            r.group.toLowerCase().includes(filter.toLowerCase())
        )
  );

  /** Insert `{{ path }}` at the cursor through Monaco's edit API so
   *  the insertion is undoable and respects readOnly. */
  function pick(r: Row) {
    if (!editor || !monaco) return;
    const sel = editor.getSelection?.();
    if (!sel) return;
    editor.executeEdits('jinja-picker', [
      { range: sel, text: `{{ ${r.path} }}`, forceMoveMarkers: true }
    ]);
    editor.focus?.();
    open = false;
    filter = '';
  }

  // Close on outside click.
  let popoverEl: HTMLDivElement | undefined;
  onMount(() => {
    function onDocClick(e: MouseEvent) {
      if (!open) return;
      if (popoverEl && !popoverEl.contains(e.target as Node)) {
        open = false;
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  });
</script>

<div class="relative inline-block" bind:this={popoverEl}>
  <button
    type="button"
    title="Insert a Jinja variable path at the cursor"
    aria-label="Insert variable"
    onclick={() => (open = !open)}
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px] text-[var(--text-muted)] shadow hover:bg-[var(--bg-canvas)]"
  >{`{x}`}</button>
  {#if open}
    <div
      role="dialog"
      aria-label="Jinja variable picker"
      class="absolute right-0 z-30 mt-1 max-h-80 w-96 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-lg"
    >
      <input
        type="text"
        bind:value={filter}
        placeholder="filter…"
        onkeydown={(e) => { if (e.key === 'Escape') open = false; }}
        class="sticky top-0 block w-full border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px]"
      />
      {#if visible.length === 0}
        <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">no matches</p>
      {:else}
        <ul>
          {#each visible as r, idx (r.path + idx)}
            <li>
              <button
                type="button"
                onclick={() => pick(r)}
                class="block w-full px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
              >
                <div class="font-mono text-[11px] text-[var(--text-default)]">{r.path}</div>
                <div class="text-[10px] text-[var(--text-faint)]">
                  {r.group} — {r.hint}
                </div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>
