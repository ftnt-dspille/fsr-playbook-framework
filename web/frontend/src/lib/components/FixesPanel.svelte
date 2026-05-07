<script lang="ts">
  import type { Fix } from '$lib/api';

  let {
    fixes = [] as Fix[],
    editor,
    monaco,
    onApplied
  }: {
    /** Source-level auto-fixes from the latest validate response.
     * Bundled into `/api/yaml/validate` so this panel doesn't need its
     * own roundtrip. */
    fixes: Fix[];
    /** Monaco editor instance — passed up via MonacoYaml's `onEditor` prop. */
    editor: any | null;
    /** Monaco namespace (for Range / Selection construction). */
    monaco: any | null;
    /** Optional callback fired after each apply so the parent can re-validate. */
    onApplied?: (newYaml: string) => void;
  } = $props();

  /** Index of the currently expanded fix's preview pane, or null. */
  let previewIdx = $state<number | null>(null);

  /** Slice the editor's current text into a small N-line context window
   * around a fix, returning {before, original, after} as line arrays so
   * the template can render an in-place red/green strip. The editor
   * model is the source of truth — re-reading it means the preview
   * stays correct even after Cmd-Z. */
  function contextFor(f: Fix, contextLines = 2):
    | { before: string[]; orig: string[]; replaced: string[]; after: string[]; startLine: number }
    | null {
    if (!editor) return null;
    const model = editor.getModel?.();
    if (!model) return null;
    const total = model.getLineCount();
    const startLine = Math.max(1, f.line - contextLines);
    // f.end_line is 1-based; ranges that consume the trailing newline land
    // on `f.end_line` with end_col=1 (same as Monaco's), so the changed
    // span is lines f.line .. f.end_line - (end_col === 1 ? 1 : 0).
    const lastChanged = f.end_col === 1 ? f.end_line - 1 : f.end_line;
    const endLine = Math.min(total, lastChanged + contextLines);

    const before: string[] = [];
    for (let l = startLine; l < f.line; l++) before.push(model.getLineContent(l));
    const orig: string[] = [];
    for (let l = f.line; l <= lastChanged; l++) orig.push(model.getLineContent(l));
    const after: string[] = [];
    for (let l = lastChanged + 1; l <= endLine; l++) after.push(model.getLineContent(l));

    // Build the post-replacement view by splicing `f.replacement` into the
    // joined `orig` block at the (line, col) offsets. Cheap because the
    // slice is at most a handful of lines.
    const joined = orig.join('\n') + (f.end_col === 1 ? '\n' : '');
    const offsetOf = (lineIdx: number, col: number): number => {
      let off = 0;
      for (let i = 0; i < lineIdx; i++) off += orig[i].length + 1;
      return off + (col - 1);
    };
    const startOff = offsetOf(0, f.col);
    const endOff = offsetOf(f.end_line - f.line, f.end_col);
    const patched = joined.slice(0, startOff) + f.replacement + joined.slice(endOff);
    const replaced = patched.split('\n');
    // Drop the trailing empty entry the trailing-newline join introduces.
    if (replaced.length > 0 && replaced[replaced.length - 1] === '') replaced.pop();

    return { before, orig, replaced, after, startLine };
  }

  function rangeFor(f: Fix) {
    if (!monaco) return null;
    return new monaco.Range(f.line, f.col, f.end_line, f.end_col);
  }

  function applyOne(f: Fix) {
    if (!editor || !monaco) return;
    const range = rangeFor(f);
    if (!range) return;
    // executeEdits adds the patch to Monaco's undo stack so Cmd-Z reverts.
    // The synthetic source name shows up in the undo history label.
    editor.executeEdits('fsrpb-fix-warnings', [
      { range, text: f.replacement, forceMoveMarkers: true }
    ]);
    onApplied?.(editor.getValue());
  }

  function applyAll() {
    if (!editor || !monaco || !fixes.length) return;
    // Sort bottom-up so earlier offsets stay valid as later edits land.
    const ordered = [...fixes].sort(
      (a, b) => b.line - a.line || b.col - a.col
    );
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
    editor.revealRangeInCenter(rangeFor(f));
    editor.setSelection(rangeFor(f));
    editor.focus();
  }
</script>

