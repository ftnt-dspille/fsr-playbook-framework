# Investigation: make trace-built playbooks run on AGENT-bound connectors (fortigate)

**Why this matters:** agent-routed connectors (FortiGate, and most customer
edge/EDR gear reached through a FortiSOAR agent) are central to real
containment. B3 (trace→playbook RUNS live) must work for them, not just for
appliance-local connectors. Today it works for connectors with an
appliance-side config record (fortiedr, virustotal, …) but NOT for fortigate.

## Where we are (2026-06-02, connector 0.3.88 live on FortiCloud id≈207)

The trace→playbook config plumbing is DONE and correct (see memory
`skill_playbook_b3_config_binding`):
- `run_op` resolves `exec_config` at execution time and we now record it onto
  the SkillTrace (`skill_trace.record_run_op(..., config=)` →
  `resolved_inputs["config"]` → step `arguments.config` via
  `skills._compile_run_connector_action`). Verified by test +
  `make verify` (153 fsr_core + 137 connector green).

**The gap:** for `fortigate-firewall`, `exec_config` comes back **`""`**, so the
recorded trace has no config and the compiled step fails at runtime:
`INTEGRATION-12: Could not find a connector configuration matching the given
configuration id or name <empty> — Connector :: fortigate-firewallV5.4.0`.

### Confirmed facts
- `GET /api/integration/connectors/?$limit=400` lists **30 connectors**; **12
  have an appliance-side config record** (smtp, code-snippet, **fortinet-fortiedr**
  `fortisoc-edr` dd2122d0…, virustotal 246b2e51…, servicenow, fortianalyzer,
  fortiguard×2, mitre, cisa, sla, soc-sim). **`fortigate-firewall` is NOT in
  that list** — its `configuration` is `[]` on the unfiltered listing.
- Yet `run_op` on fortigate `block_ip_new` *reports* success and the op appears
  to run — because `/api/integration/execute/` agent-routes it server-side even
  with `config=""`. The **workflow engine does NOT** do this for a playbook
  step, so the step needs a real config id that the listing doesn't expose.
- `_resolve_config_id(_configured_rows(client), "fortigate-firewall", "")`
  returns `""` on the box → trace records `""`.

## RESOLVED (2026-06-02) — both questions answered, fix landed offline

**Q1 — config resolution was never broken code; it was stale box state.**
With the box as it is now (active agent `efe5dafd28b5e41cd4c37e5829ccc638`,
fortigate `config_count=2`, `status=Completed`), the REAL fsr_core path resolves
cleanly — verified live by driving `tools_execution` directly:
- `_configured_rows(client, force=True)` includes `fortigate-firewall`.
- `_row_config_ids(row)` → `['3bd29afa-fb38-4e8d-9c39-68e0f8f8d5d6',
  'd7b6508f-889c-4505-a12f-8d8706ae7985']`.
- `_resolve_config_id(rows, 'fortigate-firewall', '')` → `'3bd29afa-…'` (default).
The earlier `""` was hypothesis #1/#2 from the list below: at that time there was
no active agent / no Completed fortigate config, so `_agent_configured_rows` was
empty. The data source is endpoint **B** (`connector_details?agent={id}` — rows
under the `data` key, which `_agent_configured_rows` already reads). No config-
resolution code change needed.

**Q2 — a working agent-bound step needs exactly ONE extra field: `agent`.**
Decompiled a real hand-authored fortigate step (workflow `fortigate-agent`,
`31deb99a-a4ed-4c21-aa8b-ad3283f72681`):
```json
{ "name": "Fortinet FortiGate", "agent": "efe5dafd28b5e41cd4c37e5829ccc638",
  "config": "3bd29afa-fb38-4e8d-9c39-68e0f8f8d5d6", "params": {...},
  "version": "5.4.0", "connector": "fortigate-firewall",
  "operation": "get_addresses", "pickFromTenant": false,
  "dynamicallySelected": false }
```
Identical to an appliance-local step **plus `"agent": "<agentId>"`**.
`pickFromTenant`/`dynamicallySelected` are the same defaults appliance steps get.

