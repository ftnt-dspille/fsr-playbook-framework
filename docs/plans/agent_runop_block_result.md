# Plan: Agent-routed `run_op` with live "running on agent" UX

**Status:** Phases A, B, C DONE offline (2026-05-31, `make verify` green). Resume = Phase D (live verify + deploy).

## Progress log (2026-05-31)
- **Phase A — DONE.** `priority` is now resolver-driven, NOT a baked constant.
  Store's `picklists` table (listName `WorkflowPriority`, synced live by
  `probe_modules.py`) is the source of truth. `ir.Playbook.priority` (name) +
  `priority_iri` (resolver-filled); `parser` captures the name and **defaults
  to "High"** when unset (optional field); `resolver._resolve_priority` looks up
  the IRI + warns on unknown name; `emitter` emits `priority_iri`; `decompiler`
  reverse-maps IRI→name from the same table. Tests in test_parser/test_emitter.
- **Phase B — DONE.** `_agent_config_ids()` (cached) + `_run_op_via_agent_playbook()`
  in tools_execution.py; run_op dispatches to the wrap proactively before the
  execute POST when `exec_config ∈ agent ids`. UNWRAPPED push via raw
  `client.session.post` (sidesteps the double-wrap). Disambiguation unit-tested
  offline (test_agent_run_op_wrap.py) with a fake HTTP seam.
- **Phase C — DONE.** `runs_on_agent` surfaced in `list_configured_connectors`
  and `find_containment_actions`; triage system-prompt line tells the agent to
  narrate the ~30-60s delay then call run_op. (find_connector/get_op_schema flag
  deferred — needs live agent detection; the two staging surfaces cover it.)
- **Crudhub verb gap — FIXED.** Root cause of "push broken on the agent box"
  was NOT a double-wrap: `CrudhubLiveClient`/`_CrudhubSession` (the on-platform
  loopback client) only implemented `get`/`post`, so `_push`'s idempotent
  `client.put(...)` AttributeError'd and the agent wrap's `session.put` (debug) /
  `session.delete` (cleanup) had no target. Added `put`+`delete` to both,
  symmetric with the existing shims (test_live_crudhub_verbs.py).
  CAVEAT (needs live verify): crudhub `make_request` raises on non-2xx with an
  unknown exception shape, so `_push`'s 404→POST / 409→purge→POST branch detection
  (`getattr(e.response,'status_code')`) may still not fire on the agent box. The
  agent wrap is unaffected — it does a single fresh unwrapped POST, never the
  PUT-first dance. Confirm push_playbook idempotency on the agent box in Phase D.
- **Still TODO:** Phase D live e2e + re-vendor/deploy + contract harness; verify
  push_playbook/dry_run_playbook idempotency end-to-end on the agent box now that
  put/delete exist.

**Status (orig):** planned, not started (2026-05-31). Tasks #1–#4 created. Resume = Phase A.
**Goal:** when a containment/connector op runs on a FortiSOAR **agent** config, `run_op`
must execute it exactly once AND return the real result to the widget (today it returns
an empty `in-progress` stub and the widget never sees the outcome).

## Background — all live-verified this session (FortiCloud SOAR, fsr-1, 7.6.5-5662)
- Agent-bound configs make `POST /api/integration/execute/` **fire-and-forget**: returns
  `{remote_status:"in-progress", result:{}, action:"execute_action", agent:<id>}`. The op
  DOES run; the result is websocket-pushed (`cyops.crudhub.datanotify`) and the transient
  `ExecuteAction` row is deleted → **not REST-pollable** (`/api/integration/remote-action-execution/{id}/` 404s).
- The Angular UI doesn't poll — it subscribes to the datanotify websocket. The workflow
  engine parks agent steps as `found_awaiting_step` and resumes on the ack.
- A **2-step force-fail playbook** `[connector op] → [set_variable {{ 1/0 }}]` runs the op
  ONCE and makes FSR persist all step results (FSR discards step results on SUCCESS — even
  with `debug:true`; only a FAILED run retains them). Proven: block fired once,
  `Run.result = {data:{newly_blocked:["203.0.113.99"],...}, status:"Success", _status:true}`
  read from `GET /api/wf/api/workflows/{pk}/?step_detail=true`.
- **Push must send the UNWRAPPED collection** (`POST /api/3/workflow_collections` with the
  bare collection dict → 201). The connector's current `_push` double-wraps → server-side
  TypeError (the `push_playbook`/`dry_run_playbook` failure on this box). Compiler already
  supports `config:"<name>"` on a connector step (passes through to step args).
- Streaming exists (widget contract 2.5.1): `chat_turn` writes per-event frames to
  `storage.turn_progress`; `chat_poll` reads by cursor. No spinner/pending card type; tools
  have no handle to the feed (lives in operations.py `_on_event`).

## Decisions (user, 2026-05-31)
- **Spinner = agent-narrated + pending tool_use** (NO new card type, NO contract bump, NO
  widget change). The pending `run_op` tool_use already renders a spinner; the agent narrates
  the delay first.
