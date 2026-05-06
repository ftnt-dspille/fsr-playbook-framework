<script lang="ts">
  type Tool = { name: string };
  type Card = {
    code: string; // short uppercase tag in lieu of an icon
    title: string;
    blurb: string;
    accent: string;
    bullets?: string[];
    primary?: { label: string; href: string };
    secondary?: { label: string; href: string };
    tools?: Tool[];
  };

  type Upcoming = {
    code: string;
    title: string;
    body: string;
    notes?: string[];
    eta?: string;
  };

  const cards: Card[] = [
    {
      code: 'REC',
      title: 'Generate from a recipe',
      blurb:
        'Ready-to-push playbooks for the patterns you build over and over. Picklists, modules, validation handled.',
      accent: 'emerald',
      bullets: [
        'Threat-feed ingestion (TAXII2 / AWS / Recorded Future style)',
        'Data ingestion (alerts or incidents from a SIEM-style fetch op)',
        'Layered ruleset validator catches archetype-specific mistakes'
      ],
      primary: { label: 'Open a sample', href: '/?example=recipe_threat_feed.yaml' },
      secondary: { label: 'Recipe docs', href: '/docs#tools' },
      tools: [{ name: 'fsrpb generate-recipe' }, { name: 'validate_yaml' }]
    },
    {
      code: 'LIB',
      title: 'Start from a sample playbook',
      blurb:
        '13 working fixtures covering set / decision / connector / manual-input / parent-child. Each ships with an end-to-end test runner.',
      accent: 'sky',
      bullets: [
        'Run any one with fsrpb e2e run examples/<name>.test.yaml',
        'Run all 11 demo fixtures: fsrpb e2e all'
      ],
      primary: { label: 'Browse examples', href: '/browse' },
      secondary: { label: 'Open Design tab', href: '/' }
    },
    {
      code: 'AGT',
      title: 'Let an agent build it from a one-line ask',
      blurb:
        'Describe what you want; the LLM uses 20+ MCP tools to look up connectors, write YAML, validate, and run it — no CLI hand-off.',
      accent: 'violet',
      bullets: [
        'Demo prompt: "Build me a playbook that looks up an IP on VirusTotal and tells me if it is malicious."',
        'Agent flow: find_connector → get_op_schema → emit YAML → validate → compile → push → run',
        'LLM-agnostic: structured tool I/O works with Claude, GPT, or local models'
      ],
      primary: { label: 'Open chat', href: '/' },
      tools: [
        { name: 'find_connector' },
        { name: 'get_op_schema' },
        { name: 'validate_yaml' },
        { name: 'run_op' }
      ]
    },
    {
      code: 'HTTP',
      title: 'Reach vendors without a native connector',
      blurb:
        'A 207,419-entry catalog spanning 6,927 third-party products lets the agent author HTTP-connector playbooks for vendors we have no dedicated connector for.',
      accent: 'indigo',
      bullets: [
        'Search the catalog by product or operation',
        'Synthesize an http_request step with method, path, auth, and params pre-filled',
        'Deterministic translation — the LLM picks the entry; code emits the YAML'
      ],
      primary: { label: 'Open Inventory', href: '/inventory' },
      tools: [{ name: 'search_api_examples' }, { name: 'synthesize_http_step' }]
    },
    {
      code: 'TRG',
      title: 'Troubleshoot a broken playbook',
      blurb:
        'List recent failures (live and historical), inspect the real run env, fix the shape mismatch, push, re-run.',
      accent: 'rose',
      bullets: [
        'Sees runs across the live AND historical tables (FSR purges every 30–60 min)',
        'Filter by tag, user, or time window',
        'render_jinja against a real past run before committing the fix'
      ],
      primary: { label: 'Open Run tab', href: '/run' },
      tools: [
        { name: 'list_recent_failed_runs' },
        { name: 'get_run_env' },
        { name: 'render_jinja' },
        { name: 'push_playbook' }
      ]
    },
    {
      code: 'REV',
      title: 'Reverse-engineer or audit',
      blurb:
        'Pull a live playbook to YAML, diff against your edits, search the corpus of 1,664 workflows for similar patterns.',
      accent: 'amber',
      bullets: [
        'fsrpb pull "<name>"  →  YAML',
        'fsrpb diff "<name>"  →  what changed',
        'find_jinja_pattern   →  who else uses this idiom'
      ],
      primary: { label: 'Search corpus', href: '/browse' },
      tools: [{ name: 'search_playbooks' }, { name: 'find_jinja_pattern' }]
    },
    {
      code: 'INV',
      title: 'See exactly what the assistant knows',
      blurb:
        'A live audit of every connector, operation, parameter, step type, Jinja filter, picklist, playbook, and third-party API entry indexed in the reference store.',
      accent: 'teal',
      bullets: [
        '714 connectors · 6,773 operations · 26,093 parameters',
        '172 Jinja filters · 1,664 mined playbooks · 207,419 API examples',
        'Trust ladder shows which rows are confirmed live + tested',
        'Cross-store search returns results across all five categories at once'
      ],
      primary: { label: 'Open Inventory', href: '/inventory' },
      tools: [{ name: 'fsrpb inventory' }]
    },
    {
      code: 'CHK',
      title: 'Verify before you push',
      blurb:
        'Compiler with structured "did you mean" suggestions for every typo class — connector, op, param, step-id, Jinja path, picklist value.',
      accent: 'lime',
      bullets: [
        'Validate runs every keystroke (400ms debounce) on the Design tab',
        'Title-aware op suggestions: "get_ip_reputation" → "query_ip"',
        'Errors are structured data, not prose — every diagnostic has a code, line/col, and fix hint'
      ],
      primary: { label: 'Open editor', href: '/' },
      tools: [{ name: 'validate_yaml' }, { name: 'compile_yaml' }]
    },
    {
      code: 'FSR',
      title: 'Check the live FSR',
      blurb:
        'See which connectors are configured, healthcheck a single config, list picklists, discover tags before filtering by them.',
      accent: 'cyan',
      primary: { label: 'Health view', href: '/run' },
      tools: [
        { name: 'list_configured_connectors' },
        { name: 'healthcheck_connector' },
        { name: 'list_tags' },
        { name: 'list_picklists' }
      ]
    }
  ];

  // Roadmap cards — what's planned, with honest status. No emojis.
  const upcoming: Upcoming[] = [
    {
      code: 'L2',
      title: 'Static-resolve gate',
      body:
        'Catch unresolved picklists, missing connector installs, and dangling Jinja variable paths before push — not at runtime.',
      notes: [
        'resolve_yaml MCP tool wraps the checks',
        'Variable-reachability ruleset cross-checks {{ vars.steps.X.Y }} against observed step output shapes',
        'Highest-ROI single check we don\'t have today'
      ],
      eta: 'Next'
    },
    {
      code: 'L3',
      title: 'Dry-run a playbook',
      body:
        'Step-by-step execution against the live FSR with rendered context piped from one step to the next, so failures surface in the editor instead of in production.',
      notes: [
        'Per-step-type handlers (connector, set_variable, decision, manual_input, …)',
        'Powers the dry_run_playbook MCP tool',
        'Stepper design captured in TODO.md item I10'
      ],
      eta: 'In design'
    },
    {
      code: 'L5',
      title: 'Outcome assertions',
      body:
        'Declarative success checks — record exists, field equals, count greater than N — so a playbook is "done" only when it produced the asked-for outcome.',
      notes: [
        'assert_playbook_outcome MCP tool',
        'Closes the loop: the agent knows when to stop iterating',
        'Foundation for the LLM evaluation harness'
      ]
    },
    {
      code: 'EVL',
      title: 'LLM evaluation harness',
      body:
        'Run the same authoring tasks across Claude, GPT, and a local model. Score on compile, resolve, dry-run, and gold-fixture match. Turn "LLM-agnostic" from a claim into a measurement.',
      notes: [
        'python/eval/harness.py runs three storyboards × three models',
        'Output: a per-model rubric you can show to stakeholders'
      ]
    },
    {
      code: 'DGN',
      title: 'Diagnose a failed run automatically',
      body:
        'Pull the failed execution, render every step\'s args against the captured context, and surface the first shape or value mismatch with a suggested fix.',
      notes: [
        'diagnose_yaml_against_pb_execution MCP tool',
        'Closes the failure-recovery loop the killer demo depends on'
      ]
    },
    {
      code: 'REC+',
      title: 'Recipe expansion',
      body:
        'Beyond ingestion: enrichment, triage, containment, approval-gated actions, parent/child orchestration, scheduled scans. Patterns mined from the 1,664-playbook corpus.',
      notes: [
        'Step-sequence pattern mining feeds the generator',
        'Each archetype gets its own ruleset layer'
      ]
    },
    {
      code: 'PRMT',
      title: 'Externalized system prompt',
      body:
        'Move the implicit web-app prompt to python/agent/system_prompt.md. Document the contract: tools, success-ladder discipline, when to ask the user, what counts as done.',
      notes: ['Required for any LLM to drive the product consistently']
    },
    {
      code: 'XPRT',
      title: 'Demo replay + transcript capture',
      body:
        'Persist every chat turn and tool call per session as a replayable artifact. Plus a pre-demo reset script that returns the dev FSR to known state.',
      notes: ['Token usage logging already exists; extend to full turns']
    }
  ];

  // Tailwind needs literal class names to JIT them.
  const accentClasses: Record<
    string,
    { ring: string; text: string; bg: string; border: string; dot: string }
  > = {
    emerald: { ring: 'ring-emerald-500/20', text: 'text-emerald-300', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', dot: 'bg-emerald-500/60' },
    sky: { ring: 'ring-sky-500/20', text: 'text-sky-300', bg: 'bg-sky-500/10', border: 'border-sky-500/30', dot: 'bg-sky-500/60' },
    violet: { ring: 'ring-violet-500/20', text: 'text-violet-300', bg: 'bg-violet-500/10', border: 'border-violet-500/30', dot: 'bg-violet-500/60' },
    indigo: { ring: 'ring-indigo-500/20', text: 'text-indigo-300', bg: 'bg-indigo-500/10', border: 'border-indigo-500/30', dot: 'bg-indigo-500/60' },
    rose: { ring: 'ring-rose-500/20', text: 'text-rose-300', bg: 'bg-rose-500/10', border: 'border-rose-500/30', dot: 'bg-rose-500/60' },
    amber: { ring: 'ring-amber-500/20', text: 'text-amber-300', bg: 'bg-amber-500/10', border: 'border-amber-500/30', dot: 'bg-amber-500/60' },
    teal: { ring: 'ring-teal-500/20', text: 'text-teal-300', bg: 'bg-teal-500/10', border: 'border-teal-500/30', dot: 'bg-teal-500/60' },
    lime: { ring: 'ring-lime-500/20', text: 'text-lime-300', bg: 'bg-lime-500/10', border: 'border-lime-500/30', dot: 'bg-lime-500/60' },
    cyan: { ring: 'ring-cyan-500/20', text: 'text-cyan-300', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', dot: 'bg-cyan-500/60' }
  };

  const headlineStats = [
    { v: '20+', l: 'MCP tools' },
    { v: '714', l: 'connectors' },
    { v: '6,773', l: 'operations' },
    { v: '1,664', l: 'workflows mined' },
    { v: '6,927', l: 'API products' },
    { v: '207,419', l: 'API examples' }
  ];
</script>

<div class="h-full overflow-auto bg-zinc-950 text-zinc-100">
  <div class="mx-auto max-w-6xl px-8 py-12">
    <header class="mb-12">
      <p class="mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-500">
        Capabilities
      </p>
      <h1 class="text-4xl font-semibold leading-tight text-zinc-50">
        Author, run, and triage FortiSOAR playbooks
        <span class="text-zinc-400">— without the Designer.</span>
      </h1>
      <p class="mt-4 max-w-3xl text-lg text-zinc-400">
        Pick the entry point that matches what you are trying to do. Each card lands you on a working tool, sample, or chat prompt.
      </p>

      <div class="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {#each headlineStats as s}
          <div class="rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
            <div class="text-2xl font-semibold tabular-nums text-zinc-100">{s.v}</div>
            <div class="text-xs uppercase tracking-wide text-zinc-500">{s.l}</div>
          </div>
        {/each}
      </div>
    </header>

    <div class="mb-5 flex items-baseline justify-between">
      <h2 class="text-xs font-semibold uppercase tracking-widest text-zinc-500">Available now</h2>
      <a href="/docs" class="text-xs text-zinc-500 hover:text-zinc-300">Full tool reference →</a>
    </div>

    <div class="grid gap-4 md:grid-cols-2">
      {#each cards as c}
        {@const a = accentClasses[c.accent]}
        <article
          class="group relative flex flex-col overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/40 p-6 transition hover:border-zinc-700 hover:bg-zinc-900/60"
        >
          <div class="mb-3 flex items-center gap-3">
            <div
              class="flex h-8 min-w-12 items-center justify-center rounded-md border {a.border} {a.bg} px-2 font-mono text-xs font-semibold tracking-wider {a.text}"
            >
              {c.code}
            </div>
            <h3 class="text-lg font-semibold text-zinc-100">{c.title}</h3>
          </div>

          <p class="mb-4 text-sm leading-relaxed text-zinc-400">{c.blurb}</p>

          {#if c.bullets}
            <ul class="mb-4 space-y-1.5 text-sm text-zinc-300">
              {#each c.bullets as b}
                <li class="flex gap-2">
                  <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full {a.dot}"></span>
                  <span>{b}</span>
                </li>
              {/each}
            </ul>
          {/if}

          {#if c.tools && c.tools.length}
            <div class="mb-4 flex flex-wrap gap-1.5">
              {#each c.tools as t}
                <span
                  class="inline-flex items-center rounded border border-zinc-800 bg-zinc-950/60 px-2 py-0.5 font-mono text-xs text-zinc-400"
                >
                  {t.name}
                </span>
              {/each}
            </div>
          {/if}

          <div class="mt-auto flex flex-wrap items-center gap-3 pt-2">
            {#if c.primary}
              <a
                href={c.primary.href}
                class="inline-flex items-center gap-1 rounded-md border {a.border} {a.bg} px-3 py-1.5 text-sm font-medium {a.text} transition hover:brightness-125"
              >
                {c.primary.label}
                <span class="transition group-hover:translate-x-0.5">→</span>
              </a>
            {/if}
            {#if c.secondary}
              <a
                href={c.secondary.href}
                class="text-sm text-zinc-500 hover:text-zinc-300"
              >
                {c.secondary.label}
              </a>
            {/if}
          </div>
        </article>
      {/each}
    </div>

    <!-- Roadmap / coming soon -->
    <section class="mt-16">
      <div class="mb-5 flex items-baseline justify-between">
        <h2 class="text-xs font-semibold uppercase tracking-widest text-zinc-500">
          On the roadmap
        </h2>
        <span class="text-xs text-zinc-600">
          Tracked in TODO.md and CHAT_APP_PLAN.md
        </span>
      </div>
      <p class="mb-5 max-w-3xl text-sm text-zinc-400">
        The success ladder is the spine of the next phase: a playbook that compiles is not a playbook that works. Each item below closes one of the silent-failure surfaces that today only surface at runtime.
      </p>

      <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {#each upcoming as u}
          <article
            class="relative flex flex-col rounded-md border border-dashed border-zinc-800 bg-zinc-950/40 p-5"
          >
            <div class="mb-3 flex items-center justify-between gap-2">
              <span
                class="rounded border border-zinc-800 bg-zinc-900 px-2 py-0.5 font-mono text-[11px] font-semibold tracking-wider text-zinc-400"
              >
                {u.code}
              </span>
              <span class="text-[10px] uppercase tracking-widest text-zinc-600">
                {u.eta ?? 'Planned'}
              </span>
            </div>
            <h4 class="mb-1.5 text-sm font-semibold text-zinc-200">{u.title}</h4>
            <p class="mb-3 text-sm leading-relaxed text-zinc-400">{u.body}</p>
            {#if u.notes}
              <ul class="space-y-1 text-xs text-zinc-500">
                {#each u.notes as n}
                  <li class="flex gap-2">
                    <span class="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-zinc-700"></span>
                    <span>{n}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </article>
        {/each}
      </div>
    </section>

    <!-- Demo storyboards -->
    <section class="mt-16">
      <div class="mb-5 flex items-baseline justify-between">
        <h2 class="text-xs font-semibold uppercase tracking-widest text-zinc-500">Demo storyboards</h2>
        <span class="text-xs text-zinc-600">~3–5 min each</span>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        {#each [
          { tag: 'A', title: 'Authoring from a vague ask', body: 'Connector discovery → op schema → YAML → validate → compile → push → run. Whole loop, no CLI hand-off.' },
          { tag: 'B', title: 'Iterating on a broken draft', body: 'Paste typo\'d YAML; the agent uses validator + render_jinja against a past run to fix without guessing.' },
          { tag: 'C', title: 'Triage and fix a broken playbook', body: 'list_recent_failed_runs → get_run_env → spot the shape mismatch → pull / edit / push / re-run. Not possible from the FSR Designer.' },
          { tag: 'D', title: 'Reverse-engineer an existing playbook', body: 'pull → narrate steps in plain English → cross-reference idioms via find_jinja_pattern.' }
        ] as d}
          <div class="flex gap-4 rounded-md border border-zinc-800 bg-zinc-900/40 p-4">
            <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-zinc-700 bg-zinc-950 font-mono text-sm font-semibold text-zinc-300">
              {d.tag}
            </div>
            <div>
              <h4 class="font-medium text-zinc-100">{d.title}</h4>
              <p class="mt-1 text-sm text-zinc-400">{d.body}</p>
            </div>
          </div>
        {/each}
      </div>
      <p class="mt-4 text-sm text-zinc-500">
        Pre-talk smoke:
        <code class="rounded bg-zinc-900 px-1.5 py-0.5 font-mono text-xs text-zinc-300">fsrpb e2e all</code>
        runs all 11 demo fixtures end-to-end.
      </p>
    </section>

    <footer class="mt-16 border-t border-zinc-800 pt-6 text-xs text-zinc-600">
      Sources:
      <a href="/docs" class="hover:text-zinc-400">Docs</a> ·
      <code class="rounded bg-zinc-900 px-1 text-zinc-400">CAPABILITIES.md</code> ·
      <code class="rounded bg-zinc-900 px-1 text-zinc-400">CHAT_APP_PLAN.md</code> ·
      <code class="rounded bg-zinc-900 px-1 text-zinc-400">TODO.md</code> ·
      <code class="rounded bg-zinc-900 px-1 text-zinc-400">DEMO.md</code>
    </footer>
  </div>
</div>
