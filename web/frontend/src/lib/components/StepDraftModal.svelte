<script lang="ts">
  /**
   * "Describe what you want" modal for AI-driven step authoring.
   *
   * Reusable across every step type the drafter supports — the
   * inspector's launcher button passes `stepType`, the active
   * `module` (when applicable), and the node's current `arguments`.
   * The modal manages prompt entry → backend round-trip → diff
   * preview → apply/cancel; the parent owns persistence (one
   * `setArgs` call when the user accepts the draft).
   */
  import type { VisualNode } from '../api';

  type Props = {
    node: VisualNode;
    /** Called with the proposed args when the user clicks Apply.
     * Caller writes through the visual store. */
    onApply: (next: Record<string, unknown>) => void;
    /** Called when the user closes/cancels. */
    onClose: () => void;
    /** Active module name for trigger / record_crud step types — the
     * drafter uses it to pull schema + picklists. Optional. */
    module?: string | null;
  };

  let { node, onApply, onClose, module = null }: Props = $props();

  let intent = $state('');
  let loading = $state(false);
  type Diagnostic = {
    severity: 'error' | 'warning' | 'unknown';
    code: string;
    path: string;
    message: string;
    suggestion: string;
  };
  let result = $state<{
    proposed_args?: Record<string, unknown>;
    error?: string;
    raw_text?: string;
    prompt_chars?: number;
    diagnostics?: Diagnostic[];
  } | null>(null);
  let textarea = $state<HTMLTextAreaElement | null>(null);

  // Pre-fill suggestions vary by step type so the user has a starter
  // they can edit instead of staring at a blank textarea.
  const HINTS: Record<string, string> = {
    decision: 'e.g. "branch on whether the indicator reputation is malicious or unknown"',
    manual_input: 'e.g. "ask the analyst for org name + branch, with Approve and Reject buttons"',
    find_record: 'e.g. "find tasks linked to the current incident assigned to me"',
    create_record: 'e.g. "create a comment on the incident with the run summary"',
    update_record: 'e.g. "mark this task as completed and append a status note"',
    set_variable: 'e.g. "store the indicator value and reputation lookup result"',
    delay: 'e.g. "wait 5 minutes before the next check"',
    workflow_reference: 'e.g. "call the IP Enrichment playbook with the alert\'s source IP"',
    code_snippet: 'e.g. "extract the JSON body and return only the high-severity items"',
    start_on_create: 'e.g. "fire on new high-severity phishing alerts that aren\'t already escalated"',
    start_on_update: 'e.g. "fire when an incident moves to the In Progress state"',
    start: 'e.g. "manual trigger on the alerts module"',
    manual_action: 'e.g. "trigger when an analyst clicks Block IP on an alert"',
    api_call: 'e.g. "trigger when an external system POSTs an indicator"',
    raise_exception: 'e.g. "halt with a clear message when the lookup returned nothing"',
    terminate: 'e.g. "end the run quietly when the record is already closed"',
    assert: 'e.g. "fail unless the response status is 200"'
  };

  $effect(() => {
    // Focus the textarea on mount so the user can start typing
    // immediately without an extra click.
    queueMicrotask(() => textarea?.focus());
  });

  async function submit() {
    const trimmed = intent.trim();
    if (!trimmed || loading) return;
    loading = true;
    result = null;
    try {
      const r = await fetch('/api/visual/draft-step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          step_type: node.type,
          intent: trimmed,
          module,
          current_args: node.arguments ?? {},
        })
      });
      const data = await r.json();
      if (!r.ok) {
        result = { error: data?.detail ?? data?.error ?? `HTTP ${r.status}` };
      } else if (!data.ok) {
        result = {
          error: data.error ?? 'drafter returned ok=false',
          raw_text: data.raw_text,
          prompt_chars: data.prompt_chars,
        };
      } else {
        result = {
          proposed_args: data.proposed_args,
          raw_text: data.raw_text,
          prompt_chars: data.prompt_chars,
          diagnostics: (data.diagnostics ?? []) as Diagnostic[],
        };
      }
    } catch (e: any) {
      result = { error: String(e?.message ?? e) };
    } finally {
      loading = false;
    }
  }

  function fmt(v: unknown): string {
    if (v === undefined) return '';
    try { return JSON.stringify(v, null, 2); } catch { return String(v); }
  }

  function apply() {
    if (!result?.proposed_args) return;
    onApply(result.proposed_args);
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') { onClose(); return; }
    // ⌘/Ctrl-Enter submits the prompt.
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { submit(); }
  }
</script>

<div
  role="dialog"
  aria-modal="true"
  aria-label="Describe step"
  class="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-16"
  onkeydown={onKey}
