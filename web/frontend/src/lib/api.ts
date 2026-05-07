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

export async function listProviderModels(name: string): Promise<{ ok: boolean; models: string[]; error?: string }> {
  const r = await fetch(`/api/llm/providers/${encodeURIComponent(name)}/models`);
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

export type ValidateResult = { ok: boolean; markers: Marker[] };
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
