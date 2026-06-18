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
0.3 Bump `packaging/fsr_playbooks/pyproject.toml` → `0.3.66`.
0.4 Fast-forward `reorg/phase-0-freeze-surface` → `main` (9 ahead / 0 behind).
0.5 Build wheel, **gate:** `unzip -l` shows zero `triage_*|tools_triage|tools_noc|_live_crudhub|system_prompt_triage`; clean-venv `import fsr_playbooks` + `import fsr_playbooks.mcp_server` succeed.
0.6 Publish `0.3.66`.
**After Phase 0 the leak is closed.** Phases 1–3 are correctness/dedup, not leak-driven.

### Phase 1 — re-home triage into `fsr_soc_triage/` (the real work)
1.1 **Per-file import audit** of the connector triage cluster (static + grep for lazy/
    runtime `import fsr_playbooks...`). Produce the exact seam list. Confirm it's only
    `llm.tools` + `mcp_server` (+ whatever the audit adds).
1.2 `git mv` the cluster from `connector/fsr_playbooks/{mcp_server,llm,agent}/…` into
    `connector/fsr_soc_triage/…`. Keep internal triage↔triage imports (rewrite
    `fsr_playbooks.llm.triage_x` → `fsr_soc_triage.triage_x`).
1.3 Rewrite the seam imports to consume the **installed** `fsr_playbooks` (unchanged paths,
    just no longer a sibling).
1.4 Register triage with the library's `_tools_triage_or_err()` hook from the new namespace.
1.5 **Gate:** connector test suite green offline (the 29 + triage tests), with `fsr_playbooks`
    resolved from an installed wheel, not the vendored dir.

### Phase 2 — cut the connector over to the pinned package
2.1 Delete connector `fsr_playbooks/` and `fsr_core.bak/`.
2.2 `requirements.txt` → add `fsr-playbooks==0.3.66` (drop anthropic/openai if the
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