<div class="flex h-full flex-col">
  <div class="flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-2.5">
    <div class="flex items-center gap-2">
      <span class="text-sm font-medium text-[var(--text-default)]">Auto-fixable warnings</span>
      <span
        class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-muted)]"
      >
        {fixes.length}
      </span>
    </div>
    <button
      type="button"
      class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1 text-xs font-medium text-[var(--text-default)] transition-colors hover:bg-[var(--bg-panel)] disabled:opacity-40"
      disabled={!fixes.length || !editor}
      onclick={applyAll}
    >
      Fix all
    </button>
  </div>

  {#if !fixes.length}
    <div class="flex h-full items-center justify-center px-6 py-10">
      <div class="max-w-md text-center">
        <div class="text-sm text-[var(--text-muted)]">No auto-fixable warnings.</div>
        <p class="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-[var(--text-faint)]">
          Fixes here are mechanical translations (em-dash step names, bare
          <code>yes</code>/<code>no</code> branches, missing
          <code>vars.input.params.</code> segments, <code>type: stop</code>).
          Other warnings show in the Diagnostics tab.
        </p>
      </div>
    </div>
  {:else}
    <ul class="divide-y divide-[var(--border-soft)] overflow-auto">
      {#each fixes as f, i}
        {@const ctx = previewIdx === i ? contextFor(f) : null}
        <li class="px-4 py-3 transition-colors hover:bg-[var(--bg-panel)]">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2 text-[11px]">
                <button
                  type="button"
                  class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[var(--text-muted)] hover:text-[var(--text-default)]"
                  onclick={() => revealFix(f)}
                  title="Jump to source"
                >
                  L{f.line}
                </button>
                <span class="font-mono text-[var(--text-faint)]">{f.code}</span>
              </div>
              <div class="mt-1 text-sm leading-snug text-[var(--text-default)]">
                {f.message}
              </div>
              <div class="mt-2 grid gap-1 font-mono text-[11px]">
                <div class="flex items-start gap-2">
                  <span class="mt-0.5 shrink-0 text-rose-400">−</span>
                  <code class="min-w-0 break-all text-[var(--text-muted)]">{f.original.trim()}</code>
                </div>
                <div class="flex items-start gap-2">
                  <span class="mt-0.5 shrink-0 text-emerald-400">+</span>
                  <code class="min-w-0 break-all text-[var(--text-default)]"
                    >{f.replacement.trim()}</code
                  >
                </div>
              </div>
            </div>
            <div class="flex shrink-0 flex-col items-stretch gap-1">
              <button
                type="button"
                class="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2 py-1 text-xs font-medium text-[var(--brand)] transition-colors hover:bg-[var(--bg-panel)] disabled:opacity-40"
                disabled={!editor}
                onclick={() => applyOne(f)}
              >
                Apply
              </button>
              <button
                type="button"
                class="rounded-md border border-[var(--border-soft)] bg-transparent px-2 py-0.5 text-[11px] font-medium text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-panel)] disabled:opacity-40"
                disabled={!editor}
                onclick={() => (previewIdx = previewIdx === i ? null : i)}
              >
                {previewIdx === i ? 'Hide' : 'Preview'}
              </button>
            </div>
          </div>
          {#if ctx}
            <div class="mt-3 overflow-x-auto rounded-md border border-[var(--border-soft)] bg-[var(--bg-panel)] py-1 font-mono text-[11px] leading-snug">
              {#each ctx.before as ln, j}
                <div class="flex gap-3 px-2 text-[var(--text-faint)]">
                  <span class="w-8 shrink-0 select-none text-right">{ctx.startLine + j}</span>
                  <span class="whitespace-pre">{ln}</span>
                </div>
              {/each}
              {#each ctx.orig as ln, j}
                <div class="flex gap-3 bg-rose-500/10 px-2">
                  <span class="w-8 shrink-0 select-none text-right text-rose-300">−{f.line + j}</span>
                  <span class="whitespace-pre text-[var(--text-default)]">{ln}</span>
                </div>
              {/each}
              {#each ctx.replaced as ln, j}
                <div class="flex gap-3 bg-emerald-500/10 px-2">
                  <span class="w-8 shrink-0 select-none text-right text-emerald-300">+{f.line + j}</span>
                  <span class="whitespace-pre text-[var(--text-default)]">{ln}</span>
                </div>
              {/each}
              {#each ctx.after as ln, j}
                <div class="flex gap-3 px-2 text-[var(--text-faint)]">
                  <span class="w-8 shrink-0 select-none text-right">
                    {(f.end_col === 1 ? f.end_line : f.end_line + 1) + j}
                  </span>
                  <span class="whitespace-pre">{ln}</span>
                </div>
              {/each}
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
