<script lang="ts">
  /**
   * Unified Design-mode toolbar. Hosts the editor utilities (undo/redo,
   * layout direction, Jinja test) AND the build/deploy actions
   * (Validate, Compile, Run split-button + status pill) in a single
   * row so Design has just ONE chrome bar above the canvas.
   *
   * CLI mode still mounts BuildBar separately (it has no editor toolbar
   * to merge into).
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
    onShowDrawer?: (tab: 'diagnostics' | 'fixes' | 'compile' | 'deploy' | 'debug') => void;
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

  async function onCompile() {
    onShowDrawer?.('compile');
    await playbookActions.compile();
  }
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
  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)]"
    onclick={() => playbookActions.validate()}
    title="Validate the current YAML"
  >Validate</button>
  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)] disabled:opacity-50"
    onclick={() => playbookActions.analyze()}
    disabled={playbookActions.analyzeBusy}
    title="Render-path validator — simulate offline and flag data-access bugs"
  >{playbookActions.analyzeBusy ? 'Analyzing…' : 'Analyze'}</button>
  <button
    type="button"
    class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 hover:bg-[var(--bg-canvas)]"
    onclick={onCompile}
    title="Compile to FortiSOAR JSON"
  >Compile</button>

  <RunButton />

  <!-- Status + diagnostics access -->
  <span class="ml-2 flex items-center gap-1.5">
    <span class="h-2 w-2 rounded-full {dot}"></span>
    <span class="text-[var(--text-muted)]">{status.msg}</span>
  </span>

  {#if playbookActions.errorCount > 0 || playbookActions.warningCount > 0}
    <button
      type="button"
      class="ml-1 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => onShowDrawer?.('diagnostics')}
      title="Open diagnostics drawer"
    >
      {#if playbookActions.errorCount > 0}<span class="text-red-600 dark:text-red-400">{playbookActions.errorCount} err</span>{/if}
      {#if playbookActions.errorCount > 0 && playbookActions.warningCount > 0}<span class="text-[var(--text-faint)]"> · </span>{/if}
      {#if playbookActions.warningCount > 0}<span class="text-amber-600 dark:text-amber-400">{playbookActions.warningCount} warn</span>{/if}
    </button>
  {/if}

  {#if playbookActions.analyzeErrorCount > 0 || playbookActions.analyzeWarningCount > 0}
    <button
      type="button"
      class="ml-1 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium hover:bg-[var(--bg-canvas)]"
      onclick={() => onShowDrawer?.('diagnostics')}
      title="Open diagnostics drawer (render path)"
    >
      <span class="text-[var(--text-faint)]">render</span>
      {#if playbookActions.analyzeErrorCount > 0}<span class="ml-1 text-red-600 dark:text-red-400">{playbookActions.analyzeErrorCount} err</span>{/if}
      {#if playbookActions.analyzeErrorCount > 0 && playbookActions.analyzeWarningCount > 0}<span class="text-[var(--text-faint)]"> · </span>{/if}
      {#if playbookActions.analyzeWarningCount > 0}<span class="text-amber-600 dark:text-amber-400">{playbookActions.analyzeWarningCount} warn</span>{/if}
    </button>
  {/if}
</div>
