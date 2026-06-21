<script lang="ts">
  /**
   * "Sample record" picker for the trigger step's Args tab.
   *
   * Loads recent records from FSR for the given module and lets the
   * author pin one as the canonical sample. Once pinned, the variable
   * picker uses its real field values as the preview alongside
   * `vars.input.records[0].*` paths — so the author can validate
   * field existence and see real values without running the playbook.
   */
  import { sampleRecordsStore } from '../triggerModuleFields.svelte';
  import { formatFsrValue, truncate } from '../fsrValue';
  import {
    fetchRecentRuns,
    fetchRecordByIri,
    fetchRunDetail,
    type RecentRun
  } from '../api';

  type Props = { module: string };
  let { module }: Props = $props();

  let runs = $state<RecentRun[]>([]);
  let runsLoading = $state(false);
  let runsError = $state<string | null>(null);
  let pinningRunIri = $state<string | null>(null);

  async function loadRuns() {
    runsLoading = true;
    runsError = null;
    try {
      const rs = await fetchRecentRuns(undefined, 10);
      // Only show runs that touched this module — others won't give
      // us a useful sample for vars.input.records[0].
      runs = rs.filter((r) =>
        r.records.some((iri) => iri.includes(`/api/3/${module}/`))
      );
      if (runs.length === 0) {
        runsError = `No recent FSR runs touched the \`${module}\` module.`;
      }
    } finally {
      runsLoading = false;
    }
  }

  async function pinFromRun(run: RecentRun) {
    const iri = run.records.find((x) => x.includes(`/api/3/${module}/`));
    if (!iri) return;
    pinningRunIri = iri;
    try {
      // Two fetches in parallel: (a) the record itself for the trigger
      // sample, (b) the full run detail so we can (in a follow-up) pull
      // step variables / outputs and seed jinjaShapesStore with REAL
      // observed types. For now we just stash the detail under the
      // module's pick — surfacing it is a small UX add.
      const [rec, _detail] = await Promise.all([
        fetchRecordByIri(iri),
        run.id != null ? fetchRunDetail(run.id) : Promise.resolve(null)
      ]);
      if (rec) {
        sampleRecordsStore.pick(module, rec);
        expanded = false;
      }
    } finally {
      pinningRunIri = null;
    }
  }

  function fmtRunTime(ts: string | null): string {
    if (!ts) return '?';
    try {
      const d = new Date(ts);
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    } catch {
      return ts;
    }
  }

  let records = $state<Array<Record<string, unknown>>>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let expanded = $state(false);

  /** Pick a short label per record: name/title/subject/@id last segment. */
  function recLabel(r: Record<string, unknown>): string {
    for (const k of ['name', 'title', 'subject']) {
      const v = (r as any)[k];
      if (typeof v === 'string' && v) return v;
    }
    const iri = (r as any)['@id'];
    if (typeof iri === 'string') {
      const segs = iri.split('/').filter(Boolean);
      return segs[segs.length - 1];
    }
    return '(unnamed)';
  }

  /** Pull a friendly secondary line (severity/status/createDate).
   *  Picklist objects are unwrapped via formatFsrValue → itemValue. */
  function recSubtitle(r: Record<string, unknown>): string {
    const bits: string[] = [];
    for (const k of ['severity', 'status', 'type', 'createDate']) {
      const v = (r as any)[k];
      if (v == null) continue;
      const s = formatFsrValue(v);
      if (!s || s === 'null' || s === 'undefined') continue;
      bits.push(`${k}: ${truncate(s, 24)}`);
      if (bits.length >= 3) break;
    }
    return bits.join(' · ');
  }

  async function load() {
    if (!module) { records = []; return; }
    loading = true;
    error = null;
    try {
      const recs = await sampleRecordsStore.fetch(module, 10);
      records = recs;
      if (recs.length === 0) {
        error = 'FSR returned no records (or is offline). Check the connection and the module name.';
      }
    } finally {
      loading = false;
    }
  }

  // Auto-load on module change. Picker store already caches per
  // module so this is cheap on re-mount. Recent runs reload too since
  // they're filtered by module.
  $effect(() => {
    void module;
    load();
    loadRuns();
  });

  function pick(r: Record<string, unknown>) {
    sampleRecordsStore.pick(module, r);
    expanded = false;
  }

  function clearPick() {
    sampleRecordsStore.pick(module, null);
  }

  let pickedHere = $derived(
    sampleRecordsStore.pickedModule === module
      ? sampleRecordsStore.picked
      : null
  );
</script>