>
  <div
    class="w-full max-w-2xl rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-4 shadow-xl"
  >
    <header class="flex items-center justify-between">
      <div>
        <div class="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          ✨ Describe this step
        </div>
        <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
          Type what you want; the assistant drafts <code class="font-mono">{node.type}</code> args using the live module schema + production patterns.
        </p>
      </div>
      <button
        type="button"
        class="text-xs text-[var(--text-muted)] hover:text-[var(--text-default)]"
        onclick={onClose}
        aria-label="Close"
      >×</button>
    </header>

    <textarea
      bind:this={textarea}
      bind:value={intent}
      placeholder={HINTS[node.type] ?? 'Describe what you want this step to do…'}
      rows="4"
      class="mt-3 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-sm"
    ></textarea>

    <div class="mt-2 flex items-center justify-between">
      <p class="text-[10px] text-[var(--text-faint)]">
        ⌘/Ctrl-Enter to submit · Esc to close
      </p>
      <button
        type="button"
        class="rounded border border-[var(--border-soft)] bg-[var(--brand)] px-3 py-1 text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        onclick={submit}
        disabled={!intent.trim() || loading}
      >{loading ? 'Drafting…' : 'Draft step'}</button>
    </div>

    {#if result}
      {#if result.error}
        <div class="mt-3 rounded border border-rose-300 bg-rose-50 p-2 dark:bg-rose-950/30">
          <div class="text-[10px] font-semibold uppercase tracking-wider text-rose-700 dark:text-rose-400">error</div>
          <p class="mt-1 text-xs text-rose-700 dark:text-rose-400">{result.error}</p>
          {#if result.raw_text}
            <details class="mt-2">
              <summary class="cursor-pointer text-[10px] text-[var(--text-muted)]">model output</summary>
              <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-canvas)] p-1 text-[11px]">{result.raw_text}</pre>
            </details>
          {/if}
        </div>
      {:else if result.proposed_args}
        <div class="mt-3">
          <div class="mb-1 flex items-center justify-between">
            <div class="text-[10px] font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">proposal</div>
            {#if result.prompt_chars}
              <span class="text-[10px] text-[var(--text-faint)]">prompt {result.prompt_chars} chars</span>
            {/if}
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <div class="text-[10px] uppercase tracking-wider text-[var(--text-muted)]">current</div>
              <pre class="mt-1 max-h-72 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-[11px]">{fmt(node.arguments ?? {})}</pre>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wider text-[var(--text-muted)]">proposed</div>
              <pre class="mt-1 max-h-72 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-[11px]">{fmt(result.proposed_args)}</pre>
            </div>
          </div>
          {#if (result.diagnostics ?? []).length > 0}
            {@const errs = (result.diagnostics ?? []).filter((d) => d.severity === 'error')}
            {@const warns = (result.diagnostics ?? []).filter((d) => d.severity === 'warning')}
            <div class="mt-2 rounded border {errs.length ? 'border-rose-300 bg-rose-50 dark:bg-rose-950/30' : 'border-amber-300 bg-amber-50 dark:bg-amber-950/30'} p-2">
              <div class="text-[10px] font-semibold uppercase tracking-wider {errs.length ? 'text-rose-700 dark:text-rose-400' : 'text-amber-700 dark:text-amber-400'}">
                {errs.length > 0 ? `${errs.length} compiler error${errs.length === 1 ? '' : 's'}` : `${warns.length} warning${warns.length === 1 ? '' : 's'}`}
              </div>
              <ul class="mt-1 space-y-1 text-[11px]">
                {#each result.diagnostics ?? [] as d}
                  <li class="font-mono">
                    <span class={d.severity === 'error' ? 'text-rose-600 dark:text-rose-400' : 'text-amber-700 dark:text-amber-400'}>
                      [{d.code}]
                    </span>
                    {d.message}
                    {#if d.suggestion}
                      <span class="text-[var(--text-muted)]"> — {d.suggestion}</span>
                    {/if}
                  </li>
                {/each}
              </ul>
              {#if errs.length > 0}
                <p class="mt-1 text-[10px] text-rose-700 dark:text-rose-400">
                  Apply will still write the args — the compiler runs again on save.
                  Edit the proposal first if you'd rather start clean.
                </p>
              {/if}
            </div>
          {:else}
            <div class="mt-2 text-[10px] text-emerald-600 dark:text-emerald-400">
              ✓ validated cleanly against the compiler
            </div>
          {/if}
          <div class="mt-3 flex justify-end gap-2">
            <button
              type="button"
              class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-xs hover:bg-[var(--bg-elev)]"
              onclick={onClose}
            >Cancel</button>
            <button
              type="button"
              class="rounded border border-[var(--border-soft)] bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700"
              onclick={apply}
            >Apply to step</button>
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>
