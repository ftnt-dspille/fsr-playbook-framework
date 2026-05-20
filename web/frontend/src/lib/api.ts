export type Health = {
  ok: boolean;
  compiler: { ok: boolean; error: string | null };
  fsr: { ok: boolean | null; error?: string; base_url?: string; note?: string };
  llm: { configured: boolean; provider?: string; model?: string | null };
  secrets?: { ok: boolean; backend: string };
};

export type ProviderView = {
  name: string;
  base_url: string | null;
  model: string;
  api_key_set: boolean;
  configured: boolean;
};

export type ProvidersResponse = {
  active_provider: string;
  providers: Record<string, ProviderView>;
  secrets: { ok: boolean; backend: string };
};

export async function getProviders(): Promise<ProvidersResponse> {
  const r = await fetch('/api/llm/providers');
  if (!r.ok) throw new Error(`providers ${r.status}`);
  return r.json();
}

export async function patchProvider(
  name: string,
  patch: { base_url?: string; api_key?: string; model?: string; clear_api_key?: boolean }
): Promise<ProviderView> {
  const r = await fetch(`/api/llm/providers/${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(patch)
  });
  if (!r.ok) throw new Error(`patch ${r.status}: ${await r.text()}`);
  return r.json();
}

export type ProbeResult = { ok: boolean; error?: string; latency_ms?: number; note?: string };

export async function testProvider(
  name: string,
  body: { base_url?: string; api_key?: string }
): Promise<ProbeResult> {
  const r = await fetch(`/api/llm/providers/${encodeURIComponent(name)}/test`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`test ${r.status}`);
  return r.json();
}

export async function listProviderModels(
  name: string,
  body: { base_url?: string; api_key?: string } = {}
): Promise<{ ok: boolean; models: string[]; error?: string }> {
  const r = await fetch(`/api/llm/providers/${encodeURIComponent(name)}/models`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`models ${r.status}`);
  return r.json();
}

export async function setActiveProvider(name: string, model?: string): Promise<ProvidersResponse> {
  const r = await fetch('/api/llm/active', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name, model })
  });
  if (!r.ok) throw new Error(`active ${r.status}`);
  return r.json();
}

export type ExampleEntry = { name: string; filename: string; preview: string };

export async function listExamples(): Promise<ExampleEntry[]> {
  const r = await fetch('/api/examples');
  if (!r.ok) throw new Error(`examples ${r.status}`);
  return r.json();
}

export async function loadExample(name: string): Promise<{ name: string; text: string }> {
  const r = await fetch(`/api/examples/${encodeURIComponent(name)}`);
  if (!r.ok) throw new Error(`example ${name}: ${r.status}`);
  return r.json();
}

export async function getHealth(): Promise<Health> {
  const r = await fetch('/api/health');
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export type Marker = {
  line: number;
  col: number;
  severity: 'error' | 'warning' | 'info';
  code: string;
  message: string;
  path: string;
  suggestion: string | null;
};

/** One render-path analyzer diagnostic. Step-id-based (not line-based
 * like Marker) — these come from `analyze_playbook` and are surfaced
 * in the canvas + diagnostics drawer with per-node badges. */
export type Diagnostic = {
  kind: string;
  severity: 'error' | 'warning' | 'info';
  step_id: string;
  path: string;
  location: string;
  message: string;
  suggestion: string;
  expected?: unknown;
  actual?: unknown;
  extra?: Record<string, unknown>;
};

export type SuggestedFix = {
  ok: boolean;
  kind?: string;
  step_id?: string;
  location?: string;
  before?: unknown;
  after?: unknown;
  confidence?: 'high' | 'medium' | 'low';
  explanation?: string;
  reason?: string;
};

export type AnalyzeResult = {
  ok: boolean;
  trace?: Array<Record<string, unknown>>;
  diagnostics: Diagnostic[];
  error_count: number;
  warning_count: number;
};

/** Run the render-path validator. `executeSafeOps` opts in to live
 * FSR for picklist-drift checks (C4); leave false for pure offline. */
export async function analyzePlaybook(
  yamlText: string,
  opts: { executeSafeOps?: boolean } = {}
): Promise<AnalyzeResult> {
  const r = await callMcpTool<AnalyzeResult>('analyze_playbook', {
    yaml_text: yamlText,
    execute_safe_ops: !!opts.executeSafeOps
  });
  if (!r.ok || !r.result) {
    return { ok: false, diagnostics: [], error_count: 0, warning_count: 0 };
  }
  // Some MCP responses omit fields when empty — normalize.
  return {
    ok: r.result.ok ?? false,
    trace: r.result.trace,
    diagnostics: r.result.diagnostics ?? [],
    error_count: r.result.error_count ?? 0,
    warning_count: r.result.warning_count ?? 0
  };
}

/** Forcing-function pre-submit gate. Wraps the `verify_playbook` MCP
 * tool. Returns the same envelope the agent sees: ready_to_push +
 * required_fixes + warnings + next_actions. Each fix/warning carries a
 * `step` field (the producing step id) so the canvas can map
 * diagnostics back to nodes. */
export type VerifyFix = {
  code: string;
  message: string;
  step?: string;
  branch?: string;
  path?: string;
  suggestion?: string | null;
  severity?: 'error' | 'warning' | string;
};
export type VerifyResult = {
  ok: boolean;
  ready_to_push: boolean;
  required_fixes: VerifyFix[];
  warnings: VerifyFix[];
  checks_run: Array<{ name: string; ok: boolean; summary?: string }>;
  next_actions: string[];
  /** Populated only when verbose=true. Maps jinja-key (step name with
   * spaces→underscores) to the typed_walker Shape. Consumers use this
   * + shapeStubs.buildJinjaContext to build a `context` for render_jinja. */
  evidence?: {
    per_step_jinja_shapes?: Record<string, unknown>;
    [k: string]: unknown;
  };
};

export async function verifyPlaybook(
  yamlText: string,
  opts: { playbook?: string; livePrope?: boolean; verbose?: boolean } = {}
): Promise<VerifyResult> {
  const r = await callMcpTool<VerifyResult>('verify_playbook', {
    yaml_text: yamlText,
    playbook: opts.playbook,
    live_probe: !!opts.livePrope,
    verbose: !!opts.verbose
  });
  if (!r.ok || !r.result) {
    return {
      ok: false,
      ready_to_push: false,
      required_fixes: [],
      warnings: [],
      checks_run: [],
      next_actions: r.error ? [r.error] : []
    };
  }
  return {
    ok: r.result.ok ?? false,
    ready_to_push: r.result.ready_to_push ?? false,
    required_fixes: r.result.required_fixes ?? [],
    warnings: r.result.warnings ?? [],
    checks_run: r.result.checks_run ?? [],
    next_actions: r.result.next_actions ?? [],
    evidence: r.result.evidence
  };
}

export async function suggestFixForDiagnostic(d: Diagnostic): Promise<SuggestedFix> {
  const r = await callMcpTool<SuggestedFix>('suggest_fix_for_diagnostic', { diagnostic: d });
  if (!r.ok || !r.result) return { ok: false, reason: r.error ?? 'mcp call failed' };
  return r.result;
}

export type ValidateResult = { ok: boolean; markers: Marker[]; fixes?: Fix[] };
export type CompileResult = { ok: boolean; fsr_json: unknown | null; markers: Marker[] };

export async function validateYaml(text: string): Promise<ValidateResult> {
  const r = await fetch('/api/yaml/validate', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!r.ok) throw new Error(`validate ${r.status}`);
  return r.json();
}

export type Fix = {
  line: number;
  col: number;
  end_line: number;
  end_col: number;
  original: string;
  replacement: string;
  code: string;
  message: string;
  severity: 'warning' | 'error' | 'info';
};

export async function compileYaml(text: string): Promise<CompileResult> {
  const r = await fetch('/api/yaml/compile', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!r.ok) throw new Error(`compile ${r.status}`);
  return r.json();
}

export type ChatMessage = { role: 'user' | 'assistant'; content: string };

export type LadderRung = {
  id: 'compiles' | 'runs' | 'works';
  label: string;
  state: 'passed' | 'failed' | 'skipped' | 'pending';
  summary: string;
};

export type ChatEvent =
  | { kind: 'text'; text: string }
  | {
      kind: 'tool_use';
      name: string;
      arguments: Record<string, unknown>;
      call_id: string;
      /** HITL Phase 2: server-resolved tier (0–4). 0/1/2 auto-allow;
       *  3+ went through an approval card. Used by the audit pane to
       *  flag tier-3+ rows. Default 0 when older backends don't send it. */
      tier?: number;
    }
  | { kind: 'tool_result'; call_id: string; result_preview: string }
  | {
      kind: 'usage';
      session_id: string;
      turn: number;
      model: string;
      tags: Record<string, unknown>;
      input_tokens?: number;
      output_tokens?: number;
      cache_read?: number;
      cache_write?: number;
      tool_calls?: { name: string; args_chars: number; result_chars: number }[];
    }
  | {
      kind: 'ladder';
      rungs: LadderRung[];
      error_count: number;
      warning_count: number;
      achieved: number;
    }
  | {
      kind: 'approval_request';
      approval_id: string;
      tool_use_id: string;
      tool: string;
      tier: number;
      preview: { tool: string; args: Record<string, unknown> };
      args_hash: string;
      summary: string | null;
      requires_step_up: boolean;
    }
  | { kind: 'done'; stop_reason: string }
  | { kind: 'error'; message: string };

export function parseChatEvent(event: string, data: string): ChatEvent | null {
  try {
    const obj = JSON.parse(data);
    switch (event) {
      case 'text':
        return { kind: 'text', ...obj };
      case 'tool_use':
        return { kind: 'tool_use', ...obj };
      case 'tool_result':
        return { kind: 'tool_result', ...obj };
      case 'usage':
        return { kind: 'usage', ...obj };
      case 'ladder':
        return { kind: 'ladder', ...obj };
      case 'approval_request':
        return { kind: 'approval_request', ...obj };
      case 'done':
        return { kind: 'done', ...obj };
      case 'error':
        return { kind: 'error', ...obj };
    }
  } catch {
    return null;
  }
  return null;
}

export type StepTypeHint = { name: string; detail: string };

export async function getStepTypes(): Promise<StepTypeHint[]> {
  const r = await fetch('/api/ref/step-types');
  if (!r.ok) throw new Error(`step-types ${r.status}`);
  return r.json();
}

export type ConnectorRef = {
  name: string;
  label: string | null;
  category: string | null;
  description: string | null;
};

export async function searchConnectors(q = '', limit = 50): Promise<ConnectorRef[]> {
  const r = await fetch(`/api/ref/connectors?q=${encodeURIComponent(q)}&limit=${limit}`);
  if (!r.ok) throw new Error(`connectors ${r.status}`);
  return r.json();
}

export type OperationRef = {
  op_name: string;
  title: string | null;
  category: string | null;
  description: string | null;
};

export async function listOperations(connector: string, q = '', limit = 100): Promise<OperationRef[]> {
  const r = await fetch(
    `/api/ref/connectors/${encodeURIComponent(connector)}/operations?q=${encodeURIComponent(q)}&limit=${limit}`
  );
  if (!r.ok) return [];
  return r.json();
}

export type JinjaFilterRef = {
  name: string;
  signature: string | null;
  description: string | null;
  output_type_observed: string | null;
};

export async function listJinjaFilters(q = '', limit = 200): Promise<JinjaFilterRef[]> {
  const r = await fetch(
    `/api/ref/jinja-filters?q=${encodeURIComponent(q)}&limit=${limit}`
  );
  if (!r.ok) return [];
  return r.json();
}

export type ShapesResponse = {
  ok: boolean;
  error?: string;
  shapes: Record<string, unknown>;
  /** Top-level vars created by set_variable steps; FSR exposes these
   *  as `vars.<name>`, NOT `vars.steps.<step>.<name>` (confirmed by
   *  scanning the production corpus). */
  top_level_vars?: Record<string, unknown>;
  needs_verify?: Array<{ step: string; step_id: string; reason: string }>;
};

/** Fast typed-walker pass — returns per-step Jinja shapes WITHOUT
 *  running the full verify_playbook gate. Used by the variable picker
 *  + Monaco completions so the user sees real step output shapes on
 *  every YAML edit, not just after clicking Verify. */
export async function fetchShapes(text: string): Promise<ShapesResponse> {
  try {
    const r = await fetch('/api/yaml/shapes', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!r.ok) return { ok: false, shapes: {} };
    return (await r.json()) as ShapesResponse;
  } catch (e: any) {
    return { ok: false, error: e?.message ?? String(e), shapes: {} };
  }
}

export type GlobalVarRef = {
  name: string;
  value: string | null;
  default_value: string | null;
};

export type SampleRecordResponse = {
  ok: boolean;
  module?: string;
  records: Array<Record<string, unknown>>;
  error?: string;
};

/** Pull live sample records from FSR for `<module>` — used by the
 *  start-step UI / variable picker so the user can SEE what
 *  `vars.input.records[0]` will actually look like at runtime. */
export async function fetchSampleRecords(module: string, limit = 5): Promise<SampleRecordResponse> {
  if (!module) return { ok: false, records: [] };
  try {
    const r = await fetch(`/api/ref/sample-record/${encodeURIComponent(module)}?limit=${limit}`);
    if (!r.ok) return { ok: false, records: [], error: `HTTP ${r.status}` };
    return (await r.json()) as SampleRecordResponse;
  } catch (e: any) {
    return { ok: false, records: [], error: e?.message ?? String(e) };
  }
}

export type RecentRun = {
  id: number | null;
  status: string | null;
  created: string | null;
  name: string;
  records: string[];
};

/** Recent FSR playbook executions. Returns each run with its
 *  record-IRI list — the trigger sample picker uses one of those
 *  IRIs to fetch the actual record that was running. */
export async function fetchRecentRuns(
  playbookIri?: string, limit = 5
): Promise<RecentRun[]> {
  try {
    const qs = new URLSearchParams();
    if (playbookIri) qs.set('playbook_iri', playbookIri);
    qs.set('limit', String(limit));
    const r = await fetch(`/api/ref/recent-runs?${qs}`);
    if (!r.ok) return [];
    const data = await r.json();
    return (data?.runs ?? []) as RecentRun[];
  } catch {
    return [];
  }
}

export type RunDetail = {
  ok: boolean;
  error?: string;
  id?: number | null;
  status?: string | null;
  created?: string | null;
  modified?: string | null;
  name?: string;
  records?: string[];
  wf_step_logs?: unknown;
  step_logs?: unknown;
  stepInstances?: unknown;
  input_parameters?: unknown;
};

/** Pull the full FSR workflow execution detail for a single run.
 *  Lets the editor seed sample input + (eventually) per-step variables
 *  from real production data so authors can iterate against the exact
 *  context the playbook had. */
export async function fetchRunDetail(runId: number | string): Promise<RunDetail> {
  try {
    const r = await fetch(`/api/ref/run-detail/${encodeURIComponent(String(runId))}`);
    if (!r.ok) return { ok: false, error: `HTTP ${r.status}` };
    return (await r.json()) as RunDetail;
  } catch (e: any) {
    return { ok: false, error: e?.message ?? String(e) };
  }
}

/** Fetch a single record by its IRI (`/api/3/alerts/<uuid>`). Used
 *  by the sample picker after the user picks a recent run + IRI. */
export async function fetchRecordByIri(
  iri: string
): Promise<Record<string, unknown> | null> {
  if (!iri) return null;
  try {
    const r = await fetch(`/api/ref/record-by-iri?iri=${encodeURIComponent(iri)}`);
    if (!r.ok) return null;
    const data = await r.json();
    return data?.record ?? null;
  } catch {
    return null;
  }
}

/** Fetches FSR dynamic-variables. Returns [] when FSR is offline so
 *  callers can fall back to a YAML-buffer scrape. */
export async function listGlobalVars(): Promise<GlobalVarRef[]> {
  try {
    const r = await fetch('/api/ref/global-vars');
    if (!r.ok) return [];
    return await r.json();
  } catch {
    return [];
  }
}

export type PushResult = { ok: boolean; stdout: string; stderr: string; exit_code: number };

export async function pushPlaybook(text: string, mode = 'safe'): Promise<PushResult> {
  const r = await fetch('/api/playbook/push', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text, mode })
  });
  if (!r.ok) throw new Error(`push ${r.status}`);
  return r.json();
}

export type RunStartIn = { name: string; input?: Record<string, unknown>; record?: string };

export type EnvResult = { ok: boolean; env: { vars: Record<string, unknown> } | null; error: string | null };

export async function getRunEnv(pk: string): Promise<EnvResult> {
  const r = await fetch(`/api/run/${encodeURIComponent(pk)}/env`);
  if (!r.ok) throw new Error(`env ${r.status}`);
  return r.json();
}

export function extractYamlBlock(text: string): string | null {
  const re = /```ya?ml\n([\s\S]*?)```/gi;
  let m: RegExpExecArray | null;
  let last: string | null = null;
  while ((m = re.exec(text))) last = m[1];
  return last;
}


export interface ExamplePrompt {
  name: string;
  prompt: string;
  notes: string;
  has_gold: boolean;
}

export async function listExamplePrompts(): Promise<ExamplePrompt[]> {
  const r = await fetch('/api/ref/example-prompts');
  if (!r.ok) throw new Error(`example-prompts ${r.status}`);
  return r.json();
}

// --- Visual editor (Phase 1 of VISUAL_EDITOR_PLAN) -------------------

export type VisualNode = {
  id: string;
  type: string;
  family: 'trigger' | 'connector_op' | 'decision' | 'utility'
        | 'record_crud' | 'manual_input' | 'workflow_ref' | 'terminal';
  name: string;
  arguments: Record<string, unknown>;
  for_each: Record<string, unknown> | null;
  comment: string | null;
  position: { x: number; y: number } | null;
};

export type VisualEdge = {
  source: string;
  target: string;
  label: string | null;
  branch_kind: 'next' | 'branch' | 'unlabeled';
};

export type VisualPlaybook = {
  name: string;
  description: string;
  parameters: string[];
  trigger: string;
  trigger_step_id: string | null;
  /** Whether the playbook is enabled. Trigger playbooks with
   * `is_active: false` ship to FSR but never fire — the inspector
   * surfaces a guard banner so the user catches the silent dead-end
   * before testing. Defaults to false (matches the IR default). */
  is_active?: boolean;
  /** FSR's per-workflow verbose-tracing flag. New drafts scaffold
   * with this on so authors see step output without flipping a knob;
   * production playbooks should turn it off. */
  debug?: boolean;
  nodes: VisualNode[];
  edges: VisualEdge[];
};

export type VisualGraph = {
  collection: { name: string; description: string; visible: boolean } | null;
  playbooks: VisualPlaybook[];
  layout_present: boolean;
  errors: { code: string | null; message: string; path: string | null }[];
  source: { path: string | null; yaml: string };
};

export async function listVisualFiles(): Promise<{ count: number; files: { name: string; size: number }[] }> {
  const r = await fetch('/api/visual/list');
  if (!r.ok) throw new Error(`visual/list ${r.status}`);
  return r.json();
}

export async function getVisualFile(path: string): Promise<VisualGraph> {
  const r = await fetch(`/api/visual/file?path=${encodeURIComponent(path)}`);
  if (!r.ok) throw new Error(`visual/file ${r.status}`);
  return r.json();
}

export async function getVisualFromBuffer(text: string): Promise<VisualGraph> {
  const r = await fetch('/api/visual/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!r.ok) throw new Error(`visual/buffer ${r.status}`);
  return r.json();
}

export async function callMcpTool<T = unknown>(name: string, args: Record<string, unknown>): Promise<{ ok: boolean; result?: T; error?: string }> {
  const r = await fetch(`/api/mcp/${encodeURIComponent(name)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(args)
  });
  if (!r.ok) throw new Error(`mcp/${name} ${r.status}`);
  return r.json();
}

