<script lang="ts">
  /**
   * Bottom output drawer — issues (markers + render-path + fix actions),
   * compile JSON, and deploy logs. Mode-agnostic: shown under both
   * Design and CLI.
   *
   * Fix apply depends on Monaco refs (executeEdits goes through the
   * editor's undo stack). Design has no Monaco, so the per-row Apply
   * button self-disables with an explanation tooltip.
   */
  import DiagnosticsList from './DiagnosticsList.svelte';
  import RenderPathDiagnostics from './RenderPathDiagnostics.svelte';
  import DeployPanel from './DeployPanel.svelte';
  import { playbookActions } from '$lib/playbookActions.svelte';
  import { runStore } from '$lib/runStore.svelte';
  import { visualStore } from '$lib/visualEditStore.svelte';
  import type { SuggestedFix } from '$lib/api';

  type Tab = 'diagnostics' | 'fixes' | 'deploy';
  type Props = {
    open: boolean;
    tab: Tab;
    heightPx: number;
    onTabChange: (t: Tab) => void;
    onToggle: () => void;
    onResize: (e: PointerEvent) => void;
    monacoEditor?: any;
    monacoNs?: any;
    onYamlReplace?: (next: string) => void;
  };
  let {
    open, tab, heightPx,
    onTabChange, onToggle, onResize,
    monacoEditor, monacoNs, onYamlReplace
  }: Props = $props();

  let markers = $derived(playbookActions.markers);
  let fixes = $derived(playbookActions.fixes);
  let errCount = $derived(playbookActions.errorCount);
  let warnCount = $derived(playbookActions.warningCount);

  // Legacy 'fixes' / 'compile' tab ids now route to the merged Issues view.
  let effectiveTab = $derived(
    tab === 'fixes' || (tab as string) === 'compile' ? 'diagnostics' : tab
  );

  /** Render-path "Apply" handler. */
  async function applyRenderPathFix(fix: SuggestedFix): Promise<void> {
    if (!fix.ok || !fix.location || fix.before === undefined
        || fix.after === undefined || !fix.step_id) {
      console.warn('apply: incomplete fix', fix);
      return;
    }
    const updated = await visualStore.applyTextSwap?.({
      stepId: fix.step_id,
      location: fix.location,
      before: String(fix.before),
      after: String(fix.after)
    });
    if (!updated) {
      console.warn('apply: visualStore could not locate the swap target', fix);
      return;
    }
    await playbookActions.analyze();
  }
</script>

<div class="border-t border-[var(--border-soft)] bg-[var(--bg-panel)]">
  {#if open}
    <div
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize output drawer"
      class="group relative flex h-1.5 cursor-ns-resize items-center justify-center bg-transparent hover:bg-[var(--brand)]/20"
      onpointerdown={onResize}
    >
      <span class="h-0.5 w-12 rounded-full bg-[var(--border)] group-hover:bg-[var(--brand)]"></span>
    </div>
  {/if}
  <div class="flex items-center gap-1 border-b border-[var(--border-soft)] px-2 py-1.5">
    {#each [
      { id: 'diagnostics' as Tab, label: 'Issues' },
      { id: 'deploy' as Tab, label: 'Deploy' }
    ] as t}
      {@const active = effectiveTab === t.id && open}
      <button
        type="button"
        class={'group relative flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ' +
          (active
            ? 'bg-[var(--bg-elevated)] text-[var(--text-default)] shadow-[0_0_0_1px_var(--border)]'
            : 'text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]/50 hover:text-[var(--text-default)]')}
        onclick={() => onTabChange(t.id)}
      >
        <span>{t.label}</span>
        {#if t.id === 'diagnostics'}
          {#if errCount}<span class="rounded-md border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-rose-300">{errCount}</span>{/if}
          {#if warnCount}<span class="rounded-md border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-amber-200">{warnCount}</span>{/if}
          {#if fixes.length && !errCount && !warnCount}<span class="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-emerald-200">{fixes.length}</span>{/if}
        {:else if t.id === 'deploy' && (runStore.status === 'running' || runStore.status === 'pushing')}
          <span class="relative flex h-1.5 w-1.5">
            <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-70"></span>
            <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-400"></span>
          </span>
        {/if}
      </button>
    {/each}
    <button
      type="button"
      class="ml-auto flex items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
      onclick={onToggle}
      aria-expanded={open}
    >
      <svg viewBox="0 0 12 12" class="h-2.5 w-2.5 transition-transform {open ? '' : 'rotate-180'}" fill="currentColor" aria-hidden="true">
        <path d="M2 7.5l4-3 4 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      </svg>
      <span>{open ? 'Collapse' : 'Expand'}</span>
    </button>
  </div>
  {#if open}
    <div class="fade-in" style="height: {heightPx}px">
      {#if effectiveTab === 'diagnostics'}
        {@const hasMarkers = markers.length > 0 || fixes.length > 0}
        {@const hasDataFlow = playbookActions.diagnostics.length > 0}
        <div class="flex h-full flex-col overflow-hidden">
          {#if !hasMarkers && !hasDataFlow}
            <!-- Single clean empty state covers both sources. -->
            <div class="flex h-full items-center justify-center px-6 text-center">
              <div class="max-w-md">
                <div class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--brand)]">
                  <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.7">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M8 12.2l2.7 2.7L16 9.5" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </div>
                <div class="text-sm font-medium text-[var(--text-default)]">No issues</div>
                <p class="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-[var(--text-muted)]">
                  Syntax + data-flow checks re-run automatically as you edit.
                </p>
              </div>
            </div>
          {:else}
            {#if hasMarkers}
              {#if hasDataFlow}
                <div class="border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  Syntax
                </div>
              {/if}
              <div class={hasDataFlow ? 'flex-1 overflow-auto border-b border-[var(--border-soft)]' : 'flex-1 overflow-auto'}>
                <DiagnosticsList
                  {markers}
                  {fixes}
                  editor={monacoEditor ?? null}
                  monaco={monacoNs ?? null}
                  onApplied={(v) => onYamlReplace?.(v)}
                />
              </div>
            {/if}
            {#if hasDataFlow}
              {#if hasMarkers}
                <div class="border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  Data flow
                </div>
              {/if}
              <div class={hasMarkers ? 'h-1/2 flex-shrink-0 overflow-hidden' : 'flex-1 overflow-hidden'}>
                <RenderPathDiagnostics
                  onFocusStep={(sid) => visualStore.selectStepByName?.(sid)}
                  onApplyFix={applyRenderPathFix}
                />
              </div>
            {/if}
          {/if}
        </div>
      {:else if effectiveTab === 'deploy'}
        <DeployPanel />
      {/if}
    </div>
  {/if}
</div>
