<script lang="ts">
  /**
   * Action row for CLI mode: Verify + Run + status pill + err/warn chip
   * + overflow (Re-analyze / Re-validate). Validate and Analyze run
   * automatically (on edit and on autosave); the overflow is the escape
   * valve when a user wants to force a re-run.
   *
   * State lives on `playbookActions`; this component is just buttons.
   */
  import { playbookActions } from '$lib/playbookActions.svelte';
  import RunButton from './RunButton.svelte';

  type Props = {
    onShowDrawer?: (tab: 'diagnostics' | 'fixes' | 'deploy') => void;
  };
  let { onShowDrawer }: Props = $props();

  let status = $derived(playbookActions.status);
  let dot = $derived(
    status.kind === 'ok' ? 'bg-green-500'
    : status.kind === 'err' ? 'bg-red-500'
    : status.kind === 'busy' ? 'bg-yellow-500'
    : 'bg-[var(--text-faint)]'
  );

  // ⋯ overflow menu. We use position:fixed + bind:this so the popup
  // escapes the overflow-hidden parents that wrap both Design and CLI
  // workspaces (was getting clipped as a `position:absolute` child).
  let menuOpen = $state(false);
  let menuBtn = $state<HTMLButtonElement | null>(null);
  let menuTop = $state(0);
  let menuRight = $state(0);
  function toggleMenu() {
    if (!menuOpen && menuBtn) {
      const r = menuBtn.getBoundingClientRect();
      menuTop = r.bottom + 4;
      menuRight = window.innerWidth - r.right;
    }
    menuOpen = !menuOpen;
  }
  function closeMenu() { menuOpen = false; }
</script>

<div class="flex items-center gap-1 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-4 py-1 text-xs">
  <RunButton />

  <span class="ml-3 flex items-center gap-1.5" title={status.msg}>
    <span class="h-2 w-2 rounded-full {dot}"></span>
    <span class="text-[var(--text-muted)]">{status.msg}</span>
  </span>

  {#if playbookActions.errorCount > 0 || playbookActions.warningCount > 0}
    <button
      type="button"
      class="ml-2 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => onShowDrawer?.('diagnostics')}
      title="Open issues drawer"
    >
      {#if playbookActions.errorCount > 0}<span class="text-red-600 dark:text-red-400">{playbookActions.errorCount} err</span>{/if}
      {#if playbookActions.errorCount > 0 && playbookActions.warningCount > 0}<span class="text-[var(--text-faint)]"> · </span>{/if}
      {#if playbookActions.warningCount > 0}<span class="text-amber-600 dark:text-amber-400">{playbookActions.warningCount} warn</span>{/if}
    </button>
  {/if}

  <button
    type="button"
    bind:this={menuBtn}
    class="ml-auto rounded px-2 py-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-elev)]"
    title="More actions"
    aria-label="More actions"
    aria-haspopup="menu"
    aria-expanded={menuOpen}
    onclick={toggleMenu}
  >⋯</button>
</div>

{#if menuOpen}
  <button
    type="button"
    aria-label="Close menu"
    class="fixed inset-0 z-40 cursor-default bg-transparent"
    onclick={closeMenu}
  ></button>
  <div
    role="menu"
    class="fixed z-50 flex w-48 flex-col rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] py-1 text-xs shadow-lg"
    style="top: {menuTop}px; right: {menuRight}px"
  >
    <button
      type="button"
      role="menuitem"
      class="px-3 py-1 text-left hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={() => { closeMenu(); void playbookActions.validate(); }}
    >Re-validate</button>
    <button
      type="button"
      role="menuitem"
      class="px-3 py-1 text-left hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={() => { closeMenu(); void playbookActions.analyze(); }}
      disabled={playbookActions.analyzeBusy}
    >{playbookActions.analyzeBusy ? 'Analyzing…' : 'Re-analyze render path'}</button>
    <button
      type="button"
      role="menuitem"
      class="px-3 py-1 text-left hover:bg-[var(--bg-canvas)] disabled:opacity-50"
      onclick={() => { closeMenu(); void playbookActions.runVerify(); }}
      disabled={playbookActions.verifyBusy}
    >{playbookActions.verifyBusy ? 'Verifying…' : 'Re-verify'}</button>
  </div>
{/if}
