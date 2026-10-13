"""A document with no `playbooks:` list says what it is instead.

Live, a turn sent a ZTPF template (name, outputType, script) to validate_yaml,
got only "at least one playbook is required", and stopped. The refusal now
names the document's keys and the tool that takes them.
"""
from __future__ import annotations

from fsr_playbooks.compiler.parser import parse_yaml


def _missing(text):
    _, errors = parse_yaml(text)
    (err,) = [e for e in errors if e.path == "playbooks"]
    return err.message


def test_a_record_is_told_it_is_not_a_playbook_and_where_it_goes():
    msg = _missing("name: Interfaces\noutputType: /api/3/picklists/x\nscript: '{{ x }}'\n")
    assert msg.startswith("at least one playbook is required")
    assert "not playbook YAML (its keys: name, outputType, script)" in msg
    assert "create_record or update_record" in msg


def test_one_unwrapped_playbook_is_told_to_wrap_it():
    msg = _missing("name: Enrich\nsteps:\n  - name: Start\n")
    assert "put it under `playbooks:` as a list item" in msg


def test_an_empty_playbooks_list_adds_nothing_misleading():
    msg = _missing("collection: X\nplaybooks: []\n")
    assert "playbook YAML (its keys" not in msg
