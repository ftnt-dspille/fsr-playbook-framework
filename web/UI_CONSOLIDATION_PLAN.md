# UI Consolidation Plan

Goal: trim the playbook designer chrome. Fewer buttons, fewer drawer tabs,
one consistent action bar across Design and CLI, no redundancy with the
auto-running validators.

## Diagnosis

Auto-running verbs (no user action needed):
- `validate` — runs on every keystroke (400ms debounce). Drives the status
  pill + Monaco markers.
- `analyze` — render-path sim; runs after every autosave.

User-initiated verbs:
- `verify` — the real pre-push gate.
- `run` / `push` — actually do something.
- `compile` — debug-only JSON dump.

Redundancies:
- Validate button duplicates the auto-validator. Status pill IS the result.
- Analyze button duplicates the autosave hook.
- Compile button is a debug affordance occupying primary chrome.
- Diagnostics and Fixes are two tabs for the same data with one extra button.
- Step Debugger duplicates Verify + Run, with a hostile JSON-textarea UX.
- EditorToolbar has *two* err/warn pills (markers + render-path); BuildBar
  has one. Inconsistent.

## Target shape

**One action bar** (Design and CLI):
```
[undo/redo · layout · ƒ Jinja]  |  [▶ Run ▾]  [● status]  [N issues ▾]  [⋯]
```
- Run split-button absorbs Push (Deploy) under its overflow.
- `[N issues]` chip opens the drawer; hidden when count is zero.
- Single green/red status dot is the sole ready-to-push indicator — fed
  by auto-validate, auto-analyze, AND auto-verify (all run on autosave).
  No Verify button, no separate `verify ✓` pill.
- `⋯` overflow exposes Re-validate / Re-analyze as escape valves.

**Drawer: 5 tabs → 2**
- **Issues** — merged Diagnostics + Fixes + Render path. Each diagnostic
  row carries an inline "Apply fix" when a fix exists. Count badge replaces
  the separate Fixes badge.
- **Deploy** — keeps streaming push logs.

Removed entirely:
- Step Debugger tab + `StepDebuggerPanel.svelte`.
- Compile tab. Compile JSON becomes a "View JSON" link in the Issues
  overflow / empty-state (compile still runs internally before push).

## Phased execution

### Phase 1 — Remove dead weight (safest, isolated)
- [ ] Drop Step Debugger tab from `DiagnosticsDrawer.svelte`.
- [ ] Delete `StepDebuggerPanel.svelte`.
- [ ] Narrow the `Tab` union and all callers from 5 values to 4.

### Phase 2 — Merge Diagnostics + Fixes
- [ ] In the Issues tab, render fixes inline on matching diagnostic rows
      (lookup by step_id / location).
- [ ] Drop the Fixes tab; keep the count rolled into the Issues badge.
- [ ] Keep `FixesPanel.svelte` apply logic, but invoked per-row.
- [ ] Design-mode "fixes apply through CLI" message moves to per-row
      disabled state with the same explanation.

### Phase 3 — Demote Compile
- [ ] Drop the Compile tab.
- [ ] Expose compile JSON via a "View compile JSON" item in an overflow
      (or in the Issues empty state).
- [ ] Remove the Compile button from BuildBar + EditorToolbar.

### Phase 4 — Unify action bars
- [x] Remove Validate + Analyze + Compile buttons.
- [x] Merge the two err/warn pills in EditorToolbar into one issues chip.
- [x] Add `⋯` overflow with Re-validate / Re-analyze.

### Phase 4b — Drop Verify button, auto-verify on autosave
- [x] Remove Verify button from BuildBar + EditorToolbar.
- [x] Remove the standalone `verify ✓/✗` pill from both.
- [x] Auto-run `runVerify()` from the autosave hook alongside analyze.
- [x] Status dot color is the single ready-to-push indicator.

### Phase 5 — Polish
- [ ] Update tests touching the drawer tab union and toolbar layout.
- [ ] Smoke-test Design + CLI flows; confirm autosave-triggered analyze
      still surfaces render diagnostics without a button press.

## Risk / one-way doors

- Hiding Validate/Analyze as auto-only is the highest-risk change. If the
  auto-runs ever stall, users have no obvious escape valve. Mitigation:
  the `⋯` overflow on the status pill keeps a manual trigger.
- Removing the Compile tab makes debugging "what got pushed?" slightly
  harder. Mitigation: keep the JSON one click away in overflow.
