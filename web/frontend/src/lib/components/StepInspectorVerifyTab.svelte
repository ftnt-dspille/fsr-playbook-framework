<script lang="ts">
  /**
   * Phase 4 Verify tab. 4.1 = Render button: walks every arg through
   * render_jinja and shows the resolved value inline. Later sub-phases
   * add Run (safe), Test step, Verification history, picklist precheck.
   */
  import type { VisualNode } from '../api';
  import { callMcpTool } from '../api';
  import { visualStore } from '../visualEditStore.svelte';

  type Props = { node: VisualNode };
  let { node }: Props = $props();

  type HistoryResult =
    | { kind: 'found'; status: string; method: string; ts: string; notes: string; count: number }
    | { kind: 'empty' }
    | { kind: 'error'; message: string };
  let historyBusy = $state(false);
  let historyResult: HistoryResult | null = $state(null);

  let historyKind = $derived(node.family === 'connector_op' ? 'operation' : 'step_type');
  let historyKey = $derived(
    node.family === 'connector_op'
      ? `${(node.arguments?.connector as string) ?? ''}:${(node.arguments?.operation as string) ?? ''}`
      : node.type
  );

  async function loadHistory() {
    historyBusy = true;
    historyResult = null;
    try {
      const res = await callMcpTool<Record<string, unknown>>('verification_status', {
        kind: historyKind,
        key: historyKey
      });
      const r = res.result ?? {};
      if (!res.ok) {
        historyResult = { kind: 'error', message: res.error ?? 'verification_status failed' };
      } else if (!r['found']) {
        historyResult = { kind: 'empty' };
      } else {
        historyResult = {
          kind: 'found',
          status: String(r['status'] ?? ''),
          method: String(r['method'] ?? ''),
          ts: String(r['ts'] ?? ''),
          notes: String(r['notes_excerpt'] ?? ''),
          count: Number(r['history_count'] ?? 0)
        };
      }
    } catch (e: any) {
      historyResult = { kind: 'error', message: String(e?.message ?? e) };
    } finally {
      historyBusy = false;
    }
  }

  type StepTestResult =
    | { kind: 'ok'; status: string; rendered: unknown; output: unknown; note: string }
    | { kind: 'error'; message: string };
  let stepTestBusy = $state(false);
  let stepTestResult: StepTestResult | null = $state(null);

  async function testStep() {
    const yaml = visualStore.state.graph?.source?.yaml;
    if (!yaml) {
      stepTestResult = { kind: 'error', message: 'no source YAML available' };
      return;
    }
    stepTestBusy = true;
    stepTestResult = null;
    try {
      const res = await callMcpTool<Record<string, unknown>>('step_test', {
        yaml_text: yaml,
        step_id: node.id
      });
      const r = res.result ?? {};
      if (!res.ok || r['ok'] === false && r['error']) {
        stepTestResult = { kind: 'error', message: res.error ?? String(r['error'] ?? 'step_test failed') };
      } else {
        stepTestResult = {
          kind: 'ok',
          status: String(r['status'] ?? 'rendered'),
          rendered: r['rendered_args'],
          output: r['output'],
          note: String(r['note'] ?? '')
        };
      }
    } catch (e: any) {
      stepTestResult = { kind: 'error', message: String(e?.message ?? e) };
    } finally {
      stepTestBusy = false;
    }
  }

  // Mirrors `_SAFE_NAME_PREFIXES` in python/mcp_server.py — kept local so
  // we can pre-grey the Run button without a round-trip. The server still
  // gates destructive ops via `requires_confirmation`, so this is just UX.
  const SAFE_PREFIXES = [
    'get_', 'list_', 'search_', 'fetch_', 'query_', 'check_',
    'describe_', 'lookup_', 'find_', 'read_', 'show_', 'view_'
  ];

  let connectorName = $derived(
    node.family === 'connector_op' ? (node.arguments?.connector as string | undefined) ?? null : null
  );
  let opName = $derived(
    node.family === 'connector_op' ? (node.arguments?.operation as string | undefined) ?? null : null
  );
  let opParams = $derived(
    node.family === 'connector_op' ? ((node.arguments?.params as Record<string, unknown>) ?? {}) : {}
  );
  let opIsSafe = $derived(
    !!opName && SAFE_PREFIXES.some((p) => opName!.toLowerCase().startsWith(p))
  );
  let runEnabled = $derived(node.family === 'connector_op' && !!connectorName && !!opName && opIsSafe);

  type RunResult =
    | { kind: 'ok'; data: unknown; outputShape?: unknown }
    | { kind: 'needs_confirm'; risk: string; category: string; message: string }
    | { kind: 'error'; message: string };

  let runBusy = $state(false);
  let runResult: RunResult | null = $state(null);

  async function runSafe() {
    if (!runEnabled || !connectorName || !opName) return;
    runBusy = true;
    runResult = null;
    try {
      const res = await callMcpTool<Record<string, unknown>>('run_op', {
        connector: connectorName,
        op: opName,
        params: opParams
      });
      const r = res.result ?? {};
      if (!res.ok) {
        runResult = { kind: 'error', message: res.error ?? 'run_op failed' };
      } else if (r['requires_confirmation']) {
        runResult = {
          kind: 'needs_confirm',
          risk: String(r['risk'] ?? 'unknown'),
          category: String(r['category'] ?? 'unknown'),
          message: String(r['message'] ?? 'requires confirmation')
        };
      } else if (r['ok'] === false) {
        runResult = { kind: 'error', message: String(r['message'] ?? r['error'] ?? 'op returned ok=false') };
      } else {
        runResult = { kind: 'ok', data: r['data'], outputShape: r['output_shape'] };
      }
    } catch (e: any) {
      runResult = { kind: 'error', message: String(e?.message ?? e) };
    } finally {
      runBusy = false;
    }
  }

  type Resolved =
    | { kind: 'literal'; value: unknown }
    | { kind: 'rendered'; value: unknown }
    | { kind: 'error'; message: string }
    | { kind: 'pending' };

  // Path-keyed map of resolution outcomes — paths look like "to" or
  // "headers.Authorization" or "arg_list[2].value".
  let results: Record<string, Resolved> = $state({});
  let busy = $state(false);
  let lastRunAt: string | null = $state(null);

  function isTemplateString(v: unknown): v is string {
    return typeof v === 'string' && v.includes('{{');
  }

  function* walkStrings(obj: unknown, path: string): Generator<{ path: string; value: string }> {
    if (typeof obj === 'string') {
      yield { path, value: obj };
    } else if (Array.isArray(obj)) {
      for (let i = 0; i < obj.length; i++) yield* walkStrings(obj[i], `${path}[${i}]`);
    } else if (obj && typeof obj === 'object') {
      for (const [k, v] of Object.entries(obj)) {
        yield* walkStrings(v, path ? `${path}.${k}` : k);
      }
    }
  }

  async function runRender() {
    busy = true;
    const next: Record<string, Resolved> = {};
    const args = node.arguments ?? {};
    const tasks: Promise<void>[] = [];
    for (const { path, value } of walkStrings(args, '')) {
      if (!isTemplateString(value)) {
        next[path] = { kind: 'literal', value };
        continue;
      }
      next[path] = { kind: 'pending' };
      tasks.push(
        callMcpTool<{ output?: unknown; error?: string }>('render_jinja', { template: value })
          .then((res) => {
            if (!res.ok || res.result?.error) {
              next[path] = { kind: 'error', message: res.error ?? res.result?.error ?? 'render failed' };
            } else {
              next[path] = { kind: 'rendered', value: res.result?.output };
            }
          })
          .catch((e) => {
            next[path] = { kind: 'error', message: String(e?.message ?? e) };
          })
      );
    }
    results = next;
    await Promise.all(tasks);
    results = { ...next };
    busy = false;
    lastRunAt = new Date().toLocaleTimeString();
  }

  function fmt(v: unknown): string {
    if (typeof v === 'string') return v;
    try {
      return JSON.stringify(v, null, 2);
    } catch {
      return String(v);
    }
  }

  let entries = $derived(Object.entries(results));
