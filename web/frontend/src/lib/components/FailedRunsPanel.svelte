<script lang="ts">
  import { onMount } from 'svelte';
  import {
    listRecentFailedRuns,
    whyDidPlaybookFail,
    type FailedRun,
    type WhyDidPlaybookFail,
  } from '$lib/api';

  // Phase 5 surface for VERIFY_PLAYBOOK_PLAN. Two tickets in one panel:
  // failed-runs list (left) + why-did-this-fail diagnostics (right).
  // Both are thin clients over MCP tools; no new backend routes.

  let runs = $state<FailedRun[]>([]);
  let loadingRuns = $state(true);
  let runsError = $state<string | null>(null);

  let filterText = $state('');
  let includeFinished = $state(false);

  let selected = $state<FailedRun | null>(null);
  let diag = $state<WhyDidPlaybookFail | null>(null);
  let loadingDiag = $state(false);
  let diagError = $state<string | null>(null);

  async function loadRuns() {
    loadingRuns = true;
    runsError = null;
    try {
      runs = await listRecentFailedRuns({
        limit: 50,
        include_finished: includeFinished,
        playbook: filterText.trim() || undefined,
      });
    } catch (e: any) {
      runsError = String(e?.message || e);
    } finally {
      loadingRuns = false;
    }
  }

  async function pick(r: FailedRun) {
    selected = r;
    diag = null;
    diagError = null;
    loadingDiag = true;
    try {
      // Use task_id (UUID) when present — most reliable for resolution.
      const id = r.task_id || (r.pk != null ? String(r.pk) : '');
      if (!id) throw new Error('run has no task_id or pk');
      diag = await whyDidPlaybookFail(id);
    } catch (e: any) {
      diagError = String(e?.message || e);
    } finally {
      loadingDiag = false;
    }
  }

  function fmtTs(s: string | null | undefined): string {
    if (!s) return '';
    const d = new Date(s);
    return Number.isFinite(d.getTime())
      ? d.toLocaleString(undefined, {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })
      : s;
  }

  function statusClass(s: string): string {
    switch (s) {
      case 'failed':
      case 'finished_with_error':
        return 'text-rose-400';
      case 'terminated':
        return 'text-amber-400';
      case 'finished':
        return 'text-emerald-400';
      default:
        return 'text-[var(--text-muted)]';
    }
  }

  function severityClass(sev: string): string {
    return sev === 'error'
      ? 'border-l-rose-500 bg-rose-950/20'
      : sev === 'warning'
        ? 'border-l-amber-500 bg-amber-950/15'
        : 'border-l-zinc-600 bg-[var(--bg-panel)]/40';
  }

  onMount(loadRuns);
</script>

