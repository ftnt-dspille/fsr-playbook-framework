<script lang="ts">
  /**
   * Cmd+K command palette. Opens via `commands.paletteOpen = true`
   * (bound to the Cmd+K hotkey in +page.svelte). Filters the global
   * command registry by typed query; Enter runs the highlighted one.
   *
   * Keep the markup minimal — this is a quick-access surface, not a
   * settings panel. No icons, no fancy grouping; commands self-tag
   * via the `group` field for a single right-aligned label.
   */
  import { commands } from '../commands.svelte';

  let query = $state('');
  let highlightIdx = $state(0);

  // Re-derive on every state change so paletteOpen flipping resets
  // the query / highlight to a sensible state without an effect.
  let open = $derived(commands.paletteOpen);
  $effect(() => {
    if (open) {
      query = '';
      highlightIdx = 0;
    }
  });

  let filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    const all = commands.list.filter((c) => c.run);
    if (!q) return all;
    // Cheap fuzzy: every char of the query appears in order in the
    // label. Good enough for ~20 commands; replace with a real fuzzy
    // matcher (fuse.js etc.) if the list ever grows past ~100.
    return all.filter((c) => {
      const label = c.label.toLowerCase();
      let i = 0;
      for (const ch of q) {
        i = label.indexOf(ch, i);
        if (i < 0) return false;
        i += 1;
      }
      return true;
    });
  });

  function onKey(ev: KeyboardEvent) {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      commands.paletteOpen = false;
      return;
    }
    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      highlightIdx = Math.min(highlightIdx + 1, filtered.length - 1);
      return;
    }
    if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      highlightIdx = Math.max(highlightIdx - 1, 0);
      return;
    }
    if (ev.key === 'Enter') {
      ev.preventDefault();
      const cmd = filtered[highlightIdx];
      if (cmd && (!cmd.enabled || cmd.enabled())) {
        commands.paletteOpen = false;
        void cmd.run();
      }
    }
  }

  function pick(id: string) {
    commands.paletteOpen = false;
    void commands.runById(id);
  }
</script>

{#if open}
  <!-- Modal scrim + dialog. Click-outside closes; Escape handled in
       the input's keydown so it works even when the input is focused. -->
  <div
    class="fixed inset-0 z-[100] flex items-start justify-center bg-black/40 pt-[15vh]"
    role="dialog"
    aria-label="Command palette"
    onclick={(e) => { if (e.target === e.currentTarget) commands.paletteOpen = false; }}
  >
    <div class="w-full max-w-xl rounded-lg border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-2xl">
      <input
        type="text"
        autofocus
        bind:value={query}
        onkeydown={onKey}
        placeholder="Type a command…"
        class="w-full rounded-t-lg border-b border-[var(--border-soft)] bg-transparent px-4 py-3 text-sm text-[var(--text-default)] placeholder:text-[var(--text-faint)] focus:outline-none"
      />
      <ul class="max-h-80 overflow-auto py-1">
        {#if filtered.length === 0}
          <li class="px-4 py-3 text-xs italic text-[var(--text-faint)]">
            No commands match.
          </li>
        {:else}
          {#each filtered as cmd, i (cmd.id)}
            {@const disabled = cmd.enabled && !cmd.enabled()}
            <li>
              <button
                type="button"
                disabled={disabled}
                onmouseenter={() => (highlightIdx = i)}
                onclick={() => pick(cmd.id)}
                class="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm
                       {i === highlightIdx ? 'bg-[var(--bg-elev)]' : ''}
                       {disabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[var(--bg-elev)]'}"
              >
                <span class="flex items-baseline gap-2">
                  <span class="text-[var(--text-default)]">{cmd.label}</span>
                  {#if cmd.group}
                    <span class="text-[10px] uppercase tracking-wider text-[var(--text-faint)]">{cmd.group}</span>
                  {/if}
                </span>
                {#if cmd.hotkey}
                  <kbd class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">{cmd.hotkey}</kbd>
                {/if}
              </button>
            </li>
          {/each}
        {/if}
      </ul>
      <div class="flex items-center justify-between border-t border-[var(--border-soft)] px-3 py-1.5 text-[10px] text-[var(--text-faint)]">
        <span><kbd class="font-mono">↑↓</kbd> navigate · <kbd class="font-mono">↵</kbd> run · <kbd class="font-mono">Esc</kbd> close</span>
        <span>{filtered.length} / {commands.list.length}</span>
      </div>
    </div>
  </div>
{/if}
