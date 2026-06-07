# Continue: Dynamic triage (scenario-aware prompts + first-class SIEM tools)

_Last updated: 2026-06-02. Pick up here._

## Goal
Make the triage agent reliably pivot into the originating SIEM and ground its
verdict in real evidence, by:
1. **Normalizing** any alert/case into one canonical shape (indicators, MITRE,
   embedded driving events) — so alerts and sparse cases look the same.
2. **Classifying** the record into a scenario (e.g. C2/exfil) and injecting a
   **dynamic prompt**: a grounded "what we know" block + scenario-specific
   known-good moves (entities pre-filled) + a verdict checklist.
3. **First-class SIEM tools** so the agent reliably runs SIEM queries instead of
   dodging the fiddly raw `search_events`.

Root problem this fixes (diagnosed live): the static prompt made a small model
pivot into FortiSIEM inconsistently (SIEM calls went 1→0→2 across identical
runs), and `get_record` truncated the embedded `associated_events` (the 6.8 GB
exfil evidence) before the model saw it — so it narrated evidence it never read.

## Status: DONE (all tested, 154 fsr_core tests green)
All in `fsr-playbook-framework` (canonical fsr_core — NOT yet re-vendored to connector).

| Layer | File | Tests |
|---|---|---|
| 0 Normalizer | `fsr_core/llm/triage_normalize.py` | `test_triage_normalize.py` (11) |
| 1 Scenario registry + classifier | `fsr_core/llm/triage_scenarios.py` | `test_triage_scenarios.py` (5) |
| 2 Dynamic prompt builder | `fsr_core/llm/triage_prompt.py` | `test_triage_prompt.py` (5) |
| First-class SIEM tools | `fsr_core/mcp_server/tools_triage.py` (`siem_search_ip/host/user`, `siem_events_for_incident`, `siem_raw_query`) | `test_siem_search_tools.py` (9) |

Registration for the SIEM tools is in 3 places (mirror this pattern for any new
tool): `fsr_core/mcp_server/__init__.py` (import + `__all__`), and
`fsr_core/llm/tools.py` (`SAFE_TOOLS` + `TOOL_TIERS=1`).

Also: softened the over-strong "you MUST pivot to SIEM" mandate in
`fsr_core/agent/system_prompt_triage.md` to a lighter nudge (the dynamic builder
now injects scenario moves, so the blanket mandate was redundant + unreliable).

Run tests: `./.venv/bin/python -m pytest fsr_core/tests/ -q` (needs the .venv).

## Build the C2 prompt to see it
```python
from fsr_core.llm.triage_prompt import build_triage_prompt
import json, pathlib
raw = json.loads(pathlib.Path("fsr_core/tests/fixtures/triage/alert_c2_exfil.json").read_text())
print(build_triage_prompt(raw)["system"])
```
The injected blocks ground the agent: source/severity/MITRE, IPs tagged
internal/EXTERNAL, host, the embedded exfil events (out 1.9GB/in 4.5GB →
Nigeria), then scenario opening moves with `incident_id`/host/IP pre-filled, then
the verdict checklist.

