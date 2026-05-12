<script lang="ts">
  /**
   * Render-path analyzer diagnostics list — step-id-keyed bugs that
   * `analyze_playbook` surfaces (unreachable refs, missing keys,
   * required-empty fields, picklist drift). Per-row "Suggest fix"
   * button calls `suggest_fix_for_diagnostic` and surfaces the
   * proposal inline; user accepts to apply.
   */
  import { suggestFixForDiagnostic, type Diagnostic, type SuggestedFix } from '$lib/api';
  import { playbookActions } from '$lib/playbookActions.svelte';

  type Props = {
    onFocusStep?: (stepId: string) => void;
    onApplyFix?: (fix: SuggestedFix) => void;
  };
  let { onFocusStep, onApplyFix }: Props = $props();

  let diagnostics = $derived(playbookActions.diagnostics);
  let pendingFix: Record<string, SuggestedFix> = $state({});
  let busyKey: string | null = $state(null);

  const SEV_GLYPH: Record<string, string> = {
    error: '✗',
    warning: '!',
    info: '·'
  };
  const SEV_CLASS: Record<string, string> = {
    error: 'text-red-600 dark:text-red-400',
    warning: 'text-amber-600 dark:text-amber-400',
    info: 'text-[var(--text-muted)]'
  };

  function rowKey(d: Diagnostic, i: number): string {
    return `${d.step_id}:${d.kind}:${d.location}:${i}`;
  }

  async function requestFix(d: Diagnostic, key: string) {
    busyKey = key;
    try {
      pendingFix[key] = await suggestFixForDiagnostic(d);
    } finally {
      busyKey = null;
    }
  }

  function dismissFix(key: string) {
    delete pendingFix[key];
    pendingFix = { ...pendingFix };
  }
</script>

<div class="flex h-full flex-col overflow-hidden text-sm">
  {#if diagnostics.length === 0}
    <div class="flex h-full items-center justify-center px-6 text-center text-xs text-[var(--text-faint)]">
      No render-path diagnostics. Click <span class="mx-1 font-mono">Analyze</span> in the toolbar to run the validator.
    </div>
  {:else}
    <ul class="flex-1 overflow-auto divide-y divide-[var(--border-soft)]">
      {#each diagnostics as d, i}
        {@const key = rowKey(d, i)}
        {@const fix = pendingFix[key]}
        <li class="px-3 py-2">
          <div class="flex items-start gap-2">
            <span class="mt-0.5 text-base font-bold {SEV_CLASS[d.severity] ?? ''}" aria-hidden="true">{SEV_GLYPH[d.severity] ?? '?'}</span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11px] text-[var(--text-muted)]">
                <button
                  type="button"
                  class="font-mono text-[var(--text-default)] underline-offset-2 hover:underline"
                  onclick={() => onFocusStep?.(d.step_id)}
                  title="Focus this step on the canvas"
                >{d.step_id}</button>
                <span class="rounded bg-[var(--bg-elev,var(--bg-elevated))] px-1.5 py-px text-[10px] font-medium uppercase tracking-wide">{d.kind.replace(/_/g, ' ')}</span>
                {#if d.location}<span class="truncate font-mono text-[10px] text-[var(--text-faint)]" title={d.location}>{d.location}</span>{/if}
              </div>
              <p class="mt-1 text-[12px] text-[var(--text-default)]">{d.message}</p>
              {#if d.suggestion}
                <p class="mt-0.5 text-[11px] italic text-[var(--text-muted)]">→ {d.suggestion}</p>
              {/if}

              {#if fix}
                {#if fix.ok}
                  <div class="mt-2 rounded border border-[var(--brand-ring)] bg-[var(--brand-soft)] px-2 py-1.5 text-[11px]">
                    <div class="mb-1 flex items-center gap-2">
                      <span class="font-semibold text-[var(--text-default)]">Proposed fix</span>
                      <span class="rounded bg-[var(--bg-canvas)] px-1.5 py-px text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{fix.confidence ?? '—'}</span>
                    </div>
                    <p class="mb-1.5 text-[var(--text-default)]">{fix.explanation ?? ''}</p>
                    {#if fix.before !== undefined && fix.after !== undefined}
                      <div class="font-mono text-[10.5px] leading-snug">
                        <div class="text-red-600 dark:text-red-400">- {String(fix.before)}</div>
                        <div class="text-green-600 dark:text-green-400">+ {String(fix.after)}</div>
                      </div>
                    {/if}
                    <div class="mt-1.5 flex gap-2">
                      <button
                        type="button"
                        class="rounded bg-[var(--brand)] px-2 py-0.5 text-[10px] font-semibold text-[var(--brand-fg)] hover:opacity-90"
                        onclick={() => { onApplyFix?.(fix); dismissFix(key); }}
                      >Apply</button>
                      <button
                        type="button"
                        class="rounded border border-[var(--border-soft)] px-2 py-0.5 text-[10px] hover:bg-[var(--bg-elev,var(--bg-elevated))]"
                        onclick={() => dismissFix(key)}
                      >Dismiss</button>
                    </div>
                  </div>
                {:else}
                  <div class="mt-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev,var(--bg-elevated))] px-2 py-1.5 text-[11px] italic text-[var(--text-muted)]">
                    {fix.reason ?? 'no auto-fix recipe matched'}
                    <button
                      type="button"
                      class="ml-2 not-italic underline"
                      onclick={() => dismissFix(key)}
                    >dismiss</button>
                  </div>
                {/if}
              {:else}
                <button
                  type="button"
                  class="mt-1 rounded border border-[var(--border-soft)] bg-transparent px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)] hover:bg-[var(--bg-elev,var(--bg-elevated))] hover:text-[var(--text-default)] disabled:opacity-50"
                  disabled={busyKey === key}
                  onclick={() => requestFix(d, key)}
                >{busyKey === key ? 'thinking…' : 'Suggest fix'}</button>
              {/if}
            </div>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>
