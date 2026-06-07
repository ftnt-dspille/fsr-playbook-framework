# Publish-prep + rename — LIVING TRACKER

> **This is THE living doc for this workstream.** It is kept current so context
> can be `/clear`ed frequently. To resume after a clear: read this top block,
> then the task table. Convention: update the "Resume here" block + the task
> table at the end of every work chunk, BEFORE clearing.

<!-- ───────────────────────── RESUME HERE ───────────────────────── -->
## ▶ Resume here

- **Last updated:** 2026-06-07 (session after the B4 grounding fix + rename staging)
- **Branch:** `chore/b4-golden-and-publish-prep` (framework); connector → its `main`.
- **NEXT ACTION:** run the rename cutover — `bash finalize-rename.sh` (repo root,
  untracked) **after closing this session**, then restart Claude in
  `…/PycharmProjects/fsr-playbook-framework` and tell it to read this file.
  After the move, mark task #10 done and pick up task #2.
- **If finalize hasn't run yet:** the dir is still `FSRPlaybookYaml`; nothing
  physical changed (venv + memory intact). See §Rename.
- **Mirror in auto-memory:** `[[publish_prep_and_rename]]` (pointer in MEMORY.md).
<!-- ──────────────────────────────────────────────────────────────── -->

## Task list (the publish ledger)

| # | Task | Status |
|---|------|--------|
| 1 | Pin a fast offline B4 build-fidelity golden | ✅ done — `b427373` |
| 2 | Verify slim-DB + fill-from-your-own-SOAR path is complete | ⬜ pending |
| 3 | De-hardcode widget-fixtures path in build.sh | ✅ done — connector `1a73c9f` |
| 4 | Unified cross-repo "work on the AI chat" runbook | ⬜ pending |
| 5 | `.env.example` for both repos | ✅ done — `dd7c439` + connector `5a68b6f` |
| 6 | Clean up scratch/diagnostic files (needs Dylan's OK before deleting) | ⬜ pending |
| 7 | Verify a clean-clone bootstrap reaches green unattended | ⬜ pending |
| 8 | Connector release hygiene (README, release_notes, version) | ⬜ pending |
| 9 | Close B4 sub-item: parameterized-to-trigger-record check | ⬜ pending |
| 10 | Rename FSRPlaybookYaml → fsr-playbook-framework | 🔧 in progress — see §Rename |

Suggested order for the rest: **10 (finish) → 2 → 4 → 7 → 6 → 8 → 9**.

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
3. ⬜ **NEXT (run after closing this session):** `finalize-rename.sh` (untracked,
   at repo root) does the physical move:
   ```sh
   cd /Users/dylanspille/PycharmProjects
   mv FSRPlaybookYaml fsr-playbook-framework
   cd fsr-playbook-framework
   rm -rf .venv && make sync                 # rebuild venv at new path
   # retarget connector's fsr_core symlink
   ln -sfn /Users/dylanspille/PycharmProjects/fsr-playbook-framework/fsr_core \
     /Users/dylanspille/PycharmProjects/ConnectorsV2/fsr-playbook-builder/fsr-playbook-builder/fsr_core
   # migrate auto-memory dir
   mv ~/.claude/projects/-Users-dylanspille-PycharmProjects-FSRPlaybookYaml \
      ~/.claude/projects/-Users-dylanspille-PycharmProjects-fsr-playbook-framework
   make verify                               # confirm green at new path
   ```
4. ⬜ Restart Claude Code in `/Users/dylanspille/PycharmProjects/fsr-playbook-framework`.
5. ⬜ Post-restart: `make verify` green, connector `make verify` green, re-read
   this doc, mark task #10 done, continue with #2.

### If restarting BEFORE finalize ran
Nothing physical changed — dir is still `FSRPlaybookYaml`, venv intact, memory
intact. The textual edits (if committed) reference the new name; just run the
finalize script when ready. Check `git log` on `chore/b4-golden-and-publish-prep`
for whether step 2 committed.
