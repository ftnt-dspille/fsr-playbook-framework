<script lang="ts">
  /**
   * Phase 2.2 — Examples view.
   *
   * Two stacked sections:
   * - Operation examples from `find_operation_example` (real
   *   playbook-step bodies indexed in operation_examples).
   * - Jinja examples from `find_jinja_example` driven by the
   *   var paths the agent currently has in scope (vars.input.*,
   *   vars.steps.<predecessor>.*) plus a generic "for this step
   *   type" pull when no var anchor is available.
   *
   * Each example has a "Copy" button (Phase 2.3 — write-path
   * proof). Insert-into-args uses the same plumbing once Phase 3
   * lands the structural-edit endpoint.
   */
  import { callMcpTool } from '../api';
  import type { VisualNode, VisualPlaybook } from '../api';
  import { visualStore } from '../visualEditStore.svelte';

  type Props = { node: VisualNode; playbook: VisualPlaybook; playbookIdx: number };
  let { node, playbook, playbookIdx }: Props = $props();

  type OpExample = { op_name: string; snippet: string; notes?: string };
  type OpExampleResult = { matches: OpExample[]; count: number; suggestion?: string };

  type JinjaExample = {
    raw: string;
    kind?: string;
    filters_csv?: string | null;
    vars_csv?: string | null;
    step_type?: string | null;
    from_playbook?: string | null;
    occurrences?: number;
  };
  type JinjaExampleResult = { matches: JinjaExample[]; count: number; suggestion?: string };

  let opExamples: OpExampleResult | null = $state(null);
  let jinjaExamples: JinjaExampleResult | null = $state(null);
  let copyHint: string | null = $state(null);
  let loading = $state(false);
  let loadError: string | null = $state(null);

  // Corpus-mined skeletons + summaries for non-connector step types
  // (everything routed through `/api/ref/step-examples/<type>`).
  // Loaded in parallel with the connector_op fetches above.
  type CorpusExample = {
    frequency: number;
    playbook_count: number;
    summary: string;
    arguments: Record<string, unknown>;
    corpus_type: string;
  };
  let corpusExamples = $state<CorpusExample[]>([]);
  let corpusLoadError: string | null = $state(null);

  // Step types that have a corpus-mined Examples view (mirrors
  // STEP_TYPES_WITH_EXAMPLES in StepInspector.svelte; kept local so
  // the load decision is self-contained).
  const CORPUS_TYPES = new Set([
    'decision', 'manual_input', 'set_variable', 'find_record',
    'create_record', 'insert_record', 'update_record', 'delete_record',
    'ingest_bulk_feed', 'delay', 'code_snippet', 'workflow_reference',
    'start_on_create', 'start_on_update', 'start',
    'manual_action', 'api_call'
  ]);

  let connector = $derived(node.arguments?.connector as string | undefined);
  let opName = $derived(
    (node.arguments?.operation as string | undefined) ??
      (node.family === 'connector_op' ? node.type : undefined)
  );

  // Pick the most likely jinja-search anchor: closest predecessor's
  // step name (for `vars.steps.X` lookups), or fall back to step type.
  let jinjaQuery = $derived(buildJinjaQuery(node, playbook));

  function buildJinjaQuery(n: VisualNode, pb: VisualPlaybook): {
    var_path?: string;
    step_type?: string;
  } {
    const inbound = pb.edges.find((e) => e.target === n.id);
    if (inbound) {
      const pred = pb.nodes.find((m) => m.id === inbound.source);
      if (pred) {
        // FSR step_id key in jinja is name with spaces → underscores.
        const key = (pred.name || pred.id).replace(/ /g, '_');
        return { var_path: `vars.steps.${key}` };
      }
    }
    // No predecessor — narrow by step type. ManualInput / Decision /
    // SetVariable / etc. all have idiomatic patterns.
    const stepType =
      n.type === 'set_variable' ? 'SetVariable' :
      n.type === 'decision' ? 'Decision' :
      n.type === 'update_record' ? 'UpdateRecord' :
      n.type === 'find_record' ? 'FindRecords' :
      n.type === 'create_record' ? 'InsertData' : undefined;
    return stepType ? { step_type: stepType } : {};
  }

  $effect(() => {
    loading = true;
    loadError = null;
    opExamples = null;
    jinjaExamples = null;
    corpusExamples = [];
    corpusLoadError = null;

    const tasks: Promise<unknown>[] = [];

    if (CORPUS_TYPES.has(node.type)) {
      tasks.push(
        fetch(`/api/ref/step-examples/${encodeURIComponent(node.type)}?limit=8`)
          .then(async (r) => {
            if (!r.ok) {
              corpusLoadError = `HTTP ${r.status}`;
              return;
            }
            const data = await r.json();
            corpusExamples = (data.examples ?? []) as CorpusExample[];
          })
          .catch((e) => { corpusLoadError = String(e?.message ?? e); })
      );
    }

    if (connector) {
      tasks.push(
        callMcpTool<OpExampleResult>('find_operation_example', {
          connector,
          op: opName,
          limit: 5
        }).then((r) => {
          if (r.ok) opExamples = r.result ?? null;
        })
      );
    }

    if (jinjaQuery.var_path || jinjaQuery.step_type) {
      tasks.push(
        callMcpTool<JinjaExampleResult>('find_jinja_example', {
          ...jinjaQuery,
          limit: 6
        }).then((r) => {
          if (r.ok) jinjaExamples = r.result ?? null;
        })
      );
    }

    Promise.all(tasks)
      .catch((e) => (loadError = (e as Error).message))
      .finally(() => (loading = false));
  });

  /** Minimal JSON syntax highlighter: tokenises keys, strings, numbers,
   * booleans, and null. Returns HTML with span class names — Tailwind
   * styles them via the `.fsrpb-json-*` rules at the bottom of the
   * file. Escapes `<` so injection isn't possible. */
  function highlightJson(raw: string): string {
    let pretty = raw;
    try { pretty = JSON.stringify(JSON.parse(raw), null, 2); }
    catch {}
    const escaped = pretty.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return escaped.replace(
      /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/g,
      (m, str, colon, kw) => {
        if (str && colon) return `<span class="fsrpb-json-key">${str}</span>${colon}`;
        if (str) return `<span class="fsrpb-json-string">${str}</span>`;
        if (kw) return `<span class="fsrpb-json-kw">${kw}</span>`;
        return `<span class="fsrpb-json-num">${m}</span>`;
      }
    );
  }

  /** Apply an operation example's `{connector, operation, params}` JSON
   * to the current node's arguments. Replaces connector/operation/params
   * but preserves everything else (config, comment, for_each, etc.) so
   * the user doesn't lose unrelated edits. */
  function useOpExample(snippet: string) {
    let parsed: Record<string, unknown>;
    try { parsed = JSON.parse(snippet) as Record<string, unknown>; }
    catch { copyHint = 'snippet not parseable'; setTimeout(() => (copyHint = null), 1400); return; }
    const args: Record<string, unknown> = JSON.parse(JSON.stringify(node.arguments ?? {}));
    if (typeof parsed.connector === 'string') args.connector = parsed.connector;
    if (typeof parsed.operation === 'string') args.operation = parsed.operation;
    if (parsed.params && typeof parsed.params === 'object') args.params = parsed.params;
    visualStore.setArgs(playbookIdx, node.id, args);
    copyHint = 'Applied to step';
    setTimeout(() => (copyHint = null), 1400);
  }

  async function copyToClipboard(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      copyHint = `${label} copied`;
      setTimeout(() => (copyHint = null), 1400);
    } catch {
      copyHint = 'clipboard unavailable';
    }
  }
