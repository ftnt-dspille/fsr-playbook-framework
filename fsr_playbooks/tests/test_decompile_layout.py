"""`decompile_to_yaml(layout=False)`: the readable form, without canvas noise.

Step positions and uuids (`top`, `left`, `uuid`) are what the designer needs and what
a reader does not. Dropping them takes about a quarter off a typical playbook. The
YAML must still compile, and nothing that says what a step *does* may go with them.
It must also come out the same from the 2.7 MB packaged catalog as from a full probed
reference DB, so a CI job or a plain `pip install` can produce it.
"""
from __future__ import annotations

import yaml

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.decompiler import decompile_to_yaml

_PB = """
collection: T
playbooks:
  - name: PB
    steps:
      - name: Start
        type: start_on_create
        module: incidents
        next: Pick
      - name: Pick
        type: decision
        conditions:
          - display: High
            when: "{{ vars.input.records[0].severity == 'High' }}"
            next: Flag
          - display: Else
            default: true
            next: Done
      - name: Flag
        type: set_variable
        vars:
          flagged: true
        next: Done
      - name: Done
        type: set_variable
        vars:
          finished: true
"""


def _wire() -> dict:
    res = compile_yaml(_PB, PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    return res.fsr_json


def _steps(text: str) -> list[dict]:
    return yaml.safe_load(text)["playbooks"][0]["steps"]


def test_default_keeps_layout_for_round_tripping():
    steps = _steps(decompile_to_yaml(_wire(), PACKAGED_SLIM_DB))
    assert all({"uuid", "top", "left"} <= set(s) for s in steps)


def test_no_layout_drops_position_and_step_uuids_only():
    full = _steps(decompile_to_yaml(_wire(), PACKAGED_SLIM_DB))
    lean = _steps(decompile_to_yaml(_wire(), PACKAGED_SLIM_DB, layout=False))
    assert not any({"uuid", "top", "left"} & set(s) for s in lean)
    strip = lambda s: {k: v for k, v in s.items() if k not in ("uuid", "top", "left")}  # noqa: E731
    assert lean == [strip(s) for s in full], "only layout may differ: what a step does must not change"


def test_no_layout_yaml_still_compiles_to_the_same_flow():
    lean = decompile_to_yaml(_wire(), PACKAGED_SLIM_DB, layout=False)
    res = compile_yaml(lean, PACKAGED_SLIM_DB)
    assert res.ok, [e.message for e in res.errors if e.severity != "warning"]
    names = lambda wire: sorted(s["name"] for s in wire["data"][0]["workflows"][0]["steps"])  # noqa: E731
    assert names(res.fsr_json) == names(_wire())
    routes = lambda wire: len(wire["data"][0]["workflows"][0]["routes"])  # noqa: E731
    assert routes(res.fsr_json) == routes(_wire())


def test_branch_labels_survive_without_layout():
    lean = decompile_to_yaml(_wire(), PACKAGED_SLIM_DB, layout=False)
    decision = next(s for s in _steps(lean) if s["type"] == "decision")
    assert [(c["display"], c["next"]) for c in decision["conditions"]] == [("High", "flag"), ("Else", "done")]


def test_packaged_slim_catalog_is_enough():
    """No reference DB needed: the catalog only drops values the compiler re-derives."""
    assert PACKAGED_SLIM_DB.stat().st_size < 10 * 1024 * 1024
    assert decompile_to_yaml(_wire(), PACKAGED_SLIM_DB)
