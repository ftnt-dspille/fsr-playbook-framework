# fsr_playbooks (packaging dist)

Dedicated build for the `fsr_playbooks` package — the FortiSOAR playbook
authoring/compiler framework (YAML→FSR-JSON compiler, LLM co-authoring, MCP
server tools). The source tree lives at the **repo root** (`../../fsr_playbooks`);
this directory only holds the `pyproject.toml` that builds it as its own dist,
since the root `pyproject.toml` is taken by the `fsrpb` CLI dist.

## Install (Phase 1: git+https, wheel only)

```
pip install "git+https://svl-devops-gitlab01.fortilab.fortinet.com/dspille/fsr-playbook-framework.git@<ref>#subdirectory=packaging/fsr_playbooks"
```

Extras:
- (base) — compiler + agent: `pyyaml`, `ruamel.yaml`, `jinja2`
- `[llm]` — `openai`, `anthropic`
- `[mcp]` — `mcp` (implies `[llm]`)

## Build / verify locally

```
uv build --wheel --out-dir dist        # from this directory
unzip -l dist/*.whl                     # confirm fsr_playbooks/** + .md/.json
```

> The relative `..` package-dir works for pip's in-place VCS **wheel** build off
> a clone. An sdist would be broken by the `..` — only wheels are shipped via VCS.

## Known Phase-1 limitation

The MCP live-execution / recipe tools (`mcp_server/tools_{execution,recipe,discovery}.py`)
lazily `import probes._env` / `e2e.runner`, which are sibling root packages **not**
included in this dist. Those specific tools won't work standalone; everything else
(compiler, agent, the rest of the MCP surface) imports cleanly.
