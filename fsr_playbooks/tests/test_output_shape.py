"""output_shape: shape reduction + resolvable-reference suggestions.

The live probe (probe_output) is exercised separately against a box; this pins
the pure logic that turns a real output into the paths an author should use.
"""
from __future__ import annotations

from fsr_playbooks import output_shape as os_


def test_shape_of_reduces_to_structure():
    assert os_.shape_of("x") == "str"
    assert os_.shape_of(3) == "int"
    assert os_.shape_of(["a", "b"]) == {"__list_of__": "str", "__len__": 2}
    assert os_.shape_of({"a": 1, "b": "x"}) == {"a": "int", "b": "str"}


def test_list_of_scalars_suggests_join_and_index_not_attr():
    # get_macro_list's real shape: data is a flat list of strings.
    shape = {"__list_of__": "str", "__len__": 8}
    paths = [p["path"] for p in os_.suggest_references(shape, "vars.steps.Get_Macros.data")]
    assert "vars.steps.Get_Macros.data | join(', ')" in paths
    assert "vars.steps.Get_Macros.data[0]" in paths
    # it must NOT suggest a phantom attribute on a list of scalars
    assert not any(".macros" in p or p.endswith(".name") for p in paths)


def test_list_of_records_suggests_index_and_iterate():
    # find_record's real shape: a bare list of record dicts.
    shape = {"__list_of__": {"name": "str", "severity": "str"}, "__len__": 3}
    paths = [p["path"] for p in os_.suggest_references(shape, "vars.steps.Find")]
    assert "vars.steps.Find[0].name" in paths           # index, then field
    assert "vars.steps.Find" in paths                   # whole list to iterate
    assert "vars.steps.Find.name" not in paths          # the list-as-scalar gotcha


def test_describe_output_flags_list():
    d = os_.describe_output(["a", "b", "c"], "vars.steps.X.data")
    assert d["is_list"] and d["shape"]["__len__"] == 3
    assert d["suggested_references"]


def test_probe_output_describes_envelope(monkeypatch):
    """A fake client whose op returns the {status, message, data:[...]} envelope
    is described, with suggestions rooted at `.data`."""
    class _Conns:
        def execute(self, connector, operation, params, config=None):
            return {"status": "Success", "message": "", "data": ["m1", "m2", "m3"]}

    class _Client:
        connectors = _Conns()

    out = os_.probe_output(_Client(), "cyops_utilities", "get_macro_list",
                           root="vars.steps.Get_Macros")
    assert out["ok"] and out["is_list"]
    assert out["raw_keys"] == ["data", "message", "status"]
    assert any("| join" in p["path"] for p in out["suggested_references"])


def test_probe_output_reports_error(monkeypatch):
    class _Client:
        class connectors:
            @staticmethod
            def execute(**kw):
                raise RuntimeError("connector not configured")
    out = os_.probe_output(_Client(), "x", "y")
    assert out["ok"] is False and "connector not configured" in out["error"]
