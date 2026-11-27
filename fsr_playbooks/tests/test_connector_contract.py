"""The connector models contract: loader and mock validator, on a synthetic
connector. No real connector models live in the framework; see the connector
repos under ConnectorsV2/ for those."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from fsr_playbooks.connectors.contract import (
    ContractError,
    OperationSpec,
    check_mock_results,
    load_operation_models,
    normalize_operation_models,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "synthetic_connector"


def _doc(steps: list[dict]) -> dict:
    return {"playbooks": [{"name": "P", "steps": steps}]}


def _step(op: str, data, connector: str = "synthetic", name: str = "S") -> dict:
    return {
        "id": name.lower(), "name": name, "type": "connector",
        "connector": connector, "operation": op,
        "mock_result": {"data": data, "status": "success", "message": "",
                        "operation": op},
    }


# ---- loader --------------------------------------------------------------


def test_loads_operation_models_from_connector_root():
    models = load_operation_models(FIXTURE_ROOT)
    assert set(models) == {"list_widgets", "get_widget"}
    assert models["list_widgets"].input.__name__ == "ListWidgetsParams"
    assert models["list_widgets"].output.__name__ == "WidgetPage"
    # A bare model is an output-only spec.
    assert models["get_widget"] == OperationSpec(output=models["get_widget"].output)
    assert models["get_widget"].input is None


def test_loading_twice_reuses_the_module():
    first = load_operation_models(FIXTURE_ROOT)
    second = load_operation_models(str(FIXTURE_ROOT) + "/")
    assert first["list_widgets"].output is second["list_widgets"].output


def test_does_not_touch_sys_path(tmp_path):
    import sys

    before = list(sys.path)
    load_operation_models(FIXTURE_ROOT)
    assert sys.path == before


def test_missing_package_is_a_contract_error(tmp_path):
    with pytest.raises(ContractError, match="no typed/__init__.py"):
        load_operation_models(tmp_path)


def test_package_without_mapping_is_a_contract_error(tmp_path):
    pkg = tmp_path / "typed"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("X = 1\n")
    with pytest.raises(ContractError, match="OPERATION_MODELS"):
        load_operation_models(tmp_path)


def test_malformed_entry_is_a_contract_error(tmp_path):
    pkg = tmp_path / "typed"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("OPERATION_MODELS = {'op': 'not a model'}\n")
    with pytest.raises(ContractError, match="expected a pydantic model"):
        load_operation_models(tmp_path)


def test_custom_package_name(tmp_path):
    pkg = tmp_path / "models"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from pydantic import BaseModel\n"
        "class Out(BaseModel):\n    x: int\n"
        "OPERATION_MODELS = {'op': Out}\n")
    models = load_operation_models(tmp_path, package="models")
    assert models["op"].output.__name__ == "Out"


def test_normalize_rejects_none_output():
    class In(BaseModel):
        a: int

    with pytest.raises(ContractError, match="cannot be None"):
        normalize_operation_models({"op": (In, None)})


# ---- mock validation -----------------------------------------------------


@pytest.fixture
def models():
    return {"synthetic": load_operation_models(FIXTURE_ROOT)}


def test_valid_mocks_pass_and_are_counted(models):
    doc = _doc([
        _step("list_widgets", {"items": [{"id": "a", "size": 1}], "total": 1}),
        _step("get_widget", {"id": "b", "size": 2}, name="G"),
    ])
    violations, checked = check_mock_results(doc, models)
    assert violations == []
    assert checked == 2


def test_bad_payload_reports_the_failing_location(models):
    doc = _doc([_step("list_widgets", {"items": [{"id": "a", "size": "big"}], "total": 1})])
    violations, checked = check_mock_results(doc, models)
    assert checked == 1
    assert len(violations) == 1
    v = violations[0]
    assert (v.playbook, v.step, v.connector, v.operation) == ("P", "S", "synthetic", "list_widgets")
    assert "items.0.size" in v.problem


def test_operation_without_a_model_is_a_violation(models):
    doc = _doc([_step("delete_widget", {})])
    violations, checked = check_mock_results(doc, models)
    assert checked == 0
    assert [v.problem for v in violations] == ["no output model for this operation"]


def test_connector_step_without_mock_is_a_violation(models):
    step = _step("get_widget", {"id": "x", "size": 1})
    del step["mock_result"]
    violations, _ = check_mock_results(_doc([step]), models)
    assert len(violations) == 1 and "no mock_result" in violations[0].problem


def test_steps_for_other_connectors_are_skipped(models):
    doc = _doc([_step("anything", {"not": "checked"}, connector="other-connector")])
    violations, checked = check_mock_results(doc, models)
    assert violations == [] and checked == 0


def test_non_connector_steps_are_ignored(models):
    doc = _doc([{"id": "s", "name": "Set", "type": "set_variable", "vars": {}}])
    assert check_mock_results(doc, models) == ([], 0)


def test_violation_string_names_the_step(models):
    doc = _doc([_step("get_widget", {"id": 1})])
    violations, _ = check_mock_results(doc, models)
    assert "P / 'S' (synthetic.get_widget)" in str(violations[0])