**Fix (landed, `make verify` green = 155 fsr_core + 137 connector):**
- `skill_trace.record_run_op(..., agent="")` records `resolved["agent"]`.
- `tools_execution` agent-playbook path passes `agent=agent_id` to the recorder.
- `skills._compile_run_connector_action` emits `arguments.agent`.
- `connector_args` reserves `agent` so hand-authored steps pass it through.
- Test: `test_recorded_agent_is_emitted_on_connector_step`.

**LIVE PROOF DONE (2026-06-02, connector 0.3.89 id=208):** deployed, then ran
`scripts/_b3_fortigate.py` — steered triage to a safe agent-routed fortigate op
(`get_addresses`, no action_card so the agent ran it directly, still trace-
recorded). The compiled connector step carries BOTH
`config: 3bd29afa-…` AND `agent: efe5dafd28b5e41cd4c37e5829ccc638` — an exact
match to the hand-authored ground-truth step — and `dry_run_playbook`
(`use_mock_output=True`) returned **`status: "finished"`**. Leftover collection
purged. **B3 is done for the agent path.**

**`block_ip_new` conditional-required gap — DONE (compile-time).** Schema is
fully ingested (`operation_params` carries `required` + parent + condition):
`method` → (Policy Based) `ip_type`+`ip_block_policy` → (ip_type=IPv4/IPv6) `ip`;
(Quarantine Based) `ip_addresses`+`time_to_live` → (Custom Time) `duration`. The
run_op preflight (`_shared._validate_op_params`) already enforces this, so the
recorded trace is complete. Added the matching check to the COMPILE path for
hand-authored steps: `NormalizerMixin._check_conditional_required` (+
`CatalogLookupMixin.operation_param_required_rules`), wired after
`_check_param_visibility` in `connector_args`. Walks the gate chain, honors
defaults (method defaults to Quarantine Based) and empty-string parent
sentinels, scoped to conditionally-gated params (top-level required stays the
preflight's job). Test: `fsr_core/tests/test_conditional_required.py` (6 cases).

**Still TODO:** fold the fortigate trace into the parity-eval fixtures.

## OPEN QUESTION 1 — why is the fortigate agent config "not there"?

Agent-bound configs live UNDER THE AGENT, not on the appliance, so the plain
`/api/integration/connectors/` (no agent filter) shows `configuration: []`.
The connector's warmup ALREADY fetches per-agent details (this is the
"warmup handles the agent config ids" hint):
- `fsr_core/mcp_server/tools_execution.py::_agent_configured_rows` →
  `GET /api/3/agents` → per active agent
  `POST /api/integration/connector_details/?agent={id}&active=true&exclude=operation`,
  keeps rows with `config_count>0` + `status=Completed`, stamps `_agent_id`.
- `_configured_rows` merges those into the configured set; `_resolve_config_id`
  reads it.

So if `_resolve_config_id` returned "" for fortigate, ONE of these is true —
**verify each live:**
1. **No active agent**, or `GET /api/3/agents` returns nothing/!active →
   `_agent_configured_rows` is empty. (Memory says config `claude` is
   agent-bound `572b3ecd`; check that agent is active.)
2. fortigate's per-agent row has **`config_count==0`** (installed-but-
   unconfigured on the agent) or **status != Completed** → filtered out.
3. The per-agent `connector_details` row's config UUIDs aren't extracted by
   `_row_config_ids` (shape mismatch: it probes `configs/configurations/
   config/configuration` for str or `{config_id|id|uuid}`). The agent shape may
   differ → returns `[]`.
4. `_resolve_config_id` matches by `connector` name but the per-agent row uses a
   different name/key.

