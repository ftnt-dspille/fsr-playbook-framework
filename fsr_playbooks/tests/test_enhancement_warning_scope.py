"""An enhancement offer's warnings are about the EDIT, not the whole playbook.

verify_playbook lints the entire after-document, so the offer card for a
one-step edit listed every lint the analyst's playbook already carried (live:
~20 warnings, nearly all on untouched steps, in compiler wording with JSON
paths). verify_enhancement now tags each warning with the step it is about,
whether this edit touched that step, and a readable sentence; the card leads
with the edit's own warnings and folds the rest into a count.
"""
from fsr_playbooks.compiler import parse_yaml
from fsr_playbooks.mcp_server.tools_enhancement import (
    _scope_warnings,
    verify_enhancement,
)

_BEFORE = """
collection: C
description: d
playbooks:
  - name: P
    description: d
    steps:
      - name: start
        type: start
        next: Enrich IP
      - name: Enrich IP
        type: set_variable
        next: Note It
        vars:
          reputation: "{{ vars.alert_metadata.ip }}"
      - name: Note It
        type: set_variable
        vars:
          note: done
"""

# The edit adds "Extra", whose own reference is undefined. "Enrich IP"'s
# undefined `vars.alert_metadata` was already there.
_AFTER = _BEFORE.replace("""          note: done
""", """          note: done
        next: Extra
      - name: Extra
        type: set_variable
        vars:
          x: "{{ vars.steps.Enrich_IP.foo.bar }}"
""")


def _by_step(result):
    return {w["step_name"]: w for w in result["warnings"]}


def test_each_warning_names_its_step_and_whether_the_edit_touched_it():
    ws = _by_step(verify_enhancement(_BEFORE, _AFTER))
    assert ws["Extra"]["in_change"] is True
    assert ws["Enrich IP"]["in_change"] is False


def test_warnings_read_as_sentences_not_compiler_output():
    ws = _by_step(verify_enhancement(_BEFORE, _AFTER))
    assert ws["Enrich IP"]["plain"] == (
        "vars.alert_metadata is never set before this step, so it will be "
        "empty when the playbook runs.")
    assert ws["Extra"]["plain"] == (
        "Reads 'foo' from step 'Enrich IP', which that step does not return.")
    # The original stays for the model and for anyone debugging.
    assert "Jinja reference" in ws["Enrich IP"]["message"]


def test_one_reference_reported_by_two_verifiers_is_listed_once():
    # bad_value and bad_var_reference both flag vars.steps.Enrich_IP.foo.
    extra = [w for w in verify_enhancement(_BEFORE, _AFTER)["warnings"]
             if w["step_name"] == "Extra"]
    assert len(extra) == 1


def test_a_warning_no_step_claims_stays_in_view():
    coll, _ = parse_yaml(_AFTER)
    out = _scope_warnings([{"message": "collection-level note"}], coll,
                          {"steps_added": [], "steps_modified": []})
    assert out[0]["step_name"] is None and out[0]["in_change"] is True
    assert out[0]["plain"] == "collection-level note"


def test_step_slug_and_dotted_paths_resolve_too():
    coll, _ = parse_yaml(_AFTER)
    out = _scope_warnings(
        [{"code": "unknown_shape_downstream_reference", "step": "enrich_ip",
          "path": "arguments.reputation",
          "message": "vars.steps.X.y resolves through unknown shape (r)"},
         {"message": "m in step 'note_it': other", "path": "P.note_it"}],
        coll, {"steps_added": ["Extra"], "steps_modified": []})
    assert [w["step_name"] for w in out] == ["Enrich IP", "Note It"]
    assert out[0]["plain"].startswith("vars.steps.X.y reads a connector result")
    assert out[1]["plain"] == "m: other"
