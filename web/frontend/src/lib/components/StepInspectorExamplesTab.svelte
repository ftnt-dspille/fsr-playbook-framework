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

  type Props = { node: VisualNode; playbook: VisualPlaybook };
  let { node, playbook }: Props = $props();

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

    const tasks: Promise<unknown>[] = [];

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
    <ul class="mt-1 space-y-2">
      {#each opExamples.matches as ex}
        <li class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
          <div class="flex items-center justify-between text-[11px] text-[var(--text-muted)]">
            <span class="font-mono">{ex.op_name}</span>
            <button
              type="button"
              class="rounded bg-[var(--brand)] px-1.5 py-0.5 text-[10px] font-medium text-white hover:opacity-90"
              onclick={() => copyToClipboard(ex.snippet, 'Snippet')}
            >Copy</button>
          </div>
          <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-canvas)] p-1.5 text-[11px]">{ex.snippet}</pre>
          {#if ex.notes}
            <div class="mt-1 text-[10px] text-[var(--text-faint)]">{ex.notes}</div>
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
