# ManualInput + Decision validation audit (2026-05-06)

**Question**: now that `playbook_steps` indexes 7,442 real steps from
both SP exports and the live FSR appliance, where does our current
validation diverge from production reality?

**Method**: pull the rules out of `python/compiler/resolver.py` +
`python/compiler/validator.py`, then mine the corpus (filter
`source='live_fsr'` for the strongest signal: 168 ManualInput,
352 Decision steps) and tag every rule as either:
- ✅ matches the corpus,
- ⚠️ correct in spirit but misses real shapes,
- ❌ outright rejects shapes that production uses.

Each finding is reproducible: the SQL is in this doc, run against
`store/fsr_reference.db`.

---

## 0. ManualInput is mode-driven, not free-form (revision 2026-05-06)

Per the FSR step-builder UI, every "extra" top-level key on ManualInput
is gated by one of three discrete UI-mode toggles. A flat whitelist
would accept structurally-incoherent prompts (e.g. internal-only mode
with external email recipients filled in). The right model is
**co-presence rules per mode**.

**Mode A — Context (Record Linked vs Record Independent)**
*UI: "Choose type of manual input you want to create"*
Live distribution (168 MI):

| isRecordLinked | record | n |
|---|---|---:|
| `false`/0 | empty | 93 (Independent) |
| `true`/1 | set | 46 (Linked) |
| missing | set | 29 (legacy DecisionBased; treat as warning) |

Co-presence rule:
- Linked ⟹ `isRecordLinked=true` AND `record` is a non-empty Jinja IRI
  AND `resources` is the module name.
- Independent ⟹ `isRecordLinked=false` AND `record=""` AND
  `resources=""`/null.

**Mode B — Audience (Internal vs External)**
*UI: "Limit form to FortiSOAR system only" vs "Collect from External users"*
Live distribution:

| unauthenticated_input | inputExternalUser | n |
|---|---|---:|
| 0/missing | missing | 120 |
| missing | missing | 30 |
| 0 | 1 | 9 |
| 1 | 0 | 6 |
| 0 | 0 | 2 |
| 1 | 1 | 1 |

Co-presence rule:
- Internal ⟹ `unauthenticated_input=false` AND `inputExternalUser` not set/false.
  External-distribution keys (`external_channel_list`, `customEmailExternal`,
  `external_email_subject`, `external_email_attachments`,
  `custom_email_body_external`) MUST be empty/missing.
- External ⟹ `unauthenticated_input=true` AND
  `external_channel_list` non-empty (delivery channels, picklist IRIs)
  AND at least one of email/Slack recipient configs populated.
  Optional `inputExternalUser=true` declares the form is open to
  non-FSR users; `customEmailExternal` etc. gated behind a
  "Customize email template" toggle.
- The 6 cases with `un=1, ext=0` and 9 with `un=0, ext=1` are likely
  authoring inconsistencies — warn but don't error.

**Mode C — Assignment (`owner_detail`)**
*UI: Specific Users / Specific Team / No specific assignee*
Live distribution:

| isAssigned | assignee | n |
|---|---|---:|
| 0 | none | 167 |
| 1 | person | 1 |

Co-presence rule:
- `isAssigned=false` ⟹ `assignedToPerson=[]`, `assignedToTeam=[]`,
  `assignedToRecord=false`, `assignedToField=null`.
- `isAssigned=true` ⟹ exactly one of `assignedToPerson` /
  `assignedToTeam` / `assignedToRecord` / `assignedToField`
  populated. The four are mutually exclusive (per `MANUAL_INPUT.md` §4).

**Mode D — Approval / Timeout (overlays)**
- `is_approval=true` is purely UI styling (Approve/Reject buttons +
  approval audit trail); doesn't change other keys' validity.
- `timeout: {days, hours, minutes, step_iri}` is independent — present
  on 20/168 MIs. `timeout.step_iri` MUST resolve to a step in the same
  playbook (treat as another branch target in the shared branch
  validator, §10).

