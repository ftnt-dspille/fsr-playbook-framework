# fsr_playbooks ↔ connector reconciliation plan

**Goal:** one copy of the compiler/authoring surface (the public `fsr_playbooks`
package), one copy of triage/investigation (the connector), no drift, and **no
runtime breakage on the SOAR worker.**

Status: drafted 2026-06-18. Supersedes the "destination deferred" hand-wave in
`pyfsr/docs/plans/FOLLOWUPS.md` item 0 and folds in the connector reality found in
`connector-fsr-soc-assistant/operations.py`.

---

## 0. Where things actually are right now (grounded)

| Thing | Location | State |
|-------|----------|-------|
| compiler + authoring (`compiler/*`, `agent/skill_trace`, kept `mcp_server` tools, `llm/*` minus triage) | framework `fsr_playbooks/` on `reorg/phase-0-freeze-surface` | ✅ triage-free (Phase 1, `c040744`) |
| triage cluster (`tools_triage`, `tools_noc`, `triage_*`, `_live_crudhub`, `_noc_scenarios`, `noc_scenarios.json`, `system_prompt_triage.md`) | **deleted** from the library; **only surviving copy** is the connector's vendored `fsr_playbooks/` (+ stale `fsr_core.bak/`) | ⚠️ still inside the `fsr_playbooks.*` namespace |
| public PyPI `fsr-playbooks` 0.3.62–0.3.65 | PyPI | ❌ cut from `main` (pre-reorg) → **carry triage**; to be deleted + republished as triage-free `0.3.66` |

Connector consumes the library via `operations._ensure_fsr_playbooks_path()` —
a `sys.path` prepend + **import-cache eviction** hack (see §2, Risk B).

**Cross-boundary import surface (measured):** the triage cluster imports only
`fsr_playbooks.llm.tools` (×2) and `fsr_playbooks.mcp_server` (×1) from the public
surface. Everything else is triage-internal. The seam is small; re-verify per-file
at execution time (step 1) — lazy/runtime imports of `fsr_playbooks.mcp_server._shared`
or crudhub may not show in a static grep.

---

## 1. End-state (the target topology)

```
PyPI: fsr-playbooks (compiler + authoring + kept run/debug tools)   ← single source
        ▲                    pinned ==X.Y.Z
        │
connector-fsr-soc-assistant
  ├── fsr_soc_triage/         ← triage cluster, re-homed OUT of fsr_playbooks.* namespace
  │     imports fsr_playbooks.llm.tools, fsr_playbooks.mcp_server  (the only seam)
  ├── connector.py / operations.py
  └── (NO vendored fsr_playbooks/, NO fsr_core.bak/)
```

Invariant: **dependency direction is one-way** `connector → fsr_playbooks`. If anything
in `fsr_playbooks` ever needs to import triage, the boundary was drawn wrong.

---

## 2. The three things that will break us if ignored

### Risk A — namespace collision (why "just add a dependency" fails)
Triage lives at `fsr_playbooks/mcp_server/tools_triage.py` etc. Once `fsr_playbooks` is a
pip-installed package owned by site-packages, you **cannot** also drop connector files into
that tree. Merging your own modules into a third-party package dir is the namespace-package
fragility this repo has already been bitten by.
→ **Mitigation:** re-home triage into a connector-owned namespace `fsr_soc_triage/`
(step 1). This is the bulk of the work.

### Risk B — SOAR worker import-cache identity (the deployment killer)
`fsr_playbooks` is a **top-level package name**. A long-lived FortiSOAR worker caches the
first `fsr_playbooks` it imports in `sys.modules`. `_ensure_fsr_playbooks_path()` exists
*today* to evict a stale vendored copy when the connector version changes. If two connector
versions (or two connectors) pin **different** `fsr_playbooks` versions, the worker binds
whichever imported first — new `operations.py` running against an old cached `fsr_playbooks`
→ silent stale code / `AttributeError` on Event classes.
→ **Mitigations (all required):**
  1. Connector **pins an exact version** (`fsr_playbooks==X.Y.Z`), never a float.
  2. Keep an eviction guard equivalent to `_ensure_fsr_playbooks_path()` but pointed at the
     **installed** package, and assert the imported `fsr_playbooks.__version__` matches the
     pin at connector startup — fail loud, not silent, on mismatch.
  3. Materialize the pinned wheel **into the connector zip** (don't rely on the appliance
     reaching PyPI at deploy). SOAR 3.9 runtime → `requires-python` already `>=3.9`.

