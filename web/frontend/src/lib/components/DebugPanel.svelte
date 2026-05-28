<script lang="ts">
  /**
   * Debug runner — drives stateful server-side debug sessions
   * (VISUAL_EDITOR_PLAN.md Phase 5.3-5.7).
   *
   *   ▶ Run     create a session and continue to done / breakpoint
   *   ⏭ Step    advance one step
   *   ⏹ Stop    drop the session
   *
   * Click a tile to inspect; shift-click / dbl-click to toggle a
   * breakpoint. When execution pauses at a `decision` or
   * `manual_input` step, an inline branch chooser appears so the
   * next ⏭ Step takes the picked branch (5.4). The trigger payload
   * editor (5.7) lets the user shape `vars.input` before Run;
   * the Watch panel (5.5) pins `vars.steps.X.Y` paths and resolves
   * them from the live trace.
   *
   * Breakpoints + watch paths + trigger input live in `debugStore`
   * so they survive drawer collapse and are visible to the canvas
   * (red breakpoint dot on each node — VISUAL_EDITOR_PLAN 5.4 tail).
   */
  import { playbookStore } from '$lib/playbookStore.svelte';
  import { visualStore } from '$lib/visualEditStore.svelte';
  import {
    startDebugSession,
    stepDebugSession,
    continueDebugSession,
    stopDebugSession,
    type DebugStepFrame,
    type DebugSessionStatus,
    type VisualNode,
    type VisualEdge,
  } from '$lib/api';
  import { debugStore, resolvePath, varsFromTrace } from '$lib/debugStore.svelte';

  let busy = $state(false);
  let status = $state<DebugSessionStatus | null>(null);
  let error = $state<string | null>(null);
  let selectedIdx = $state<number>(-1);
  let lastStopReason = $state<string | null>(null);
  let triggerOpen = $state(false);
  let watchOpen = $state(true);
  let watchDraft = $state('');

  let sessionId = $derived(status?.session_id ?? null);
  let trace = $derived<DebugStepFrame[]>(status?.trace ?? []);
  let breakpoints = $derived<Set<string>>(debugStore.breakpoints);
  let pausedAt = $derived(status?.paused_at ?? null);
  let done = $derived(status?.done ?? false);
  let selected = $derived<DebugStepFrame | null>(
    selectedIdx >= 0 && selectedIdx < trace.length ? trace[selectedIdx] : null
  );

  // Pull the current playbook's nodes/edges so we can offer branch
  // choices when paused at a decision / manual_input step (5.4).
  let activeNodes = $derived<VisualNode[]>(
    visualStore.state.graph?.playbooks?.[0]?.nodes ?? []
  );
  let activeEdges = $derived<VisualEdge[]>(
    visualStore.state.graph?.playbooks?.[0]?.edges ?? []
  );
  let triggerStepId = $derived<string | null>(
    visualStore.state.graph?.playbooks?.[0]?.trigger_step_id ?? null
  );

  // When paused, what kind of step are we about to execute and what
  // branches does it expose? `pausedAt` is the step ID we will run
  // on the next Step click — its outgoing `branch_kind === 'branch'`
  // edges are the choices.
  let pausedNode = $derived<VisualNode | null>(
    pausedAt ? (activeNodes.find((n) => n.id === pausedAt) ?? null) : null
  );
  let pausedBranches = $derived(
    pausedNode && (pausedNode.family === 'decision' || pausedNode.family === 'manual_input')
      ? activeEdges
          .filter((e) => e.source === pausedNode!.id && e.branch_kind === 'branch')
          .map((e) => ({ label: e.label ?? e.target, target: e.target }))
      : []
  );

  // Live vars tree for the Watch panel — stitched from the trace
  // outputs, mirroring both the raw step id and its space→underscore
  // jkey form so authors can paste whichever form they remembered.
  let liveVars = $derived(varsFromTrace(trace));

  async function ensureSession(): Promise<string | null> {
    const yaml = playbookStore.currentYaml;
    if (!yaml) {
      error = 'no playbook loaded';
      return null;
    }
    if (sessionId && !done) return sessionId;
    if (sessionId) await stopDebugSession(sessionId);
    const parsed = debugStore.parseTriggerInputStrict();
    if (!parsed.ok) {
      error = `trigger input: ${parsed.error}`;
      return null;
    }
    const r = await startDebugSession(yaml, {
      executeSafeOps: true,
      input: parsed.value,
    });
    if (!r.ok || !r.status) {
      error = r.error ?? 'session start failed';
      status = null;
      return null;
    }
    status = r.status;
    return r.status.session_id;
  }

  async function run() {
    busy = true;
    error = null;
    selectedIdx = -1;
    lastStopReason = null;
    try {
      const sid = await ensureSession();
      if (!sid) return;
      const r = await continueDebugSession(sid, { addBreakpoints: [...breakpoints] });
      if (!r.ok || !r.status) {
        error = r.error ?? 'continue failed';
        return;
      }
      status = r.status;
      lastStopReason = r.stop_reason ?? null;
      if (status.first_error) {
        const idx = trace.findIndex((f) => f.step_id === status!.first_error!.step_id);
        selectedIdx = idx >= 0 ? idx : trace.length - 1;
      } else if (trace.length > 0) {
        selectedIdx = trace.length - 1;
      }
    } finally {
      busy = false;
    }
  }

  // Stepper. Optional `branchOverride` lets the inline branch chooser
  // pin the next-step routing for this one advance.
  async function step(branchOverride?: Record<string, string>) {
    busy = true;
    error = null;
    lastStopReason = null;
    try {
      const sid = await ensureSession();
      if (!sid) return;
      let r = await stepDebugSession(sid, branchOverride);
      if (!r.ok || !r.status) {
        error = r.error ?? 'step failed';
        return;
      }
      status = r.status;
      // Auto-skip the trivial trigger entry so the first Step lands
      // on a step that's actually interesting.
      if (r.status.last_step?.step_id
          && (r.status.last_step.type ?? '').startsWith('start')
          && !r.status.done) {
        try {
          const r2 = await stepDebugSession(sid);
          if (r2.ok && r2.status) status = r2.status;
        } catch { /* trivial */ }
      }
      selectedIdx = trace.length - 1;
    } finally {
      busy = false;
    }
  }

  // Take a chosen branch at the currently-paused step. The override
  // map is keyed by step id so the server routes JUST this advance.
  async function chooseBranch(stepId: string, label: string) {
    await step({ [stepId]: label });
  }

  async function stop() {
    if (!sessionId) {
      status = null;
      selectedIdx = -1;
      return;
    }
    busy = true;
    try {
      const r = await stopDebugSession(sessionId);
      if (r.ok && r.status) {
        status = { ...r.status, done: true };
      } else {
        status = null;
      }
      selectedIdx = -1;
    } finally {
      busy = false;
    }
  }

  function statusClass(s: string): string {
    if (s === 'ok' || s === 'finished' || s === 'simulated' || s === 'executed') {
      return 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20';
    }
    if (s === 'error' || s === 'exec_failed') {
      return 'border-rose-500 bg-rose-50 dark:bg-rose-900/20';
    }
    if (s === 'skipped' || s === 'unsafe_placeholder') {
      return 'border-amber-500 bg-amber-50 dark:bg-amber-900/20';
    }
    return 'border-[var(--border)] bg-[var(--bg-elev)]';
  }

  function formatWatchValue(v: unknown): string {
    if (v === undefined) return '—';
    if (v === null) return 'null';
    if (typeof v === 'string') return v;
    try { return JSON.stringify(v); } catch { return String(v); }
  }

  function addWatchDraft() {
    if (!watchDraft.trim()) return;
    debugStore.addWatch(watchDraft);
    watchDraft = '';
  }
