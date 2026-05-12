<script lang="ts">
  /**
   * Live "pick a record" dropdown for relation-typed fields on
   * record-CRUD writes (and anywhere else we want to drop in an IRI
   * without making the user paste UUIDs).
   *
   * Calls the `search_module_records` MCP tool to hit the configured
   * FSR's ``GET /api/3/<module>?$search=<q>``; debounces typing so we
   * don't hammer the server on every keystroke. The selected value is
   * the record's IRI; the parent's `onChange` writes it back wherever
   * relations live.
   *
   * Free-text mode is preserved: clicking the input + typing a Jinja
   * expression like ``{{ vars.steps.X[0]['@id'] }}`` and blurring
   * still commits the literal string. The dropdown is suggestion-only.
   */
  import { onDestroy } from 'svelte';
  import { callMcpTool } from '../api';

  type Props = {
    /** Target module for the live search (e.g. ``people``, ``alerts``). */
    module: string;
    /** Current IRI / Jinja expression — passes through unchanged on
     * each keystroke; commits to onChange on blur or pick. */
    value: string;
    /** Fires with the new value (IRI from the picker, or whatever the
     * user typed). */
    onChange: (next: string) => void;
    /** Optional placeholder shown when the value is empty. */
    placeholder?: string;
    /** Optional aria-label for accessibility. */
    ariaLabel?: string;
  };

  let { module, value, onChange, placeholder = '', ariaLabel = 'relation picker' }: Props = $props();

  type SearchResult = { iri: string; label: string; id?: number | string | null };
  let results = $state<SearchResult[]>([]);
  let loading = $state(false);
  let lastError = $state<string | null>(null);
  let isOpen = $state(false);
  let query = $state('');
  // Track the most recent search request so out-of-order responses
  // don't overwrite a fresher result set with stale data.
  let inflight = 0;

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  onDestroy(() => { if (debounceTimer) clearTimeout(debounceTimer); });

  function open() {
    if (isOpen) return;
    isOpen = true;
    // Pre-populate with the unfiltered first page so the dropdown
    // never opens empty.
    if (!results.length && !loading) void runSearch('');
  }

  function close() {
    isOpen = false;
  }

  function scheduleSearch(q: string) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { void runSearch(q); }, 200);
  }

  async function runSearch(q: string) {
    if (!module) return;
    loading = true;
    lastError = null;
    const ticket = ++inflight;
    try {
      const res = await callMcpTool<Record<string, unknown>>('search_module_records', {
        module, q, limit: 12
      });
      if (ticket !== inflight) return;
      const r = res.result ?? {};
      if (!res.ok || r['ok'] === false) {
        lastError = String(r['message'] ?? res.error ?? 'search failed');
        results = [];
      } else {
        results = (r['results'] as SearchResult[]) ?? [];
      }
    } catch (e: any) {
      if (ticket === inflight) lastError = String(e?.message ?? e);
    } finally {
      if (ticket === inflight) loading = false;
    }
  }

  function pick(r: SearchResult) {
    onChange(r.iri);
    isOpen = false;
    query = '';
  }
</script>

<div class="relative">
  <input
    type="text"
    aria-label={ariaLabel}
    {value}
    {placeholder}
    onfocus={open}
    oninput={(e) => {
      const v = (e.currentTarget as HTMLInputElement).value;
      // Pass through every keystroke so users can type a Jinja
      // expression freely; the dropdown filters live records by the
      // separate `query` state (kept distinct so the bound value
      // doesn't fight the input).
      onChange(v);
    }}
    onblur={() => {
      // Delay close so a click on a dropdown row registers before the
      // dropdown unmounts.
      setTimeout(close, 150);
    }}
    class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 font-mono text-[11px]"
  />
  {#if isOpen}
    <div
      role="listbox"
      aria-label={`${module} records`}
      class="absolute left-0 z-20 mt-1 max-h-64 w-full overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] shadow-lg"
    >
      <input
        type="text"
        aria-label={`search ${module}`}
        placeholder={`filter ${module}…`}
        bind:value={query}
        oninput={(e) => scheduleSearch((e.currentTarget as HTMLInputElement).value)}
        onkeydown={(e) => { if (e.key === 'Escape') close(); }}
        class="sticky top-0 block w-full border-b border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 font-mono text-[11px]"
      />
      {#if loading}
        <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">searching…</p>
      {:else if lastError}
        <p class="px-2 py-1 text-[11px] text-rose-600 dark:text-rose-400">{lastError}</p>
      {:else if results.length === 0}
        <p class="px-2 py-1 text-[11px] italic text-[var(--text-faint)]">no records</p>
      {:else}
        <ul>
          {#each results as r (r.iri)}
            <li>
              <button
                type="button"
                onclick={() => pick(r)}
                class="block w-full px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
              >
                <div class="text-[11px] {r.iri === value ? 'font-bold text-[var(--brand)]' : ''}">{r.label}</div>
                <div class="truncate font-mono text-[10px] text-[var(--text-faint)]" title={r.iri}>{r.iri}</div>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>
