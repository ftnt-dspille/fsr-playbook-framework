# Using fsrpb without an LLM

Every MCP tool in this repo is a plain Python function. The
`@mcp.tool()` decorator advertises it to MCP clients, but nothing about
the implementation depends on an LLM being in the loop. This doc maps
the four no-LLM access paths so you can pick whichever fits the
workflow.

## 1. Direct Python imports

```python
from mcp_server import (
    find_connector, get_op_schema, validate_yaml, run_op,
    diagnose_yaml_against_pb_execution, assert_playbook_outcome,
)

# Search the catalog without paying tokens.
hits = find_connector("siem")

# Compile-check a YAML file in a script.
result = validate_yaml(open("my.yaml").read())
if not result["ok"]:
    for e in result["errors"]:
        print(f"[{e['code']}] {e['path']}: {e['message']}")

# After running a playbook, verify the effect.
assert_playbook_outcome([
    {"kind": "record_exists", "module": "alerts",
     "filters": {"name": "Demo alert"}},
    {"kind": "field_equals", "module": "alerts",
     "filters": {"name": "Demo alert"},
     "field": "status.itemValue", "value": "Closed"},
])
```

Used internally by `python/evals/harness.py`,
`python/tests/test_assert_outcome.py`, and the diagnose tests.

## 2. The `fsrpb` CLI

Most MCP tools have a one-shot CLI mirror. Pipe-friendly; `--json` on
the read commands.

| What you want                            | Command                                                 |
|------------------------------------------|---------------------------------------------------------|
| compile / dry-run                        | `fsrpb validate <yaml>` · `fsrpb compile <yaml>`        |
| live prechecks (connector, picklists)    | `fsrpb resolve <yaml>`                                  |
| push to the live FSR                     | `fsrpb push --mode replace <yaml>`                      |
| run a deployed playbook + follow         | `fsrpb run-playbook <name> --follow`                    |
| diagnose a failed run                    | `fsrpb diagnose <yaml> <pb_execution>`                  |
| pull an existing playbook as YAML        | `fsrpb pull <name\|uuid>`                               |
| local↔live diff                          | `fsrpb diff <yaml>`                                     |
| outcome assertions (post-run)            | `fsrpb assert assertions.json`                          |
| LLM-eval matrix                          | `fsrpb evals --models gold,echo,anthropic`              |
| picklist exploration                     | `fsrpb picklist list \| show \| for-field \| resolve`   |
| jinja filter catalog                     | `fsrpb jinja-filter <q> [--examples]`                   |
| corpus search                            | `fsrpb search <q>`                                      |
| recipe library                           | `fsrpb recipe find [--kind data_ingest]`                |
| index audit                              | `fsrpb inventory summary \| connectors \| stale`        |
| reset demo state                         | `fsrpb demo prep` (FSR_ALLOW_E2E gated)                 |

Every command exits 0 on success, non-zero on failure — easy to wire
into any shell pipeline.

## 3. Web HTTP routes

The web app already exposes a subset of tools as REST so non-Python
clients can consume them:

```
GET  /api/ref/connectors?q=siem
GET  /api/ref/connectors/<name>/operations
GET  /api/ref/jinja-filters?q=picklist
GET  /api/ref/inventory
GET  /api/ref/inventory/search?q=...
GET  /api/ref/api-examples?q=...
GET  /api/ref/synthesize-http-step?entry_id=...
```

Same data the LLM sees — without the LLM. The Inventory dashboard's
"Browse the index" panel is the most visible consumer; it powers
zero-typing exploration of the entire reference store.

## 4. Editor integration

Monaco YAML autocomplete is wired through the same routes:

- `type: <Tab>`        → step-type snippets that scaffold the next required fields
- `connector: <Tab>`   → fuzzy-search every catalogued connector
- `operation: <Tab>`   → ops for the connector named on the line above
- `{{ value | <Tab>`   → 170+ Jinja filters with signatures + descriptions

No LLM round-trip for any of these — pure SQLite reads through the web
backend.

## 5. Pre-commit hook

`scripts/external/pre-commit.fsrpb.sh` runs `validate` + `resolve` against
every staged playbook YAML. Install:

```bash
ln -s ../../scripts/external/pre-commit.fsrpb.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

`validate` is offline-clean (compiler + linter); `resolve` short-circuits
silently when no live FSR is configured, so the hook works in CI too.

## 6. Other MCP clients

`fsrpb mcp` starts the server over stdio. Any MCP-compatible client —
Cursor, Continue, Zed, Claude Code, custom scripts — can register it:

```jsonc
// .claude/settings.json (or your client's equivalent)
{
  "mcpServers": {
    "fsrpb": {
      "command": "python",
      "args": ["/path/to/fsrpb/tooling/cli.py", "mcp"]
    }
  }
}
```

## What still genuinely needs an LLM

Two narrow surfaces:

1. **Translating English into a connector + op + arg choice.**
   ("Ingest VirusTotal alerts at Severity High" → which op? which
   field maps to severity?) Once you've picked, the rest is
   deterministic.
2. **Writing the YAML scaffold from scratch.** Once a draft exists,
   `validate` + `resolve` + `diagnose` + `assert` close every loop
   without an LLM in sight.

Everything else — lookups, validation, live execution, diagnostics,
recipe synthesis from `info.json`, outcome assertions — is plain
Python you can call from any context.
