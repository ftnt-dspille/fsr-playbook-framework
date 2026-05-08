<script lang="ts">
  /**
   * Combined Push + Run output. One tab instead of two — the user
   * almost always wants to see both side-by-side ("did the push land,
   * and what did the run say?"). Top half shows push stdout/stderr;
   * bottom half shows the streaming run logs. Both expose status
   * badges and the same Console widget (so URL linkification, copy,
   * autoscroll all carry over).
   */
  import Console from './Console.svelte';
  import { runStore, type RunStatus } from '$lib/runStore.svelte';

  function statusBadge(status: RunStatus, kind: 'push' | 'run') {
    if (kind === 'push') {
      if (status === 'pushing')
        return { label: 'pushing…', cls: 'border-amber-500/40 bg-amber-500/10 text-amber-200' };
      if (status === 'error' && !runStore.logs.length)
        return { label: 'error', cls: 'border-rose-500/40 bg-rose-500/10 text-rose-300' };
      if (runStore.pushOutput)
        return { label: 'pushed', cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' };
      return null;
    }
    // run
    if (status === 'running')
      return { label: 'running…', cls: 'border-amber-500/40 bg-amber-500/10 text-amber-200' };
    if (status === 'done' && runStore.exitCode === 0)
      return { label: 'done', cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' };
    if (runStore.exitCode !== null && runStore.exitCode !== 0)
      return { label: `exit ${runStore.exitCode}`, cls: 'border-rose-500/40 bg-rose-500/10 text-rose-300' };
    if (status === 'error' && runStore.logs.length)
      return { label: 'error', cls: 'border-rose-500/40 bg-rose-500/10 text-rose-300' };
    return null;
  }

  const pushBadge = $derived(statusBadge(runStore.status, 'push'));
  const runBadge = $derived(statusBadge(runStore.status, 'run'));

  let pushCopied = $state(false);
  let runCopied = $state(false);

  async function copyText(s: string, which: 'push' | 'run') {
    if (!s) return;
    try {
      await navigator.clipboard.writeText(s);
      if (which === 'push') {
        pushCopied = true;
        setTimeout(() => (pushCopied = false), 1200);
      } else {
        runCopied = true;
        setTimeout(() => (runCopied = false), 1200);
      }
    } catch {
      /* ignore clipboard errors */
    }
  }

  const pushLineCount = $derived(
    runStore.pushOutput ? runStore.pushOutput.split('\n').length : 0,
  );
  const runLineCount = $derived(runStore.logs.length);
</script>

<!-- Push usually emits 1–4 lines; Run streams indefinitely. A 50/50
     split wasted half the panel on push and starved run. Push takes a
     fixed minimum (so it always renders), capped at 35% so a noisy push
     can't crowd out run. We can't use `auto` here — Console's body uses
     h-full, which collapses to 0 inside an auto-sized grid row. -->
<div class="grid h-full min-h-0 grid-rows-[minmax(110px,35%)_minmax(0,1fr)] divide-y divide-[var(--border-soft)]">
  <!-- Push section. Sized by the parent grid row (110px–35%); flex-col
       inside so the body fills below the header. -->
  <section class="flex min-h-0 flex-col">
    <header class="flex items-center gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-panel)]/60 px-3 py-1 text-[11px] uppercase tracking-wider text-[var(--text-faint)]">
      <span class="font-semibold">Push</span>
      {#if pushBadge}
        <span class={'rounded-full border px-1.5 py-0 text-[10px] font-medium normal-case tracking-normal ' + pushBadge.cls}>
          {pushBadge.label}
        </span>
      {/if}
      {#if runStore.errorMsg && runStore.status === 'error' && !runStore.logs.length}
        <span class="ml-2 truncate text-rose-300 normal-case tracking-normal">{runStore.errorMsg}</span>
      {/if}
      <div class="ml-auto flex items-center gap-1.5">
        {#if pushLineCount}
          <span class="rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0 font-mono text-[10px] normal-case tracking-normal text-[var(--text-muted)]">
            {pushLineCount} {pushLineCount === 1 ? 'line' : 'lines'}
          </span>
          <button
            type="button"
            onclick={() => copyText(runStore.pushOutput ?? '', 'push')}
            class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0 text-[10px] font-medium normal-case tracking-normal text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
          >
            {pushCopied ? '✓ copied' : 'copy'}
          </button>
        {/if}
      </div>
    </header>
    <div class="min-h-0 flex-1">
      <Console
        text={runStore.pushOutput ?? ''}
        showToolbar={false}
        emptyTitle="No push attempted"
        emptyHint="Push compiles the YAML and PUTs/POSTs the collection."
      />
    </div>
  </section>

  <!-- Run section -->
  <section class="flex min-h-0 flex-col">
    <header class="flex items-center gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-panel)]/60 px-3 py-1 text-[11px] uppercase tracking-wider text-[var(--text-faint)]">
      <span class="font-semibold">Run</span>
      {#if runBadge}
        <span class={'rounded-full border px-1.5 py-0 text-[10px] font-medium normal-case tracking-normal ' + runBadge.cls}>
          {runBadge.label}
        </span>
      {/if}
      {#if runStore.taskId}
        <span class="rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0 font-mono text-[10px] normal-case tracking-normal text-[var(--text-muted)]" title={runStore.taskId}>
          task {runStore.taskId.slice(0, 8)}…
        </span>
      {/if}
      {#if runStore.errorMsg && runStore.logs.length}
        <span class="ml-2 truncate text-rose-300 normal-case tracking-normal">{runStore.errorMsg}</span>
      {/if}
      <div class="ml-auto flex items-center gap-1.5">
        {#if runLineCount}
          <span class="rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0 font-mono text-[10px] normal-case tracking-normal text-[var(--text-muted)]">
            {runLineCount} {runLineCount === 1 ? 'line' : 'lines'}
          </span>
          <button
            type="button"
            onclick={() => copyText(runStore.logs.join('\n'), 'run')}
            class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0 text-[10px] font-medium normal-case tracking-normal text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
          >
            {runCopied ? '✓ copied' : 'copy'}
          </button>
        {/if}
      </div>
    </header>
    <div class="min-h-0 flex-1">
      <Console
        lines={runStore.logs}
        autoScroll
        showToolbar={false}
        emptyTitle="No active run"
        emptyHint="Push & Run pushes the playbook then triggers it via fsrpb run-playbook --follow."
      />
    </div>
  </section>
</div>
