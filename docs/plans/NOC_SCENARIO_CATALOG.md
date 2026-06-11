# NOC scenario catalog + reproduction pipeline

Status: design + build plan. Companion to `NOC_FORTIMANAGER_TOOLS_PLAN.md`
(the agent-side tools) — this doc owns the **scenarios** (what realistic NOC
alerts look like) and the **reproduction** (how to make each one happen on
demand so the SOC Assistant triages real data).

Decision (2026-06-10): the Fabric Studio FGTs are managed by the **same FMG/FAZ
the SOC Assistant queries** (10.99.249.205), so we reproduce faults **for real**
— induce on the device → FMG/FAZ reflect it → seed the matching Alert in
FortiSOAR → open the SOC Assistant on it. Offline sim fixtures stay as the
no-pod fallback (CI + `?mock=` widget demos), derived from the same manifest so
they never drift.

---

## The pipeline

```
 noc_scenarios manifest (one source of truth)
        │
        ├──► FS fault recipe  (induce)  ──► real FGT state change ──► FMG/FAZ reflect it ──┐
        │         ▲ revert recipe restores clean state                                     │
        │                                                                                  ▼
        ├──► alert seeder  ──────────────────────────────► Alert record in FortiSOAR ──► SOC Assistant
        │                                                   (printed IRI + widget deep-link)   triages
        │                                                                                  ▲
        └──► sim fixture + widget ?mock ──────────────────────────────────────────────────┘
                    (no-pod fallback: CI, render tests, screenshots)
```

Real-induce and sim share the **same manifest entry**, so a scenario is defined
once and every consumer (FS recipe, alert content, sim fixture, widget mock)
derives from it.

### Substrate that already exists (do not rebuild)

- **Induce/revert mechanism** — `fabric_studio_fixer/backend/seed_checks/scenarios.yaml`
  is a declarative `setup → wait → probe → assertions` recipe format pushed over
  SSH-jump to a device's mgmt IP. The `Check` model already carries
  `setup`/`teardown`, so a fault recipe is `setup:` = induce, `teardown:` = revert.
  Today the recipes are *provisioning* checks (set hostname/DNS/IP); our NOC
  faults are the same shape with destructive `setup` + restoring `teardown`.
- **Link/power levers** — `fabric_studio_fixer/backend/engine/fs_admin.py`:
  `set_port_link(dev, port, up=False)` does a runtime **cable break** (link-down,
  cable kept) and `up=True` repairs it; `power_off_device`/`power_on_device`;
  `set_vm_parameters` (cpu/memory, applies on reinstall). Verified live.
- **Agent tools** — `fsr_core/mcp_server/tools_noc.py`
  (`fmg_get_device_list/_status/_ha_status/_policy_package_status`,
  `faz_search_device_events/_by_serial/_event_summary`) already read FMG/FAZ.
- **Scenario classifier** — `fsr_core/llm/triage_scenarios.py` routes an Alert to
  a scenario (`device_down`, `c2_exfil`, `generic`) and injects guidance. New NOC
  scenarios are added here (one dict each), mirroring `device_down`.
- **Sim fixtures** — `fsr_core/mcp_server/_sim_fixtures.py` serves canned FMG/FAZ
  data when the connector's `simulation_mode` is on. Currently one hardcoded
  device-down story; needs to become a **scenario registry** keyed so multiple
  stories coexist.

---

## Scenario catalog

Each scenario reproduces a distinct, realistic NOC alert. "Induce (real)" is the
FS/CLI lever; "FMG/FAZ shows" is what the agent's tools will actually return;
"Alert" is the seeded record's gist (title/description/device drive the
classifier).

### 1. Managed device down / not reporting  *(EXISTS — baseline)*
- **Induce:** `set_port_link(mgmt_port, up=False)` (cable break) or shut all uplinks.
- **Revert:** `set_port_link(..., up=True)`.
- **FMG/FAZ:** `conn_status=down`; FAZ shows the last logs before silence (WAN/link-down).
- **Alert:** "FGT-BRANCH-04 stopped reporting to FortiManager."
- **Classifier:** `device_down` (already implemented).

### 2. HA failover
- **Induce:** on an HA pair, `power_off_device(primary)` or break the primary's
  heartbeat + uplinks; secondary takes master.
- **Revert:** `power_on_device(primary)`; HA re-syncs (verify with `fmg_get_ha_status`).
- **FMG/FAZ:** primary down / secondary = master; FAZ HA-failover log.
- **Alert:** "HA cluster CL-EDGE failed over — primary unreachable."
- **Classifier:** new `ha_failover` (verdict: graceful failover vs split-brain;
  did traffic survive?).

### 3. SD-WAN / WAN member degradation
- **Induce (CLI):** `config system interface; edit wan1; set status down; end`
  (or degrade an SD-WAN member / inject loss so it breaches SLA).
- **Revert:** `set status up`.
- **FMG/FAZ:** device up but a WAN member down / out-of-SLA; FAZ link-monitor + SLA logs.
- **Alert:** "SD-WAN member wan1 on FGT-BRANCH-02 breached SLA / went down."
- **Classifier:** new `wan_degraded` (which member, since when, was traffic steered off it?).

### 4. VPN tunnel down  ← **first vertical slice**
- **Induce (CLI):** disable phase1 — `config vpn ipsec phase1-interface;
  edit HQ-BRANCH04; set status disable; end` (or shut the WAN carrying it).
- **Revert:** `set status enable`.
- **FMG/FAZ:** FAZ IPsec phase2-down / tunnel-down events; branch isolated.
- **Alert:** "Site-to-site VPN HQ↔BRANCH04 is down — branch isolated."
- **Classifier:** new `vpn_tunnel_down` (phase1 vs phase2, peer reachable?,
  renegotiation failing?, blast radius = which subnets lost).

