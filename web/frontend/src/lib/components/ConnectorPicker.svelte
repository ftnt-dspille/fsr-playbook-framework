<script lang="ts">
  /**
   * Combobox replacement for `<datalist>` so the connector dropdown
   * can render the connector's icon next to each suggestion.
   *
   * Important behavior: while the user is typing we ONLY refresh the
   * suggestion list. We do NOT push every keystroke up to the parent.
   * `onCommit` fires on three events: a list pick, Enter, or blur.
   * That keeps consumers like StepInspectorArgsTab from triggering
   * `get_op_schema` (or any other side-effect) on every partial value
   * — which would otherwise flash "operation 'b' not found" before
   * the user finished typing.
   */
  import { callMcpTool } from '../api';
  import ConnectorIcon from './ConnectorIcon.svelte';

  type Suggestion = { name: string; label?: string; category?: string };
  type Props = {
    value: string;
    placeholder?: string;
    ariaLabel?: string;
    onCommit: (value: string) => void;
  };
  let { value, placeholder = 'e.g. jira', ariaLabel = 'Connector', onCommit }: Props = $props();

  // Internal input text — kept separate from the parent prop so that
  // refreshing the dropdown can't fight a stale prop value. Synced
  // FROM the prop only when it changes externally (e.g. node switch).
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

  async function refresh(q: string) {
    const stamp = ++queryAt;
    try {
      const r = await callMcpTool<{ matches: Suggestion[] }>('find_connector', { q: q ?? '', limit: 25 });
      if (stamp !== queryAt) return; // stale
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
    inputText = s.name;
    open = false;
    activeIdx = -1;
    commit(s.name);
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

<div class="fsrpb-connector-picker">
  <input
    type="text"
    autocomplete="off"
    aria-label={ariaLabel}
    {placeholder}
    value={inputText}
    class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
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
    <ul class="fsrpb-connector-picker-menu" role="listbox">
      {#each suggestions as s, i (s.name)}
        <li
          role="option"
          aria-selected={i === activeIdx}
          class="fsrpb-connector-picker-row"
          class:fsrpb-connector-picker-row--active={i === activeIdx}
          onmousedown={(e) => { e.preventDefault(); pick(s); }}
          onmouseenter={() => (activeIdx = i)}
        >
          <ConnectorIcon name={s.name} size="sm" />
          <span class="flex flex-col min-w-0">
            <span class="font-mono text-[11px] truncate">{s.name}</span>
            {#if s.label}<span class="text-[10px] text-[var(--text-faint)] truncate">{s.label}</span>{/if}
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .fsrpb-connector-picker {
    position: relative;
  }
  .fsrpb-connector-picker-menu {
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
  .fsrpb-connector-picker-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    cursor: pointer;
  }
  .fsrpb-connector-picker-row--active,
  .fsrpb-connector-picker-row:hover {
    background: var(--bg-elev, #f3f4f6);
  }
</style>