- **Route ALL agent-bound ops** (reads + writes) through the wrap — reads (get_blocked_ip)
  are also fire-and-forget on agents and return empty today.
- **Playbook priority = High** on the wrap; compiler must support `priority`.
- Detect agent-bound **proactively, before the execute** (never execute-then-wrap → would
  double-fire the action).

## Phase A — Compiler `priority` support  (offline; Task #1)
Files: `fsr_playbooks/compiler/ir.py`, `parser.py`, `emitter.py`, tests.
1. `ir.py` `Playbook`: add `priority: Optional[str] = None`.
2. `parser.py` (~line 682, near `debug=`): read `priority` from `pb_raw`; validate `High|Medium|Low|...`.
3. `emitter.py:411`: replace hardcoded `"priority": None` with name→IRI from a constant map.
   High = `/api/3/picklists/9e8d41e4-8ada-4a2c-bd02-07f62c6d0a00` (listName
   `/api/3/picklist_names/e104ef72-11b4-4d0c-be0e-e1cf3b87b5f2`). Emit as a **bare IRI string**
   (same as `collection`/`triggerStep`). hydra accepts IRI on POST.
4. Tests: priority round-trips; unknown value → compile warning.
- Robustness: system picklist UUIDs are usually stable but not guaranteed cross-instance;
  the Phase B live helper re-resolves High by `listName+itemValue` at push and overrides the
  compiled IRI, so a stale constant can't break it.

## Phase B — Agent detection + force-fail wrap in `run_op`  (Task #2)
File: `fsr_playbooks/mcp_server/tools_execution.py`.
1. `_agent_config_ids(client)` → cached set of agent-bound config UUIDs (from
   `_agent_configured_rows` + `_row_config_ids`), short TTL like `_configured_rows`.
2. In `run_op`, AFTER resolve + risk/confirm gate + preflight, BEFORE the execute POST:
   `if exec_config in _agent_config_ids(client): return _run_op_via_agent_playbook(...)`.
   Raw execute never runs for agent configs.
3. `_run_op_via_agent_playbook(connector, op, params, config_name, client, timeout_s)`:
   - Build 2-step YAML: op step (`config: <name>`, params) → `set_variable boom: "{{ 1/0 }}"`;
     `priority: High`, `debug: true`.
   - compile → **unwrapped** `POST /api/3/workflow_collections` → `PUT /api/3/workflows/{uuid}
     {"debug":true}` + set High priority → `POST /api/triggers/1/notrigger/{uuid}` →
     poll `/api/wf/api/workflows/?task_id=...&parent_wf__isnull=True` until terminal (failed).
   - `GET /api/wf/api/workflows/{pk}/?step_detail=true`; extract connector step `result` by name.
   - Disambiguate: connector step `status==finished` & `result.status=="Success"` ⇒ success →
     return normalized `{ok:true, data: result.data, output_shape, _via_agent:true, _agent_id}`.
     Connector step failed ⇒ real error envelope. IGNORE the intentional Boom failure.
   - `finally`: hard-purge collection (reuse `_hard_purge`). Poll timeout → `{ok:false, status:"agent_timeout"}`.
4. Fix `_push` double-wrap bug (or give the helper a dedicated unwrapped push) — also unblocks
   `push_playbook`/`dry_run_playbook` on this box.

## Phase C — Agent-narrated UX  (Task #3)
Files: discovery tools + system prompt (no contract bump, no widget change).
1. Surface `runs_on_agent: true` (+ agent id) in `find_containment_actions`, `find_connector`,
   `list_configured_connectors`, `get_op_schema` so the agent knows BEFORE calling.
2. System-prompt line: "If `runs_on_agent` is true, tell the user the action runs on a FortiSOAR
   agent and may take ~30–60s, THEN call `run_op`." → agent narrates → pending run_op tool_use
   spins → result streams. `_via_agent`/`_agent_id` in the return lets the agent confirm in its
   result narration.

## Phase D — Verify & deploy  (Task #4)
1. `make verify` (fsr_playbooks + connector offline).
2. Live e2e: agent block via run_op → single execution + spinner frame in chat_poll + result card.
3. Re-vendor fsr_playbooks → connector; bump version + `$replace`; `scripts/deploy.sh`.
4. Contract harness re-capture (`probe_fsr.py` + `tests/fsr_contract.py`).

## Key refs
- Memory: `fsr_agent_proxied_execute_async.md` (the validated recipe + gotchas).
- `run_op` @ `fsr_playbooks/mcp_server/tools_execution.py:1130`; `run_playbook` follow loop ~:1420;
  `_resolve_config_id` :524; `_agent_configured_rows` :176; `_configured_rows` :218; `_row_config_ids` :250.
- Streaming: connector `operations.py` `_on_event` ~:1566; `storage.append_turn_progress` :328;
  contract version const `operations.py:603` (2.5.1).
- `emitter.py:411` priority; `ir.py` Playbook ~:72; `parser.py:682` debug parse.
