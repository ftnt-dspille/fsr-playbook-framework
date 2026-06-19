// FSRPB TypeScript compiler — widget-runnable.
//
// Loads `data/fsr_reference.json` (produced by the Python probes) and
// compiles a YAML playbook to FortiSOAR import JSON. Mirrors the Python
// compiler's stages: parse → resolve → validate → layout → emit.
//
// Real implementation lands in Phase 3b.

export type Reference = {
  schema_version: number;
  connectors: Array<{ name: string; version: string; label?: string }>;
  operations: Array<{ connector_name: string; op_name: string; title?: string }>;
  step_types: Array<{ uuid: string; name: string; args_schema_json?: string }>;
  // ... full type lands with Phase 3b
};

export function loadReference(json: string): Reference {
  return JSON.parse(json) as Reference;
}

export function compile(_yaml: string, _ref: Reference): unknown {
  throw new Error("not yet implemented — see Phase 3b in FSR_PLAYBOOK_YAML_PLAN.md");
}
