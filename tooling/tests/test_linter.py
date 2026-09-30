"""Linter v1 -- Norway problem, step-name charset, mock_result on Fetch.

Each rule has a positive (catches the foot-gun) and a negative (clean
input passes) case so future refactors can't silently weaken the linter.
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml


def _codes(r) -> list[str]:
    return [e.code.value for e in r.errors]


def _messages(r) -> list[str]:
    return [e.message for e in r.errors]


# ---- Norway problem ------------------------------------------------------

NORWAY_BAD = """
collection: Norway
playbooks:
  - name: pb
    parameters: [go]
    steps:
      - name: trigger
        type: start
        next: choose
      - name: choose
        type: decision
        conditions:
          - display: yes
            when: "{{ vars.input.params.go == 'yes' }}"
            next: act
          - display: Else
            default: true
            next: skip
      - name: act
        type: set_variable
        vars: { x: 1 }
      - name: skip
        type: set_variable
        vars: { x: 0 }
"""

NORWAY_OK = NORWAY_BAD.replace("display: yes", 'display: "yes"')


def test_norway_bare_yes_in_display_caught(db_path):
    r = compile_yaml(NORWAY_BAD, db_path)
    assert not r.ok
    msgs = " ".join(_messages(r))
    assert "display value 'yes'" in msgs


def test_norway_quoted_yes_passes(db_path):
    r = compile_yaml(NORWAY_OK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- Step-name charset ---------------------------------------------------

NAME_BAD = """
collection: Names
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: "Hello -- World? (yes)"
      - name: "Hello -- World? (yes)"
        type: set_variable
        vars: { x: 1 }
"""

NAME_OK = NAME_BAD.replace(
    'Hello -- World? (yes)',
    'Hello World yes',
)


def test_step_name_with_dash_paren_em_dash_auto_rewritten(db_path):
    r = compile_yaml(NAME_BAD, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    # Linter emits a warning explaining the auto-rename.
    warnings = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warnings)
    assert "auto-renamed" in msgs
    # The compiled JSON has the cleaned name (no em-dash / paren / ?).
    steps = r.fsr_json["data"][0]["workflows"][0]["steps"]
    assert any(_BAD_CHAR not in s["name"]
               for s in steps for _BAD_CHAR in "--()?")


def test_step_name_clean_passes(db_path):
    r = compile_yaml(NAME_OK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]


# ---- mock_result on Fetch ------------------------------------------------

FETCH_NO_MOCK = """
collection: F
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Fetch alerts from VirusTotal
      - name: Fetch alerts from VirusTotal
        type: connector
        connector: virustotal
        operation: query_url
        url: "https://example.com"
"""

FETCH_WITH_MOCK = FETCH_NO_MOCK.replace(
    'url: "https://example.com"',
    'url: "https://example.com"\n        mock_result:\n          status: success',
)


def test_fetch_step_without_mock_emits_warning(db_path):
    r = compile_yaml(FETCH_NO_MOCK, db_path)
    # Warning, not error -- compile still succeeds.
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert any("mock_result" in w.message for w in warns)
    assert any("Fetch alerts from VirusTotal" in w.message for w in warns)


def test_fetch_step_with_mock_clean(db_path):
    r = compile_yaml(FETCH_WITH_MOCK, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert not any("mock_result" in w.message for w in warns)


# ---- Sanity: linter ignores yes-shaped keys outside `branches:` ---------

def test_linter_does_not_misfire_on_unrelated_yes_key(db_path):
    """A `yes:` key inside `vars:` is fine -- the Norway rule only
    fires for `display:` values on decision/manual_input branches."""
    text = """
collection: T
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: a
      - name: a
        type: set_variable
        vars:
          ok_value: 1
