"""Strict whitelist + canonical-form pass-through for manual_input.

Regression coverage for the silent-drop trap that produced the
screenshot-YAML bug: the resolver used to accept any top-level keys on
manual_input (including `label`, `message`, `type: textarea`) and
silently fill in defaults, leaving the deployed step rendering only a
default Continue button.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.errors import ErrorCode


def _wrap(args_block: str, options_block: str = "") -> str:
    """Wrap a manual_input arguments block in a minimal compilable
    playbook. `args_block` goes under `arguments:` (8-space-indented).
    `options_block` goes at step level (6-space-indented) and provides
    the options list when needed."""
    opt = options_block if options_block else "        options:\n          - display: stop\n            next: stop\n"
    return f"""
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
{args_block}{opt}
      - name: stop
        type: end
"""


# ---- friendly form -----------------------------------------------

def test_friendly_form_compiles_clean(db_path):
    text = _wrap(
        "          title: Approve?\n"
        "          description: Click approve\n",
        options_block=(
            "        options:\n"
            "          - display: approve\n"
            "            primary: true\n"
            "            next: stop\n"
            "          - display: reject\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_friendly_form_options_string_shorthand(db_path):
    """Options list with display + next."""
    text = _wrap(
        "          title: Pick\n",
        options_block=(
            "        options:\n"
            "          - display: approve\n"
            "            next: stop\n"
            "          - display: reject\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_friendly_form_default_continue_when_no_options(db_path):
    """No options at all → resolver supplies a primary 'Continue'."""
    text = _wrap(
        "          title: Continue?\n",
        options_block="        next: stop\n",
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


# ---- canonical wire form -----------------------------------------

def test_canonical_form_passes_through(db_path):
    """An author who hand-writes the full FSR shape should not get
    rejected — every key is on the canonical whitelist."""
    text = _wrap(
        "          type: InputBased\n"
        "          input:\n"
        "            schema:\n"
        "              title: T\n"
        "              description: D\n"
        "              inputVariables: []\n"
        "          response_mapping:\n"
        "            options:\n"
        "              - {option: Continue, primary: true}\n"
        "            duplicateOption: false\n"
        "            customSuccessMessage: ok\n"
        "          record: ''\n"
        "          owner_detail: {isAssigned: false}\n"
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


# ---- previously-rejected keys now accepted (live corpus shows usage) -----

def test_label_message_timeout_now_accepted(db_path):
    """`label`, `message`, and `timeout` were originally rejected as
    unknown — but the live FSR corpus shows real ManualInputs use all
    three (label 1×, message 4×, timeout 20× across 168 live MIs). After
    audit §0 the resolver accepts them. Junk keys still get caught
    (test_unknown_key_truly_unknown_rejected below).
    """
    for friendly in ("label: Message", "message: hello", "timeout: 3600"):
        text = _wrap(f"          {friendly}\n")
        r = compile_yaml(text, db_path)
        assert r.ok, [str(e) for e in r.errors]


def test_unknown_key_truly_unknown_rejected(db_path):
    """Genuine typos / nonsense keys are still caught."""
    text = _wrap("          floopwidget: 42\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.UNKNOWN_PARAM)
    assert "floopwidget" in e.message


# ---- the trap: bad `type` value ----------------------------------

def test_type_textarea_rejected(db_path):
    """`type: textarea` is not a real FSR ManualInput dispatch."""
    text = _wrap("          type: textarea\n          title: hi\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.BAD_VALUE)
    assert "InputBased" in e.message


def test_type_single_select_rejected(db_path):
    """Old `type: single-select` shape — pre-fix examples used it."""
    text = _wrap("          type: single-select\n          title: hi\n")
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.BAD_VALUE)
    assert "InputBased" in e.message


# ---- the trap: input must be a dict ------------------------------

def test_input_string_rejected_with_pointer(db_path):
    """An LLM that emits `input: "some string"` would crash FSR with
    `'str' object has no attribute 'get'`. Resolver catches it early
    and points to the right shape."""
    text = _wrap('          input: "some string"\n')
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.BAD_VALUE)
    assert "must be a mapping" in e.message


# ---- audit-driven additions (2026-05-06): I17, I20, I21, I22, I23 ------

def test_type_decision_based_accepted(db_path):
    """`type: DecisionBased` is real (button-only prompts, 26/168 live).
    Audit §2 — used to be a hard error."""
    text = _wrap(
        "          type: DecisionBased\n",
        options_block=(
            "        options:\n"
            "          - display: Continue\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_description_defaults_to_title_when_omitted(db_path):
    """AGENT_DX_PLAN D1 — a manual_input with no `description:` used to emit an
    empty description body, which validates offline but FSR's runtime rejects.
    The description now falls back to the title so the prompt still runs."""
    text = _wrap("          title: Approve the heist?\n")
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    schema = r.fsr_json["data"][0]["workflows"][0]["steps"][1]["arguments"]\
        ["input"]["schema"]
    assert schema["title"] == "Approve the heist?"
    assert schema["description"] == "Approve the heist?"


def test_explicit_description_is_preserved(db_path):
    """An explicit description must win over the title fallback."""
    text = _wrap(
        "          title: Approve?\n"
        "          description: Read carefully before approving\n"
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    schema = r.fsr_json["data"][0]["workflows"][0]["steps"][1]["arguments"]\
        ["input"]["schema"]
    assert schema["description"] == "Read carefully before approving"


def test_kind_ipv4_compiles(db_path):
    """I17 — formType=ipv4 was never in our whitelist, but live FSR
    uses it (audit §4). Should now compile and emit the webAddress
    template."""
    text = _wrap(
        "          title: Enter IP\n"
        "          inputs:\n"
        "            - {name: ip, kind: ipv4, label: Address, required: true}\n"
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    iv = r.fsr_json["data"][0]["workflows"][0]["steps"][1]["arguments"]\
        ["input"]["schema"]["inputVariables"]
    assert iv[0]["formType"] == "ipv4"
    assert iv[0]["templateUrl"].endswith("/webAddress.html")
    assert iv[0]["title"] == "IPv4"


def test_kind_lookup_requires_module(db_path):
    """I23 — `kind: lookup` without a `module:` key has no target;
    FSR's typeahead won't render."""
    text = _wrap(
        "          inputs:\n"
        "            - {name: who, kind: lookup, label: Who}\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    e = next(e for e in r.errors if e.code is ErrorCode.MISSING_FIELD
             and "module" in e.message)
    assert e is not None


def test_kind_lookup_with_module_emits_module_as_type(db_path):
    """Live FSR uses the module name as the `type` field on lookup
    inputVariables (audit §5)."""
    text = _wrap(
        "          inputs:\n"
        "            - {name: who, kind: lookup, module: people}\n"
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    iv = r.fsr_json["data"][0]["workflows"][0]["steps"][1]["arguments"]\
        ["input"]["schema"]["inputVariables"]
    assert iv[0]["formType"] == "lookup"
    assert iv[0]["type"] == "people"


def test_kind_picklist_requires_picklist_name(db_path):
    text = _wrap(
        "          inputs:\n"
        "            - {name: sev, kind: picklist}\n"
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(e.code is ErrorCode.MISSING_FIELD and "picklist" in e.message
               for e in r.errors)


def test_per_option_next_promoted_to_branches(db_path):
    """I22 — friendly `next:` per option used to be silently dropped."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        arguments:
          title: Approve?
        options:
          - display: ok
            primary: true
            next: stop
          - display: cancel
            next: cleanup
      - name: cleanup
        type: end
        next: stop
      - name: stop
        type: end