### Commands to run (laptop → box, creds from FSRPlaybookYaml/.env)
```python
# scripts/fsr_live.py LiveFSR gives .base/.headers/.verify
# A) list agents
GET  /api/3/agents                         # agentId, active, name
# B) fortigate under each agent — does a config_id appear here?
POST /api/integration/connector_details/?format=json&agent={aid}&active=true&exclude=operation   body {}
#    -> find name==fortigate-firewall: config_count, configuration[].config_id, agent
# C) the agent-install listing (no agent_id needed)
POST /api/integration/connectors/agents/fortigate-firewall/5.4.0/?format=json&active=true   body {}
# D) direct: the agent-scoped connector detail (carries configuration[].config_id + health)
POST /api/integration/connectors/fortigate-firewall/5.4.0/?format=json&agent={aid}   body {}
```
Whichever of B/C/D returns a real `config_id` for fortigate IS the source we
must wire `_resolve_config_id`/`_agent_configured_rows` to. Likely fix: relax
the `config_count>0`/status filter or fix `_row_config_ids` for the agent shape,
so `exec_config` resolves the agent config id → it then auto-flows onto the
trace + step (no further compiler change needed).

## OPEN QUESTION 2 — what does a WORKING agent-bound playbook step look like?

A playbook connector step for an agent-routed connector almost certainly needs
MORE than `arguments.config` — likely an agent/tenant binding
(`pickFromTenant`, an `agent` field, or the config_id itself is agent-scoped).
**Find ground truth by decompiling a real one:**
1. On the box, find an EXISTING playbook that runs a fortigate (or any
   agent-bound) connector step — search `/api/wf/api/workflows/` or the
   collections — and GET its full record; inspect the connector step's
   `arguments` (config, agent, pickFromTenant, version).
2. Reproduce minimally: hand-author a 2-step playbook
   `[start → fortigate block_ip_new]` with the **agent config_id from Q1** (and
   whatever agent/tenant fields the decompiled step had), push + `dry_run_playbook`
   `use_mock_output=True`. Iterate until it reaches `finished`.
   - Use `scripts/_b3_diag.py` shape for push/trigger/poll; fetch the full
     failed record by pk (`/api/wf/api/workflows/{pk}/?format=json`) — the
     dry_run summary's `failed_steps` is always `[]` (list endpoint has no
     steps); the per-step `result["Error message"]` is the real signal.
3. Encode the winning recipe into the compiler:
   - `skills._compile_run_connector_action` already emits `arguments.config`
     from the trace. Add any extra agent/tenant fields there, sourced from the
     trace (record them in `record_run_op` the same way `config` was — run_op
     knows `_agent_id` for agent-routed ops, see `tools_execution.run_op`
     ~line 1579-1589 `agent_ids`/`_agent_id`).
   - Mirror the recipe in the resolver normalizer
     (`connector_args._resolve_connector_args`) so hand-authored agent steps
     work too.

## Then: re-run B3
Re-deploy (`scripts/deploy.sh --bump patch`, FortiCloud), re-run
`scripts/_b3_diag.py` (steer to fortigate block_ip_new) → expect the dry_run to
reach `finished`. Then the harness `offer_playbook_runs` check goes green and
B3 is done for the agent path. Fold the live trace into the parity-eval fixtures.

## Loose ends from this session
- Throwaway diag scripts (gitignored-ish, untracked): connector
  `scripts/_b3_diag.py`, `_b3_fetch.py`. Keep for the investigation.
- UNCOMMITTED: fsr_core changes on `feat/skill-based-playbook`
  (skill_trace.py, tools_execution.py, skills.py, skill_compiler.py,
  connector_args.py + test_build_from_trace.py). Connector
  `feat/action-based-streaming` has its older batch + info.json/release_notes at
  0.3.88.
- B3 also surfaced a SECOND real gap: `block_ip_new` needs `ip_type` (conditional
  required param) — FSR hides `ip` without it. Address after the config path
  runs (param-completeness: record/emit conditional-required params).
