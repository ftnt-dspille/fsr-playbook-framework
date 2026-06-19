<script lang="ts">
  /**
   * `?` cheat-sheet overlay. Reads the same command registry the
   * palette and keybindings use, so adding a new command surfaces
   * here automatically — no separate doc to maintain.
   */
  import { commands } from '../commands.svelte';

  let open = $derived(commands.helpOpen);

  // Group by `group` field. Commands without one bucket into 'Other'.
  let grouped = $derived.by(() => {
    const out: Record<string, typeof commands.list> = {};
    for (const c of commands.list) {
      if (!c.hotkey) continue;  // palette-only commands aren't shortcuts
      const g = c.group ?? 'Other';
      (out[g] ??= []).push(c);
    }
    return out;
  });
</script>

{#if open}
  <div
    class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40"
    role="dialog"
    aria-label="Keyboard shortcuts"
    onclick={(e) => { if (e.target === e.currentTarget) commands.helpOpen = false; }}
  >
    <div class="w-full max-w-lg rounded-lg border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-4 shadow-2xl">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-[var(--text-default)]">Keyboard shortcuts</h2>
        <button
          type="button"
          class="text-xs text-[var(--text-muted)] hover:text-[var(--text-default)]"
          onclick={() => (commands.helpOpen = false)}
          aria-label="Close"
        >Esc</button>
      </div>
      <div class="space-y-3 text-sm">
        {#each Object.entries(grouped) as [group, list] (group)}
          <section>
            <h3 class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">{group}</h3>
            <ul class="space-y-1">
              {#each list as cmd (cmd.id)}
                <li class="flex items-center justify-between gap-3">
                  <span class="text-[var(--text-default)]">{cmd.label}</span>
                  <kbd class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">{cmd.hotkey}</kbd>
                </li>
              {/each}
            </ul>
          </section>
        {/each}
      </div>
    </div>
  </div>
{/if}