"""
    r = compile_yaml(text, db_path)
    assert not any("YAML 1.1 boolean" in (e.message or "")
                   for e in r.errors)


# ---- Mock connector/code_snippet `.data` ref (empty in --mock) ------------

# A connector step that carries a mock_result. Downstream reads via `.data`
# -- which renders EMPTY in a --mock run (mock_result is returned verbatim,
# no {data,status,message,operation} envelope). The linter must warn.
MOCK_CONNECTOR_DATA_REF = """
collection: M
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Fetch
      - name: Fetch
        type: connector
        connector: virustotal
        operation: query_ip
        next: Capture
        ip: "8.8.8.8"
        mock_result:
          value:
            - id: alert-1
      - name: Capture
        type: set_variable
        vars:
          n: "{{ vars.steps.Fetch.data.value | length }}"
"""

# Same shape but the downstream reference uses the direct path (correct for
# --mock). No warning expected.
MOCK_CONNECTOR_DIRECT_REF = MOCK_CONNECTOR_DATA_REF.replace(
    "vars.steps.Fetch.data.value",
    "vars.steps.Fetch.value",
)

# A code_snippet step with a mock_result, referenced downstream via `.data`.
MOCK_SNIPPET_DATA_REF = """
collection: S
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Compute
      - name: Compute
        type: code_snippet
        next: Capture
        code: |
          print({'probe': 'hello'})
        mock_result:
          code_output:
            probe: hello
      - name: Capture
        type: set_variable
        vars:
          p: "{{ vars.steps.Compute.data.code_output.probe }}"
"""

MOCK_SNIPPET_DIRECT_REF = MOCK_SNIPPET_DATA_REF.replace(
    "vars.steps.Compute.data.code_output.probe",
    "vars.steps.Compute.code_output.probe",
)


def test_mock_connector_data_ref_warns(db_path):
    r = compile_yaml(MOCK_CONNECTOR_DATA_REF, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("Fetch.data.value" in msgs and "mock_result" in msgs for w in warns), msgs


def test_mock_connector_direct_ref_clean(db_path):
    r = compile_yaml(MOCK_CONNECTOR_DIRECT_REF, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert not any("mock_result" in (w.message or "") and "Fetch" in (w.message or "")
                   for w in warns)


def test_mock_code_snippet_data_ref_warns(db_path):
    r = compile_yaml(MOCK_SNIPPET_DATA_REF, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("Compute.data.code_output" in msgs and "mock_result" in msgs for w in warns), msgs


def test_mock_code_snippet_direct_ref_clean(db_path):
    r = compile_yaml(MOCK_SNIPPET_DIRECT_REF, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert not any("mock_result" in (w.message or "") and "Compute" in (w.message or "")
                   for w in warns)


# ---- message: comment without record: ------------------------------------

MSG_NO_RECORD = """
collection: C
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Comment
      - name: Comment
        type: set_variable
        next: Done
        message:
          type: comment
          content: "Test comment"
      - name: Done
        type: end
"""

MSG_WITH_RECORD = """
collection: C
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Comment
      - name: Comment
        type: set_variable
        next: Done
        message:
          type: comment
          content: "Test comment"
          record: "{{ vars.input.records[0]['@id'] }}"
      - name: Done
        type: end
"""

MSG_POST_COMMENT_SUGAR = """
collection: C
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Comment
      - name: Comment
        type: set_variable
        next: Done
        post_comment: "Auto comment"
      - name: Done
        type: end
"""


def test_message_without_record_warns(db_path):
    r = compile_yaml(MSG_NO_RECORD, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("message:" in msgs and "record:" in msgs for w in warns), msgs
    assert any("No record found" in (w.message or "") for w in warns), msgs


def test_message_with_record_clean(db_path):
    r = compile_yaml(MSG_WITH_RECORD, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert not any("message:" in (w.message or "") and "record:" in (w.message or "")
                   for w in warns)


def test_post_comment_sugar_warns(db_path):
    r = compile_yaml(MSG_POST_COMMENT_SUGAR, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("message:" in msgs and "record:" in msgs for w in warns), msgs


# ---- code_snippet .code_output → .data.code_output auto-rewrite -----------

SNIPPET_NO_DATA_REF = """
collection: C
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Compute
      - name: Compute
        type: code_snippet
        next: Capture
        code: |
          print({'probe': 'hello'})
      - name: Capture
        type: set_variable
        next: Done
        vars:
          p: "{{ vars.steps.Compute.code_output.probe }}"
      - name: Done
        type: end