### Risk C — severed-tendril contract must stay intact
The library already makes `tools_jinja(from_pb_execution=…)` and `tools_recipe` live-run
diagnostics degrade via `_tools_triage_or_err()` when triage is absent. Post-reconciliation
the connector re-supplies triage and those paths relight. Contract = **"library works
without triage; connector adds it back."** Reconciliation must *exercise* this, not weaken it.
The re-homed triage must register itself through the same guard hook, not by patching library
internals.

---

## 3. Phased execution (each phase gated; nothing lands red)

### Phase 0 — publish the clean library first (unblocks everything, low risk)
0.1 Delete PyPI `0.3.62`–`0.3.65` (poisoned). *(owner: user — PyPI creds)*
0.2 Commit the in-flight message-block feature (green, 15/15) as its own commit.
0.3 Bump `packaging/fsr_playbooks/pyproject.toml` → `0.3.66`. ✅ (then → `0.3.67`, see Phase 1)
0.4 Fast-forward `reorg/phase-0-freeze-surface` → `main`. ✅
0.5 Build wheel, **gate:** `unzip -l` shows zero `triage_*|tools_triage|tools_noc|_live_crudhub|system_prompt_triage`; clean-venv `import fsr_playbooks` + `import fsr_playbooks.mcp_server` succeed. ✅
0.6 **Publish `0.3.67`** (NOT 0.3.66 — superseded). 0.3.67 is triage-free AND carries the
    Phase-1 facade, so a single publish closes the leak and unblocks the connector. *(owner: user)*
    Built wheel: `packaging/fsr_playbooks/dist/fsr_playbooks-0.3.67-py3-none-any.whl`.
**After Phase 0 the leak is closed.** Phases 1–3 are correctness/dedup, not leak-driven.

### Phase 1 — re-home triage into its own namespace (the real work)
1.1 **Per-file import audit** ✅ DONE (2026-06-18). The seam is bigger than the first naive
    grep suggested — triage uses **relative** imports inside `fsr_playbooks`, hiding the
    coupling. Findings:

  **Cross-boundary PRIVATE seam (13 kept-library internals triage depends on):**
  - `mcp_server._shared`: `_db`, `_rows`, `_VERIF_RANK`, `_capability_gap_suggestion`, `_live_client`
  - `mcp_server.tools_execution`: `_fetch_runs_both`, `_shape_run`, `_live_healthcheck`,
    `_cached_health`, `_store_health`, `_agent_configured_rows`, `run_op`  ← **7 internals; the crux**
  - `llm.tools._tier_for_run_op`, `agent.skill_trace.mute_recording`

  **Cross-boundary PUBLIC seam (stable, fine):** `_shared.mcp`,
  `intents.{DIRECTIVE, classify_message, gate_directive, load_intent_prompt}`.

  **Non-shipped deps:** `probes._env.{get_client,get_config}` (dev client; connector must
  vendor `probes` or supply an equivalent), `integrations.crudhub` / `connectors.core.connector`
  (on-platform loopback — present on the appliance, absent from the wheel; `_live_crudhub.py`
  already try/excepts these).

  **Intra-cluster (becomes internal on re-home, harmless):** tools_noc→tools_triage
  (`_envelope`, `_faz_*`, `_is_empty`, `_FAZ_LOG_TIME`), preflight→normalize
  (`_RELATED_ALERT_KEYS`, `_digest_event`), prompt→{normalize,scenarios,sources}, etc.

  → **The re-home is blocked on D4 (below): does `tools_execution` stay public?** Triage's
  dominant coupling is to its 7 private helpers. Either promote them to a stable public API,
  or move `tools_execution` out of the public package with triage.
1.2 **[LIBRARY] Build the public execution facade** — a NEW module
    `fsr_playbooks/execution_api.py` that imports the chosen internals and re-exports them under
    stable, non-underscore names. This is the *only* surface triage may import from the kept
    library for run/exec; it's the frozen contract. Rename map:

    | Internal (today) | Public facade name | Source |
    |---|---|---|
    | `_shared._VERIF_RANK` | `VERIF_RANK` | _shared |
    | `_shared._rows` | `query_rows` | _shared |
    | `_shared._db` | `open_reference_db` | _shared |
    | `_shared._live_client` | `live_client` | _shared |
    | `_shared._capability_gap_suggestion` | `capability_gap_suggestion` | _shared |
    | `tools_execution._shape_run` | `shape_run` | tools_execution |
    | `tools_execution._store_health` | `store_health` | tools_execution |
    | `tools_execution._cached_health` | `cached_health` | tools_execution |
    | `tools_execution._fetch_runs_both` | `fetch_runs` | tools_execution |
    | `tools_execution._agent_configured_rows` | `agent_configured_rows` | tools_execution |
    | `tools_execution._live_healthcheck` | `live_healthcheck` | tools_execution |
    | `tools_execution.run_op` | `run_op` (already public) | tools_execution |
    | `llm.tools._tier_for_run_op` | `tier_for_run_op` | llm.tools |
    | `agent.skill_trace.mute_recording` | `mute_recording` (already public) | agent.skill_trace |

    The facade only RE-EXPORTS (no logic), so the underscore originals stay put and unrenamed —
    zero risk to existing internal callers. `__all__` lists exactly these names.
