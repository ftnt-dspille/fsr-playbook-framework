<script lang="ts">
  /**
   * Phase 4 Verify tab. 4.1 = Render button: walks every arg through
   * render_jinja and shows the resolved value inline. Later sub-phases
   * add Run (safe), Test step, Verification history, picklist precheck.
   */
  import type { VisualNode } from '../api';
  import { callMcpTool, verifyPlaybook, getVisualFromBuffer } from '../api';
  import { playbookStore } from '../playbookStore.svelte';
  import { visualStore } from '../visualEditStore.svelte';
  import { buildJinjaContext, type Shape } from '../shapeStubs';

  type Props = { node: VisualNode; playbookIdx: number };
  let { node, playbookIdx }: Props = $props();

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
    | { kind: 'needs_confirm'; risk: string; category: string; rendered: unknown; note: string }
    | { kind: 'error'; message: string };
  let stepTestBusy = $state(false);
  let stepTestResult: StepTestResult | null = $state(null);

  async function testStep(confirm = false) {
    const yaml = playbookStore.currentYaml;
    if (!yaml) {
      stepTestResult = { kind: 'error', message: 'no source YAML available' };
      return;
    }
    stepTestBusy = true;
    stepTestResult = null;
    try {
      const res = await callMcpTool<Record<string, unknown>>('step_test', {
        yaml_text: yaml,
        step_id: node.id,
        confirm
      });
      const r = res.result ?? {};
      if (!res.ok || (r['ok'] === false && r['error'])) {
        stepTestResult = { kind: 'error', message: res.error ?? String(r['error'] ?? 'step_test failed') };
      } else if (r['status'] === 'needs_confirm') {
        stepTestResult = {
          kind: 'needs_confirm',
          risk: String(r['risk'] ?? 'unknown'),
          category: String(r['risk_category'] ?? 'unknown'),
          rendered: r['rendered_args'],
          note: String(r['note'] ?? '')
        };
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

  // Save the just-captured Test step output as the step's `mock_result`.
  // This persists on the step's args in YAML so downstream Verify/Render
  // (and any other step_test invocation) resolves cross-step Jinja
  // against the real shape the connector returned. FSR only consults
  // `mock_result` when mock-mode is on, so this is safe to leave behind
  // on a normal-mode push.
  let mockSaveStatus = $state<'' | 'saving' | 'saved' | 'error'>('');
  let mockSaveError = $state<string | null>(null);
  async function saveAsMock(output: unknown) {
    if (output === undefined || output === null) return;
    mockSaveStatus = 'saving';
    mockSaveError = null;
    try {
      const nextArgs = { ...(node.arguments ?? {}), mock_result: output };
      visualStore.setArgs(playbookIdx, node.id, nextArgs);
      mockSaveStatus = 'saved';
    } catch (e: any) {
      mockSaveStatus = 'error';
      mockSaveError = String(e?.message ?? e);
    }
  }

  // Surface whether the step already has a saved mock so the button
  // says "Update saved mock" instead of "Save as mock" — small, but
  // helps the user know they're not double-saving the same thing.
  let hasMock = $derived(
    (node.arguments as Record<string, unknown> | undefined)?.mock_result !== undefined
  );

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

  // ── Find-record live query preview ──────────────────────────────
  // Posts the current `arguments.query` body to the configured FSR's
  // /api/query/<module> via the `test_find_record` MCP tool. Returns
  // total + first 5 records so the user gets immediate "did my filter
  // match anything" feedback without leaving the inspector.
  type FindResult =
    | { kind: 'ok'; total: number; returned: number; records: unknown[]; url: string }
    | { kind: 'error'; code: string; message: string; url?: string };
  let findBusy = $state(false);
  let findResult: FindResult | null = $state(null);

  function bareModuleName(s: string | undefined | null): string {
    if (!s) return '';
    const q = s.indexOf('?');
    return (q < 0 ? s : s.slice(0, q)).trim();
  }

  let findModule = $derived(
    node.type === 'find_record'
      ? bareModuleName(node.arguments?.module as string | undefined)
      : ''
  );

  async function runFindRecord() {
    if (!findModule) {
      findResult = { kind: 'error', code: 'no_module', message: 'pick a module first' };
      return;
    }
    findBusy = true;
    findResult = null;
    try {
      // Pass the query body as-is — `test_find_record` validates and
      // strips the module name's query-string suffix on the backend.
      const query = (node.arguments?.query as Record<string, unknown> | undefined) ?? {
        logic: 'AND', filters: []
      };
      const res = await callMcpTool<Record<string, unknown>>('test_find_record', {
        module: findModule,
        query,
        limit: 5
      });
      const r = res.result ?? {};
      if (!res.ok || r['ok'] === false) {
        findResult = {
          kind: 'error',
          code: String(r['code'] ?? 'mcp_error'),
          message: String(r['message'] ?? res.error ?? 'test_find_record failed'),
          url: typeof r['url'] === 'string' ? (r['url'] as string) : undefined
        };
      } else {
        findResult = {
          kind: 'ok',
          total: Number(r['total'] ?? 0),
          returned: Number(r['returned'] ?? 0),
          records: (r['records'] as unknown[]) ?? [],
          url: String(r['url'] ?? '')
        };
      }
    } catch (e: any) {
      findResult = { kind: 'error', code: 'transport', message: String(e?.message ?? e) };
    } finally {
      findBusy = false;
    }
  }

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

  /** Provenance for a rendered value. Tells the author whether the
   * resolved string came from real sample data they wrote, a typed
   * stub, or no step ref at all. Drives the colored chip per row. */
  type ValueSource = 'sample' | 'mock' | 'stub' | 'mixed' | 'context';
  type Resolved =
    | { kind: 'literal'; value: unknown }
    | { kind: 'rendered'; value: unknown; source: ValueSource; refs: string[] }
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

  /** Build a Jinja context from the typed_walker's per-step shapes so
   * cross-step refs like `vars.steps.Get_Org.records[0].id` resolve
   * against deterministic stubs instead of erroring as undefined. */
  // Step keys (both id and name-underscored forms) that the most-recent
  // buildContext overlaid sample data onto. Used to classify each
  // rendered value's provenance after a runRender.
  let sampleKeys = $state<Set<string>>(new Set());
  // Step keys that had a `mock_result:` overlaid from the YAML — same
  // role as sampleKeys but distinct because the source of truth and the
  // chip color differ (mocks live on the step itself, samples in the
  // sidecar).
  let mockKeys = $state<Set<string>>(new Set());

  async function buildContext(): Promise<Record<string, unknown>> {
    const yaml = playbookStore.currentYaml;
    if (!yaml) return {};
    try {
      const [verify, graph] = await Promise.all([
        verifyPlaybook(yaml, { verbose: true }),
        getVisualFromBuffer(yaml)
      ]);
      const shapes = (verify.evidence?.per_step_jinja_shapes ?? {}) as Record<string, Shape>;
      const ctx = buildJinjaContext(shapes) as {
        vars: { steps: Record<string, unknown>; input: unknown };
      };
      // Overlay sidecar samples on top of the stubs so manual_input
      // answers (and any future sample types) win over the placeholder
      // values. We overlay under BOTH `step.id` and the
      // `name.replace(" ", "_")` form — FSR keys vars.steps by the
      // name-underscored form (typed_walker._jinja_key), and authors
      // write their templates that way, but ids are how samples are
      // stored on disk.
      const samples = graph.samples ?? {};
      const overlaid = new Set<string>();
      const mocked = new Set<string>();
      for (const pb of graph.playbooks) {
        const idToNameUs = new Map<string, string>();
        for (const n of pb.nodes) {
          idToNameUs.set(n.id, (n.name ?? n.id).replace(/ /g, '_'));
        }
        const overlayPayload = (stepId: string, payload: unknown, bucket: Set<string>) => {
          ctx.vars.steps[stepId] = deepMerge(ctx.vars.steps[stepId], payload);
          bucket.add(stepId);
          const nameKey = idToNameUs.get(stepId);
          if (nameKey && nameKey !== stepId) {
            ctx.vars.steps[nameKey] = deepMerge(ctx.vars.steps[nameKey], payload);
            bucket.add(nameKey);
          }
        };
        // Pass 1: sidecar samples (manual_input answers etc.).
        const pbSamples = samples[pb.name];
        if (pbSamples) {
          for (const [stepId, payload] of Object.entries(pbSamples)) {
            overlayPayload(stepId, payload, overlaid);
          }
        }
        // Pass 2: per-step `mock_result` on connector / record_crud /
        // utility steps. Mock wins over sample on the same step — it's
        // the freshest synthetic value (saved straight from a Test
        // step run).
        for (const n of pb.nodes) {
          const mr = (n.arguments as Record<string, unknown> | undefined)?.mock_result;
          if (mr !== undefined && mr !== null) overlayPayload(n.id, mr, mocked);
        }
      }
      sampleKeys = overlaid;
      mockKeys = mocked;
      return ctx;
    } catch {
      return {};
    }
  }

  /** Sample values win, but anything the stub already had stays so the
   * universal envelope keys (`status`, `result`, `@id`) remain present
   * for downstream templates that touch them. */
  function deepMerge(base: unknown, overlay: unknown): unknown {
    if (overlay === null || overlay === undefined) return base;
    if (
      base && typeof base === 'object' && !Array.isArray(base)
      && overlay && typeof overlay === 'object' && !Array.isArray(overlay)
    ) {
      const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
      for (const [k, v] of Object.entries(overlay as Record<string, unknown>)) {
        out[k] = deepMerge(out[k], v);
      }
      return out;
    }
    return overlay;
  }

  /** Extract every `vars.steps.<key>` reference from a Jinja template
   * string. Pure regex — we only need the head of the lookup chain to
   * classify provenance, not parse the whole Jinja AST. */
  function extractStepRefs(tpl: string): string[] {
    const out = new Set<string>();
    const re = /vars\s*\.\s*steps\s*\.\s*([A-Za-z0-9_]+)|vars\s*\[\s*['"]steps['"]\s*\]\s*[\.\[]\s*['"]?([A-Za-z0-9_]+)/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(tpl)) !== null) {
      const key = m[1] ?? m[2];
      if (key) out.add(key);
    }
    return [...out];
  }

  function classifySource(tpl: string): { source: ValueSource; refs: string[] } {
    const refs = extractStepRefs(tpl);
    if (refs.length === 0) return { source: 'context', refs };
    // Each ref is either: backed by a mock_result, by a sidecar sample,
    // or unbacked (falls through to the typed stub). Promote to the
    // strongest single-source label when every ref agrees; otherwise
    // call it mixed.
    const labels = refs.map((k): 'mock' | 'sample' | 'stub' => {
      if (mockKeys.has(k)) return 'mock';
      if (sampleKeys.has(k)) return 'sample';
      return 'stub';
    });
    const unique = new Set(labels);
    if (unique.size === 1) return { source: labels[0], refs };
    return { source: 'mixed', refs };
  }

  async function runRender() {
    busy = true;
    const next: Record<string, Resolved> = {};
    const args = node.arguments ?? {};
    const tasks: Promise<void>[] = [];
    // One verify call up front; reused for every template render in
    // this step. Cheap (no live probe) and ensures every template sees
    // the same env snapshot.
    const context = await buildContext();
    for (const { path, value } of walkStrings(args, '')) {
      if (!isTemplateString(value)) {
        next[path] = { kind: 'literal', value };
        continue;
      }
      next[path] = { kind: 'pending' };
      tasks.push(
        callMcpTool<{ output?: unknown; error?: string }>(
          'render_jinja', { template: value, context }
        )
          .then((res) => {
            if (!res.ok || res.result?.error) {
              next[path] = { kind: 'error', message: res.error ?? res.result?.error ?? 'render failed' };
            } else {
              const { source, refs } = classifySource(value);
              next[path] = { kind: 'rendered', value: res.result?.output, source, refs };
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
  <header class="flex items-center justify-between gap-3">
    <div>
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Render args</div>
      <p class="mt-0.5 text-xs text-[var(--text-faint)]">
        Replace every <code class="font-mono">{`{{ … }}`}</code> in this
        step with what it will actually become at runtime. Output appears
        in <strong>Rendered args</strong> below.
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
        <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Past test runs</div>
        <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
          {#if node.family === 'connector_op'}
            Verifications for <code class="font-mono">{historyKey || 'this operation'}</code>.
          {:else}
            Verifications for any <code class="font-mono">{node.type}</code> step.
          {/if}
        </p>
      </div>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
        onclick={loadHistory}
        disabled={historyBusy}
      >{historyBusy ? 'Loading…' : 'Load'}</button>
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
          {#if node.family === 'trigger'}
            Triggers fire on FSR events — they can't be "tested" in isolation.
            Clicking renders the step's args only; status will say
            <em>rendered</em> with no execution attempted.
          {:else if node.family === 'connector_op'}
            Render this step's args, then execute the connector op if it's
            marked read-only. Pass/fail is logged to <em>Past test runs</em> above.
          {:else}
            Render this step's args and mark the result pass/fail in the
            verifications log. No record changes for non-connector steps.
          {/if}
        </p>
      </div>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
        onclick={() => testStep(false)}
        disabled={stepTestBusy}
      >{stepTestBusy ? 'Testing…' : 'Test step'}</button>
    </div>
    {#if stepTestResult}
      {#if stepTestResult.kind === 'needs_confirm'}
        <div class="mt-2 rounded border border-amber-500/50 bg-amber-50 dark:bg-amber-900/20 p-2">
          <div class="flex items-center gap-2">
            <span class="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">{stepTestResult.risk}</span>
            <span class="text-[10px] uppercase tracking-wider text-amber-700 dark:text-amber-400">{stepTestResult.category}</span>
          </div>
          <p class="mt-1 text-xs text-[var(--text-default)]">
            This op is classified <strong>{stepTestResult.risk}</strong> — running it
            will hit the live FSR instance and could mutate or block real
            resources. {stepTestResult.note}
          </p>
          <button
            type="button"
            class="mt-2 rounded border border-amber-500 bg-amber-500 px-3 py-1 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
            onclick={() => testStep(true)}
            disabled={stepTestBusy}
          >{stepTestBusy ? 'Running…' : 'Run anyway'}</button>
        </div>
      {:else if stepTestResult.kind === 'ok'}
        <div class="mt-2 flex items-center gap-2">
          <span class="rounded bg-emerald-50 dark:bg-emerald-900/30 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400">{stepTestResult.status}</span>
          <span class="text-[10px] text-[var(--text-faint)]">
            {#if stepTestResult.status === 'rendered'}
              args resolved cleanly — no live call was made
            {:else if stepTestResult.status === 'executed'}
              connector op ran successfully against the live FSR
            {/if}
          </span>
        </div>
        {#if stepTestResult.note}
          <p class="mt-1 text-xs text-[var(--text-muted)]">{stepTestResult.note}</p>
        {/if}
        {#if stepTestResult.output !== null && stepTestResult.output !== undefined}
          <details class="mt-1" open>
            <summary class="cursor-pointer text-[10px] uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-default)]">Show output</summary>
            <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-canvas)] p-2 text-xs">{fmt(stepTestResult.output)}</pre>
          </details>
          {#if stepTestResult.status === 'executed' && node.family === 'connector_op'}
            <div class="mt-2 flex items-center gap-2">
              <button
                type="button"
                class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
                onclick={() => saveAsMock(stepTestResult.kind === 'ok' ? stepTestResult.output : undefined)}
                disabled={mockSaveStatus === 'saving'}
                title="Persist this output as `mock_result` on the step's YAML so downstream Verify/Render resolve Jinja against this shape without re-running"
              >{mockSaveStatus === 'saving'
                  ? 'Saving…'
                  : hasMock ? 'Update saved mock' : 'Save as mock output'}</button>
              {#if mockSaveStatus === 'saved'}
                <span class="text-[10px] text-emerald-600 dark:text-emerald-400">Saved as mock_result</span>
              {:else if mockSaveStatus === 'error'}
                <span class="text-[10px] text-rose-600 dark:text-rose-400">{mockSaveError ?? 'Save failed'}</span>
              {:else if hasMock}
                <span class="text-[10px] text-[var(--text-faint)]">step already has a saved mock</span>
              {/if}
            </div>
          {/if}
        {/if}
      {:else}
        <div class="mt-2 text-[10px] uppercase tracking-wider text-rose-600 dark:text-rose-400">error</div>
        <pre class="mt-1 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{stepTestResult.message}</pre>
      {/if}
    {/if}
  </section>

  {#if node.type === 'find_record'}
    <section class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
      <div class="flex items-center justify-between gap-2">
        <div>
          <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Test query</div>
          <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
            {#if !findModule}
              Pick a module first — the test posts the current filter
              body to <code class="font-mono">/api/query/&lt;module&gt;</code>.
            {:else}
              Posts to <code class="font-mono">/api/query/{findModule}</code> with the current filter and returns the first 5 matches.
            {/if}
          </p>
        </div>
        <button
          type="button"
          class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:cursor-not-allowed disabled:opacity-40"
          onclick={runFindRecord}
          disabled={!findModule || findBusy}
          title={findModule ? 'Run query against the configured FSR (read-only)' : 'Module is empty'}
        >{findBusy ? 'Querying…' : 'Test query'}</button>
      </div>
      {#if findResult}
        {#if findResult.kind === 'ok'}
          <div class="mt-2 flex items-center gap-2 text-[10px] uppercase tracking-wider">
            <span class={findResult.total === 0 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}>
              {findResult.total === 0 ? 'no matches' : 'ok'}
            </span>
            <span class="text-[var(--text-faint)]">total {findResult.total}</span>
            <span class="text-[var(--text-faint)]">· showing {findResult.returned}</span>
          </div>
          {#if findResult.url}
            <p class="mt-1 truncate font-mono text-[10px] text-[var(--text-faint)]" title={findResult.url}>{findResult.url}</p>
          {/if}
          {#if findResult.records.length === 0}
            <p class="mt-2 text-xs italic text-[var(--text-faint)]">
              The query ran but matched no records. Tweak the filters and rerun.
            </p>
          {:else}
            <pre class="mt-1 max-h-60 overflow-auto rounded bg-[var(--bg-canvas)] p-2 text-xs">{fmt(findResult.records)}</pre>
          {/if}
        {:else}
          <div class="mt-2 text-[10px] uppercase tracking-wider text-rose-600 dark:text-rose-400">
            error · {findResult.code}
          </div>
          <pre class="mt-1 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{findResult.message}</pre>
          {#if findResult.url}
            <p class="mt-1 truncate font-mono text-[10px] text-[var(--text-faint)]" title={findResult.url}>{findResult.url}</p>
          {/if}
        {/if}
      {/if}
    </section>
  {/if}

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
    <p class="italic text-[var(--text-faint)]">
      Click <strong>Render</strong> above to resolve this step's args.
      Output will appear here.
    </p>
  {:else}
    <div>
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Rendered args
      </div>
      <p class="mt-0.5 mb-2 text-[11px] text-[var(--text-faint)]">
        One row per arg path. Tag shows where the resolved value came from:
        <span class="text-violet-600 dark:text-violet-400">mock</span> (saved <code class="font-mono">mock_result</code> on a connector step),
        <span class="text-emerald-600 dark:text-emerald-400">sample</span> (saved manual_input answers),
        <span class="text-amber-600 dark:text-amber-400">stub</span> (typed placeholder — nothing saved),
        <span class="text-orange-600 dark:text-orange-400">mixed</span>, or
        <span class="text-sky-600 dark:text-sky-400">context</span> (no step ref).
        No tag = value was already a literal.
      </p>
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
              <!-- Provenance chip: tells the author whether this value
                   came from saved sample answers, a typed stub, a
                   non-step context (e.g. vars.input.params.*), or a
                   mix. Helps explain why a render looks right /
                   wrong without staring at the YAML. -->
              <div class="mt-0.5 flex items-center gap-1">
                {#if r.source === 'mock'}
                  <span class="rounded-full bg-violet-500/20 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-violet-700 dark:text-violet-400"
                        title={`Resolved from a saved mock_result on: ${r.refs.join(', ')}`}>mock</span>
                {:else if r.source === 'sample'}
                  <span class="rounded-full bg-emerald-500/20 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400"
                        title={`Resolved from saved sample data on: ${r.refs.join(', ')}`}>sample</span>
                {:else if r.source === 'stub'}
                  <span class="rounded-full bg-amber-500/20 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400"
                        title={`Resolved against typed stubs (no sample saved on: ${r.refs.join(', ')}). Save sample answers on those manual_input steps for accurate values.`}>stub</span>
                {:else if r.source === 'mixed'}
                  <span class="rounded-full bg-orange-500/20 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-orange-700 dark:text-orange-400"
                        title={`Mixed: some refs hit saved samples, others fell back to stubs. Refs: ${r.refs.join(', ')}`}>mixed</span>
                {:else}
                  <span class="rounded-full bg-sky-500/20 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-sky-700 dark:text-sky-400"
                        title="Resolved against the playbook input / non-step context — no vars.steps.* lookup">context</span>
                {/if}
                {#if r.refs.length > 0}
                  <span class="font-mono text-[9px] text-[var(--text-faint)]">{r.refs.join(', ')}</span>
                {/if}
              </div>
            {:else if r.kind === 'error'}
              <pre class="mt-1 whitespace-pre-wrap text-xs text-rose-600 dark:text-rose-400">{r.message}</pre>
            {/if}
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</section>