"""
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    # Two distinct step_iri targets emitted, one per option.
    rmap = r.fsr_json["data"][0]["workflows"][0]["steps"][1]\
        ["arguments"]["response_mapping"]
    iris = [o.get("step_iri") for o in rmap["options"]]
    assert all(iris)
    assert iris[0] != iris[1]


def _step_level_inputs_pb(extra_step_keys: str) -> str:
    """A manual_input whose form fields/title/description are written at the
    STEP level (the shape the YAML reference guide documents), not under
    `arguments:`. `extra_step_keys` is 8-space-indented step-level YAML."""
    return f"""
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
{extra_step_keys}        options:
          - display: Submit
            primary: true
            next: stop
      - name: stop
        type: end
"""


def test_step_level_inputs_title_description_hoisted(db_path):
    """Step-level `inputs:`/`title:`/`description:` must reach the wire schema.

    Regression: the parser hoisted step-level `options:` but not `inputs:`/
    `title:`/`description:`, so a prompt authored in the documented step-level
    shape shipped with an empty form (`inputVariables: []`) and title/description
    falling back to the step name. They must now hoist like `options:`."""
    text = _step_level_inputs_pb(
        "        title: Enter a six digit number\n"
        "        description: Exactly 6 digits please.\n"
        "        inputs:\n"
        "          - {name: my_number, kind: integer, label: My Number, required: true}\n"
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    schema = r.fsr_json["data"][0]["workflows"][0]["steps"][1]["arguments"]\
        ["input"]["schema"]
    assert schema["title"] == "Enter a six digit number"
    assert schema["description"] == "Exactly 6 digits please."
    iv = schema["inputVariables"]
    assert len(iv) == 1 and iv[0]["name"] == "my_number"
    assert iv[0]["formType"] == "integer"


def test_step_level_inputs_match_live_playbook_wire_shape(db_path):
    """Grounded in a live FortiSOAR prompt (step_examples provenance
    `step:00c8a0b4-6633-4bd6-89d5-bf0abb6230d5`): an InputBased manual_input
    declaring one "Dynamic List" field. Authoring it in the documented
    step-level friendly form (`kind: select`) must reproduce the captured wire
    tuple — formType/dataType `dynamicList`, type `array` — proving the hoist
    fix yields the real platform shape, not an empty form."""
    text = _step_level_inputs_pb(
        "        title: test\n"
        "        description: test\n"
        "        inputs:\n"
        "          - {name: test, kind: select, label: test, "
        'options: "{{ vars.dyn_list }}"}\n'
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]
    iv = r.fsr_json["data"][0]["workflows"][0]["steps"][1]["arguments"]\
        ["input"]["schema"]["inputVariables"]
    assert len(iv) == 1
    f = iv[0]
    # Field tuple captured from the live appliance playbook.
    assert f["name"] == "test"
    assert f["formType"] == "dynamicList"
    assert f["dataType"] == "dynamicList"
    assert f["type"] == "array"
    assert f["templateUrl"].endswith("/dynamicList.html")
    assert f["options"] == "{{ vars.dyn_list }}"


def test_step_level_and_arguments_inputs_conflict_errors(db_path):
    """Same key at step level and under `arguments:` is a hard error, not a
    silent winner (mirrors the global hoist conflict guard)."""
    text = """
