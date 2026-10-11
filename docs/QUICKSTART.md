---
title: Quickstart -- author, compile, deploy, run
category: playbook-authoring
status: reference
source: hand-written
topics:
- quickstart
- compile
- deploy
canonical: false
summary: End-to-end worked example of the fsrpb workflow (moved out of AGENTS.md).
---
# Quickstart: author → compile → deploy → run

## 1. Author YAML

```yaml
collection: My Demo
visible: true
playbooks:
  - name: Hello
    steps:
      - name: Start
        type: start
        next: Set Var
      - name: Set Var
        type: set_variable
        next: Lookup
        vars:
          target: "Fortinet"
      - name: Lookup
        type: connector
        connector: fortinet-fortisiem
        operation: get_org_name_by_org_id
        config: ""
        params:
          domain_id: "{{ vars.target }}"
        next: Done
      - name: Done
        type: end
```

See [`docs/AUTHORING.md`](docs/AUTHORING.md) for the full step-type reference,
variables, branching, looping, and universal step keys (`when`, `retry`,
`for_each`, `with`, `set`, etc.).

## 2. Compile to FortiSOAR JSON

```sh
fsrpb compile in.yaml -o out.json    # emit FSR import envelope
fsrpb validate in.yaml               # check refs + "did you mean..." diagnostics
```

From Python:

```python
from pathlib import Path
from fsr_playbooks import compile_yaml

result = compile_yaml(Path("in.yaml").read_text(), Path("data/fsr_reference.db"))
if not result.ok:
    for err in result.errors:
        print(f"[{err.severity}] {err.code}: {err.message}  ({err.path})")
else:
    collection = result.fsr_json["data"][0]
```

`compile_yaml(text, db_path) -> CompileResult` returns `.ok`, `.fsr_json`,
`.errors`, `.warnings`, `.ir`. It reports problems as structured `CompileError`s,
never raises.

## 3. Deploy + run (uses pyfsr)

```sh
pip install pyfsr                    # transport layer
fsrpb push in.yaml                   # compile + push to appliance
fsrpb run-playbook "Hello" --follow  # trigger + poll to terminal
```

From Python:

```python
from pyfsr import FortiSOAR

client = FortiSOAR("https://your-fortisoar-host", auth="<api-key>")
client.workflow_collections.create(
    name=collection["name"],
    uuid=collection["uuid"],
    workflows=collection["workflows"],
)

# One-call trigger + wait + typed result
result = client.playbooks.run_and_wait("Hello", inputs={})
print(result.status)        # 'finished' / 'failed' / 'terminated'
print(result.succeeded)     # True iff status == 'finished'
```