## WHAT'S LEFT
1. ~~**#4 Wire pre-flight into demo_hunt + connector.**~~ **DONE.** New shared
   helper `fsr_core/llm/triage_preflight.py` (`triage_preflight(target|raw_record,
   emit=)`) does the FULL raw fetch (needs embedded `associated_events`, which
   the pruned `get_record` drops) → `build_triage_prompt` → emits
   `normalize`/`classify`/`ground` activity events. Tests:
   `fsr_core/tests/test_triage_preflight.py` (5). Wired into:
   - `python/demo_hunt.py` — preflights `--record`, prints the activity trail +
     scenario, uses the dynamic `system`.
   - connector `operations.py` `_resolve_system_prompt(intent, entity, storage,
     session_id, turn_idx)` (called after `turn_start`) — triage with a
     resolvable entity preflights via `entity.iri`/`module:uuid` and streams
     `activity` frames into the poll feed. Falls back to the static prompt for
     `build`/no-entity/fetch-failure. Tests in `tests/test_chat_operations.py`
     (`_triage_lookup_key`, `_resolve_system_prompt` ×3). 141 connector tests
     green. NOTE: connector sees canonical fsr_core via the `fsr_core` symlink,
     so this works pre-re-vendor; packaging still needs the re-vendor (#4 below).
2. ~~**#7 Emit backend activity events to widget chat.**~~ **DONE (widget half).**
   Added an `activity` transcript event (contract **bumped 2.7.0 → 2.8.0** in
   the MD + widget `WIDGET_CONTRACT_VERSION` + connector `CONTRACT_VERSION`).
   - Renderer: `fsrPbRender.js` coalesces a consecutive run of `activity` frames
     into one `{type:'activity', lines:[{phase,message}]}` timeline event (drops
     empty). Template: `view.html` renders `.pb-activity` bulleted lines + CSS;
     excluded from the catch-all default block.
   - Tests: `render.pipeline.test.js` (3 new), `contract.completeness.test.js`
     (added `activity` to EVENT_CASES + documented in contract §5 so the guard
     stays honest). 256 jest tests green. **e2e green**: `rendering.spec.js`
     info_cards test now asserts `.pb-activity` (3 coalesced lines + text).
   - Widget NOT version-bumped — source stays 1.0.49; the bump (info.json +
     version-derived controller names) is done atomically at ship time by
     `widget.js push --bump patch` / `scripts/ship.sh <id> --bump patch`. DO NOT
     hand-edit info.json: it desyncs the `…1049DevCtrl` registrations and the
     harness controller-mismatch lint blocks bootstrap → all e2e fail at `idle`.
   - STILL TODO for #7: emit `activity` frames around the SIEM tool calls
     themselves (siem_search_*), not just pre-flight. The tool-call path is in
     `fsr_core/llm/run_turn.py`; consider emitting from the tool wrappers.
3. **#5 Validate**: investigation eval fixtures `python/evals/tasks/25–29_*`
   (required_facts/tool_budget) to measure variance reduction objectively, then
   2–3 live `demo_hunt` runs (C2 alert + one other seeded alert).
4. **Re-vendor to connector** when ready: `cd fsr-playbook-framework && scripts/build.sh`,
   bump connector info.json + scripts/install_to_fsr.py. See memory
   `fsr_connector_vendoring`. Until then changes are live in `demo_hunt`
   (canonical fsr_core) but NOT on the box's connector.
5. **Add more scenarios** beyond `c2_exfil` + `generic` (malware-unremediated,
   mail-egress, intrusion, defense-evasion — map to eval fixtures 25–29). Add a
   dict to `SCENARIOS` in `triage_scenarios.py`; nothing else changes.

## KEY TECHNICAL LEARNINGS (FortiSIEM connector — hard-won, verify before relying)
Connector source: `/Users/dylanspille/Downloads/fortinet-fortisiem`
(`operations.py`, `utils.py`, `connections.py`). The SOAR FortiSIEM connector
has **THREE separate query subsystems** — do not interchange their query-ids:
- **`get_associated_events_new`** → `/rest/pub/incident/triggeringEvents/start|progress|result`
  (JSON, incident-scoped). **This WORKS live.** Params: `incident_id`,
  optional `timeFrom`/`timeTo`, `perPage`. ← reliable pivot for driving events.
- **`search_events` / `run_report`** → `get_event_query` builds an **XML**
  payload, POST `/rest/query/eventQuery` (Content-Type text/xml). This is the
  subsystem that **500s ("Internal Server Error") on this box** for src/dst IP
  filters. `siem_search_ip/host/user` wrap this — they're correct usage but
  inherit the box's XML-engine instability.
- **pub/v2 JSON** `/rest/pub/v2/query/{eventQuery,progress,events/results}` —
  `siem_raw_query` (the escape hatch) uses this via `execute_api_request`. It
  returned a queryId live once, but the engine is **intermittently 500-ing**
  (submit fails most of the time). Not yet seen end-to-end live.

Other verified facts:
- **base_url = `config.server` + `/phoenix`** (`connections.py:17`). So
  `execute_api_request` endpoints are relative to `/phoenix` → use
  `/rest/pub/v2/...` NOT `/phoenix/rest/...` (the latter 404s — double /phoenix).
- **`execute_api_request` needs `confirm=True`** (category investigation but
  risk 'unknown' → run_op gates it). It's read-only for queries.
- **FortiSOC scope: drop `exclude`** from `customerScope`; use
  `{groupByEachCustomer:true, include:{all:true}}`.
- **Time format**: `timeFrom`/`timeTo` must match `%Y-%m-%dT%H:%M:%S.%fZ` —
  i.e. **fractional seconds required** (e.g. `2026-06-02T13:40:01.0101Z`).
  Without the `.%f` it errors. `siem_events_for_incident` should coerce this
  (TODO: it currently passes through verbatim — add a normalizer).
- **fsr_core output summarizer wraps event lists** as
  `{"_digest":"event_list","count":N,"samples":[...],"facets":{...}}` — events
  are under **`samples`** (not `rows`/`events`). `_event_rows` now checks it.
- **Incident id caveat**: the FortiSIEM live incident id (e.g. `11544`) can
  differ from / outlive the `incident_data.incidentId` embedded in an old
  alert's sourcedata (our C2 alert's `10868` is now "Invalid Incident Id").
  So for old alerts, rely on the **embedded `associated_events`** (normalizer
  already surfaces them) rather than a live triggeringEvents call.
- Native FSM REST also reachable directly at
  `https://mfz9dldmc5b7hllc2rs-fsm.us-west-1.fortisoc.forticloud.com`
  (Basic auth `super/collector_reg` or `super/admin`, pw `FSMworkshop25!`) —
  used only to validate grammar; **production path is run_op**, do NOT ship the
  direct-FSM creds. Working native `where` uses `reptDevIpAddr="…"`; `srcIpAddr`
  OR-filters 500. Backend attribute names (Admin → Device Support → Event
  Attributes), e.g. display "Destination TCP/UDP Port" → `destIpPort`.

## ENVIRONMENT CAVEATS
- Both the SOAR box and its FortiSIEM are **intermittently overloaded** all
  session (auth 502/504s, query 500s; "works once then fails"). Likely a
  concurrent-query limit — `siem_raw_query` should DELETE its queryId after
  fetch (TODO) to avoid exhausting the pool. User is checking FSM-side
  (query worker health / retention / max concurrent queries).
- `git status` shows `fsr_core/mcp_server/tools_execution.py` modified with a
  `config=` kwarg added to `record_run_op` calls — **this is NOT from this work**
  (likely the other agent's connector branch). Leave it / review separately.

## Demo anchor
Seeded C2 chain: `wendy.smith` / `smithDesktop` / `10.50.60.70` →
`102.220.160.21` (Nigeria), `7ogger.exe`, T1041. Alert
`alerts:d39ecc9a-2968-42d5-948d-ce96fd76b227` (FortiSIEM incident 10868, May 29).
Live runner: `./.venv/bin/python python/demo_hunt.py --record alerts:<uuid>`.
Fixtures captured: `fsr_core/tests/fixtures/triage/{alert_c2_exfil,incident_smithdesktop}.json`.
Helper scripts (delete when done): `python/_poll_then_hunt.py`,
`python/_poll_raw_query.py`.
