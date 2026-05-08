<script lang="ts">
  /**
   * Bottom output drawer — diagnostics, fixes, compile JSON, and
   * deploy logs. Mode-agnostic: shown under both Design and CLI.
   *
   * Fixes tab depends on Monaco refs (executeEdits goes through the
   * editor's undo stack). Design has no Monaco, so callers omit the
   * refs and the Fixes tab self-disables with a helpful message.
   */
  import DiagnosticsList from './DiagnosticsList.svelte';
  import FixesPanel from './FixesPanel.svelte';
  import Console from './Console.svelte';
  import DeployPanel from './DeployPanel.svelte';
  import { playbookActions } from '$lib/playbookActions.svelte';
  import { runStore } from '$lib/runStore.svelte';

  type Tab = 'diagnostics' | 'fixes' | 'compile' | 'deploy';
  type Props = {
    open: boolean;
    tab: Tab;
    heightPx: number;
    onTabChange: (t: Tab) => void;
    onToggle: () => void;
    onResize: (e: PointerEvent) => void;
    /** Optional Monaco refs: when present (CLI), Fixes can apply via
     * executeEdits so each fix lands in the editor's undo stack.
     * When absent (Design), the Fixes tab still shows the suggestions
     * but disables Apply with an explanation. */
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
  let compileJson = $derived(playbookActions.compileJson);
  let errCount = $derived(playbookActions.errorCount);
  let warnCount = $derived(playbookActions.warningCount);
  let canApplyFixes = $derived(!!monacoEditor && !!monacoNs);
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
      { id: 'diagnostics' as Tab, label: 'Diagnostics' },
      { id: 'fixes' as Tab, label: 'Fixes' },
      { id: 'compile' as Tab, label: 'Compile' },
      { id: 'deploy' as Tab, label: 'Deploy' }
    ] as t}
      {@const active = tab === t.id && open}
      <button
        type="button"
        class={'group relative flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ' +
          (active
            ? 'bg-[var(--bg-elevated)] text-[var(--text-default)] shadow-[0_0_0_1px_var(--border)]'
            : 'text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]/50 hover:text-[var(--text-default)]')}
        onclick={() => onTabChange(t.id)}
      >
        <span>{t.label}</span>
        {#if t.id === 'fixes' && fixes.length}
          <span class="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-emerald-200">{fixes.length}</span>
        {:else if t.id === 'diagnostics'}
          {#if errCount}<span class="rounded-md border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-rose-300">{errCount}</span>{/if}
          {#if warnCount}<span class="rounded-md border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-amber-200">{warnCount}</span>{/if}
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
      {#if tab === 'diagnostics'}
        <div class="h-full overflow-auto">
          <DiagnosticsList {markers} />
        </div>
      {:else if tab === 'fixes'}
        {#if canApplyFixes}
          <div class="h-full overflow-hidden">
            <FixesPanel {fixes} editor={monacoEditor} monaco={monacoNs} onApplied={(v) => onYamlReplace?.(v)} />
          </div>
        {:else}
          <div class="flex h-full items-center justify-center px-6 text-center text-xs text-[var(--text-faint)]">
            Fixes apply through the YAML editor; switch to CLI mode to use them.
            ({fixes.length} {fixes.length === 1 ? 'suggestion' : 'suggestions'} pending.)
          </div>
        {/if}
      {:else if tab === 'compile'}
        <Console
          text={compileJson ?? ''}
          emptyTitle="No compile output yet"
          emptyHint="Press Compile to produce the FortiSOAR JSON the wire format pushes to /api/3/workflow_collections."
        />
      {:else if tab === 'deploy'}
        <DeployPanel />
      {/if}
    </div>
  {/if}
</div>
