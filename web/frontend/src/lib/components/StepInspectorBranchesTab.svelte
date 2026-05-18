<script lang="ts">
  /**
   * Branch editor for decision / manual_input nodes.
   *
   * Each row binds an outgoing `branch_kind: 'branch'` edge to its
   * matching entry in the node's `arguments.conditions[]` (decision)
   * or `arguments.options[]` (manual_input). Edges and the conditions
   * array are kept in lockstep — renaming a label, retargeting, adding
   * or deleting a branch updates both sides so the emitted YAML is
   * coherent.
   *
   * Decision rows additionally expose:
   *  - `condition` — the Jinja predicate that gates the branch.
   *  - `default` — the else/default flag (FSR's designer renders a
   *     broken else edge unless exactly one row has default: true).
   *
   * Manual_input rows expose `formType` so users can pick string /
   * picklist / ipv4 / lookup etc. without dropping into Raw.
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import { visualStore } from '../visualEditStore.svelte';
  import VarPathPicker from './VarPathPicker.svelte';
  import { attachVarPaneFocus } from '../varPaneFocus';
  import { jinjaShapesStore } from '../jinjaShapesStore.svelte';

  type Props = { node: VisualNode; playbook: VisualPlaybook; playbookIdx: number };
  let { node, playbook, playbookIdx }: Props = $props();

  const isDecision = $derived(node.type === 'decision');
  const isManualInput = $derived(node.type === 'manual_input');

  let branches = $derived(
    playbook.edges.filter((e) => e.source === node.id && e.branch_kind === 'branch')
  );
  let allTargets = $derived(playbook.nodes.filter((n) => n.id !== node.id));

  type CondEntry = {
    option?: string | null;
    condition?: string;
    default?: boolean;
    step_iri?: string;
    step_name?: string;
  } & Record<string, unknown>;
  type OptEntry = {
    option?: string | null;
    formType?: string;
    type?: string;
    step_iri?: string;
    step_name?: string;
  } & Record<string, unknown>;

  /** Pull the matching entry from the node's arguments by label. We
   * match on the canonical `option` key the parser writes (display →
   * option), falling back to the legacy `display`. */
  function findEntry<T extends { option?: string | null }>(
    list: T[] | undefined,
    label: string | null
  ): { entry: T; index: number } | null {
    if (!Array.isArray(list)) return null;
    const idx = list.findIndex((x) => (x.option ?? (x as Record<string, unknown>).display ?? null) === label);
    if (idx < 0) return null;
    return { entry: list[idx], index: idx };
  }

  function getConditions(): CondEntry[] {
    const c = node.arguments?.conditions;
    return Array.isArray(c) ? (c as CondEntry[]) : [];
  }
  function getOptions(): OptEntry[] {
    const o = node.arguments?.options;
    return Array.isArray(o) ? (o as OptEntry[]) : [];
  }

  function writeArgs(next: Record<string, unknown>) {
    visualStore.setArgs(playbookIdx, node.id, { ...node.arguments, ...next });
  }

  function rename(oldLabel: string | null, e: Event) {
    const v = (e.currentTarget as HTMLInputElement).value;
    visualStore.renameBranchLabel(playbookIdx, node.id, oldLabel, v);
    // Mirror the rename into conditions[].option / options[].option so
    // the emitter doesn't drop the row on next save.
    if (isDecision) {
      const conds = getConditions().slice();
      const m = findEntry(conds, oldLabel);
      if (m) {
        conds[m.index] = { ...m.entry, option: v || null };
        writeArgs({ conditions: conds });
      }
    } else if (isManualInput) {
      const opts = getOptions().slice();
      const m = findEntry(opts, oldLabel);
      if (m) {
        opts[m.index] = { ...m.entry, option: v || null };
        writeArgs({ options: opts });
      }
    }
  }

  function retarget(label: string | null, oldTarget: string, e: Event) {
    const v = (e.currentTarget as HTMLSelectElement).value;
    visualStore.retargetEdge(
      playbookIdx,
      { source: node.id, target: oldTarget, label },
      v
    );
    // Conditions/options entries also carry the target via step_name.
    // Update so the emitted YAML's `next:` matches the canvas edge.
    const targetNode = playbook.nodes.find((n) => n.id === v);
    const newName = targetNode?.name ?? v;
    if (isDecision) {
      const conds = getConditions().slice();
      const m = findEntry(conds, label);
      if (m) {
        conds[m.index] = { ...m.entry, step_name: newName };
        writeArgs({ conditions: conds });
      }
    } else if (isManualInput) {
      const opts = getOptions().slice();
      const m = findEntry(opts, label);
      if (m) {
        opts[m.index] = { ...m.entry, step_name: newName };
        writeArgs({ options: opts });
      }
    }
  }

  function remove(label: string | null, target: string) {
    if (!confirm(`Delete branch '${label ?? '(default)'}'?`)) return;
    visualStore.removeEdge(playbookIdx, { source: node.id, target, label });
    if (isDecision) {
      const conds = getConditions().filter(
        (c) => (c.option ?? (c as Record<string, unknown>).display ?? null) !== label
      );
      writeArgs({ conditions: conds });
    } else if (isManualInput) {
      const opts = getOptions().filter(
        (o) => (o.option ?? (o as Record<string, unknown>).display ?? null) !== label
      );
      writeArgs({ options: opts });
    }
  }

  function setCondition(label: string | null, e: Event) {
    const v = (e.currentTarget as HTMLInputElement).value;
    const conds = getConditions().slice();
    const m = findEntry(conds, label);
    if (m) {
      conds[m.index] = { ...m.entry, condition: v };
    } else {
      // Synthesize an entry for legacy decisions where the conditions
      // array is missing some labels (e.g. came from a hand-edited YAML).
      conds.push({ option: label, condition: v });
    }
    writeArgs({ conditions: conds });
  }

  function setDefault(label: string | null, e: Event) {
    const checked = (e.currentTarget as HTMLInputElement).checked;
    const conds = getConditions().slice();
    if (checked) {
      // FSR allows only one default — clear the flag on every other row
      // first so the user doesn't end up with two else branches that
      // race in the designer.
      for (let i = 0; i < conds.length; i++) {
        if (conds[i].default) conds[i] = { ...conds[i], default: false };
      }
    }
    const m = findEntry(conds, label);
    if (m) {
      const next = { ...m.entry, default: checked };
      // When marked default, FSR ignores the predicate. Drop it so the
      // YAML stays clean and matches the designer's expectations.
      if (checked) delete next.condition;
      conds[m.index] = next;
    } else if (checked) {
      conds.push({ option: label, default: true });
    }
    writeArgs({ conditions: conds });
  }

  function setFormType(label: string | null, e: Event) {
    const v = (e.currentTarget as HTMLSelectElement).value;
    const opts = getOptions().slice();
    const m = findEntry(opts, label);
    if (m) {
      opts[m.index] = { ...m.entry, formType: v || undefined };
    } else {
      opts.push({ option: label, formType: v || undefined });
    }
    writeArgs({ options: opts });
  }

  // Per-edge lookups so the row can read the bound entry without
  // re-scanning on every render.
  function condFor(label: string | null): CondEntry | null {
    return findEntry(getConditions(), label)?.entry ?? null;
  }
  function optFor(label: string | null): OptEntry | null {
    return findEntry(getOptions(), label)?.entry ?? null;
  }

  let newLabel = $state('');
  let newTarget = $state('');
  let newCondition = $state('');
  let newDefault = $state(false);
  let newFormType = $state('');

  function addBranch() {
    const lbl = newLabel.trim();
    const tgt = newTarget;
    if (!lbl || !tgt) return;
    const dup = playbook.edges.find(
      (e) => e.source === node.id && e.branch_kind === 'branch' && (e.label ?? '') === lbl
    );
    if (dup) return;
    visualStore.addEdge(playbookIdx, {
      source: node.id,
      target: tgt,
      label: lbl,
      branch_kind: 'branch'
    });
    const targetNode = playbook.nodes.find((n) => n.id === tgt);
    if (isDecision) {
      const conds = getConditions().slice();
      let entry: CondEntry = { option: lbl, step_name: targetNode?.name ?? tgt };
      if (newDefault) {
        // Clear any other default first.
        for (let i = 0; i < conds.length; i++) {
          if (conds[i].default) conds[i] = { ...conds[i], default: false };
        }
        entry.default = true;
      } else if (newCondition.trim()) {
        entry.condition = newCondition.trim();
      }
      conds.push(entry);
      writeArgs({ conditions: conds });
    } else if (isManualInput) {
      const opts = getOptions().slice();
      const entry: OptEntry = { option: lbl, step_name: targetNode?.name ?? tgt };
      if (newFormType) entry.formType = newFormType;
      opts.push(entry);
      writeArgs({ options: opts });
    }
    newLabel = '';
    newTarget = '';
    newCondition = '';
    newDefault = false;
    newFormType = '';
  }

  // Common manual_input formTypes observed in the live FSR corpus
  // (190 ManualInput steps, 14 distinct formTypes). Free-form fallback
  // available via the "(custom)" entry — the user can drop into Raw if
  // they need something exotic.
  const FORM_TYPES = [
    '', 'string', 'text', 'number', 'integer', 'boolean', 'datetime',
    'picklist', 'lookup', 'ipv4', 'ipv6', 'email', 'url', 'domain', 'json'
  ];
