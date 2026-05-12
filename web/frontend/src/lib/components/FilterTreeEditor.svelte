<script lang="ts">
  /**
   * Recursive AND/OR filter-tree editor for triggers + FindRecords.
   *
   * Wire shape (mirrors FortiSOAR's Query API — see store/QUERY_API.md
   * §2.2 "Logic groups"):
   *
   *   { logic: "AND" | "OR",
   *     filters: [
   *       // leaf
   *       { field, operator, value, type, _operator?, _value? },
   *       // group — recurse
   *       { logic: "AND" | "OR", filters: [...] }
   *     ],
   *     limit?: 30,
   *     sort?: [] }
   *
   * Triggers nest the same shape under `arguments.fieldbasedtrigger`
   * (filters predicate-on-record-events); FindRecords nests it under
   * `arguments.query`. Other top-level keys (limit, sort, __selectFields)
   * are passed through untouched on every edit so we don't lose state
   * the FSR designer set.
   */
  import Self from './FilterTreeEditor.svelte';

  type Leaf = {
    field: string;
    operator: string;
    value: unknown;
    type?: string;
    _operator?: string;
    _value?: unknown;
  };
  type Group = { logic: 'AND' | 'OR'; filters: (Leaf | Group)[] };

  type FieldMeta = {
    name: string;
    title?: string | null;
    type?: string;
    operators?: string[];
    picklist_options?: string | null;
    tooltip?: string | null;
  };

  import VarPathPicker from './VarPathPicker.svelte';
  import type { VisualNode, VisualPlaybook } from '../api';

  type Props = {
    /** Root group. Pass `{logic:'AND', filters:[]}` if the underlying
     * argument is missing — the parent owns initialization. */
    group: Group;
    /** Replace the whole subtree. Caller is responsible for writing
     * back into the node arguments and dispatching to the visual store. */
    onChange: (next: Group) => void;
    /** Field catalog for the leaf field-name dropdown. Each entry's
     * `operators` (when present) scopes the operator picker to ops
     * that make sense for that field's type. Empty array = free text. */
    fields?: (string | FieldMeta)[];
    /** Recursion depth — internal. Caps the visual nesting to keep the
     * inspector readable when authors paste 6-deep monstrosities from
     * the live designer. */
    depth?: number;
    /** Show related-module fields (lookup / manyToMany / manyToOne /
     * oneToMany / a foreign module name as type)? Hidden on On-Create
     * triggers because querying a related module's fields is a
     * separate sub-tree the FSR designer only exposes when prior state
     * exists (On Update / Find Record). Defaults true. */
    allowRelatedModules?: boolean;
    /** Extra operators to merge into every field's catalog — used by
     * On Update triggers to surface `is_changed` on every field. */
    extraOperators?: string[];
    /** Names of every known FSR module. A field whose `type` matches
     * one of these is a relation to that module (the trained store
     * encodes relations by storing the target module's name as the
     * field type — e.g. `assignedTo: people`, `alerts: alerts`).
     * Without this set we can't distinguish relations from primitive
     * types like `string` or `picklists`. */
    moduleNames?: string[];
    /** Resolver for a related module's field catalog. Called when the
     * user drills into a relation (e.g. picks `assets`, then needs
     * `hostname`). Parent owns the fetch + cache so we don't re-issue
     * the same /api/ref/modules/<m>/fields request per leaf. Returns
     * an empty array while the load is in flight; FilterTreeEditor
     * re-renders when the parent's cache fills. */
    getRelatedFields?: (module: string) => FieldMeta[];
    /** When provided, leaf value inputs sprout a `{x}` button that
     * opens a Jinja var-path picker. Requires both the active node
     * and its playbook so the picker can walk inbound edges to
     * suggest predecessor outputs. Optional — leaves stay plain text
     * when omitted. */
    node?: VisualNode | null;
    playbook?: VisualPlaybook | null;
  };

  let {
    group, onChange, fields = [], depth = 0,
    allowRelatedModules = true, extraOperators = [],
    moduleNames = [], getRelatedFields = () => [],
    node = null, playbook = null
  }: Props = $props();
  let moduleNameSet = $derived(new Set(moduleNames));

  /** Split `assets.hostname` → `{root:'assets', sub:'hostname'}`.
   * Bare `assets` → `{root:'assets', sub:''}`. */
  function splitRelation(field: string): { root: string; sub: string } {
    if (!field) return { root: '', sub: '' };
    const dot = field.indexOf('.');
    if (dot < 0) return { root: field, sub: '' };
    return { root: field.slice(0, dot), sub: field.slice(dot + 1) };
  }

  /** Is the current leaf's root field a relation we can drill into? */
  function relationFor(rootField: string): string | null {
    const meta = fieldByName[rootField];
    if (!meta) return null;
    if (meta.type && moduleNameSet.has(meta.type)) return meta.type;
    if (meta.type === rootField && moduleNameSet.has(rootField)) return rootField;
    return null;
  }

  // Track which relation-leaf has its sub-field picker open. Stored
  // separately from `openPickerIdx` so the user can flip between the
  // root picker and the sub-field picker on the same leaf.
  let openSubPickerIdx = $state<number | null>(null);
  let subPickerFilter = $state('');

  function toggleSubPicker(i: number) {
    if (openSubPickerIdx === i) {
      openSubPickerIdx = null;
      subPickerFilter = '';
    } else {
      openSubPickerIdx = i;
      subPickerFilter = '';
      openPickerIdx = null;
    }
  }

  function pickSubField(i: number, relation: string, subField: FieldMeta) {
    const newType = valueTypeFor(subField.type);
    const validOps = subField.operators?.length ? subField.operators : OPERATORS;
    const cur = (group.filters[i] as Leaf).operator;
    const opNext = validOps.includes(cur) ? cur : validOps[0];
    patchAt(i, {
      field: `${relation}.${subField.name}`,
      type: newType,
      operator: opNext,
    });
    openSubPickerIdx = null;
    subPickerFilter = '';
  }

  // Normalize the heterogenous `fields` prop (string | FieldMeta) into
  // a lookup table for the per-field operator catalog and a flat name
  // list for the datalist suggestions. Callers can pass either form.
  let fieldList = $derived<FieldMeta[]>(
    fields.map((f) => (typeof f === 'string' ? { name: f } : f))
  );
  let fieldByName = $derived(
    Object.fromEntries(fieldList.map((f) => [f.name, f]))
  );

  /** Field types that point at another module, not a literal value.
   * Picking one of these in the FSR designer pivots the query into a
   * sub-tree on the related module's fields — flagged with a header
   * in the picker and hidden entirely on On-Create triggers (the
   * designer doesn't allow them there since the record has no prior
   * state to query against). */
  const RELATED_TYPES = new Set([
    'lookup', 'manyToMany', 'manyToOne', 'oneToMany'
  ]);

  /** Auto-detect whether every leaf in this group references the same
   * related module via its dotted prefix. When true, we render the
   * group as a "filter on <rel>:" sub-query and scope the field
   * picker to that relation's catalog so adding more conditions
   * doesn't make the user keep picking `assets` every time.
   *
   * Returns the relation name when:
   *   - the group has at least one leaf;
   *   - every leaf's field is `<rel>.<sub>` for the same `<rel>`;
   *   - `<rel>` is in `moduleNameSet` (so we know it's a real module).
   * Otherwise returns null and the group renders as a generic AND/OR. */
  let inferredRelation = $derived.by(() => {
    if (group.filters.length === 0) return null;
    let common: string | null = null;
    for (const f of group.filters) {
      if (isGroup(f)) return null;
      const fld = (f as Leaf).field || '';
      const dot = fld.indexOf('.');
      if (dot <= 0) return null;
      const root = fld.slice(0, dot);
      if (!moduleNameSet.has(root)) return null;
      if (common === null) common = root;
      else if (common !== root) return null;
    }
    return common;
  });
  let scopedFields = $derived(
    inferredRelation ? getRelatedFields(inferredRelation) : []
  );
  function isRelated(meta: FieldMeta): boolean {
    if (!meta.type) return false;
    if (RELATED_TYPES.has(meta.type)) return true;
    // The trained store encodes most relations by storing the target
    // module's name in the `type` column. We check against the live
    // modules list passed in by the parent.
    return moduleNameSet.has(meta.type);
  }

  // Two buckets so the related-module fields sort to the bottom of the
  // picker under their own header — matches the FSR designer's UX.
  let plainFields = $derived(
    fieldList.filter((f) => !isRelated(f)).sort((a, b) => a.name.localeCompare(b.name))
  );
  let relatedFields = $derived(
    allowRelatedModules
      ? fieldList.filter(isRelated).sort((a, b) => a.name.localeCompare(b.name))
      : []
  );

  // Per QUERY_API.md §2.1 — full operator catalog. `notlike` and
  // `search` are excluded (search is internal-only; notlike is
  // de-listed but technically works — surface only on demand).
  const OPERATORS = [
    'eq', 'neq',
    'lt', 'lte', 'gt', 'gte',
    'in', 'nin',
    'like',
    'contains', 'exists',
    'isnull'
  ];

  /** Friendly labels mirroring the FSR designer's operator dropdown.
   * Falls back to the wire token when no friendly label exists so a
   * future operator we don't have a label for still renders. */
  const OPERATOR_LABEL: Record<string, string> = {
    eq: 'equals',
    neq: 'not equal',
    lt: 'less than',
    lte: 'less or equal',
    gt: 'greater than',
    gte: 'greater or equal',
    in: 'is one of',
    nin: 'is not one of',
    like: 'matches pattern',
    notlike: 'does not match',
    contains: 'contains',
    exists: 'has key',
    isnull: 'is empty',
    changed: 'is changed',
    in_all: 'matches all of'
  };

  /** Map an FSR field type to the wire-level value `type` the query API
   * expects. Picklist / lookup / relation fields ship with `type:object`
   * (the value is an IRI); date-likes use `type:datetime`; everything
   * else is `type:primitive`. The user never sees this selector — it's
   * derived from the field they pick. */
  function valueTypeFor(fieldType: string | undefined): 'primitive' | 'object' | 'datetime' {
    switch (fieldType) {
      case 'picklists':
      case 'lookup':
      case 'manyToMany':
      case 'manyToOne':
      case 'oneToMany':
      case 'json':
      case 'object':
        return 'object';
      case 'datetime':
      case 'date':
        return 'datetime';
      default:
        return 'primitive';
    }
  }

  function isGroup(f: Leaf | Group): f is Group {
    return (f as Group).logic !== undefined;
  }

  // Track which leaf's field-picker is open. Stored as a per-row index
  // because there's never more than one open at a time within a group.
  let openPickerIdx = $state<number | null>(null);
  let pickerFilter = $state('');

  function toggleFieldPicker(i: number) {
    if (openPickerIdx === i) {
      openPickerIdx = null;
      pickerFilter = '';
    } else {
      openPickerIdx = i;
      pickerFilter = '';
    }
  }

  function pickField(i: number, name: string) {
    const meta = fieldByName[name];
    const newType = valueTypeFor(meta?.type);
    // When the field type changes the operator catalog narrows; if the
    // current operator is no longer valid for the new field type, snap
    // back to a sensible default so the leaf stays runnable.
    const validOps = meta?.operators?.length ? meta.operators : OPERATORS;
    const cur = (group.filters[i] as Leaf).operator;
    const opNext = validOps.includes(cur) ? cur : validOps[0];
    patchAt(i, { field: name, type: newType, operator: opNext });
    openPickerIdx = null;
    pickerFilter = '';
  }

  function setLogic(v: 'AND' | 'OR') {
    onChange({ ...group, logic: v });
  }

  function addLeaf() {
    // When the group is auto-scoped to a relation (every existing
    // leaf is `<rel>.X`), pre-seed the new leaf with the same prefix
    // so the user only has to pick the sub-field. Falls back to a
    // bare empty field when there's no inferred scope.
    const seed: Leaf = inferredRelation
      ? { field: `${inferredRelation}.`, operator: 'eq', value: '',
          type: 'primitive', _operator: 'eq' }
      : { field: '', operator: 'eq', value: '', type: 'primitive', _operator: 'eq' };
    onChange({ ...group, filters: [...group.filters, seed] });
  }

  function addGroup() {
    onChange({
      ...group,
      filters: [...group.filters, { logic: 'AND', filters: [] }]
    });
  }

  function patchAt(i: number, patch: Partial<Leaf>) {
    const copy = group.filters.slice();
    const cur = copy[i] as Leaf;
    copy[i] = { ...cur, ...patch };
    // Keep `_operator` shadow in sync with `operator` — the FSR designer
    // reads it back when rebuilding the predicate UI; drift produces an
    // empty operator dropdown on round-trip.
    if (patch.operator !== undefined) (copy[i] as Leaf)._operator = patch.operator;
    onChange({ ...group, filters: copy });
  }

  function replaceAt(i: number, child: Group) {
    const copy = group.filters.slice();
    copy[i] = child;
    onChange({ ...group, filters: copy });
  }

  function removeAt(i: number) {
    const copy = group.filters.slice();
    copy.splice(i, 1);
    onChange({ ...group, filters: copy });
  }

  function valueToText(v: unknown): string {
    if (v === undefined || v === null) return '';
    if (typeof v === 'string') return v;
    return JSON.stringify(v);
  }
