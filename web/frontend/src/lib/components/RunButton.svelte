<script lang="ts">
  /**
   * Run split-button. One primary action (▶ Run) defaults to "Push & Run";
   * a chevron drops a menu offering Push only / Push & Run / Mock run /
   * Live run. Replaces the four-button row that was filling chrome.
   *
   * Default action is configurable via prop; component remembers the
   * last-used variant in localStorage so the next click of the primary
   * button does what the user actually wants without re-opening the menu.
   */
  import { playbookActions } from '$lib/playbookActions.svelte';

  type Variant = 'push' | 'push_and_run' | 'mock' | 'live';

  let menuOpen = $state(false);
  let lastVariant: Variant = $state(
    (typeof localStorage !== 'undefined'
      ? (localStorage.getItem('fsrpb.run.last') as Variant | null)
      : null) ?? 'push_and_run'
  );

  $effect(() => {
    try { localStorage.setItem('fsrpb.run.last', lastVariant); } catch {}
  });

  const VARIANTS: { id: Variant; label: string; hint: string }[] = [
    { id: 'push',         label: 'Push only',  hint: 'Compile + push to FSR; no run' },
    { id: 'push_and_run', label: 'Push & Run', hint: 'Push then trigger a live run' },
    { id: 'mock',         label: 'Mock run',   hint: 'Step through locally without FSR' },
    { id: 'live',         label: 'Live run',   hint: 'Run against the configured FSR' }
  ];

  async function fire(v: Variant) {
    lastVariant = v;
    menuOpen = false;
    if (v === 'push') await playbookActions.push();
    else if (v === 'push_and_run' || v === 'live') await playbookActions.pushAndRun();
    else if (v === 'mock') {
      // Mock-run isn't wired through playbookActions yet — surface a
      // status message so the button isn't a no-op.
      playbookActions.state.status = { kind: 'idle', msg: 'Mock run — not yet implemented' };
    }
  }

  let primaryLabel = $derived(VARIANTS.find((v) => v.id === lastVariant)?.label ?? 'Run');
</script>

<div class="relative inline-flex">
  <button
    type="button"
    class="rounded-l border border-r-0 border-orange-700/40 bg-orange-500/10 px-3 py-0.5 text-xs font-medium text-orange-700 hover:bg-orange-500/20 dark:text-orange-300"
    onclick={() => fire(lastVariant)}
    title={primaryLabel}
  >
    <span aria-hidden="true">▶</span> {primaryLabel}
  </button>
  <button
    type="button"
    class="rounded-r border border-orange-700/40 bg-orange-500/10 px-1.5 py-0.5 text-xs font-medium text-orange-700 hover:bg-orange-500/20 dark:text-orange-300"
    onclick={() => (menuOpen = !menuOpen)}
    aria-haspopup="menu"
    aria-expanded={menuOpen}
    aria-label="Run options"
    title="Choose a run variant"
  >▾</button>

  {#if menuOpen}
    <!-- Click-shield closes the menu on outside click without nuking
         the trigger button click first. -->
    <button
      type="button"
      class="fixed inset-0 z-30 cursor-default bg-transparent"
      aria-hidden="true"
      tabindex="-1"
      onclick={() => (menuOpen = false)}
    ></button>
    <div class="absolute right-0 top-full z-40 mt-1 w-64 overflow-hidden rounded-md border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-xl" role="menu">
      {#each VARIANTS as v (v.id)}
        <button
          type="button"
          role="menuitem"
          class="block w-full border-b border-[var(--border-soft)] px-3 py-2 text-left text-xs last:border-b-0 hover:bg-[var(--bg-elev)] {lastVariant === v.id ? 'bg-[var(--brand)]/5' : ''}"
          onclick={() => fire(v.id)}
        >
          <div class="font-medium text-[var(--text-default)]">{v.label}</div>
          <div class="mt-0.5 text-[10px] text-[var(--text-faint)]">{v.hint}</div>
        </button>
      {/each}
    </div>
  {/if}
</div>
