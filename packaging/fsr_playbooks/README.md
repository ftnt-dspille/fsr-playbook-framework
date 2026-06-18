# fsr_playbooks

A FortiSOAR **playbook authoring & compiler framework**:

- **Compiler** — turn readable YAML into FortiSOAR playbook JSON (parser →
  resolver → validator → emitter), round-trip lossless with structured
  diagnostics.
- **Agent** — LLM co-authoring helpers for building and triaging playbooks.
- **MCP server** — tools that expose the compiler, connector/Jinja reference,
  and playbook authoring to MCP-compatible clients.

## Install

```bash
pip install fsr_playbooks            # base: compiler + agent
pip install "fsr_playbooks[llm]"     # + OpenAI / Anthropic providers
pip install "fsr_playbooks[mcp]"     # + MCP server (implies [llm])
```

Requires Python 3.9+ (the base compiler). The `[mcp]` extra requires 3.10+.

## End-to-end: author → compile → deploy → run

### 1. Author a playbook in YAML

The compiler input is a readable collection of playbooks. A minimal one
(`start → set_variable → connector`):

```yaml
# hello_connector.yaml
collection: Compiler Demo
description: Smallest possible end-to-end — start, set a variable, call a connector.
visible: true

playbooks:
  - name: Hello Connector
    description: Demonstrates start -> set_variable -> connector flow.
    steps:
      - name: Start
        type: start
        next: Prepare inputs

      - name: Prepare inputs
        type: set_variable
        next: Get organization
        vars:
          target_org: "Fortinet"

      - name: Get organization
        type: connector
        arguments:
          connector: fortinet-fortisiem
          operation: get_org_name_by_org_id
          config: ""
          params:
            domain_id: "{{ vars.target_org }}"
```

### 2. Compile it to FortiSOAR playbook JSON

```python
from pathlib import Path
from fsr_playbooks import compile_yaml

# The reference DB resolves connectors, operations, params, step types, and
# Jinja. It ships with the full framework repo (store/fsr_reference.db), NOT
# the PyPI wheel — point this at your copy.
REFERENCE_DB = Path("store/fsr_reference.db")

text = Path("hello_connector.yaml").read_text()
result = compile_yaml(text, REFERENCE_DB)

if not result.ok:
    for err in result.errors:                       # structured, never raises
        print(f"[{err.severity}] {err.code}: {err.message}  ({err.path})")
    raise SystemExit("compile failed")

collection = result.fsr_json["data"][0]             # the FortiSOAR collection entity
```

`compile_yaml(text, db_path, lax_codes=None) -> CompileResult` returns a result
object with `.ok`, `.fsr_json` (`{"data": [collection]}`), `.errors`,
`.warnings`, and `.ir` (the parsed tree) — it reports problems as structured
`CompileError`s rather than raising.

### 3. Deploy the collection to a FortiSOAR instance

Pushing and triggering talk to a live FortiSOAR REST API, so they use the
[`pyfsr`](https://pypi.org/project/pyfsr/) client (`pip install pyfsr`) — this
package does the compiling, `pyfsr` does the transport.

```python
from pyfsr import FortiSOAR

client = FortiSOAR(
    base_url="https://your-fortisoar-host",
    auth="<api-key>",                  # or ("username", "password")
    verify_ssl=True,
)

# Push the compiled collection. The compiler-assigned uuid is preserved, so
# re-deploys can target it with client.workflow_collections.update(uuid, ...)
# / .delete(uuid).
client.workflow_collections.create(
    name=collection["name"],
    description=collection.get("description", ""),
    visible=collection.get("visible", True),
    uuid=collection["uuid"],
    workflows=collection["workflows"],     # full workflow objects (steps + routes)
    record_tags=collection.get("recordTags"),
)
```

### 4. Trigger the playbook and wait for it

```python
import time

wf_uuid = collection["workflows"][0]["uuid"]

run = client.playbooks.trigger(playbook="Hello Connector", inputs={})
task_id = run["task_id"]

# Poll the run records (shaped dicts: task_id, name, status, error_message, ...)
# until this run reaches a terminal state.
while True:
    match = next(
        (r for r in client.playbooks.runs(playbook_uuid=wf_uuid, limit=5)
         if r["task_id"] == task_id),
        None,
    )
    status = match["status"] if match else "pending"
    if status in ("finished", "failed", "terminated"):
        print("execution status:", status)
        break
    time.sleep(2)
```

> **What needs what:** step 2 (compile) is pure `fsr_playbooks` + the reference
> DB. Steps 3–4 (deploy/run) additionally need `pyfsr` and a reachable
> FortiSOAR instance. The `fsr_playbooks` package never imports `pyfsr` itself.

## Extras

| Extra    | Adds                          | Use for                          |
|----------|-------------------------------|----------------------------------|
| (base)   | `pyyaml`, `ruamel.yaml`, `jinja2` | YAML → FSR JSON compilation  |
| `[llm]`  | `openai`, `anthropic`         | LLM-assisted authoring / triage  |
| `[mcp]`  | `mcp` (+ `[llm]`)             | running the MCP server tools      |

## License

MIT — see [LICENSE](LICENSE).

## Links

- Source: https://github.com/ftnt-dspille/fsr-playbook-framework

> Note: the MCP server's live-execution / recipe tools depend on the reference
> store and probe helpers that ship with the full framework repo, not this
> package alone. The compiler, agent, and the rest of the MCP surface work
> standalone.
