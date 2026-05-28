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

  // ─── Static checks (Tier 1/2/3 diagnostics filtered to this step) ────
  // The whole-playbook verify gate already runs in `buildContext`; the
  // result carries every required_fix with a `step` field. Surfacing
  // the subset that fires on the focused step makes them actionable
  // without forcing the user to leave the inspector for the global
  // diagnostics drawer.

  type StepFix = {
    code: string;
    message: string;
    path: string | null;
    suggestion: string | null;
  };
  let stepFixes = $state<StepFix[]>([]);
  let stepWarnings = $state<StepFix[]>([]);
  let staticChecksBusy = $state(false);
  let staticChecksTs: string | null = $state(null);

  function _normaliseFix(raw: Record<string, unknown>): StepFix {
    return {
      code: String(raw['code'] ?? 'unknown'),
      message: String(raw['message'] ?? ''),
      path: raw['path'] != null ? String(raw['path']) : null,
      suggestion: raw['suggestion'] != null ? String(raw['suggestion']) : null,
    };
  }

  function _matchesNode(raw: Record<string, unknown>): boolean {
    // Walker diagnostics carry `step` keyed by step.id; resolver
    // diagnostics carry `path` like `playbooks[0].steps[2].arguments.…`.
    // Match on either.
    const sid = raw['step'];
    if (typeof sid === 'string' && sid && (sid === node.id || sid === node.name?.replace(/ /g, '_'))) {
      return true;
    }
    const path = raw['path'];
    if (typeof path === 'string' && path.includes(`.steps[${playbookIdx}]`)) {
      // Crude: scan for the step's index in the IR-style path; not
      // perfect when steps reorder but covers the dominant case.
      // (Future: thread node.irIndex through if needed.)
      return path.includes(`.${node.id}.`) || path.includes(`.${node.name}.`);
    }
    return false;
  }

  async function runStaticChecks() {
    const yaml = playbookStore.currentYaml;
    if (!yaml) return;
    staticChecksBusy = true;
    try {
      const verify = await verifyPlaybook(yaml, { verbose: false });
      const fixes = (verify.required_fixes ?? []) as Record<string, unknown>[];
      const warns = (verify.warnings ?? []) as Record<string, unknown>[];
      stepFixes = fixes.filter(_matchesNode).map(_normaliseFix);
      stepWarnings = warns.filter(_matchesNode).map(_normaliseFix);
      staticChecksTs = new Date().toLocaleTimeString();
    } catch {
      // Auto-run swallows failures so an offline verify_playbook
      // endpoint doesn't spam unhandled rejections; the manual ↻
      // button still surfaces errors when explicitly invoked.
      stepFixes = [];
      stepWarnings = [];
    } finally {
      staticChecksBusy = false;
    }
  }

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

  // Auto-run on tab open + whenever the focused node changes. We
  // no longer auto-render args — step_test (Run this step) returns
  // the rendered_args alongside execution status, so the standalone
  // render call is now dead surface. Keep the function around in
  // case a future "preview" view wants it.
  let autoRanFor = $state<string | null>(null);
  $effect(() => {
    const key = node?.id ?? null;
    if (!key || key === autoRanFor) return;
    autoRanFor = key;
    void runStaticChecks();
    void loadHistory();
  });
</script>

