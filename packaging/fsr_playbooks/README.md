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

## Quickstart

```python
from fsr_playbooks.compiler import ...  # compile YAML -> FortiSOAR playbook JSON
```

See the compiler module for the parse → resolve → validate → emit pipeline.

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
