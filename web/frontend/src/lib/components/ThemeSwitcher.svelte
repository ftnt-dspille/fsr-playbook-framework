<script lang="ts">
  import { theme, THEMES, type ThemeId } from '$lib/theme.svelte';

  let open = $state(false);
  let menu: HTMLDivElement | undefined;

  function toggle() {
    open = !open;
  }
  function pick(id: ThemeId) {
    theme.set(id);
    open = false;
  }
  function onDocClick(e: MouseEvent) {
    if (!open) return;
    if (menu && !menu.contains(e.target as Node)) open = false;
  }

  const active = $derived(THEMES.find((t) => t.id === theme.current) ?? THEMES[0]);
</script>

<svelte:window onclick={onDocClick} />

<div class="relative" bind:this={menu}>
  <button
    type="button"
    onclick={toggle}
    class="flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
    aria-haspopup="listbox"
    aria-expanded={open}
    title="Switch theme"
  >
    <span class="flex h-3 w-3 items-center justify-center">
      {#if active.mode === 'dark'}
        <svg viewBox="0 0 16 16" class="h-3 w-3" fill="currentColor" aria-hidden="true">
          <path d="M8 0a8 8 0 1 0 7.93 7.07A6 6 0 0 1 8.93 0.07 8 8 0 0 0 8 0z" />
        </svg>
      {:else}
        <svg viewBox="0 0 16 16" class="h-3 w-3" fill="currentColor" aria-hidden="true">
          <circle cx="8" cy="8" r="3.2" />
          <g stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
            <path d="M8 1.2v1.6" />
            <path d="M8 13.2v1.6" />
            <path d="M1.2 8h1.6" />
            <path d="M13.2 8h1.6" />
            <path d="M3.2 3.2l1.1 1.1" />
            <path d="M11.7 11.7l1.1 1.1" />
            <path d="M3.2 12.8l1.1-1.1" />
            <path d="M11.7 4.3l1.1-1.1" />
          </g>
        </svg>
      {/if}
    </span>
    <span>{active.label}</span>
    <svg viewBox="0 0 12 12" class="h-2.5 w-2.5 opacity-70 transition-transform {open ? 'rotate-180' : ''}" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
      <path d="M2.5 4.5L6 8l3.5-3.5" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
  </button>

  {#if open}
    <div
      role="listbox"
      class="absolute right-0 top-full z-50 mt-1.5 w-44 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-1 shadow-lg fade-in"
    >
      {#each THEMES as t}
        {@const active = t.id === theme.current}
        <button
          role="option"
          aria-selected={active}
          onclick={() => pick(t.id)}
          class={'flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition-colors ' +
            (active
              ? 'bg-[var(--brand-soft)] text-[var(--text-default)]'
              : 'text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-default)]')}
        >
          <span class="flex items-center gap-2">
            <span class="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-[var(--border)]" data-swatch={t.id} aria-hidden="true">
              {#if t.id === 'forest'}
                <span class="h-2 w-2 rounded-full" style="background:#2dd4bf"></span>
              {:else if t.id === 'cobalt'}
                <span class="h-2 w-2 rounded-full" style="background:#3b82f6"></span>
              {:else if t.id === 'aurora'}
                <span class="h-2 w-2 rounded-full" style="background:#c084fc"></span>
              {:else}
                <span class="h-2 w-2 rounded-full" style="background:#0d9488"></span>
              {/if}
            </span>
            <span>{t.label}</span>
            <span class="text-[10px] uppercase tracking-wide text-[var(--text-faint)]">{t.mode}</span>
          </span>
          {#if active}
            <svg viewBox="0 0 16 16" class="h-3.5 w-3.5 text-[var(--brand)]" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path d="M3 8.5L7 12.5 13 5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>
