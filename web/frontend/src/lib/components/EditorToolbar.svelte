<script lang="ts">
  /**
   * Unified Design-mode toolbar: editor utilities (undo/redo, layout,
   * Jinja test) + actions (Verify, Run + status). Validate / Analyze
   * run automatically; their escape valve lives in the ⋯ overflow.
   */
  import { visualStore } from '../visualEditStore.svelte';
  import { forceLayout, type LayoutDirection } from '../visualLayout';
  import { playbookActions } from '$lib/playbookActions.svelte';
  import RunButton from './RunButton.svelte';

  type Props = {
    playbookIdx: number;
    direction?: LayoutDirection;
    onDirectionChange?: (dir: LayoutDirection) => void;
    onJinjaTest?: () => void;
    onShowDrawer?: (tab: 'diagnostics' | 'fixes' | 'deploy' | 'debug') => void;
  };
  let {
    playbookIdx,
    direction = 'TB',
    onDirectionChange,
    onJinjaTest,
    onShowDrawer
  }: Props = $props();

  let layoutDir = $derived(direction);
  let canUndo = $derived(visualStore.canUndo);
  let canRedo = $derived(visualStore.canRedo);

  let status = $derived(playbookActions.status);
  let dot = $derived(
    status.kind === 'ok' ? 'bg-green-500'
    : status.kind === 'err' ? 'bg-red-500'
    : status.kind === 'busy' ? 'bg-yellow-500'
    : 'bg-[var(--text-faint)]'
  );

  function applyLayout(dir: LayoutDirection) {
    onDirectionChange?.(dir);
    const pb = visualStore.state.graph?.playbooks[playbookIdx];
    if (!pb) return;
    const positioned = forceLayout(pb.nodes, pb.edges, dir);
    for (const n of positioned) {
      visualStore.setPosition(playbookIdx, n.id, n.position);
    }
  }

  // Combined error/warning counts across validate + analyze, so the
  // toolbar shows one chip instead of two.
  let totalErr = $derived(playbookActions.errorCount + playbookActions.analyzeErrorCount);
  let totalWarn = $derived(playbookActions.warningCount + playbookActions.analyzeWarningCount);

  // ⋯ overflow menu, position:fixed to escape overflow-hidden parents.
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

<div
  class="flex items-center gap-1 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs"
  role="toolbar"
  aria-label="Editor toolbar"
>
  <!-- Editor utility group: history + layout + Jinja test -->
  <button
    type="button"
    class="rounded px-2 py-0.5 font-medium hover:bg-[var(--bg-elev)] disabled:cursor-not-allowed disabled:opacity-40"
    onclick={() => visualStore.undo()}
    disabled={!canUndo}
    title="Undo (⌘Z)"
    aria-label="Undo"
  >↶</button>
  <button
    type="button"
    class="rounded px-2 py-0.5 font-medium hover:bg-[var(--bg-elev)] disabled:cursor-not-allowed disabled:opacity-40"
    onclick={() => visualStore.redo()}
    disabled={!canRedo}
    title="Redo (⌘⇧Z)"
    aria-label="Redo"
  >↷</button>

  <span class="mx-1.5 h-4 w-px bg-[var(--border-soft)]" aria-hidden="true"></span>

  <div class="inline-flex rounded border border-[var(--border-soft)] p-0.5" role="group" aria-label="Layout direction">
    <button
      type="button"
      class="rounded px-1.5 py-0.5 font-medium {layoutDir === 'TB' ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
      onclick={() => applyLayout('TB')}
      title="Auto-layout top → bottom"
      aria-label="Layout top to bottom"
    >↧</button>
    <button
      type="button"
      class="rounded px-1.5 py-0.5 font-medium {layoutDir === 'LR' ? 'bg-[var(--brand)] text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
      onclick={() => applyLayout('LR')}
      title="Auto-layout left → right"
      aria-label="Layout left to right"
    >↦</button>
  </div>

  <button
    type="button"
    class="ml-1 rounded px-2 py-0.5 font-medium hover:bg-[var(--bg-elev)]"
    onclick={() => onJinjaTest?.()}
    title="Test a Jinja expression"
    aria-label="Test Jinja"
  >ƒ Jinja</button>

  <span class="mx-1.5 h-4 w-px bg-[var(--border-soft)]" aria-hidden="true"></span>

  <!-- Build/deploy group -->
  <RunButton />

  <!-- Status + issues access. Dot color = latest auto-run outcome
       (validate / analyze / verify). -->
  <span class="ml-2 flex items-center gap-1.5" title={status.msg}>
    <span class="h-2 w-2 rounded-full {dot}"></span>
    <span class="text-[var(--text-muted)]">{status.msg}</span>
  </span>

  {#if totalErr > 0 || totalWarn > 0}
    <button
      type="button"
      class="ml-1 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => onShowDrawer?.('diagnostics')}
      title="Open issues drawer"
    >
      {#if totalErr > 0}<span class="text-red-600 dark:text-red-400">{totalErr} err</span>{/if}
      {#if totalErr > 0 && totalWarn > 0}<span class="text-[var(--text-faint)]"> · </span>{/if}
      {#if totalWarn > 0}<span class="text-amber-600 dark:text-amber-400">{totalWarn} warn</span>{/if}
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
