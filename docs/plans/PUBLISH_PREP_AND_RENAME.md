# Publish-prep + rename — LIVING TRACKER

> **This is THE living doc for this workstream.** It is kept current so context
> can be `/clear`ed frequently. To resume after a clear: read this top block,
> then the task table. Convention: update the "Resume here" block + the task
> table at the end of every work chunk, BEFORE clearing.

<!-- ───────────────────────── RESUME HERE ───────────────────────── -->
## ▶ Resume here

- **Last updated:** 2026-06-07 (PM — publish executed: 0.3.127 deployed, repos
  created on Gitea, connector renamed, framework merged to `main`).
- **STATUS: PUBLISH LEDGER COMPLETE (10/10 ✅) + published to internal remotes.**
  Original cutover (AM): dir → `fsr-playbook-framework`, `.venv` rebuilt, connector
  `fsr_core` symlink retargeted, auto-memory migrated, `make verify` green
  (339 + 162). pyfsr blocker fixed (junk tags `v0.2.4-tag`/`v0.2.2-fix` deleted,
  clean `v0.2.4` recreated so hatch-vcs / `make sync` works).

### Done this session (PM)
- **Connector 0.3.127 DEPLOYED & live-verified** — warmup now fills grounding
  tables (modules 43 / module_fields 1036 / picklists 690 + the 4 WARM tables).
  All 9 workers on 0.3.127. (Was task #2's pending "deploy when ready".)
- **Framework merged to `main`** — fast-forward of `chore/b4-golden-and-publish-prep`
  (15 commits, all publish-prep/rename + 1 golden test). Pushed to BOTH remotes.
- **Repo homes (all 3 projects):**
  - **framework** → GitLab `origin` (`svl-devops-gitlab01…/dspille/fsr-playbook-framework`,
    renamed today from `agentic-playbook-creation`) **+** Gitea `gitea`
    (`git.fndn.fortinet.net/dspille/fsr-playbook-framework`, private, default `main`).
  - **connector** → Gitea `git.fndn.fortinet.net/dspille/connector-fsr-soc-assistant`
    (private). NO GitLab remote. Local checkout dir still `ConnectorsV2/fsr-playbook-builder`.
  - **widget** (`WebstormProjects/fsr_all_widgets`) → Gitea repo NOT created yet.
- **Connector RENAMED** `fsr-playbook-builder` → `connector-fsr-soc-assistant`
  (info.json name + label "FSR SOC Assistant" + python module
  `connector_fsr_soc_assistant` + package dir + scripts/tests/README/pyproject).
  `make verify` green. On branch `chore/rename-to-connector-fsr-soc-assistant`
  (pushed to Gitea), NOT yet merged to `feat/action-based-streaming`, NOT deployed.

### ⏳ Remaining follow-ups (non-ledger)
1. **Connector live cutover** (user chose deploy-new + delete-old): deploy
   `connector-fsr-soc-assistant` 0.3.127 to the box, then delete the orphaned
   `fsr-playbook-builder` 0.3.127. Merge the rename branch → `feat/action-based-streaming` first.
2. **Widget Gitea repo** — create `widget-fsr-soc-assistant` (handoff steps in chat;
   push-to-create is DISABLED → must create via API using `GITEA_TOKEN` in `.env`,
   scopes `write:user`+`write:repository`). 3 uncommitted `scripts/` edits — don't commit WIP.
3. **Auto-memory refresh** — `[[connector_state]]` still says 0.3.115 / old name;
   update to 0.3.127 + `connector-fsr-soc-assistant` + the 3 repo homes.
4. **GitHub (framework)** — NOT pushed. User intent: keep DBs local, drop Fortinet
   infra refs, drop most docs. Scrub pass needed BEFORE any GitHub push
   (bundled `.db`+`store/fsr_reference.json` are in git HISTORY → would need history
   rewrite/fresh repo, not just a delete commit).
5. **Store-publish metadata** deferred (publisher/help_online/cs_approved — only
   for formal Fortinet store submission).

- **Mirror in auto-memory:** `[[publish_prep_and_rename]]` (pointer in MEMORY.md).
<!-- ──────────────────────────────────────────────────────────────── -->

## Task list (the publish ledger)

| # | Task | Status |
|---|------|--------|
| 1 | Pin a fast offline B4 build-fidelity golden | ✅ done — `b427373` |
| 2 | Verify slim-DB + fill-from-your-own-SOAR path is complete | ✅ done — caveat 1 FIXED (warmup now fills modules/fields/picklists), caveat 2 ACCEPTED. See §Task2 |
| 3 | De-hardcode widget-fixtures path in build.sh | ✅ done — connector `1a73c9f` |
| 4 | Unified cross-repo "work on the AI chat" runbook | ✅ done — `docs/CHAT_DEV_RUNBOOK.md` |
| 5 | `.env.example` for both repos | ✅ done — `dd7c439` + connector `5a68b6f` |
| 6 | Clean up scratch/diagnostic files | ✅ done — user chose KEEP+gitignore (not delete). `_[a-z]*.py` patterns added both repos (framework `cfee248`, connector `255badb`); files stay on disk, none committed |
| 7 | Verify a clean-clone bootstrap reaches green unattended | ✅ done — verified 2026-06-07, see §Task7 |
| 8 | Connector release hygiene (README, release_notes, version) | ✅ done — see §Task8 (metadata decision deferred) |
| 9 | Close B4 sub-item: parameterized-to-trigger-record check | ✅ done — already impl + test-pinned, see §Task9 |
| 10 | Rename FSRPlaybookYaml → fsr-playbook-framework | ✅ done — cutover ran 2026-06-07, `make verify` green at new path. See §Rename |

**ALL 10 LEDGER ITEMS COMPLETE + PUBLISHED.** Connector 0.3.127 deployed,
framework merged to `main` + pushed to GitLab+Gitea. Remaining follow-ups are
listed in the "Remaining follow-ups" block under ▶ Resume here.

### Context for the pending tasks
- **#2** Slim-DB design CONFIRMED real (not a 63MB-distribution cliff): connector
  ships `build.sh --slim` (~1.0M, hard-mined tables only) + `connector.warmup`
  repopulates WARM tables from the operator's OWN SOAR; dev rebuilds via
  `fsrpb refresh`. Task is to VERIFY the hard-mined tables ship complete +
  connector-agnostic, and a fresh operator's warmup covers THEIR connectors.
- **#6** Scratch files: framework `python/_poll_raw_query.py _poll_then_hunt.py
  _prove_rel_query.py _prove_rel_query2.py _q1_fortigate_cfg.py` (untracked);
  connector `scripts/_*.py` (8). Decide promote-vs-delete per file. ASK first.
- **#9** Beyond ops-overlap: confirm built connector-step inputs are
  parameterized to `vars.input.records[0].*`, not hardcoded one-off IOCs.

## §Task2 findings — slim-DB + warmup path (verified 2026-06-07)

Traced `scripts/build.sh --slim` (connector) ↔ `warmup()` op (operations.py
~3882) ↔ source `store/fsr_reference.db` (63 MB full).

**What works (path is sound for MVP demo flows):**
- KEEP/hard-mined tables ship populated & substantively connector-agnostic:
  step_types(43), step_handlers(44), step_examples(66), jinja_filter_usage(1690),
  jinja_macros(172), jinja_globals(15), jinja_tests(39), jinja_context_vars(1).
- `warmup()` repopulates 4 WARM tables live from the operator's OWN SOAR
  (`/api/integration/connectors/` + bulk `connector_details`): connectors,
  operations, operation_params, op_safety. Idempotent, lifecycle-triggered,
  live-proven. `_warmup_needed` gates on empty `connectors`.

**Caveat 1 — 6 WARM tables truncated by --slim but NEVER re-warmed.**
slim DELETEs 10 tables; warmup only writes 4. Orphaned (truncated, no warm path):
picklists(710), modules(63), module_fields(1234), connector_icons(31),
param_type_probes(2216), operation_examples(1172). Docstring labels these
"Deferred — not needed for the contract's demo flows" (record-step grounding).
Impact: a fresh operator building **record-creation / module-grounded** playbooks
gets empty module/picklist grounding until/unless these are warmed too.
→ RESOLVED (user: extend warmup). `warmup()` now also fills modules,
  module_fields, picklists from the operator's own SOAR via the SAME endpoints
  as the offline miner (`/api/3/staging_model_metadatas` +
  `/api/3/picklist_names`, both `$relationships=true`). New helper
  `_warmup_modules_picklists()`; `_warmup_needed()` now also fires when the
  `modules` table is empty so upgrades auto-fill. Counts added to the warmup
  envelope. 3 new tests in test_warmup_hooks.py. connector commit `3927a0a`.
  Still deferred (out of MVP scope, no warm path): connector_icons,
  param_type_probes, operation_examples.

**Caveat 2 — provenance leak in shipped KEEP tables.**
`jinja_filter_usage.from_playbook` ships 362 human-readable playbook names from
the mining corpus (mostly stock Fortinet content e.g. "Enrich Indicators", but
some custom: "netshot domain - link profiles", "Use Case 2: Investigate Malware
Alert"). `step_examples.from_playbook` is opaque `step:<uuid>` (no leak).
Not sensitive (no creds/data), but ships dev-env playbook NAMES.
→ RESOLVED (user: accept). Names are reference provenance, not runtime-matched;
  mostly stock Fortinet content; no creds/sensitive data. Left as-is.

## §Task7 — clean-clone bootstrap (verified 2026-06-07)

Cloned the branch into `/tmp` and ran `scripts/bootstrap.sh` fully unattended:
```sh
NONINTERACTIVE=1 \
PYFSR_REPO=/Users/dylanspille/PycharmProjects/pyfsr \
FSR_DB_SRC=<…>/store/fsr_reference.db \
bash scripts/bootstrap.sh
```
Result: all 6 steps green → **339 fsr_core tests passed**, "BOOTSTRAP COMPLETE".
Unattended path needs the 3 env vars above (uv auto-resolves toolchain;
`make sync` clones pyfsr from PYFSR_REPO; FSR_DB_SRC seeds the gitignored 63 MB
reference DB — **required for green**, without it step 6 reds). `.env` is
auto-created from `.env.example` under NONINTERACTIVE but is only needed for
live work. Temp clone removed after.

## §Task8 — connector release hygiene (2026-06-07)

- **README** (connector `README.md`): fixed stale "Status — 0.1.0" → an
  accurate "Operations" section listing all 20 ops; added the `--slim` build
  path (default distribution is <1 M, not the old "~14M"/"~63M" full DB).
- **release_notes.md** (user: fill current only): wrote real notes for 0.3.126
  (grounding 1.0) and pre-staged a 0.3.127 entry for the warmup change so the
  next `deploy.sh --bump patch` lands on 0.3.127 without re-stubbing. The 60+
  older `_TODO` entries left as historical churn per the decision.
- **version**: shipped is 0.3.126 (info.json); the warmup change deploys as
  0.3.127. Not deployed this session — deploy is a live-box action.

**Publish-metadata (DEFERRED — user "not sure yet").** If/when submitting to
the **Fortinet Connector Store**, info.json needs: a real `publisher` (currently
"Internal"), a `help_online` URL (currently null), and `cs_approved` true — the
last is a Fortinet review gate, NOT settable by us. `category` is "utilities".
For an internal-only distribution the current metadata is fine as-is.

## §Task9 — IOC parameterization (verified 2026-06-07)

Confirmed the trace→YAML build parameterizes one-off triage IOCs to the trigger
record instead of baking literals. Mechanism lives in
`fsr_core/compiler/skill_compiler.py` (the gap-param parameterizer ~L258):
value-matches a literal against the trigger record's fields, stages it on a
synthetic `Set Inputs` (set_variable) step as `{{ vars.input.records[0].<field>
}}`, and rewrites the consuming connector step to `{{ vars.steps.Set_Inputs.<var>
}}`. Handles embedded spans in query strings too.

Test-pinned in `fsr_core/tests/test_build_from_trace.py`:
- positive: IOC `102.220.160.21` (= record `sourceIp`) → Set Inputs
  `{{ vars.input.records[0].sourceIp }}`, step consumes
  `{{ vars.steps.Set_Inputs.ip }}`, and `"102.220.160.21" not in yaml`
  (NO hardcoded IOC anywhere).
- negative guard: no module → records[0] wouldn't resolve, so IOC stays literal
  and no Set Inputs is injected (avoids a dangling reference).
Caveat (by design): parameterization requires a module-bound trigger
(record_fields + module). 55 related tests green.

## Rename — FSRPlaybookYaml → fsr-playbook-framework

Decision (user, this session): **full clean rename**. New canonical name
`fsr-playbook-framework`; the git REMOTE (`agentic-playbook-creation`) is
unaffected — only the local dir name changes.

### Why it needs care (couplings)
- Live session cwd is inside the dir → can't plain `mv` mid-session.
- `.venv` has absolute paths (editable `fsr_core` + `../pyfsr`) → rebuild needed.
- Connector `fsr_core` symlink is ABSOLUTE to `FSRPlaybookYaml/fsr_core` → retarget.
- Auto-memory dir is keyed on the path
  (`~/.claude/projects/-Users-dylanspille-PycharmProjects-FSRPlaybookYaml/`) → migrate.

### Plan / progress
1. ✅ Bulk-replaced `FSRPlaybookYaml` → `fsr-playbook-framework` in tracked text of
   BOTH repos (excluded `store/eval_runs/*.log`, `store/**/*.db`, this doc).
   23 framework + 19 connector files. `make chat-fast` green pre-move.
2. ✅ Committed: framework **`a4391d4`**, connector **`994a614`**. (Refs now point
   at the new path, which won't exist until finalize runs — that's the cutover.)
3. ✅ **DONE — `finalize-rename.sh` ran 2026-06-07.** Physical move completed.
   The script aborted mid-`make sync` on a pyfsr build error (junk tag
   `v0.2.4-tag` unparseable by hatch-vcs). Fixed in pyfsr: deleted junk tags
   `v0.2.4-tag` + `v0.2.2-fix`, created clean `v0.2.4` at commit `2b3d372`;
   `git describe` → `v0.2.4-2-gf5f1564`. Re-ran `make sync` (green), then the
   remaining steps by hand: symlink retargeted, auto-memory migrated.
   `finalize-rename.sh` deleted after use (spent).
4. ✅ `make verify` green at new path: **339 fsr_core + 162 connector passed.**
5. ⬜ Restart Claude Code in `/Users/dylanspille/PycharmProjects/fsr-playbook-framework`
   (this session's cwd was recovered after the move; a restart picks up the
   migrated auto-memory dir cleanly).

### Done — cutover complete
Dir is now `fsr-playbook-framework`, venv rebuilt, connector symlink retargeted,
auto-memory migrated, both suites green. Publish ledger is 10/10.
