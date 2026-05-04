# Agentic Playbook Building — Presentation Outline

Working title: **Playbooks Without the Designer — An Agent-First Path to FortiSOAR Automation**

Audience: SOAR engineers, automation leads, and stakeholders who already know FortiSOAR but have not seen agent-driven authoring.
Length target: ~15 slides, 20-minute talk.

---

## Slide 1 — Title

- **Agentic Playbook Building for FortiSOAR**
- Subtitle: Why authoring should be a YAML + LLM loop, not a drag-and-drop canvas
- Presenter / date

## Slide 2 — The pain we keep hitting

- Playbook Designer is click-heavy, opaque, and not diff-able
- Iteration loop is slow: edit → save → run → squint at run-log → repeat
- Field-shape bugs (`.records` vs `.data`, Jinja typos) only surface at runtime
- No version control, no PR review, no portability between environments
- Talented automation engineers spend their day clicking, not designing

## Slide 3 — Why now: agents are good enough

- Frontier LLMs handle structured authoring well *if* given the right tools
- Agents need: a queryable spec of the platform, a deterministic compiler, fast feedback
- We do **not** need to fine-tune — tool use plus good cheatsheets is sufficient
- The bottleneck has moved from "can the model write YAML" to "can it verify what it wrote"

## Slide 4 — The core idea

- One simplified YAML IR. Three authoring surfaces (CLI, agent-via-MCP, future visual editor)
- All three compile through the same pipeline to native FSR `WorkflowCollection` JSON
- FortiSOAR stays the execution engine — we never replace it, we just author *into* it
- Insert the ARCHITECTURE.md ASCII diagram as a graphic

## Slide 5 — Why YAML is the right IR

- Human-readable, diff-able, review-able in a PR
- Trivially round-trippable: pull from FSR → YAML → edit → push
- Easy for an LLM to emit and reason about
- No vendor JSON ceremony (UUIDs, port coordinates, layout metadata) leaks into authoring

## Slide 6 — Why benefits stack up

- **Speed**: a vague natural-language ask becomes a tested playbook in minutes
- **Correctness**: validator with structured errors + "did you mean…" before push
- **Portability**: YAML lives in git; promote dev → prod as a normal merge
- **Auditability**: every change is a commit, every playbook is a file
- **Reverse-engineering**: `pull` + `decompile` makes any existing playbook readable

## Slide 7 — Design choice 1: SQLite-first reference store

- Every connector, op, parameter, step type, Jinja filter, module field lives in `fsr_reference.db`
- FTS-indexed; one SQL query per agent question
- Probes refresh it from the live appliance — compiler stays stable while the world changes
- Trust ladder (`live_*`, `tested_pass` → `is_trusted=1`) keeps unverified data flagged

## Slide 8 — Design choice 2: Library-first compiler

- `parser → resolver → validator → emitter`
- Compiler is a Python library; CLI, MCP server, and TS widget are thin wrappers
- **Errors are data, not strings** — every diagnostic has a code, line/col, and suggested fix
- Same IR + same compiler across all surfaces = output is interoperable

## Slide 9 — Design choice 3: MCP as the agent contract

- MCP server exposes 16 tools: `find_connector`, `get_op_schema`, `validate_yaml`, `compile`, `dry_run_playbook`, `render_jinja`, `list_recent_failed_runs`, `get_run_env`, …
- The LLM never writes FSR JSON directly — it writes YAML and trusts the compiler
- The same tools work from Claude Code, IDE plugins, or a future in-FSR widget

## Slide 10 — Design choice 4: Live verification loop

- `validate_yaml` catches shape errors before push
- `render_jinja(template, from_pb_execution=<pk>)` resolves Jinja against a real past run
- `dry_run_playbook` imports + executes + cleans up on a test instance
- Failures are evidence — if a demo breaks, that's a real bug to file

## Slide 11 — How it works end-to-end

- Diagram: agent → MCP tool calls → reference store + compiler + live FSR → tested JSON
- Walk through one demo: "Build me a playbook that looks up an IP on VirusTotal"
  - `find_connector` → `get_op_schema` → emit YAML → `validate_yaml` → `compile` → `push` → `run`
- Total time from prompt to passing run: minutes

## Slide 12 — The killer demo: triage and fix

- "My playbook is broken. Figure out which one and fix it."
- Agent: `list_recent_failed_runs` → `get_run_env(<pk>)` → spots `.records` vs `.data` mismatch
- Pulls YAML, edits, validates, diffs, pushes, re-runs, watches it pass
- **None of this loop is possible from the FSR Playbook Designer**

## Slide 13 — What's already shipped

- 714 connectors indexed, 1,669 playbooks corpus-mined
- Compiler v1: parser → resolver → validator → emitter (round-trip lossless)
- MCP server with 16 tools, live-tested against a real FSR appliance
- E2E runner: import, execute, poll, cleanup
- Pull / decompile / diff / push all working

## Slide 14 — What's next

- Visual editor surface (consumes the same IR)
- TS compiler port for an in-FSR widget
- Expanded demo coverage: SOP → playbook, cross-env diff, sub-playbook extraction
- Continue feeding pyfsr enhancements upstream rather than hand-rolling HTTP

## Slide 15 — Takeaways

- Authoring surface ≠ execution engine — keep them separate, win on both
- An agent + a queryable spec + a deterministic compiler beats a visual designer for power users
- YAML in git is the unfair advantage: review, audit, promote, roll back
- Q&A
