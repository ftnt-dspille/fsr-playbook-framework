# Agentic Playbook Building — Presentation Outline

Working title: **From Designer Clicks to Working Playbooks — Agent-Authored FortiSOAR Automation**

Audience: SOAR engineers, automation leads, and stakeholders who already know FortiSOAR but have not seen agent-driven authoring.
Length target: ~18 slides, 25-minute talk.

Last updated: 2026-05-06.

---

## Slide 1 — Title

- **Agent-Authored Playbooks for FortiSOAR**
- Subtitle: A YAML IR + a deterministic compiler + an MCP toolbelt — any LLM can drive it
- Presenter / date

## Slide 2 — The pain we keep hitting

- Playbook Designer is click-heavy, opaque, and not diff-able
- Iteration loop is slow: edit → save → run → squint at run-log → repeat
- Field-shape bugs (`.records` vs `.data`, Jinja typos) only surface at runtime
- No version control, no PR review, no portability between environments
- Talented automation engineers spend their day clicking, not designing

## Slide 3 — The product principle

- *"Producing valid YAML is the start of the job, not the end."*
- A playbook is useless if it doesn't run on a real FSR and produce the asked-for outcome
- So the system has to prove playbooks **work**, not just compile
- Everything else on the next slides serves that one principle

## Slide 4 — Why now: agents are good enough

- Frontier LLMs handle structured authoring well — given the right tools
- Agents need a queryable spec, a deterministic compiler, fast feedback
- No fine-tuning required — tool use plus good cheatsheets is sufficient
- Bottleneck moved from "can the model write YAML" to "can it verify what it wrote"

## Slide 5 — The core idea

- One simplified YAML IR. Three authoring surfaces: CLI, agent-via-MCP, future visual editor
- All three compile through the same pipeline to native FSR `WorkflowCollection` JSON
- FortiSOAR stays the execution engine — we never replace it, we author *into* it
- Diagram: three surfaces → YAML IR → compiler → FSR

## Slide 6 — Why YAML is the right IR

- Human-readable, diff-able, review-able in a PR
- Trivially round-trippable: pull from FSR → YAML → edit → push
- Easy for an LLM to emit and reason about
- No vendor JSON ceremony (UUIDs, port coords, layout metadata) leaks into authoring

## Slide 7 — Design choice 1: SQLite-first reference store

- 714 connectors, 6,773 ops, 26K params, 43 step types, 172 Jinja filters, 1,664 playbooks corpus-mined
- FTS-indexed; one SQL query per agent question — no LLM where a lookup will do
- Probes refresh from the live appliance — compiler stays stable while the world changes
- Trust ladder (`live_*`, `tested_pass` → `is_trusted=1`) flags unverified data

## Slide 8 — Design choice 2: Library-first compiler

- Pipeline: `parser → resolver → validator → emitter`
- Compiler is a Python library; CLI, MCP server, web app are thin wrappers
- **Errors are data, not strings** — every diagnostic has a code, line/col, suggested fix
- Round-trip (compile → decompile) is lossless modulo formatting

## Slide 9 — Design choice 3: MCP as the agent contract

- 20+ MCP tools: `find_connector`, `get_op_schema`, `validate_yaml`, `compile_yaml`,
  `render_jinja`, `run_op`, `list_recent_failed_runs`, `get_run_env`,
  `resolve_picklist_value`, `search_api_examples`, `synthesize_http_step`, …
- The LLM never writes FSR JSON — it writes YAML and trusts the compiler
- Same tools work from Claude Code, IDE plugins, or the in-browser web app
- LLM-agnostic by construction: structured I/O, externalized prompt, token-budget discipline

## Slide 10 — The success ladder

- One gate isn't enough. Five rungs, each a deterministic check, each an MCP tool:
  - **L1 Compile** — structurally valid YAML
  - **L2 Static-resolve** — connectors / ops / picklists / step-types / Jinja vars all exist
  - **L3 Dry-run** — step args render against expected upstream context
  - **L4 Live single-step** — step N actually executes on real FSR
  - **L5 Post-run assert** — playbook produced the asked-for outcome
- Failure at any rung = structured `{ok, error_code, message, suggestions[]}`
- Diagram: success ladder with current status

## Slide 11 — Recipes: from blank page to working playbook