</script>

{#if loading}
  <div class="text-xs text-[var(--text-faint)]">Loading examples…</div>
{/if}
{#if loadError}
  <div class="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-800">{loadError}</div>
{/if}
{#if copyHint}
  <div class="mb-2 rounded bg-[var(--brand)] px-2 py-0.5 text-[11px] text-white">{copyHint}</div>
{/if}

<section class="mb-4">
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
    Operation examples
  </div>
  {#if !connector}
    <p class="mt-1 text-xs italic text-[var(--text-faint)]">
      Set a <code>connector</code> to see real-world examples.
    </p>
  {:else if opExamples?.count === 0 || !opExamples}
    <p class="mt-1 text-xs italic text-[var(--text-faint)]">
      {opExamples?.suggestion ?? 'No examples in store yet.'}
    </p>
  {:else}
    <ul class="mt-2 space-y-3">
      {#each opExamples.matches as ex}
        <li class="fsrpb-example-card overflow-hidden rounded-lg border border-[var(--border-soft)] bg-[var(--bg-elev)] shadow-sm transition-shadow hover:shadow">
          <div class="flex items-center justify-between gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1.5">
            <span class="truncate font-mono text-[12px] font-semibold text-[var(--text-default)]">{ex.op_name}</span>
            <div class="flex flex-shrink-0 gap-1">
              <button
                type="button"
                class="rounded border border-[var(--border-soft)] bg-[var(--brand)] px-2 py-0.5 text-[10px] font-medium text-white transition-colors hover:opacity-90"
                onclick={() => useOpExample(ex.snippet)}
              >Use</button>
              <button
                type="button"
                class="rounded border border-[var(--border-soft)] bg-transparent px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-canvas)]"
                onclick={() => copyToClipboard(ex.snippet, 'Snippet')}
              >Copy</button>
            </div>
          </div>
          <pre class="fsrpb-json max-h-56 overflow-auto px-3 py-2 text-[11px] leading-relaxed">{@html highlightJson(ex.snippet)}</pre>
          {#if ex.notes}
            <div class="border-t border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-[10px] text-[var(--text-faint)]">{ex.notes}</div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</section>

<section>
  <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
    Jinja patterns
    {#if jinjaQuery.var_path}
      <span class="font-mono normal-case text-[var(--text-faint)]"> · {jinjaQuery.var_path}</span>
    {:else if jinjaQuery.step_type}
      <span class="normal-case text-[var(--text-faint)]"> · {jinjaQuery.step_type}</span>
    {/if}
  </div>
  {#if !jinjaQuery.var_path && !jinjaQuery.step_type}
    <p class="mt-1 text-xs italic text-[var(--text-faint)]">No jinja anchor for this step.</p>
  {:else if jinjaExamples?.count === 0 || !jinjaExamples}
    <p class="mt-1 text-xs italic text-[var(--text-faint)]">
      {jinjaExamples?.suggestion ?? 'No matching expressions in corpus.'}
    </p>
  {:else}
    <ul class="mt-1 space-y-1">
      {#each jinjaExamples.matches as je}
        <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1">
          <div class="flex items-center justify-between gap-2 text-[10px] text-[var(--text-faint)]">
            <span>
              {je.step_type ?? '?'}
              {#if je.occurrences}· seen {je.occurrences}×{/if}
            </span>
            <button
              type="button"
              class="rounded bg-[var(--brand)] px-1.5 py-0.5 text-[10px] font-medium text-white hover:opacity-90"
              onclick={() => copyToClipboard(je.raw, 'Expression')}
            >Copy</button>
          </div>
          <code class="block break-all font-mono text-[11px] text-[var(--text-default)]">{je.raw}</code>
        </li>
      {/each}
    </ul>
  {/if}
</section>

{#if CORPUS_TYPES.has(node.type)}
  <section class="mt-4">
    <header class="mb-2">
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Patterns from production
      </div>
      <p class="text-[11px] text-[var(--text-faint)]">
        Real <code class="font-mono">{node.type}</code> shapes mined
        from playbooks on disk + the live FSR, ranked by frequency.
        Click a row to inspect the full args.
      </p>
    </header>
    {#if loading}
      <p class="italic text-[var(--text-faint)] text-[11px]">loading…</p>
    {:else if corpusLoadError}
      <p class="text-[11px] text-rose-600 dark:text-rose-400">{corpusLoadError}</p>
    {:else if corpusExamples.length === 0}
      <p class="text-[11px] italic text-[var(--text-faint)]">
        No examples in the trained store for this step type yet.
        Run <code class="font-mono">fsrpb train</code> against a live
        FSR to populate.
      </p>
    {:else}
      <ul class="space-y-2">
        {#each corpusExamples as ex, idx (idx)}
          <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
            <details>
              <summary class="cursor-pointer">
                <div class="flex items-baseline justify-between gap-2">
                  <p class="text-[12px] text-[var(--text-default)]">{ex.summary}</p>
                  <span class="flex-shrink-0 text-[10px] text-[var(--text-faint)]">
                    {ex.frequency}× · {ex.playbook_count} {ex.playbook_count === 1 ? 'pb' : 'pbs'}
                  </span>
                </div>
              </summary>
              <pre class="fsrpb-json mt-2 max-h-60 overflow-auto rounded p-2 text-[11px]">{@html highlightJson(JSON.stringify(ex.arguments))}</pre>
              <div class="mt-1 flex items-center justify-end gap-2 text-[10px]">
                <span class="text-[var(--text-faint)]">corpus type: <code class="font-mono">{ex.corpus_type}</code></span>
                <button
                  type="button"
                  class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-0.5 hover:bg-[var(--bg-elev)]"
                  onclick={async () => {
                    try {
                      await navigator.clipboard.writeText(JSON.stringify(ex.arguments, null, 2));
                      copyHint = 'copied!';
                      setTimeout(() => (copyHint = null), 1200);
                    } catch {
                      copyHint = 'copy failed';
                      setTimeout(() => (copyHint = null), 1200);
                    }
                  }}
                >Copy args</button>
              </div>
            </details>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}


<style>
  .fsrpb-json {
    background: var(--bg-canvas);
    color: var(--text-default);
    font-family: ui-monospace, "SF Mono", "Monaco", monospace;
  }
  :global(.fsrpb-json-key) { color: #93c5fd; font-weight: 600; }
  :global(.fsrpb-json-string) { color: #86efac; }
  :global(.fsrpb-json-num) { color: #fdba74; }
  :global(.fsrpb-json-kw) { color: #c4b5fd; font-style: italic; }
</style>