<div class="flex h-full min-h-0">
  <aside
    class="w-96 shrink-0 border-r border-[var(--border-soft)] overflow-y-auto"
  >
    <div
      class="sticky top-0 z-10 bg-[var(--bg-canvas)] border-b border-[var(--border-soft)] px-4 py-3"
    >
      <div class="flex items-center justify-between mb-2">
        <h2 class="font-semibold">Failed runs</h2>
        <button
          onclick={loadRuns}
          class="text-xs text-[var(--text-muted)] hover:text-[var(--text-default)]"
          title="Refresh"
        >
          ↻
        </button>
      </div>
      <input
        type="text"
        bind:value={filterText}
        onkeydown={(e) => e.key === 'Enter' && loadRuns()}
        onblur={loadRuns}
        placeholder="Filter by playbook name…"
        class="w-full rounded border border-[var(--border)] bg-[var(--bg-panel)] px-2 py-1 text-xs text-[var(--text-default)] placeholder:text-[var(--text-faint)] focus:border-[var(--brand)] focus:outline-none"
      />
      <label class="mt-2 flex items-center gap-2 text-xs text-[var(--text-muted)]">
        <input
          type="checkbox"
          bind:checked={includeFinished}
          onchange={loadRuns}
        />
        Include finished runs
      </label>
    </div>

    {#if loadingRuns}
      <div class="p-4 text-[var(--text-faint)] text-sm">Loading…</div>
    {:else if runsError}
      <div class="p-4 text-rose-400 text-sm">{runsError}</div>
    {:else if runs.length === 0}
      <div class="p-4 text-[var(--text-faint)] text-sm">
        No failed runs in the live + historical workflow tables.
      </div>
    {:else if runs[0]?.error}
      <div class="p-4 text-rose-400 text-sm">{runs[0].error}</div>
    {:else}
      <ul>
        {#each runs as r}
          <li>
            <button
              onclick={() => pick(r)}
              class={[
                'w-full text-left px-4 py-3 border-b border-[var(--border-soft)] hover:bg-[var(--bg-panel)]/50',
                selected?.task_id === r.task_id ? 'bg-[var(--bg-panel)]/70' : '',
              ].join(' ')}
            >
              <div
                class="flex items-center justify-between text-xs text-[var(--text-muted)]"
              >
                <span>{fmtTs(r.modified)}</span>
                <span class={statusClass(r.status)}>{r.status}</span>
              </div>
              <div
                class="text-sm text-[var(--text-default)] truncate font-medium mt-0.5"
              >
                {r.name || '(unnamed)'}
              </div>
              {#if r.error_message}
                <div
                  class="text-xs text-[var(--text-faint)] mt-1 truncate"
                  title={r.error_message}
                >
                  {r.error_message}
                </div>
              {/if}
              <div class="text-[10px] text-[var(--text-faint)] mt-0.5">
                {r.source} · {r.task_id?.slice(0, 8) || r.pk}
              </div>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>

  <main class="flex-1 overflow-y-auto">
    {#if !selected}
      <div
        class="h-full flex items-center justify-center text-[var(--text-faint)]"
      >
        Pick a failed run on the left to diagnose it.
      </div>
    {:else if loadingDiag}
      <div class="p-6 text-[var(--text-faint)]">
        Pulling run env + decompiling playbook…
      </div>
    {:else if diagError}
      <div class="p-6 text-rose-400">Diagnostics failed: {diagError}</div>
    {:else if diag && !diag.ok}
      <div class="p-6">
        <h2 class="text-lg font-semibold mb-2">Could not diagnose</h2>
        <div class="text-rose-400 text-sm">
          <code>{diag.code}</code> — {diag.message}
        </div>
      </div>
    {:else if diag}
      <div class="px-6 py-5 border-b border-[var(--border-soft)]">
        <h1 class="text-lg font-semibold">
          {diag.playbook_name || selected.name || '(unknown playbook)'}
        </h1>
        <div class="text-xs text-[var(--text-faint)] mt-1">
          run {diag.pb_execution} · status
          <span class={statusClass(diag.run_status || '')}>
            {diag.run_status}
          </span>
          {#if selected.modified}
            · modified {fmtTs(selected.modified)}
          {/if}
        </div>
        {#if diag.error_message}
          <div
            class="mt-3 rounded border border-rose-700/60 bg-rose-900/20 px-3 py-2 text-sm text-rose-200"
          >
            {diag.error_message}
          </div>
        {/if}
      </div>

      {#if diag.summary}
        <div
          class="px-6 py-3 border-b border-[var(--border-soft)] flex gap-6 text-xs text-[var(--text-muted)]"
        >
          <span>
            <strong class="text-[var(--text-default)]">
              {diag.summary.total_templates}
            </strong>
            Jinja templates
          </span>
          <span>
            <strong
              class={diag.summary.render_failures
                ? 'text-rose-400'
                : 'text-emerald-400'}
            >
              {diag.summary.render_failures}
            </strong>
            render failure{diag.summary.render_failures === 1 ? '' : 's'}
          </span>
          {#if diag.summary.referenced_step_keys?.length}
            <span>
              <strong class="text-[var(--text-default)]">
                {diag.summary.referenced_step_keys.length}
              </strong>
              referenced step keys
            </span>
          {/if}
        </div>
      {/if}

      {#if diag.hints?.length}
        <section class="px-6 py-4 border-b border-[var(--border-soft)]">
          <h2
            class="text-xs uppercase tracking-wide text-[var(--text-faint)] mb-2"
          >
            Hints
          </h2>
          <ul class="space-y-1 text-sm text-[var(--text-muted)] list-disc pl-5">
            {#each diag.hints as h}
              <li>{h}</li>
            {/each}
          </ul>
        </section>
      {/if}

      <section class="px-6 py-4">
        <h2 class="text-sm font-medium text-[var(--text-muted)] mb-3">
          Step diagnostics ({diag.step_diagnostics?.length ?? 0})
        </h2>
        {#if !diag.step_diagnostics?.length}
          <div class="text-[var(--text-faint)] text-sm">
            No per-step diagnostics. The run failed but the YAML's Jinja
            rendered cleanly against the captured env — failure likely
            originated in a connector op or remote side. Check the
            run's error_message above.
          </div>
        {:else}
          <div class="space-y-2">
            {#each diag.step_diagnostics as d}
              <div
                class={[
                  'border-l-2 rounded-r px-3 py-2 text-sm',
                  severityClass(d.severity),
                ].join(' ')}
              >
                <div
                  class="flex items-center justify-between text-xs text-[var(--text-muted)]"
                >
                  <span class="font-medium">
                    {d.step} · {d.location}
                  </span>
                  <span>
                    <code class="text-[var(--text-faint)]">{d.code}</code>
                  </span>
                </div>
                <div class="mt-1 text-[var(--text-default)]">{d.message}</div>
                {#if d.template}
                  <pre
                    class="mt-1 overflow-x-auto rounded bg-[var(--bg-canvas)]/60 p-2 text-xs text-[var(--text-muted)]">{d.template}</pre>
                {/if}
                {#if d.suggestion}
                  <div class="mt-1 text-xs text-emerald-300">
                    → {d.suggestion}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}
  </main>
</div>
