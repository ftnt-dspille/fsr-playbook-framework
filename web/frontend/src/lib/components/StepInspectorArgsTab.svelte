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

  type Props = { node: VisualNode; playbookIdx: number };
  let { node, playbookIdx }: Props = $props();

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

  let schema: Schema | null = $state(null);
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

{#if node.type === 'set_variable'}
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
    Variables
  </div>
  {#if varList.length === 0}
    <p class="mt-1 text-xs italic text-[var(--text-faint)]">No variables defined yet.</p>
  {:else}
    <ul class="mt-1 space-y-2">
      {#each varList as v (v.name)}
        <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
          <div class="flex items-baseline justify-between text-xs">
            <span class="font-mono font-semibold text-[var(--text-default)]">{v.name}</span>
            <button
              type="button"
              aria-label={`Remove variable ${v.name}`}
              class="text-[10px] text-rose-600 hover:text-rose-700"
              onclick={() => removeVar(v.name)}
            >×</button>
          </div>
          <textarea
            class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
            rows="2"
            value={typeof v.value === 'string' ? v.value : JSON.stringify(v.value)}
            oninput={(e) => setVar(v.name, (e.currentTarget as HTMLTextAreaElement).value)}
          ></textarea>
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
  <div class="text-sm text-[var(--text-faint)]">
    Schema-driven editing is wired for connector ops + set_variable in Phase 3.
    For <code class="rounded bg-[var(--bg-elev)] px-1">{node.type}</code> steps,
    see the raw arguments below.
  </div>
  <pre class="mt-2 max-h-96 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.arguments, null, 2)}</pre>
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
        <textarea
          class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
          rows={typeof val === 'string' && val.length > 60 ? 3 : 1}
          placeholder={p.placeholder ?? (val === undefined ? '<not set>' : '')}
          value={val === undefined ? '' : preview(val)}
          oninput={(e) => setParam(p.param_name, (e.currentTarget as HTMLTextAreaElement).value)}
          onblur={(e) => precheckPicklist(p.param_name, (e.currentTarget as HTMLTextAreaElement).value)}
        ></textarea>
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