<section class="space-y-3">
  <!-- Step-scoped static issues: shown ONLY when there's something to
       fix. No header, no Re-check button, no zero-state message. If the
       step is clean, this section is invisible. -->
  {#if stepFixes.length > 0 || stepWarnings.length > 0}
    <section class="space-y-2">
      {#each stepFixes as f}
        <div class="rounded border-l-2 border-rose-500 bg-rose-50 dark:bg-rose-900/20 px-2 py-1.5">
          <div class="flex items-baseline gap-2">
            <span class="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-rose-700 dark:text-rose-400">{f.code}</span>
            {#if f.path}<span class="font-mono text-[10px] text-[var(--text-faint)]">{f.path}</span>{/if}
          </div>
          <p class="mt-1 text-xs text-[var(--text-default)]">{f.message}</p>
          {#if f.suggestion}<p class="mt-1 text-[11px] italic text-[var(--text-muted)]">→ {f.suggestion}</p>{/if}
        </div>
      {/each}
      {#each stepWarnings as w}
        <div class="rounded border-l-2 border-amber-500 bg-amber-50 dark:bg-amber-900/20 px-2 py-1.5">
          <div class="flex items-baseline gap-2">
            <span class="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">{w.code}</span>
            {#if w.path}<span class="font-mono text-[10px] text-[var(--text-faint)]">{w.path}</span>{/if}
          </div>
          <p class="mt-1 text-xs text-[var(--text-default)]">{w.message}</p>
        </div>
      {/each}
    </section>
  {/if}

  <!-- The single deliberate action on this tab. Beneath it: rendered
       arg preview (auto-loaded), result status (after click), history
       line (auto-loaded), and Save-as-mock (after connector exec).
       Everything that was once 5 separate sections lives in one block. -->
  <section class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
    <div class="flex items-center justify-between gap-2">
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Run this step</div>
        <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
          {#if node.family === 'trigger'}
            Triggers fire on FSR events. Click renders args only.
          {:else if node.family === 'connector_op'}
            Renders args and executes the op if read-only. Output can be saved as a mock.
          {:else}
            Renders args and logs the result. No record changes for non-connector steps.
          {/if}
        </p>
      </div>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--brand)] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        onclick={() => testStep(false)}
        disabled={stepTestBusy}
      >{stepTestBusy ? 'Running…' : '▶ Run this step'}</button>
    </div>

    <!-- Inline history: single line replacing the old "Past test runs"
         section. Shown only when there's a recorded run. -->
    {#if historyResult && historyResult.kind === 'found'}
      <details class="mt-2 text-[10px]">
        <summary class="cursor-pointer text-[var(--text-faint)]">
          last test:
          <span class:text-emerald-600={historyResult.status === 'tested_pass'}
                class:text-rose-600={historyResult.status === 'tested_fail'}
                class:text-[var(--text-muted)]={historyResult.status !== 'tested_pass' && historyResult.status !== 'tested_fail'}
                class="font-medium uppercase tracking-wider">{historyResult.status}</span>
          <span>· via {historyResult.method}</span>
          {#if historyResult.ts}<span>· {historyResult.ts}</span>{/if}
        </summary>
        {#if historyResult.notes}
          <pre class="mt-1 whitespace-pre-wrap text-[10px] text-[var(--text-default)]">{historyResult.notes}</pre>
        {/if}
      </details>
    {/if}
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
        {@const okResult = stepTestResult}
        <div class="mt-2 flex items-center gap-2">
          <span class="rounded bg-emerald-50 dark:bg-emerald-900/30 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400">{okResult.status}</span>
          <span class="text-[10px] text-[var(--text-faint)]">
            {#if okResult.status === 'rendered'}
              args resolved cleanly — no live call was made
            {:else if okResult.status === 'executed'}
              connector op ran successfully against the live FSR
            {/if}
          </span>
        </div>
        {#if okResult.note}
          <p class="mt-1 text-xs text-[var(--text-muted)]">{okResult.note}</p>
        {/if}
        {#if okResult.output !== null && okResult.output !== undefined}
          <details class="mt-1" open>
            <summary class="cursor-pointer text-[10px] uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-default)]">Show output</summary>
            <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-canvas)] p-2 text-xs">{fmt(okResult.output)}</pre>
          </details>
          {#if okResult.status === 'executed' && node.family === 'connector_op'}
            <div class="mt-2 flex items-center gap-2">
              <button
                type="button"
                class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
                onclick={() => saveAsMock(okResult.output)}
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

</section>
