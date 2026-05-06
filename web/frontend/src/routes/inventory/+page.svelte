<script lang="ts">
  // Inventory dashboard — "what does the assistant know?"
  // Powered by GET /api/ref/inventory + /api/ref/inventory/search.
  // Demonstrates the assistant is grounded in a real, queryable index —
  // not just an LLM guessing.
  import { onMount } from 'svelte';

  type Summary = {
    summary: {
      reference_db: Record<string, number>;
      trust: { trusted: number; total: number };
      last_probes: { probe: string; ts: string; version: string }[];
      catalog: Record<string, number>;
    };
    top_api_products: { name: string; category: string; entry_count: number }[];
  };

  type ConnectorHit = { name: string; version: string; category: string };
  type OperationHit = { connector_name: string; op_name: string; title: string };
  type JinjaHit = { name: string; signature: string };
  type ApiExampleHit = {
    product: string;
    action: string;
    http_method: string;
    http_path: string;
    entry_id?: number;
  };

  type SearchHit = {
    connectors: ConnectorHit[];
    operations: OperationHit[];
    jinja_macros: JinjaHit[];
    api_examples: ApiExampleHit[];
  };

  let data = $state<Summary | null>(null);
  let err = $state<string | null>(null);
  let q = $state('');
  let hits = $state<SearchHit | null>(null);
  let searching = $state(false);
  let toast = $state<string | null>(null);
  let searchDebounce: ReturnType<typeof setTimeout> | undefined;
  let toastTimeout: ReturnType<typeof setTimeout> | undefined;

  const SUGGESTIONS = ['virustotal', 'fortigate', 'slack', 'picklist', 'http_request', 'github'];

  onMount(async () => {
    try {
      const r = await fetch('/api/ref/inventory');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      data = await r.json();
    } catch (e: any) {
      err = e?.message ?? String(e);
    }
  });

  function fmt(n: number): string {
    return n.toLocaleString();
  }

  function showToast(msg: string) {
    toast = msg;
    if (toastTimeout) clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => (toast = null), 2400);
  }

  function runSearch(needle: string) {
    q = needle;
  }

  $effect(() => {
    if (searchDebounce) clearTimeout(searchDebounce);
    if (!q.trim()) {
      hits = null;
      return;
    }
    const needle = q.trim();
    searching = true;
    searchDebounce = setTimeout(async () => {
      try {
        // We need entry_id on api_examples for the insert button — fetch
        // a richer search via the api-examples-aware endpoint when needed.
        const r = await fetch(
          `/api/ref/inventory/search?q=${encodeURIComponent(needle)}&limit=5`
        );
        hits = r.ok ? await r.json() : null;
        // Enrich api_examples with entry_id by hitting search_api_examples.
        if (hits && needle.length > 1) {
          try {
            const r2 = await fetch(
              `/api/ref/api-examples?q=${encodeURIComponent(needle)}&limit=5`
            );
            if (r2.ok) {
              const richer = await r2.json();
              if (Array.isArray(richer)) hits.api_examples = richer;
            }
          } catch {}
        }
      } finally {
        searching = false;
      }
    }, 250);
  });

  async function insertHttpStep(entry: ApiExampleHit) {
    if (entry.entry_id == null) {
      showToast('No entry_id — cannot synthesize');
      return;
    }
    try {
      const r = await fetch(
        `/api/ref/synthesize-http-step?entry_id=${entry.entry_id}` +
          `&step_name=${encodeURIComponent('Call ' + entry.product)}`
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      await navigator.clipboard.writeText(j.yaml);
      showToast('Copied YAML step to clipboard — paste into Design view');
    } catch (e: any) {
      showToast(`Failed: ${e?.message ?? e}`);
    }
  }

  const STAT_LABELS: Record<string, string> = {
    connectors: 'Connectors',
    operations: 'Operations',
    operation_params: 'Op parameters',
    step_types: 'Step types',
    jinja_macros: 'Jinja filters',
    playbooks_seen: 'Live playbooks indexed'
  };
</script>

<div class="mx-auto max-w-6xl space-y-8 p-6">
  <header>
    <h1 class="text-2xl font-semibold text-zinc-100">What the assistant knows</h1>
    <p class="mt-1 text-sm text-zinc-400">
      Every number here is a real row in a queryable index — not a guess.
      The agent does SQL lookups before it touches an LLM.
    </p>
  </header>

  {#if err}
    <div class="rounded border border-red-700 bg-red-950/40 p-3 text-sm text-red-300">
      Failed to load inventory: {err}
    </div>
  {:else if !data}
    <div class="text-sm text-zinc-500">Loading…</div>
  {:else}
    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
        FortiSOAR reference store
      </h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {#each Object.entries(data.summary.reference_db) as [k, v]}
          <div class="rounded border border-zinc-800 bg-zinc-900/50 p-4">
            <div class="text-2xl font-semibold text-zinc-100">{fmt(v)}</div>
            <div class="text-xs text-zinc-400">{STAT_LABELS[k] ?? k}</div>
          </div>
        {/each}
      </div>
      <div class="mt-3 text-xs text-zinc-500">
        Trust ladder: {fmt(data.summary.trust.trusted)} / {fmt(data.summary.trust.total)}
        rows confirmed live + tested.
      </div>
    </section>

    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
        Third-party API examples (HTTP virtual-connector corpus)
      </h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div class="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <div class="text-2xl font-semibold text-zinc-100">
            {fmt(data.summary.catalog.products)}
          </div>
          <div class="text-xs text-zinc-400">Products covered</div>
        </div>
        <div class="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <div class="text-2xl font-semibold text-zinc-100">
            {fmt(data.summary.catalog.entries)}
          </div>
          <div class="text-xs text-zinc-400">API examples indexed</div>
        </div>
        <div class="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <div class="text-2xl font-semibold text-zinc-100">
            {fmt(data.summary.catalog.connector_lifecycle)}
          </div>
          <div class="text-xs text-zinc-400">Lifecycle records</div>
        </div>
      </div>
      <div class="mt-3 text-xs text-zinc-500">
        Top products by entry count (click to search):
      </div>
      <ul class="mt-1 space-y-1 text-sm">
        {#each data.top_api_products.slice(0, 8) as p}
          <li class="flex items-center justify-between border-b border-zinc-800/60 py-1">
            <button
              type="button"
              class="truncate text-left text-zinc-300 hover:text-zinc-100 hover:underline"
              onclick={() => runSearch(p.name.split(' ')[0].toLowerCase())}
            >
              {p.name}
            </button>
            <span class="ml-3 font-mono text-xs text-zinc-500">{fmt(p.entry_count)}</span>
          </li>
        {/each}
      </ul>
    </section>

    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
        Cross-store search
      </h2>
      <input
        type="text"
        bind:value={q}
        placeholder="virustotal, ip reputation, picklist…"
        class="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-500 focus:outline-none"
      />
      {#if !q && !searching}
        <div class="mt-2 flex flex-wrap gap-2 text-xs">
          <span class="text-zinc-500">Try:</span>
          {#each SUGGESTIONS as s}
            <button
              type="button"
              class="rounded border border-zinc-800 px-2 py-0.5 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
              onclick={() => runSearch(s)}
            >{s}</button>
          {/each}
        </div>
      {/if}
      {#if searching}
        <div class="mt-2 text-xs text-zinc-500">Searching…</div>
      {/if}
      {#if hits}
        <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <!-- Connectors -->
          <div class="rounded border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-zinc-400">
              Connectors · {hits.connectors.length}
            </div>
            {#if hits.connectors.length === 0}
              <div class="text-xs text-zinc-600">no matches</div>
            {:else}
              <ul class="space-y-1 text-sm">
                {#each hits.connectors as c}
                  <li class="flex items-center justify-between gap-2">
                    <span class="font-mono text-zinc-200">{c.name}</span>
                    <span class="text-xs text-zinc-500">v{c.version} · {c.category}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- Operations -->
          <div class="rounded border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-zinc-400">
              Operations · {hits.operations.length}
            </div>
            {#if hits.operations.length === 0}
              <div class="text-xs text-zinc-600">no matches</div>
            {:else}
              <ul class="space-y-1 text-sm">
                {#each hits.operations as o}
                  <li>
                    <span class="font-mono text-zinc-200">{o.connector_name}.{o.op_name}</span>
                    <span class="ml-2 text-xs text-zinc-500">{o.title ?? ''}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- Jinja macros -->
          <div class="rounded border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-zinc-400">
              Jinja filters · {hits.jinja_macros.length}
            </div>
            {#if hits.jinja_macros.length === 0}
              <div class="text-xs text-zinc-600">no matches</div>
            {:else}
              <ul class="space-y-1 text-sm">
                {#each hits.jinja_macros as j}
                  <li class="font-mono text-zinc-200">
                    {j.name}<span class="text-xs text-zinc-500">{j.signature ?? ''}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- API examples — actionable -->
          <div class="rounded border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-zinc-400">
              API examples · {hits.api_examples.length}
            </div>
            {#if hits.api_examples.length === 0}
              <div class="text-xs text-zinc-600">no matches</div>
            {:else}
              <ul class="space-y-2 text-sm">
                {#each hits.api_examples as e}
                  <li class="flex items-center justify-between gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2">
                        {#if e.http_method}
                          <span class="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
                            {e.http_method}
                          </span>
                        {/if}
                        <span class="truncate font-mono text-xs text-zinc-200">
                          {e.http_path || e.action}
                        </span>
                      </div>
                      <div class="truncate text-xs text-zinc-500">
                        {e.product} · {e.action}
                      </div>
                    </div>
                    {#if e.entry_id != null}
                      <button
                        type="button"
                        class="shrink-0 rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
                        onclick={() => insertHttpStep(e)}
                        title="Synthesize an HTTP-connector step from this entry and copy YAML to clipboard"
                      >
                        → HTTP step
                      </button>
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        </div>
      {/if}
    </section>

    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
        Recent probe runs
      </h2>
      <div class="space-y-1 text-xs text-zinc-400">
        {#each data.summary.last_probes.slice(0, 8) as p}
          <div class="flex gap-3 border-b border-zinc-800/60 py-1">
            <span class="w-44 font-mono text-zinc-300">{p.probe}</span>
            <span class="text-zinc-500">{p.ts}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if toast}
    <div
      class="fixed bottom-6 right-6 rounded border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-100 shadow-lg"
    >
      {toast}
    </div>
  {/if}
</div>