</script>

<div class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2"
     style:margin-left={depth > 0 ? '0.5rem' : ''}>
  <div class="flex items-center gap-2">
    <select
      aria-label="Group logic"
      value={group.logic}
      onchange={(e) => setLogic((e.currentTarget as HTMLSelectElement).value as 'AND' | 'OR')}
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[11px] font-semibold"
    >
      <option value="AND">AND</option>
      <option value="OR">OR</option>
    </select>
    <span class="text-[10px] text-[var(--text-faint)]">
      {group.filters.length} {group.filters.length === 1 ? 'condition' : 'conditions'}
    </span>
    {#if inferredRelation}
      <span
        class="ml-2 rounded-full bg-[var(--brand)]/15 px-2 py-0.5 text-[10px] font-medium text-[var(--brand)]"
        title={`All conditions filter on the related ${inferredRelation} module's fields`}
      >
        on <code class="font-mono">{inferredRelation}</code>
      </span>
    {/if}
  </div>

  {#if group.filters.length === 0}
    <p class="mt-2 text-[11px] italic text-[var(--text-faint)]">
      No conditions. Add a leaf or a nested group below.
    </p>
  {:else}
    <ul class="mt-2 space-y-2">
      {#each group.filters as f, i (i)}
        <li>
          {#if isGroup(f)}
            <div class="flex items-start gap-1">
              <Self
                group={f}
                fields={fields}
                depth={depth + 1}
                onChange={(child) => replaceAt(i, child)}
              />
              <button
                type="button"
                class="text-[10px] text-rose-600 hover:text-rose-700"
                aria-label="Remove group"
                onclick={() => removeAt(i)}
              >×</button>
            </div>
          {:else}
            {@const split = splitRelation(f.field)}
            {@const relation = relationFor(split.root)}
            {@const subFieldList = relation ? getRelatedFields(relation) : []}
            {@const subFieldByName = Object.fromEntries(subFieldList.map((x) => [x.name, x]))}
            {@const subMeta = relation && split.sub ? subFieldByName[split.sub] : undefined}
            {@const meta = subMeta ?? fieldByName[split.root]}
            {@const baseOps = meta?.operators?.length ? meta.operators : OPERATORS}
            {@const opsForField = extraOperators.length ? [...baseOps, ...extraOperators.filter((x) => !baseOps.includes(x))] : baseOps}
            {@const matchesFilter = (x: FieldMeta) =>
              !pickerFilter ||
              x.name.toLowerCase().includes(pickerFilter.toLowerCase()) ||
              (x.title ?? '').toLowerCase().includes(pickerFilter.toLowerCase())}
            {@const visiblePlain = plainFields.filter(matchesFilter)}
            {@const visibleRelated = relatedFields.filter(matchesFilter)}
            <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1">
              <div class="flex flex-wrap items-center gap-1">
                <!-- Field picker. Click to open a real dropdown listing
                     the module's fields with title + type; falls back
                     to a free-text input when no field catalog was
                     passed in. -->
                {#if fieldList.length > 0 && (!inferredRelation || split.root !== inferredRelation)}
                  <!-- Primary picker hides when the group is auto-scoped
                       to a relation AND this leaf's root matches that
                       relation; the relation chip in the group header
                       carries the same info, and the sub-field picker
                       below is the only meaningful pick at that point. -->
                  <div class="relative">
                    <button
                      type="button"
                      onclick={() => toggleFieldPicker(i)}
                      title={fieldByName[split.root]?.title ?? split.root ?? 'pick field'}
                      class="flex w-40 items-center justify-between rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 text-left font-mono text-[11px] hover:bg-[var(--bg-canvas)]"
                    >
                      <span class={split.root ? '' : 'italic text-[var(--text-faint)]'}>
                        {split.root || 'pick field…'}
                      </span>
                      <span class="ml-1 text-[10px] text-[var(--text-faint)]">▾</span>
                    </button>
                    {#if openPickerIdx === i}
                      <div
                        role="dialog"
                        aria-label="Field picker"
                        class="absolute left-0 z-20 mt-1 max-h-64 w-72 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-lg"
                      >
                        <input
                          type="text"
                          autofocus
                          placeholder="filter fields…"
                          bind:value={pickerFilter}
                          onkeydown={(e) => { if (e.key === 'Escape') { openPickerIdx = null; pickerFilter = ''; } }}
                          class="sticky top-0 block w-full border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px]"
                        />
                        {#if visiblePlain.length === 0 && visibleRelated.length === 0}
                          <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">no matches</p>
                        {:else}
                          <ul>
                            {#each visiblePlain as fld (fld.name)}
                              <li>
                                <button
                                  type="button"
                                  onclick={() => pickField(i, fld.name)}
                                  class="block w-full px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
                                >
                                  <div class="flex items-baseline justify-between gap-2">
                                    <span class="font-mono text-[11px] {f.field === fld.name ? 'font-bold text-[var(--brand)]' : ''}">{fld.name}</span>
                                    <span class="text-[10px] text-[var(--text-faint)]">{fld.type ?? ''}</span>
                                  </div>
                                  {#if fld.title}
                                    <div class="text-[10px] text-[var(--text-muted)]">{fld.title}</div>
                                  {/if}
                                </button>
                              </li>
                            {/each}
                            {#if visibleRelated.length > 0}
                              <li class="sticky border-t border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                                Related modules
                                <span class="ml-1 font-normal normal-case text-[var(--text-faint)]">— sub-query against the related record</span>
                              </li>
                              {#each visibleRelated as fld (fld.name)}
                                <li>
                                  <button
                                    type="button"
                                    onclick={() => pickField(i, fld.name)}
                                    class="block w-full px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
                                  >
                                    <div class="flex items-baseline justify-between gap-2">
                                      <span class="font-mono text-[11px] {f.field === fld.name ? 'font-bold text-[var(--brand)]' : ''}">{fld.name}</span>
                                      <span class="text-[10px] text-[var(--text-faint)]">{fld.type ?? ''}</span>
                                    </div>
                                    {#if fld.title}
                                      <div class="text-[10px] text-[var(--text-muted)]">{fld.title}</div>
                                    {/if}
                                  </button>
                                </li>
                              {/each}
                            {/if}
                          </ul>
                        {/if}
                      </div>
                    {/if}
                  </div>
                {:else}
                  <input
                    type="text"
                    placeholder="field"
                    value={f.field}
                    oninput={(e) => patchAt(i, { field: (e.currentTarget as HTMLInputElement).value })}
                    class="w-32 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[11px]"
                  />
                {/if}
                <!-- Sub-field picker for relation drills. Appears only
                     when the user selected a field whose type is
                     another module — at which point they can either
                     compare the relation directly (`assets eq <iri>`)
                     or drill in to a sub-field (`assets.hostname`). -->
                {#if relation}
                  {@const visibleSub = subPickerFilter
                    ? subFieldList.filter((x) =>
                        x.name.toLowerCase().includes(subPickerFilter.toLowerCase()) ||
                        (x.title ?? '').toLowerCase().includes(subPickerFilter.toLowerCase()))
                    : subFieldList}
                  <span class="text-[10px] text-[var(--text-faint)]">→</span>
                  <div class="relative">
                    <button
                      type="button"
                      onclick={() => toggleSubPicker(i)}
                      title={split.sub
                        ? `${relation}.${split.sub}${subMeta?.title ? ' — ' + subMeta.title : ''}`
                        : `pick a field on ${relation}`}
                      class="flex w-40 items-center justify-between rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 text-left font-mono text-[11px] hover:bg-[var(--bg-canvas)]"
                    >
                      <span class={split.sub ? '' : 'italic text-[var(--text-faint)]'}>
                        {split.sub || `${relation} field…`}
                      </span>
                      <span class="ml-1 text-[10px] text-[var(--text-faint)]">▾</span>
                    </button>
                    {#if openSubPickerIdx === i}
                      <div
                        role="dialog"
                        aria-label={`${relation} field picker`}
                        class="absolute left-0 z-20 mt-1 max-h-64 w-72 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-lg"
                      >
                        <div class="sticky top-0 border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                          fields on {relation}
                        </div>
                        <input
                          type="text"
                          placeholder="filter…"
                          bind:value={subPickerFilter}
                          onkeydown={(e) => { if (e.key === 'Escape') { openSubPickerIdx = null; subPickerFilter = ''; } }}
                          class="block w-full border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px]"
                        />
                        {#if subFieldList.length === 0}
                          <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">
                            loading {relation} fields…
                          </p>
                        {:else if visibleSub.length === 0}
                          <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">no matches</p>
                        {:else}
                          <ul>
                            {#each visibleSub as sf (sf.name)}
                              <li>
                                <button
                                  type="button"
                                  onclick={() => pickSubField(i, relation, sf)}
                                  class="block w-full px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
                                >
                                  <div class="flex items-baseline justify-between gap-2">
                                    <span class="font-mono text-[11px] {split.sub === sf.name ? 'font-bold text-[var(--brand)]' : ''}">{sf.name}</span>
                                    <span class="text-[10px] text-[var(--text-faint)]">{sf.type ?? ''}</span>
                                  </div>
                                  {#if sf.title}
                                    <div class="text-[10px] text-[var(--text-muted)]">{sf.title}</div>
                                  {/if}
                                </button>
                              </li>
                            {/each}
                          </ul>
                        {/if}
                      </div>
                    {/if}
                  </div>
                {/if}
                <select
                  aria-label="Operator"
                  value={f.operator}
                  onchange={(e) => patchAt(i, { operator: (e.currentTarget as HTMLSelectElement).value })}
                  class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1 py-0.5 font-mono text-[11px]"
                  title={meta?.type ? `operators valid for ${meta.type}` : 'all operators'}
                >
                  {#each opsForField as op}
                    <option value={op}>{OPERATOR_LABEL[op] ?? op}</option>
                  {/each}
                </select>
                {#if f.operator === 'isnull'}
                  <select
                    aria-label="isnull value"
                    value={String(f.value ?? 'true')}
                    onchange={(e) => patchAt(i, { value: (e.currentTarget as HTMLSelectElement).value })}
                    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1 py-0.5 font-mono text-[11px]"
                  >
                    <option value="true">is empty</option>
                    <option value="false">is not empty</option>
                  </select>
                {:else if f.operator === 'changed'}
                  <!-- `changed` has no value side — the trigger fires
                       whenever the field's value differs from before.
                       Confirmed against the live-FSR corpus (300+
                       post_update steps use this exact operator). -->
                  <span class="text-[11px] italic text-[var(--text-faint)]">(any change to this field)</span>
                {:else}
                  <input
                    type="text"
                    placeholder="value"
                    value={valueToText(f.value)}
                    oninput={(e) => patchAt(i, { value: (e.currentTarget as HTMLInputElement).value })}
                    class="min-w-[8rem] flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[11px]"
                  />
                  {#if node}
                    <VarPathPicker
                      {node}
                      {playbook}
                      wrap={true}
                      onInsert={(snippet) => {
                        const cur = valueToText(f.value);
                        patchAt(i, { value: cur ? `${cur} ${snippet}` : snippet });
                      }}
                    />
                  {/if}
                {/if}
                <button
                  type="button"
                  class="text-[10px] text-rose-600 hover:text-rose-700"
                  aria-label="Remove condition"
                  onclick={() => removeAt(i)}
                >×</button>
              </div>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  <div class="mt-2 flex gap-2">
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-elev)]"
      onclick={addLeaf}
    >+ condition</button>
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-elev)]"
      onclick={addGroup}
    >+ group</button>
  </div>
</div>
