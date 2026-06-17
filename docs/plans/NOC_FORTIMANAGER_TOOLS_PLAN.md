# NOC / FortiManager + FortiAnalyzer agent tools — plan

**Status:** Phases A + B + C DONE 2026-06-10. **LIVE DEPLOYED + VERIFIED
2026-06-10b** on 10.99.249.205 (connector-fsr-soc-assistant **0.4.7**,
openai/gpt-4o-mini). `fsr_playbooks` **380 passed**. Authored 2026-06-10.

## Live deploy + drive — DONE 2026-06-10b
Box 10.99.249.205 (`csadmin/fortinet`). FMG `fortinet-fortimanager-json-rpc`
1.2.6 configured (default config `evoke`, real FMG: 33 devices / 13 in root
ADOM); FAZ `fortinet-fortianalyzer` 3.4.0 (default `faz`). Deploy:
`FSR_ENV=<box-env-file> scripts/deploy.sh --bump patch --with-config --model
gpt-4o-mini` — the box-env file (FSR_BASE_URL/creds + OPENAI_*/FSR_LLM_PROVIDER)
overrides the forticloud default `.env`, since deploy.sh sources `$FSR_ENV`
*after* inline vars.

Live-verified vs the real FMG (0 tool failures): device-down (*"Branch2 stopped
reporting"* → device_list → device_status → policy_package_status → accurate
down/out-of-sync diagnosis) and fleet sweep (full 13-device root-ADOM list,
model devices tagged not flagged as outages). No HA pair on the box (all
standalone) → failover money-shot not demoable.

### 4 bugs the live drive exposed (all fixed in canonical `fsr_playbooks`)
1. **FMG response shape.** `_fmg_rows` only knew `result[].data`/`samples`, but
   the `fortinet-fortimanager-json-rpc` connector nests rows under
   `get_response`. The sim fixture `_fmg_jsonrpc` *lied* (emitted `result[].data`)
   so offline passed while live returned 0 rows. Fixed `dig()` + the sim now
   mirrors the real `{data:{get_response:[…]}}` shape.
2. **`run_op` over-summarization.** `_summarize_op_output`→`_truncate_generic`
   keeps only the first 40 dict keys + first 5 list items. FMG device objects
   bury `name`/`sn`/`ip` past key 40 → those fields vanished and a 13-device
   list capped to 5. Added `summarize=False` to `run_op` (guard at **both** the
   agent-path AND direct-path call sites — the direct site was the live path and
   was missed on the first pass), and the NOC wrappers project `data.fields` at
   the FMG query (small payload, keeps name/ip).
3. **Agent-wrap fired for a LOCAL connector.** `_agent_config_ids` treated any
   config visible under a remote tenant agent as agent-bound, but a tenant
   `connector_details?agent=…` query echoes the master's shared configs. The
   wrap reads a PERSISTED workflow step that FSR caps → truncation. Fixed:
   subtract `_local_config_ids` (master-local configs use direct execute). The
   force-fail-playbook wrap is only for connectors reachable ONLY via a remote
   agent.
4. **`unknown` conn_status ≠ `down`.** Model devices (FMG `flags: is_model`,
   never deployed) were reported as outages. `_fmg_conn_state` keeps `unknown`
   distinct; the digest tags `is_model`; the NOC prompt fragment tells the agent
   a model device isn't an outage.

Open: commit (all uncommitted); widget on the box still points at the old
connector name (UI not re-verified live).

## Phase C — shipped (widget repo: widgets-src/fsrSocAssistant)
- Fixture `widget/widgetAssets/fixtures/noc_device_down.json`: full device-down
  hunt transcript (get_record → fmg_get_device_status → fmg_get_ha_status →
  faz_search_device_events → faz_event_summary → fmg_get_policy_package_status →
  warning info_card diagnosis), `end_turn`, NO action card (root cause =
  upstream/power → field dispatch). Auto-served by the mock connector at
  `?mock=noc_device_down`.
- jest: 3 targeted tests added to `tests/render.pipeline.test.js` (FMG/FAZ chips
  completed, warning info_card with WAN1 timeline, no action_card) — plus the
  existing every-fixture replay now covers the new fixture.
- e2e: `tests/e2e/fsrSocAssistant.nocDeviceDown.spec.js` — drives the mock,
  asserts the tool chips + diagnosis card DOM. PASS.
- Sim-incident side (live-mode-but-simulated drive) was delivered in Phase A via
  `_sim_fixtures` (FMG json_rpc_get + FAZ bulk-logs); no separate `_noc_incident`
  helper needed for the demo.
- NOTE: the widget jest target also surfaces 3 PRE-EXISTING failures in
  `contract.completeness.test.js` (missing
  `FSR_PLAYBOOK_BUILDER_CONNECTOR_CONTRACT.md` after the repo reorg) — unrelated
  to this work.

## Phase B — shipped
- `triage_sources.py`: new `fortimanager` source (device-centric:
  `fmg_get_device_status` + `device_extra` HA/policy/FAZ pivots) + a `device`
  move on the `fortianalyzer` source; FMG aliases; `_moves_for_source` now emits
  device pivots (device name normalizes into `indicators.hosts` via `deviceName`).
