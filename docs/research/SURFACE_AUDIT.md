# Surface-area audit (Phase 0)

Input for `VERIFY_PLAYBOOK_PLAN.md` Phases 1 + 5. Every MCP tool,
backend route, system-prompt directive, and `fsrpb` CLI verb is listed
once with a decision. The keep-criterion is binary: an item earns its
place iff it serves the agent loop **or** the web app (editor / chat /
history). CLI-only usage is not sufficient.

Legend
- **Agent**: `Y` = referenced in `python/agent/system_prompt.md` (count
  in parens) OR ever called in `chat_messages.kind='tool_use'` in
  `web/backend/history.db`. `n` = never.
- **Editor**: `Y` = direct fetch from `web/frontend/src/**` (non-test).
- **CLI**: `Y` = exposed as an `fsrpb` subparser in `python/cli.py`.
- **Decision**: `keep` / `wire` / `delete` (per plan §Phase 0). `wire`
  items become Phase 5 tickets. `delete` items become Phase 1 removals.

Deletion direction (clarified)

MCP tools are agent capabilities. An MCP tool that the agent doesn't
*currently* call but could plausibly use in the verify loop is **wire**
(teach the system prompt to call it), not **delete**. Only MCP tools
that are strictly redundant with another tool — same call, same return
shape — are deletion candidates.

App features (frontend components, backend routes that aren't called
by the frontend, system-prompt directives) are the deletion target.
An unused backend route is dead code; an unwired MCP tool is latent
capability.

Counts at a glance

- MCP tools: 51 — keep-as-is 25, wire-into-agent-loop 26, delete 0.
  (`resolve_yaml` and `generate_recipe` were flagged as strict
  duplicates but each has active CLI + evals/tests callers, so they
  aren't dead. They stay; both become Phase 3 wire-into-agent-loop
  candidates.)
- Backend routes: ~53 — keep 48, delete 5 (dead routes with no
  frontend caller).
- `fsrpb` CLI verbs: ~50 — all keep.
- System-prompt directives: kept; Phase 3 adds the `verify_playbook`
  rule.

---

## 1. MCP tools (`python/mcp_server/tools_*.py`)

Agent usage was measured two ways: (a) tokens in
`python/agent/system_prompt.md`, (b) historical tool_use rows in
`web/backend/history.db` (`chat_messages` table). Editor usage was
measured by grepping `web/frontend/src/**` (excluding `*.test.*`) for
`callMcpTool('<name>'` and direct `/api/mcp/<name>` fetches.

