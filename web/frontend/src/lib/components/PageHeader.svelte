<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    title,
    subtitle,
    eyebrow,
    actions
  }: {
    title: string;
    subtitle?: string;
    eyebrow?: string;
    actions?: Snippet;
  } = $props();
</script>

<header class="border-b border-[var(--border-soft)] px-6 pb-4 pt-5">
  <div class="flex items-end justify-between gap-6">
    <div class="min-w-0">
      {#if eyebrow}
        <div class="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--brand)]">
          {eyebrow}
        </div>
      {/if}
      <h1 class="truncate text-xl font-semibold tracking-tight text-[var(--text-default)]">
        {title}
      </h1>
      {#if subtitle}
        <p class="mt-1 max-w-2xl text-sm text-[var(--text-muted)]">{subtitle}</p>
      {/if}
    </div>
    {#if actions}
      <div class="flex shrink-0 items-center gap-2">
        {@render actions()}
      </div>
    {/if}
  </div>
</header>