- `triage_scenarios.py`: new `device_down` scenario — keyword/source matcher,
  device-routed recipes (`_device_down_recipes`), NOC-troubleshooting fragment
  (confirm reachability → HA → corroborate in FAZ → rule out bad push →
  recommend, never auto-remediate), `ti_targets=[]`.
- Hunt loop itself needs no new infra: pivot tools are in agent hands and
  `resume()→stream()` chains them, bounded by the `hunt_depth` lever.
- Tests: `fsr_playbooks/tests/test_noc_triage_routing.py` (7) — routing, scenario
  classification, entity-filled recipes, no security-alert misclassification.
- Remaining for B (optional): live drive validation against real/sim FMG+FAZ.


## Phase A — shipped
- New module `fsr_playbooks/mcp_server/tools_noc.py` (7 tools, all **tier 1**):
  - FMG (all via `json_rpc_get`, portable across connector variants):
    `fmg_get_device_list`, `fmg_get_device_status`, `fmg_get_ha_status`,
    `fmg_get_policy_package_status`. Connector const `_FMG_CONNECTOR =
    "fortinet-fortimanager"` (override in one place if the box runs a different
    build — the `_dev` variant has rich named ops but all variants expose
    `json_rpc_get`).
  - FAZ device hunt (reuses `tools_triage` `_faz_run`/`_faz_window`/digests):
    `faz_search_device_events`, `faz_search_by_serial`, `faz_event_summary`.
- Registered: `__init__.py` import+re-export+`__all__`; `tools.py` `SAFE_TOOLS`
  + `TOOL_TIERS` (=1).
- Sim fixtures in `_sim_fixtures.py`: FGT-BRANCH-04 down-since-03:14 story —
  `_fmg_json_rpc_get` (branches on url: device list/single/ha_slave/pkg status),
  `_faz_device_logs` (WAN1 link-down → tunnel-down → last keepalive). Added
  `fortinet-fortimanager`/`fortinet-fortianalyzer` to `_ROSTER`. HA peer up +
  clean policy install ⇒ diagnosis points at upstream/power, not a bad push.
- Tests: `fsr_playbooks/tests/test_noc_tools.py` (10) — contract/digest/tier/round-trip.
  `make verify` green: 370 fsr_playbooks + 163 connector.
- **Resolved open Q1:** FMG named-op connector is `fortinet-fortimanager_dev`
  (`get_devices`, `get_adom_policy_package`, `reinstall_policy`); the json-rpc /
  utils variants only expose `json_rpc_*`. Phase A uses `json_rpc_get` for
  portability; a future live-mutation tool (Phase B+) can target the named
  `reinstall_policy` op behind the tier-3 card.

**Goal:** Let the SOC Assistant act as a NOC copilot — given a device-failure
alert, talk to **FortiManager** (device posture) and **FortiAnalyzer** (event
hunting) via the agent toolset, pivot/hunt intelligently, diagnose, and propose
(not auto-run) remediation. Demo-safe offline; real when the connectors are wired.

## Decisions (locked with the user)
- **Fidelity: dual-mode.** Tools wrap `run_op` against `fortinet-fortimanager` /
  `fortinet-fortianalyzer`: live when configured, deterministic `_sim_fixtures`
  otherwise. Same pattern as the existing `siem_*` tools.
- **Scenario: FortiGate offline / device down.** Seeded alert: managed FortiGate
  `FGT-BRANCH-04` stopped reporting to FortiManager.
- **Action safety: read-only diagnostics first.** Ship tier-1 read tools now; any
  mutating action (policy re-install, device reboot) goes through the existing
  tier-3 approval card later.
- **User add-on:** searching **FAZ for device-failure events** + an **intelligent
  iterative hunt** (try new angles, pivot) is the headline value — model on the
  SIEM hunt/pivot machinery, don't rebuild it.

## Demo story (FortiGate offline)
1. NOC alert fires ("FGT-BRANCH-04 stopped reporting").
2. Agent recognizes a FortiManager-sourced device-down record (new
   `triage_sources.py` branch) → pivots into FMG: status, device list, HA status.
3. Hunts FAZ for corroborating events (last syslog before silence, WAN1 link-down,
   failed tunnel).
4. Iterates angles when thin (widen window / HA peer / search by serial) — bounded
   by the `hunt_depth` lever.
5. Diagnoses (unreachable since 03:14, preceded by WAN1 down → upstream/power, not a
   bad config push) and emits a findings card. Any fix = tier-3 approval card.
All offline on fixtures for the demo; against real FMG/FAZ when configured — same code.