collection: T
visible: true
playbooks:
  - name: P
    is_active: false
    steps:
      - name: start
        type: start
        next: ask
      - name: ask
        type: manual_input
        title: Step Level Title
        arguments:
          title: Arguments Title
        options:
          - display: Submit
            primary: true
            next: stop
      - name: stop
        type: end
"""
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any(e.code is ErrorCode.BAD_VALUE and "both at" in e.message
               for e in r.errors)


def test_mode_record_linked_requires_record(db_path):
    """I20 — Context mode coherence: isRecordLinked=true ⟹ record set."""
    text = _wrap(
        "          isRecordLinked: true\n",
        options_block=(
            "        options:\n"
            "          - display: ok\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("isRecordLinked=true requires" in e.message for e in r.errors)


def test_mode_external_keys_in_internal_prompt_rejected(db_path):
    """I20 — Audience mode coherence: external email-distribution keys
    require unauthenticated_input or inputExternalUser to be true."""
    text = _wrap(
        "          customEmailExternal: 'subj'\n",
        options_block=(
            "        options:\n"
            "          - display: ok\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("external-distribution key" in e.message for e in r.errors)


def test_mode_external_with_unauthenticated_ok(db_path):
    """Same keys are valid once unauthenticated_input is on."""
    text = _wrap(
        "          unauthenticated_input: true\n"
        "          inputExternalUser: true\n"
        "          customEmailExternal: 'subj'\n"
        "          external_channel_list: ['/api/3/picklists/abc']\n",
        options_block=(
            "        options:\n"
            "          - display: ok\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert r.ok, [str(e) for e in r.errors]


def test_mode_assignment_requires_exactly_one_target(db_path):
    """I20 — Assignment mode coherence: isAssigned=true ⟹ exactly one
    of assignedToPerson/Team/Record/Field set."""
    text = _wrap(
        "          owner_detail:\n"
        "            isAssigned: true\n",
        options_block=(
            "        options:\n"
            "          - display: ok\n"
            "            next: stop\n"
        ),
    )
    r = compile_yaml(text, db_path)
    assert not r.ok
    assert any("isAssigned=true requires" in e.message for e in r.errors)
