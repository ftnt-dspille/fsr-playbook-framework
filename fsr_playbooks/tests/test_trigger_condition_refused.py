"""A record trigger's `condition:` is refused: it is never read, so the playbook ran on every record."""
from fsr_playbooks._db import default_db_path
from fsr_playbooks.compiler import compile_yaml


def _yaml(extra):
    return ("collection: C\nplaybooks:\n- name: P\n  steps:\n"
            "  - name: Start\n    type: start_on_create\n    module: alerts\n" + extra +
            "    next: Note\n  - name: Note\n    type: set_variable\n    vars: {a: 1}\n")


def test_condition_on_a_record_trigger_is_an_error_pointing_at_when():
    r = compile_yaml(_yaml("    condition: \"{{ vars.input.records[0].name.startswith('x') }}\"\n"),
                     default_db_path())
    assert not r.ok
    [e] = [e for e in r.errors if "condition" in e.message]
    assert "every record" in e.message and "when:" in e.suggestion


def test_a_when_filter_compiles():
    r = compile_yaml(_yaml("    when: {logic: AND, filters: [{field: name, op: like, value: 'x%'}]}\n"),
                     default_db_path())
    assert r.ok, r.errors


def _start(extra, module=""):
    return ("collection: C\nplaybooks:\n- name: P\n  steps:\n"
            "  - name: Start\n    type: start\n" + module + extra +
            "    next: Note\n  - name: Note\n    type: set_variable\n    vars: {a: 1}\n")


def test_an_unknown_key_on_a_manual_start_is_refused():
    r = compile_yaml(_start("    bogus_key: 1\n"), default_db_path())
    assert not r.ok and any("bogus_key" in e.message for e in r.errors)


def test_an_unknown_key_on_a_record_action_start_is_refused():
    r = compile_yaml(_start("    buton_label: Go\n", "    module: alerts\n"), default_db_path())
    assert not r.ok and any("buton_label" in e.message for e in r.errors)


def test_a_documented_record_action_start_compiles():
    r = compile_yaml(_start("    button_label: Go\n    requires_record: true\n    run_mode: per_record\n",
                            "    module: alerts\n"), default_db_path())
    assert r.ok, r.errors