## Architecture map (what already exists vs new)
| Need | Existing mechanism | New |
|---|---|---|
| Call FMG/FAZ | `run_op` → `/api/integration/execute/` | thin named tool wrappers |
| Offline demo | `_sim_client` + `_sim_fixtures` keyed by `(connector,op)` | FMG+FAZ fixtures + NOC incident |
| LLM picks tools reliably | `SAFE_TOOLS`+`TOOL_TIERS`+auto-schema in `fsr_playbooks/llm/tools.py` | ~6–8 entries + tiers |
| "Hunt / try new things" | `fsr_playbooks/llm/triage_sources.py` source→pivot map; `hunt_depth` lever; `resume()`→`stream()` loop | a `fortimanager`/`fortianalyzer` source entry w/ pre-filled pivots |
| Mutations gated | tier-3 `pending_approval` → approval card | assign tier 3 to future remediation tool |
| Widget rendering | tool_call chips (incl. new duration timers), activity trail, cards | nothing |

Tools resolve via `getattr(mcp_server, name)` (`fsr_playbooks/llm/tools.py::_resolve`);
implement in a tools module, export from `fsr_playbooks/mcp_server/__init__.py`, register
in `SAFE_TOOLS`+`TOOL_TIERS`. Template: `siem_search_host` in
`fsr_playbooks/mcp_server/tools_triage.py`.

## Tool surface (Phase A — read-only, dual-mode)
New module `fsr_playbooks/mcp_server/tools_noc.py`:
- **FMG:** `fmg_get_device_status(device)`, `fmg_get_device_list(adom?)`,
  `fmg_get_ha_status(device)`, `fmg_get_policy_package_status(device)`
- **FAZ (event hunt, submit→poll like FortiSIEM):**
  `faz_search_device_events(device, window="6h", limit=25)`,
  `faz_search_by_serial(serial, window, limit)`, `faz_event_summary(device, window)`
Each ~30–50 lines: build run_op call, shape/truncate into a compact digest (reuse
SIEM digest helpers), `echo` params for the activity trail. All **tier 1**.

## Intelligent hunt loop (Phase B) — wiring, not new infra
1. Add `fortimanager`/`fortianalyzer` branch to `triage_sources.py` → pre-filled
   pivots for a device-down record.
2. Pivot tools already in agent hands (`get_record`, `search_module_records`, new
   `faz_*`/`fmg_*`); `resume()` chains status→events→peer→summary.
3. Bound with the `hunt_depth` lever.
4. Add a short NOC-troubleshooting system-prompt section (alongside security triage):
   confirm reachability → corroborate in FAZ → network/power vs config-push →
   recommend, don't auto-remediate.

## Seeded NOC alert (Phase C)
- Widget fixture `noc_device_down.json` (mock transcript; same shape as
  `c2_hunt.json`) → renders offline with no backend.
- Sim incident fixture `_sim_fixtures._noc_incident()` + `(fortinet-fortimanager,
  get_device_status)`-style execute fixtures → live-mode-but-simulated drive works
  end to end.
- Optional: real seeded Incident on the forticloud box (like the C2 wendy.smith chain).

## Effort
- **A** 6–8 read-only tools + fixtures + tiers + unit tests — ~1 session (each tool a `siem_*` clone).
- **B** source-pivot entry + NOC prompt + hunt-loop validation — ~½–1 session.
- **C** widget fixture + sim incident (+1 if wiring real FMG/FAZ) — ~½ session.
Hard parts: believable FMG/FAZ fixture payloads (pull real response schemas first);
tuning the NOC prompt + pivots; confirming real connector op names/params when live.
Not hard: the plumbing (registration, tiering, dispatch, approval-gating, widget
render, hunt/pivot loop) — all proven by the SIEM side.

## Testing (definition of done)
- fsr_playbooks unit: each tool digest shape + sim round-trip; tier=1; NOC source-pivot map.
- connector offline suite: `_event_to_wire`/transcript for a NOC turn; `make verify` green.
- widget jest: NOC fixture transcript render via `render.pipeline`.
- widget e2e: `fsrSocAssistant.nocDeviceDown.spec.js` (mock=noc_device_down) asserts FMG/FAZ chips + diagnosis card.
- live eval (optional): `demo_hunt` task drives device-down in sim mode; assert FMG→FAZ pivot.

## Open questions before Phase A
1. Exact `fortinet-fortimanager` / `fortinet-fortianalyzer` op names + param shapes
   (FAZ has a submit→poll log-search flow like FortiSIEM). Pull from connector
   metadata / FORTISOAR_RESOURCES_INDEX.md.
2. Will FAZ be wired live eventually, or demo-only? (drives fixture fidelity)
3. Multi-ADOM FMG? → optional `adom` param on tools.

## Pointers
- Tool registry/tiers/dispatch: `fsr_playbooks/llm/tools.py`. Tool impls/exports:
  `fsr_playbooks/mcp_server/tools_*.py` + `__init__.py`. Sim layer:
  `fsr_playbooks/mcp_server/_sim_client.py` + `_sim_fixtures.py`.
- Hunt/pivot intelligence: `fsr_playbooks/llm/triage_sources.py`,
  `triage_normalize.py`, `triage_preflight.py`; `hunt_depth` lever.
- Widget render already handles tool chips/activity/cards (+ per-tool duration
  timers added 2026-06-10).
