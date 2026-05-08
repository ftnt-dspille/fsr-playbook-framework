<script lang="ts">
  import '../app.css';
  import StatusBar from '$lib/components/StatusBar.svelte';
  import { theme } from '$lib/theme.svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/state';

  let { children } = $props();

  onMount(() => {
    // Apply the saved theme to <html data-theme="..."> (SSR-safe).
    theme.init();
  });

  // Top-nav is the frequent set. Capabilities and Docs got folded into
  // Settings as sub-pages; theme switcher lives there too. Health pills
  // moved to the bottom StatusBar (VS Code style) so the header stays
  // light. Order matches frequency of use.
  // /run was retired — its log surface lives in the DiagnosticsDrawer's
  // Deploy tab now (visible inline during Push & Run instead of needing
  // a tab switch). The route still resolves and redirects to /, so old
  // bookmarks survive.
  const NAV: { href: string; label: string }[] = [
    { href: '/', label: 'Studio' },
    { href: '/browse', label: 'Browse' },
    { href: '/inventory', label: 'Inventory' },
    { href: '/history', label: 'History' },
    { href: '/settings', label: 'Settings' }
  ];

  function isActive(href: string, path: string): boolean {
    if (href === '/') return path === '/';
    return path === href || path.startsWith(href + '/');
  }
</script>

<div class="flex h-full flex-col bg-[var(--bg-canvas)]">
  <header class="glass sticky top-0 z-30 flex items-center gap-6 border-b border-[var(--border-soft)] px-5 py-1.5">
    <a href="/" class="group flex items-center gap-2" aria-label="FSR Playbook Studio home">
      <span class="relative flex h-6 w-6 items-center justify-center" aria-hidden="true">
        <svg viewBox="0 0 64 64" class="h-6 w-6 transition-transform group-hover:rotate-6">
          <ellipse cx="32" cy="32" rx="29" ry="12" fill="none" stroke="currentColor" stroke-width="3" class="text-[var(--brand)]"/>
          <ellipse cx="32" cy="32" rx="29" ry="12" fill="none" stroke="currentColor" stroke-width="3" class="text-[var(--brand)]" transform="rotate(60 32 32)"/>
          <ellipse cx="32" cy="32" rx="29" ry="12" fill="none" stroke="currentColor" stroke-width="3" class="text-[var(--brand)]" transform="rotate(120 32 32)"/>
          <circle cx="32" cy="32" r="6" fill="var(--color-accent-amber)"/>
        </svg>
      </span>
      <span class="text-[13px] font-semibold tracking-tight text-[var(--text-default)]">FSR Playbook Studio</span>
    </a>
    <nav class="flex items-center gap-0.5 text-sm">
      {#each NAV as item}
        {@const active = isActive(item.href, page.url.pathname)}
        <a
          href={item.href}
          aria-current={active ? 'page' : undefined}
          class="relative rounded-md px-2.5 py-1 font-medium transition-colors {active
            ? 'text-[var(--text-default)]'
            : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
        >
          {item.label}
          {#if active}
            <span class="absolute inset-x-2 -bottom-[7px] h-[2px] rounded-full bg-[var(--brand)]"></span>
          {/if}
        </a>
      {/each}
    </nav>
  </header>
  <main class="min-h-0 flex-1 fade-in">{@render children()}</main>
  <StatusBar />
</div>
