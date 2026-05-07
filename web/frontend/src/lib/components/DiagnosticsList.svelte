<script lang="ts">
  import type { Marker } from '$lib/api';

  let { markers }: { markers: Marker[] } = $props();

  function severityClasses(s: string) {
    if (s === 'error') {
      return {
        dot: 'bg-rose-500',
        chip: 'bg-rose-500/10 text-rose-300 border-rose-500/30'
      };
    }
    if (s === 'warning') {
      return {
        dot: 'bg-amber-400',
        chip: 'bg-amber-400/10 text-amber-200 border-amber-400/30'
      };
    }
    return {
      dot: 'bg-[var(--text-muted)]',
      chip: 'bg-[var(--text-faint)]/10 text-[var(--text-muted)] border-[var(--text-faint)]/30'
    };
  }
</script>

{#if !markers.length}
  <div class="flex h-full items-center justify-center px-6 py-10">
    <div class="max-w-md text-center">
      <div class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--brand)]">
        <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.7">
          <circle cx="12" cy="12" r="9" />
          <path d="M8 12.2l2.7 2.7L16 9.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </div>
      <div class="text-sm font-medium text-[var(--text-default)]">No diagnostics</div>
      <p class="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-[var(--text-muted)]">
        The YAML parses, resolves, and validates clean. Live errors and warnings will appear here as you type.
      </p>
    </div>
  </div>
{:else}
  <ul class="divide-y divide-[var(--border-soft)] fade-in">
    {#each markers as m}
      {@const cls = severityClasses(m.severity)}
      <li class="px-4 py-2.5 transition-colors hover:bg-[var(--bg-panel)]">
        <div class="flex items-start gap-3">
          <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full {cls.dot}" aria-hidden="true"></span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2 text-[11px]">
              <span class="rounded-md border px-1.5 py-0.5 font-medium uppercase tracking-wide {cls.chip}">{m.severity}</span>
              <span class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[var(--text-muted)]">L{m.line}</span>
              {#if m.code}
                <span class="font-mono text-[var(--text-faint)]">{m.code}</span>
              {/if}
              {#if m.path}
                <span class="truncate font-mono text-[var(--text-faint)]" title={m.path}>· {m.path}</span>
              {/if}
            </div>
            <div class="mt-1 text-sm leading-snug text-[var(--text-default)]">{m.message}</div>
            {#if m.suggestion}
              <div class="mt-1.5 flex items-start gap-1.5 rounded-md border border-[var(--border-soft)] bg-[var(--bg-panel)] px-2 py-1 text-xs text-[var(--text-muted)]">
                <span class="text-[var(--brand)]" aria-hidden="true">→</span>
                <span class="min-w-0">{m.suggestion}</span>
              </div>
            {/if}
          </div>
        </div>
      </li>
    {/each}
  </ul>
{/if}
