<script lang="ts">
  /**
   * Operation combobox for connector_op steps.
   *
   * Asks the server for `verbose` results so it can render the
   * one-line op description and a verification dot (green/red/gray)
   * alongside `op_name`. Re-ranks the server's list by a local
   * recently-picked store (opPickerPrefs) so the user's habitual ops
   * float to the top without a backend dependency.
   *
   * Only commits on selection / Enter / blur so `get_op_schema` doesn't
   * fire mid-keystroke and surface "operation 'b' not found".
   */
  import { callMcpTool } from '../api';
  import { recordPick, scoreFor } from '../opPickerPrefs';

  type Verification = { status: string; method?: string; ts?: string };
  type Suggestion = {
    op_name: string;
    title?: string;
    description?: string;
    verification?: Verification | null;
  };
  type Props = {
    connector: string;
    value: string;
    placeholder?: string;
    onCommit: (value: string) => void;
  };
  let { connector, value, placeholder = 'e.g. get_ticket_details', onCommit }: Props = $props();

  // svelte-ignore state_referenced_locally
  let inputText = $state(value ?? '');
  // svelte-ignore state_referenced_locally
  let lastValueProp = $state(value);
  $effect(() => {
    if (value !== lastValueProp) {
      lastValueProp = value;
      inputText = value ?? '';
    }
  });

  let suggestions = $state<Suggestion[]>([]);
  let open = $state(false);
  let activeIdx = $state(-1);
  let queryAt = 0;

  // Verification dot colors: green = tested_pass, red = tested_fail,
  // gray = merely seen / unknown. Mirrors the canvas store-verification
  // pattern in StepNode.
  const VERIF_COLOR: Record<string, string> = {
    tested_pass: '#16a34a',
    tested_fail: '#dc2626',
    seen: '#9ca3af'
  };

  async function refresh(q: string) {
    if (!connector) { suggestions = []; return; }
    const stamp = ++queryAt;
    try {
      const r = await callMcpTool<{ matches: Suggestion[] }>(
        'find_operation', { connector, q: q ?? '', limit: 25, verbose: true }
      );
      if (stamp !== queryAt) return;
      if (!r.ok) { suggestions = []; return; }
      const matches = r.result?.matches ?? [];
      // Re-rank by local user-pref score. Stable sort preserves the
      // server's own order (verification status, then alpha) inside a
      // score tier — the server has signal we lack (e.g. tested_fail
      // demotion), and we only want to *boost* familiar ops.
      const score = scoreFor(connector);
      suggestions = matches
        .map((m, i) => ({ m, s: score(m.op_name), i }))
        .sort((a, b) => (b.s - a.s) || (a.i - b.i))
        .map((x) => x.m);
    } catch {
      if (stamp === queryAt) suggestions = [];
    }
  }

  function commit(v: string) {
    if (v === lastValueProp) return;
    lastValueProp = v;
    onCommit(v);
  }

  function pick(s: Suggestion) {
    inputText = s.op_name;
    open = false;
    activeIdx = -1;
    recordPick(connector, s.op_name);
    commit(s.op_name);
  }

  function onKey(e: KeyboardEvent) {
    if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      open = true;
      e.preventDefault();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, suggestions.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIdx >= 0 && activeIdx < suggestions.length) pick(suggestions[activeIdx]);
      else { open = false; commit(inputText); }
    } else if (e.key === 'Escape') {
      open = false;
    }
  }
</script>

<div class="fsrpb-operation-picker">
  <input
    type="text"
    autocomplete="off"
    aria-label="Operation"
    {placeholder}
    value={inputText}
    disabled={!connector}
    class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px] disabled:opacity-50"
    onfocus={() => { open = true; refresh(inputText); }}
    onblur={() => { setTimeout(() => (open = false), 120); commit(inputText); }}
    oninput={(e) => {
      inputText = (e.currentTarget as HTMLInputElement).value;
      open = true;
      activeIdx = -1;
      refresh(inputText);
    }}
    onkeydown={onKey}
  />
  {#if open && suggestions.length > 0}
    <ul class="fsrpb-operation-picker-menu" role="listbox">
      {#each suggestions as s, i (s.op_name)}
        <li
          role="option"
          aria-selected={i === activeIdx}
          class="fsrpb-operation-picker-row"
          class:fsrpb-operation-picker-row--active={i === activeIdx}
          onmousedown={(e) => { e.preventDefault(); pick(s); }}
          onmouseenter={() => (activeIdx = i)}
        >
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="flex items-center gap-1.5">
              <span class="font-mono text-[11px] truncate">{s.op_name}</span>
              {#if s.verification}
                <span
                  class="inline-block h-1.5 w-1.5 rounded-full"
                  style="background: {VERIF_COLOR[s.verification.status] ?? '#d1d5db'}"
                  title={`verification: ${s.verification.status}${s.verification.method ? ` (${s.verification.method})` : ''}`}
                  aria-label={`verification ${s.verification.status}`}
                ></span>
              {/if}
            </span>
            {#if s.title}<span class="text-[10px] text-[var(--text-faint)] truncate">{s.title}</span>{/if}
            {#if s.description}<span class="text-[10px] text-[var(--text-muted)] line-clamp-2">{s.description}</span>{/if}
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .fsrpb-operation-picker { position: relative; }
  .fsrpb-operation-picker-menu {
    position: absolute;
    top: calc(100% + 2px);
    left: 0;
    right: 0;
    max-height: 360px;
    overflow-y: auto;
    background: var(--bg-canvas, white);
    border: 1px solid var(--border-soft, #e5e7eb);
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    z-index: 100;
    margin: 0;
    padding: 4px 0;
    list-style: none;
  }
  .fsrpb-operation-picker-row {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 6px 10px; cursor: pointer;
  }
  .fsrpb-operation-picker-row--active,
  .fsrpb-operation-picker-row:hover {
    background: var(--bg-elev, #f3f4f6);
  }
  .line-clamp-2 {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
</style>