// --- Phase 5 failed-runs surface (VERIFY_PLAYBOOK_PLAN) -----------------

export type FailedRun = {
  task_id: string;
  pk: number | null;
  name: string | null;
  status: string;
  error_message: string | null;
  modified: string | null;
  uuid: string | null;
  source: 'live' | 'historical' | string;
  error?: string;
};

export async function listRecentFailedRuns(
  args: { limit?: number; playbook?: string; include_finished?: boolean } = {},
): Promise<FailedRun[]> {
  const r = await callMcpTool<FailedRun[]>('list_recent_failed_runs', args);
  if (!r.ok) throw new Error(r.error || 'list_recent_failed_runs failed');
  return r.result ?? [];
}

export type WhyDidPlaybookFail = {
  ok: boolean;
  code?: string;
  message?: string;
  pb_execution?: string;
  run_status?: string;
  playbook_name?: string;
  error_message?: string | null;
  summary?: {
    total_templates: number;
    render_failures: number;
    referenced_step_keys: string[];
  };
  step_diagnostics?: Array<{
    step: string;
    location: string;
    severity: string;
    code: string;
    message: string;
    template?: string;
    suggestion?: string;
  }>;
  hints?: string[];
};

export async function whyDidPlaybookFail(
  playbook_or_id: string,
  yaml_text?: string,
): Promise<WhyDidPlaybookFail> {
  const args: Record<string, unknown> = { playbook_or_id };
  if (yaml_text) args.yaml_text = yaml_text;
  const r = await callMcpTool<WhyDidPlaybookFail>('why_did_playbook_fail', args);
  if (!r.ok) throw new Error(r.error || 'why_did_playbook_fail failed');
  return r.result ?? { ok: false };
}