1.2 ✅ DONE (2026-06-18) — `fsr_playbooks/execution_api.py` created; pure re-export, underscore
    originals untouched.
1.3 **[LIBRARY] Freeze it:** ✅ DONE — `test_public_surface_contract.py` extended (+1 module,
    +14 symbols); 62 passed. Wheel `0.3.67` built & verified: facade present, triage absent,
    `from fsr_playbooks.execution_api import run_op, shape_run, live_client, tier_for_run_op`
    imports from a clean `[mcp,llm]` install. **Remaining: user publishes 0.3.67.**
    --- below here Phase 1 is NOT yet started (connector-side) ---
1.4 **[CONNECTOR] `git mv`** the cluster from `connector/fsr_playbooks/{mcp_server,llm,agent}/…`
    into the new triage namespace (name per D1). Rewrite imports:
    - triage↔triage internal imports → new namespace (e.g. `..llm.triage_normalize` → sibling).
    - seam imports → `from fsr_playbooks.execution_api import <public name>` (the table above) and
      `from fsr_playbooks.llm.intents import …` / `from fsr_playbooks.mcp_server import mcp`.
    - `_live_crudhub.py` keeps its `integrations.crudhub` / `connectors.core.connector` try/except
      (on-platform, unchanged).
1.5 **[CONNECTOR]** Register triage with the library's `_tools_triage_or_err()` hook from the
    new namespace (Risk C) — triage relights the severed tendrils without patching library internals.
1.6 **Gate:** connector test suite green offline (29 + triage tests) with `fsr_playbooks`
    resolved from the **installed `0.3.67` wheel**, not the vendored dir; and a grep proving no
    `from .` / `..` import in triage still points at a kept-library module.

### Phase 1.4–2 EXECUTION STATUS (2026-06-18) — WIP on connector branch `reorg/triage-rehome`
Done as one combined change (the vendored copy wired triage → move+delete+pin inseparable):
- ✅ 9 triage/NOC files → `fsr_soc_triage/` (flattened, connector-owned); seam imports via
  `fsr_playbooks.execution_api` + `llm.intents` + `mcp_server._shared`.
- ✅ Deleted vendored `fsr_playbooks/` (106 files) + `fsr_core.bak/`; depends on published lib.
- ✅ Repointed `operations.py` + root `tests/`; recovered 16 triage tests + fixtures, repointed.
- ✅ `_load_prompt` reads `system_prompt_triage.md` from `fsr_soc_triage`.
- **286 tests pass; 26 fail on TWO integration seams (need design, not mechanics):**
  - **D5 — tool REGISTRY/tiers:** `anthropic_provider` *curates* `REGISTRY` at import (NOT via
    `@mcp.tool` side-effects); Phase 1 pruned the triage/NOC entries, so importing the cluster
    does NOT re-add them. The connector must explicitly re-register its triage/NOC tools + safety
    tiers. Affects `test_noc_tools`, `test_*_tier_*`, `test_*_slice*`. **Approach undecided.**
  - **Triage prompt content:** `test_triage_prompt*` assert `.md`-derived text; the prompt builder
    in `fsr_soc_triage/triage_prompt.py` needs its `.md` load path confirmed.
- Tested vs the locally-built `0.3.67` wheel (PyPI publish pending). NOT merged to connector main.

### Phase 2 — cut the connector over to the pinned package
2.1 Delete connector `fsr_playbooks/` and `fsr_core.bak/`.
2.2 `requirements.txt` → add `fsr-playbooks==0.3.67` (the facade-bearing release from 1.3;
    NOT 0.3.66, which predates `execution_api`) (drop anthropic/openai if the
    `[llm]` extra covers them; keep pyyaml only if used directly).