| # | Tool | Agent | Editor | CLI | Decision | Notes |
|---|---|---|---|---|---|---|
| 1 | `search_playbooks` | Y(1) | n | Y | **keep** | Agent corpus search. |
| 2 | `review_chat_session` | n | n | Y | **wire** | Agent-side self-review tool. Add to system prompt for agent retrospection on its own session, or remove. |
| 3 | `review_recent_thumbs_down` | n | n | n | **wire** | Same — agent retrospection. Useful pre-task: "what have I gotten wrong recently?" |
| 4 | `find_step_examples` | n | n | n | **wire** | Add to system prompt for the drafter. |
| 5 | `find_step_recipe` | Y(1) | n | Y | **keep** | |
| 6 | `search_api_examples` | n | n | Y | **wire** | Useful when agent is building HTTP-shaped connector_ops. |
| 7 | `validate_yaml` | Y(6, 26×) | Y | Y | **keep** | Primary gate today; demoted to a sub-step of `verify_playbook` in Phase 3. |
| 8 | `resolve_yaml` | n | n | n | **delete (redundant)** | Strict internal step of `compile_yaml` — calling it standalone returns a subset of `compile_yaml`'s output. Pure duplication. |
| 9 | `compile_yaml` | Y(1, 1×) | Y | Y | **keep** | First gate of `verify_playbook`. |
| 10 | `step_through_playbook` | n | n | n | **wire** | Plan §Phase 5 step debugger panel + agent debugging loop. |
| 11 | `analyze_playbook` | Y(5) | Y | Y | **keep** | |
| 12 | `suggest_fix_for_diagnostic` | Y(1) | Y | n | **keep** | |
| 13 | `step_test` | n | Y | n | **keep** | |
| 14 | `precheck_connector_installed` | n | n | Y | **wire** | Internal call inside `verify_playbook` fan-out. |
| 15 | `synthesize_http_step` | n | n | n | **wire** | Drafter helper; agent can use it when given a curl example. |
| 16 | `find_connector` | Y(2, 1×) | Y | Y | **keep** | |
| 17 | `find_operation` | Y(4, 8×) | Y | Y | **keep** | |
| 18 | `get_op_schema` | Y(2, 7×) | Y | n | **keep** | |
| 19 | `get_connector_icon` | n | Y | n | **keep** | |
| 20 | `list_connector_configurations` | n | Y | n | **keep** | |
| 21 | `get_connector_source` | n | n | Y | **wire** | Agent fallback when `get_op_schema` is incomplete — read the actual `operations.py`. |
| 22 | `get_step_type` | Y(3, 2×) | n | n | **keep** | |
| 23 | `find_operation_example` | n | Y | n | **keep** | |
| 24 | `find_jinja_filter` | Y(1) | n | n | **wire** | Inspector Jinja help bundle (Phase 5). |
| 25 | `find_jinja_pattern` | Y(1) | n | n | **wire** | Same. |
| 26 | `get_filter_examples` | Y(1) | n | n | **wire** | Same. |
| 27 | `render_jinja` | n | Y | Y | **keep** | |
| 28 | `find_jinja_example` | n | Y | n | **keep** | |
| 29 | `list_picklists` | n | n | Y | **wire** | Agent discovery: "what picklists exist for this module?" |
| 30 | `get_picklist` | n | n | Y | **wire** | Agent: enumerate valid values before authoring. |
| 31 | `picklist_for_field` | Y(1) | n | Y | **keep** | |
| 32 | `resolve_picklist_value` | Y(1) | n | Y | **keep** | |
| 33 | `precheck_picklist_value` | n | Y | n | **keep** | Plan calls this in the verify fan-out. |
| 34 | `run_op` | n | Y | Y | **keep** | `verify_playbook` live-probe depends on this. |
| 35 | `push_playbook` | n | n | Y | **wire** | Teach agent to push end-to-end via MCP. |
| 36 | `run_playbook` | n | n | Y | **wire** | Agent post-push smoke run. |
| 37 | `dry_run_playbook` | n | n | n | **wire** | Plan §Non-goals keeps it as the interactive debugging tool; wire the agent to use it when verify has degraded-to-warning shapes. |
| 38 | `healthcheck_connector` | n | n | Y | **wire** | Agent diagnostic when `run_op` fails inexplicably. |
| 39 | `assert_playbook_outcome` | Y(1) | n | n | **wire** | Land in `verify_playbook` fan-out. |
| 40 | `generate_recipe` | n | n | Y | **delete (redundant)** | Strictly authoring/dev tool — generates a recipe row from an existing playbook. Distinct from `find_step_recipe`/`find_recipe` (lookup). Move the logic into a CLI-only helper; remove `@mcp.tool()`. |
| 41 | `find_recipe` | n | n | Y | **wire** | Agent recipe lookup (read path). Not redundant with `find_step_recipe` — different scoping. |
| 42 | `diagnose_yaml_against_pb_execution` | n | n | n | **wire** | Agent post-mortem when a pushed playbook fails live. |
| 43 | `why_did_playbook_fail` | n | n | n | **wire** | Phase 5 history panel + agent reach-back. |
| 44 | `get_run_env` | n | n | Y | **wire** | Agent needs to inspect a past run's vars when diagnosing. Frontend already gets this through `/api/run/{id}/env`. |
| 45 | `list_configured_connectors` | n | n | Y | **wire** | Agent pre-flight: confirm the connector is configured before authoring. |
| 46 | `list_tags` | n | n | n | **wire** | Useful for agent when authoring tag-bearing steps; otherwise low priority. |
| 47 | `list_recent_failed_runs` | n | n | Y | **wire** | Phase 5 failed-runs panel + agent triage. |
| 48 | `list_playbook_runs` | n | n | Y | **wire** | Same. |
| 49 | `verification_status` | n | Y | n | **keep** | |
| 50 | `test_find_record` | n | Y | n | **keep** | |
| 51 | `search_module_records` | n | Y | n | **keep** | |

**Phase 1 MCP deletions** (0): none. `resolve_yaml` and
`generate_recipe` have active CLI/evals/tests callers and are not
dead code. Both move to the wire-into-agent-loop list below.

**System-prompt wire-up tickets** (agent loop, lands with Phase 3):
`review_chat_session`, `review_recent_thumbs_down`,
`find_step_examples`, `search_api_examples`,
`precheck_connector_installed`, `synthesize_http_step`,
`get_connector_source`, `list_picklists`, `get_picklist`,
`push_playbook`, `run_playbook`, `dry_run_playbook`,
`healthcheck_connector`, `assert_playbook_outcome`,
`diagnose_yaml_against_pb_execution`, `why_did_playbook_fail`,
`get_run_env`, `list_configured_connectors`, `list_tags`,
`list_recent_failed_runs`, `list_playbook_runs`, `find_recipe`.

**Editor surface tickets** (Phase 5):
`step_through_playbook` (debugger panel), `find_jinja_filter` +
`find_jinja_pattern` + `get_filter_examples` (Jinja help in
inspector), `why_did_playbook_fail` (history panel),
`list_recent_failed_runs` (failed-runs surface),
`precheck_connector_installed` (canvas badge).

---

## 2. Backend routes (`web/backend/routes/`)

Editor column is non-test `web/frontend/src/**` grep.

