<script lang="ts">
  /**
   * Validate / Compile / Run row for CLI mode.
   *
   * Design merges these actions into EditorToolbar (one row instead of
   * two stacked bars). CLI has no editor toolbar to merge into, so it
   * keeps a thin BuildBar.
   *
   * State (markers, status, run output) lives on `playbookActions`;
   * this component is just buttons + a status pill.
   */
  import { playbookActions } from '$lib/playbookActions.svelte';
  import RunButton from './RunButton.svelte';

  type Props = {
    onShowDrawer?: (tab: 'diagnostics' | 'fixes' | 'compile' | 'deploy' | 'debug') => void;
  };
  let { onShowDrawer }: Props = $props();

  let status = $derived(playbookActions.status);
  let dot = $derived(
    status.kind === 'ok' ? 'bg-green-500'
    : status.kind === 'err' ? 'bg-red-500'
    : status.kind === 'busy' ? 'bg-yellow-500'
    : 'bg-[var(--text-faint)]'
  );

  async function onCompile() {
    onShowDrawer?.('compile');
    await playbookActions.compile();
  }

  async function onVerify() {
    await playbookActions.runVerify();
    // If verify blocked, pop the diagnostics drawer so the user sees
    // the per-step badges' explanations alongside markers.
    if (!playbookActions.verifyReady) onShowDrawer?.('diagnostics');
  }
</script>

<div class="flex items-center gap-1 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-4 py-1 text-xs">
  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)]"
    onclick={() => playbookActions.validate()}
  >Validate</button>
  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)]"
    onclick={onCompile}
  >Compile</button>
  <!-- Verify: forcing-function pre-submit gate (compile + typed walk
       + per-step schema checks). Runs `verify_playbook`; per-step
       results render as red/amber badges on the canvas. -->
  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)]"
    onclick={onVerify}
    disabled={playbookActions.verifyBusy}
    title="Run verify_playbook — single forcing-function gate before push"
  >Verify</button>

  <RunButton />

  <span class="ml-3 flex items-center gap-1.5">
    <span class="h-2 w-2 rounded-full {dot}"></span>
    <span class="text-[var(--text-muted)]">{status.msg}</span>
  </span>

  {#if playbookActions.verify}
    <span
      class="ml-2 rounded px-2 py-0.5 text-[10px] font-medium"
      style="background: {playbookActions.verifyReady ? '#dcfce7' : '#fee2e2'}; color: {playbookActions.verifyReady ? '#166534' : '#991b1b'}"
      title={playbookActions.verifyReady
        ? 'verify: ready to push'
        : `${playbookActions.verifyFixCount} required fix(es)`}
    >
      {playbookActions.verifyReady ? 'verify ✓' : `verify ✗ ${playbookActions.verifyFixCount}`}
    </span>
  {/if}

  {#if playbookActions.errorCount > 0 || playbookActions.warningCount > 0}
    <button
      type="button"
      class="ml-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => onShowDrawer?.('diagnostics')}
      title="Open diagnostics drawer"
    >
      {#if playbookActions.errorCount > 0}<span class="text-red-600 dark:text-red-400">{playbookActions.errorCount} err</span>{/if}
      {#if playbookActions.errorCount > 0 && playbookActions.warningCount > 0}<span class="text-[var(--text-faint)]"> · </span>{/if}
      {#if playbookActions.warningCount > 0}<span class="text-amber-600 dark:text-amber-400">{playbookActions.warningCount} warn</span>{/if}
    </button>
  {/if}
</div>
