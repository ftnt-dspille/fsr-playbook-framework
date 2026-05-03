# fsrpb Demo Guide

Four scripted demo scenarios showing the agentic playbook-authoring loop
against a real FortiSOAR instance. Each is a **live LLM session** — the
agent uses the MCP tools (`fsrpb mcp`), the `fsrpb` CLI, and live FSR API
calls. There is no rigging, no canned outputs, no hand-staged data.
What the LLM produces is what it produces. What FSR returns is what FSR
returns.

If a demo fails, that's evidence of a real bug — file it.

---

## Prerequisites

- `.env` configured for a non-prod instance (default `dev` =
  `https://10.99.249.205`). `FSR_ALLOW_E2E=true`.
- Configured connectors (verified 2026-05-03 on dev):
  `virustotal`, `fortigate-firewall`, `cyops_utilities`, `slack`,
  `servicenow`, `splunk`, `mitre-attack`, `openai`, `hello-world`. Run
  `fsrpb health` to confirm.
- MCP server registered: `.claude/settings.json` already wires `fsrpb`
  over stdio. Restart Claude Code if it isn't picking up tool changes.
- A separate browser open to `https://10.99.249.205` showing the
  Playbooks list — the demo's wow moment is watching collections appear
  there in real time as the agent works.

---

## Demo A — Authoring from a vague ask

**Showcases**: connector discovery, op-schema lookup, fixture authoring,
push, run, verify — all from a one-line natural-language prompt.

**You say**:

> Build me a playbook that takes an IP, looks it up on VirusTotal, and
> tells me whether it's malicious or clean.

**Expected agent moves**:

1. `find_connector("virustotal")` → confirms `virustotal v3.2.1` is
   configured.
2. `find_operation("virustotal", "ip")` → finds `query_ip`.
3. `get_op_schema("virustotal", "query_ip")` → confirms the `ip` param
   and the response shape (`data.attributes.last_analysis_stats.malicious`).
4. Authors a YAML playbook: `start → connector(query_ip) → set_variable
   (extract malicious_count) → decision → stamp verdict`.
5. `validate_yaml(text)` → no errors.
6. `compile_yaml(text)` → fsr JSON.
7. Writes a sidecar `.test.yaml` asserting `verdict: clean` for `8.8.8.8`.
8. Hands the user a single command to run end-to-end.

**You run**:

```bash
fsrpb e2e run examples/demo_virustotal_ip.test.yaml
```

**Pass criteria**:

- `status: finished` in 2–4s.
- `Query_VirusTotal.result` contains real VT response fields
  (`attributes`, `last_analysis_stats`, etc).
- `Stamp_clean.status: finished`, `Stamp_malicious.status: skipped`.
- `vars.verdict: clean`.

**Variant**: ask the agent to swap to a known-malicious IP and re-run.
Only the `.test.yaml`'s `input.ip` and `expects.vars.verdict` change —
the playbook itself is the same.

---

## Demo B — Iterating on a broken draft

**Showcases**: structured diagnostics, "did you mean" suggestions, live
Jinja rendering, the validate-before-push loop.

**You say** (paste imperfect YAML — typos, wrong refs, vague Jinja):

```yaml
collection: My Demo
playbooks:
  - name: My Playbook
    parameters: [ip]
    steps:
      - id: start
        type: start
        next: lookup
      - id: lookup
        type: connector
        arguments:
          connector: virustotl                # typo
          operation: get_ip_reputation        # wrong op name
          params:
            address: "{{ vars.input.params.ip }}"   # wrong param name
        next: check
      - id: check
        type: decision
        arguments:
          conditions:
            - option: bad
              condition: "{{ vars.steps.lookup.records[0].malicious }}"  # wrong field path
        branches:
          bad: alert
```

> Can you fix this for me?

**Expected agent moves**:

1. `validate_yaml(text)` returns structured errors with `did you mean`
   suggestions: `virustotal`, `query_ip`, `ip`.
2. `find_operation("virustotal", "ip")` → confirms canonical op.
3. `get_op_schema("virustotal", "query_ip")` → param is `ip`, output
   path is `data.attributes.last_analysis_stats.malicious`.
4. Optionally `render_jinja('{{ vars.steps.Query_VirusTotal.data.attributes.last_analysis_stats.malicious }}', from_pb_execution=<a past run>)`
   to confirm the path resolves before committing.
5. Patches all four issues, validates clean, hands the user the fixed
   YAML.

**Pass criteria**: every error is fixable from validator output alone —
the agent does not have to guess. If the agent has to ask the user for
field names that should be in `get_op_schema`, that's a reference-store
gap.

---

## Demo C — Triage and fix a broken playbook

**Showcases**: live failure-listing, run-env introspection, pull/edit/diff/push
loop. The killer demo — none of this is possible from the FSR Playbook
Designer.

There are two equally-real entry paths. Use whichever matches reality on
the target instance.

### C-1: Continuation from Demo A or B

The agent built a playbook earlier in the session that genuinely doesn't
work — most often a `vars.steps.<step>.records` vs `.data` confusion, a
`int` vs `str` Jinja comparison, or a connector op called with a
required param missing. **You do not stage the bug** — the LLM made the
mistake itself and the run failed.

### C-2: Inherited broken YAML

You hand the agent a hand-written-by-someone-else YAML that you compiled
and pushed earlier (whichever pre-existing `examples/*.yaml` actually
fails on this instance, or any genuinely-broken playbook already on
`dev`).

### Either way

**You say**:

> My playbook is broken. Can you figure out which one and fix it?

**Expected agent moves**:

