<script lang="ts">
  /**
   * Debug runner MVP. Calls `step_through_playbook` once; renders the
   * resulting trace as clickable tiles. Click a tile to see its
   * rendered args + output. No pause / breakpoints yet — the MCP tool
   * runs the whole walk in a single call and we scrub the result.
   *
   * Phase 5.1 / 5.2 / 5.6 of VISUAL_EDITOR_PLAN. Phases 5.3-5.5
   * (breakpoints, branch chooser, watch panel) deferred.
   */
  import { playbookStore } from '$lib/playbookStore.svelte';
  import { stepThroughPlaybook, type DebugStepFrame, type DebugRunResult } from '$lib/api';

  let busy = $state(false);
  let result = $state<DebugRunResult | null>(null);
  let selectedIdx = $state<number>(-1);
  let lastRunAt = $state<string | null>(null);

  let trace = $derived(result?.trace ?? []);
  let selected = $derived<DebugStepFrame | null>(
    selectedIdx >= 0 && selectedIdx < trace.length ? trace[selectedIdx] : null
  );

  async function run() {
    const yaml = playbookStore.currentYaml;
    if (!yaml) {
      result = { ok: false, trace: [], error: 'no playbook loaded' };
      return;
    }
    busy = true;
    selectedIdx = -1;
    try {
      result = await stepThroughPlaybook(yaml, { executeSafeOps: true });
      lastRunAt = new Date().toLocaleTimeString();
      // Auto-select the first errored frame, else the last frame.
      if (result.first_error) {
        const idx = trace.findIndex((f) => f.step_id === result!.first_error!.step_id);
        selectedIdx = idx >= 0 ? idx : trace.length - 1;
      } else if (trace.length > 0) {
        selectedIdx = trace.length - 1;
      }
    } finally {
      busy = false;
    }
  }

  function stop() {
    // No server-side session yet; "stop" just clears the result.
    result = null;
    selectedIdx = -1;
  }

  function statusClass(status: string): string {
    if (status === 'ok' || status === 'finished' || status === 'simulated') {
      return 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20';
    }
    if (status === 'error' || status === 'failed') {
      return 'border-rose-500 bg-rose-50 dark:bg-rose-900/20';
    }
    if (status === 'skipped' || status === 'unsafe_simulated') {
      return 'border-amber-500 bg-amber-50 dark:bg-amber-900/20';
    }
    return 'border-[var(--border)] bg-[var(--bg-elev)]';
  }
</script>

<div class="flex h-full flex-col">
  <!-- Run controls -->
  <div class="flex items-center gap-2 border-b border-[var(--border-soft)] px-3 py-2">
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={run}
      disabled={busy}
      title="Run the playbook through the offline stepper (renders Jinja, executes safe ops, simulates the rest)"
    >{busy ? '▶ Running…' : '▶ Run'}</button>
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={stop}
      disabled={busy || !result}
      title="Clear the trace"
    >⏹ Clear</button>
    {#if lastRunAt}
      <span class="text-[10px] text-[var(--text-faint)]">last run: {lastRunAt}</span>
    {/if}
    {#if result}
      <span class="ml-2 text-[11px] text-[var(--text-muted)]">
        {result.steps_executed ?? trace.length} step(s)
        {#if result.first_error}
          · <span class="text-rose-600 dark:text-rose-400 font-medium">first error: {result.first_error.step_id}</span>
        {/if}
      </span>
    {/if}
    <div class="ml-auto text-[10px] text-[var(--text-faint)]">
      Offline stepper · safe ops execute live · unsafe simulated
    </div>
  </div>

  <!-- Body: trace tape (left) + detail (right) -->
  <div class="grid h-full min-h-0 grid-cols-[260px_1fr]">
    <!-- Trace tape -->
    <div class="overflow-y-auto border-r border-[var(--border-soft)] p-2">
      {#if !result}
        <p class="px-1 py-2 text-xs text-[var(--text-faint)]">
          Press <strong>Run</strong> to walk the playbook step-by-step. The trace
          appears here; click a tile to see its rendered args and output.
        </p>
      {:else if result.error && trace.length === 0}
        <p class="px-1 py-2 text-xs text-rose-600 dark:text-rose-400">
          {result.error}
        </p>
      {:else if trace.length === 0}
        <p class="px-1 py-2 text-xs text-[var(--text-faint)]">
          no steps walked
        </p>
      {:else}
        {#each trace as frame, i}
          <button
            type="button"
            class={'mb-1.5 w-full rounded border-l-2 px-2 py-1.5 text-left transition-colors ' +
              statusClass(frame.status) +
              (i === selectedIdx ? ' ring-2 ring-[var(--brand)]' : '')}
            onclick={() => (selectedIdx = i)}
          >
            <div class="flex items-baseline justify-between gap-2">
              <span class="font-mono text-xs font-medium text-[var(--text-default)]">
                {i + 1}. {frame.step_id}
              </span>
              <span class="text-[9px] uppercase tracking-wider text-[var(--text-faint)]">
                {frame.status}
              </span>
            </div>
            <div class="text-[10px] text-[var(--text-faint)]">{frame.type}</div>
            {#if frame.note}
              <div class="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                {frame.note}
              </div>
            {/if}
          </button>
        {/each}
      {/if}
    </div>

    <!-- Detail pane -->
    <div class="overflow-y-auto p-3">
      {#if !selected}
        <p class="text-xs text-[var(--text-faint)]">
          Select a step on the left to see its rendered args and output.
        </p>
      {:else}
        <div class="mb-2 flex items-baseline gap-3">
          <h3 class="font-mono text-sm font-semibold text-[var(--text-default)]">
            {selected.step_id}
          </h3>
          <span class="text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
            {selected.type} · {selected.status}
          </span>
        </div>
        {#if selected.note}
          <p class="mb-3 text-xs italic text-[var(--text-muted)]">{selected.note}</p>
        {/if}
        <div class="mb-3">
          <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            Rendered args
          </div>
          <pre class="overflow-x-auto rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2 text-[11px] font-mono text-[var(--text-default)]">{JSON.stringify(selected.rendered_args, null, 2)}</pre>
        </div>
        <div>
          <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            Output{selected.output_top_keys?.length
              ? ` (keys: ${selected.output_top_keys.join(', ')})`
              : ''}
          </div>
          <pre class="overflow-x-auto rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2 text-[11px] font-mono text-[var(--text-default)]">{JSON.stringify(selected.output, null, 2)}</pre>
        </div>
      {/if}
    </div>
  </div>
</div>