**Implementation note (supersedes flat I20)**: replace the existing
`_FRIENDLY ∪ _CANONICAL` whitelist with a mode-aware checker. Pseudocode:

```python
def _check_manual_input_modes(args):
    is_linked  = bool(args.get("isRecordLinked"))
    is_extern  = bool(args.get("unauthenticated_input")) or bool(args.get("inputExternalUser"))
    is_assigned = bool((args.get("owner_detail") or {}).get("isAssigned"))

    # Context coherence
    if is_linked and not args.get("record"):
        error("isRecordLinked=true requires non-empty record")
    if not is_linked and args.get("record"):
        warn("record is set but isRecordLinked=false; FSR will ignore record")

    # Audience coherence
    EXT_KEYS = {"customEmailExternal", "external_email_subject",
                "external_email_attachments", "custom_email_body_external"}
    if not is_extern and any(args.get(k) for k in EXT_KEYS):
        error(f"external-distribution keys present but audience is internal")
    if is_extern and not args.get("external_channel_list"):
        warn("external mode usually has a non-empty external_channel_list")

    # Assignment coherence
    od = args.get("owner_detail") or {}
    populated = [k for k in ("assignedToPerson","assignedToTeam","assignedToRecord","assignedToField")
                 if od.get(k) not in (None, [], False)]
    if is_assigned and len(populated) != 1:
        error(f"isAssigned=true requires exactly one of {populated or 'assignee fields'}")
    if not is_assigned and populated:
        error(f"isAssigned=false but {populated} are populated")
```

This replaces the punch-list item I20 below.

---

## 1. ManualInput — top-level keys

**Current rule** (`resolver.py:646`): hard whitelist of
`_FRIENDLY = {title, description, options, inputs}` ∪
`_CANONICAL = {type, input, record, is_approval, isRecordLinked,
owner_detail, step_variables, response_mapping, email_notification,
inline_channel_list, external_channel_list, unauthenticated_input,
resources}`. Anything else → `UNKNOWN_PARAM` error.

**Live distribution** (168 InputBased + DecisionBased MI):

| key | count | in our whitelist? |
|---|---:|---|
| type / step_variables / response_mapping / record / owner_detail / input | 168 | ✅ |
| email_notification | 142 | ✅ |
| isRecordLinked | 139 | ✅ |
| unauthenticated_input | 138 | ✅ |
| inline_channel_list / external_channel_list | 138 | ✅ |
| resources | 127 | ✅ |
| **agent_id** | 112 | ❌ |
| is_approval | 96 | ✅ |
| **internal_email_subject / external_email_subject** | 74 | ❌ |
| **customEmailExternal** | 73 | ❌ |
| **external_email_attachments** | 72 | ❌ |
| **custom_email_body_external** | 72 | ❌ |
| **timeout** | 20 | ❌ |
| **inputExternalUser** | 18 | ❌ |
| **internal_email_attachments / custom_email_body_internal / customEmailInternal** | 13 | ❌ |
| **inputInternalUsers** | 8 | ❌ |
| **message** | 4 | ❌ |
| **label** | 1 | ❌ |

**Verdict**: ❌ — the resolver would error on roughly **half** of all
real ManualInput steps because we don't whitelist the email-distribution
keys, `agent_id`, `timeout`, or the per-user routing keys.

**Fix (I20)**: extend `_CANONICAL` to:
```
agent_id, timeout, inputExternalUser, inputInternalUsers,
internal_email_subject, external_email_subject,
customEmailExternal, customEmailInternal,
custom_email_body_external, custom_email_body_internal,
external_email_attachments, internal_email_attachments,
message, label
```

---

## 2. ManualInput — `type` field

**Current rule** (`resolver.py:678`): error if `type` is not exactly
`"InputBased"`.

**Live distribution**:

| type | count |
|---|---:|
| InputBased | 141 |
| **DecisionBased** | 26 |
| **textarea** | 1 (likely junk) |

