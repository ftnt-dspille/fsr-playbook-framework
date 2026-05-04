<script lang="ts">
  type Section = { id: string; title: string };

  const sections: Section[] = [
    { id: 'overview', title: 'What this is' },
    { id: 'architecture', title: 'Architecture' },
    { id: 'design-tab', title: 'Design tab — editor + chat' },
    { id: 'autocomplete', title: 'Autocomplete' },
    { id: 'examples', title: 'Examples menu' },
    { id: 'validate-compile', title: 'Validate vs Compile' },
    { id: 'push-run', title: 'Push & Run — talking to FortiSOAR' },
    { id: 'run-tab', title: 'Run tab — logs and env viewer' },
    { id: 'chat-internals', title: 'How the chat knows FSR' },
    { id: 'tools', title: 'The 14 tools' },
    { id: 'tokens', title: 'Tokens and cost' },
    { id: 'health', title: 'The status pills' },
    { id: 'env', title: 'Configuration (.env)' },
    { id: 'tests', title: 'Running the tests' },
    { id: 'roadmap', title: 'Roadmap' }
  ];
</script>

<div class="grid h-full grid-cols-[220px_1fr]">
  <!-- ToC -->
  <nav class="overflow-auto border-r border-zinc-800 p-4 text-sm">
    <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Contents</h2>
    <ul class="space-y-1">
      {#each sections as s}
        <li>
          <a href="#{s.id}" class="text-zinc-400 hover:text-zinc-100">{s.title}</a>
        </li>
      {/each}
    </ul>
  </nav>

  <!-- Body -->
  <article class="min-h-0 overflow-auto px-8 py-6 text-zinc-200">
    <div class="mx-auto max-w-3xl space-y-10 text-[15px] leading-relaxed [&_h2]:mt-2 [&_p]:my-1 [&_li]:my-0.5 [&_code]:rounded [&_code]:bg-zinc-800/60 [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[13px] [&_code]:text-zinc-100">
      <header>
        <h1 class="text-3xl font-semibold text-zinc-100">FSR Playbook Studio — Docs</h1>
        <p class="mt-2 text-zinc-400">
          Browser app for authoring, validating, pushing, and running FortiSOAR
          playbooks. Combines a Monaco YAML editor with an LLM chat that drives
          the same compiler and reference store you'd use from the command line.
        </p>
      </header>

      <section id="overview">
        <h2 class="text-xl font-semibold">What this is</h2>
        <p class="mt-2">
          A single-user dev tool that bundles four things into one window:
        </p>
        <ol class="mt-2 list-decimal space-y-1 pl-6">
          <li>A YAML editor with live diagnostics from the FortiSOAR-aware compiler.</li>
          <li>An Anthropic chat that can drive 14 read-only tools to look up connectors, operations, step types, and Jinja idioms — and write the YAML for you.</li>
          <li>One-click <span class="font-semibold">Push</span> and <span class="font-semibold">Push &amp; Run</span> against a live FortiSOAR appliance.</li>
          <li>A run viewer that streams the CLI's output and rebuilds the runtime <code>vars</code> tree.</li>
        </ol>
        <p class="mt-2 text-zinc-400">
          Everything sits on top of the existing <code>fsrpb</code> CLI and
          <code>store/fsr_reference.db</code> — there's no FortiSOAR knowledge
          baked into the web app itself.
        </p>
      </section>

      <section id="architecture">
        <h2 class="text-xl font-semibold">Architecture</h2>
        <pre class="mt-3 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-tight text-zinc-300">{`┌──────────────────────────────────────────────────────────┐
│  SvelteKit (Svelte 5 + Tailwind + Monaco)                │
│  • Design / Run / Browse / History / Docs tabs           │
│  • Streams SSE for chat and run logs                     │
└─────────────────────────────┬────────────────────────────┘
                              │ /api/*
┌─────────────────────────────▼────────────────────────────┐
│  FastAPI                                                 │
│  • /api/health   /api/yaml/*   /api/playbook/*           │
│  • /api/chat (SSE)   /api/ref/*   /api/examples/*        │
│  imports → ../python/  (compiler, mcp_server, _env)      │
└─────────────┬──────────────────────┬─────────────────────┘
              │                      │
        in-process              subprocess
              │                      │
   ┌──────────▼──────────┐  ┌────────▼────────────────────┐
   │  python/compiler/    │  │  python -m cli push|run    │
   │  python/mcp_server   │  │  (the 'fsrpb' CLI)         │
   │  python/probes/_env  │  │  → live FortiSOAR over     │
   │  store/*.db          │  │    HTTPS using .env creds  │
   └──────────────────────┘  └─────────────────────────────┘`}</pre>
        <p class="mt-3 text-zinc-400">
          The web layer never re-implements anything. Authoring tools import
          the Python modules directly; Push/Run subprocess the existing CLI so
          the same battle-tested code paths handle real FortiSOAR I/O.
        </p>
      </section>

      <section id="design-tab">
        <h2 class="text-xl font-semibold">Design tab — editor + chat</h2>
        <p class="mt-2">
          The Design tab is split: Monaco YAML editor on the left, chat on the
          right, and an output drawer along the bottom.
        </p>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li><span class="font-semibold">Editor</span> — every keystroke triggers a 400ms debounced <code>POST /api/yaml/validate</code>. Errors and warnings render as Monaco red/yellow squigglies and as a list in the bottom drawer.</li>
          <li><span class="font-semibold">Chat</span> — sends to <code>POST /api/chat</code> as Server-Sent Events. The assistant streams text + tool-call cards. If its response ends with a fenced <code>```yaml</code> block, the editor buffer is replaced.</li>
          <li><span class="font-semibold">Output drawer</span> — four tabs: Diagnostics, Compile output, Push log, Run log. The right one auto-opens when you click the matching button.</li>
        </ul>
      </section>

      <section id="autocomplete">
        <h2 class="text-xl font-semibold">Autocomplete</h2>
        <p class="mt-2">
          Monaco completion provider, scoped by the YAML key:
        </p>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li><code>type:</code> — all 15 short step types. Picking one inserts a snippet scaffold (<code>arguments:</code>, required keys, tab-stops). Press Tab to jump between fields.</li>
          <li><code>connector:</code> — fuzzy-searches all 714 connectors from <code>store/fsr_reference.db</code>.</li>
          <li><code>operation:</code> — looks at the <code>connector:</code> line above and lists only that connector's ops.</li>
        </ul>
        <p class="mt-2 text-zinc-400">
          Backed by <code>/api/ref/step-types</code>, <code>/api/ref/connectors</code>,
          and <code>/api/ref/connectors/&lt;name&gt;/operations</code>.
        </p>
      </section>

      <section id="examples">
        <h2 class="text-xl font-semibold">Examples menu</h2>
        <p class="mt-2">
          The <span class="font-semibold">Examples ▾</span> dropdown lists every
          fixture in <code>FSRPlaybookYaml/examples/*.yaml</code>. Clicking one
          loads it into the editor — useful for "I want something to play with"
          and for the demo storyboard. <code>.test.yaml</code> sidecars are excluded.
        </p>
      </section>

      <section id="validate-compile">
        <h2 class="text-xl font-semibold">Validate vs Compile</h2>
        <p class="mt-2">
          Both run locally; neither talks to FortiSOAR.
        </p>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li>
            <span class="font-semibold">Validate</span> (auto, 400ms after each keystroke):
            parser → resolver → arg validator → graph validator. Returns markers with
            line numbers, error codes, and "did you mean" suggestions.
          </li>
          <li>
            <span class="font-semibold">Compile</span> (button): same pipeline,
            but on success also emits the FortiSOAR <code>WorkflowCollection</code>
            JSON dict. The dict is what would get POSTed to the appliance.
          </li>
        </ul>
        <p class="mt-2 text-zinc-400">
          A "valid" buffer can still have warnings — they don't block compile.
          A "compiled" buffer is ready to push.
        </p>
      </section>

      <section id="push-run">
        <h2 class="text-xl font-semibold">Push &amp; Run — talking to FortiSOAR</h2>
        <p class="mt-2">
          Both buttons subprocess the existing <code>fsrpb</code> CLI. That CLI
          handles all the FortiSOAR-specific quirks (idempotent push, soft-delete
          recovery, --follow polling).
        </p>
        <h3 class="mt-3 font-semibold">Push</h3>
        <ol class="mt-1 list-decimal space-y-1 pl-6">
          <li>Backend writes the editor YAML to a tmp file.</li>
          <li>Runs <code>python -m cli push &lt;tmp&gt; --mode replace</code>.</li>
          <li>The CLI tries <code>PUT /api/3/workflow_collections/&lt;uuid&gt;</code> first; on 404 it falls back to <code>POST</code>; on 409 (soft-deleted record holds the UUID) it hard-purges and re-POSTs. Including child-workflow purge.</li>
          <li>Result and full stdout/stderr land in the bottom drawer's "Push log" tab.</li>
        </ol>
        <h3 class="mt-3 font-semibold">Run (= Push &amp; Run)</h3>
        <ol class="mt-1 list-decimal space-y-1 pl-6">
          <li>Pushes first (same path as above).</li>
          <li>Extracts <code>collection:</code> and the first <code>playbooks[0].name</code> from the YAML.</li>
          <li>Runs <code>python -m cli run-playbook "&lt;coll&gt;:&lt;name&gt;" --follow</code>.</li>
          <li>The CLI POSTs to <code>/api/triggers/1/notrigger/&lt;wf_uuid&gt;</code> (or <code>/action/&lt;wf_uuid&gt;</code> for record-context triggers), then polls <code>/api/wf/api/workflows/?task_id=…</code> until terminal status.</li>
          <li>Backend streams stdout line-by-line as SSE. The frontend parses out the <code>task_id</code> UUID for use by the Run tab.</li>
        </ol>
      </section>

      <section id="run-tab">
        <h2 class="text-xl font-semibold">Run tab — logs and env viewer</h2>
        <p class="mt-2">
          Mirrors the bottom-drawer Run log so you have a full-window view, plus
          a <span class="font-semibold">Run env</span> rail that pulls the rebuilt
          Jinja context from any past run.
        </p>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li>After a Run finishes with a parsed <code>task_id</code>, the env rail auto-loads.</li>
          <li>Otherwise paste any workflow PK or task UUID; the backend subprocesses <code>python -m cli env &lt;pk&gt;</code> which calls <code>GET /api/wf/api/workflows/&lt;pk&gt;/?step_detail=true</code> and rebuilds <code>{`{ vars: { …env, steps: { Step_Name: result } } }`}</code>.</li>
          <li>The <code>Step_Name</code> form is the canonical Jinja key — display name with spaces→underscores. Hard rule #1 in the system prompt.</li>
        </ul>
      </section>

      <section id="chat-internals">
        <h2 class="text-xl font-semibold">How the chat knows FSR</h2>
        <p class="mt-2">
          No FortiSOAR knowledge lives in the model itself. Every turn assembles:
        </p>
        <ol class="mt-2 list-decimal space-y-1 pl-6">
          <li><span class="font-semibold">System prompt</span> (~720 tokens) — role, the 10 hard rules, tool-use playbook. Same every turn; cached.</li>
          <li><span class="font-semibold">Tools schema</span> (~935 tokens, 14 tools) — auto-generated JSON Schema from <code>mcp_server.py</code> docstrings + Python type hints. Cached.</li>
          <li><span class="font-semibold">Editor primer</span> — the current YAML wrapped in a fenced block plus an "Acknowledged." assistant message. Refreshes every turn.</li>
          <li><span class="font-semibold">Conversation history</span> — your prior messages + assistant turns + inline tool calls and results.</li>
          <li><span class="font-semibold">Your latest message</span>.</li>
        </ol>
        <p class="mt-2 text-zinc-400">
          The model emits <code>tool_use</code> blocks; the backend dispatches
          them to in-process Python functions and feeds the results back as
          <code>tool_result</code> blocks. Loop until the model stops asking
          for tools. Then if it ended with a <code>```yaml</code> fence, the
          editor buffer swaps.
        </p>
      </section>

      <section id="tools">
        <h2 class="text-xl font-semibold">The 14 tools</h2>
        <p class="mt-2">
          Read-only by design. <code>run_op</code>, <code>push</code>,
          and <code>run_playbook</code> are <span class="font-semibold">not</span>
          available to the chat — push and run are explicit user actions.
        </p>
        <table class="mt-3 w-full text-sm">
          <thead class="border-b border-zinc-700 text-left text-zinc-400">
            <tr><th class="py-1 pr-4">Tool</th><th>What it does</th></tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            <tr><td class="py-1 pr-4 font-mono">find_connector</td><td>fuzzy search 714 connectors</td></tr>
            <tr><td class="py-1 pr-4 font-mono">find_operation</td><td>list/search ops on a connector</td></tr>
            <tr><td class="py-1 pr-4 font-mono">get_op_schema</td><td>full param schema + observed output shape</td></tr>
            <tr><td class="py-1 pr-4 font-mono">get_step_type</td><td>step-type schema by short name</td></tr>
            <tr><td class="py-1 pr-4 font-mono">find_jinja_filter</td><td>filter catalog ranked by corpus usage</td></tr>
            <tr><td class="py-1 pr-4 font-mono">find_jinja_pattern</td><td>search <code>{`{% set %}`}</code>, <code>{`{% for %}`}</code>, etc. patterns</td></tr>
            <tr><td class="py-1 pr-4 font-mono">get_filter_examples</td><td>real expressions using a filter</td></tr>
            <tr><td class="py-1 pr-4 font-mono">search_playbooks</td><td>FTS over playbook corpus</td></tr>
            <tr><td class="py-1 pr-4 font-mono">validate_yaml</td><td>same compiler the editor uses</td></tr>
            <tr><td class="py-1 pr-4 font-mono">compile_yaml</td><td>YAML → FSR JSON dict</td></tr>
            <tr><td class="py-1 pr-4 font-mono">list_configured_connectors</td><td>configured + active set on the appliance</td></tr>
            <tr><td class="py-1 pr-4 font-mono">list_picklists</td><td>known picklists</td></tr>
            <tr><td class="py-1 pr-4 font-mono">picklist_for_field</td><td>picklist for (module, field) pair</td></tr>
            <tr><td class="py-1 pr-4 font-mono">resolve_picklist_value</td><td>friendly value → IRI</td></tr>
          </tbody>
        </table>
      </section>

      <section id="tokens">
        <h2 class="text-xl font-semibold">Tokens and cost</h2>
        <p class="mt-2">
          Default model: Claude Sonnet 4.5. ($3/M input, $15/M output, $0.30/M
          cached read.)
        </p>
        <table class="mt-3 w-full text-sm">
          <thead class="border-b border-zinc-700 text-left text-zinc-400">
            <tr><th class="py-1 pr-4">Turn</th><th class="pr-4">Input</th><th class="pr-4">Output</th><th>Cost</th></tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            <tr><td class="py-1 pr-4">Quick question, no tool calls</td><td class="pr-4">~3k</td><td class="pr-4">~300</td><td>~$0.014</td></tr>
            <tr><td class="py-1 pr-4">Typical authoring (4 tool calls)</td><td class="pr-4">~7k</td><td class="pr-4">~1k</td><td>~$0.036</td></tr>
            <tr><td class="py-1 pr-4">Heavy turn (8 calls, big YAML)</td><td class="pr-4">~15k</td><td class="pr-4">~2k</td><td>~$0.075</td></tr>
          </tbody>
        </table>
        <p class="mt-3">
          Sessions: a 15–25 turn authoring run is roughly <span class="font-semibold">$0.50–$0.90</span>;
          a 10-turn live demo is about <span class="font-semibold">$0.30</span>.
          Anthropic's prompt cache makes the system+tools prefix essentially free
          after the first turn within 5 minutes.
        </p>
        <p class="mt-2 text-zinc-400">
          Watch real spend at <a class="text-blue-400 hover:underline" href="https://console.anthropic.com/dashboard" target="_blank" rel="noreferrer">console.anthropic.com/dashboard</a>.
        </p>
      </section>

      <section id="health">
        <h2 class="text-xl font-semibold">The status pills</h2>
        <p class="mt-2">
          Three pills in the top-right, refreshed every 8 seconds:
        </p>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li><span class="font-semibold">backend</span> — green if FastAPI is up. Click to force-refresh.</li>
          <li><span class="font-semibold">FSR</span> — green if a live <code>GET /api/3/picklists/?$limit=1</code> returns 200. Hover to see the base URL or the error.</li>
          <li><span class="font-semibold">LLM</span> — green if <code>ANTHROPIC_API_KEY</code> is set in the backend's environment.</li>
        </ul>
        <p class="mt-2 text-zinc-400">
          A red FSR pill means Push/Run will fail — check the <code>.env</code>
          file in the FSRPlaybookYaml repo (one level up from <code>web/</code>).
        </p>
      </section>

      <section id="env">
        <h2 class="text-xl font-semibold">Configuration (.env)</h2>
        <p class="mt-2">
          Two env vars matter:
        </p>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li>
            <code>ANTHROPIC_API_KEY</code> — set in the shell where you run
            <code>uvicorn</code>. Without it, <code>/api/chat</code> returns an error event.
          </li>
          <li>
            <code>.env</code> in the FSRPlaybookYaml repo root — the
            <code>_env.py</code> loader reads <code>FSR_BASE_URL</code>,
            <code>FSR_USERNAME</code> + <code>FSR_PASSWORD</code> (or
            <code>FSR_API_KEY</code>), and <code>FSR_ALLOW_E2E=true</code>.
          </li>
        </ul>
        <pre class="mt-3 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-tight text-zinc-300">{`# FSRPlaybookYaml/.env
FSR_BASE_URL=https://10.99.249.205
FSR_USERNAME=csadmin
FSR_PASSWORD=fortinet
FSR_ALLOW_E2E=true`}</pre>
      </section>

      <section id="tests">
        <h2 class="text-xl font-semibold">Running the tests</h2>
        <pre class="mt-3 overflow-auto rounded border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-tight text-zinc-300">{`# Web backend (20 tests)
cd web && python3 -m pytest tests/ -q

# Web frontend (14 tests)
cd web/frontend && pnpm test

# FSRPlaybookYaml core (52 tests)
cd FSRPlaybookYaml && python3 -m pytest python/tests/ -q`}</pre>
        <p class="mt-2 text-zinc-400">
          The web backend tests use <code>FastAPI.TestClient</code> with
          monkeypatched subprocess for Push/Run paths. The frontend tests use
          Vitest + Testing Library; Monaco is mocked via a stub at
          <code>src/lib/__mocks__/monaco-editor.ts</code>.
        </p>
      </section>

      <section id="roadmap">
        <h2 class="text-xl font-semibold">Roadmap</h2>
        <ul class="mt-2 list-disc space-y-1 pl-6">
          <li><span class="font-semibold">Phase 4</span> — Browse tab over the reference store; visual node-tree designer (Svelte Flow) with two-way YAML sync; cross-links from chat tool calls into Browse.</li>
          <li><span class="font-semibold">Phase 5</span> — chat history persistence + OpenAI provider via the <code>LLMProvider</code> abstraction.</li>
          <li><span class="font-semibold">Phase 6</span> — hosting prep: shared-secret auth, Dockerfile, externalized creds.</li>
          <li><span class="font-semibold">TS port of the compiler</span> — so Monaco can validate/compile in a Web Worker and the round-trip drops to the keystroke.</li>
        </ul>
      </section>

      <footer class="mt-12 border-t border-zinc-800 pt-4 text-xs text-zinc-500">
        Source: <code>web/PLAN.md</code>, <code>web/CHAT_APP_PLAN.md</code>,
        and the implementation under <code>web/backend</code> + <code>web/frontend</code>.
      </footer>
    </div>
  </article>
</div>
