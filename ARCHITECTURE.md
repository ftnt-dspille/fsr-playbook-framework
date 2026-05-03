# FSRPlaybookYaml — architecture & end state

**Status**: living doc. Last updated 2026-05-02.

## North star

FortiSOAR is the execution engine. Everything we build emits a valid FSR
`WorkflowCollection` JSON in the end. What changes is *who* authors the
upstream representation and *how* they get feedback while doing it.

There are three authoring surfaces, all targeting the same compiler:

```
   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
   │  Human (CLI)     │    │  Agent (MCP)     │    │  Human (visual)  │
   │  writes YAML     │    │  writes YAML     │    │  drags blocks    │
   └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    ▼
                       ┌────────────────────────┐
                       │   Simplified YAML IR   │
                       └───────────┬────────────┘
                                   ▼
                       ┌────────────────────────┐
                       │  Compiler (parser →    │
                       │  resolver → validator  │
                       │  → emitter)            │
                       └───────────┬────────────┘
                                   ▼
                       ┌────────────────────────┐
                       │  FSR WorkflowCollection│
                       │  JSON (importable)     │
                       └───────────┬────────────┘
                                   ▼
                              FortiSOAR
```

The reference store (`store/fsr_reference.db` + `.json`) is the brain: it
is what the resolver/validator consult, what MCP tools query, and what the
visual editor renders pickers from.

## The two LLM flows

### Flow A — deterministic compile, no LLM at compile-time
Human (or any tool) writes simplified YAML → `fsrpb compile` → FSR JSON.
Reproducible, diff-able, version-controllable. This is the foundation.
Compiler v1 (TODO #4) targets this.

### Flow B — agent-in-the-loop authoring
LLM writes the YAML, calls validation/testing tools, iterates. The LLM
never writes FSR JSON directly — it writes YAML and trusts the compiler.
The MCP server is the interface that makes this loop work.

We are **not planning to fine-tune** a model. With a good MCP toolset and
the cheatsheets already built (`FSR_CUSTOM_JINJA.md`, `STEP_TYPES.md`),
frontier-class models should author correctly via tool use. Revisit only
if tool-use authoring plateaus.

## Components

### 1. Reference store (built — Phase 1-2 complete)
SQLite + bundled JSON snapshot. Trust-tracked. Source of truth for every
"does this exist / what shape" question.

### 2. Compiler (TODO #4 — next)
- `parser.py` — YAML → IR
- `resolver.py` — connector/op/param/step/jinja-ref lookups against store
- `validator.py` — strict mode, "did you mean…" suggestions
- `emitter.py` — IR → FSR JSON
- **Returns structured error objects, not stderr strings** — MCP needs
  machine-readable diagnostics.
- Acceptance: bambenek-feed YAML → JSON byte-equivalent (modulo
  UUIDs/timestamps) to vendor original.

### 3. MCP server (new — after compiler v1)
Wraps compiler + reference store + live FSR. Exposes tools any
MCP-capable agent (Claude Code, IDE plugins, the widget) can call:

| Tool | Backed by | Purpose |
|---|---|---|
| `find_connector(q)` | SQLite FTS | fuzzy search 714 connectors |
| `find_operation(connector, q)` | SQLite | list ops + fuzzy search |
| `get_op_schema(connector, op)` | SQLite | params, types, required, picklists |
| `get_step_type(name)` | SQLite + STEP_TYPES.md | schema + 3 real examples |
| `find_jinja_filter(q)` | SQLite | filter sig + observed type |
| `render_jinja(template, ctx)` | live `/api/wf/api/jinja-editor/` | runtime check |
| `search_playbooks(q)` | FTS over `playbooks_seen` | "how do others do X" |
| `validate_yaml(yaml)` | compiler dry-run | structured errors |
| `compile(yaml)` | compiler | YAML → FSR JSON |
| `dry_run_playbook(yaml)` | Phase 5 e2e probes | import + execute + cleanup on test FSR |

### 4. End-user interfaces (longer-term)
All sit on top of the compiler + MCP, none reinvent the engine.

- **CLI** (`fsrpb`) — power-user path. `fsrpb compile`, `fsrpb validate`,
  `fsrpb push`, `fsrpb diff`. Already scaffolded.
- **Visual editor** — drag-and-drop block authoring for non-CLI users.
  Renders pickers from the reference store. Same compiler under the hood,
  so visual output is interoperable with hand-written YAML.
- **FortiSOAR widget** — TS port of compiler runs in-browser inside
  FSR. Same reference JSON snapshot, same emitter. Lets users author
  inside FSR without leaving the appliance.

The invariant: **all three surfaces produce the same simplified YAML IR**,
which goes through the same compiler. A YAML authored visually opens
correctly in the CLI editor and vice versa.

## Roadmap (ordered)

1. ~~Reference store (probes + cheatsheets + JSON bundle)~~ ✅
2. **Compiler v1** — TODO #4. Build with MCP as explicit consumer:
   structured errors, programmatic API, no `print()` side effects.
3. **MCP server v1** — read-only tools first (find_*, get_*, render_jinja,
   validate_yaml, compile). Ship before e2e is wired.
4. **Phase 5 e2e probes** — TODO #3. Becomes `dry_run_playbook` MCP tool.
5. **TS compiler port** — for the widget surface.
6. **Visual editor** — only after CLI + MCP are stable; consumes same IR.

## Design rules

- **Compiler is library-first, CLI is a thin wrapper.** Anything the CLI
  does, MCP and the widget can do too, by importing the same functions.
- **Errors are data, not strings.** Every validator failure has a code,
  location (line/col), suggested fix.
- **Reference store is the single source of truth.** Compiler never
  hardcodes connector/op/step-type knowledge — always resolves through
  the store. Probes refresh the store; the compiler stays stable.
- **Never trust local-only data for correctness.** Existing trust ladder
  stays: `live_*` + `tested_pass` ⇒ `is_trusted=1`; everything else is
  `seen` and surfaces with a warning.
- **Same IR across surfaces.** CLI YAML, MCP-authored YAML, and visual
  editor output are the same shape. A round-trip (compile → decompile)
  should be lossless modulo formatting.
