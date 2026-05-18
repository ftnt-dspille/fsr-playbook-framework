<script lang="ts">
  /**
   * Variable tree pane — flies in to the immediate left of the step
   * inspector when a Jinja-accepting field is focused (or its `{x}`
   * button is clicked). Renders every variable in scope at the active
   * step as an expandable tree with inline `= value` previews from the
   * pinned sample record / typed shapes.
   *
   * Source toggle: "Mock / shape" uses the trigger module's catalog +
   * sample + typed_walker output (today's data). "Real run" is wired
   * for a future plumb of per-run observed values — disabled with a
   * tooltip until the run-vars extraction backlog item lands.
   *
   * Clicking a leaf calls `varPaneStore.insert('{{ path }}')` which
   * delegates to whichever field is the current insert target.
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import type { Shape } from '../shapeStubs';
  import { varPaneStore } from '../varPaneStore.svelte';
  import { runVarsStore } from '../runVarsStore.svelte';
  import { jinjaShapesStore } from '../jinjaShapesStore.svelte';
  import {
    triggerModuleFieldsStore,
    sampleRecordsStore,
    globalVarsStore
  } from '../triggerModuleFields.svelte';
  import { formatFsrValue, truncate } from '../fsrValue';
  import { playbookStore } from '../playbookStore.svelte';

  type Props = {
    node: VisualNode | null;
    playbook: VisualPlaybook | null;
    onClose: () => void;
  };
  let { node, playbook, onClose }: Props = $props();

  type Source = 'mock' | 'run';
  let source = $state<Source>('mock');
  let filter = $state('');

  // Fetch recent runs the first time the user opens the Real-run tab.
  // Filtered by the active playbook's name when available — FSR's
  // recent-runs endpoint accepts a template_iri filter, but we don't
  // have the IRI here, so we just fetch the appliance-wide recent
  // list and let the user pick. (Hooking up template_iri requires
  // wiring deployment metadata through — separate follow-up.)
  $effect(() => {
    if (source !== 'run') return;
    if (runVarsStore.runs.length || runVarsStore.runsLoading) return;
    runVarsStore.loadRuns();
  });

  /** Same scope walker VarPathPicker used — kept here so the pane is
   *  self-contained and doesn't depend on the legacy picker code. */
  function collectAncestors(): VisualNode[] {
    if (!playbook || !node) return [];
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

  function stepKey(name: string): string { return name.replace(/\s+/g, '_'); }

  function shapeLabel(s: Shape | null | undefined): string {
    if (!s) return '';
    switch (s.kind) {
      case 'object': return 'object';
      case 'list': return `list<${shapeLabel(s.item) || 'any'}>`;
      case 'scalar': return s.type ?? 'any';
      case 'none': return 'none';
      case 'unknown': return 'unknown';
    }
  }

  /** Refresh typed shapes + module fields + globals + sample whenever
   *  the active step changes or the pane (re)opens. The pane is cheap
   *  to leave mounted, so we don't gate on `open` — but we do skip
   *  fetches when there is no step. */
  let triggerRecordFields = $state<string[] | null>(null);
  let triggerSample = $state<Record<string, unknown> | null>(null);
  let triggerModule = $state<string | null>(null);
  let globals = $state<Array<{ name: string; value?: unknown }>>([]);

  $effect(() => {
    if (!node || !playbook) return;
    const yaml = playbookStore.yaml;
    if (yaml) jinjaShapesStore.refresh(yaml);
    const trig = playbook.nodes.find((n) => n.family === 'trigger');
    const mod = (trig?.arguments as any)?.module ?? (trig?.arguments as any)?.resource;
    const bare =
      typeof mod === 'string' ? mod.split('?')[0].trim().replace(/^["']|["']$/g, '') : '';
    triggerModule = bare || null;
    if (!bare) {
      triggerRecordFields = null;
      triggerSample = null;
    } else {
      triggerModuleFieldsStore.fieldsFor(bare).then((fs) => {
        triggerRecordFields = fs.length ? fs : null;
      });
      if (sampleRecordsStore.pickedModule === bare && sampleRecordsStore.picked) {
        triggerSample = sampleRecordsStore.picked;
      } else {
        sampleRecordsStore.fetch(bare).then((recs) => {
          triggerSample = sampleRecordsStore.picked ?? recs[0] ?? null;
        });
      }
    }
    globalVarsStore.list().then((gs) => {
      globals = gs ?? [];
    });
  });

  /** Tree node model — `children` is a thunk so deep paths only
   *  materialize when the user expands them. Keeps the render tight
   *  even on playbooks with dozens of typed steps. */
  type TreeNode = {
    key: string;
    label: string;        // displayed segment (e.g. ".severity" or "[0]")
    path: string;         // full insertable path
    hint?: string;        // type / preview
    children?: () => TreeNode[];
    /** Group header (no insert affordance). */
    isGroup?: boolean;
  };

  function expandShapeNodes(shape: Shape, root: string, depth = 3): TreeNode[] {
    if (depth <= 0) return [];
    if (shape.kind === 'object') {
      return Object.entries(shape.keys ?? {}).map(([k, v]) => {
        const safe = /^[A-Za-z_][\w]*$/.test(k);
        const seg = safe ? `.${k}` : `['${k}']`;
        const childPath = root + seg;
        const childHint = shapeLabel(v);
        return {
          key: childPath,
          label: safe ? k : `['${k}']`,
          path: childPath,
          hint: childHint,
          children:
            v.kind === 'object' || v.kind === 'list'
              ? () => expandShapeNodes(v, childPath, depth - 1)
              : undefined
        } as TreeNode;
      });
    }
    if (shape.kind === 'list') {
      const childPath = root + '[0]';
      return [{
        key: childPath,
        label: '[0]',
        path: childPath,
        hint: shapeLabel(shape.item),
        children:
          shape.item.kind === 'object' || shape.item.kind === 'list'
            ? () => expandShapeNodes(shape.item, childPath, depth - 1)
            : undefined
      }];
    }
    return [];
  }

  /** Render the input.records[0] subtree using the trigger module's
   *  catalog. Live sample fields come first with `= value` previews
   *  (validates existence + shows real data); remaining catalog fields
   *  follow. Falls back to the static `@id/name/id` triplet when no
   *  module is known. */
  function inputRecordChildren(): TreeNode[] {
    const root = 'vars.input.records[0]';
    if (!triggerRecordFields || !triggerRecordFields.length) {
      return [
        { key: `${root}.@id`, label: "['@id']", path: `${root}['@id']`, hint: 'IRI' },
        { key: `${root}.name`, label: 'name', path: `${root}.name`, hint: 'string' },
        { key: `${root}.id`, label: 'id', path: `${root}.id`, hint: 'int' }
      ];
    }
    const sample = triggerSample ?? {};
    const sampleKeys = Object.keys(sample);
    const ordered = [
      ...sampleKeys.filter((k) => triggerRecordFields!.includes(k)),
      ...triggerRecordFields.filter((f) => !(f in sample))
    ];
    return ordered.map((f) => {
      const safe = /^[A-Za-z_][\w]*$/.test(f);
      const seg = safe ? `.${f}` : `['${f}']`;
      const inSample = f in sample;
      let hint = inSample ? 'record field' : 'record field (typed)';
      if (inSample) {
        const s = formatFsrValue((sample as any)[f]);
        hint = `= ${truncate(s, 50)}`;
      }
      return {
        key: `${root}${seg}`,
        label: safe ? f : `['${f}']`,
        path: `${root}${seg}`,
        hint
      } as TreeNode;
    });
  }

  let tree = $derived.by<TreeNode[]>(() => {
    if (!node || !playbook) return [];
    const out: TreeNode[] = [];

    // Input group: trigger records + params.
    out.push({
      key: 'g:input',
      label: 'Input',
      path: '',
      isGroup: true,
      children: () => {
        const kids: TreeNode[] = [{
          key: 'vars.input.records',
          label: 'records[0]',
          path: 'vars.input.records[0]',
          hint: triggerModule ? `${triggerModule} record` : 'trigger record',
          children: inputRecordChildren
        }];
        kids.push({
          key: 'vars.input.params',
          label: 'params',
          path: 'vars.input.params',
          hint: 'playbook params (dict)',
          children: () => [{
            key: 'vars.input.params.<name>',
            label: "['<name>']",
            path: "vars.input.params['<name>']",
            hint: 'replace <name>'
          }]
        });
        return kids;
      }
    });

    // globalVars group — env/tenant settings from the FSR catalog.
    out.push({
      key: 'g:globals',
      label: 'globalVars',
      path: '',
      isGroup: true,
      children: () => {
        if (!globals.length) {
          return [{
            key: 'globalVars.<name>',
            label: '<name>',
            path: 'globalVars.<name>',
            hint: 'replace <name>'
          }];
        }
        return globals.map((g) => ({
          key: `globalVars.${g.name}`,
          label: g.name,
          path: `globalVars.${g.name}`,
          hint:
            g.value === undefined || g.value === null
              ? 'env / tenant'
              : `= ${truncate(formatFsrValue(g.value), 40)}`
        }));
      }
    });

    // Top-level set_variable outputs — FSR exposes these as
    // `{{ vars.<name> }}` (NOT vars.steps.<step>.<name>); corpus-
    // verified, see jinja-picker-session-state memory.
    const topLevel = jinjaShapesStore.topLevelVars;
    if (Object.keys(topLevel).length) {
      out.push({
        key: 'g:vars',
        label: 'vars (set_variable)',
        path: '',
        isGroup: true,
        children: () => Object.entries(topLevel).map(([k, sh]) => ({
          key: `vars.${k}`,
          label: k,
          path: `vars.${k}`,
          hint: shapeLabel(sh as Shape),
          children:
            (sh as Shape).kind === 'object' || (sh as Shape).kind === 'list'
              ? () => expandShapeNodes(sh as Shape, `vars.${k}`)
              : undefined
        }))
      });
    }

    // Per-ancestor typed outputs. set_variable steps are surfaced
    // under "vars (set_variable)" above, so we skip them here.
    const ancestors = collectAncestors();
    const liveShapes = jinjaShapesStore.shapes;
    const needsVerifyMap = new Map(
      jinjaShapesStore.needsVerify.map((n) => [n.step, n.reason] as const)
    );
    const stepKids: TreeNode[] = [];
    for (const a of ancestors) {
      if (a.type === 'set_variable') continue;
      const k = stepKey(a.name || a.id);
      const root = `vars.steps.${k}`;
      const shape = liveShapes[k];
      const verifyReason = needsVerifyMap.get(k);
      const baseHint = shape ? shapeLabel(shape) : (verifyReason ? `verify needed: ${verifyReason}` : '');
      stepKids.push({
        key: root,
        label: a.name || a.id,
        path: root,
        hint: baseHint,
        children: shape
          ? () => expandShapeNodes(shape, root)
          : undefined
      });
    }
    if (stepKids.length) {
      out.push({
        key: 'g:steps',
        label: 'Step outputs',
        path: '',
        isGroup: true,
        children: () => stepKids
      });
    }
    return out;
  });

  // Expansion state — keyed by node.key so subtrees survive re-derives.
  // Groups default to open; everything else collapsed.
  let expanded = $state<Record<string, boolean>>({
    'g:input': true,
    'g:globals': true,
    'g:vars': true,
    'g:steps': true
  });
  function toggleExpand(k: string) { expanded[k] = !expanded[k]; }

  /** Filter test — substring match on label or full path. Returns
   *  true if this node OR any descendant matches, so parents stay
   *  visible when a descendant matches. */
  function matches(n: TreeNode, q: string): boolean {
    if (!q) return true;
    const ql = q.toLowerCase();
    if (n.label.toLowerCase().includes(ql)) return true;
    if (n.path && n.path.toLowerCase().includes(ql)) return true;
    if (n.children) {
      for (const c of n.children()) if (matches(c, ql)) return true;
    }
    return false;
  }

  function pick(n: TreeNode) {
    if (n.isGroup || !n.path) return;
    varPaneStore.insert(`{{ ${n.path} }}`);
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="flex h-full w-full flex-col bg-[var(--bg-canvas)]">
  <header class="flex items-center justify-between border-b border-[var(--border-soft)] px-3 py-1.5">
    <div class="flex items-baseline gap-2">
      <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Variables
      </span>
      {#if varPaneStore.target}
        <span class="font-mono text-[10px] text-[var(--text-faint)] truncate" title={varPaneStore.target.label}>
          → {varPaneStore.target.label}
        </span>
      {/if}
    </div>
    <button
      type="button"
      class="rounded px-1 text-[var(--text-faint)] hover:text-[var(--text-default)]"
      onclick={onClose}
      aria-label="Close variable pane"
      title="Close (Esc)"
    >×</button>
  </header>

  <!-- Source toggle. "Mock / shape" uses the trigger module's catalog,
       pinned sample, and typed_walker output. "Real run" pulls per-step
       observed values from a past FSR workflow execution so leaves
       show what the playbook actually produced. -->
  <div class="flex border-b border-[var(--border-soft)] text-[10px]">
    <button
      type="button"
      class="flex-1 px-2 py-1 font-medium transition-colors {source === 'mock'
        ? 'border-b-2 border-[var(--brand)] text-[var(--text-default)]'
        : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
      onclick={() => (source = 'mock')}
    >Mock / shape</button>
    <button
      type="button"
      class="flex-1 px-2 py-1 font-medium transition-colors {source === 'run'
        ? 'border-b-2 border-[var(--brand)] text-[var(--text-default)]'
        : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
      onclick={() => (source = 'run')}
      title="Pick a past FSR run to see real observed values"
    >Real run</button>
  </div>

  {#if source === 'run'}
    <!-- Run picker — populated lazily on first tab open. The detail
         fetch happens on select; rows then show `= value` previews
         from the run's step traces (defensively probing the three
         field names FSR uses across versions). -->
    <div class="border-b border-[var(--border-soft)] p-2 space-y-1">
      {#if runVarsStore.runsLoading}
        <p class="text-[10px] italic text-[var(--text-faint)]">loading recent runs…</p>
      {:else if runVarsStore.runsError}
        <p class="text-[10px] italic text-rose-500">runs error: {runVarsStore.runsError}</p>
      {:else if runVarsStore.runs.length === 0}
        <p class="text-[10px] italic text-[var(--text-faint)]">
          No recent runs found. Run this playbook on FSR first, then refresh.
        </p>
        <button
          type="button"
          class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] hover:bg-[var(--bg-canvas)]"
          onclick={() => runVarsStore.loadRuns()}
        >Refresh</button>
      {:else}
        <label class="block text-[10px] text-[var(--text-muted)]">
          <span class="font-semibold uppercase tracking-wider">Run</span>
          <select
            class="mt-0.5 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
            value={runVarsStore.selectedRunId ?? ''}
            onchange={(e) => {
              const v = (e.currentTarget as HTMLSelectElement).value;
              runVarsStore.selectRun(v ? Number(v) : null);
            }}
          >
            <option value="">— pick a run —</option>
            {#each runVarsStore.runs as r (r.id)}
              <option value={r.id ?? ''}>
                #{r.id} · {r.status ?? '?'} · {r.created?.slice(0, 19) ?? ''}
              </option>
            {/each}
          </select>
        </label>
        {#if runVarsStore.detailLoading}
          <p class="text-[10px] italic text-[var(--text-faint)]">loading run detail…</p>
        {:else if runVarsStore.detailError}
          <p class="text-[10px] italic text-rose-500">{runVarsStore.detailError}</p>
        {/if}
      {/if}
    </div>
  {/if}

  <div class="border-b border-[var(--border-soft)] p-2">
    <input
      type="text"
      bind:value={filter}
      placeholder="filter…"
      class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px]"
    />
  </div>

  <div class="min-h-0 flex-1 overflow-auto">
    {#if !node}
      <p class="px-3 py-2 text-[11px] italic text-[var(--text-faint)]">
        Select a step to see its variable scope.
      </p>
    {:else if !varPaneStore.target}
      <p class="px-3 py-2 text-[11px] italic text-[var(--text-faint)]">
        Click <code class="font-mono">{`{x}`}</code> next to a value field, or focus a Jinja-accepting input, to pick a destination.
      </p>
    {/if}
    <ul class="py-1">
      {#each tree as n (n.key)}
        {#if matches(n, filter)}
          {@render row(n, 0)}
        {/if}
      {/each}
    </ul>
  </div>
</div>

{#snippet row(n: TreeNode, depth: number)}
  {@const hasKids = !!n.children}
  {@const isOpen = !!expanded[n.key] || (!!filter && hasKids)}
  {@const observed = source === 'run' && !n.isGroup && n.path
    ? runVarsStore.observedAt(n.path)
    : { found: false } as const}
  {@const observedHint = observed.found
    ? `= ${truncate(formatFsrValue(observed.value), 50)}`
    : null}
  {@const dim = source === 'run' && !n.isGroup && n.path && !observed.found}
  <li>
    <div
      class="group flex items-baseline gap-1 px-2 py-0.5 text-[11px] hover:bg-[var(--bg-elev)] {dim ? 'opacity-40' : ''}"
      style:padding-left="{depth * 12 + 8}px"
    >
      {#if hasKids}
        <button
          type="button"
          class="w-3 text-[var(--text-faint)] hover:text-[var(--text-default)]"
          aria-label={isOpen ? 'Collapse' : 'Expand'}
          onclick={() => toggleExpand(n.key)}
        >{isOpen ? '▾' : '▸'}</button>
      {:else}
        <span class="w-3"></span>
      {/if}
      {#if n.isGroup}
        <button
          type="button"
          class="flex-1 truncate text-left text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]"
          onclick={() => toggleExpand(n.key)}
        >{n.label}</button>
      {:else}
        <button
          type="button"
          class="flex-1 truncate text-left font-mono text-[var(--text-default)] disabled:cursor-default"
          disabled={!varPaneStore.target}
          title={varPaneStore.target ? `Insert {{ ${n.path} }}` : 'Focus a field first'}
          onclick={() => pick(n)}
        >{n.label}</button>
        {#if observedHint}
          <span class="truncate text-[10px] text-emerald-500">{observedHint}</span>
        {:else if n.hint}
          <span class="truncate text-[10px] text-[var(--text-faint)]">{n.hint}</span>
        {/if}
      {/if}
    </div>
    {#if hasKids && isOpen}
      <ul>
        {#each n.children!() as c (c.key)}
          {#if matches(c, filter)}
            {@render row(c, depth + 1)}
          {/if}
        {/each}
      </ul>
    {/if}
  </li>
{/snippet}
