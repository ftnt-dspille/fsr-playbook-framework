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
  id: 'compile' | 'prechecks' | 'reachability' | 'dry_run' | 'outcome';
  label: string;
  state: 'passed' | 'failed' | 'skipped' | 'pending';
  summary: string;
};

export type ChatEvent =
  | { kind: 'text'; text: string }
  | { kind: 'tool_use'; name: string; arguments: Record<string, unknown>; call_id: string }
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

export type PushResult = { ok: boolean; stdout: string; stderr: string; exit_code: number };

export async function pushPlaybook(text: string, mode = 'replace'): Promise<PushResult> {
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

export async function putDraft(name: string, yaml: string, opts: { reason?: string; auto?: boolean } = {}): Promise<{ ok: boolean; revision_id: number; updated_ts: string }> {
  const r = await fetch(`/api/playbooks/draft/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yaml, reason: opts.reason ?? null, auto: !!opts.auto })
  });
  if (!r.ok) throw new Error(`draft put ${r.status}`);
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