1. `list_recent_failed_runs()` → recent failed runs across the instance,
   newest first, with playbook name and pk.
2. Picks the most recent failure.
3. `get_run_env(pb_execution=<pk>)` → rebuilds the `{vars: {…env, steps:
   {Step_Name: result}}}` Jinja context from the failed run. Inspects
   what was actually in `steps.<failing_step>.result`.
4. Compares against what the next step's Jinja expression *expected* to
   find. The shape mismatch (e.g. `.records` vs `.data`) is now obvious.
5. `fsrpb pull "<playbook name>"` → fetches the live YAML.
6. Edits the YAML to fix the shape mismatch.
7. `validate_yaml` → clean. `fsrpb diff` → narrates the change to the
   user.
8. `fsrpb push --mode replace` → idempotent re-deploy.
9. `fsrpb run-playbook "<name>" --follow` → re-trigger; watches it pass.

**Pass criteria**: agent never asks the user "which playbook?" — the
triage tool answers that. The fix is grounded in real run-env data, not
guesses. Final run reaches `finished`.

---

## Demo D — Reverse-engineer an existing playbook

**Showcases**: `pull`, `decompile`, `search_playbooks`, the corpus-mined
Jinja idioms, plain-English summarization.

**You say** (point at any non-trivial live playbook):

> What does the "<Playbook Name>" playbook actually do?

**Expected agent moves**:

1. `fsrpb pull "<name>"` → live collection as YAML.
2. Walks the steps in order, narrates trigger → branches → side effects
   in plain English.
3. For unfamiliar Jinja idioms in the playbook, calls `find_jinja_pattern`
   to see how the same idiom is used elsewhere in the corpus (1,669
   playbooks).
4. For each connector call, `get_op_schema` so the narrative includes
   which API the playbook hits and what it does there.
5. Flags anything that looks brittle — undefined Jinja paths, missing
   error handling, deprecated connector versions — based on what the
   reference store knows.

**Pass criteria**: agent's summary aligns with what the playbook actually
does on read-through. No hallucinated steps. Cross-references back to
canvas step names (`vars.steps.<Underscored_Name>`) using the rule
documented in `AUTHORING.md`.

---

## Conventions used in fixtures

These show up across the demos and shape what the agent should produce.

### `type: stop` / `type: end`

When a decision branch should do nothing, write
`type: stop` (or `end`) — the compiler emits the canonical `cyops_utilities.no_op`
("Utils: No Operation") connector call. Don't dangle a branch and don't
fill with a no-op `set_variable`.

### Decision steps need both branches in `conditions:`

The implicit-else shorthand (only one entry in `conditions:`, two in
`branches:`) is supported but explicit is clearer. The compiler will
synthesize a `default: true` entry for any branch in `branches:` that's
not in `conditions:`.

### Trigger payload for parameterized playbooks

Parameter values ride in `request.data` of the `/notrigger` body, NOT
`input.params`. FSR maps `request.data.<k>` → `vars.input.params.<k>`
at runtime. The e2e runner handles this — when writing a `.test.yaml`,
just put values directly under `input:`.

### `vars.steps.<key>` keys off display name, not id

`vars.steps.Query_VirusTotal.data.…` — that's the step's `name:` with
spaces→underscores, case preserved. NOT the YAML `id:`, NOT the UUID.

---

## Running the demos

```bash
# Pure-logic smoke test (no external APIs)
fsrpb e2e run examples/demo_pure_logic.test.yaml

# Demo A backbone — real VT API call
fsrpb e2e run examples/demo_virustotal_ip.test.yaml

# Demo C triage prereq — list recent failures
fsrpb runs                # default: failed only
fsrpb runs --all          # include successes
fsrpb runs --json         # machine-readable

# Cleanup leftover demo collections
fsrpb e2e cleanup
```

Logs land in `store/e2e_runs/<run_id>/` (compiled.json, run.log,
final_record.json, plus push_error.txt or compile_errors.json on failure).

---

## Other scenarios (parking lot)

These weren't picked for the headline four but each showcases a distinct
power. Promote any of them when the demo audience changes.

| # | Scenario | What it shows |
|---|----------|--------------|
| 5 | **SOP → playbook** — paste a written runbook doc, agent translates it to YAML | NL-to-structured-automation translation |
| 6 | **Data-driven authoring** — agent inspects a real alert record before authoring, builds a playbook around its actual shape | Avoids the `.records` vs `.data` class of bug at author time |
| 7 | **Live env introspection** — agent uses `get_run_env` + `render_jinja(from_pb_execution=…)` to interactively probe a past run's data shape before writing the next step | The unique inspection loop |
| 8 | **Compare environments** — pull a playbook from dev and from a backup, semantic diff, narrate the drift | Cross-environment audit |
| 9 | **Extract sub-playbook** — agent spots a duplicated branch across two playbooks, extracts to a child via `workflow_reference`, updates both callers | Multi-playbook editing |
| 10 | **Migrate connector version** — "this calls VT v1, migrate to v2" — diff `get_op_schema` for both, rewrite params, validate, push | Connector-version migration |
| 11 | **Connector exploration** — "what can I do with FortiGate?" → agent uses `find_operation` + `get_op_schema` + `run_op` to live-test before authoring | Live experimentation, not just spec-reading |
| 12 | **Audit sweep** — "find any playbook on dev that uses a deprecated jinja filter / has no error handling / hardcodes a credential" | Bulk-read across the corpus |
| 13 | **Author + regression-test together** — agent writes the playbook *and* its `.test.yaml` so it can be re-verified after future edits | The e2e runner as a CI primitive |