</script>

<div class="flex h-full flex-col">
  <!-- Run controls -->
  <div class="flex items-center gap-2 border-b border-[var(--border-soft)] px-3 py-2">
    <button
      type="button"
      class="rounded border border-[var(--brand)] bg-[var(--brand)] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
      onclick={() => run()}
      disabled={busy}
      title={done ? 'Drop the current trace and run again' : 'Run the playbook through to the end (or next breakpoint)'}
    >{done && sessionId ? '↺ Restart' : '▶ Run'}</button>
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={() => step()}
      disabled={busy || done}
      title="Advance one step (creates a session on first click)"
    >⏭ Step</button>
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-1 text-xs font-medium hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={stop}
      disabled={busy || !sessionId}
      title="Drop the session (trace stays visible for inspection)"
    >⏹ Stop</button>

    {#if status}
      <span class="ml-2 text-[11px] text-[var(--text-muted)]">
        {status.steps_advanced ?? 0} step(s)
        {#if busy}
          · <span class="inline-flex items-center gap-1 text-[var(--brand)]">
              <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand)]"></span>
              advancing…
            </span>
        {:else if pausedAt && !done}
          · paused at <span class="font-mono">{pausedAt}</span>
        {/if}
        {#if done}
          · <span class="text-emerald-600 dark:text-emerald-400">done</span>
        {/if}
        {#if lastStopReason && lastStopReason !== 'done' && !busy}
          · {lastStopReason.replace('_', ' ')}
        {/if}
        {#if status.first_error}
          · <span class="text-rose-600 dark:text-rose-400 font-medium">err: {status.first_error.step_id}</span>
        {/if}
      </span>
    {/if}
    <div class="ml-auto text-[10px] text-[var(--text-faint)]">
      shift-click a tile to toggle a breakpoint
    </div>
  </div>

  <!-- Trigger payload editor (5.7) — collapsed by default; expanded
       reveals a JSON editor that seeds `vars.input` on Run. Disabled
       once a session exists (would be ignored anyway). -->
  <details
    class="border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1.5 text-[11px]"
    bind:open={triggerOpen}
  >
    <summary class="cursor-pointer select-none text-[var(--text-muted)] hover:text-[var(--text-default)]">
      Trigger input
      {#if triggerStepId}
        <span class="ml-1 font-mono text-[10px] text-[var(--text-faint)]">→ {triggerStepId}</span>
      {/if}
      {#if sessionId && !done}
        <span class="ml-2 text-[10px] text-[var(--text-faint)]">(locked while session active)</span>
      {:else if debugStore.triggerInputJson.trim() && debugStore.triggerInputJson.trim() !== '{}'}
        <span class="ml-2 text-[10px] text-emerald-500">armed</span>
      {/if}
    </summary>
    <div class="mt-1.5">
      <p class="mb-1 text-[10px] text-[var(--text-faint)]">
        JSON object seeded as <code class="rounded bg-[var(--bg-elev)] px-1">vars.input.params</code> on the next Run. Empty / <code>{'{}'}</code> means no override.
      </p>
      <textarea
        class="block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px] text-[var(--text-default)] focus:outline-none focus:ring-1 focus:ring-[var(--brand)]"
        rows="4"
        spellcheck="false"
        placeholder={'{ "ip": "1.1.1.1" }'}
        disabled={!!(sessionId && !done)}
        bind:value={debugStore.triggerInputJson}
      ></textarea>
    </div>
  </details>

  {#if error}
    <div class="border-b border-rose-300 bg-rose-50 px-3 py-1.5 text-xs text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">{error}</div>
  {/if}

  <!-- Body: trace tape (left) + detail (right) -->
  <div class="grid h-full min-h-0 grid-cols-[260px_1fr]">
    <!-- Trace tape -->
    <div class="flex min-h-0 flex-col overflow-hidden border-r border-[var(--border-soft)]">
      <div class="min-h-0 flex-1 overflow-y-auto p-2">
      {#if !status}
        <p class="px-1 py-2 text-xs text-[var(--text-faint)]">
          Press <strong>▶ Run</strong> to walk the playbook end-to-end.
          Or <strong>⏭ Step</strong> to advance one tile at a time.
          Shift-click a tile to set a breakpoint before re-running.
        </p>
      {:else if trace.length === 0 && !pausedAt}
        <p class="px-1 py-2 text-xs text-[var(--text-faint)]">no steps walked yet</p>
      {:else}
        {#each trace as frame, i}
          {@const isBp = breakpoints.has(frame.step_id)}
          <button
            type="button"
            class={'mb-1.5 w-full rounded border-l-2 px-2 py-1.5 text-left transition-colors ' +
              statusClass(frame.status) +
              (i === selectedIdx ? ' ring-2 ring-[var(--brand)]' : '') +
              (isBp ? ' outline outline-1 outline-rose-500' : '')}
            onclick={(e) => {
              if (e.shiftKey) {
                debugStore.toggleBreakpoint(frame.step_id);
              } else {
                selectedIdx = i;
              }
            }}
            ondblclick={() => debugStore.toggleBreakpoint(frame.step_id)}
            title="click to inspect · shift-click or dbl-click to toggle breakpoint"
          >
            <div class="flex items-baseline justify-between gap-2">
              <span class="font-mono text-xs font-medium text-[var(--text-default)]">
                {isBp ? '● ' : ''}{i + 1}. {frame.step_id}
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
        {#if pausedAt && !done}
          <div class="mt-1 rounded border border-dashed border-[var(--brand)] bg-[var(--brand)]/10 px-2 py-1.5 text-[11px] font-mono text-[var(--text-default)]">
            <div class="text-center">▶ paused at <strong>{pausedAt}</strong></div>

            <!-- Branch chooser (5.4) — only shown when the paused step
                 is a decision / manual_input with branches. Click a
                 chip to step with `branch_choice_override` pinned. -->
            {#if pausedBranches.length > 0}
              <div class="mt-1.5 border-t border-[var(--brand)]/30 pt-1.5">
                <div class="mb-1 text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
                  pick branch
                </div>
                <div class="flex flex-wrap gap-1">
                  {#each pausedBranches as b}
                    <button
                      type="button"
                      class="rounded border border-[var(--brand)]/50 bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-default)] hover:bg-[var(--brand)] hover:text-white disabled:opacity-50"
                      disabled={busy}
                      title={`Take this branch on the next step → ${b.target}`}
                      onclick={() => chooseBranch(pausedAt!, b.label)}
                    >{b.label}</button>
                  {/each}
                </div>
              </div>
            {/if}
          </div>
        {/if}
      {/if}
      </div>

      <!-- Watch panel (5.5) — resolved client-side against the
           stitched trace, so it updates after every Step / Run. -->
      <details
        class="shrink-0 border-t border-[var(--border-soft)] bg-[var(--bg-canvas)] p-2 text-[11px]"
        bind:open={watchOpen}
      >
        <summary class="cursor-pointer select-none text-[var(--text-muted)] hover:text-[var(--text-default)]">
          Watch ({debugStore.watchPaths.length})
        </summary>
        <div class="mt-1.5 space-y-1">
          {#each debugStore.watchPaths as path}
            {@const value = resolvePath(liveVars, path)}
            <div class="flex items-start gap-1.5">
              <button
                type="button"
                class="mt-0.5 text-[10px] text-[var(--text-faint)] hover:text-rose-500"
                title="Remove watch"
                onclick={() => debugStore.removeWatch(path)}
              >×</button>
              <div class="min-w-0 flex-1">
                <div class="truncate font-mono text-[10px] text-[var(--text-muted)]" title={path}>{path}</div>
                <div class={'truncate font-mono text-[11px] ' + (value === undefined ? 'text-[var(--text-faint)]' : 'text-[var(--text-default)]')} title={formatWatchValue(value)}>
                  {formatWatchValue(value)}
                </div>
              </div>
            </div>
          {/each}
          <div class="flex items-center gap-1 pt-1">
            <input
              type="text"
              class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-default)] focus:outline-none focus:ring-1 focus:ring-[var(--brand)]"
              placeholder="vars.steps.X.field"
              bind:value={watchDraft}
              onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addWatchDraft(); } }}
            />
            <button
              type="button"
              class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 text-[10px] hover:bg-[var(--bg-canvas)] disabled:opacity-50"
              disabled={!watchDraft.trim()}
              onclick={addWatchDraft}
            >+</button>
          </div>
        </div>
      </details>
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
        <!-- Output first — that's what downstream Jinja reads, so
             it's the primary debugging target. Step input below is
             collapsed by default; expand it to see the rendered
             prompt / args FSR would receive. -->
        <div class="mb-3">
          <div class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            Output{selected.output_top_keys?.length ? ` (keys: ${selected.output_top_keys.join(', ')})` : ''}
          </div>
          <pre class="overflow-x-auto rounded border border-emerald-500/30 bg-[var(--bg-elev)] p-2 text-[11px] font-mono text-[var(--text-default)]">{JSON.stringify(selected.output, null, 2)}</pre>
        </div>
        <details>
          <summary class="mb-1 cursor-pointer select-none text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)] hover:text-[var(--text-muted)]">
            Step input (rendered args)
          </summary>
          <pre class="overflow-x-auto rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2 text-[11px] font-mono text-[var(--text-muted)]">{JSON.stringify(selected.rendered_args, null, 2)}</pre>
        </details>
      {/if}
    </div>
  </div>
</div>