2.3 Rework `_ensure_fsr_playbooks_path()` → version-assert guard (Risk B.2).
2.4 Zip-build materializes the pinned wheel into the bundle (Risk B.3).
2.5 **Gate:** clean build of the connector tarball; `unzip` shows the pinned `fsr_playbooks`
    present and exactly one copy; no `fsr_soc_triage` files under any `fsr_playbooks/` path.

### Phase 3 — live verification (cannot be gated offline)
3.1 Deploy the connector to a lab appliance (10.99.249.205 or .159).
3.2 Smoke: a compile/push authoring op (pure library path) **and** a triage/agent op
    (connector path) on a real record.
3.3 Restart the worker, run both again → proves the import-cache identity is stable across
    a cold worker (Risk B end-to-end).
3.4 Bump connector version + redeploy.

---

## 4. Don't-break checklist (run before declaring each phase done)
- [ ] `import fsr_playbooks` and `import fsr_playbooks.mcp_server` succeed in a clean venv with **no triage on disk**.
- [ ] Public wheel contains zero investigation files (the §0 grep).
- [ ] Connector resolves `fsr_playbooks` from the **installed** package, never a sibling dir, in tests.
- [ ] Exactly one `fsr_playbooks` on `sys.path` at connector runtime; version-assert passes.
- [ ] Severed-tendril tools degrade (library-only) AND relight (connector) — both states tested.
- [ ] No `fsr_soc_triage` file sits under a `fsr_playbooks/` path anywhere.

## 5. Open decisions (resolve before Phase 1)
- **D1 — triage namespace name:** `fsr_soc_triage` vs nesting under the connector module
  (`connector_fsr_soc_assistant.triage`). Nesting avoids a 2nd top-level name on the worker
  (helps Risk B) but is a bigger import rewrite. **DECISION (2026-06-18): deferred to Phase 1**
  — pick after step 1.1's per-file import audit shows the true rewrite cost. *Leaning: nest.*
- **D2 — public vs private index for `fsr_playbooks`:** it's already public (accidentally).
  Keep public going forward, or move to a private index and republish? Affects 2.4 fetch.
- **D3 — `[llm]`/`[mcp]` extras vs pinning anthropic/openai in the connector directly.**
- **D4 — does `tools_execution` stay in the public package? (BLOCKS Phase 1)** The audit shows
  triage couples to 7 private helpers of `tools_execution` + 4 of `_shared`. Three ways out:
  - **(a) Promote** ~13 private symbols to a documented, stable public "extension API" in
    `fsr_playbooks` (rename sans underscore, freeze via the public-surface contract test).
    Keeps run/deploy in the public package per the REORG decision; cost = a real public API
    surface to maintain + triage pinned to it.
  - **(b) Move `tools_execution` (and `_shared`'s live bits) OUT** with triage into the
    connector. Public package becomes pure authoring (compile/emit/verify/catalog/corpus/
    jinja/picklists/discovery + llm build path). Cleanest seam — the coupling leaves with the
    code — but the public package loses "run a playbook," reversing the REORG "running is
    authoring" call, and any authoring user who wanted run/push loses it.
  - **(c) Duplicate the thin run-helpers** into triage (copy `_fetch_runs_both`/`_shape_run`/
    health helpers). Fast, but reintroduces exactly the drift this whole effort kills. Reject
    unless the helpers are trivial + stable.
  *Leaning (a)* — preserves the REORG boundary and keeps one copy; the ~13 symbols are a
  bounded, mechanical promotion. Decide before any Phase 1 code moves.

  **Sizing (read 2026-06-18, judging a vs c):** the promotion surface is small and stable —
  `_shared`: `_VERIF_RANK` (1-line const), `_rows` (2 loc), `_db` (10), `_live_client` (18),
  `_capability_gap_suggestion` (33). `tools_execution`: `_shape_run` (16), `_store_health` (14),
  `_cached_health` (26), `_fetch_runs_both` (29), `_agent_configured_rows` (40),
  `_live_healthcheck` (59), and **`run_op` (291) which is ALREADY `@mcp.tool()` / public**.
  So the real work is exposing ~10 stable helpers (~250 loc) under non-underscore names via a
  thin `fsr_playbooks.execution` facade, frozen by `test_public_surface_contract.py`. None are
  churn-prone. `_db`/`_live_client` already soft-depend on non-shipped `probes` via try/except,
  so triage's `probes` need is the same posture the public package already takes, not a new one.
  → **(a) chosen as the cheap, drift-free path; (b) rejected (rips out the public run/healthcheck
  tools authoring users use); (c) rejected (reintroduces drift).**
  **DECISION (2026-06-18): LOCKED = (a). See Phase 1 steps below.**