</script>

<section class="space-y-3">
  <header class="flex items-center justify-between">
    <div>
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Verify</div>
      <p class="mt-0.5 text-xs text-[var(--text-faint)]">
        Resolve every arg through the live FSR Jinja engine.
      </p>
    </div>
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={runRender}
      disabled={busy}
    >{busy ? 'Rendering…' : 'Render'}</button>
  </header>

  {#if lastRunAt}
    <div class="text-[10px] text-[var(--text-faint)]">last run: {lastRunAt}</div>
  {/if}

  <section class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
    <div class="flex items-center justify-between gap-2">
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">History</div>
        <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
          <code class="font-mono">{historyKind}</code> · <code class="font-mono">{historyKey || '(none)'}</code>
        </p>
      </div>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
        onclick={loadHistory}
        disabled={historyBusy}
      >{historyBusy ? 'Loading…' : 'History'}</button>
    </div>
    {#if historyResult}
      {#if historyResult.kind === 'found'}
        <div class="mt-2 flex items-center gap-2 text-[10px] uppercase tracking-wider">
          <span class:text-emerald-600={historyResult.status === 'tested_pass'}
                class:text-rose-600={historyResult.status === 'tested_fail'}
                class:text-[var(--text-muted)]={historyResult.status !== 'tested_pass' && historyResult.status !== 'tested_fail'}>
            {historyResult.status}
          </span>
          <span class="text-[var(--text-faint)]">via {historyResult.method}</span>
          <span class="text-[var(--text-faint)]">· {historyResult.count} {historyResult.count === 1 ? 'row' : 'rows'}</span>
        </div>
        {#if historyResult.ts}
          <p class="mt-1 text-[10px] text-[var(--text-faint)]">{historyResult.ts}</p>
        {/if}
        {#if historyResult.notes}
          <pre class="mt-1 whitespace-pre-wrap text-xs text-[var(--text-default)]">{historyResult.notes}</pre>
        {/if}
      {:else if historyResult.kind === 'empty'}
        <p class="mt-2 text-xs italic text-[var(--text-faint)]">No verifications recorded.</p>
      {:else}
        <pre class="mt-2 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{historyResult.message}</pre>
      {/if}
    {/if}
  </section>

  <section class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
    <div class="flex items-center justify-between gap-2">
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Test step</div>
        <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
          Render this step and (if read-only) execute it; records pass/fail to the verifications log.
        </p>
      </div>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
        onclick={testStep}
        disabled={stepTestBusy}
      >{stepTestBusy ? 'Testing…' : 'Test step'}</button>
    </div>
    {#if stepTestResult}
      {#if stepTestResult.kind === 'ok'}
        <div class="mt-2 text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400">{stepTestResult.status}</div>
        {#if stepTestResult.note}
          <p class="mt-1 text-xs text-[var(--text-muted)]">{stepTestResult.note}</p>
        {/if}
        {#if stepTestResult.output !== null && stepTestResult.output !== undefined}
          <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-canvas)] p-2 text-xs">{fmt(stepTestResult.output)}</pre>
        {/if}
      {:else}
        <div class="mt-2 text-[10px] uppercase tracking-wider text-rose-600 dark:text-rose-400">error</div>
        <pre class="mt-1 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{stepTestResult.message}</pre>
      {/if}
    {/if}
  </section>

  {#if node.family === 'connector_op'}
    <section class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <div class="flex items-center justify-between gap-2">
        <div>
          <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Run (safe)</div>
          <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
            {#if !connectorName || !opName}
              Connector + operation must be set.
            {:else if !opIsSafe}
              Op name doesn't match a read-only prefix — locked to avoid side effects.
            {:else}
              Executes <code class="font-mono">{connectorName}.{opName}</code> with current params.
            {/if}
          </p>
        </div>
        <button
          type="button"
          class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:cursor-not-allowed disabled:opacity-40"
          onclick={runSafe}
          disabled={!runEnabled || runBusy}
          title={runEnabled ? 'Run live against FSR (read-only)' : 'Locked — destructive or unknown-risk op'}
        >{runBusy ? 'Running…' : 'Run'}</button>
      </div>
      {#if runResult}
        {#if runResult.kind === 'ok'}
          <div class="mt-2 text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400">ok</div>
          <pre class="mt-1 max-h-60 overflow-auto rounded bg-[var(--bg-canvas)] p-2 text-xs">{fmt(runResult.data)}</pre>
        {:else if runResult.kind === 'needs_confirm'}
          <div class="mt-2 text-[10px] uppercase tracking-wider text-amber-600 dark:text-amber-400">
            requires confirmation · {runResult.risk}
          </div>
          <p class="mt-1 text-xs">{runResult.message}</p>
        {:else}
          <div class="mt-2 text-[10px] uppercase tracking-wider text-rose-600 dark:text-rose-400">error</div>
          <pre class="mt-1 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{runResult.message}</pre>
        {/if}
      {/if}
    </section>
  {/if}

  {#if entries.length === 0}
    <p class="italic text-[var(--text-faint)]">Click <strong>Render</strong> to resolve args.</p>
  {:else}
    <ul class="space-y-2">
      {#each entries as [path, r] (path)}
        <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
          <div class="font-mono text-[11px] text-[var(--text-muted)]">{path || '(root)'}</div>
          {#if r.kind === 'pending'}
            <div class="mt-1 text-xs italic text-[var(--text-faint)]">resolving…</div>
          {:else if r.kind === 'literal'}
            <pre class="mt-1 whitespace-pre-wrap text-xs text-[var(--text-default)]">{fmt(r.value)}</pre>
          {:else if r.kind === 'rendered'}
            <pre class="mt-1 whitespace-pre-wrap text-xs text-[var(--text-default)]">{fmt(r.value)}</pre>
            <div class="mt-0.5 text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400">rendered</div>
          {:else if r.kind === 'error'}
            <pre class="mt-1 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{r.message}</pre>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>