export type RecipeRef = { name: string; kind: string; when_to_use: string | null };

export async function listRecipes(): Promise<RecipeRef[]> {
  const r = await fetch('/api/ref/recipes');
  if (!r.ok) throw new Error(`recipes ${r.status}`);
  return r.json();
}

// --- Unified playbook store (Phase A backend) ---------------------------

export type PlaybookKind = 'example' | 'draft';
export type PlaybookListItem = {
  kind: PlaybookKind;
  name: string;
  size: number;
  updated_ts: string;
};
export type DraftRevision = {
  id: number;
  reason: string | null;
  is_auto: boolean;
  created_ts: string;
  size: number;
};

export async function listPlaybooks(): Promise<{ count: number; items: PlaybookListItem[] }> {
  const r = await fetch('/api/playbooks');
  if (!r.ok) throw new Error(`playbooks ${r.status}`);
  return r.json();
}

export async function getExample(name: string): Promise<{ kind: 'example'; name: string; yaml: string }> {
  const r = await fetch(`/api/playbooks/example/${encodeURIComponent(name)}`);
  if (!r.ok) throw new Error(`example ${r.status}`);
  return r.json();
}

export async function getDraft(name: string): Promise<{ kind: 'draft'; name: string; yaml: string; created_ts: string; updated_ts: string }> {
  const r = await fetch(`/api/playbooks/draft/${encodeURIComponent(name)}`);
  if (!r.ok) throw new Error(`draft ${r.status}`);
  return r.json();
}