<div class="mt-3 rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] p-2">
  <div class="flex items-center justify-between gap-2">
    <div>
      <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Sample record
      </div>
      <p class="mt-0.5 text-[11px] text-[var(--text-faint)]">
        {#if runs.length > 0}
          Iterating on a real run? Pin its record below — the picker
          will preview actual values for
          <code class="font-mono">{`{{ vars.input.records[0].* }}`}</code>.
          Or pick any recent <code class="font-mono">{module}</code> for greenfield work.
        {:else}
          Building from scratch — pin a representative
          <code class="font-mono">{module}</code> record so the variable picker
          shows real field values for
          <code class="font-mono">{`{{ vars.input.records[0].* }}`}</code>.
        {/if}
      </p>
    </div>
    <button
      type="button"
      class="rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-[11px] font-medium hover:bg-[var(--bg-elev)] disabled:opacity-50"
      onclick={() => (expanded = !expanded)}
      disabled={loading}
    >{expanded ? 'Hide' : (pickedHere ? 'Change' : 'Pick')}</button>
  </div>

  {#if pickedHere}
    <div class="mt-2 rounded border border-emerald-500/40 bg-emerald-500/5 p-2">
      <div class="flex items-baseline justify-between gap-2">
        <div class="text-[11px] font-medium text-[var(--text-default)]">
          {recLabel(pickedHere)}
        </div>
        <button
          type="button"
          class="text-[10px] text-rose-600 hover:text-rose-700"
          onclick={clearPick}
        >Unpin</button>
      </div>
      {#if recSubtitle(pickedHere)}
        <div class="mt-0.5 text-[10px] text-[var(--text-faint)]">{recSubtitle(pickedHere)}</div>
      {/if}
      <details class="mt-1">
        <summary class="cursor-pointer text-[10px] uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-default)]">
          Show fields
        </summary>
        <pre class="mt-1 max-h-48 overflow-auto rounded bg-[var(--bg-canvas)] p-2 text-[11px]">{JSON.stringify(pickedHere, null, 2)}</pre>
      </details>
    </div>
  {/if}

  {#if expanded}
    <div class="mt-2 space-y-3">
      <!-- When runs exist, lead with them: the record from a real run
           carries the same context (linked records, populated fields,
           runtime state) the playbook will see in production. -->
      {#if runs.length > 0}
        <div>
          <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            From a real run <span class="ml-1 text-[9px] font-normal normal-case text-[var(--text-faint)]">recommended</span>
          </div>
          <p class="mt-0.5 text-[10px] text-[var(--text-faint)]">
            FSR workflow history — pin the record an actual run fired on.
            Best for iterating on a live playbook.
          </p>
          {#if runsLoading}
            <p class="mt-1 text-[11px] italic text-[var(--text-faint)]">loading…</p>
          {:else}
            <ul class="mt-1 max-h-48 space-y-1 overflow-auto">
              {#each runs as run (run.id ?? run.created)}
                {@const iri = run.records.find((x) => x.includes(`/api/3/${module}/`))}
                <li>
                  <button
                    type="button"
                    onclick={() => pinFromRun(run)}
                    disabled={!!pinningRunIri}
                    class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-left hover:bg-[var(--bg-elev)] disabled:opacity-50"
                  >
                    <div class="flex items-baseline justify-between gap-2">
                      <span class="text-[11px] font-medium text-[var(--text-default)]">
                        {run.name || '(unnamed)'}
                      </span>
                      <span class="text-[10px] text-[var(--text-faint)]">{fmtRunTime(run.created)}</span>
                    </div>
                    <div class="text-[10px] text-[var(--text-faint)]">
                      {run.status ?? '?'} · <code class="font-mono">{iri ? iri.split('/').slice(-1)[0] : '—'}</code>
                    </div>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}

      <!-- Greenfield path: pick a representative record straight from
           the module. Always available, even before any runs exist. -->
      <div>
        <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {#if runs.length > 0}Or pick from {module}{:else}Pick a {module} to design against{/if}
        </div>
        {#if loading}
          <p class="mt-1 text-[11px] italic text-[var(--text-faint)]">loading…</p>
        {:else if error}
          <p class="mt-1 text-[11px] text-rose-600 dark:text-rose-400">{error}</p>
        {:else if records.length === 0}
          <p class="mt-1 text-[11px] italic text-[var(--text-faint)]">No records found.</p>
        {:else}
          <ul class="mt-1 max-h-48 space-y-1 overflow-auto">
            {#each records as r, idx (idx)}
              <li>
                <button
                  type="button"
                  onclick={() => pick(r)}
                  class="block w-full rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-left hover:bg-[var(--bg-elev)]"
                >
                  <div class="text-[11px] font-medium text-[var(--text-default)]">{recLabel(r)}</div>
                  {#if recSubtitle(r)}
                    <div class="text-[10px] text-[var(--text-faint)]">{recSubtitle(r)}</div>
                  {/if}
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="flex gap-3">
        <button
          type="button"
          class="text-[10px] text-[var(--text-muted)] hover:text-[var(--text-default)]"
          onclick={() => { load(); loadRuns(); }}
        >↻ Refresh both</button>
      </div>
    </div>
  {/if}
</div>
