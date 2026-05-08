<script lang="ts">
  /**
   * Operation combobox for connector_op steps. Sibling to
   * ConnectorPicker — only commits on selection / Enter / blur so
   * `get_op_schema` doesn't fire mid-keystroke and surface
   * "operation 'b' not found" errors while the user is still typing.
   */
  import { callMcpTool } from '../api';

  type Suggestion = { op_name: string; title?: string };
  type Props = {
    connector: string;
    value: string;
    placeholder?: string;
    onCommit: (value: string) => void;
  };
  let { connector, value, placeholder = 'e.g. get_ticket_details', onCommit }: Props = $props();

  let inputText = $state(value ?? '');
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

  async function refresh(q: string) {
    if (!connector) { suggestions = []; return; }
    const stamp = ++queryAt;
    try {
      const r = await callMcpTool<{ matches: Suggestion[] }>(
        'find_operation', { connector, q: q ?? '', limit: 25 }
      );
      if (stamp !== queryAt) return;
      if (r.ok) suggestions = r.result?.matches ?? [];
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
          <span class="flex flex-col min-w-0">
            <span class="font-mono text-[11px] truncate">{s.op_name}</span>
            {#if s.title}<span class="text-[10px] text-[var(--text-faint)] truncate">{s.title}</span>{/if}
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
    max-height: 320px;
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
    display: flex; align-items: center; gap: 8px;
    padding: 6px 10px; cursor: pointer;
  }
  .fsrpb-operation-picker-row--active,
  .fsrpb-operation-picker-row:hover {
    background: var(--bg-elev, #f3f4f6);
  }
</style>
