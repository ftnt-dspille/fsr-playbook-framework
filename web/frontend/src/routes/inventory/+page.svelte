<script lang="ts">
  // Inventory dashboard — "what does the assistant know?"
  // Powered by GET /api/ref/inventory + /api/ref/inventory/search.
  // Demonstrates the assistant is grounded in a real, queryable index —
  // not just an LLM guessing.
  import { onMount } from 'svelte';

  import PageHeader from '$lib/components/PageHeader.svelte';

  type Summary = {
    summary: {
      reference_db: Record<string, number>;
      trust: { trusted: number; total: number };
      last_probes: { probe: string; ts: string; version: string }[];
      catalog: Record<string, number>;
    };
    top_api_products: { name: string; category: string; entry_count: number }[];
  };

  type ConnectorHit = { name: string; version: string; category: string; label?: string };
  type OperationHit = { connector_name: string; op_name: string; title: string; category?: string };
  type StepTypeHit = { name: string; label: string | null; description: string | null };
  type JinjaHit = { name: string; signature: string };
  type ModuleHit = { name: string; label: string | null; plural: string | null };
  type ModuleFieldHit = { module_name: string; field_name: string; label: string | null; type: string };
  type PlaybookStepHit = {
    step_type_name: string | null;
    step_name: string | null;
    playbook_name: string | null;
    collection: string | null;
    source: string;
  };
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
    step_types: StepTypeHit[];
    jinja_macros: JinjaHit[];
    modules: ModuleHit[];
    module_fields: ModuleFieldHit[];
    playbook_steps: PlaybookStepHit[];
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

  // Curated, click-to-search browse chips. Each group targets a slice
  // of the index so a user can explore "what's in here?" without ever
  // typing — the most common request when demoing the dashboard.
  type BrowseGroup = {
    label: string;
    blurb: string;
    items: { term: string; alias?: string }[];
  };
  const BROWSE_GROUPS: BrowseGroup[] = [
    {
      label: 'Security & EDR connectors',
      blurb: 'Endpoint, network, threat-intel vendors',
      items: [
        { term: 'virustotal' },
        { term: 'crowdstrike' },
        { term: 'sentinelone', alias: 'SentinelOne' },
        { term: 'fortigate' },
        { term: 'fortianalyzer' },
        { term: 'paloalto', alias: 'Palo Alto' },
        { term: 'splunk' },
        { term: 'recorded future' },
      ],
    },
    {
      label: 'Identity, ticketing & chat',
      blurb: 'IAM, ITSM, collaboration',
      items: [
        { term: 'okta' },
        { term: 'azure ad', alias: 'Azure AD' },
        { term: 'jira' },
        { term: 'servicenow' },
        { term: 'pagerduty' },
        { term: 'slack' },
        { term: 'teams' },
        { term: 'github' },
      ],
    },
    {
      label: 'Common operations',
      blurb: 'Action verbs across connectors',
      items: [
        { term: 'get_reputation' },
        { term: 'scan_url' },
        { term: 'isolate_endpoint' },
        { term: 'block_ip' },
        { term: 'send_message' },
        { term: 'create_ticket' },
        { term: 'http_request' },
        { term: 'fetch_records' },
      ],
    },
    {
      label: 'Jinja filters',
      blurb: 'Templating idioms used inside steps',
      items: [
        { term: 'picklist' },
        { term: 'json_query' },
        { term: 'fromIRI' },
        { term: 'resolveRange' },
        { term: 'b64encode' },
        { term: 'regex_search' },
        { term: 'tojson' },
        { term: 'yaql' },
      ],
    },
    {
      label: 'Picklists',
      blurb: 'Drop-down value sets the compiler resolves',
      items: [
        { term: 'Severity' },
        { term: 'AlertStatus' },
        { term: 'IncidentStatus' },
        { term: 'TrafficLightProtocol', alias: 'TLP' },
        { term: 'IndicatorType' },
        { term: 'ThreatType' },
      ],
    },
    {
      label: 'API example verbs',
      blurb: 'HTTP virtual-connector recipes',
      items: [
        { term: 'list users' },
        { term: 'create incident' },
        { term: 'update ticket' },
        { term: 'search alerts' },
        { term: 'send alert' },
        { term: 'export report' },
      ],
    },
  ];

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
          `/api/ref/inventory/search?q=${encodeURIComponent(needle)}&limit=15`
        );
        hits = r.ok ? await r.json() : null;
        // Enrich api_examples with entry_id by hitting search_api_examples.
        if (hits && needle.length > 1) {
          try {
            const r2 = await fetch(
              `/api/ref/api-examples?q=${encodeURIComponent(needle)}&limit=15`
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

<div class="flex h-full flex-col">
  <PageHeader
    eyebrow="Reference store"
    title="What the assistant knows"
    subtitle="Every number here is a real row in a queryable index — not a guess. The agent does SQL lookups before it touches an LLM."
  />
  <div class="flex-1 overflow-y-auto fade-in">
    <div class="mx-auto max-w-6xl space-y-8 p-6 pb-16">

  {#if err}
    <div class="rounded border border-red-700 bg-red-950/40 p-3 text-sm text-red-300">
      Failed to load inventory: {err}
    </div>
  {:else if !data}
    <div class="text-sm text-[var(--text-faint)]">Loading…</div>
  {:else}
    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--text-faint)]">
        FortiSOAR reference store
      </h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {#each Object.entries(data.summary.reference_db) as [k, v]}
          <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/50 p-4">
            <div class="text-2xl font-semibold text-[var(--text-default)]">{fmt(v)}</div>
            <div class="text-xs text-[var(--text-muted)]">{STAT_LABELS[k] ?? k}</div>
          </div>
        {/each}
      </div>
      <div class="mt-3 text-xs text-[var(--text-faint)]">
        Trust ladder: {fmt(data.summary.trust.trusted)} / {fmt(data.summary.trust.total)}
        rows confirmed live + tested.
      </div>
    </section>

    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--text-faint)]">
        Third-party API examples (HTTP virtual-connector corpus)
      </h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/50 p-4">
          <div class="text-2xl font-semibold text-[var(--text-default)]">
            {fmt(data.summary.catalog.products)}
          </div>
          <div class="text-xs text-[var(--text-muted)]">Products covered</div>
        </div>
        <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/50 p-4">
          <div class="text-2xl font-semibold text-[var(--text-default)]">
            {fmt(data.summary.catalog.entries)}
          </div>
          <div class="text-xs text-[var(--text-muted)]">API examples indexed</div>
        </div>
        <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/50 p-4">
          <div class="text-2xl font-semibold text-[var(--text-default)]">
            {fmt(data.summary.catalog.connector_lifecycle)}
          </div>
          <div class="text-xs text-[var(--text-muted)]">Lifecycle records</div>
        </div>
      </div>
      <div class="mt-3 text-xs text-[var(--text-faint)]">
        Top products by entry count (click to search):
      </div>
      <ul class="mt-1 space-y-1 text-sm">
        {#each data.top_api_products.slice(0, 8) as p}
          <li class="flex items-center justify-between border-b border-[var(--border-soft)]/60 py-1">
            <button
              type="button"
              class="truncate text-left text-[var(--text-muted)] hover:text-[var(--text-default)] hover:underline"
              onclick={() => runSearch(p.name.split(' ')[0].toLowerCase())}
            >
              {p.name}
            </button>
            <span class="ml-3 font-mono text-xs text-[var(--text-faint)]">{fmt(p.entry_count)}</span>
          </li>
        {/each}
      </ul>
    </section>

    <section>
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--text-faint)]">
        Cross-store search
      </h2>
      <div class="flex items-center gap-2">
        <input
          type="text"
          bind:value={q}
          placeholder="virustotal, ip reputation, picklist…"
          class="flex-1 rounded border border-[var(--border)] bg-[var(--bg-panel)] px-3 py-2 text-sm text-[var(--text-default)] placeholder:text-[var(--text-faint)] focus:border-[var(--brand)] focus:outline-none"
        />
        {#if q}
          <button
            type="button"
            class="rounded border border-[var(--border)] px-3 py-2 text-xs text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
            onclick={() => runSearch('')}
            title="Clear search"
          >Clear</button>
        {/if}
      </div>

      <!-- Always-visible browse panel. The whole point: zero typing
           required. Each chip fires the same search the input would. -->
      <div class="mt-4 rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/30 p-3">
        <div class="mb-2 flex items-baseline justify-between">
          <div class="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Browse the index
          </div>
          <div class="text-[11px] text-[var(--text-faint)]">
            click any term to search across connectors, ops, filters & API examples
          </div>
        </div>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {#each BROWSE_GROUPS as g}
            <div>
              <div class="mb-1 text-[11px] font-semibold uppercase text-[var(--text-muted)]">
                {g.label}
              </div>
              <div class="mb-2 text-[11px] text-[var(--text-faint)]">{g.blurb}</div>
              <div class="flex flex-wrap gap-1.5">
                {#each g.items as it}
                  <button
                    type="button"
                    class="rounded border px-2 py-0.5 text-xs transition-colors {q.trim().toLowerCase() === it.term.toLowerCase() ? 'border-emerald-600 bg-emerald-900/30 text-emerald-200' : 'border-[var(--border-soft)] text-[var(--text-muted)] hover:border-[var(--border)] hover:text-[var(--text-default)]'}"
                    onclick={() => runSearch(it.term)}
                    title={`Search for "${it.term}"`}
                  >{it.alias ?? it.term}</button>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      </div>
      {#if searching}
        <div class="mt-2 text-xs text-[var(--text-faint)]">Searching…</div>
      {/if}
      {#if hits}
        <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <!-- Connectors -->
          <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
              Connectors · {hits.connectors.length}
            </div>
            {#if hits.connectors.length === 0}
              <div class="text-xs text-[var(--text-faint)]">no matches</div>
            {:else}
              <ul class="space-y-1 text-sm">
                {#each hits.connectors as c}
                  <li class="flex items-center justify-between gap-2">
                    <span class="font-mono text-[var(--text-default)]">{c.name}</span>
                    <span class="text-xs text-[var(--text-faint)]">v{c.version} · {c.category}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- Operations -->
          <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
              Operations · {hits.operations.length}
            </div>
            {#if hits.operations.length === 0}
              <div class="text-xs text-[var(--text-faint)]">no matches</div>
            {:else}
              <ul class="space-y-1 text-sm">
                {#each hits.operations as o}
                  <li>
                    <span class="font-mono text-[var(--text-default)]">{o.connector_name}.{o.op_name}</span>
                    <span class="ml-2 text-xs text-[var(--text-faint)]">{o.title ?? ''}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- Step types -->
          {#if hits.step_types?.length}
            <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
              <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
                Step types · {hits.step_types.length}
              </div>
              <ul class="space-y-1 text-sm">
                {#each hits.step_types as t}
                  <li>
                    <span class="font-mono text-[var(--text-default)]">{t.name}</span>
                    {#if t.label}<span class="text-xs text-[var(--text-faint)]"> · {t.label}</span>{/if}
                    {#if t.description}
                      <div class="text-xs text-[var(--text-faint)] truncate">{t.description}</div>
                    {/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          <!-- Jinja macros -->
          <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
              Jinja filters · {hits.jinja_macros.length}
            </div>
            {#if hits.jinja_macros.length === 0}
              <div class="text-xs text-[var(--text-faint)]">no matches</div>
            {:else}
              <ul class="space-y-1 text-sm">
                {#each hits.jinja_macros as j}
                  <li class="font-mono text-[var(--text-default)]">
                    {j.name}<span class="text-xs text-[var(--text-faint)]">{j.signature ?? ''}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- Modules -->
          {#if hits.modules?.length}
            <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
              <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
                Modules · {hits.modules.length}
              </div>
              <ul class="space-y-1 text-sm">
                {#each hits.modules as m}
                  <li>
                    <span class="font-mono text-[var(--text-default)]">{m.name}</span>
                    {#if m.label}<span class="text-xs text-[var(--text-faint)]"> · {m.label}</span>{/if}
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          <!-- Module fields -->
          {#if hits.module_fields?.length}
            <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
              <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
                Module fields · {hits.module_fields.length}
              </div>
              <ul class="space-y-1 text-sm">
                {#each hits.module_fields as f}
                  <li>
                    <span class="font-mono text-[var(--text-default)]">
                      {f.module_name}.{f.field_name}
                    </span>
                    <span class="text-xs text-[var(--text-faint)]">
                      · {f.type}{f.label ? ` · ${f.label}` : ''}
                    </span>
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          <!-- Playbook step examples -->
          {#if hits.playbook_steps?.length}
            <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
              <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
                Playbook step examples · {hits.playbook_steps.length}
              </div>
              <ul class="space-y-1 text-sm">
                {#each hits.playbook_steps as s}
                  <li>
                    <span class="font-mono text-[var(--text-default)]">
                      {s.step_name || '(unnamed)'}
                    </span>
                    <span class="text-xs text-[var(--text-faint)]">
                      · {s.step_type_name || '?'}
                    </span>
                    <div class="text-xs text-[var(--text-faint)] truncate">
                      {s.collection ? `${s.collection} / ` : ''}{s.playbook_name || ''}
                      <span class="text-[var(--text-faint)]"> · {s.source}</span>
                    </div>
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          <!-- API examples — actionable -->
          <div class="rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-3">
            <div class="mb-2 text-xs font-semibold uppercase text-[var(--text-muted)]">
              API examples · {hits.api_examples.length}
            </div>
            {#if hits.api_examples.length === 0}
              <div class="text-xs text-[var(--text-faint)]">no matches</div>
            {:else}
              <ul class="space-y-2 text-sm">
                {#each hits.api_examples as e}
                  <li class="flex items-center justify-between gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2">
                        {#if e.http_method}
                          <span class="rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                            {e.http_method}
                          </span>
                        {/if}
                        <span class="truncate font-mono text-xs text-[var(--text-default)]">
                          {e.http_path || e.action}
                        </span>
                      </div>
                      <div class="truncate text-xs text-[var(--text-faint)]">
                        {e.product} · {e.action}
                      </div>
                    </div>
                    {#if e.entry_id != null}
                      <button
                        type="button"
                        class="shrink-0 rounded border border-[var(--border)] px-2 py-1 text-xs text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
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
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--text-faint)]">
        Recent probe runs
      </h2>
      <div class="space-y-1 text-xs text-[var(--text-muted)]">
        {#each data.summary.last_probes.slice(0, 8) as p}
          <div class="flex gap-3 border-b border-[var(--border-soft)]/60 py-1">
            <span class="w-44 font-mono text-[var(--text-muted)]">{p.probe}</span>
            <span class="text-[var(--text-faint)]">{p.ts}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}

    {#if toast}
      <div
        class="fixed bottom-6 right-6 rounded border border-[var(--border)] bg-[var(--bg-panel)] px-4 py-2 text-sm text-[var(--text-default)] shadow-lg"
      >
        {toast}
      </div>
    {/if}
    </div>
  </div>
</div>