"""


def test_snippet_code_output_auto_rewrite(db_path):
    """code_snippet results are wrapped in {data: {code_output: …}} at runtime;
    a bare `.code_output` ref renders empty. The rewriter must auto-fix it to
    `.data.code_output` and emit a warning."""
    r = compile_yaml(SNIPPET_NO_DATA_REF, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("Compute.code_output" in msgs and ".data.code_output" in msgs
               for w in warns), msgs


# ---- mock_result with `data` key suppresses mock data-ref warning --------

MOCK_WITH_ENVELOPE = """
collection: C
playbooks:
  - name: pb
    steps:
      - name: trigger
        type: start
        next: Compute
      - name: Compute
        type: code_snippet
        next: Capture
        code: |
          print({'probe': 'hello'})
        mock_result:
          data:
            code_output:
              probe: hello
      - name: Capture
        type: set_variable
        next: Done
        vars:
          p: "{{ vars.steps.Compute.data.code_output.probe }}"
      - name: Done
        type: end
"""


def test_mock_result_with_data_key_no_warning(db_path):
    """When mock_result includes a top-level `data` key, the author has shaped
    it to match the production envelope -- `.data` refs work in mock mode and
    the mock data-ref warning should be suppressed."""
    r = compile_yaml(MOCK_WITH_ENVELOPE, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert not any("mock_result" in msgs and "Compute" in msgs for w in warns), msgs


# ---- workflow_reference child terminal check ------------------------------

WF_REF_CHILD_END = """
collection: C
playbooks:
  - name: Parent
    steps:
      - name: trigger
        type: start
        next: Call Child
      - name: Call Child
        type: workflow_reference
        next: Done
        target: Child
      - name: Done
        type: end
  - name: Child
    steps:
      - name: trigger
        type: start
        next: Compute
      - name: Compute
        type: code_snippet
        next: Done
        code: |
          print({'result': 'hello'})
      - name: Done
        type: end
"""

WF_REF_CHILD_EXPORTS = """
collection: C
playbooks:
  - name: Parent
    steps:
      - name: trigger
        type: start
        next: Call Child
      - name: Call Child
        type: workflow_reference
        next: Read
        target: Child
      - name: Read
        type: set_variable
        next: Done
        vars:
          a: "{{ vars.steps.Call_Child.priority }}"
          b: "{{ vars.steps.Call_Child.missing }}"
      - name: Done
        type: end
  - name: Child
    steps:
      - name: trigger
        type: start
        next: Export
      - name: Export
        type: set_variable
        vars:
          priority: high
          classification: manager
