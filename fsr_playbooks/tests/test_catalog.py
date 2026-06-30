"""Tests for the public step-type catalog (:mod:`fsr_playbooks.catalog`)."""

from __future__ import annotations

import pytest

from fsr_playbooks.catalog import StepHelp, StepTypeInfo, list_step_types, step_help


def test_list_step_types_nonempty_and_sorted():
    infos = list_step_types()
    assert infos, "catalog should list at least the core step types"
    assert all(isinstance(i, StepTypeInfo) for i in infos)
    shorts = [i.short for i in infos]
    assert shorts == sorted(shorts), "entries are sorted by friendly short name"
    # Every entry maps to a non-empty canonical name and carries a purpose line.
    for i in infos:
        assert i.canonical
        assert i.purpose


def test_list_step_types_covers_common_types():
    shorts = {i.short for i in list_step_types()}
    for expected in ("set_variable", "decision", "connector", "manual_input"):
        assert expected in shorts


def test_step_help_by_short_name():
    h = step_help("manual_input")
    assert isinstance(h, StepHelp)
    assert h.short == "manual_input"
    assert h.canonical == "ManualInput"
    assert h.label
    assert h.example_yaml, "manual_input has a curated example"
    assert "manual_input" in h.example_yaml


def test_step_help_by_canonical_name():
    h = step_help("SetVariable")
    assert h.short == "set_variable"
    assert h.canonical == "SetVariable"


def test_step_help_modeled_carries_arg_schema():
    h = step_help("set_variable")
    if h.modeled:
        assert isinstance(h.arg_schema, dict)


def test_step_help_unknown_raises_with_suggestion():
    with pytest.raises(KeyError) as exc:
        step_help("manual_inpt")  # typo
    assert "Did you mean" in str(exc.value)
