<script lang="ts">
  import { runStore } from '$lib/runStore.svelte';
  import { getRunEnv, type EnvResult } from '$lib/api';

  let env = $state<EnvResult | null>(null);
  let envErr = $state<string | null>(null);
  let manualPk = $state('');
  let logEl: HTMLDivElement | undefined;

  $effect(() => {
    void runStore.logs.length;
    queueMicrotask(() => logEl?.scrollTo({ top: logEl.scrollHeight }));
  });

  async function loadEnv(pk: string) {
    if (!pk) return;
    envErr = null;
    try {
      env = await getRunEnv(pk);
      if (!env.ok) envErr = env.error ?? 'env lookup failed';
    } catch (e: any) {
      envErr = e?.message ?? String(e);
    }
  }

  $effect(() => {
    if (runStore.status === 'done' && runStore.taskId && !env) loadEnv(runStore.taskId);
  });

  const dotColor = $derived(
    runStore.status === 'done'
      ? 'bg-green-500'
      : runStore.status === 'error'
        ? 'bg-red-500'
        : runStore.status === 'running' || runStore.status === 'pushing'
          ? 'bg-yellow-500 animate-pulse'
          : 'bg-[var(--text-faint)]'
  );
</script>

<div class="grid h-full grid-cols-[minmax(0,1fr)_minmax(320px,30rem)]">
  <div class="flex min-h-0 flex-col border-r border-[var(--border-soft)]">
    <div class="flex items-center gap-2 border-b border-[var(--border-soft)] px-3 py-1.5 text-xs">
      <span class="h-2 w-2 rounded-full {dotColor}"></span>
      <span class="text-[var(--text-muted)]">{runStore.status}</span>
      {#if runStore.taskId}
        <span class="text-[var(--text-faint)]">task {runStore.taskId.slice(0, 8)}…</span>
      {/if}
      {#if runStore.exitCode !== null}
        <span class="text-[var(--text-faint)]">exit {runStore.exitCode}</span>
      {/if}
      <button
        class="ml-auto rounded border border-[var(--border)] px-2 py-0.5 hover:bg-[var(--bg-elevated)]"
        onclick={() => runStore.reset()}
      >
        clear
      </button>
    </div>
    <div bind:this={logEl} class="min-h-0 flex-1 overflow-auto p-3 font-mono text-xs">
      {#if runStore.pushOutput}
        <div class="mb-2">
          <div class="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-faint)]">push</div>
          <pre class="whitespace-pre-wrap text-[var(--text-muted)]">{runStore.pushOutput}</pre>
        </div>
      {/if}
      {#if runStore.logs.length}
        <div class="mb-1 text-[10px] uppercase tracking-wide text-[var(--text-faint)]">run logs</div>
        {#each runStore.logs as line}
          <div class="whitespace-pre-wrap text-[var(--text-default)]">{line}</div>
        {/each}
      {:else if runStore.status === 'idle'}
        <div class="text-[var(--text-faint)]">No active run. Press Run on the Author tab.</div>
      {/if}
      {#if runStore.errorMsg}
        <div class="mt-2 rounded border border-red-900 bg-red-950/40 p-2 text-red-300">
          {runStore.errorMsg}
        </div>
      {/if}
    </div>
  </div>

  <aside class="flex min-h-0 flex-col p-4">
    <h2 class="text-sm font-semibold text-[var(--text-muted)]">Run env</h2>
    <p class="mt-1 text-xs text-[var(--text-faint)]">
      Rebuilt <code>vars</code> tree from <code>fsrpb env</code> (workflow PK or task UUID).
    </p>
    <div class="mt-3 flex gap-2">
      <input
        class="flex-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-xs"
        placeholder="task_id or pk"
        bind:value={manualPk}
      />
      <button
        class="rounded border border-[var(--border)] px-2 py-1 text-xs hover:bg-[var(--bg-elevated)]"
        onclick={() => loadEnv(manualPk)}>load</button
      >
    </div>
    {#if envErr}
      <div class="mt-3 rounded border border-red-900 bg-red-950/40 p-2 text-xs text-red-300">
        {envErr}
      </div>
    {/if}
    {#if env?.ok && env.env}
      <pre
        class="mt-3 min-h-0 flex-1 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-2 font-mono text-[11px] text-[var(--text-default)]">{JSON.stringify(
          env.env,
          null,
          2
        )}</pre>
    {/if}
  </aside>
</div>