"""


def test_wf_ref_child_end_warns(db_path):
    """Child ending with `end` returns {data:null} -- warn the parent gets no data."""
    r = compile_yaml(WF_REF_CHILD_END, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("Call Child" in msgs and "end" in msgs and "set_variable" in msgs
               for w in warns), msgs


def test_wf_ref_child_bad_field_warns(db_path):
    """Parent reads a field the child doesn't export -- warn it evaluates empty."""
    r = compile_yaml(WF_REF_CHILD_EXPORTS, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("missing" in msgs and "Call_Child" in msgs for w in warns), msgs
    # `priority` IS exported -- should not warn about IT evaluating empty
    assert not any("Field 'priority'" in w.message and "will evaluate empty" in w.message
                   for w in warns), msgs


# ---- tojson boolean warning ------------------------------------------------

TOJSON_DANGEROUS = """
collection: C
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Snippet
      - name: Snippet
        type: code_snippet
        next: Done
        code: |
          data = {{ vars.steps.Snippet.data | tojson }}
          print(data)
      - name: Done
        type: end
"""

TOJSON_SAFE_FIELD = """
collection: C
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Other
      - name: Other
        type: set_variable
        next: Snippet
        vars:
          upn: alice
      - name: Snippet
        type: code_snippet
        next: Done
        code: |
          upn = {{ vars.steps.Other.upn | tojson }}
          print(upn)
      - name: Done
        type: end
"""

TOJSON_SAFE_MAP = """
collection: C
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Other
      - name: Other
        type: set_variable
        next: Snippet
        vars:
          address: foo
      - name: Snippet
        type: code_snippet
        next: Done
        code: |
          addrs = {{ vars.steps.Other | map(attribute='address') | list | tojson }}
          print(addrs)
      - name: Done
        type: end
"""


def test_tojson_dangerous_warns(db_path):
    """tojson on whole step result / data envelope / input -- warn."""
    r = compile_yaml(TOJSON_DANGEROUS, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert any("tojson" in msgs and "booleans" in msgs for w in warns), msgs


def test_tojson_safe_field_no_warning(db_path):
    """tojson on a specific leaf field -- safe, no warning."""
    r = compile_yaml(TOJSON_SAFE_FIELD, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert not any("tojson" in msgs and "booleans" in msgs for w in warns), msgs


def test_tojson_safe_map_no_warning(db_path):
    """tojson on map(attribute=...) | list -- safe, no warning."""
    r = compile_yaml(TOJSON_SAFE_MAP, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert not any("tojson" in msgs and "booleans" in msgs for w in warns), msgs


# ---- next: [A, B] fanout syntax + cross-path var access ---------------------

FANOUT_MERGE = """
collection: C
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Split
      - name: Split
        type: set_variable
        next: [Path A, Path B]
        vars:
          split_time: now
      - name: Path A
        type: set_variable
        next: Merge
        vars:
          path_a_value: from_path_a
      - name: Path B
        type: set_variable
        next: Merge
        vars:
          path_b_value: from_path_b
      - name: Merge
        type: code_snippet
        next: Done
        code: |
          a = "{{ vars.path_a_value | default('UNSET') }}"
          b = "{{ vars.path_b_value | default('UNSET') }}"
          print({'path_a': a, 'path_b': b})
      - name: Done
        type: end
"""

DECISION_BRANCH = """
collection: C
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Decide
      - name: Decide
        type: decision
        conditions:
          - display: "Yes"
            when: "{{ true }}"
            next: Path A
          - display: "No"
            default: true
            next: Path B
      - name: Path A
        type: set_variable
        next: Merge
        vars:
          path_a_value: from_path_a
      - name: Path B
        type: set_variable
        next: Merge
        vars:
          path_b_value: from_path_b
      - name: Merge
        type: code_snippet
        next: Done
        code: |
          a = "{{ vars.path_a_value | default('UNSET') }}"
          b = "{{ vars.path_b_value | default('UNSET') }}"
          print({'path_a': a, 'path_b': b})
      - name: Done
        type: end
"""


def test_fanout_next_list_syntax_parses(db_path):
    """`next: [A, B]` should parse as unlabeled_next fanout."""
    from fsr_playbooks.compiler.parser import parse_yaml
    coll, errs = parse_yaml(FANOUT_MERGE)
    assert coll is not None
    by_name = {s.name: s for s in coll.playbooks[0].steps}
    split = by_name["Split"]
    assert split.next is None or split.next == ""
    assert "path_a" in split.unlabeled_next
    assert "path_b" in split.unlabeled_next


def test_fanout_no_cross_path_warning(db_path):
    """Fanout paths share vars at merge -- no var_defined_other_branch warning."""
    r = compile_yaml(FANOUT_MERGE, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    msgs = " ".join(w.message for w in warns)
    assert not any("different branch" in w.message for w in warns), msgs
    assert not any("does not run on branch" in w.message for w in warns), msgs


def test_decision_branch_still_warns(db_path):
    """Decision branches ARE isolated -- var_defined_other_branch should fire."""
    r = compile_yaml(DECISION_BRANCH, db_path)
    assert r.ok, [e.to_dict() for e in r.errors]
    warns = [e for e in r.errors if e.severity == "warning"]
    assert any("different branch" in w.message for w in warns), \
        [w.message for w in warns]