/** Thrown by `putDraft` (and any other mutation that wants retry-aware
 *  behavior). `transient` flags errors the save mutation should retry:
 *  network failures + 5xx. 4xx is treated as permanent — those usually
 *  mean validation / auth / route-not-found and won't change on retry. */
export class SaveError extends Error {
  status: number | 'network';
  transient: boolean;
  constructor(message: string, status: number | 'network') {
    super(message);
    this.name = 'SaveError';
    this.status = status;
    this.transient = status === 'network' || (typeof status === 'number' && status >= 500);
  }
}

export async function putDraft(name: string, yaml: string, opts: { reason?: string; auto?: boolean } = {}): Promise<{ ok: boolean; revision_id: number; updated_ts: string }> {
  let r: Response;
  try {
    r = await fetch(`/api/playbooks/draft/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml, reason: opts.reason ?? null, auto: !!opts.auto })
    });
  } catch (e) {
    // fetch only throws on network failure (DNS, offline, CORS preflight).
    throw new SaveError(`network: ${(e as Error).message}`, 'network');
  }
  if (!r.ok) {
    const detail = await r.text().catch(() => '');
    throw new SaveError(`draft put ${r.status}${detail ? `: ${detail}` : ''}`, r.status);
  }
  return r.json();
}

export async function deleteDraft(name: string): Promise<void> {
  const r = await fetch(`/api/playbooks/draft/${encodeURIComponent(name)}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`draft delete ${r.status}`);
}

export async function listDraftRevisions(name: string): Promise<{ count: number; revisions: DraftRevision[] }> {
  const r = await fetch(`/api/playbooks/draft/${encodeURIComponent(name)}/revisions`);
  if (!r.ok) throw new Error(`revisions ${r.status}`);
  return r.json();
}

export async function getDraftRevision(name: string, id: number): Promise<{ id: number; yaml: string; reason: string | null; is_auto: boolean; created_ts: string }> {
  const r = await fetch(`/api/playbooks/draft/${encodeURIComponent(name)}/revisions/${id}`);
  if (!r.ok) throw new Error(`revision ${r.status}`);
  return r.json();
}

export async function cloneExample(example: string, draft: string): Promise<{ ok: boolean; name: string }> {
  const r = await fetch('/api/playbooks/draft/from-example', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ example, draft })
  });
  if (!r.ok) {
    let msg = `clone ${r.status}`;
    try { const j = await r.json(); if (j.detail) msg = j.detail; } catch {}
    throw new Error(msg);
  }
  return r.json();
}
