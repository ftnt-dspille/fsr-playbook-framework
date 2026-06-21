<script lang="ts">
  let {
    validateCount,
    inputTokens,
    outputTokens,
    elapsedMs,
    busy
  }: {
    validateCount: number;
    inputTokens: number;
    outputTokens: number;
    elapsedMs: number;
    busy: boolean;
  } = $props();

  function fmtElapsed(ms: number) {
    if (!ms) return '0s';
    const s = Math.round(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rs = s % 60;
    return `${m}m ${rs}s`;
  }
  function fmtTokens(n: number) {
    if (n < 1000) return `${n}`;
    if (n < 100_000) return `${(n / 1000).toFixed(1)}k`;
    return `${Math.round(n / 1000)}k`;
  }

  const totalTokens = $derived(inputTokens + outputTokens);
  const hasState = $derived(validateCount > 0 || totalTokens > 0);
</script>

{#if hasState}
  <div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--border-soft)] bg-[var(--bg-panel)] px-3 py-2 text-[10px] text-[var(--text-faint)] fade-in">
    {#if busy}
      <span class="relative flex h-1.5 w-1.5" aria-hidden="true">
        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--brand)] opacity-70"></span>
        <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--brand)]"></span>
      </span>
    {/if}
    <span title="Verify / validate calls observed in the agent loop this session">
      validate <span class="font-mono text-[var(--text-muted)]">{validateCount}</span>
    </span>
    <span title="Total tokens this session (input + output)">
      tokens <span class="font-mono text-[var(--text-muted)]">{fmtTokens(totalTokens)}</span>
    </span>
    <span title="Elapsed wall-clock from the first turn of this session">
      elapsed <span class="font-mono text-[var(--text-muted)]">{fmtElapsed(elapsedMs)}</span>
    </span>
  </div>
{/if}
