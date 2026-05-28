# ManualInput output-keys catalog (C8 scope)

**Built**: 2026-05-25. Source: `store/fsr_reference.db` (193 MI steps
on the live FSR appliance + SP exports).

Feeds **C8 — MI mode/output mismatch** check in
`RENDER_PATH_VALIDATOR_PLAN.md` Phase 5.4. The analyzer needs to
answer: *given an MI step in mode M with declared
`inputVariables: [...]`, which `vars.steps.<MI>.<key>...` reads are
legitimate at runtime?*

This doc is **the catalog** + the design notes. When C8 ships the
`MI_OUTPUT_KEYS` dict below moves into
`python/compiler/mi_output_catalog.py`.

---

## 1. Modes in the corpus

`arguments.type` distribution (193 MI + ApprovalMI steps):

| Mode | Count | Notes |
|---|---:|---|
| `InputBased` | 163 | Default. 82 declare `inputVariables`; 83 are button-only (form empty). |
| `InputBased` + `is_approval=true` | 3 | Approval overlay; same output schema. |
| `DecisionBased` | 26 | Pure routing via `step_iri`. No input form. |
| `textarea` (typo) | 1 | Authoring bug; ignore. |
| Legacy `ApprovalManualInput` step type | 3 | Treat as `InputBased + is_approval`. |

## 2. Downstream consumption shape (live)

Scanned all 193 MI playbooks for `vars.steps.<MI_name>.<key>` refs in
every co-located step's `arguments_json`. Tabulated by mode:

**InputBased (262 refs total):**

- `input.<X>` — 259 refs, where `<X>` is one of the MI's declared
  `inputVariables[].name`. Top X: `reason` (30), `orgName` (14),
  `contentRepositoryName` (10), `developmentSettingsRepositoryName` (10),
  `productionSettingsRepositoryName` (8), `rangeOfDevices` (8),
  `oldModule` (8), `fortiManager` (6), `alertName` (6),
  `commands` (6), `sourceControlUsername` (5), `fortiSOARUsername` (4),
  `binaryFile` (4), `firewalls` (4), …
- `userid` — 3 refs (system-injected: IRI of the responding user).
- `username` — 1 ref.
- `datetime` — 1 ref (resume timestamp).

**Real mismatches found in the corpus** (consumer reads
`input.<X>` where `<X>` is NOT in the producer's declared
`inputVariables`):

| Producer MI | Bad key | Declared inputs |
|---|---|---|
| `Get_Issue_Details` | `input.items` | `[issueNumber, repositoryType]` |
| `Ask_for_user_input` | `input.fortiManager` | `[rangeOfDevices]` |
| `Identify_Target_System` | `input.fileHash` | `[targetSystem]` |

Three confirmed runtime-broken playbooks. C8 would flag all three at
authoring time.

**DecisionBased (0 refs):**

Zero `vars.steps.<DecisionBased_MI>.*` references across the entire
corpus. Confirms the routing-only contract: branches fire via the
chosen option's `step_iri`; downstream steps don't read MI output.

C8 should flag **any** `vars.steps.<DecisionBased_MI>.input.*` read
as an error — there is no input form to source from.

## 3. Catalog (final)

```python
# python/compiler/mi_output_catalog.py (target home; embedded here
# for the scope phase).

MI_SYSTEM_KEYS: frozenset[str] = frozenset({
    # Resume-body metadata FSR always injects on the MI output frame.
    # Safe to read in any mode; not part of the declared form.
    "userid",     # IRI of the responding user
    "username",   # responding user's display name
    "datetime",   # resume timestamp (ISO-8601)
})

# Per-mode shape descriptor used by the C8 analyzer.
#   form_key: top-level key under which the declared inputVariables
#             appear. None means the mode has no input form.
#   allow_input_star: True iff `vars.steps.<MI>.input.<X>` is a legal
#                     pattern (subject to X ∈ declared inputVariables).
MI_OUTPUT_KEYS: dict[str, dict] = {
    "InputBased": {
        "form_key": "input",
        "allow_input_star": True,
    },
    "DecisionBased": {
        "form_key": None,
        "allow_input_star": False,
    },
}

# Treat these step.arguments.type strings as aliases for the canonical
# modes above. Caught one corpus typo (`textarea`); seed with what
# we've actually seen.
MI_MODE_ALIASES: dict[str, str] = {
    "":             "InputBased",   # unset == default
    "textarea":     "InputBased",   # authoring typo found in corpus
}

# ApprovalManualInput legacy step type → treat as InputBased with the
# is_approval flag overlay.
APPROVAL_MI_STEP_TYPES: frozenset[str] = frozenset({
    "ApprovalManualInput",
})
```

## 4. C8 check semantics (for when wiring happens)

For each `vars.steps.<MI_name>.<segments...>` ref in a downstream
step's rendered_args / consumed_paths:

1. Resolve `<MI_name>` → MI step in this playbook. If not an MI,
   skip (C1/C2 cover it).
2. Determine mode from `arguments.type` (apply `MI_MODE_ALIASES`).
3. Walk `segments`:
   - If `segments[0]` ∈ `MI_SYSTEM_KEYS`: ok.
   - If `segments[0] == mode.form_key` (i.e. `"input"`):
     - If `mode.allow_input_star is False`: **error** —
       *"reads input.X off a DecisionBased manual_input; mode has no
       input form."*
     - Else if `segments[1]` not in declared
       `inputVariables[].name`: **error** —
       *"reads input.X but the form doesn't collect X
       (declared: [...])."*
   - Else: **warning** — *"reads an undocumented key off a
     manual_input; expected one of input.*, userid, username,
     datetime."*

Severity calibration mirrors C2: error when we're confident
(declared inputVariables is a closed set); warning when we can't
prove the mismatch (no inputVariables declared = button-only InputBased
that someone may have repurposed; emit warning rather than spam).

## 5. Edge cases to confirm before C8 ships

- **InputBased with empty inputVariables**: 83 button-only flows.
  These would *all* false-positive on any `input.*` read since the
  declared set is empty. Recommended handling: downgrade to warning
  when `len(declared)==0`, because button-only InputBased frequently
  gets retrofitted with form fields later without the consumers
  being re-checked.
- **Jinja-built MI names**: if a downstream consumer uses
  `vars.steps[some_var].input.X`, we can't statically resolve the
  producer. Skip silently (matches C1's behavior on dynamic refs).
- **`is_approval=true`**: adds an `approved: bool` key to the resume
  body but the corpus shows no consumers reading it via
  `vars.steps.<MI>.approved`. Add to `MI_SYSTEM_KEYS` only if
  consumption shows up later; speculative for now.

## 6. Open follow-up probes (not blocking C8)

- Probe `WorkflowViewSet.approval` action for the wire shape of
  `is_approval=true` resumes — confirms whether `approved` surfaces
  on the output frame and whether it's worth catalogging.
- Mine the SP-export half (vs `live_fsr`) for any additional
  metadata keys not seen on the live appliance.
- Confirm whether MI in `for_each` body exposes `vars.item` to the
  prompt's response_mapping (would be a separate check, not C8).

---

**Status**: catalog data complete; analyzer wiring deferred.
Re-baseline of `agent_corpus` after C8 ships will tell us how many
of the 3 confirmed corpus mismatches are caught at authoring time
(expected: all 3).
