<script lang="ts">
  import '../app.css';
  import HealthPill from '$lib/components/HealthPill.svelte';
  import ThemeSwitcher from '$lib/components/ThemeSwitcher.svelte';
  import { theme } from '$lib/theme.svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/state';

  let { children } = $props();

  onMount(() => {
    // Apply the saved theme to <html data-theme="..."> (SSR-safe).
    theme.init();
  });

  const NAV: { href: string; label: string }[] = [
    { href: '/', label: 'Design' },
    { href: '/run', label: 'Run' },
    { href: '/browse', label: 'Browse' },
    { href: '/inventory', label: 'Inventory' },
    { href: '/history', label: 'History' },
    { href: '/capabilities', label: 'Capabilities' },
    { href: '/docs', label: 'Docs' },
    { href: '/settings', label: 'Settings' }
  ];

  function isActive(href: string, path: string): boolean {
    if (href === '/') return path === '/';
    return path === href || path.startsWith(href + '/');
  }
</script>

<div class="flex h-full flex-col bg-[var(--bg-canvas)]">
  <header class="glass sticky top-0 z-30 flex items-center justify-between border-b border-[var(--border-soft)] px-5 py-2.5">
    <div class="flex items-center gap-6">
      <a href="/" class="group flex items-center gap-2.5" aria-label="FSR Playbook Studio home">
        <span class="relative flex h-7 w-7 items-center justify-center" aria-hidden="true">
          <svg viewBox="0 0 64 64" class="h-7 w-7 transition-transform group-hover:rotate-6">
            <ellipse cx="32" cy="32" rx="29" ry="12" fill="none" stroke="currentColor" stroke-width="3" class="text-[var(--brand)]"/>
            <ellipse cx="32" cy="32" rx="29" ry="12" fill="none" stroke="currentColor" stroke-width="3" class="text-[var(--brand)]" transform="rotate(60 32 32)"/>
            <ellipse cx="32" cy="32" rx="29" ry="12" fill="none" stroke="currentColor" stroke-width="3" class="text-[var(--brand)]" transform="rotate(120 32 32)"/>
            <circle cx="32" cy="32" r="6" fill="var(--color-accent-amber)"/>
          </svg>
        </span>
        <span class="flex flex-col leading-tight">
          <span class="text-[13px] font-semibold tracking-tight text-[var(--text-default)]">FSR Playbook Studio</span>
          <span class="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--text-faint)]">FortiSOAR · authoring &amp; ops</span>
        </span>
      </a>
      <nav class="flex items-center gap-0.5 text-sm">
        {#each NAV as item}
          {@const active = isActive(item.href, page.url.pathname)}
          <a
            href={item.href}
            aria-current={active ? 'page' : undefined}
            class="relative rounded-md px-2.5 py-1.5 font-medium transition-colors {active
              ? 'text-[var(--text-default)]'
              : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
          >
            {item.label}
            {#if active}
              <span class="absolute inset-x-2 -bottom-[11px] h-[2px] rounded-full bg-[var(--brand)]"></span>
            {/if}
          </a>
        {/each}
      </nav>
    </div>
    <div class="flex items-center gap-2">
      <ThemeSwitcher />
      <HealthPill />
    </div>
  </header>
  <main class="min-h-0 flex-1 fade-in">{@render children()}</main>
</div>
