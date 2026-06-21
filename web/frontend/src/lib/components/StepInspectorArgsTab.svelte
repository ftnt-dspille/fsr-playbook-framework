<script lang="ts">
  /**
   * Phase 2.1 — schema-driven Args view.
   *
   * For connector_op nodes we fetch `get_op_schema` and lay each
   * declared param next to its current value. Conditional params
   * (`param_groups_by_select`) are rendered grouped by their
   * gating select-value so the user sees which branch is active.
   *
   * Read-only in Phase 2. Phase 3 introduces edit-back via the
   * Phase 0.1 dispatcher.
   */
  import { callMcpTool } from '../api';
  import type { VisualNode } from '../api';
  import { visualStore } from '../visualEditStore.svelte';
  import ConnectorIcon from './ConnectorIcon.svelte';
  import ConnectorPicker from './ConnectorPicker.svelte';
  import OperationPicker from './OperationPicker.svelte';
  import FilterTreeEditor from './FilterTreeEditor.svelte';
  import RelationPicker from './RelationPicker.svelte';
  import MonacoCode from './MonacoCode.svelte';
  import VarPathPicker from './VarPathPicker.svelte';
  import { attachVarPaneFocus } from '../varPaneFocus';
  import { jinjaShapesStore } from '../jinjaShapesStore.svelte';
  import { sampleRecordsStore } from '../triggerModuleFields.svelte';
  import SampleRecordPicker from './SampleRecordPicker.svelte';
  import JinjaInlinePreview from './JinjaInlinePreview.svelte';
  import { summarizeTrigger, summarizeFind } from '../filterSummary';

  type Props = {
    node: VisualNode;
    playbookIdx: number;
    /** Active VisualPlaybook; needed for the manual_input buttons preview
     * (we render the outgoing branch labels at the bottom of the form
     * builder). Optional so other call sites that don't have one yet
     * keep working. */
    playbook?: import('../api').VisualPlaybook | null;
  };
  let { node, playbookIdx, playbook = null }: Props = $props();

  // Modules + per-module field catalog. Backed by the trained
  // reference store via /api/ref/modules + /api/ref/modules/{m}/fields.
  // Cached at module-scope on first load; the inspector typically only
  // touches one or two modules per session.
  type ModuleSummary = { name: string; label: string | null; plural: string | null };
  type ModuleField = {
    name: string;
    title: string | null;
    type: string;
    required: boolean;
    picklist_options: string | null;
    tooltip: string | null;
    operators: string[];
  };
  let allModules = $state<ModuleSummary[]>([]);
  let modulesLoaded = $state(false);
  let modulesLoading = $state(false);
  let fieldsByModule = $state<Record<string, ModuleField[]>>({});
  let fieldsLoadingFor = $state<string | null>(null);

  async function ensureModulesLoaded() {
    if (modulesLoaded || modulesLoading) return;
    modulesLoading = true;
    try {
      const r = await fetch('/api/ref/modules');
      if (r.ok) allModules = await r.json();
      modulesLoaded = true;
    } catch { /* trained store missing — leave list empty */ }
    finally { modulesLoading = false; }
  }

  async function ensureFieldsLoaded(module: string) {
    if (!module) return;
    if (fieldsByModule[module] !== undefined) return;
    if (fieldsLoadingFor === module) return;
    fieldsLoadingFor = module;
    try {
      const r = await fetch(`/api/ref/modules/${encodeURIComponent(module)}/fields`);
      if (r.ok) {
        const data = await r.json();
        fieldsByModule = { ...fieldsByModule, [module]: data.fields ?? [] };
      } else {
        // Cache the empty result so we don't retry on every keystroke.
        fieldsByModule = { ...fieldsByModule, [module]: [] };
      }
    } catch {
      fieldsByModule = { ...fieldsByModule, [module]: [] };
    } finally {
      if (fieldsLoadingFor === module) fieldsLoadingFor = null;
    }
  }

  // Lazy-load on mount when the node is a trigger / record_crud — the
  // dropdown wants the list ready before the user clicks.
  $effect(() => {
    if (node.family === 'trigger' || node.family === 'record_crud') {
      void ensureModulesLoaded();
    }
  });

  /** Strip the `?$limit=30` (and any other query-string) tail that
   * FindRecords appends to its `module:` arg. The bare module name is
   * what `/api/ref/modules/{m}/fields` expects, and what the user sees
   * in the picker. */
  function bareModule(s: string | undefined | null): string {
    if (!s) return '';
    const q = s.indexOf('?');
    return (q < 0 ? s : s.slice(0, q)).trim();
  }

  /** Pull the active module name from the node's arguments — different
   * step families stash it in different keys. Centralised so the
   * field-loader effect below reacts to the same source the editor
   * blocks read. */
  function activeModule(): string {
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    if (node.family === 'trigger') {
      return bareModule(a.resource as string | undefined);
    }
    if (node.family === 'record_crud') {
      const m = a.module as string | undefined;
      if (m) return bareModule(m);
      const c = a.collection as string | undefined;
      if (c) return bareModule(c.replace(/^\/api\/(?:3|ingest-feeds)\//, ''));
    }
    return '';
  }

  // React to the module changing (either user picks a new one or a
  // freshly-mounted node already has one set) — load its field
  // catalog so the FilterTreeEditor's picker has data when the user
  // clicks. Using $effect (not `{@const}` for side-effects) so the
  // reactive graph actually fires the fetch.
  $effect(() => {
    const m = activeModule();
    if (m) void ensureFieldsLoaded(m);
  });

  type Param = {
    param_name: string;
    title?: string;
    type?: string;
    required?: number;
    description?: string;
    tooltip?: string;
    placeholder?: string;
    default_value?: string;
    options_json?: string[] | null;
    visible?: number;
    editable?: number;
    parent_param_name?: string;
    condition_value?: string;
    applies_when?: { parent: string; value: string }[];
  };

  type Schema = {
    op_name?: string;
    title?: string;
    description?: string;
    params?: Param[];
    param_groups_by_select?: Record<string, Param[]>;
    output_schema_json_keys?: string[];
    ok?: boolean;
    code?: string;
    message?: string;
    suggestions?: string[];
  };

  let schema = $state<Schema | null>(null);
  let loading = $state(false);
  let loadError: string | null = $state(null);

  // Connector + Operation autocomplete are owned by their respective
  // pickers (ConnectorPicker / OperationPicker). They commit on
  // selection/Enter/blur — never on partial keystrokes — so the
  // schema $effect below doesn't see "operation 'b'" mid-type.
  let connector = $derived(node.arguments?.connector as string | undefined);
  let opName = $derived(
    (node.arguments?.operation as string | undefined) ??
      (node.family === 'connector_op' ? node.type : undefined)
  );
  let configName = $derived((node.arguments?.config as string | undefined) ?? '');

  /** Configurations for the selected connector — populated on demand
   * from the live FSR (`list_connector_configurations` MCP). Empty list
   * when the env isn't configured or the connector has none yet. */
  type ConfigEntry = { config_id: string; name: string; default: boolean };
  let configurations = $state<ConfigEntry[]>([]);
  let configsLoading = $state(false);
  let configsLoadedFor = $state<string | null>(null);

  $effect(() => {
    const c = connector;
    if (!c) {
      configurations = [];
      configsLoadedFor = null;
      return;
    }
    if (configsLoadedFor === c) return;
    configsLoading = true;
    callMcpTool<{ configurations: ConfigEntry[] }>('list_connector_configurations', { connector: c })
      .then((r) => {
        if (connector !== c) return; // user moved on
        configurations = r.ok ? (r.result?.configurations ?? []) : [];
        configsLoadedFor = c;
      })
      .catch(() => {
        // Tolerate transport / 404 / FSR-down errors silently — the
        // form falls back to the "no configurations" hint.
        if (connector === c) {
          configurations = [];
          configsLoadedFor = c;
        }
      })
      .finally(() => { if (connector === c) configsLoading = false; });
  });

  function setConfig(value: string) {
    const args = { ...(deepClone(node.arguments) as Record<string, unknown>) };
    if (value) args.config = value;
    else delete args.config;
    visualStore.setArgs(playbookIdx, node.id, args);
  }

  // Track the previous schema's title/op_name so the auto-name logic
  // below can decide "did the user customise the name, or is it just
  // the previous operation's auto-derived label?" The set of strings
  // we treat as "system-set defaults" — overwrite on op change.
  let lastSchemaTitle: string | null = $state(null);
  let lastSchemaOpName: string | null = $state(null);

  $effect(() => {
    if (node.family !== 'connector_op' || !connector || !opName) {
      schema = null;
      loadError = null;
      return;
    }
    loading = true;
    loadError = null;
    callMcpTool<Schema>('get_op_schema', { connector, op: opName, verbose: true })
      .then((r) => {
        if (r.ok) {
          schema = r.result ?? null;
          maybeAutoRename(schema);
        }
        else loadError = r.error ?? 'tool error';
      })
      .catch((e) => (loadError = (e as Error).message))
      .finally(() => (loading = false));
  });

  /** When the user picks an operation (and the step name is still the
   * generic placeholder OR the previous op's auto-derived label), set
   * the step name to the new operation's title. Skips if the user has
   * obviously customised the name. */
  function maybeAutoRename(s: Schema | null) {
    if (!s) return;
    const newTitle = s.title || s.op_name || opName || '';
    if (!newTitle) return;
    const current = (node.name ?? '').trim();
    const isDefault =
      current === '' ||
      current === 'Connector Action' ||
      current === 'connector_action' ||
      current === 'Connector' ||
      (lastSchemaTitle !== null && current === lastSchemaTitle) ||
      (lastSchemaOpName !== null && current === lastSchemaOpName);
    lastSchemaTitle = newTitle;
    lastSchemaOpName = s.op_name ?? null;
    if (isDefault && current !== newTitle) {
      visualStore.patchNode(playbookIdx, node.id, { name: newTitle });
    }
  }

  function currentValue(name: string): unknown {
    const params = node.arguments?.params as Record<string, unknown> | undefined;
    if (params && name in params) return params[name];
    return node.arguments?.[name];
  }

  /** Like currentValue, but falls back to the schema default_value when
   * the param hasn't been set explicitly AND the param itself is
   * currently visible. Visibility is recursive: a hidden parent's
   * default never leaks into a child's gating check. Without the
   * recursion guard, params like fortigate-firewall:block_ip's `ip`
   * (gated on `ip_type=IPv4`) would render under method=Quarantine
   * Based simply because `ip_type` declared `default_value="IPv4"`,
   * even though `ip_type` itself is hidden under that method. */
  function effectiveValue(name: string, stack: Set<string> = new Set()): unknown {
    const v = currentValue(name);
    if (v !== undefined && v !== '') return v;
    const p = (schema?.params ?? []).find((x) => x.param_name === name);
    if (!p) return undefined;
    if (!paramVisibleRec(p, stack)) return undefined;
    return normalizeDefault(p.default_value);
  }

  /** `default_value` arrives JSON-quoted in the verbose schema response
   * (e.g. `"\"Quarantine Based\""` or `"true"`). Unwrap one level of JSON
   * encoding so equality / `options_json.includes` checks land on the
   * plain string the user actually sees. */
  function normalizeDefault(raw: unknown): string | undefined {
    if (raw === undefined || raw === null || raw === '') return undefined;
    if (typeof raw !== 'string') return String(raw);
    const t = raw.trim();
    if (
      (t.startsWith('"') && t.endsWith('"')) ||
      t === 'true' || t === 'false' || t === 'null' ||
      /^-?\d+(\.\d+)?$/.test(t)
    ) {
      try { const v = JSON.parse(t); return v == null ? undefined : String(v); }
      catch { /* fall through */ }
    }
    return raw;
  }

  function preview(v: unknown): string {
    if (v === undefined || v === null) return '';
    if (typeof v === 'string') return v;
    return JSON.stringify(v);
  }

  // Svelte 5 `$state` proxies aren't structured-cloneable; round-trip
  // through JSON for a clean, plain copy.
  function deepClone<T>(v: T): T {
    return JSON.parse(JSON.stringify(v ?? null));
  }

  /** Update a single connector-op param via the shared edit store. */
  function setParam(name: string, raw: string) {
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const params = ((args.params as Record<string, unknown>) ?? {});
    params[name] = raw;
    args.params = params;
    visualStore.setArgs(playbookIdx, node.id, args);
  }

  /** set_variable lives under arg_list:[{name,value}] post-parse. */
  function setVar(varName: string, raw: string) {
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const list = (args.arg_list as { name: string; value: unknown }[] | undefined) ?? [];
    const idx = list.findIndex((v) => v.name === varName);
    if (idx >= 0) list[idx] = { ...list[idx], value: raw };
    else list.push({ name: varName, value: raw });
    args.arg_list = list;
    visualStore.setArgs(playbookIdx, node.id, args);
  }

  let newVarName = $state('');
  function addVar() {
    const nm = newVarName.trim();
    if (!nm) return;
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const list = (args.arg_list as { name: string; value: unknown }[] | undefined) ?? [];
    if (list.some((v) => v.name === nm)) return;
    list.push({ name: nm, value: '' });
    args.arg_list = list;
    visualStore.setArgs(playbookIdx, node.id, args);
    newVarName = '';
  }
  function removeVar(name: string) {
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const list = (args.arg_list as { name: string; value: unknown }[] | undefined) ?? [];
    args.arg_list = list.filter((v) => v.name !== name);
    visualStore.setArgs(playbookIdx, node.id, args);
  }

  /** Rename a connector parameter (mostly relevant for G7 freeform params). */
  function renameParam(oldName: string, newName: string) {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === oldName) return;
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const params = ((args.params as Record<string, unknown>) ?? {});
    if (trimmed in params) return;  // collision — silent no-op
    params[trimmed] = params[oldName];
    delete params[oldName];
    args.params = params;
    visualStore.setArgs(playbookIdx, node.id, args);
  }
  function removeParam(name: string) {
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const params = ((args.params as Record<string, unknown>) ?? {});
    delete params[name];
    args.params = params;
    visualStore.setArgs(playbookIdx, node.id, args);
  }

  let newParamName = $state('');
  function addParam() {
    const nm = newParamName.trim();
    if (!nm) return;
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    const params = ((args.params as Record<string, unknown>) ?? {});
    if (nm in params) return;
    params[nm] = '';
    args.params = params;
    visualStore.setArgs(playbookIdx, node.id, args);
    newParamName = '';
  }

  /** Swap connector / operation on an existing connector_op node. Clears
   * params since they're op-specific. */
  function setConnectorField(field: 'connector' | 'operation', value: string) {
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    args[field] = value;
    if (field === 'operation') args.params = {};
    visualStore.setArgs(playbookIdx, node.id, args);
  }

  /** Decide whether a conditional param should render right now based
   * on the live values of its parent params. A param is "conditional"
   * when it carries `applies_when` (an OR list of parent=value rules)
   * or a single `parent_param_name`+`condition_value` pair. Returns
   * true if the param has no gating at all. */
  function paramVisible(p: Param): boolean {
    return paramVisibleRec(p, new Set());
  }

  /** Recursive visibility check with a visiting-set cycle guard. The
   * stack accumulates param names already on the current chain so a
   * malformed schema with mutual gating doesn't infinite-loop. */
  function paramVisibleRec(p: Param, stack: Set<string>): boolean {
    if (p.visible === 0) return false;
    const rules: { parent: string; value: string }[] = [];
    if (p.applies_when?.length) rules.push(...p.applies_when);
    else if (p.parent_param_name && p.condition_value !== undefined) {
      rules.push({ parent: p.parent_param_name, value: p.condition_value });
    }
    if (rules.length === 0) return true;
    if (stack.has(p.param_name)) return true; // cycle — assume visible
    const next = new Set(stack); next.add(p.param_name);
    return rules.some((r) => String(effectiveValue(r.parent, next) ?? '') === String(r.value));
  }

  let visibleParams = $derived((schema?.params ?? []).filter(paramVisible));
  let hiddenParams  = $derived((schema?.params ?? []).filter((p) => !paramVisible(p)));

  let schemaParamNames = $derived(new Set((schema?.params ?? []).map((p) => p.param_name)));
  let extraParamEntries = $derived(
    Object.entries((node.arguments?.params as Record<string, unknown>) ?? {})
      .filter(([k]) => !schemaParamNames.has(k))
  );

  let varList = $derived((node.arguments?.arg_list as { name: string; value: unknown }[] | undefined) ?? []);

  // --- Picklist precheck on blur (Phase 4.5) -------------------------
  // Scans a value for `{{ 'VAL' | picklist('NAME') }}` literals; for
  // each unique pair, calls precheck_picklist_value and stashes the
  // result keyed by param name so we can render close-match suggestions.
  type PicklistMatch = { picklist: string; value: string; ok: boolean; message?: string; suggestions?: string[] };
  const PICKLIST_RE = /\{\{\s*['"]([^'"]+)['"]\s*\|\s*picklist\(\s*['"]([^'"]+)['"]\s*\)/g;
  let picklistResults: Record<string, PicklistMatch[]> = $state({});

  async function precheckPicklist(paramName: string, raw: string) {
    const text = String(raw ?? '');
    const pairs = new Map<string, { picklist: string; value: string }>();
    for (const m of text.matchAll(PICKLIST_RE)) {
      const value = m[1];
      const picklist = m[2];
      pairs.set(`${picklist}|${value}`, { picklist, value });
    }
    if (pairs.size === 0) {
      // Clear any stale results once the literal is gone.
      if (picklistResults[paramName]) {
        const next = { ...picklistResults };
        delete next[paramName];
        picklistResults = next;
      }
      return;
    }
    const checks = await Promise.all(
      [...pairs.values()].map(async ({ picklist, value }) => {
        try {
          const r = await callMcpTool<Record<string, unknown>>('precheck_picklist_value', {
            picklist_name: picklist,
            value
          });
          const out = r.result ?? {};
          return {
            picklist,
            value,
            ok: !!out['ok'],
            message: (out['message'] as string) ?? undefined,
            suggestions: (out['suggestions'] as string[] | undefined) ?? undefined
          } satisfies PicklistMatch;
        } catch (e: any) {
          return { picklist, value, ok: false, message: String(e?.message ?? e) } satisfies PicklistMatch;
        }
      })
    );
    picklistResults = { ...picklistResults, [paramName]: checks };
  }
</script>

<!-- Shared module datalist — referenced by every Resource/Module input
     in the trigger + record_crud editors below. Rendered once so we
     don't repeat it inside the {#each} branches. -->
{#if allModules.length > 0}
  <datalist id="fsrpb-modules-list">
    {#each allModules as m (m.name)}
      <!-- modules.label often holds the FSR Jinja template for the
           record's display name (e.g. `{{ name }}`) — not useful as a
           UI label. Show the plural noun when distinct from the
           machine name; that's what the analyst recognizes. -->
      <option value={m.name}>{m.plural && m.plural !== m.name ? m.plural : ''}</option>
    {/each}
  </datalist>
{/if}

{#if node.type === 'manual_input'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const canonSchema = ((a.input as Record<string, unknown> | undefined)?.schema as Record<string, unknown> | undefined)}
  {@const friendlyInputs = a.inputs as Record<string, unknown>[] | undefined}
  {@const canonicalInputs = canonSchema?.inputVariables as Record<string, unknown>[] | undefined}
  {@const fields = (Array.isArray(canonicalInputs) && canonicalInputs.length > 0
    ? canonicalInputs
    : Array.isArray(friendlyInputs) ? friendlyInputs : [])}
  {@const title = (a.title as string | undefined) ?? (canonSchema?.title as string | undefined) ?? ''}
  {@const description = (a.description as string | undefined) ?? (canonSchema?.description as string | undefined) ?? ''}

  {@const FORM_TYPES = [
    'text', 'textarea', 'number', 'integer', 'boolean', 'datetime',
    'picklist', 'lookup', 'ipv4', 'ipv6', 'email', 'url', 'domain', 'json'
  ]}

  {@const writeFields = (next: Record<string, unknown>[]) => {
    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
    args.inputs = next;
    // Drop the canonical block when present so we have one source of
    // truth — the resolver re-expands `inputs:` into `input.schema.*`
    // at compile time.
    delete args.input;
    visualStore.setArgs(playbookIdx, node.id, args);
  }}

  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Form prompt</div>
  <p class="mt-1 text-[11px] text-[var(--text-faint)]">
    Build the form an analyst sees at runtime. Each field collects one
    input; <em>buttons</em> at the bottom resume the playbook on the
    matching branch.
  </p>

  <label class="mt-2 block">
    <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Title</span>
    <input
      type="text"
      value={title}
      placeholder="What is shown in the form header"
      oninput={(e) => {
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        const v = (e.currentTarget as HTMLInputElement).value;
        if (v) args.title = v; else delete args.title;
        delete args.input;
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
      class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
    />
  </label>
  <label class="mt-2 block">
    <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Description (HTML allowed)</span>
    <textarea
      rows="3"
      value={description}
      placeholder="Context the analyst reads before answering — supports markdown / inline HTML."
      oninput={(e) => {
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        const v = (e.currentTarget as HTMLTextAreaElement).value;
        if (v) args.description = v; else delete args.description;
        delete args.input;
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
      class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
    ></textarea>
  </label>

  <div class="mt-3 flex flex-wrap gap-3 text-[11px] text-[var(--text-muted)]">
    <label class="flex items-center gap-1">
      <input
        type="checkbox"
        checked={(a.is_approval as boolean) ?? false}
        onchange={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.is_approval = (e.currentTarget as HTMLInputElement).checked;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
      <span title="Marks the prompt as an Approval — surfaces in the analyst's queue with approval-specific UX.">approval</span>
    </label>
    <label class="flex items-center gap-1">
      <input
        type="checkbox"
        checked={(a.isRecordLinked as boolean) ?? false}
        onchange={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.isRecordLinked = (e.currentTarget as HTMLInputElement).checked;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
      <span>linked to record</span>
    </label>
    <label class="flex items-center gap-1">
      <input
        type="checkbox"
        checked={(a.unauthenticated_input as boolean) ?? false}
        onchange={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.unauthenticated_input = (e.currentTarget as HTMLInputElement).checked;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
      <span title="Allow unauthenticated users to respond via tokenized link (external mode).">unauth respond</span>
    </label>
  </div>

  <div class="mt-4">
    <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Fields ({fields.length})</div>
    {#if fields.length === 0}
      <p class="text-[11px] italic text-[var(--text-faint)]">No fields. Add one below — the form will render with just the buttons.</p>
    {:else}
      <ul class="space-y-2">
        {#each fields as f, idx (f.name ?? `__${idx}`)}
          <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
            <div class="flex items-baseline gap-1">
              <input
                type="text"
                aria-label="Field name"
                value={(f.name as string) ?? ''}
                placeholder="field_name"
                onchange={(e) => {
                  const v = (e.currentTarget as HTMLInputElement).value.trim();
                  if (!v) return;
                  const next = fields.slice();
                  next[idx] = { ...next[idx], name: v };
                  writeFields(next);
                }}
                class="w-32 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1.5 py-0.5 font-mono text-[11px]"
              />
              <select
                aria-label="Form type"
                value={((f.formType as string | undefined) ?? (f.type as string | undefined)) ?? 'text'}
                onchange={(e) => {
                  const v = (e.currentTarget as HTMLSelectElement).value;
                  const next = fields.slice();
                  next[idx] = { ...next[idx], formType: v };
                  writeFields(next);
                }}
                class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1 py-0.5 text-[11px]"
              >
                {#each FORM_TYPES as ft}
                  <option value={ft}>{ft}</option>
                {/each}
              </select>
              <label class="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
                <input
                  type="checkbox"
                  checked={(f.required as boolean) ?? false}
                  onchange={(e) => {
                    const next = fields.slice();
                    next[idx] = { ...next[idx], required: (e.currentTarget as HTMLInputElement).checked };
                    writeFields(next);
                  }}
                />
                <span>required</span>
              </label>
              <button
                type="button"
                class="ml-auto text-[10px] text-rose-600 hover:text-rose-700"
                aria-label="Remove field"
                onclick={() => {
                  const next = fields.slice();
                  next.splice(idx, 1);
                  writeFields(next);
                }}
              >×</button>
            </div>
            <input
              type="text"
              aria-label="Label"
              value={(f.label as string) ?? ''}
              placeholder="Display label (what the analyst sees)"
              oninput={(e) => {
                const next = fields.slice();
                next[idx] = { ...next[idx], label: (e.currentTarget as HTMLInputElement).value };
                writeFields(next);
              }}
              class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-[11px]"
            />
            <input
              type="text"
              aria-label="Tooltip"
              value={(f.tooltip as string) ?? ''}
              placeholder="Tooltip / help text (optional)"
              oninput={(e) => {
                const next = fields.slice();
                const v = (e.currentTarget as HTMLInputElement).value;
                if (v) next[idx] = { ...next[idx], tooltip: v };
                else { const c: Record<string, unknown> = { ...next[idx] }; delete c.tooltip; next[idx] = c; }
                writeFields(next);
              }}
              class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-[11px] text-[var(--text-muted)]"
            />
            <input
              type="text"
              aria-label="Default value"
              value={typeof f.defaultValue === 'string' ? f.defaultValue : (f.defaultValue == null ? '' : JSON.stringify(f.defaultValue))}
              placeholder="Default value (optional, supports Jinja)"
              oninput={(e) => {
                const next = fields.slice();
                const v = (e.currentTarget as HTMLInputElement).value;
                if (v) next[idx] = { ...next[idx], defaultValue: v };
                else { const c: Record<string, unknown> = { ...next[idx] }; delete c.defaultValue; next[idx] = c; }
                writeFields(next);
              }}
              class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
            />
          </li>
        {/each}
      </ul>
    {/if}
    <button
      type="button"
      class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[11px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => {
        // Pick a unique name so the {#each} key doesn't collide with
        // an existing row.
        let i = 1; let nm = 'newField';
        const used = new Set(fields.map((x) => x.name as string | undefined).filter(Boolean));
        while (used.has(nm)) { i += 1; nm = `newField_${i}`; }
        writeFields([...fields, {
          name: nm, label: '', formType: 'text', required: false
        }]);
      }}
    >+ Add field</button>
  </div>

  <!-- Buttons (one branch per option) are now rendered+editable by
       the Branches section that StepInspector folds in beneath this
       block. Keeping a separate preview here would double-render the
       same data and drift out of sync on edits. -->

{:else if node.type === 'code_snippet'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const params = (a.params as Record<string, unknown> | undefined) ?? {}}
  {@const code = (params.python_function as string | undefined) ?? ''}

  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Code snippet (Python / Jinja-Python)</div>
  <p class="mt-1 text-[11px] text-[var(--text-faint)]">
    Run inline Python against the playbook's <code class="font-mono">vars</code>
    context. The function body is wrapped server-side; reference inputs as
    <code class="font-mono">{`{{ vars.X }}`}</code> or via
    <code class="font-mono">step_variables</code> bindings.
  </p>
  <div class="mt-2">
    <MonacoCode
      value={code}
      language="python"
      placeholder={'def main():\n    return {"result": vars.input.records[0]}'}
      height="20rem"
      onInput={(v) => {
        // Skip the round-trip when Monaco fired with an unchanged
        // value (it does on initial mount + theme swaps); otherwise
        // we'd dirty the playbook on every node click.
        if (v === code) return;
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        const p = { ...((args.params as Record<string, unknown>) ?? {}) };
        p.python_function = v;
        args.params = p;
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
    />
  </div>
  <p class="mt-1 text-[10px] text-[var(--text-faint)]">
    Monaco editor with Python highlighting · Jinja
    <code class="font-mono">{'{{ vars.X }}'}</code>
    expressions resolve at runtime · Tab indents 4 spaces.
  </p>

{:else if node.type === 'workflow_reference' || node.family === 'workflow_ref'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const target = (a.workflowReference as string | undefined) ?? ''}
  {@const inputMap = (a.arguments as Record<string, unknown> | undefined) ?? {}}

  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Workflow reference</div>
  <p class="mt-1 text-[11px] text-[var(--text-faint)]">
    Invoke another playbook by IRI. Inputs flow through
    <code class="font-mono">arguments</code>, indexed by name on the
    target playbook's input parameters.
  </p>

  <label class="mt-2 block">
    <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Target playbook IRI</span>
    <input
      type="text"
      value={target}
      placeholder={'/api/3/workflows/<uuid>  or  {{ globalVars.MyPlaybook_IRI }}' /* live picker is a TODO */}
      oninput={(e) => {
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        const v = (e.currentTarget as HTMLInputElement).value;
        if (v) args.workflowReference = v;
        else delete args.workflowReference;
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
      class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
    />
  </label>

  <div class="mt-3 flex flex-wrap gap-3 text-[11px] text-[var(--text-muted)]">
    <label class="flex items-center gap-1">
      <input
        type="checkbox"
        checked={(a.apply_async as boolean) ?? false}
        onchange={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.apply_async = (e.currentTarget as HTMLInputElement).checked;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
      <span title="Fire-and-forget — caller does not wait for the nested playbook to finish.">apply_async</span>
    </label>
    <label class="flex items-center gap-1">
      <input
        type="checkbox"
        checked={(a.pass_input_record as boolean) ?? true}
        onchange={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.pass_input_record = (e.currentTarget as HTMLInputElement).checked;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
      <span>pass input record</span>
    </label>
    <label class="flex items-center gap-1">
      <input
        type="checkbox"
        checked={(a.pass_parent_env as boolean) ?? false}
        onchange={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.pass_parent_env = (e.currentTarget as HTMLInputElement).checked;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
      <span title="Forward the caller's vars/env into the nested playbook.">pass parent env</span>
    </label>
  </div>

  <div class="mt-3">
    <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
      Input mapping
    </div>
    {#if Object.keys(inputMap).length === 0}
      <p class="text-[11px] italic text-[var(--text-faint)]">No inputs mapped. Add one below.</p>
    {:else}
      <ul class="space-y-1">
        {#each Object.entries(inputMap) as [k, v] (k)}
          <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
            <div class="flex items-baseline gap-1">
              <input
                type="text"
                aria-label={`input name ${k}`}
                value={k}
                onchange={(e) => {
                  const newKey = (e.currentTarget as HTMLInputElement).value.trim();
                  if (!newKey || newKey === k) return;
                  const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                  const m = { ...((args.arguments as Record<string, unknown>) ?? {}) };
                  if (newKey in m) return;
                  m[newKey] = m[k];
                  delete m[k];
                  args.arguments = m;
                  visualStore.setArgs(playbookIdx, node.id, args);
                }}
                class="w-32 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1.5 py-0.5 font-mono text-[11px]"
              />
              <button
                type="button"
                class="ml-auto text-[10px] text-rose-600 hover:text-rose-700"
                aria-label={`Remove input ${k}`}
                onclick={() => {
                  const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                  const m = { ...((args.arguments as Record<string, unknown>) ?? {}) };
                  delete m[k];
                  args.arguments = m;
                  visualStore.setArgs(playbookIdx, node.id, args);
                }}
              >×</button>
            </div>
            <textarea
              rows="2"
              value={typeof v === 'string' ? v : JSON.stringify(v, null, 2)}
              oninput={(e) => {
                const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                const m = { ...((args.arguments as Record<string, unknown>) ?? {}) };
                m[k] = (e.currentTarget as HTMLTextAreaElement).value;
                args.arguments = m;
                visualStore.setArgs(playbookIdx, node.id, args);
              }}
              class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
            ></textarea>
          </li>
        {/each}
      </ul>
    {/if}
    <button
      type="button"
      class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[11px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => {
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        const m = { ...((args.arguments as Record<string, unknown>) ?? {}) };
        let i = 1; let nm = 'newInput';
        while (nm in m) { i += 1; nm = `newInput_${i}`; }
        m[nm] = '';
        args.arguments = m;
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
    >+ Add input</button>
  </div>

{:else if node.family === 'trigger'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const fbt = (a.fieldbasedtrigger as Record<string, unknown> | undefined) ?? null}
  {@const rootGroup = {
    logic: ((fbt?.logic as 'AND' | 'OR') ?? 'AND'),
    filters: (Array.isArray(fbt?.filters) ? (fbt!.filters as unknown[]) : []) as any[]
  }}
  {@const resource = (a.resource as string | undefined) ?? ''}

  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Trigger</div>
  <p class="mt-1 text-[11px] text-[var(--text-faint)]">
    {#if node.type === 'start_on_create'}Fires when a record is created in the chosen module.{:else if node.type === 'start_on_update'}Fires when a record is updated in the chosen module.{:else if node.type === 'manual_action'}Fires when an analyst clicks an action button on a record.{:else if node.type === 'api_call'}Fires when an external system POSTs to this playbook's endpoint.{:else}Manual trigger — runs on demand.{/if}
  </p>

  <label class="mt-2 block">
    <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Resource (module)</span>
    <input
      type="text"
      list="fsrpb-modules-list"
      value={resource}
      placeholder={modulesLoaded && allModules.length ? 'pick from list…' : 'alerts | incidents | indicators | tasks | …'}
      oninput={(e) => {
        const v = (e.currentTarget as HTMLInputElement).value;
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        if (v) {
          args.resource = v;
          args.resources = [v];
        } else {
          delete args.resource;
          delete args.resources;
        }
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
      class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
    />
    {#if !modulesLoaded && modulesLoading}
      <p class="mt-0.5 text-[10px] italic text-[var(--text-faint)]">loading modules…</p>
    {:else if modulesLoaded && allModules.length === 0}
      <p class="mt-0.5 text-[10px] italic text-[var(--text-faint)]">
        Module catalog empty — run <code>fsrpb train</code> against the live FSR to populate.
      </p>
    {/if}
  </label>

  <!-- Sample record from the live FSR. Picking one tells the variable
       picker + Verify tab "this is what vars.input.records[0] will look
       like at runtime" so authors can validate fields exist + see real
       values inline. Lives at module level (not per-step) so it stays
       valid even after the user navigates away and back. -->
  {#if resource}
    {@const bareRes = bareModule(resource)}
    <SampleRecordPicker module={bareRes} />
  {/if}

  {#if node.type === 'start_on_create' || node.type === 'start_on_update'}
    <div class="mt-3">
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Filter conditions
      </div>
      <!-- Live English summary of the trigger — refreshes as the user
           edits filters so they can sanity-check intent without
           parsing the AND/OR tree visually. -->
      <p class="mb-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[11px] italic text-[var(--text-default)]">
        {summarizeTrigger(node.type, resource, rootGroup)}
      </p>
      <FilterTreeEditor
        group={rootGroup}
        fields={fieldsByModule[resource] ?? []}
        moduleNames={allModules.map((m) => m.name)}
        node={node}
        playbook={playbook ?? null}
        getRelatedFields={(m) => {
          // Trigger the lazy-load for the related module if we
          // haven't fetched it yet; return whatever's cached so far
          // (empty array on first call → the picker shows
          // "loading…" until the fetch resolves and Svelte's $state
          // reactivity re-renders).
          void ensureFieldsLoaded(m);
          return fieldsByModule[m] ?? [];
        }}
        allowRelatedModules={node.type !== 'start_on_create'}
        extraOperators={node.type === 'start_on_update' ? ['changed', 'in_all'] : ['in_all']}
        onChange={(next) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          const prev = (args.fieldbasedtrigger as Record<string, unknown> | undefined) ?? {};
          args.fieldbasedtrigger = {
            ...prev,
            logic: next.logic,
            filters: next.filters,
            // Preserve sort/limit set by the FSR designer; default when missing.
            limit: (prev.limit as number) ?? 30,
            sort: (prev.sort as unknown[]) ?? []
          };
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
    </div>

    <details class="mt-3 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <summary class="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Advanced
      </summary>
      <div class="mt-2 flex flex-col gap-2 text-[11px] text-[var(--text-muted)]">
        <label class="flex items-center gap-2">
          <input
            type="checkbox"
            checked={(a.triggerOnSource as boolean) ?? true}
            onchange={(e) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              args.triggerOnSource = (e.currentTarget as HTMLInputElement).checked;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
          />
          <span>Trigger on source records (created on this FSR appliance).</span>
        </label>
        <label class="flex items-center gap-2">
          <input
            type="checkbox"
            checked={(a.triggerOnReplicate as boolean) ?? false}
            onchange={(e) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              args.triggerOnReplicate = (e.currentTarget as HTMLInputElement).checked;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
          />
          <span>Trigger on replicated records (received from a tenant / sibling node).</span>
        </label>
        <label class="flex items-center gap-2">
          <input
            type="checkbox"
            checked={(a.__triggerLimit as boolean) ?? false}
            onchange={(e) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              args.__triggerLimit = (e.currentTarget as HTMLInputElement).checked;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
          />
          <span title="Caps how many times this trigger can refire on the same record per minute.">Throttle (<code>__triggerLimit</code>) — rate-limit re-fires on the same record.</span>
        </label>
      </div>
    </details>
  {/if}

{:else if node.family === 'record_crud'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const isFind = node.type === 'find_record'}
  {@const isDelete = node.type === 'delete_record'}
  {@const isWrite = node.type === 'create_record' || node.type === 'insert_record' || node.type === 'update_record'}
  {@const isBulk = node.type === 'ingest_bulk_feed'}
  {@const queryGroup = {
    logic: (((a.query as Record<string, unknown>)?.logic as 'AND' | 'OR') ?? 'AND'),
    filters: ((a.query as Record<string, unknown>)?.filters as any[]) ?? []
  }}
  {@const moduleVal = bareModule(
    (a.module as string | undefined) ??
    (a.collection as string | undefined)?.replace(/^\/api\/(?:3|ingest-feeds)\//, '')
  )}
  {@const resourceObj = (a.resource as Record<string, unknown> | undefined) ?? {}}
  {@const fieldOps = (a.fieldOperation as Record<string, unknown> | undefined) ?? {}}

  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
    {isFind ? 'Find records' : isDelete ? 'Delete record' : isBulk ? 'Ingest bulk feed' : 'Write record'}
  </div>

  <label class="mt-2 block">
    <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Module</span>
    <input
      type="text"
      list="fsrpb-modules-list"
      value={moduleVal}
      placeholder={modulesLoaded && allModules.length ? 'pick from list…' : 'alerts | incidents | tasks | indicators | …'}
      oninput={(e) => {
        const v = (e.currentTarget as HTMLInputElement).value;
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        if (isFind) {
          // FindRecords keeps `module: '<name>?$limit=30'` per corpus.
          args.module = v ? `${v}?$limit=30` : '';
        } else if (isBulk) {
          args.collection = v ? `/api/ingest-feeds/${v}` : '';
        } else {
          args.collection = v ? `/api/3/${v}` : '';
        }
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
      class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
    />
    {#if !modulesLoaded && modulesLoading}
      <p class="mt-0.5 text-[10px] italic text-[var(--text-faint)]">loading modules…</p>
    {:else if modulesLoaded && allModules.length === 0}
      <p class="mt-0.5 text-[10px] italic text-[var(--text-faint)]">
        Module catalog empty — run <code>fsrpb train</code> to populate.
      </p>
    {/if}
  </label>

  {#if isFind}
    {@const queryObj = (a.query as Record<string, unknown> | undefined) ?? {}}
    {@const recordLimit = (queryObj.limit as number | undefined) ?? 30}
    {@const selectFields = (queryObj.__selectFields as string[] | undefined) ?? []}
    {@const sortRows = (queryObj.sort as Array<Record<string, unknown>> | undefined) ?? []}
    {@const fieldList = fieldsByModule[moduleVal] ?? []}
    <!--
      "Include Correlated Records" + "Maximum correlated records limit"
      live in the `module:` URL query string, NOT as top-level args
      (verified against the trained corpus: 61 rows with
      `$relationships=true`, 4 with `$fsr_max_relation_count=N`).
      Parse them back out for display.
    -->
    {@const moduleRaw = (a.module as string | undefined) ?? ''}
    {@const moduleParams = (() => {
      const q = moduleRaw.indexOf('?');
      if (q < 0) return new URLSearchParams();
      try { return new URLSearchParams(moduleRaw.slice(q + 1)); }
      catch { return new URLSearchParams(); }
    })()}
    {@const includeCorrelated = moduleParams.get('$relationships') === 'true'}
    {@const correlatedLimit = (() => {
      const v = moduleParams.get('$fsr_max_relation_count');
      const n = v ? Number(v) : NaN;
      return Number.isFinite(n) && n > 0 ? n : 100;
    })()}
    {@const writeModuleParams = (mut: (p: URLSearchParams) => void) => {
      const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
      const cur = (args.module as string | undefined) ?? '';
      const q = cur.indexOf('?');
      const bare = q < 0 ? cur : cur.slice(0, q);
      const params = new URLSearchParams(q < 0 ? '' : cur.slice(q + 1));
      mut(params);
      const qs = params.toString();
      args.module = qs ? `${bare}?${qs}` : bare;
      visualStore.setArgs(playbookIdx, node.id, args);
    }}

    <label class="mt-3 block">
      <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Record limit</span>
      <input
        type="number"
        min="1"
        max="5000"
        value={recordLimit}
        oninput={(e) => {
          const v = Number((e.currentTarget as HTMLInputElement).value);
          if (!Number.isFinite(v) || v <= 0) return;
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          const q = { ...((args.query as Record<string, unknown>) ?? {}) };
          q.limit = v;
          args.query = q;
          // Mirror into the `module:` URL while preserving any other
          // params the FSR designer set (`$relationships`,
          // `$fsr_max_relation_count`, etc.).
          const cur = (args.module as string | undefined) ?? '';
          const idx = cur.indexOf('?');
          const bare = idx < 0 ? cur : cur.slice(0, idx);
          const params = new URLSearchParams(idx < 0 ? '' : cur.slice(idx + 1));
          params.set('$limit', String(v));
          args.module = bare ? `${bare}?${params.toString()}` : '';
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
        class="mt-1 block w-32 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
      />
      <p class="mt-0.5 text-[10px] text-[var(--text-faint)]">Max records returned. FSR caps at 5000 per QUERY_API.md.</p>
    </label>

    <div class="mt-3 space-y-2 text-[11px] text-[var(--text-muted)]">
      <label class="flex items-center gap-2">
        <input
          type="checkbox"
          checked={includeCorrelated}
          onchange={(e) => {
            const on = (e.currentTarget as HTMLInputElement).checked;
            writeModuleParams((p) => {
              if (on) p.set('$relationships', 'true');
              else { p.delete('$relationships'); p.delete('$fsr_max_relation_count'); }
            });
          }}
        />
        <span title="Pull records linked to the matched ones (assets, comments, tasks, …) inline.">Include correlated records</span>
      </label>
      {#if includeCorrelated}
        <label class="ml-6 flex items-center gap-2">
          <span class="text-[10px] uppercase tracking-wider">Max correlated</span>
          <input
            type="number"
            min="1"
            value={correlatedLimit}
            oninput={(e) => {
              const v = Number((e.currentTarget as HTMLInputElement).value);
              writeModuleParams((p) => {
                if (Number.isFinite(v) && v > 0) p.set('$fsr_max_relation_count', String(v));
                else p.delete('$fsr_max_relation_count');
              });
            }}
            class="w-24 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 font-mono text-[11px]"
          />
        </label>
      {/if}
    </div>

    <details class="mt-3 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <summary class="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Limit output ({selectFields.length || 'all fields'})
      </summary>
      <p class="mt-1 text-[10px] text-[var(--text-faint)]">
        When set, only these fields come back. Saves payload + speeds
        the fetch on wide modules.
      </p>
      {#if selectFields.length > 0}
        <div class="mt-2 flex flex-wrap gap-1">
          {#each selectFields as f, idx (f + '|' + idx)}
            <span class="inline-flex items-center gap-1 rounded-full bg-[var(--brand)]/20 px-2 py-0.5 text-[11px] text-[var(--brand)]">
              {f}
              <button
                type="button"
                aria-label={`remove ${f}`}
                class="text-[10px] hover:text-rose-600"
                onclick={() => {
                  const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                  const q = { ...((args.query as Record<string, unknown>) ?? {}) };
                  q.__selectFields = (selectFields).filter((_, i) => i !== idx);
                  args.query = q;
                  visualStore.setArgs(playbookIdx, node.id, args);
                }}
              >×</button>
            </span>
          {/each}
        </div>
      {/if}
      <select
        aria-label="Add output field"
        value=""
        onchange={(e) => {
          const v = (e.currentTarget as HTMLSelectElement).value;
          if (!v) return;
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          const q = { ...((args.query as Record<string, unknown>) ?? {}) };
          const next = [...selectFields];
          if (!next.includes(v)) next.push(v);
          q.__selectFields = next;
          args.query = q;
          visualStore.setArgs(playbookIdx, node.id, args);
          (e.currentTarget as HTMLSelectElement).value = '';
        }}
        class="mt-2 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
      >
        <option value="">+ add field…</option>
        {#each fieldList.filter((f) => !selectFields.includes(f.name)) as f (f.name)}
          <option value={f.name}>{f.name}{f.title ? ` — ${f.title}` : ''}</option>
        {/each}
      </select>
    </details>

    <details class="mt-3 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <summary class="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Sort by ({sortRows.length})
      </summary>
      <ul class="mt-2 space-y-1">
        {#each sortRows as row, idx (idx)}
          {@const sortMeta = fieldList.find((x) => x.name === row.field)}
          <li class="flex items-center gap-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1.5 py-1">
            <select
              aria-label="Sort field"
              value={(row.field as string) ?? ''}
              onchange={(e) => {
                const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                const q = { ...((args.query as Record<string, unknown>) ?? {}) };
                const next = sortRows.slice();
                const v = (e.currentTarget as HTMLSelectElement).value;
                const m = fieldList.find((x) => x.name === v);
                next[idx] = {
                  ...next[idx],
                  field: v,
                  _fieldName: v,
                  _fieldTitle: m?.title ?? v
                };
                q.sort = next;
                args.query = q;
                visualStore.setArgs(playbookIdx, node.id, args);
              }}
              class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1 py-0.5 font-mono text-[11px]"
            >
              <option value="">— pick field —</option>
              {#each fieldList as f (f.name)}
                <option value={f.name}>{f.name}</option>
              {/each}
            </select>
            <select
              aria-label="Sort direction"
              value={(row.direction as string) ?? 'ASC'}
              onchange={(e) => {
                const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                const q = { ...((args.query as Record<string, unknown>) ?? {}) };
                const next = sortRows.slice();
                next[idx] = { ...next[idx], direction: (e.currentTarget as HTMLSelectElement).value };
                q.sort = next;
                args.query = q;
                visualStore.setArgs(playbookIdx, node.id, args);
              }}
              class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1 py-0.5 font-mono text-[11px]"
            >
              <option value="ASC">ascending</option>
              <option value="DESC">descending</option>
            </select>
            <button
              type="button"
              aria-label="Remove sort row"
              class="text-[10px] text-rose-600 hover:text-rose-700"
              onclick={() => {
                const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                const q = { ...((args.query as Record<string, unknown>) ?? {}) };
                q.sort = sortRows.filter((_, i) => i !== idx);
                args.query = q;
                visualStore.setArgs(playbookIdx, node.id, args);
              }}
            >×</button>
          </li>
        {/each}
      </ul>
      <button
        type="button"
        class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-[11px] font-medium hover:bg-[var(--bg-elev)]"
        onclick={() => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          const q = { ...((args.query as Record<string, unknown>) ?? {}) };
          const next = sortRows.slice();
          next.push({ field: '', direction: 'ASC' });
          q.sort = next;
          args.query = q;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      >+ Sort row</button>
    </details>

    <div class="mt-3">
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Query filter</div>
      <p class="mb-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[11px] italic text-[var(--text-default)]">
        {summarizeFind(moduleVal, queryGroup)}
      </p>
      <FilterTreeEditor
        group={queryGroup}
        fields={fieldsByModule[moduleVal] ?? []}
        moduleNames={allModules.map((m) => m.name)}
        node={node}
        playbook={playbook ?? null}
        getRelatedFields={(m) => {
          // Trigger the lazy-load for the related module if we
          // haven't fetched it yet; return whatever's cached so far
          // (empty array on first call → the picker shows
          // "loading…" until the fetch resolves and Svelte's $state
          // reactivity re-renders).
          void ensureFieldsLoaded(m);
          return fieldsByModule[m] ?? [];
        }}
        onChange={(next) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          const prev = (args.query as Record<string, unknown> | undefined) ?? {};
          args.query = {
            ...prev,
            logic: next.logic,
            filters: next.filters,
            limit: (prev.limit as number) ?? 30,
            sort: (prev.sort as unknown[]) ?? []
          };
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
      />
    </div>
  {/if}

  {#if isBulk}
    {@const feRaw = (a.for_each as Record<string, unknown> | undefined) ?? {}}
    {@const feItem = (feRaw.item as string | undefined) ?? ''}
    {@const feBatch = (feRaw.batch_size as number | undefined) ?? 100}
    {@const feParallel = (feRaw.parallel as boolean | undefined) ?? false}
    {@const whenExpr = (a.when as string | undefined) ?? ''}
    {@const updateForEach = (patch: Record<string, unknown>) => {
      const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
      const fe = { ...((args.for_each as Record<string, unknown>) ?? {}), ...patch };
      // `__bulk: true` is the marker FSR uses to route this for_each
      // through the Ingest Bulk Feed step engine instead of regular
      // looped Create. Keep it asserted whenever we touch the block.
      fe.__bulk = true;
      if (fe.condition === undefined) fe.condition = '';
      args.for_each = fe;
      visualStore.setArgs(playbookIdx, node.id, args);
    }}
    {@const feItemFocus = attachVarPaneFocus({
      label: `${node.name || 'step'} · for_each.item`,
      insert: (snippet) => updateForEach({ item: feItem ? `${feItem} ${snippet}` : snippet })
    })}
    {@const whenFocus = attachVarPaneFocus({
      label: `${node.name || 'step'} · when`,
      insert: (snippet) => {
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        args.when = whenExpr ? `${whenExpr} ${snippet}` : snippet;
        visualStore.setArgs(playbookIdx, node.id, args);
      }
    })}

    <div class="mt-3 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Feed source
      </div>
      <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
        Iterate over a list expression — each element becomes
        <code class="font-mono">vars.item</code>. The bulk-feed step
        bypasses on-create triggers (intentional: ingestion is
        firehose-rate, triggers fire post-hoc on enrichment).
      </p>

      <label class="mt-2 block">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Item iterable</span>
        <div class="mt-1 flex items-center gap-1">
          <input
            type="text"
            value={feItem}
            placeholder={'{{ vars.steps.Fetch_Feed.data }}'}
            oninput={(e) => updateForEach({ item: (e.currentTarget as HTMLInputElement).value })}
            onfocus={feItemFocus.onfocus}
            onblur={feItemFocus.onblur}
            class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
          />
          <VarPathPicker
            {node}
            {playbook}
            shapes={jinjaShapesStore.shapes}
            wrap={true}
            onInsert={(snippet) => updateForEach({
              item: feItem ? `${feItem} ${snippet}` : snippet
            })}
          />
        </div>
      </label>

      <div class="mt-3 grid grid-cols-2 gap-3">
        <label class="block">
          <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Batch size</span>
          <input
            type="number"
            min="1"
            value={feBatch}
            oninput={(e) => {
              const v = Number((e.currentTarget as HTMLInputElement).value);
              if (Number.isFinite(v) && v > 0) updateForEach({ batch_size: v });
            }}
            class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
          />
        </label>
        <label class="flex items-end gap-2 pb-1 text-[11px] text-[var(--text-muted)]">
          <input
            type="checkbox"
            checked={feParallel}
            onchange={(e) => updateForEach({ parallel: (e.currentTarget as HTMLInputElement).checked })}
          />
          <span title="Run batches concurrently — speeds up wide ingest at the cost of ordering guarantees.">parallel</span>
        </label>
      </div>

      <label class="mt-3 block">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Skip-if predicate (when)</span>
        <div class="mt-1 flex items-center gap-1">
          <input
            type="text"
            value={whenExpr}
            placeholder={'{{ vars.data | length > 0 }}'}
            oninput={(e) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              const v = (e.currentTarget as HTMLInputElement).value;
              if (v) args.when = v; else delete args.when;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
            onfocus={whenFocus.onfocus}
            onblur={whenFocus.onblur}
            class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
          />
          <VarPathPicker
            {node}
            {playbook}
            shapes={jinjaShapesStore.shapes}
            wrap={true}
            onInsert={(snippet) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              args.when = whenExpr ? `${whenExpr} ${snippet}` : snippet;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
          />
        </div>
        <p class="mt-0.5 text-[10px] text-[var(--text-faint)]">
          Whole step is skipped when this evaluates falsy. Common pattern: gate on
          <code class="font-mono">{'vars.data | length > 0'}</code> so an empty feed doesn't churn.
        </p>
      </label>
    </div>
  {/if}

  {#if isWrite || isBulk}
    <div class="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-[var(--text-muted)]">
      {#if node.type === 'update_record'}
        <label class="flex items-center gap-1">
          <span>operation</span>
          <select
            value={(a.operation as string) ?? 'Overwrite'}
            onchange={(e) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              args.operation = (e.currentTarget as HTMLSelectElement).value;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
            class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1 py-0.5 text-[11px]"
          >
            <option value="Overwrite">Overwrite</option>
            <option value="Append">Append</option>
            <option value="Replace">Replace</option>
          </select>
        </label>
      {/if}
      {#if !isBulk}
        <label class="flex items-center gap-1">
          <input
            type="checkbox"
            checked={(a.__bulk as boolean) ?? false}
            onchange={(e) => {
              const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
              args.__bulk = (e.currentTarget as HTMLInputElement).checked;
              visualStore.setArgs(playbookIdx, node.id, args);
            }}
          />
          <span title="Batches the create — does NOT skip on-create triggers; use Ingest Bulk Feed for that.">__bulk</span>
        </label>
      {/if}
    </div>

    {@const writeFieldList = fieldsByModule[moduleVal] ?? []}
    {@const writeFieldByName = Object.fromEntries(writeFieldList.map((f) => [f.name, f]))}
    {@const setFieldNames = Object.keys(resourceObj)}
    {@const unsetFields = writeFieldList.filter((f) => !setFieldNames.includes(f.name))}
    {@const parsePicklistOptions = (raw: string | null | undefined): string[] => {
      if (!raw) return [];
      try { const v = JSON.parse(raw); return Array.isArray(v) ? v.map(String) : []; }
      catch { return []; }
    }}
    {@const writeField = (name: string, value: unknown) => {
      const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
      const r = { ...((args.resource as Record<string, unknown>) ?? {}) };
      if (value === undefined || value === '') delete r[name]; else r[name] = value;
      args.resource = r;
      visualStore.setArgs(playbookIdx, node.id, args);
    }}
    {@const removeField = (name: string) => {
      const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
      const r = { ...((args.resource as Record<string, unknown>) ?? {}) };
      delete r[name];
      args.resource = r;
      const fo = { ...((args.fieldOperation as Record<string, unknown>) ?? {}) };
      delete fo[name];
      args.fieldOperation = fo;
      visualStore.setArgs(playbookIdx, node.id, args);
    }}

    <div class="mt-3">
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Fields</div>
      {#if isBulk}
        <p class="mb-1 text-[10px] text-[var(--text-faint)]">
          Each batch row maps the iterable element via
          <code class="font-mono">{'{{ vars.item.<key> }}'}</code>.
        </p>
      {/if}
      {#if setFieldNames.length === 0}
        <p class="text-[11px] italic text-[var(--text-faint)]">No fields set. Pick one below to start writing.</p>
      {:else}
        <ul class="space-y-1">
          {#each setFieldNames as k (k)}
            {@const v = resourceObj[k]}
            {@const fieldMeta = writeFieldByName[k]}
            {@const isPicklist = fieldMeta?.type === 'picklists'}
            {@const isBool = fieldMeta?.type === 'checkbox' || fieldMeta?.type === 'boolean'}
            {@const isNumber = fieldMeta?.type === 'integer' || fieldMeta?.type === 'decimal' || fieldMeta?.type === 'number'}
            {@const isDate = fieldMeta?.type === 'datetime' || fieldMeta?.type === 'date'}
            {@const isRel = !!fieldMeta?.type && (fieldMeta.type === 'lookup' || fieldMeta.type === 'manyToOne' || fieldMeta.type === 'manyToMany' || fieldMeta.type === 'oneToMany' || allModules.some((m) => m.name === fieldMeta.type))}
            {@const picklistVals = isPicklist ? parsePicklistOptions(fieldMeta?.picklist_options ?? null) : []}
            <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
              <div class="flex items-baseline gap-2">
                <span class="font-mono text-[11px] font-semibold text-[var(--text-default)]">{k}</span>
                {#if fieldMeta?.title}<span class="text-[10px] text-[var(--text-muted)]">{fieldMeta.title}</span>{/if}
                <span class="text-[10px] text-[var(--text-faint)]">{fieldMeta?.type ?? 'unknown'}</span>
                <select
                  aria-label={`fieldOperation ${k}`}
                  value={(fieldOps[k] as string | undefined) ?? ''}
                  onchange={(e) => {
                    const fv = (e.currentTarget as HTMLSelectElement).value;
                    const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
                    const fo = { ...((args.fieldOperation as Record<string, unknown>) ?? {}) };
                    if (fv) fo[k] = fv; else delete fo[k];
                    args.fieldOperation = fo;
                    visualStore.setArgs(playbookIdx, node.id, args);
                  }}
                  class="ml-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-1 py-0.5 text-[10px] text-[var(--text-muted)]"
                  title="Per-field write strategy (overrides top-level operation)"
                >
                  <option value="">(inherit)</option>
                  <option value="Overwrite">Overwrite</option>
                  <option value="Append">Append</option>
                  <option value="Replace">Replace</option>
                </select>
                <button
                  type="button"
                  class="text-[10px] text-rose-600 hover:text-rose-700"
                  aria-label={`Remove field ${k}`}
                  onclick={() => removeField(k)}
                >×</button>
              </div>
              {#if isPicklist && picklistVals.length > 0}
                <select
                  aria-label={`value of ${k}`}
                  value={typeof v === 'string' ? v : ''}
                  onchange={(e) => writeField(k, (e.currentTarget as HTMLSelectElement).value)}
                  class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
                >
                  <option value="">— pick value —</option>
                  {#each picklistVals as pv}
                    <option value={pv}>{pv}</option>
                  {/each}
                </select>
                <p class="mt-0.5 text-[10px] text-[var(--text-faint)]">
                  Stored as the friendly value; resolver maps to the picklist IRI at compile time.
                </p>
              {:else if isBool}
                <label class="mt-1 flex items-center gap-2 text-[11px]">
                  <input
                    type="checkbox"
                    checked={v === true || v === 'true'}
                    onchange={(e) => writeField(k, (e.currentTarget as HTMLInputElement).checked)}
                  />
                  <span class="text-[var(--text-muted)]">{v === true || v === 'true' ? 'true' : 'false'}</span>
                </label>
              {:else if isNumber}
                <input
                  type="number"
                  aria-label={`value of ${k}`}
                  value={v == null ? '' : String(v)}
                  oninput={(e) => writeField(k, (e.currentTarget as HTMLInputElement).value)}
                  class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
                />
              {:else if isDate}
                <input
                  type="text"
                  aria-label={`value of ${k}`}
                  value={typeof v === 'string' ? v : ''}
                  placeholder={'ISO 8601 or {{ now }} / epoch ms'}
                  oninput={(e) => writeField(k, (e.currentTarget as HTMLInputElement).value)}
                  class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
                />
              {:else if isRel}
                {@const relTarget = (fieldMeta?.type && allModules.some((m) => m.name === fieldMeta!.type))
                  ? fieldMeta!.type
                  : ''}
                <div class="mt-1">
                  {#if relTarget}
                    <RelationPicker
                      module={relTarget}
                      value={typeof v === 'string' ? v : JSON.stringify(v ?? '')}
                      onChange={(next) => writeField(k, next)}
                      placeholder={`/api/3/${relTarget}/<uuid>  or  {{ vars.steps.X[0]['@id'] }}`}
                      ariaLabel={`pick ${relTarget} record for ${k}`}
                    />
                  {:else}
                    <input
                      type="text"
                      aria-label={`value of ${k}`}
                      value={typeof v === 'string' ? v : JSON.stringify(v ?? '')}
                      placeholder={`/api/3/${fieldMeta?.type ?? '<module>'}/<uuid>  or  {{ vars.steps.X[0]['@id'] }}`}
                      oninput={(e) => writeField(k, (e.currentTarget as HTMLInputElement).value)}
                      class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
                    />
                  {/if}
                </div>
                <p class="mt-0.5 text-[10px] text-[var(--text-faint)]">
                  Relation to <code>{fieldMeta?.type}</code> — pick a record or paste an IRI / Jinja expression.
                </p>
              {:else}
                <textarea
                  rows="1"
                  aria-label={`value of ${k}`}
                  value={typeof v === 'string' ? v : JSON.stringify(v ?? '')}
                  placeholder={fieldMeta?.tooltip ?? ''}
                  oninput={(e) => writeField(k, (e.currentTarget as HTMLTextAreaElement).value)}
                  class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
                ></textarea>
              {/if}
              {#if fieldMeta?.tooltip && !isRel}
                <p class="mt-0.5 text-[10px] text-[var(--text-faint)]">{fieldMeta.tooltip}</p>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
      {#if writeFieldList.length > 0}
        <select
          aria-label="Add field"
          value=""
          onchange={(e) => {
            const v = (e.currentTarget as HTMLSelectElement).value;
            if (!v) return;
            const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
            const r = { ...((args.resource as Record<string, unknown>) ?? {}) };
            if (!(v in r)) r[v] = '';
            args.resource = r;
            visualStore.setArgs(playbookIdx, node.id, args);
            (e.currentTarget as HTMLSelectElement).value = '';
          }}
          class="mt-2 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
        >
          <option value="">+ Add field…</option>
          {#each unsetFields as f (f.name)}
            <option value={f.name}>
              {f.name}{f.title ? ` — ${f.title}` : ''} ({f.type}){f.required ? ' · required' : ''}
            </option>
          {/each}
        </select>
      {:else}
        <!-- No catalog (module not picked yet, or trained store is
             empty). Fall back to a plain "+ Add field" button so users
             can still author writes via free-text keys. -->
        <button
          type="button"
          class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-[11px] font-medium hover:bg-[var(--bg-canvas)]"
          onclick={() => {
            const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
            const r = { ...((args.resource as Record<string, unknown>) ?? {}) };
            let i = 1; let nm = 'newField';
            while (nm in r) { i += 1; nm = `newField_${i}`; }
            r[nm] = '';
            args.resource = r;
            visualStore.setArgs(playbookIdx, node.id, args);
          }}
        >+ Add field (free text)</button>
      {/if}
    </div>
  {/if}

  {#if isDelete}
    <p class="mt-3 text-[11px] text-[var(--text-faint)]">
      Delete steps use the upstream record reference — usually
      <code class="font-mono">{`{{ vars.input.records[0]['@id'] }}`}</code>
      or a Find step's result. Author the IRI via the Raw tab; no
      additional config is needed here.
    </p>
  {/if}

{:else if node.type === 'delay'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const canon = (a.delay ?? {}) as Record<string, unknown>}
  {@const v = (k: string) => {
    // Friendly form (top-level) wins; fall back to canonical `delay.{…}`.
    const top = a[k];
    if (top !== undefined && top !== null && top !== '') return String(top);
    const c = canon[k];
    if (c !== undefined && c !== null && c !== '') return String(c);
    return '';
  }}
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Delay</div>
  <p class="mt-1 text-[11px] text-[var(--text-faint)]">Pause the playbook for the configured duration. Any combination of fields is summed.</p>
  <div class="mt-2 grid grid-cols-2 gap-2">
    {#each ['days', 'hours', 'minutes', 'seconds'] as unit}
      <label class="block">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">{unit}</span>
        <input
          type="number"
          min="0"
          value={v(unit)}
          oninput={(e) => {
            const raw = (e.currentTarget as HTMLInputElement).value;
            const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
            // Write the friendly form; resolver expands to canonical at compile time.
            // Drop the canonical `delay`/`type`/`rule` so we don't end up with two
            // sources of truth in the YAML.
            delete args.delay;
            delete args.type;
            delete args.rule;
            if (raw === '' || raw === '0') delete args[unit];
            else args[unit] = Number(raw);
            visualStore.setArgs(playbookIdx, node.id, args);
          }}
          class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
        />
      </label>
    {/each}
  </div>
{:else if node.type === 'raise_exception' || node.type === 'terminate' || node.type === 'assert'}
  {@const a = (node.arguments ?? {}) as Record<string, unknown>}
  {@const labels: Record<string, string> = {
    raise_exception: 'Raise an exception with a descriptive message. Halts the playbook and surfaces in the run log.',
    terminate: 'Terminate the current playbook run. Use sparingly — most flows should end on a normal terminal step.',
    assert: 'Fail the run when the predicate evaluates falsy. Useful for guarding preconditions.'
  }}
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
    {node.type.replace('_', ' ')}
  </div>
  <p class="mt-1 text-[11px] text-[var(--text-faint)]">{labels[node.type]}</p>
  {#if node.type === 'assert'}
    <label class="mt-2 block">
      <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Predicate</span>
      <input
        type="text"
        value={(a.condition as string) ?? (a.expression as string) ?? ''}
        placeholder={'{{ vars.steps.foo.status == "ok" }}' /* literal Jinja */}
        oninput={(e) => {
          const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
          args.condition = (e.currentTarget as HTMLInputElement).value;
          delete args.expression;
          visualStore.setArgs(playbookIdx, node.id, args);
        }}
        class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
      />
    </label>
  {/if}
  <label class="mt-2 block">
    <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Message</span>
    <textarea
      rows="2"
      value={(a.message as string) ?? (a.reason as string) ?? ''}
      placeholder="Describe why the run is failing — surfaces in logs."
      oninput={(e) => {
        const args = deepClone(node.arguments ?? {}) as Record<string, unknown>;
        args.message = (e.currentTarget as HTMLTextAreaElement).value;
        delete args.reason;
        visualStore.setArgs(playbookIdx, node.id, args);
      }}
      class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
    ></textarea>
  </label>
{:else if node.type === 'set_variable'}
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
    Variables
  </div>
  {#if varList.length === 0}
    <p class="mt-1 text-xs italic text-[var(--text-faint)]">No variables defined yet.</p>
  {:else}
    <ul class="mt-1 space-y-2">
      {#each varList as v (v.name)}
        {@const setVarFocus = attachVarPaneFocus({
          label: `${node.name || 'set_variable'} · ${v.name}`,
          insert: (snippet) => {
            const cur = typeof v.value === 'string' ? v.value : JSON.stringify(v.value);
            setVar(v.name, cur ? `${cur} ${snippet}` : snippet);
          }
        })}
        <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
          <div class="flex items-baseline justify-between text-xs">
            <span class="font-mono font-semibold text-[var(--text-default)]">{v.name}</span>
            <div class="flex items-center gap-1">
              <VarPathPicker
                {node}
                {playbook}
                shapes={jinjaShapesStore.shapes}
                wrap={true}
                onInsert={(snippet) => {
                  const cur = typeof v.value === 'string'
                    ? v.value
                    : JSON.stringify(v.value);
                  setVar(v.name, cur ? `${cur} ${snippet}` : snippet);
                }}
              />
              <button
                type="button"
                aria-label={`Remove variable ${v.name}`}
                class="text-[10px] text-rose-600 hover:text-rose-700"
                onclick={() => removeVar(v.name)}
              >×</button>
            </div>
          </div>
          <!-- Monaco-backed value editor: syntax highlighting + the same
               {{ vars.* }} autocomplete + hover the main YAML editor has
               (Jinja path completion is registered globally on first
               YAML editor mount via ensureYamlSupport). -->
          <div class="mt-1">
            <MonacoCode
              value={typeof v.value === 'string' ? v.value : JSON.stringify(v.value)}
              language="jinja"
              compact={true}
              autoGrow={true}
              height="2.5rem"
              autoGrowMaxPx={280}
              placeholder={'{{ vars.input.records[0].severity }}'}
              onInput={(s) => setVar(v.name, s)}
              onFocus={setVarFocus.onfocus}
              onBlur={setVarFocus.onblur}
            />
          </div>
          <!-- Live render: see what `{{ … }}` becomes against the current
               context (pinned sample, upstream set_variable outputs, etc.)
               while you type — no need to switch to the Verify tab. -->
          <JinjaInlinePreview value={typeof v.value === 'string' ? v.value : ''} />
        </li>
      {/each}
    </ul>
  {/if}
  <div class="mt-3 flex gap-2">
    <input
      type="text"
      placeholder="new variable name"
      bind:value={newVarName}
      class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
      onkeydown={(e) => { if (e.key === 'Enter') addVar(); }}
    />
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={addVar}
      disabled={!newVarName.trim()}
    >+ Add variable</button>
  </div>
{:else if node.family !== 'connector_op'}
  {#if node.type === 'decision' || node.type === 'manual_input'}
    <!-- Decision / manual_input args ARE the branches — and the
         Branches editor is folded in beneath this slot by
         StepInspector. Skip the raw JSON dump so the user sees the
         actual editor, not the raw blob it produces. -->
    <div class="text-[11px] italic text-[var(--text-faint)]">
      Edit branches below.
    </div>
  {:else}
    <div class="text-sm text-[var(--text-faint)]">
      Schema-driven editing is wired for connector ops + set_variable in Phase 3.
      For <code class="rounded bg-[var(--bg-elev)] px-1">{node.type}</code> steps,
      see the raw arguments below.
    </div>
    <pre class="mt-2 max-h-96 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.arguments, null, 2)}</pre>
  {/if}
{:else if !connector || !opName}
  <section class="mb-3 space-y-2">
    {#if connector}
      <div class="mb-2 flex items-center gap-3">
        <ConnectorIcon name={connector as string} size="lg" />
        <div class="text-sm font-medium text-[var(--text-default)]">{connector}</div>
      </div>
    {/if}
    <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Connector</div>
    <ConnectorPicker
      value={(connector as string) ?? ''}
      placeholder="e.g. jira"
      ariaLabel="Connector"
      onCommit={(v) => setConnectorField('connector', v)}
    />
    {#if connector}
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Configuration</div>
      {#if configsLoading}
        <div class="text-[11px] italic text-[var(--text-faint)]">loading…</div>
      {:else if configurations.length === 0}
        <div class="text-[11px] italic text-[var(--text-faint)]">
          No configurations on the live FSR for {connector}. Defaults will be used.
        </div>
      {:else}
        <select
          aria-label="Configuration"
          value={configName}
          onchange={(e) => setConfig((e.currentTarget as HTMLSelectElement).value)}
          class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
        >
          <option value="">(default)</option>
          {#each configurations as cfg (cfg.config_id)}
            <option value={cfg.name}>{cfg.name}{cfg.default ? ' · default' : ''}</option>
          {/each}
        </select>
      {/if}
    {/if}
    <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Operation</div>
    <OperationPicker
      connector={(connector as string) ?? ''}
      value={(opName as string) ?? ''}
      onCommit={(v) => setConnectorField('operation', v)}
    />
  </section>
{:else if loading}
  <div class="text-sm text-[var(--text-faint)]">Loading schema for {connector}:{opName}…</div>
{:else if loadError}
  <div class="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-800">{loadError}</div>
{:else if schema && schema.ok === false}
  <div class="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-900">
    {schema.message}
    {#if schema.suggestions}
      <ul class="mt-1 list-disc pl-4">
        {#each schema.suggestions as s}<li>{s}</li>{/each}
      </ul>
    {/if}
  </div>
{:else if schema}
  <header class="mb-3 space-y-2">
    <div class="flex items-center gap-3">
      <ConnectorIcon name={connector ?? ''} size="lg" />
      <div class="text-xs font-semibold text-[var(--text-default)]">{connector} · {schema.op_name ?? opName}</div>
    </div>
    {#if schema.title}<div class="text-xs text-[var(--text-muted)]">{schema.title}</div>{/if}
    {#if schema.description}
      <p class="mt-1 text-xs leading-relaxed text-[var(--text-faint)]">{schema.description}</p>
    {/if}
    {#if configurations.length > 0}
      <div class="flex items-center gap-2">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Config</span>
        <select
          aria-label="Configuration"
          value={configName}
          onchange={(e) => setConfig((e.currentTarget as HTMLSelectElement).value)}
          class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
        >
          <option value="">(default)</option>
          {#each configurations as cfg (cfg.config_id)}
            <option value={cfg.name}>{cfg.name}{cfg.default ? ' · default' : ''}</option>
          {/each}
        </select>
      </div>
    {/if}
    <details class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <summary class="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Change connector / operation</summary>
      <div class="mt-2 space-y-1">
        <ConnectorPicker
          value={(connector as string) ?? ''}
          ariaLabel="Connector"
          onCommit={(v) => setConnectorField('connector', v)}
        />
        <OperationPicker
          connector={(connector as string) ?? ''}
          value={(opName as string) ?? ''}
          onCommit={(v) => setConnectorField('operation', v)}
        />
        <p class="text-[10px] text-[var(--text-faint)]">Switching the operation clears params (they're op-specific).</p>
      </div>
    </details>
  </header>

  {#snippet paramRow(p: Param)}
    {@const val = currentValue(p.param_name)}
    {@const opts = p.options_json}
    {@const isSelect = (p.type === 'select' || p.type === 'picklist') && Array.isArray(opts) && opts.length > 0}
    {@const isInt = p.type === 'integer' || p.type === 'number'}
    {@const isBool = p.type === 'checkbox' || p.type === 'boolean'}
    {@const showTitle = p.title && p.title.toLowerCase().replace(/[\s_]/g, '') !== p.param_name.toLowerCase().replace(/[\s_]/g, '')}
    {@const desc = p.description ?? p.tooltip}
    {@const longDesc = !!desc && desc.length > 80}
    <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1.5">
      <div class="flex items-baseline justify-between gap-2">
        <div class="min-w-0 flex-1">
          <span class="font-mono text-xs font-semibold text-[var(--text-default)]">{p.param_name}</span>
          {#if showTitle}<span class="ml-2 text-[11px] text-[var(--text-muted)]">{p.title}</span>{/if}
        </div>
        <span class="flex-shrink-0 text-[10px] text-[var(--text-faint)]">
          {p.type ?? 'text'}{p.required ? ' · required' : ''}
        </span>
      </div>
      {#if desc}
        {#if longDesc}
          <details class="mt-0.5 group">
            <summary class="cursor-pointer text-[10px] text-[var(--text-faint)] hover:text-[var(--text-muted)] line-clamp-1 group-open:line-clamp-none list-none">
              <span class="group-open:hidden">{desc.slice(0, 80)}…</span>
              <span class="hidden group-open:inline">{desc}</span>
            </summary>
          </details>
        {:else}
          <div class="mt-0.5 text-[10px] text-[var(--text-faint)]">{desc}</div>
        {/if}
      {/if}
      {#if isSelect}
        {@const dflt = normalizeDefault(p.default_value)}
        {@const hasDefault = dflt !== undefined && opts.includes(dflt)}
        {@const selectedVal = val !== undefined && val !== '' ? String(val) : (hasDefault ? dflt! : '')}
        <select
          class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
          value={selectedVal}
          onchange={(e) => setParam(p.param_name, (e.currentTarget as HTMLSelectElement).value)}
        >
          {#if !hasDefault}
            <option value="">{dflt ? `(default: ${dflt})` : '<not set>'}</option>
          {/if}
          {#each opts as opt}
            <option value={opt}>{opt}{hasDefault && opt === dflt ? ' · default' : ''}</option>
          {/each}
        </select>
      {:else if isBool}
        <label class="mt-1 flex items-center gap-2 text-[11px]">
          <input
            type="checkbox"
            checked={val === true || val === 'true'}
            onchange={(e) => setParam(p.param_name, String((e.currentTarget as HTMLInputElement).checked))}
          />
          <span class="text-[var(--text-muted)]">{val === true || val === 'true' ? 'true' : 'false'}</span>
        </label>
      {:else if isInt}
        <input
          type="number"
          class="mt-1 block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
          placeholder={p.placeholder ?? '<not set>'}
          value={val === undefined ? '' : String(val)}
          oninput={(e) => setParam(p.param_name, (e.currentTarget as HTMLInputElement).value)}
        />
      {:else}
        {@const paramFocus = attachVarPaneFocus({
          label: `${node.name || 'connector'} · params.${p.param_name}`,
          insert: (snippet) => {
            const cur = typeof val === 'string' ? val : (val === undefined ? '' : String(val));
            setParam(p.param_name, cur ? `${cur} ${snippet}` : snippet);
          }
        })}
        <div class="mt-1 flex items-start gap-1">
          <textarea
            class="block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
            rows={typeof val === 'string' && val.length > 60 ? 3 : 1}
            placeholder={p.placeholder ?? (val === undefined ? '<not set>' : '')}
            value={val === undefined ? '' : preview(val)}
            oninput={(e) => setParam(p.param_name, (e.currentTarget as HTMLTextAreaElement).value)}
            onfocus={paramFocus.onfocus}
            onblur={(e) => {
              paramFocus.onblur();
              precheckPicklist(p.param_name, (e.currentTarget as HTMLTextAreaElement).value);
            }}
          ></textarea>
          <VarPathPicker
            {node}
            {playbook}
            wrap={true}
            onInsert={(snippet) => {
              const cur = typeof val === 'string' ? val : (val === undefined ? '' : String(val));
              setParam(p.param_name, cur ? `${cur} ${snippet}` : snippet);
            }}
          />
        </div>
      {/if}
      {#if picklistResults[p.param_name]?.length}
        <ul class="mt-1 space-y-1 text-[11px]">
          {#each picklistResults[p.param_name] as pm}
            <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1">
              <div class="flex items-center gap-2">
                <span class={pm.ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
                  {pm.ok ? '✓' : '⚠'}
                </span>
                <code class="font-mono">{pm.picklist}</code>
                <span class="text-[var(--text-faint)]">·</span>
                <code class="font-mono">{pm.value}</code>
              </div>
              {#if !pm.ok && pm.message}<p class="mt-0.5 text-[var(--text-muted)]">{pm.message}</p>{/if}
              {#if pm.suggestions && pm.suggestions.length}
                <p class="mt-0.5 text-[var(--text-faint)]">try: {pm.suggestions.slice(0, 4).join(', ')}</p>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </li>
  {/snippet}

  {#if visibleParams.length}
    <section class="mb-3">
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Parameters</div>
      <ul class="mt-1 space-y-2">
        {#each visibleParams as p (p.param_name)}{@render paramRow(p)}{/each}
      </ul>
    </section>
  {/if}

  {#if hiddenParams.length}
    <details class="mb-3 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <summary class="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Hidden ({hiddenParams.length}) — gated by other field values
      </summary>
      <ul class="mt-2 space-y-2">
        {#each hiddenParams as p (p.param_name)}
          <li class="text-[11px]">
            <div class="flex items-baseline justify-between gap-2">
              <span class="font-mono">{p.param_name}</span>
              <span class="text-[10px] text-[var(--text-faint)]">
                shown when
                {#if p.applies_when?.length}{p.applies_when.map((c) => `${c.parent}=${c.value}`).join(' or ')}
                {:else if p.parent_param_name}{p.parent_param_name}={p.condition_value}{/if}
              </span>
            </div>
          </li>
        {/each}
      </ul>
    </details>
  {/if}

  <section class="mb-3">
    <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Extra params (not in schema)</div>
    {#if extraParamEntries.length === 0}
      <p class="mt-1 text-[11px] italic text-[var(--text-faint)]">None.</p>
    {:else}
      <ul class="mt-1 space-y-2">
        {#each extraParamEntries as [k, v] (k)}
          <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
            <div class="flex items-baseline justify-between gap-2 text-xs">
              <input
                type="text"
                aria-label={`rename param ${k}`}
                value={k}
                onchange={(e) => renameParam(k, (e.currentTarget as HTMLInputElement).value)}
                class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 font-mono text-[11px]"
              />
              <button
                type="button"
                aria-label={`Remove param ${k}`}
                class="text-[10px] text-rose-600 hover:text-rose-700"
                onclick={() => removeParam(k)}
              >×</button>
            </div>
            <textarea
              class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
              rows="1"
              value={typeof v === 'string' ? v : JSON.stringify(v)}
              oninput={(e) => setParam(k, (e.currentTarget as HTMLTextAreaElement).value)}
            ></textarea>
          </li>
        {/each}
      </ul>
    {/if}
    <div class="mt-2 flex gap-2">
      <input
        type="text"
        placeholder="new param name"
        bind:value={newParamName}
        class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
        onkeydown={(e) => { if (e.key === 'Enter') addParam(); }}
      />
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
        onclick={addParam}
        disabled={!newParamName.trim()}
      >+ Add param</button>
    </div>
  </section>

  {#if schema.output_schema_json_keys && schema.output_schema_json_keys.length}
    <section>
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Output keys</div>
      <div class="mt-1 flex flex-wrap gap-1">
        {#each schema.output_schema_json_keys as k}
          <code class="rounded bg-[var(--bg-elev)] px-1.5 py-0.5 text-[11px]">{k}</code>
        {/each}
      </div>
    </section>
  {/if}
{/if}
