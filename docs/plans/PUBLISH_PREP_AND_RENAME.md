# Publish-prep + rename — resume state

Working branch: **`chore/b4-golden-and-publish-prep`** (framework).
Connector changes land on the connector repo's `main`.

This is the session resume point for the "solid publish" task list and the
`FSRPlaybookYaml` → `fsr-playbook-framework` rename. If we restarted mid-rename,
read **§Rename** first.

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
1. ⬜ Bulk-replace `FSRPlaybookYaml` → `fsr-playbook-framework` in tracked text of
   BOTH repos (exclude `store/eval_runs/*.log`, `store/**/*.db`). File lists:
   `git grep -l FSRPlaybookYaml`. ~23 framework + ~19 connector files.
2. ⬜ Commit the textual edits in both repos (refs now point at the new path,
   which won't exist until the finalize script runs — that's the cutover).
3. ⬜ `finalize-rename.sh` (written to repo root) does the physical move:
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
