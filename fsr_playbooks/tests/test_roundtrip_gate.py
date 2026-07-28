"""The round-trip fidelity GATE, and proof it actually catches data loss.

`compiler/roundtrip.py` has the mechanism (decompile -> emit -> semantic diff);
`scripts/corpus_gate.py` runs it over a committed corpus and emits a pass-rate.
This test does two things:

  1. GREEN — the committed synthesized corpus round-trips 100% clean, so
     `make corpus-gate` is a real, passing floor.
  2. RED-PROOF — for each field-class we have watched get silently deleted
     (`for_each`, declared `parameters`), reintroduce the loss on the emit side
     and assert the gate goes RED *and names the lost field*. Per
     [[tests_inherit_the_fixs_blind_spots]]: a gate that never goes red on the
     bug it exists to catch is not a gate.

The RED-proof patches the emitter the gate calls, rather than a hand-diff of two
dicts, so it exercises the real `roundtrip()` code path — the same function the
corpus runner calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import fsr_playbooks.compiler.roundtrip as rt
from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler.roundtrip import roundtrip

import sys
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import corpus_gate  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "roundtrip_corpus"


def _load(name: str) -> dict:
    payload = json.loads((CORPUS_DIR / f"{name}.json").read_text())
    return payload["envelope"]


# --------------------------------------------------------------------------- #
# 1. GREEN — the committed corpus is a passing floor.
# --------------------------------------------------------------------------- #

def test_corpus_dir_is_populated():
    files = list(CORPUS_DIR.glob("*.json"))
    assert files, (
        "no committed round-trip corpus — run scripts/gen_roundtrip_corpus.py")
    # The two historically-lost classes must both be represented, or the gate
    # is green for the wrong reason.
    names = {f.stem for f in files}
    assert "for_each_loop" in names
    assert "declared_parameters" in names
    assert "trigger_parameters" in names


def test_whole_corpus_round_trips_clean():
    passed, total, failures = corpus_gate.run_gate(CORPUS_DIR, PACKAGED_SLIM_DB)
    assert failures == [], f"corpus regressed: {failures}"
    assert passed == total > 0


def test_gate_main_exits_zero_on_clean_corpus():
    rc = corpus_gate.main(["--corpus-dir", str(CORPUS_DIR)])
    assert rc == 0


# --------------------------------------------------------------------------- #
# 2. RED-PROOF — reintroduce each loss on the emit side; the gate must catch it.
# --------------------------------------------------------------------------- #

def _emit_dropping(field_mutator):
    """Wrap the real emitter so its output has a field stripped — i.e. simulate
    a decompiler/emitter that fails to write that field back. Returns a
    drop-in for `roundtrip.emit`."""
    real_emit = rt.emit

    def _patched(ir):
        wire = real_emit(ir)
        for wf in wire["data"][0]["workflows"]:
            for step in wf.get("steps", []):
                field_mutator(wf, step)
        return wire

    return _patched


def test_gate_goes_red_when_for_each_is_dropped(monkeypatch):
    """The original `for_each` bug: the emitter never wrote the loop back."""
    def drop_for_each(_wf, step):
        (step.get("arguments") or {}).pop("for_each", None)

    monkeypatch.setattr(rt, "emit", _emit_dropping(drop_for_each))

    ok, diffs = roundtrip(_load("for_each_loop"), PACKAGED_SLIM_DB)
    assert not ok, "gate stayed GREEN with for_each dropped — it is blind to it"
    assert any("for_each" in d for d in diffs), (
        f"gate went red but did not name for_each: {diffs}")


def test_gate_goes_red_when_top_level_parameters_are_dropped(monkeypatch):
    """The `parameters` bug, top-level-declared shape: the manual-trigger input
    form did not survive. Reintroduce by clearing the emitted top-level list."""
    def drop_params(wf, _step):
        wf["parameters"] = []

    monkeypatch.setattr(rt, "emit", _emit_dropping(drop_params))

    ok, diffs = roundtrip(_load("declared_parameters"), PACKAGED_SLIM_DB)
    assert not ok, "gate stayed GREEN with declared parameters dropped"
    assert any("parameters" in d for d in diffs), (
        f"gate went red but did not name parameters: {diffs}")


def test_gate_goes_red_when_trigger_input_variables_are_dropped(monkeypatch):
    """The real F4 shape: parameters declared on the trigger's `inputVariables`
    with an empty top-level list. This is the shape whose loss (42 of 122 hard
    failures) motivated the union in the decompiler — drop the input vars and
    the projection must see fewer declared parameters and go red.
    """
    def drop_input_vars(_wf, step):
        args = step.get("arguments") or {}
        if "inputVariables" in args:
            args["inputVariables"] = []

    monkeypatch.setattr(rt, "emit", _emit_dropping(drop_input_vars))

    ok, diffs = roundtrip(_load("trigger_parameters"), PACKAGED_SLIM_DB)
    assert not ok, "gate stayed GREEN with trigger-declared parameters dropped"
    # The manual-trigger input form is carried on the wire as the trigger's
    # `inputVariables`; its loss surfaces there (or as `parameters` if the
    # top-level list also drops). Either name is the form failing to survive.
    assert any(("inputVariables" in d) or ("parameters" in d) for d in diffs), (
        f"gate went red but did not name the input form: {diffs}")


def test_gate_runner_reports_and_fails_on_a_lossy_corpus(monkeypatch, tmp_path):
    """End-to-end at the runner level: one lossy playbook -> non-zero exit and
    a named failure, so CI actually blocks."""
    # A corpus of exactly the looping fixture...
    (tmp_path / "for_each_loop.json").write_text(
        (CORPUS_DIR / "for_each_loop.json").read_text())

    def drop_for_each(_wf, step):
        (step.get("arguments") or {}).pop("for_each", None)

    monkeypatch.setattr(rt, "emit", _emit_dropping(drop_for_each))

    passed, total, failures = corpus_gate.run_gate(tmp_path, PACKAGED_SLIM_DB)
    assert passed == 0 and total == 1
    assert failures and failures[0][0] == "for_each_loop"

    rc = corpus_gate.main(["--corpus-dir", str(tmp_path)])
    assert rc == 1, "runner did not fail on a lossy corpus"
