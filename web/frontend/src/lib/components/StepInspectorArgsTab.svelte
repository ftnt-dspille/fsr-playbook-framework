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

  type Props = { node: VisualNode; playbookIdx: number };
  let { node, playbookIdx }: Props = $props();

  type Param = {
    param_name: string;
    title?: string;
    type?: string;
    required?: number;
    description?: string;
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

  let connector = $derived(node.arguments?.connector as string | undefined);
  let opName = $derived(
    (node.arguments?.operation as string | undefined) ??
      (node.family === 'connector_op' ? node.type : undefined)
  );

  $effect(() => {
    if (node.family !== 'connector_op' || !connector || !opName) {
      schema = null;
      loadError = null;
      return;
    }
    loading = true;
    loadError = null;
    callMcpTool<Schema>('get_op_schema', { connector, op_name: opName, verbose: true })
      .then((r) => {
        if (r.ok) schema = r.result ?? null;
        else loadError = r.error ?? 'tool error';
      })
      .catch((e) => (loadError = (e as Error).message))
      .finally(() => (loading = false));
  });

  function currentValue(name: string): unknown {
    const params = node.arguments?.params as Record<string, unknown> | undefined;
    if (params && name in params) return params[name];
    return node.arguments?.[name];
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

  let varList = $derived((node.arguments?.arg_list as { name: string; value: unknown }[] | undefined) ?? []);
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
{:else if node.family !== 'connector_op'}
  <div class="text-sm text-[var(--text-faint)]">
    Schema-driven editing is wired for connector ops + set_variable in Phase 3.
    For <code class="rounded bg-[var(--bg-elev)] px-1">{node.type}</code> steps,
    see the raw arguments below.
  </div>
  <pre class="mt-2 max-h-96 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.arguments, null, 2)}</pre>
{:else if !connector || !opName}
  <div class="text-sm text-[var(--text-faint)]">
    This node has no <code>connector</code>/<code>operation</code> set yet.
  </div>
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
  <header class="mb-3">
    <div class="text-xs font-semibold text-[var(--text-default)]">{connector} · {schema.op_name ?? opName}</div>
    {#if schema.title}<div class="text-xs text-[var(--text-muted)]">{schema.title}</div>{/if}
    {#if schema.description}
      <p class="mt-1 text-xs leading-relaxed text-[var(--text-faint)]">{schema.description}</p>
    {/if}
  </header>

  {#if schema.params && schema.params.length}
    <section class="mb-3">
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Always shown</div>
      <ul class="mt-1 space-y-2">
        {#each schema.params as p}
          {@const val = currentValue(p.param_name)}
          <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
            <div class="flex items-baseline justify-between gap-2 text-xs">
              <span class="font-mono font-semibold text-[var(--text-default)]">{p.param_name}</span>
              <span class="text-[10px] text-[var(--text-faint)]">
                {p.type ?? 'text'}{p.required ? ' · required' : ''}
              </span>
            </div>
            {#if p.title}<div class="text-[11px] text-[var(--text-muted)]">{p.title}</div>{/if}
            <textarea
              class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
              rows={typeof val === 'string' && val.length > 60 ? 3 : 1}
              placeholder={val === undefined ? '<not set>' : ''}
              value={val === undefined ? '' : preview(val)}
              oninput={(e) => setParam(p.param_name, (e.currentTarget as HTMLTextAreaElement).value)}
            ></textarea>
            {#if p.applies_when && p.applies_when.length}
              <div class="mt-1 text-[10px] text-[var(--text-faint)]">
                shown when {p.applies_when.map((c) => `${c.parent}=${c.value}`).join(' or ')}
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

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