### 5. Bad policy push / config drift
- **Induce:** device-side edit that diverges from the FMG-managed config (so FMG
  reads `conf_status=outofsync`), timed near a recent push.
- **Revert:** re-sync from FMG (or `teardown` restores the managed value).
- **FMG/FAZ:** `conf_status=outofsync`; last policy-package install timestamp lines up.
- **Alert:** "FGT-BRANCH-03 out-of-sync after policy install — connectivity impact."
- **Classifier:** new `config_drift` (was the push the cause? recommend re-install vs revert).

### 6. High CPU / conserve-mode
- **Induce (CLI):** session/CPU stressor, or lower the conserve-mode memory
  threshold to force entry.
- **Revert:** stop the stressor / restore the threshold.
- **FMG/FAZ:** FAZ cpu/mem/conserve-mode logs climbing.
- **Alert:** "FGT-HQ entered conserve mode — high memory utilization."
- **Classifier:** new `resource_exhaustion` (traffic spike vs attack vs leak).

### 7. FortiGuard / license degradation
- **Induce (CLI):** point FortiGuard at a bad override-server / disable default
  servers so IPS/AV updates fail (or let a contract lapse in the lab).
- **Revert:** restore the FortiGuard config.
- **FMG/FAZ:** FAZ fortiguard update-failure logs; stale signature versions.
- **Alert:** "FGT-HQ FortiGuard updates failing — security services degraded."
- **Classifier:** new `fortiguard_degraded` (which service, since when, exposure window).

---

## Manifest shape (single source of truth)

Proposed `noc_scenarios.json` (lives where both halves can read it; the FS side
gets a `scenarios.yaml` recipe generated from / kept in sync with it):

```jsonc
{
  "vpn_tunnel_down": {
    "device": "FGT-BRANCH-04",
    "alert": {
      "title": "Site-to-site VPN HQ↔BRANCH04 is down — branch isolated",
      "description": "FortiAnalyzer reported repeated IPsec phase2-down events for tunnel HQ-BRANCH04 ...",
      "severity": "High",
      "fields": { "source": "FortiAnalyzer", "type": "Network/VPN" }
    },
    "induce": {                       // FS fault recipe (setup)
      "capability": "cli",
      "setup":   ["config vpn ipsec phase1-interface", "edit HQ-BRANCH04", "set status disable", "end"],
      "teardown":["config vpn ipsec phase1-interface", "edit HQ-BRANCH04", "set status enable",  "end"]
    },
    "fmg_rows":  [ /* device row the sim returns when no pod */ ],
    "faz_logs":  [ /* phase2-down events the sim returns */ ],
    "policy_status": null
  }
  // ... one entry per scenario
}
```

`alert` → seeder + widget mock. `induce` → FS recipe. `fmg_rows`/`faz_logs` →
sim fixture. `device` ties the agent's tool calls to the right story.

---

## Build plan

**Vertical slice first (scenario 4, VPN tunnel down)** — prove the whole pipeline
end-to-end before replicating:

1. ✅ **Manifest** — `fsr_core/mcp_server/noc_scenarios.json` + loader
   `_noc_scenarios.py` (`load`/`scenarios`/`by_device`) with the
   `vpn_tunnel_down` entry (alert + induce/teardown + fmg_row + faz_logs).
2. ✅ **Classifier** — `vpn_tunnel_down` scenario in `triage_scenarios.py`
   (matches "tunnel down"/"vpn"/"ipsec"/"phase2"; recipes confirm device-up
   first then read vpn logs; fragment + verdict checklist). Tests added.
3. ✅ **Sim** — `_sim_fixtures.py` appends each manifest device to the FMG device
   list (reachable) and serves the scenario's `faz_logs` keyed on the queried
   `devid`; BRANCH-04 device-down path untouched. Tests added.
   → `fsr_core` **387 passed** (offline slice complete + green).
4. ⏳ **Alert seeder** — `seed_noc_alert.py --scenario vpn_tunnel_down` (FSR side):
   POST an Alert from the manifest, print IRI + widget deep-link. (Connector repo
   `scripts/`, alongside `prompt_loop.py`.) BLOCKED on alert-module confirmation.
5. ⏳ **FS recipe** — add the induce/teardown recipe to
   `fabric_studio_fixer/.../scenarios.yaml` (or generate from the manifest).
   BLOCKED on FS device name/mgmt-IP/jump-host.
6. ⏳ **Widget mock** — generate `noc_vpn_tunnel_down.json` for `?mock=`; render test.
7. ⏳ **Live drive** — induce on the FS FGT, seed the alert, open the SOC Assistant
   on 10.99.249.205, confirm the agent diagnoses a real phase2-down tunnel; revert.

NOTE: the manifest's `device` is `FGT-BRANCH-07` (a NEW device, distinct from the
device-down baseline's `FGT-BRANCH-04`) so the two stories don't collide in the
device-keyed sim. Swap to the real FS device name when wiring the live drive.

**Then replicate** scenarios 2, 3, 5, 6, 7 from the same manifest shape.

### Open questions for the slice
- Exact FS device name + mgmt IP + jump host for the target FGT (and an HA pair
  for scenario 2).
- Whether to generate the FS `scenarios.yaml` recipe from `noc_scenarios.json`
  or hand-keep both (generation avoids drift but couples the repos).
- Alert module: `alerts` vs `incidents` on this box (plural-modules note in
  `forticloud_demo_scenario` memory) — confirm before the seeder hardcodes a path.