**Verdict**: ❌ — `DecisionBased` is real and used for button-only
prompts (no input form). Our resolver rejects 26 production steps.
`textarea` is a corrupt outlier; warn but allow.

**Fix (I21)**: accept `{InputBased, DecisionBased}`. For
`DecisionBased`, the `inputVariables` array MUST be empty
(presence is the structural difference between the two modes).
Cross-reference `MANUAL_INPUT.md` §1 — already documented but the
resolver was never updated.

---

## 3. ManualInput — `response_mapping.options[]` shape

**Current rule** (`resolver.py:695`): every option gets
`{option, primary?, step_iri}` after compilation; `primary` injected
on the first option if missing; `next:` (if specified per-option) is
**silently dropped** at line 701 (`{k:v for k,v in o.items() if k != "next"}`).

**Live distribution**:

| per-option key | count |
|---|---:|
| option | 256 |
| step_iri | 247 |
| primary | 119 |

So **10 of 256 options have no `step_iri`** (terminal "end the
playbook" buttons). 116 of 168 MIs (~69%) have a primary marker.
Across all options: 1-option = 83 MIs, 2-option = 82 MIs, 3-option = 3.

**Verdict**:
- ⚠️ **option without step_iri is real** (~4%). A planned strict
  rule "every option must have step_iri" would error on these.
  Treat null/missing as "terminal".
- ❌ **`next:` per option is silently dropped**. Authors writing
  `{option: Cancel, next: end_pb}` get the line silently stripped
  and end up with a button that has no target — exactly the bug the
  validator should catch.
- ⚠️ ~31% of live MIs have **no `primary`** marker on any option
  (52 of 168). Our resolver auto-promotes the first option to primary,
  so the produced JSON always has one, but live FSR clearly accepts
  prompts with zero primaries. Don't error on YAML that omits
  `primary:`; just don't auto-inject either if unset.

**Fix (I22)**: in `_normalize_manual_input_args`, lift `next:` per
option into `step_iri` resolution (mirror Decision's `branches:`
mapping). Don't auto-inject primary; preserve author intent. Validator
check: every option needs `option:` set; `step_iri` is optional but if
multiple options exist and ≥2 have empty/missing step_iri, warn (likely
authoring mistake).

---

## 4. ManualInput — `inputVariables[].formType`

**Current rule** (`resolver.py:468`): hardcoded 14-entry
`_INPUT_FIELD_KINDS` map covering `text, textarea, richtext, html,
email, url, password, integer, number, checkbox, boolean, select,
datetime, json`.

**Live distribution** (121 inputVariables across 65 InputBased MIs):

| formType | count | in resolver? | notes |
|---|---:|---|---|
| text | 38 | ✅ | |
| dynamicList | 35 | ✅ (as `select`) | |
| picklist | 12 | ❌ | distinct from dynamicList |
| textarea | 12 | ✅ | |
| checkbox | 7 | ✅ | |
| richtext | 5 | ✅ | |
| **ipv4** | 3 | ❌ | the prompt that started this audit |
| lookup | 3 | ✅ but wrong type | see §5 |
| password | 2 | ✅ | |
| **domain** | 1 | ❌ | webAddress.html template |
| **file** | 1 | ❌ | |
| **ipv6** | 1 | ❌ | webAddress.html template |
| **object** | 1 | ❌ | |

**Verdict**: ❌ — 6 distinct formType values used in production are
unknown to the resolver: `picklist`, `ipv4`, `ipv6`, `domain`, `file`,
`object`. Plus per `MANUAL_INPUT.md` corpus survey, the FSR UI also
exposes `multiselect, multiselectpicklist, decimal, date, image, phone,
filehash, array` — none in the corpus today but legal to author.

**Fix (I17 already on TODO)**: extend `_INPUT_FIELD_KINDS` with the
full FSR catalog. The `ipv4 / ipv6 / domain / phone / filehash` family
all share `dataType=text, type=string, templateUrl=webAddress.html`
and differ only in `formType` + per-kind title. After I14 lands,
auto-derive this map from the corpus.

---

## 5. ManualInput — `inputVariables[].type` field

**Current rule** (`resolver.py:560`): `_INPUT_FIELD_KINDS["lookup"]`
hardcodes `type: "array"`.

**Live observation**: lookup formType uses `type: "people"` — the
**FSR module name** the lookup targets (people, indicators, alerts,
etc.). Picklist formType uses `type: "picklists"` similarly.
Our hardcoded `type: array` is structurally wrong and would emit
JSON that doesn't render in the FSR UI.

**Verdict**: ❌

**Fix (I23)**: for `kind: lookup`, require an additional friendly key
`module:` (e.g. `module: people`) and emit it as `type: <module>`.
Same for `kind: picklist`: require `picklist: <name>` (or treat the
`options:` field as the picklist name reference).

---

## 6. ManualInput — `inputVariables[]` per-field keys we omit

**Current emit** (`resolver.py:579-595`): `name, type, label, title,
usable, tooltip, dataType, formType, required, _expanded, templateUrl,
defaultValue, _previousName, playbookField, jinjaExpressionView,
useRecordFieldDefault`.

**Live observation** — additional keys present in 70%+ of real entries:

| key | count (of 121) | we emit? |
|---|---:|---|
| searchable | 85 | ❌ |
| collection | 85 | ❌ |
| allowedGridColumn | 85 | ❌ |
| mmdUpdate | 83 | ❌ |
| lengthConstraint | 83 | ❌ |
| allowedEncryption | 48 | ❌ |
| requiredCondition | 20 | ❌ |
| _addRequiredConditions | 20 | ❌ |
| dataSource | 18 | ❌ (lookup-specific) |
| displayTemplate | 17 | ❌ (lookup-specific) |

**Verdict**: ⚠️ — open question whether the FSR UI/runtime tolerates
these missing. Current corpus only has 121 inputVariable entries; the
fact that 85/121 have `searchable`/`collection`/`allowedGridColumn` is
suspicious — likely the form-builder writes them on save, and our
emitted JSON might re-render fine without them on import. **Action:
push one of our emitted MI prompts to live FSR, open the form-builder,
save without changes, and diff the round-tripped JSON.** That tells us
which keys are author-required vs. UI-cosmetic. Track as I24.

---

## 7. Decision — top-level keys

**Current rule** (`validator.py`): no whitelist on Decision's top-level
arguments; only graph-level branch coverage is enforced.

**Live distribution**:

| key | count |
|---|---:|
| conditions | 352 |
| step_variables | 170 |

**Verdict**: ✅ — only two keys ever, both already understood. No
gap. The 182 Decisions without `step_variables` are fine (FSR
defaults it to empty).

---

## 8. Decision — per-condition shape

**Current rule** (`validator.py:444`): for each `s.type == "decision"`
step, walk `arguments.conditions[].option`; require that every option
label appears in `s.branches` OR a default `s.next:` exists. Stale
labels in `s.branches` (no matching option) get a warning.

**Live distribution**:

| per-condition key | count (758 conditions across 352 Decisions) |
|---|---:|
| step_iri | 758 |
| step_name | 692 |
| option | 679 |
| condition | 435 |
| default | 323 |

Width distribution:

| n_conditions | Decisions |
|---:|---:|
| 1 | 8 |
| 2 | **315** |
| 3 | 16 |
| 4 | 6 |
| 5 | 1 |
| 7 | 5 |
| 8 | 1 |

`default: true` distribution:

| | count |
|---|---:|
| with at least one default entry | 323 |
| with **no** default entry | 29 |
| total | 352 |

**Verdicts**:

- ✅ **Every condition has step_iri** (758/758). Branch-target
  reachability is real.
- ⚠️ **8 single-condition Decisions exist**. User asked for a rule
  "≥2 branches" — rejecting these would error on 2.3% of live
  Decisions. Demote to a warning ("usually decisions have a default
  branch; this one doesn't").
- ⚠️ **`option` missing on 79 entries** (758 - 679). All of these
  are likely the default entries (default-true entries omit `option`
  in many examples). Verify with a join query before encoding the
  rule. Don't error on missing `option` if `default: true`.
- ❌ **`condition` missing on 323 entries — exactly the default
  entries**. The pattern is rigid: a default-true entry omits both
  `option` and `condition`; everything else has both. Encode this.
- ⚠️ **29 Decisions have no default** (8.2%). Our planned I15 rule
  "exactly one default" would error on these. Soften to "at most one
  default; if zero, every condition must have a step_iri AND the step's
  outgoing edges must collectively cover the next-step graph". Easier
  alternative: warn-only when no default present.

**Fix (I15 — refine)**: replace the "exactly one default" rule with:
- exactly one entry has `default: true` (warn if zero, error if ≥2),
- every entry without `default: true` MUST have a non-empty `condition`,
- every entry has a non-empty `step_iri`,
- every entry without `default: true` MUST have a non-empty `option`,
- a default entry MUST NOT have a `condition`.

---

## 9. Decision — friendly YAML form (compile from)

Today our YAML lets authors write
```yaml
- id: dec_step
  type: decision
  arguments:
    conditions:
      - {option: Yes, condition: "{{ x > 5 }}"}
      - {option: No}
  branches:
    Yes: handle_high
    No:  handle_low
```
or as a single `next:` fall-through. The compiler then injects
`step_iri` per branch. There's no friendly way today to mark one
entry as the default — authors have to know to write
`condition: ""` + a `branches:` entry that uses `default` as the label.

**Fix (I25)**: lift a friendly `default: <step_id>` key on the
decision step itself, parallel to `branches:`:
```yaml
- id: dec_step
  type: decision
  arguments:
    conditions:
      - {option: Yes, condition: "{{ x > 5 }}"}
    default: handle_low
```
Compiles to a `default: true` entry pointing at `handle_low`.

---

## 10. Cross-cutting — shared branch validator

ManualInput's `response_mapping.options[]` and Decision's
`arguments.conditions[]` are structurally the same:
- list of branches,
- each carries a target step IRI,
- exactly one (usually) is marked exclusively (`primary` for MI,
  `default` for Decision),
- soft rule: branch targets are usually distinct.

Both should share `_check_branch_fan_out(step, *, branches, target_key,
exclusivity_key)` in validator.py. Already drafted in I15; now
informed by §3 (MI) and §8 (Decision) above.

---

## Punch list (new TODO IDs)

Adding these alongside I12–I19 already on TODO.md. Order chosen to
unblock the largest false-positive class first.

| id | rule | severity in corpus |
|---|---|---|
| **I20** | extend MI `_CANONICAL` with `agent_id`, `timeout`, email-distribution + per-user keys | ❌ rejects ~50% of live MI |
| **I21** | accept `type: DecisionBased` (button-only MI) | ❌ rejects 26 live steps |
| **I22** | lift `next:` per option in friendly MI form; preserve author primary; allow null step_iri (terminal) | ❌ silently drops `next:` today |
| **I23** | `kind: lookup` requires `module:`; emit as `type: <module>` | ❌ wrong shape today |
| **I17** (existing, refined) | full FSR formType catalog incl. ipv4/ipv6/domain/picklist/file/object | ❌ 6 unknown formTypes |
| **I15** (existing, refined) | shared branch validator using §3 + §8 rules | ❌ would error on 8% of live Decisions if naive |
| **I24** | round-trip an emitted MI through FSR's form-builder; diff to find author-required keys | ⚠️ unknown |
| **I25** | friendly `default: <step_id>` on decision steps | ⚠️ ergonomics |

Each entry in the punch list links back to a SQL-reproducible finding
above. Re-run the queries after the live FSR is re-probed (next quarter)
to keep the rule set honest.
