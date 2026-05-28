// Authoritative list of MCP tools exposed by python/mcp_server.
// Source of truth: the @mcp.tool() decorators across python/mcp_server/tools_*.py.
// Mirror this when adding/removing tools so /capabilities + /docs stay accurate.

export type Tool = {
  name: string;
  /** One-liner pulled from the tool's docstring. */
  blurb: string;
  /** Marker tags rendered as chips. */
  flags?: ('safe' | 'mutating' | 'live-fsr' | 'local' | 'llm-only')[];
};

export type ToolGroup = {
  id: string;
  title: string;
  /** Short paragraph explaining what this group of tools is for. */
  intro: string;
  accent: string; // tailwind hue for the section badge
  tools: Tool[];
};

export const TOOL_GROUPS: ToolGroup[] = [
  {
    id: 'discovery',
    title: 'Discovery',
    accent: 'sky',
    intro:
      'Look up what FortiSOAR can do. Browse the 714 connectors, drill into operations, fetch param schemas, and resolve step-type names. Read-only against the reference store + live appliance.',
    tools: [
      { name: 'find_connector', blurb: 'Fuzzy-search connectors by name, label, category, or description.', flags: ['local'] },
      { name: 'find_operation', blurb: 'List or search operations for a connector.', flags: ['local'] },
      { name: 'find_operation_example', blurb: 'Return real-world (connector, op) param snippets observed in actual playbooks.', flags: ['local'] },
      { name: 'get_op_schema', blurb: 'Return the parameter schema for a connector operation.', flags: ['local'] },
      { name: 'get_connector_source', blurb: 'Fetch the Python source code for a connector from the live FSR.', flags: ['live-fsr'] },
      { name: 'get_connector_icon', blurb: 'Return the connector’s icon_small / icon_large as base64 PNGs.', flags: ['live-fsr'] },
      { name: 'get_step_type', blurb: 'Return schema and examples for a playbook step type.', flags: ['local'] },
      { name: 'list_connector_configurations', blurb: 'List the configurations the user has set up for a connector.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'compile',
    title: 'Compile & validate',
    accent: 'lime',
    intro:
      'The compiler the editor calls on every keystroke. Parser → resolver → arg validator → graph validator → (optional) emit. All three are pure-local; nothing reaches FSR.',
    tools: [
      { name: 'validate_yaml', blurb: 'Compiler dry-run — structured diagnostics with line/col + fix hints.', flags: ['safe', 'local'] },
      { name: 'resolve_yaml', blurb: 'Whole-YAML resolvability check (picklists, install status, Jinja paths).', flags: ['safe', 'local'] },
      { name: 'compile_yaml', blurb: 'Compile YAML to FortiSOAR WorkflowCollection JSON.', flags: ['safe', 'local'] }
    ]
  },
  {
    id: 'execution',
    title: 'Execution (live FSR)',
    accent: 'rose',
    intro:
      'The only tools that mutate state. Used by the Studio’s Push / Push & Run buttons and — selectively — by the chat when it asks to probe a real op. Always gated.',
    tools: [
      { name: 'run_op', blurb: 'Execute one connector op live and return its real output.', flags: ['mutating', 'live-fsr'] },
      { name: 'push_playbook', blurb: 'Compile a YAML playbook and push it to the live FSR.', flags: ['mutating', 'live-fsr'] },
      { name: 'run_playbook', blurb: 'Trigger a deployed playbook and (optionally) poll until terminal.', flags: ['mutating', 'live-fsr'] },
      { name: 'dry_run_playbook', blurb: 'Compile + push + run + auto-cleanup — the agent’s full E2E loop in one call.', flags: ['mutating', 'live-fsr'] },
      { name: 'healthcheck_connector', blurb: 'Live-check whether a single connector configuration is reachable.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'jinja',
    title: 'Jinja',
    accent: 'amber',
    intro:
      'The 172-filter catalog plus 7,789 mined `{{…}}` / `{%…%}` expressions. Search for an idiom or render a template against the live FSR Jinja engine when you need ground truth.',
    tools: [
      { name: 'find_jinja_filter', blurb: 'Search the Jinja filter catalog by name, description, or example.', flags: ['local'] },
      { name: 'find_jinja_pattern', blurb: 'Search the corpus Jinja-block catalog by substring + kind.', flags: ['local'] },
      { name: 'find_jinja_example', blurb: 'Search 7,789 real Jinja expressions + 1,690 indexed filter usages.', flags: ['local'] },
      { name: 'get_filter_examples', blurb: 'Real-world usages of a Jinja filter from the playbook corpus.', flags: ['local'] },
      { name: 'render_jinja', blurb: 'Render a Jinja template against the live FSR Jinja engine.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'corpus',
    title: 'Corpus search',
    accent: 'indigo',
    intro:
      'Full-text + structured search across mined playbooks, step fragments, and the 207k-entry third-party API catalog. Useful for “who else solved this before me”.',
    tools: [
      { name: 'search_playbooks', blurb: 'Full-text search over playbook patterns seen in production.', flags: ['local'] },
      { name: 'search_api_examples', blurb: 'Search the api_examples_catalog (207k entries / 6,927 products).', flags: ['local'] },
      { name: 'find_step_examples', blurb: 'Search the playbook_steps corpus for real-world examples of a step type.', flags: ['local'] },
      { name: 'find_step_recipe', blurb: 'Look up prebuilt YAML step fragments by intent.', flags: ['local'] },
      { name: 'review_chat_session', blurb: 'Mine one chat session for known failure patterns; structured report.', flags: ['local'] },
      { name: 'review_recent_thumbs_down', blurb: 'Sweep recent thumbs-down sessions for failure-pattern frequencies.', flags: ['local'] }
    ]
  },
  {
    id: 'triage',
    title: 'Triage & run history',
    accent: 'teal',
    intro:
      'Pull the live state of past runs and the appliance. Powers the History tab and the chat’s “why did this break” loop — spans live and archived run tables (FSR purges every 30–60 min).',
    tools: [
      { name: 'get_run_env', blurb: 'Fetch the live Jinja context (vars + per-step results) of a past execution.', flags: ['live-fsr'] },
      { name: 'list_recent_failed_runs', blurb: 'List recent workflow runs (default: failures only) for triage.', flags: ['live-fsr'] },
      { name: 'list_playbook_runs', blurb: 'List runs of a single playbook, server-filtered by template_iri.', flags: ['live-fsr'] },
      { name: 'list_configured_connectors', blurb: 'List connectors configured AND active on the live FSR.', flags: ['live-fsr'] },
      { name: 'list_tags', blurb: 'List FortiSOAR tag names; discover tags before filtering runs by them.', flags: ['live-fsr'] },
      { name: 'verification_status', blurb: 'Look up the strongest recorded verification for a (kind, key).', flags: ['local'] },
      { name: 'test_find_record', blurb: 'Run a Find-Records preview against the configured FSR.', flags: ['live-fsr'] },
      { name: 'search_module_records', blurb: 'Live record search for the relation IRI picker.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'picklists',
    title: 'Picklists',
    accent: 'violet',
    intro:
      'Discover and resolve picklists — friendly values to IRIs and back. Wired into Studio’s field-aware autocomplete and the resolver gate.',
    tools: [
      { name: 'list_picklists', blurb: 'List every picklist listName.name known to the FSR instance.', flags: ['live-fsr'] },
      { name: 'get_picklist', blurb: 'List items of a single picklist as [{itemValue, uuid, iri, ordinal}].', flags: ['live-fsr'] },
      { name: 'picklist_for_field', blurb: 'Auto-discover the picklist behind a (module, field).', flags: ['live-fsr'] },
      { name: 'resolve_picklist_value', blurb: 'Resolve a friendly value (e.g. “High”) to a picklist IRI.', flags: ['live-fsr'] },
      { name: 'precheck_picklist_value', blurb: 'Verify a friendly value resolves before embedding it in YAML.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'analysis',
    title: 'Analysis & debug runner',
    accent: 'cyan',
    intro:
      'Stateful debug-runner that powers Studio’s Debug drawer (Restart / Step / Stop) plus the static render-path analyzer. Lets the agent walk a playbook step-by-step without ever pushing to FSR.',
    tools: [
      { name: 'analyze_playbook', blurb: 'Render-path validator: simulate the playbook + run heuristic checks (C1–C10).', flags: ['safe', 'local'] },
      { name: 'step_through_playbook', blurb: 'Pre-push stepper: walk a playbook step-by-step without pushing.', flags: ['safe', 'local'] },
      { name: 'step_test', blurb: 'Single-step probe: render one step’s args + (if safe) execute it.', flags: ['safe', 'local'] },
      { name: 'start_debug_session', blurb: 'Create a fresh stateful debug session at the playbook’s start step.', flags: ['safe', 'local'] },
      { name: 'step_debug_session', blurb: 'Advance the session by exactly one step.', flags: ['safe', 'local'] },
      { name: 'continue_debug_session', blurb: 'Run steps until breakpoint / until_step_id / max_advance.', flags: ['safe', 'local'] },
      { name: 'get_debug_session', blurb: 'Return the current status snapshot + full trace so far.', flags: ['safe', 'local'] },
      { name: 'stop_debug_session', blurb: 'Drop a debug session. Returns the final status snapshot.', flags: ['safe', 'local'] },
      { name: 'suggest_fix_for_diagnostic', blurb: 'Translate one render-path diagnostic into a structured patch proposal.', flags: ['local'] },
      { name: 'synthesize_http_step', blurb: 'Translate a catalog entry into a FortiSOAR HTTP-connector step.', flags: ['local'] },
      { name: 'precheck_connector_installed', blurb: 'Verify a connector is installed on the live FSR before authoring.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'recipe',
    title: 'Recipes & failure diagnosis',
    accent: 'emerald',
    intro:
      'Higher-order tools that combine the primitives — generate a working ingestion playbook from a connector’s info.json, or one-shot triage why a past run failed.',
    tools: [
      { name: 'generate_recipe', blurb: 'Synthesize an ingestion playbook from a connector’s info.json.', flags: ['local'] },
      { name: 'find_recipe', blurb: 'Look up persisted recipes by name / connector / kind.', flags: ['local'] },
      { name: 'assert_playbook_outcome', blurb: 'Verify a playbook produced its intended effect on the live FSR.', flags: ['live-fsr'] },
      { name: 'diagnose_yaml_against_pb_execution', blurb: 'Re-render each step’s args against a run’s actual vars env.', flags: ['live-fsr'] },
      { name: 'why_did_playbook_fail', blurb: 'One-shot triage: fetch the most recent failed run + render every Jinja block against its vars.', flags: ['live-fsr'] }
    ]
  },
  {
    id: 'verify',
    title: 'Pre-submit gates',
    accent: 'amber',
    intro:
      'Forcing functions the chat must clear before declaring a draft “done”. Diff-aware so re-runs only re-check what changed.',
    tools: [
      { name: 'verify_playbook', blurb: 'Single forcing-function pre-submit gate.', flags: ['safe', 'local'] },
      { name: 'verify_enhancement', blurb: 'Diff-aware pre-submit gate for enhance mode.', flags: ['safe', 'local'] },
      { name: 'emit_decision_step', blurb: 'Emit a canonical decision step — schema enforced so malformed shapes can’t be produced.', flags: ['local'] }
    ]
  },
  {
    id: 'catalog',
    title: 'HTTP fallback catalog',
    accent: 'slate',
    intro:
      '207,419 API entries spanning 6,927 third-party products. Lets the agent author HTTP-connector playbooks for vendors that don’t have a native FortiSOAR connector.',
    tools: [
      { name: 'find_api_product', blurb: 'Fuzzy-search the 6,927 vendor products in the API catalog.', flags: ['local'] },
      { name: 'find_api_example', blurb: 'FTS5 search over the 207k API command-catalogue entries.', flags: ['local'] },
      { name: 'find_api_fixture', blurb: 'Find HTTP request/response fixtures for a product.', flags: ['local'] },
      { name: 'propose_http_fallback', blurb: 'Decide how to invoke an intent against a vendor and emit the step.', flags: ['local'] }
    ]
  }
];

export const TOOL_TOTAL = TOOL_GROUPS.reduce((n, g) => n + g.tools.length, 0);

// Tailwind needs literal class names — JIT scans source.
export const accentClasses: Record<
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
  cyan: { ring: 'ring-cyan-500/20', text: 'text-cyan-300', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', dot: 'bg-cyan-500/60' },
  slate: { ring: 'ring-slate-500/20', text: 'text-slate-300', bg: 'bg-slate-500/10', border: 'border-slate-500/30', dot: 'bg-slate-500/60' }
};

export const flagBadge: Record<string, string> = {
  safe: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  mutating: 'border-rose-500/40 bg-rose-500/10 text-rose-300',
  'live-fsr': 'border-sky-500/30 bg-sky-500/10 text-sky-300',
  local: 'border-zinc-500/30 bg-zinc-500/10 text-zinc-300',
  'llm-only': 'border-violet-500/30 bg-violet-500/10 text-violet-300'
};
