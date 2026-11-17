<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    title,
    description,
    icon,
    actions
  }: {
    title: string;
    description?: string;
    icon?: Snippet;
    actions?: Snippet;
  } = $props();
</script>

<div class="flex h-full min-h-[24rem] w-full items-center justify-center px-6 py-12 fade-in">
  <div class="max-w-md text-center">
    <div class="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--brand)]">
      {#if icon}
        {@render icon()}
      {:else}
        <!-- default: orbit mark -->
        <svg viewBox="0 0 64 64" class="h-7 w-7" aria-hidden="true">
          <ellipse cx="32" cy="32" rx="22" ry="9" fill="none" stroke="currentColor" stroke-width="2.5"/>
          <ellipse cx="32" cy="32" rx="22" ry="9" fill="none" stroke="currentColor" stroke-width="2.5" transform="rotate(60 32 32)"/>
          <ellipse cx="32" cy="32" rx="22" ry="9" fill="none" stroke="currentColor" stroke-width="2.5" transform="rotate(120 32 32)"/>
          <circle cx="32" cy="32" r="4" fill="var(--color-accent-amber)"/>
        </svg>
      {/if}
    </div>
    <h2 class="text-base font-semibold tracking-tight text-[var(--text-default)]">{title}</h2>
    {#if description}
      <p class="mx-auto mt-1.5 max-w-sm text-sm leading-relaxed text-[var(--text-muted)]">
        {description}
      </p>
    {/if}
    {#if actions}
      <div class="mt-5 flex items-center justify-center gap-2">
        {@render actions()}
      </div>
    {/if}
  </div>
</div>
