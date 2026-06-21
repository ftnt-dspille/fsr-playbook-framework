<script lang="ts">
  import { TOOL_GROUPS, TOOL_TOTAL, accentClasses, flagBadge } from '$lib/mcpTools';

  type Section = { id: string; title: string };

  const sections: Section[] = [
    { id: 'overview', title: 'What this is' },
    { id: 'architecture', title: 'Architecture' },
    { id: 'tabs', title: 'The 5 tabs' },
    { id: 'studio', title: 'Studio tab' },
    { id: 'autocomplete', title: 'Autocomplete & samples' },
    { id: 'validate-compile', title: 'Validate / Resolve / Compile' },
    { id: 'push-run', title: 'Push & Run' },
    { id: 'debug', title: 'Debug runner' },
    { id: 'history-triage', title: 'History & triage' },
    { id: 'inventory', title: 'Inventory' },
    { id: 'chat-internals', title: 'How the chat knows FSR' },
    { id: 'tools', title: `${TOOL_TOTAL} MCP tools` },
    { id: 'tokens', title: 'Tokens and cost' },
    { id: 'health', title: 'Status bar' },
    { id: 'env', title: 'Configuration' },
    { id: 'tests', title: 'Running tests' }
  ];
</script>

<div class="grid h-full grid-cols-[minmax(180px,16rem)_minmax(0,1fr)]">
  <nav class="overflow-auto border-r border-[var(--border-soft)] bg-[var(--bg-canvas)] p-4">
    <h2 class="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--text-faint)]">Contents</h2>
    <ul class="space-y-2 text-sm">
      {#each sections as s}
        <li><a href="#{s.id}" class="text-[var(--text-muted)] hover:text-[var(--text-default)]">{s.title}</a></li>
      {/each}
      <li class="mt-3 border-t border-[var(--border-soft)] pt-3">
        <span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--text-faint)]">Tool groups</span>
      </li>
      {#each TOOL_GROUPS as g}
        <li><a href="#tools-{g.id}" class="text-[var(--text-muted)] hover:text-[var(--text-default)]">{g.title} ({g.tools.length})</a></li>
      {/each}
    </ul>
  </nav>

  <article class="min-h-0 overflow-auto px-10 py-8">
    <div class="mx-auto max-w-3xl">
      <h1 class="text-3xl font-semibold text-[var(--text-default)]">FSR Playbook Studio — Docs</h1>
      <p class="mt-3 text-base text-[var(--text-muted)]">
        Browser app for authoring, validating, debugging, pushing, and triaging FortiSOAR
        playbooks. A Monaco YAML editor sits next to an LLM chat that drives the same
        {TOOL_TOTAL}-tool MCP server you'd use from Claude Code or any other agent host.
      </p>

      <div class="mt-10 space-y-12 text-base leading-relaxed text-[var(--text-default)]">
        <section id="overview">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">What this is</h2>
          <p class="mb-3">A single-user dev tool that bundles four things into one window:</p>
          <ol class="list-decimal space-y-1 pl-6 text-[var(--text-muted)]">
            <li>A Monaco YAML editor with live diagnostics from the FortiSOAR-aware compiler.</li>
            <li>A pluggable LLM chat (Anthropic, OpenAI, LM Studio) that drives {TOOL_TOTAL} MCP tools.</li>
            <li>One-click <span class="font-semibold">Push</span> and <span class="font-semibold">Push &amp; Run</span> against a live FortiSOAR appliance, with a stateful <span class="font-semibold">Debug runner</span> for pre-push step-through.</li>
            <li>A run viewer that streams the CLI's output, rebuilds the runtime <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">vars</code> tree, and indexes failures for triage.</li>
          </ol>
          <p class="mt-3 text-[var(--text-muted)]">
            Everything sits on top of the existing <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">fsrpb</code> CLI and the <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">store/</code> reference DBs — the same code path agents use over stdio MCP.
          </p>
        </section>

        <section id="architecture">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Architecture</h2>
          <pre class="overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-4 font-mono text-xs leading-tight text-[var(--text-muted)]">{`┌─────────────────────────────────────────────────────────┐
│  SvelteKit (Svelte 5 + Tailwind + Monaco)               │
│  Studio / Browse / Inventory / History / Settings tabs  │
│  Streams SSE for chat, run logs, and debug ticks        │
└────────────────────────────┬────────────────────────────┘
                             │ /api/*
┌────────────────────────────▼────────────────────────────┐
│  FastAPI                                                │
│  /api/health  /api/yaml/*  /api/playbook/*              │
│  /api/chat (SSE)  /api/ref/*  /api/examples/*           │
│  /api/debug/*  (stateful debug-runner sessions)         │
│  imports → ../python/  (compiler, mcp_server, _env)     │
└────────────┬──────────────────────┬─────────────────────┘
             │                      │
       in-process              subprocess
             │                      │
   ┌─────────▼──────────┐  ┌────────▼────────────────────┐
   │ python/compiler/   │  │ python -m cli push|run      │
   │ python/mcp_server  │  │ → live FortiSOAR over HTTPS │
   │ python/probes/_env │  │   using .env credentials    │
   │ store/*.db         │  │                             │
   └────────────────────┘  └─────────────────────────────┘`}</pre>
          <p class="mt-3 text-[var(--text-muted)]">
            The web layer never re-implements anything. Authoring tools import the Python modules directly; Push / Run / env-fetch subprocess the existing CLI. The MCP server (<code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">python -m mcp_server</code>) exposes the same Python functions over stdio to outside agents.
          </p>
        </section>

        <section id="tabs">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">The 5 tabs</h2>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li><span class="font-semibold">Studio</span> — Monaco YAML editor + chat + the Diagnostics / Debug / Deploy drawer.</li>
            <li><span class="font-semibold">Browse</span> — playbook corpus discovery (collections, tags, FTS). Phase 4 — see roadmap.</li>
            <li><span class="font-semibold">Inventory</span> — live audit of everything the assistant knows: 714 connectors, 6,773 operations, 172 Jinja filters, picklists, 1,664 mined playbooks, 207,419 API examples.</li>
            <li><span class="font-semibold">History</span> — recent runs (live + archived), filterable by tag / user / time, with one-click <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">get_run_env</code> + render-Jinja triage.</li>
            <li><span class="font-semibold">Settings</span> — LLM provider config (Anthropic / OpenAI / LM Studio), theme, links to Capabilities + Docs.</li>
          </ul>
        </section>

        <section id="studio">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Studio tab</h2>
          <p class="mb-3">Monaco editor on the left, chat on the right, bottom drawer with three sub-tabs.</p>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li><span class="font-semibold">Editor</span> — every keystroke triggers a 400ms-debounced <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">POST /api/yaml/validate</code>. Errors and warnings render as Monaco squigglies and in the Diagnostics tab. A visual node-tree designer with two-way YAML sync lives alongside the text view.</li>
            <li><span class="font-semibold">Chat</span> — streams via SSE. If the assistant's reply ends with a fenced <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">```yaml</code> block, the editor buffer is replaced.</li>
            <li><span class="font-semibold">Drawer</span> — three sub-tabs:
              <ul class="mt-1.5 list-[circle] space-y-1 pl-6">
                <li><span class="font-semibold">Issues</span> — diagnostics from the compiler + render-path analyzer.</li>
                <li><span class="font-semibold">Debug</span> — Restart / Step / Stop the stateful debug runner.</li>
                <li><span class="font-semibold">Deploy</span> — Push log + Run log (no separate /run tab anymore).</li>
              </ul>
            </li>
          </ul>
        </section>

        <section id="autocomplete">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Autocomplete &amp; samples</h2>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li><code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">type:</code> — all 15 short step types. Picking one inserts a snippet scaffold.</li>
            <li><code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">connector:</code> — fuzzy-searches the 714 connectors from the reference DB.</li>
            <li><code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">operation:</code> — reads the <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">connector:</code> line above and offers only its ops.</li>
            <li><span class="font-semibold">Sample answers</span> — for <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">manual_input</code> steps, the Inspector's <em>Samples</em> tab lets you record what a user would enter at runtime. Values land in a <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm"># fsrpb:samples</code> comment block in the YAML and feed downstream Jinja in both the static analyzer and the debug runner — never reach the FSR push payload.</li>
            <li><span class="font-semibold">Mock results</span> — connector steps can carry a <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">mock_result:</code> sidecar that the analyzer + debug runner treat as the step's output without a live call.</li>
          </ul>
        </section>

        <section id="validate-compile">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Validate / Resolve / Compile</h2>
          <p class="mb-3">All three run locally; none talk to FortiSOAR directly (resolve checks the local picklist mirror).</p>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li><span class="font-semibold">Validate</span> (auto, 400ms after each keystroke): parser → resolver → arg validator → graph validator → render-path analyzer (C1–C10). Returns markers with line numbers, error codes, and "did you mean" suggestions.</li>
            <li><span class="font-semibold">Resolve</span>: deeper static check for unresolved picklists, missing connector installs, dangling <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">vars.steps.X.Y</code> Jinja paths, and friendly→IRI resolution.</li>
            <li><span class="font-semibold">Compile</span>: same pipeline, but on success also emits the FortiSOAR <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">WorkflowCollection</code> JSON — what would get POSTed to the appliance.</li>
          </ul>
        </section>

        <section id="push-run">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Push &amp; Run — talking to FortiSOAR</h2>
          <p class="mb-3">Both buttons subprocess the existing <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">fsrpb</code> CLI; logs stream into the Deploy drawer.</p>
          <h3 class="mb-2 mt-4 font-semibold text-[var(--text-default)]">Push</h3>
          <ol class="list-decimal space-y-1 pl-6 text-[var(--text-muted)]">
            <li>Backend writes the editor YAML to a tmp file.</li>
            <li>Runs <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">python -m cli push &lt;tmp&gt; --mode replace</code>.</li>
            <li>The CLI tries <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">PUT /api/3/workflow_collections/&lt;uuid&gt;</code> first; on 404 it falls back to POST; on 409 it hard-purges and re-POSTs (including child workflows).</li>
            <li>Soft-deleted rows still reserve the unique name — the CLI auto-renames stale collisions with a <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">__recycled_&lt;epoch&gt;</code> suffix.</li>
          </ol>
          <h3 class="mb-2 mt-4 font-semibold text-[var(--text-default)]">Run</h3>
          <ol class="list-decimal space-y-1 pl-6 text-[var(--text-muted)]">
            <li>Pushes first.</li>
            <li>Extracts <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">collection:</code> and the first <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">playbooks[0].name</code>.</li>
            <li>Runs <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">python -m cli run-playbook "&lt;coll&gt;:&lt;name&gt;" --follow</code>.</li>
            <li>The CLI POSTs to <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">/api/triggers/1/notrigger/&lt;uuid&gt;</code> and polls until terminal status.</li>
            <li>Backend streams stdout line-by-line as SSE; the frontend parses out the <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">task_id</code>.</li>
          </ol>
        </section>

        <section id="debug">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Debug runner</h2>
          <p class="mb-3">A stateful, server-side stepper exposed over <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">/api/debug/*</code> and as five MCP tools (<code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">start_debug_session</code>, <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">step_debug_session</code>, <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">continue_debug_session</code>, <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">get_debug_session</code>, <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">stop_debug_session</code>).</p>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li>Drives Studio's Debug drawer (Restart / Step / Stop) with a trace tape on the left and per-step detail on the right.</li>
            <li><code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">manual_input</code> steps consume the saved sample answers; <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">decision</code> branches use the chosen branch labels; safe connector ops run live, unsafe ones simulate with a placeholder.</li>
            <li>Each step yields rendered args, output, and Jinja-key updates to <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">vars.steps.&lt;Step_Name&gt;</code> so downstream rendering sees the same shape FSR would.</li>
          </ul>
        </section>

        <section id="history-triage">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">History &amp; triage</h2>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li>Lists recent workflow runs (default: failures only) across the live AND archived run tables — FSR purges every 30–60 min, so the archive is often the only place a failure still exists.</li>
            <li>Filter by tag, user, or time window.</li>
            <li>Click a run → backend subprocesses <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">python -m cli env &lt;pk&gt;</code> which calls <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">GET /api/wf/api/workflows/&lt;pk&gt;/?step_detail=true</code> and rebuilds the Jinja context. The <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">Step_Name</code> form is the canonical Jinja key.</li>
            <li>Authorization header is masked and step results are pre-sanitized server-side before they hit the UI.</li>
          </ul>
        </section>

        <section id="inventory">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Inventory</h2>
          <p>
            Live audit of every connector, operation, parameter, step type, Jinja filter, picklist, mined playbook, and third-party API entry in <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">store/</code>. Cross-store search returns results across all categories at once. The trust ladder shows which rows are confirmed-live + tested vs. only mined.
          </p>
        </section>

        <section id="chat-internals">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">How the chat knows FSR</h2>
          <p class="mb-3">No FortiSOAR knowledge lives in the model. Every turn assembles:</p>
          <ol class="list-decimal space-y-1 pl-6 text-[var(--text-muted)]">
            <li><span class="font-semibold">System prompt</span> — role, hard rules, tool-use playbook. Cached.</li>
            <li><span class="font-semibold">Tools schema</span> — auto-generated JSON Schema for the {TOOL_TOTAL} MCP tools. Cached.</li>
            <li><span class="font-semibold">Editor primer</span> — current YAML wrapped in a fenced block.</li>
            <li><span class="font-semibold">Conversation history</span>.</li>
            <li><span class="font-semibold">Your latest message</span>.</li>
          </ol>
          <p class="mt-3 text-[var(--text-muted)]">
            The model emits tool-use blocks; the backend dispatches to in-process Python functions and feeds results back. Loops until the model stops requesting tools. Same dispatch table is exposed over stdio MCP for outside agents (Claude Code, IDE plugins).
          </p>
        </section>

        <section id="tools">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">{TOOL_TOTAL} MCP tools</h2>
          <p class="mb-4 text-[var(--text-muted)]">
            Grouped by responsibility. The chat has access to all of them. Tools tagged
            <span class="ml-1 inline-flex items-center rounded border {flagBadge.mutating} px-1.5 py-0.5 font-mono text-[10px]">mutating</span>
            change live FSR state and are only invoked after explicit user action (Push / Run buttons, or chat confirmation flow).
          </p>

          <div class="mb-6 flex flex-wrap gap-2 text-[11px]">
            <span class="inline-flex items-center rounded border {flagBadge.safe} px-1.5 py-0.5 font-mono">safe</span>
            <span class="inline-flex items-center rounded border {flagBadge.mutating} px-1.5 py-0.5 font-mono">mutating</span>
            <span class="inline-flex items-center rounded border {flagBadge['live-fsr']} px-1.5 py-0.5 font-mono">live-fsr</span>
            <span class="inline-flex items-center rounded border {flagBadge.local} px-1.5 py-0.5 font-mono">local</span>
          </div>

          <div class="space-y-8">
            {#each TOOL_GROUPS as g}
              {@const a = accentClasses[g.accent]}
              <div id="tools-{g.id}" class="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-5">
                <div class="mb-2 flex items-baseline justify-between gap-3">
                  <h3 class="text-base font-semibold text-[var(--text-default)]">
                    <span class="mr-2 inline-flex items-center rounded border {a.border} {a.bg} px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider {a.text}">{g.id}</span>
                    {g.title}
                  </h3>
                  <span class="text-xs text-[var(--text-faint)]">{g.tools.length} tool{g.tools.length === 1 ? '' : 's'}</span>
                </div>
                <p class="mb-3 text-sm text-[var(--text-muted)]">{g.intro}</p>
                <table class="w-full text-sm">
                  <tbody class="divide-y divide-[var(--border-soft)]">
                    {#each g.tools as t}
                      <tr>
                        <td class="w-1/3 py-1.5 pr-4 align-top font-mono text-xs text-[var(--text-default)]">{t.name}</td>
                        <td class="py-1.5 align-top text-[var(--text-muted)]">
                          {t.blurb}
                          {#if t.flags?.length}
                            <span class="ml-1 inline-flex flex-wrap gap-1 align-middle">
                              {#each t.flags as f}
                                <span class="inline-flex items-center rounded border {flagBadge[f]} px-1 py-px font-mono text-[10px]">{f}</span>
                              {/each}
                            </span>
                          {/if}
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/each}
          </div>
        </section>

        <section id="tokens">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Tokens and cost</h2>
          <p class="mb-3">Default model: Claude Sonnet 4.6. ($3/M input, $15/M output, $0.30/M cached read.) The system prompt + tools schema (≈2.5k tokens for {TOOL_TOTAL} tools) are cached per session, so the per-turn cost is dominated by the editor primer + conversation history.</p>
          <table class="w-full text-sm">
            <thead class="border-b border-[var(--border)] text-left text-[var(--text-muted)]">
              <tr><th class="py-2 pr-4">Turn</th><th class="py-2 pr-4">Input</th><th class="py-2 pr-4">Output</th><th class="py-2">Cost</th></tr>
            </thead>
            <tbody class="divide-y divide-zinc-800 text-[var(--text-default)]">
              <tr><td class="py-1.5 pr-4">Quick question, no tool calls</td><td class="py-1.5 pr-4">~3k</td><td class="py-1.5 pr-4">~300</td><td class="py-1.5">~$0.014</td></tr>
              <tr><td class="py-1.5 pr-4">Typical (4 tool calls)</td><td class="py-1.5 pr-4">~7k</td><td class="py-1.5 pr-4">~1k</td><td class="py-1.5">~$0.036</td></tr>
              <tr><td class="py-1.5 pr-4">Heavy (8 calls, big YAML)</td><td class="py-1.5 pr-4">~15k</td><td class="py-1.5 pr-4">~2k</td><td class="py-1.5">~$0.075</td></tr>
            </tbody>
          </table>
          <p class="mt-3">15–25 turn authoring run: <span class="font-semibold">$0.50–$0.90</span>. 10-turn live demo: <span class="font-semibold">~$0.30</span>.</p>
        </section>

        <section id="health">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Status bar</h2>
          <p class="mb-3">Health pills live in the bottom StatusBar (VS Code style), refreshed every 8 seconds:</p>
          <ul class="list-disc space-y-2 pl-6 text-[var(--text-muted)]">
            <li><span class="font-semibold">backend</span> — green if FastAPI is up. Click to force-refresh.</li>
            <li><span class="font-semibold">FSR</span> — green if a live <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">GET /api/3/picklists/?$limit=1</code> returns 200.</li>
            <li><span class="font-semibold">LLM</span> — green if the active provider (Anthropic / OpenAI / LM Studio) responds to a ping.</li>
          </ul>
        </section>

        <section id="env">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Configuration</h2>
          <p class="mb-3">LLM provider credentials are managed in the Settings tab. FSR credentials live in <code class="rounded bg-[var(--bg-elevated)] px-1 text-sm">.env</code>:</p>
          <pre class="mt-3 overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-4 font-mono text-xs leading-tight text-[var(--text-muted)]">{`# fsr-playbook-framework/.env
FSR_BASE_URL=https://198.51.100.10
FSR_USERNAME=csadmin
FSR_PASSWORD=fortinet
FSR_ALLOW_E2E=true

# Optional — provider keys are also configurable from the Settings tab
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...`}</pre>
        </section>

        <section id="tests">
          <h2 class="mb-3 text-xl font-semibold text-[var(--text-default)]">Running tests</h2>
          <pre class="overflow-auto rounded border border-[var(--border-soft)] bg-[var(--bg-canvas)] p-4 font-mono text-xs leading-tight text-[var(--text-muted)]">{`# Core Python (compiler, MCP tools, debug runner)
python -m pytest python/tests/ -q

# Web backend
cd web && python -m pytest tests/ -q

# Web frontend
cd web/frontend && pnpm test`}</pre>
        </section>

        <footer class="mt-12 border-t border-[var(--border-soft)] pt-4 text-xs text-[var(--text-faint)]">
          Source: <code class="rounded bg-[var(--bg-elevated)] px-1">web/PLAN.md</code>,
          <code class="rounded bg-[var(--bg-elevated)] px-1">CHAT_APP_PLAN.md</code>, and the implementation under <code class="rounded bg-[var(--bg-elevated)] px-1">python/mcp_server</code>, <code class="rounded bg-[var(--bg-elevated)] px-1">web/backend</code>, and <code class="rounded bg-[var(--bg-elevated)] px-1">web/frontend</code>.
        </footer>
      </div>
    </div>
  </article>
</div>