| Route | Editor | Decision | Notes |
|---|---|---|---|
| `GET /api/chat` POST | Y | keep | Chat panel. |
| `GET /api/examples`, `GET /api/examples/{name}` | Y | keep | Examples picker. |
| `/api/health` | Y | keep | |
| `GET/POST/DELETE /api/history/sessions/...` | Y | keep | History view. |
| `POST /api/history/sessions/{id}/feedback` | Y | keep | Thumbs UI. |
| `GET /api/history/feedback` | n | **delete** | No editor caller; CLI uses `chat-stats` against DB directly. |
| `GET /api/history/pushes`, `/pushes/{id}` | n | **delete** | Unused. |
| `GET /api/history/timeline` | n | **delete** | Unused. |
| `/api/llm/providers/...`, `/api/llm/active` | Y | keep | Settings panel. |
| `POST /api/mcp/{tool_name}` | Y | keep | Generic MCP bridge. Will surface 13 fewer tools after Phase 1. |
| `GET /api/mcp/_tools` | Y? | keep | Tool list for dev panels. |
| `GET /api/playbooks*`, drafts, revisions, from-example | Y | keep | Editor file mgmt. |
| `POST /api/playbook/push` | Y | keep | Push button. |
| `POST /api/playbook/run` | Y | keep | Run button. |
| `GET /api/run/{pk}/env` | Y | keep | (See MCP tool #44 — eventually reroute through `get_run_env`.) |
| `GET /api/ref/*` (all 13 endpoints) | Y | keep | Inspector + drafter. |
| `GET /api/visual/list`, `/file`, `POST /api/visual/`, `/write`, `/write_file`, `/draft-step` | Y | keep | Visual editor. |
| `POST /api/yaml/validate`, `/compile` | Y | keep | |
| `POST /api/yaml/fixes` | n | **delete** | No editor caller; `suggest_fix_for_diagnostic` MCP is the live path. |

**Phase 1 backend deletions** (5 routes across 2 files):
`history.feedback`, `history.pushes`, `history.pushes/{id}`,
`history.timeline`, `yaml.fixes`.

---

## 3. CLI verbs (`python/cli.py`)

CLI is a first-class ops surface. **All keep**, but a few notes:

- Verbs whose backing MCP tool gets deleted in Phase 1
  (`review-chat-session`, `inventory api-examples`, `picklists list`,
  `picklists show`, `health`, `recipes generate`/`find`, `runs`) must
  be rewired to call store helpers directly. The CLI dropping its
  in-process MCP shim removes one layer; behavior is unchanged.
- `fsrpb mcp` (stdio MCP server boot) is unaffected.
- `fsrpb refresh` gets a new sub-step in Phase 1 to populate the
  `op_safety` table via `probe_op_safety`.

No CLI deletions.

---

## 4. System-prompt directives (`python/agent/system_prompt.md`)

Tool-name references and their disposition:

| Mentioned tool | After Phase 1? | Action |
|---|---|---|
| `validate_yaml` (6×) | exists | keep; demote behind `verify_playbook` |
| `analyze_playbook` (5×) | exists | keep |
| `find_operation` (4×) | exists | keep |
| `get_step_type` (3×) | exists | keep |
| `find_connector` (2×) | exists | keep |
| `get_op_schema` (2×) | exists | keep |
| `compile_yaml` (1×) | exists | keep; demote behind `verify_playbook` |
| `find_step_recipe` (1×) | exists | keep |
| `search_playbooks` (1×) | exists | keep |
| `suggest_fix_for_diagnostic` (1×) | exists | keep |
| `picklist_for_field` (1×) | exists | keep |
| `resolve_picklist_value` (1×) | exists | keep |
| `find_jinja_filter` (1×) | exists (wired Phase 5) | keep |
| `find_jinja_pattern` (1×) | exists (wired Phase 5) | keep |
| `get_filter_examples` (1×) | exists (wired Phase 5) | keep |
| `assert_playbook_outcome` (1×) | exists (wired Phase 5) | keep |

No system-prompt entry references a Phase-1-deleted tool. The Phase 3
system-prompt update adds the `verify_playbook` rule.

---

## 5. Risks / out-of-scope

- **Plugin auth and connector ops** live in `python/connector_configs.py`
  and aren't in this audit; they're consumed by `run_op` and are not a
  surface item per se.
- **`store/schema.sql`** has the `operations`, `playbooks`, `connectors`,
  etc. tables; not a surface but Phase 1 adds `op_safety` there.
- **Eval suites** (`python/evals/`) are not user-facing surfaces and
  aren't audited here; Phase 4 modifies them in place.
- Frequency counts in `history.db` are local-dev only; production
  usage may differ. The decisions still hold because a tool with zero
  references in *any* of the four lookups (system prompt, history,
  frontend, MCP-routed editor) is by definition unused.

---

## 6. Phase 1 work order (consequence of this audit)

App-side dead-code removal:

1. Delete 5 backend routes (`history.feedback`, `history.pushes`,
   `history.pushes/{id}`, `history.timeline`, `yaml.fixes`).
2. Sweep frontend for any component/import that referenced those
   routes (the grep above shows none, but confirm during the patch).

Verify-feature foundation:

3. Add `op_safety` table to `store/schema.sql`; land
   `python/probes/probe_op_safety.py`.
4. Update `fsrpb refresh` to call the new probe.

Phase 3 picks up the system-prompt wire-up tickets so the agent
actually exercises the latent tools. Phase 5 picks up the editor
surface tickets.