- Recipe generators emit known-good playbooks for common archetypes
- Today: threat-feed ingestion, data ingestion (alerts/incidents)
- Roadmap: enrichment, triage, containment, approval-gated actions, orchestration
- Each recipe ships compile-clean, with TODO notes only where the user must intervene
- Layered ruleset validator enforces archetype-specific rules

## Slide 12 — HTTP virtual-connector — covering the long tail

- FortiSOAR has a generic HTTP connector (10 ops including `http_paginate`)
- We crawled 207,419 API examples across 6,927 third-party products
- New: `search_api_examples` + `synthesize_http_step` deterministically translate a catalog entry → an `http_request` step pre-filled with method / path / auth / params
- Result: the agent can author playbooks for **vendors we don't have a native connector for**, seeded from real API examples — not LLM guesses

## Slide 13 — Live verification loop

- `validate_yaml` catches shape errors before push
- `render_jinja(template, from_pb_execution=<pk>)` resolves Jinja against a real past run
- `run_op` executes one connector op live and caches the observed output shape in SQLite
- `dry_run_playbook` (in build) imports → executes → cleans up on dev FSR
- Failures are evidence — if a demo breaks, that's a real bug to file

## Slide 14 — Demo 1: vague ask → working playbook

- Prompt: "Build me a playbook that looks up an IP on VirusTotal and updates the alert"
- Agent: `find_connector` → `get_op_schema` → emit YAML
- Then: `validate_yaml` → `resolve_yaml` (L2) → `compile_yaml` → `push` → `run` → `assert`
- Total time from prompt to passing run: minutes

## Slide 15 — Demo 2: triage and fix (the killer demo)

- "My playbook is broken. Figure out which one and fix it."
- Agent: `list_recent_failed_runs` → `get_run_env(<pk>)` → spots `.records` vs `.data`
- Pulls YAML, edits, validates, diffs, pushes, re-runs, watches it pass
- **None of this loop is possible from the FSR Playbook Designer**

## Slide 16 — What we've indexed: FortiSOAR knowledge

- 714 connectors · 6,773 operations · 26,093 op parameters
- 43 step types · 172 Jinja filters · 1,664 live playbooks
- Trust ladder: 1,959 rows confirmed live + tested
- Big-number grid layout — every number is a real row in a queryable index, refreshed from the live appliance
- Punch line: *the agent does SQL lookups before it touches an LLM*

## Slide 17 — What we've indexed: third-party APIs

- 6,927 products covered · 207,419 API examples · 6,272 lifecycle records
- Standouts: 33,783 entries for Microsoft Graph; 13,818 for GitHub v3 REST
- FTS5-indexed for sub-millisecond search
- `search_api_examples` + `synthesize_http_step` turn any of these into a working `http_request` step — deterministically, no LLM in the translation
- Dashboard: this same data is live at `/inventory` in the web app

## Slide 18 — What's already shipped

- 714 connectors / 6,773 ops / 1,664 playbooks indexed in SQLite
- Compiler v1: parser → resolver → validator → emitter (round-trip lossless)
- 20+ MCP tools, live-tested against a real FSR appliance
- E2E runner: 11/11 fixtures green; 4 LLM-driven storyboards in `DEMO.md`
- Recipe generators (feed-ingest + data-ingest) + layered ruleset validator
- HTTP virtual-connector tools wired (`search_api_examples`, `synthesize_http_step`)
- Inventory surface (`fsrpb inventory`) — answers "what does the assistant know?"

## Slide 19 — What's next (the roadmap)

- L2 prechecks (picklist resolvability, connector installation)
- `resolve_yaml` + variable-reachability ruleset (highest-ROI single check we don't have)
- `dry_run_playbook` MCP tool (L3) — interactive stepper
- `assert_playbook_outcome` MCP tool (L5) — declarative success checks
- LLM evaluation harness — proves "any LLM works" with measurements
- Recipe expansion: enrichment, triage, containment, HTTP virtual-connector recipes
- Inventory web dashboard + transcript capture for demo replay

## Slide 20 — Takeaways

- Authoring surface ≠ execution engine — keep them separate, win on both
- An agent + a queryable spec + a deterministic compiler + a success ladder beats a visual designer for power users
- YAML in git is the unfair advantage: review, audit, promote, roll back
- The HTTP virtual-connector + 207K API examples means thousands of vendors are reachable today, no new connector code required
- Q&A