</script>

{#if branches.length === 0}
  <p class="text-xs italic text-[var(--text-faint)]">No branches yet. Use the form below to add one, or drag from this node on the canvas.</p>
{:else}
  <ul class="space-y-2">
    {#each branches as br (br.label + '|' + br.target)}
      {@const cond = isDecision ? condFor(br.label) : null}
      {@const opt = isManualInput ? optFor(br.label) : null}
      <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
        <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Label</div>
        <input
          type="text"
          value={br.label ?? ''}
          placeholder={br.label === null ? '(default)' : ''}
          oninput={(e) => rename(br.label, e)}
          class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
        />
        <div class="mt-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Target</div>
        <select
          aria-label="Branch target"
          value={br.target}
          onchange={(e) => retarget(br.label, br.target, e)}
          class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
        >
          {#each allTargets as t (t.id)}
            <option value={t.id}>{t.name} ({t.id})</option>
          {/each}
        </select>

        {#if isDecision}
          <div class="mt-2 mb-1 flex items-center justify-between">
            <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Condition</span>
            <div class="flex items-center gap-2">
              {#if !cond?.default}
                <VarPathPicker
                  {node}
                  {playbook}
                  shapes={jinjaShapesStore.shapes}
                  wrap={true}
                  onInsert={(snippet) => {
                    // Append the picked path to the existing condition
                    // text — keeps any prose/operators the user already
                    // typed. The compiler is forgiving about whitespace
                    // around `{{ }}` boundaries.
                    const cur = (cond?.condition as string | undefined) ?? '';
                    const next = cur ? `${cur} ${snippet}` : snippet;
                    const conds = getConditions().slice();
                    const m = findEntry(conds, br.label);
                    if (m) conds[m.index] = { ...m.entry, condition: next };
                    else conds.push({ option: br.label, condition: next });
                    writeArgs({ conditions: conds });
                  }}
                />
              {/if}
              <label class="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
                <input
                  type="checkbox"
                  checked={!!cond?.default}
                  onchange={(e) => setDefault(br.label, e)}
                />
                <span>Default (else)</span>
              </label>
            </div>
          </div>
          {@const condFocus = attachVarPaneFocus({
            label: `${node.name || 'decision'} · ${br.label}`,
            insert: (snippet) => {
              const cur = (cond?.condition as string | undefined) ?? '';
              const next = cur ? `${cur} ${snippet}` : snippet;
              const conds = getConditions().slice();
              const m = findEntry(conds, br.label);
              if (m) conds[m.index] = { ...m.entry, condition: next };
              else conds.push({ option: br.label, condition: next });
              writeArgs({ conditions: conds });
            }
          })}
          <input
            type="text"
            value={(cond?.condition as string | undefined) ?? ''}
            placeholder={cond?.default ? '(default branch — predicate ignored)' : '{{ vars.score > 50 }}' /* literal Jinja */}
            disabled={!!cond?.default}
            oninput={(e) => setCondition(br.label, e)}
            onfocus={cond?.default ? undefined : condFocus.onfocus}
            onblur={cond?.default ? undefined : condFocus.onblur}
            class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px] disabled:opacity-50"
          />
        {/if}

        {#if isManualInput}
          <div class="mt-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Form type</div>
          <select
            aria-label="Form type"
            value={(opt?.formType as string | undefined) ?? (opt?.type as string | undefined) ?? ''}
            onchange={(e) => setFormType(br.label, e)}
            class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
          >
            {#each FORM_TYPES as ft}
              <option value={ft}>{ft || '— none —'}</option>
            {/each}
          </select>
        {/if}

        <button
          type="button"
          class="mt-2 text-[10px] text-red-600 underline hover:text-red-700"
          onclick={() => remove(br.label, br.target)}
        >Delete branch</button>
      </li>
    {/each}
  </ul>
{/if}

<section class="mt-3 rounded border border-dashed border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Add branch</div>
  <input
    type="text"
    placeholder="label (e.g. matched)"
    bind:value={newLabel}
    class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
  />
  <select
    aria-label="New branch target"
    bind:value={newTarget}
    class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
  >
    <option value="">— pick target —</option>
    {#each allTargets as t (t.id)}
      <option value={t.id}>{t.name} ({t.id})</option>
    {/each}
  </select>

  {#if isDecision}
    {@const newCondFocus = attachVarPaneFocus({
      label: `${node.name || 'decision'} · new branch`,
      insert: (snippet) => { newCondition = newCondition ? `${newCondition} ${snippet}` : snippet; }
    })}
    <div class="mt-1 flex items-center gap-1">
      <input
        type="text"
        placeholder={'condition (e.g. {{ vars.score > 50 }})'}
        bind:value={newCondition}
        disabled={newDefault}
        onfocus={newDefault ? undefined : newCondFocus.onfocus}
        onblur={newDefault ? undefined : newCondFocus.onblur}
        class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px] disabled:opacity-50"
      />
      {#if !newDefault}
        <VarPathPicker
          {node}
          {playbook}
          shapes={jinjaShapesStore.shapes}
          wrap={true}
          onInsert={(snippet) => {
            newCondition = newCondition ? `${newCondition} ${snippet}` : snippet;
          }}
        />
      {/if}
    </div>
    <label class="mt-1 flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
      <input type="checkbox" bind:checked={newDefault} />
      <span>Default (else)</span>
    </label>
  {/if}

  {#if isManualInput}
    <select
      aria-label="New branch form type"
      bind:value={newFormType}
      class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
    >
      {#each FORM_TYPES as ft}
        <option value={ft}>{ft || '— form type (optional) —'}</option>
      {/each}
    </select>
  {/if}

  <button
    type="button"
    class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
    onclick={addBranch}
    disabled={!newLabel.trim() || !newTarget}
  >+ Add branch</button>
</section>
