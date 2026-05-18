<script lang="ts">
  /**
   * Step debugger — drives `step_through_playbook` against the
   * current YAML buffer. Phase 5 ticket from VERIFY_PLAYBOOK_PLAN.md.
   *
   * The user supplies simulated inputs (free-form JSON) and optional
   * branch/manual choices to pin paths; the panel renders one row per
   * step the engine walked, showing rendered args + the synthesized
   * output. Read-only — connector ops on the safe-read allowlist are
   * executed live when `executeSafeOps=true` and a live FSR is
   * configured; everything else is simulated.
   */
  import { playbookStore } from '$lib/playbookStore.svelte';
  import { stepThroughPlaybook, type StepTraceRow } from '$lib/api';

  let inputJson = $state('{}');
  let branchJson = $state('{}');
  let manualJson = $state('{}');
  let executeSafeOps = $state(false);
  let busy = $state(false);
  let trace = $state<StepTraceRow[]>([]);
  let firstError = $state<{ step_id: string; message: string } | null>(null);
  let errorMsg = $state<string | null>(null);

  function parseJsonOrEmpty(s: string): Record<string, any> | string {
    const trimmed = s.trim();
    if (!trimmed) return {};
    try {
      const v = JSON.parse(trimmed);
      if (v && typeof v === 'object' && !Array.isArray(v)) return v;
      return `expected a JSON object, got ${typeof v}`;
    } catch (e: any) {
      return `invalid JSON: ${e?.message ?? e}`;
    }
  }

  async function run() {
    const yaml = playbookStore.yaml;
    if (!yaml) {
      errorMsg = 'no playbook loaded';
      return;
    }
    const input = parseJsonOrEmpty(inputJson);
    if (typeof input === 'string') { errorMsg = `input: ${input}`; return; }
    const branch = parseJsonOrEmpty(branchJson);
    if (typeof branch === 'string') { errorMsg = `branch: ${branch}`; return; }
    const manual = parseJsonOrEmpty(manualJson);
    if (typeof manual === 'string') { errorMsg = `manual: ${manual}`; return; }

    busy = true;
    errorMsg = null;
    try {
      const r = await stepThroughPlaybook(yaml, {
        input: input as Record<string, unknown>,
        branchChoices: branch as Record<string, string>,
        manualChoices: manual as Record<string, string>,
        executeSafeOps
      });
      trace = r.trace;
      firstError = r.first_error ?? null;
      if (!r.ok && !r.first_error) {
        errorMsg = r.error ?? 'step-through failed';
      }
    } catch (e: any) {
      errorMsg = e?.message ?? String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex h-full flex-col overflow-hidden text-xs">
  <div class="grid grid-cols-3 gap-2 border-b border-[var(--border-soft)] p-2">
    <label class="flex flex-col gap-1">
      <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        vars.input.params (JSON)
      </span>
      <textarea
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-1 font-mono text-[11px]"
        rows="3"
        bind:value={inputJson}
        placeholder={'{"ip": "1.2.3.4"}'}
      ></textarea>
    </label>
    <label class="flex flex-col gap-1">
      <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        branch choices (decision step_id → label)
      </span>
      <textarea
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-1 font-mono text-[11px]"
        rows="3"
        bind:value={branchJson}
        placeholder={'{"d1": "yes"}'}
      ></textarea>
    </label>
    <label class="flex flex-col gap-1">
      <span class="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        manual_input choices (step_id → option)
      </span>
      <textarea
        class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-1 font-mono text-[11px]"
        rows="3"
        bind:value={manualJson}
        placeholder={'{"mi": "approve"}'}
      ></textarea>
    </label>
  </div>
  <div class="flex items-center gap-3 border-b border-[var(--border-soft)] px-2 py-1.5">
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)] disabled:opacity-60"
      onclick={run}
      disabled={busy}
    >{busy ? 'Stepping…' : 'Step Through'}</button>
    <label class="flex items-center gap-1.5">
      <input type="checkbox" bind:checked={executeSafeOps} />
      <span>execute_safe_ops (read-only ops only)</span>
    </label>
    {#if errorMsg}
      <span class="text-rose-500">{errorMsg}</span>
    {/if}
    {#if firstError}
      <span class="text-amber-500">
        first error at {firstError.step_id}: {firstError.message}
      </span>
    {/if}
  </div>
  <div class="flex-1 overflow-auto">
    {#if trace.length === 0}
      <div class="flex h-full items-center justify-center text-[var(--text-faint)]">
        Press <span class="mx-1 font-mono">Step Through</span> to simulate the playbook
      </div>
    {:else}
      <table class="w-full border-collapse text-[11px]">
        <thead class="sticky top-0 bg-[var(--bg-canvas)] text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
          <tr>
            <th class="border-b border-[var(--border-soft)] px-2 py-1 text-left">#</th>
            <th class="border-b border-[var(--border-soft)] px-2 py-1 text-left">step</th>
            <th class="border-b border-[var(--border-soft)] px-2 py-1 text-left">type</th>
            <th class="border-b border-[var(--border-soft)] px-2 py-1 text-left">status</th>
            <th class="border-b border-[var(--border-soft)] px-2 py-1 text-left">output keys</th>
            <th class="border-b border-[var(--border-soft)] px-2 py-1 text-left">note</th>
          </tr>
        </thead>
        <tbody>
          {#each trace as row, i}
            <tr class="border-b border-[var(--border-soft)] align-top">
              <td class="px-2 py-1 text-[var(--text-faint)]">{i + 1}</td>
              <td class="px-2 py-1 font-mono">{row.step_id}</td>
              <td class="px-2 py-1">{row.type ?? '?'}</td>
              <td class="px-2 py-1">
                <span class:text-emerald-500={row.status === 'ok'} class:text-rose-500={row.status === 'error'}>
                  {row.status ?? '–'}
                </span>
              </td>
              <td class="px-2 py-1 font-mono text-[var(--text-muted)]">
                {(row.output_top_keys ?? []).join(', ') || '–'}
              </td>
              <td class="px-2 py-1 text-[var(--text-muted)]">{row.note ?? ''}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>
