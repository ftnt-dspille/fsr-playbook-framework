<script lang="ts">
  /**
   * Live Jinja preview that sits next to a value input (set_variable
   * rows, decision conditions, anywhere the author types a `{{ … }}`).
   * Debounced so it doesn't fire on every keystroke; shows the resolved
   * value against the current playbook context + pinned sample record.
   */
  import { renderJinja, type RenderOutcome } from '../jinjaRender.svelte';

  type Props = { value: string };
  let { value }: Props = $props();

  let outcome = $state<RenderOutcome | null>(null);
  let timer: any = null;

  // Don't fire the render call while the user is actively typing or
  // navigating Monaco's autocomplete — the preview popping in
  // mid-keystroke is distracting and burns API requests on partial
  // expressions like `{{ vars.in` that always error.
  const DEBOUNCE_MS = 700;

  function autocompleteOpen(): boolean {
    return !!document.querySelector(
      '.monaco-editor .suggest-widget.visible, .monaco-editor .parameter-hints-widget.visible'
    );
  }

  function schedule(cur: string) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(async () => {
      // Defer one more cycle while a suggestion popup is up so we
      // don't render against an incomplete expression the user is
      // still picking from a menu.
      if (autocompleteOpen()) {
        schedule(cur);
        return;
      }
      outcome = await renderJinja(cur);
    }, DEBOUNCE_MS);
  }

  $effect(() => {
    const cur = value;
    if (timer) clearTimeout(timer);
    if (!cur || !cur.includes('{{')) {
      outcome = null;
      return;
    }
    outcome = { kind: 'pending' };
    schedule(cur);
  });

  function fmt(v: unknown): string {
    if (typeof v === 'string') return v;
    if (v === null || v === undefined) return String(v);
    try { return JSON.stringify(v); } catch { return String(v); }
  }
</script>

{#if outcome}
  <div class="mt-1 rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1">
    <div class="flex items-baseline gap-1.5">
      <span class="text-[9px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">→ renders to</span>
      {#if outcome.kind === 'pending'}
        <span class="text-[10px] italic text-[var(--text-faint)]">…</span>
      {:else if outcome.kind === 'rendered'}
        <code class="break-all font-mono text-[11px] text-emerald-600 dark:text-emerald-400">{fmt(outcome.value)}</code>
      {:else if outcome.kind === 'error'}
        <code class="break-all font-mono text-[11px] text-rose-600 dark:text-rose-400">{outcome.message}</code>
      {/if}
    </div>
  </div>
{/if}
