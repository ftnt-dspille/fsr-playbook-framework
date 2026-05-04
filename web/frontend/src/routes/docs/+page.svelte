<script lang="ts">
  type Section = { id: string; title: string };

  const sections: Section[] = [
    { id: 'overview', title: 'What this is' },
    { id: 'architecture', title: 'Architecture' },
    { id: 'design-tab', title: 'Design tab' },
    { id: 'autocomplete', title: 'Autocomplete' },
    { id: 'examples', title: 'Examples menu' },
    { id: 'validate-compile', title: 'Validate vs Compile' },
    { id: 'push-run', title: 'Push & Run' },
    { id: 'run-tab', title: 'Run tab' },
    { id: 'chat-internals', title: 'How the chat knows FSR' },
    { id: 'tools', title: 'The 14 tools' },
    { id: 'tokens', title: 'Tokens and cost' },
    { id: 'health', title: 'Status pills' },
    { id: 'env', title: 'Configuration' },
    { id: 'tests', title: 'Running tests' },
    { id: 'roadmap', title: 'Roadmap' }
  ];
</script>

<div class="grid h-full grid-cols-[minmax(180px,16rem)_minmax(0,1fr)]">
  <nav class="overflow-auto border-r border-zinc-800 bg-zinc-950 p-4">
    <h2 class="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Contents</h2>
    <ul class="space-y-2 text-sm">
      {#each sections as s}
        <li><a href="#{s.id}" class="text-zinc-400 hover:text-zinc-100">{s.title}</a></li>
      {/each}
    </ul>
  </nav>

  <article class="min-h-0 overflow-auto px-10 py-8">
    <div class="mx-auto max-w-3xl">
      <h1 class="text-3xl font-semibold text-zinc-100">FSR Playbook Studio — Docs</h1>
      <p class="mt-3 text-base text-zinc-400">
        Browser app for authoring, validating, pushing, and running FortiSOAR
        playbooks. A Monaco YAML editor sits next to an LLM chat that drives
        the same compiler and reference store you'd use from the command line.
      </p>

      <div class="mt-10 space-y-12 text-base leading-relaxed text-zinc-200">
        <section id="overview">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">What this is</h2>
          <p class="mb-3">A single-user dev tool that bundles four things into one window:</p>
          <ol class="list-decimal space-y-1 pl-6 text-zinc-300">
            <li>A YAML editor with live diagnostics from the FortiSOAR-aware compiler.</li>
            <li>An Anthropic chat that drives 14 read-only tools to look up connectors, operations, step types, and Jinja idioms.</li>
            <li>One-click <span class="font-semibold">Push</span> and <span class="font-semibold">Push &amp; Run</span> against a live FortiSOAR appliance.</li>
            <li>A run viewer that streams the CLI's output and rebuilds the runtime <code class="rounded bg-zinc-800 px-1 text-sm">vars</code> tree.</li>
          </ol>
          <p class="mt-3 text-zinc-400">
            Everything sits on top of the existing <code class="rounded bg-zinc-800 px-1 text-sm">fsrpb</code> CLI and <code class="rounded bg-zinc-800 px-1 text-sm">store/fsr_reference.db</code> — no FortiSOAR knowledge is baked into the web app itself.
          </p>
        </section>

        <section id="architecture">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Architecture</h2>
          <pre class="overflow-auto rounded border border-zinc-800 bg-zinc-950 p-4 font-mono text-xs leading-tight text-zinc-300">{`┌─────────────────────────────────────────────────────────┐
│  SvelteKit (Svelte 5 + Tailwind + Monaco)               │
│  Design / Run / Browse / History / Docs tabs            │
│  Streams SSE for chat and run logs                      │
└────────────────────────────┬────────────────────────────┘
                             │ /api/*
┌────────────────────────────▼────────────────────────────┐
│  FastAPI                                                │
│  /api/health  /api/yaml/*  /api/playbook/*              │
│  /api/chat (SSE)  /api/ref/*  /api/examples/*           │
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
          <p class="mt-3 text-zinc-400">
            The web layer never re-implements anything. Authoring tools import the Python modules directly; Push/Run subprocess the existing CLI.
          </p>
        </section>

        <section id="design-tab">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Design tab</h2>
          <p class="mb-3">Monaco editor on the left, chat on the right, output drawer along the bottom.</p>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li><span class="font-semibold">Editor</span> — every keystroke triggers a 400ms debounced <code class="rounded bg-zinc-800 px-1 text-sm">POST /api/yaml/validate</code>. Errors and warnings render as Monaco squigglies and in the Diagnostics drawer.</li>
            <li><span class="font-semibold">Chat</span> — streams via SSE. If the assistant's reply ends with a fenced <code class="rounded bg-zinc-800 px-1 text-sm">```yaml</code> block, the editor buffer is replaced.</li>
            <li><span class="font-semibold">Output drawer</span> — Diagnostics / Compile output / Push log / Run log. Auto-switches to the relevant tab when you click a button.</li>
          </ul>
        </section>

        <section id="autocomplete">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Autocomplete</h2>
          <p class="mb-3">Monaco completions, scoped by the YAML key:</p>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li><code class="rounded bg-zinc-800 px-1 text-sm">type:</code> — all 15 short step types. Picking one inserts a snippet scaffold; press Tab to jump between fields.</li>
            <li><code class="rounded bg-zinc-800 px-1 text-sm">connector:</code> — fuzzy-searches all 714 connectors from the reference DB.</li>
            <li><code class="rounded bg-zinc-800 px-1 text-sm">operation:</code> — looks at the <code class="rounded bg-zinc-800 px-1 text-sm">connector:</code> line above and lists only that connector's ops.</li>
          </ul>
        </section>

        <section id="examples">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Examples menu</h2>
          <p>
            The <span class="font-semibold">Examples ▾</span> dropdown lists every fixture in
            <code class="rounded bg-zinc-800 px-1 text-sm">FSRPlaybookYaml/examples/*.yaml</code>.
            Click one to load it into the editor. <code class="rounded bg-zinc-800 px-1 text-sm">.test.yaml</code> sidecars are excluded.
          </p>
        </section>

        <section id="validate-compile">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Validate vs Compile</h2>
          <p class="mb-3">Both run locally; neither talks to FortiSOAR.</p>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li><span class="font-semibold">Validate</span> (auto, 400ms after each keystroke): parser → resolver → arg validator → graph validator. Returns markers with line numbers, error codes, and "did you mean" suggestions.</li>
            <li><span class="font-semibold">Compile</span> (button): same pipeline, but on success also emits the FortiSOAR <code class="rounded bg-zinc-800 px-1 text-sm">WorkflowCollection</code> JSON — what would get POSTed to the appliance.</li>
          </ul>
        </section>

        <section id="push-run">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Push &amp; Run — talking to FortiSOAR</h2>
          <p class="mb-3">Both buttons subprocess the existing <code class="rounded bg-zinc-800 px-1 text-sm">fsrpb</code> CLI.</p>
          <h3 class="mb-2 mt-4 font-semibold text-zinc-100">Push</h3>
          <ol class="list-decimal space-y-1 pl-6 text-zinc-300">
            <li>Backend writes the editor YAML to a tmp file.</li>
            <li>Runs <code class="rounded bg-zinc-800 px-1 text-sm">python -m cli push &lt;tmp&gt; --mode replace</code>.</li>
            <li>The CLI tries <code class="rounded bg-zinc-800 px-1 text-sm">PUT /api/3/workflow_collections/&lt;uuid&gt;</code> first; on 404 it falls back to POST; on 409 it hard-purges and re-POSTs (including child workflows).</li>
            <li>Result and full stdout/stderr land in the bottom drawer's Push log.</li>
          </ol>
          <h3 class="mb-2 mt-4 font-semibold text-zinc-100">Run</h3>
          <ol class="list-decimal space-y-1 pl-6 text-zinc-300">
            <li>Pushes first.</li>
            <li>Extracts <code class="rounded bg-zinc-800 px-1 text-sm">collection:</code> and the first <code class="rounded bg-zinc-800 px-1 text-sm">playbooks[0].name</code>.</li>
            <li>Runs <code class="rounded bg-zinc-800 px-1 text-sm">python -m cli run-playbook "&lt;coll&gt;:&lt;name&gt;" --follow</code>.</li>
            <li>The CLI POSTs to <code class="rounded bg-zinc-800 px-1 text-sm">/api/triggers/1/notrigger/&lt;uuid&gt;</code> and polls until terminal status.</li>
            <li>Backend streams stdout line-by-line as SSE; the frontend parses out the <code class="rounded bg-zinc-800 px-1 text-sm">task_id</code>.</li>
          </ol>
        </section>

        <section id="run-tab">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Run tab — logs and env viewer</h2>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li>Mirrors the Run log with a full-window view.</li>
            <li>After a run finishes with a parsed <code class="rounded bg-zinc-800 px-1 text-sm">task_id</code>, the env rail auto-loads.</li>
            <li>Or paste any past PK / task UUID; backend subprocesses <code class="rounded bg-zinc-800 px-1 text-sm">python -m cli env &lt;pk&gt;</code> which calls <code class="rounded bg-zinc-800 px-1 text-sm">GET /api/wf/api/workflows/&lt;pk&gt;/?step_detail=true</code> and rebuilds the Jinja context.</li>
            <li>The <code class="rounded bg-zinc-800 px-1 text-sm">Step_Name</code> form is the canonical Jinja key — display name with spaces→underscores.</li>
          </ul>
        </section>

        <section id="chat-internals">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">How the chat knows FSR</h2>
          <p class="mb-3">No FortiSOAR knowledge lives in the model itself. Every turn assembles:</p>
          <ol class="list-decimal space-y-1 pl-6 text-zinc-300">
            <li><span class="font-semibold">System prompt</span> (~720 tokens) — role, the 10 hard rules, tool-use playbook. Cached.</li>
            <li><span class="font-semibold">Tools schema</span> (~935 tokens, 14 tools) — auto-generated JSON Schema. Cached.</li>
            <li><span class="font-semibold">Editor primer</span> — current YAML wrapped in a fenced block.</li>
            <li><span class="font-semibold">Conversation history</span>.</li>
            <li><span class="font-semibold">Your latest message</span>.</li>
          </ol>
          <p class="mt-3 text-zinc-400">
            The model emits tool-use blocks; the backend dispatches to in-process Python functions and feeds results back. Loops until the model stops requesting tools.
          </p>
        </section>

        <section id="tools">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">The 14 tools</h2>
          <p class="mb-3 text-zinc-400">
            Read-only by design. <code class="rounded bg-zinc-800 px-1 text-sm">run_op</code>, <code class="rounded bg-zinc-800 px-1 text-sm">push</code>, and <code class="rounded bg-zinc-800 px-1 text-sm">run_playbook</code> are <span class="font-semibold">not</span> available to the chat.
          </p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="border-b border-zinc-700 text-left text-zinc-400">
                <tr><th class="py-2 pr-4">Tool</th><th class="py-2">What it does</th></tr>
              </thead>
              <tbody class="divide-y divide-zinc-800 text-zinc-200">
                <tr><td class="py-1.5 pr-4 font-mono text-xs">find_connector</td><td class="py-1.5">fuzzy search 714 connectors</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">find_operation</td><td class="py-1.5">list/search ops on a connector</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">get_op_schema</td><td class="py-1.5">full param schema + observed output shape</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">get_step_type</td><td class="py-1.5">step-type schema by short name</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">find_jinja_filter</td><td class="py-1.5">filter catalog ranked by corpus usage</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">find_jinja_pattern</td><td class="py-1.5">search for / set / if patterns</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">get_filter_examples</td><td class="py-1.5">real expressions using a filter</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">search_playbooks</td><td class="py-1.5">FTS over playbook corpus</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">validate_yaml</td><td class="py-1.5">same compiler the editor uses</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">compile_yaml</td><td class="py-1.5">YAML → FSR JSON dict</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">list_configured_connectors</td><td class="py-1.5">configured + active set on the appliance</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">list_picklists</td><td class="py-1.5">known picklists</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">picklist_for_field</td><td class="py-1.5">picklist for (module, field) pair</td></tr>
                <tr><td class="py-1.5 pr-4 font-mono text-xs">resolve_picklist_value</td><td class="py-1.5">friendly value → IRI</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section id="tokens">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Tokens and cost</h2>
          <p class="mb-3">Default model: Claude Sonnet 4.5. ($3/M input, $15/M output, $0.30/M cached read.)</p>
          <table class="w-full text-sm">
            <thead class="border-b border-zinc-700 text-left text-zinc-400">
              <tr><th class="py-2 pr-4">Turn</th><th class="py-2 pr-4">Input</th><th class="py-2 pr-4">Output</th><th class="py-2">Cost</th></tr>
            </thead>
            <tbody class="divide-y divide-zinc-800 text-zinc-200">
              <tr><td class="py-1.5 pr-4">Quick question, no tool calls</td><td class="py-1.5 pr-4">~3k</td><td class="py-1.5 pr-4">~300</td><td class="py-1.5">~$0.014</td></tr>
              <tr><td class="py-1.5 pr-4">Typical (4 tool calls)</td><td class="py-1.5 pr-4">~7k</td><td class="py-1.5 pr-4">~1k</td><td class="py-1.5">~$0.036</td></tr>
              <tr><td class="py-1.5 pr-4">Heavy (8 calls, big YAML)</td><td class="py-1.5 pr-4">~15k</td><td class="py-1.5 pr-4">~2k</td><td class="py-1.5">~$0.075</td></tr>
            </tbody>
          </table>
          <p class="mt-3">15–25 turn authoring run: <span class="font-semibold">$0.50–$0.90</span>. 10-turn live demo: <span class="font-semibold">~$0.30</span>.</p>
        </section>

        <section id="health">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Status pills</h2>
          <p class="mb-3">Three pills in the top-right, refreshed every 8 seconds:</p>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li><span class="font-semibold">backend</span> — green if FastAPI is up. Click to force-refresh.</li>
            <li><span class="font-semibold">FSR</span> — green if a live <code class="rounded bg-zinc-800 px-1 text-sm">GET /api/3/picklists/?$limit=1</code> returns 200.</li>
            <li><span class="font-semibold">LLM</span> — green if <code class="rounded bg-zinc-800 px-1 text-sm">ANTHROPIC_API_KEY</code> is set.</li>
          </ul>
        </section>

        <section id="env">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Configuration</h2>
          <p class="mb-3">Two env vars matter:</p>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li><code class="rounded bg-zinc-800 px-1 text-sm">ANTHROPIC_API_KEY</code> in the shell where you run uvicorn.</li>
            <li><code class="rounded bg-zinc-800 px-1 text-sm">.env</code> in the FSRPlaybookYaml repo root.</li>
          </ul>
          <pre class="mt-3 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-4 font-mono text-xs leading-tight text-zinc-300">{`# FSRPlaybookYaml/.env
FSR_BASE_URL=https://10.99.249.205
FSR_USERNAME=csadmin
FSR_PASSWORD=fortinet
FSR_ALLOW_E2E=true`}</pre>
        </section>

        <section id="tests">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Running tests</h2>
          <pre class="overflow-auto rounded border border-zinc-800 bg-zinc-950 p-4 font-mono text-xs leading-tight text-zinc-300">{`# Web backend (20 tests)
cd web && python3 -m pytest tests/ -q

# Web frontend (14 tests)
cd web/frontend && pnpm test

# FSRPlaybookYaml core (52 tests)
cd FSRPlaybookYaml && python3 -m pytest python/tests/ -q`}</pre>
        </section>

        <section id="roadmap">
          <h2 class="mb-3 text-xl font-semibold text-zinc-100">Roadmap</h2>
          <ul class="list-disc space-y-2 pl-6 text-zinc-300">
            <li><span class="font-semibold">Phase 4</span> — Browse tab over the reference store; visual node-tree designer with two-way YAML sync.</li>
            <li><span class="font-semibold">Phase 5</span> — chat history persistence + OpenAI provider.</li>
            <li><span class="font-semibold">Phase 6</span> — hosting prep: shared-secret auth, Dockerfile, externalized creds.</li>
            <li><span class="font-semibold">TS port of the compiler</span> — Monaco gets a Web Worker so validate-on-keystroke is local.</li>
          </ul>
        </section>

        <footer class="mt-12 border-t border-zinc-800 pt-4 text-xs text-zinc-500">
          Source: <code class="rounded bg-zinc-800 px-1">web/PLAN.md</code>,
          <code class="rounded bg-zinc-800 px-1">CHAT_APP_PLAN.md</code>, and the implementation under <code class="rounded bg-zinc-800 px-1">web/backend</code> and <code class="rounded bg-zinc-800 px-1">web/frontend</code>.
        </footer>
      </div>
    </div>
  </article>
</div>
