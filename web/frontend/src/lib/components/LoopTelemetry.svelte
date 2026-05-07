<script lang="ts">
  import type { LadderRung } from '$lib/api';

  let {
    rungs,
    achieved,
    errorCount,
    warningCount,
    errorTrend,
    validateCount,
    inputTokens,
    outputTokens,
    elapsedMs,
    busy
  }: {
    rungs: LadderRung[];
    achieved: number;
    errorCount: number;
    warningCount: number;
    /** -1 down (improving), 0 flat, 1 up (regressing). null = first turn. */
    errorTrend: -1 | 0 | 1 | null;
    validateCount: number;
    inputTokens: number;
    outputTokens: number;
    elapsedMs: number;
    busy: boolean;
  } = $props();

  const RUNG_ORDER: LadderRung['id'][] = [
    'compile',
    'prechecks',
    'reachability',
    'dry_run',
    'outcome'
  ];

  function rungAt(id: LadderRung['id']): LadderRung | undefined {
    return rungs.find((r) => r.id === id);
  }

  function rungColor(state: LadderRung['state']) {
    switch (state) {
      case 'passed':
        return 'border-[var(--status-ok)]/40 bg-[var(--status-ok)]/15 text-[var(--status-ok)]';
      case 'failed':
        return 'border-[var(--status-err)]/40 bg-[var(--status-err)]/15 text-[var(--status-err)]';
      case 'skipped':
        return 'border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--text-faint)]';
      case 'pending':
      default:
        return 'border-[var(--border-soft)] bg-[var(--bg-panel)] text-[var(--text-muted)]';
    }
  }

  function rungIcon(state: LadderRung['state']) {
    if (state === 'passed') return '✓';
    if (state === 'failed') return '!';
    if (state === 'skipped') return '–';
    return '·';
  }

  const trendGlyph = $derived(
    errorTrend === null
      ? ''
      : errorTrend < 0
        ? '↘'
        : errorTrend > 0
          ? '↗'
          : '→'
  );
  const trendTone = $derived(
    errorTrend === null
      ? 'text-[var(--text-faint)]'
      : errorTrend < 0
        ? 'text-[var(--status-ok)]'
        : errorTrend > 0
          ? 'text-[var(--status-err)]'
          : 'text-[var(--status-warn)]'
  );

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
  const hasState = $derived(rungs.length > 0 || validateCount > 0 || totalTokens > 0);
</script>

{#if hasState}
  <div class="flex flex-col gap-2 border-b border-[var(--border-soft)] bg-[var(--bg-panel)] px-3 py-2 fade-in">
    <div class="flex items-center gap-1.5">
      {#each RUNG_ORDER as id, i}
        {@const rung = rungAt(id)}
        {@const state = rung?.state ?? 'pending'}
        <div
          class={'flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[10px] font-medium tracking-wide ' +
            rungColor(state)}
          title={rung
            ? `${rung.label}: ${state}${rung.summary ? ' — ' + rung.summary : ''}`
            : 'pending'}
        >
          <span class="font-mono leading-none">L{i + 1}</span>
          <span class="leading-none">{rungIcon(state)}</span>
        </div>
        {#if i < RUNG_ORDER.length - 1}
          <span
            class={'h-px w-2 ' +
              (i < achieved ? 'bg-[var(--status-ok)]/60' : 'bg-[var(--border)]')}
            aria-hidden="true"
          ></span>
        {/if}
      {/each}
      <span class="ml-auto flex items-center gap-1 text-[10px] text-[var(--text-faint)]">
        {#if busy}
          <span class="relative flex h-1.5 w-1.5">
            <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--brand)] opacity-70"></span>
            <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--brand)]"></span>
          </span>
        {/if}
        ladder
      </span>
    </div>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--text-faint)]">
      <span title="Compile errors at the latest turn">
        <span class="font-mono text-[var(--text-muted)]">{errorCount}</span> err
      </span>
      <span title="Compile warnings at the latest turn">
        <span class="font-mono text-[var(--text-muted)]">{warningCount}</span> warn
      </span>
      <span title="Trend in error count vs the previous turn">
        trend
        <span class={'ml-0.5 font-mono ' + trendTone}>{trendGlyph || '—'}</span>
      </span>
      <span title="Validate calls observed in the agent loop this session">
        validate <span class="font-mono text-[var(--text-muted)]">{validateCount}</span>
      </span>
      <span title="Total tokens this session (input + output)">
        tokens <span class="font-mono text-[var(--text-muted)]">{fmtTokens(totalTokens)}</span>
      </span>
      <span title="Elapsed wall-clock from the first turn of this session">
        elapsed <span class="font-mono text-[var(--text-muted)]">{fmtElapsed(elapsedMs)}</span>
      </span>
    </div>
  </div>
{/if}
