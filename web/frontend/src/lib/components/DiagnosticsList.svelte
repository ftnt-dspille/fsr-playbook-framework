<script lang="ts">
  import type { Marker, Fix } from '$lib/api';

  let {
    markers,
    fixes = [] as Fix[],
    editor = null,
    monaco = null,
    onApplied
  }: {
    markers: Marker[];
    /** Optional auto-fixes. Rendered inline on the matching marker row
     * (line + code match) or appended as standalone rows when unmatched. */
    fixes?: Fix[];
    editor?: any | null;
    monaco?: any | null;
    onApplied?: (newYaml: string) => void;
  } = $props();

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

  function matchFix(m: Marker): Fix | undefined {
    return fixes.find((f) => f.line === m.line && f.code === m.code);
  }

  let unmatchedFixes = $derived(
    fixes.filter((f) => !markers.some((m) => m.line === f.line && m.code === f.code))
  );

  function rangeFor(f: Fix) {
    if (!monaco) return null;
    return new monaco.Range(f.line, f.col, f.end_line, f.end_col);
  }

  function applyOne(f: Fix) {
    if (!editor || !monaco) return;
    const range = rangeFor(f);
    if (!range) return;
    editor.executeEdits('fsrpb-fix-warnings', [
      { range, text: f.replacement, forceMoveMarkers: true }
    ]);
    onApplied?.(editor.getValue());
  }

  function applyAll() {
    if (!editor || !monaco || !fixes.length) return;
    const ordered = [...fixes].sort((a, b) => b.line - a.line || b.col - a.col);
    const ops = ordered
      .map((f) => {
        const range = rangeFor(f);
        return range
          ? { range, text: f.replacement, forceMoveMarkers: true }
          : null;
      })
      .filter((x): x is { range: any; text: string; forceMoveMarkers: boolean } => !!x);
    editor.pushUndoStop();
    editor.executeEdits('fsrpb-fix-warnings:all', ops);
    editor.pushUndoStop();
    onApplied?.(editor.getValue());
  }

  function revealFix(f: Fix) {
    if (!editor) return;
    const r = rangeFor(f);
    if (!r) return;
    editor.revealRangeInCenter(r);
    editor.setSelection(r);
    editor.focus();
  }

  let canApply = $derived(!!editor && !!monaco);
</script>

{#if !markers.length && !fixes.length}
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
  {#if fixes.length > 1 && canApply}
    <div class="flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-1.5 text-[11px] text-[var(--text-muted)]">
      <span>{fixes.length} auto-fixable</span>
      <button
        type="button"
        class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-0.5 font-medium text-[var(--text-default)] hover:bg-[var(--bg-panel)]"
        onclick={applyAll}
      >Fix all</button>
    </div>
  {/if}
  <ul class="divide-y divide-[var(--border-soft)] fade-in">
    {#each markers as m}
      {@const cls = severityClasses(m.severity)}
      {@const fix = matchFix(m)}
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
            {#if fix}
              <div class="mt-2 grid gap-1 font-mono text-[11px]">
                <div class="flex items-start gap-2">
                  <span class="mt-0.5 shrink-0 text-rose-400">−</span>
                  <code class="min-w-0 break-all text-[var(--text-muted)]">{fix.original.trim()}</code>
                </div>
                <div class="flex items-start gap-2">
                  <span class="mt-0.5 shrink-0 text-emerald-400">+</span>
                  <code class="min-w-0 break-all text-[var(--text-default)]">{fix.replacement.trim()}</code>
                </div>
              </div>
            {/if}
          </div>
          {#if fix}
            <button
              type="button"
              class="shrink-0 rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--brand)] hover:bg-[var(--bg-panel)] disabled:opacity-40"
              disabled={!canApply}
              title={canApply ? 'Apply this fix to the YAML' : 'Fixes apply through the YAML editor; switch to CLI mode'}
              onclick={() => applyOne(fix)}
            >Apply</button>
          {/if}
        </div>
      </li>
    {/each}
    {#each unmatchedFixes as f}
      {@const cls = severityClasses(f.severity)}
      <li class="px-4 py-2.5 transition-colors hover:bg-[var(--bg-panel)]">
        <div class="flex items-start gap-3">
          <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full {cls.dot}" aria-hidden="true"></span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2 text-[11px]">
              <span class="rounded-md border px-1.5 py-0.5 font-medium uppercase tracking-wide {cls.chip}">fix</span>
              <button
                type="button"
                class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[var(--text-muted)] hover:text-[var(--text-default)]"
                onclick={() => revealFix(f)}
                disabled={!canApply}
                title="Jump to source"
              >L{f.line}</button>
              <span class="font-mono text-[var(--text-faint)]">{f.code}</span>
            </div>
            <div class="mt-1 text-sm leading-snug text-[var(--text-default)]">{f.message}</div>
            <div class="mt-2 grid gap-1 font-mono text-[11px]">
              <div class="flex items-start gap-2">
                <span class="mt-0.5 shrink-0 text-rose-400">−</span>
                <code class="min-w-0 break-all text-[var(--text-muted)]">{f.original.trim()}</code>
              </div>
              <div class="flex items-start gap-2">
                <span class="mt-0.5 shrink-0 text-emerald-400">+</span>
                <code class="min-w-0 break-all text-[var(--text-default)]">{f.replacement.trim()}</code>
              </div>
            </div>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--brand)] hover:bg-[var(--bg-panel)] disabled:opacity-40"
            disabled={!canApply}
            title={canApply ? 'Apply this fix to the YAML' : 'Fixes apply through the YAML editor; switch to CLI mode'}
            onclick={() => applyOne(f)}
          >Apply</button>
        </div>
      </li>
    {/each}
  </ul>
{/if}
