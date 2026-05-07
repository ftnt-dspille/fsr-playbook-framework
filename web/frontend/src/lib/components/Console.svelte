<script lang="ts">
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';

  let {
    text = '',
    lines = null,
    emptyTitle,
    emptyHint,
    emptyIcon,
    autoScroll = false,
    metaLeft,
    metaRight
  }: {
    text?: string;
    lines?: string[] | null;
    emptyTitle: string;
    emptyHint?: string;
    emptyIcon?: Snippet;
    autoScroll?: boolean;
    metaLeft?: Snippet;
    metaRight?: Snippet;
  } = $props();

  let scrollEl: HTMLDivElement | undefined;
  let copied = $state(false);

  const hasContent = $derived((lines?.length ?? 0) > 0 || (text || '').length > 0);
  const lineCount = $derived(
    lines ? lines.length : text ? text.split('\n').length : 0
  );

  $effect(() => {
    // Re-scroll to bottom when new content arrives in streaming mode.
    void (lines?.length ?? 0);
    void text;
    if (!autoScroll || !scrollEl) return;
    queueMicrotask(() => scrollEl?.scrollTo({ top: scrollEl.scrollHeight }));
  });

  async function copy() {
    const payload = lines ? lines.join('\n') : text;
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(payload);
      copied = true;
      setTimeout(() => (copied = false), 1200);
    } catch {
      /* ignore clipboard errors (sandbox / permissions) */
    }
  }

  function scrollToBottom() {
    scrollEl?.scrollTo({ top: scrollEl.scrollHeight, behavior: 'smooth' });
  }
</script>

<div class="flex h-full min-h-0 flex-col">
  <div class="flex items-center gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-panel)] px-3 py-1.5 text-[11px] text-[var(--text-muted)]">
    {#if metaLeft}
      {@render metaLeft()}
    {/if}
    {#if hasContent}
      <span class="rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
        {lineCount} line{lineCount === 1 ? '' : 's'}
      </span>
    {/if}
    <div class="ml-auto flex items-center gap-1.5">
      {#if metaRight}
        {@render metaRight()}
      {/if}
      {#if hasContent}
        <button
          type="button"
          class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
          onclick={copy}
          aria-label="Copy console contents"
        >
          {copied ? '✓ copied' : 'copy'}
        </button>
        {#if autoScroll}
          <button
            type="button"
            class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
            onclick={scrollToBottom}
            aria-label="Scroll to latest"
          >
            ↓ latest
          </button>
        {/if}
      {/if}
    </div>
  </div>
  <div bind:this={scrollEl} class="min-h-0 flex-1 overflow-auto bg-[var(--bg-canvas)]">
    {#if hasContent}
      <pre class="m-0 px-4 py-3 font-mono text-[12.5px] leading-[1.55] text-[var(--text-default)] whitespace-pre-wrap">{lines ? lines.join('\n') : text}</pre>
    {:else}
      <div class="flex h-full items-center justify-center px-6 py-10">
        <div class="max-w-md text-center">
          <div class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--brand)]">
            {#if emptyIcon}
              {@render emptyIcon()}
            {:else}
              <svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="1.6">
                <rect x="3.5" y="4.5" width="17" height="13" rx="2" />
                <path d="M7 10l3 2.5L7 15" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M12 15h5" stroke-linecap="round" />
              </svg>
            {/if}
          </div>
          <div class="text-sm font-medium text-[var(--text-default)]">{emptyTitle}</div>
          {#if emptyHint}
            <p class="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-[var(--text-muted)]">{emptyHint}</p>
          {/if}
        </div>
      </div>
    {/if}
  </div>
</div>
