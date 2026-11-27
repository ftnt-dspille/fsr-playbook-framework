"""Connector output contract: a connector repo exports typed models, the
framework loads them and checks mock payloads against them.

A connector repo keeps its models in a package (default name ``typed``) at
its root. The package's ``__init__.py`` defines ``OPERATION_MODELS``, a mapping
from operation name to either:

- a pydantic model class: the operation's output model, no input model; or
- a ``(input_model, output_model)`` tuple, where ``input_model`` may be ``None``.

The framework never imports the models by name. ``load_operation_models``
takes the connector repo root, imports its package from that path (under a
private package name, so two connectors with a ``typed`` package never
collide and nothing is left on ``sys.path``), and returns the normalized
mapping. ``check_mock_results`` then validates every connector step's
``mock_result.data`` against the output model of its operation.

The contract is build- and test-time only. A connector package may import
pydantic and its own modules; it must not need this framework at runtime.
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

#: Package name a connector repo uses for its models, relative to its root.
MODELS_PACKAGE = "typed"

#: Name of the mapping the package's ``__init__`` must export.
MODELS_SYMBOL = "OPERATION_MODELS"


class ContractError(Exception):
    """A connector repo does not satisfy the models contract."""


@dataclass(frozen=True)
class OperationSpec:
    """The models for one operation. ``input`` is optional."""

    output: type[Any]
    input: type[Any] | None = None


@dataclass(frozen=True)
class MockViolation:
    """One mock payload that does not satisfy its operation's contract."""

    playbook: str
    step: str
    connector: str
    operation: str
    problem: str

    def __str__(self) -> str:
        return (f"{self.playbook} / {self.step!r} ({self.connector}.{self.operation}): "
                f"{self.problem}")


def _normalize_one(op: str, value: Any) -> OperationSpec:
    if isinstance(value, OperationSpec):
        return value
    if isinstance(value, type) and issubclass(value, BaseModel):
        return OperationSpec(output=value)
    if isinstance(value, tuple) and len(value) == 2:
        input_model, output_model = value
        for model in (input_model, output_model):
            if model is not None and not (isinstance(model, type) and issubclass(model, BaseModel)):
                raise ContractError(f"{op}: tuple entries must be pydantic models or None")
        if output_model is None:
            raise ContractError(f"{op}: the output model cannot be None")
        return OperationSpec(output=output_model, input=input_model)
    raise ContractError(
        f"{op}: expected a pydantic model or (input, output) tuple, got {value!r}")


def normalize_operation_models(raw: Mapping[str, Any]) -> dict[str, OperationSpec]:
    """Accept any of the documented value forms and return ``OperationSpec``s."""
    return {str(op): _normalize_one(str(op), value) for op, value in raw.items()}


def load_operation_models(connector_root: str | Path,
                          package: str = MODELS_PACKAGE) -> dict[str, OperationSpec]:
    """Import ``<connector_root>/<package>`` and return its normalized models.

    Raises ``ContractError`` if the package or its ``OPERATION_MODELS`` is
    missing or malformed. The package is imported under a name derived from its
    absolute path, so loading the same repo twice reuses one module.
    """
    root = Path(connector_root).expanduser().resolve()
    pkg_dir = root / package
    init = pkg_dir / "__init__.py"
    if not init.is_file():
        raise ContractError(f"{pkg_dir}: no {package}/__init__.py to load models from")

    digest = hashlib.sha256(str(pkg_dir).encode("utf-8")).hexdigest()[:12]
    mod_name = f"_fsrp_connector_{digest}_{package}"
    module = sys.modules.get(mod_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(
            mod_name, init, submodule_search_locations=[str(pkg_dir)])
        if spec is None or spec.loader is None:
            raise ContractError(f"{init}: not an importable Python package")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            del sys.modules[mod_name]
            raise

    raw = getattr(module, MODELS_SYMBOL, None)
    if not isinstance(raw, Mapping):
        raise ContractError(f"{init}: must define {MODELS_SYMBOL} as a mapping")
    return normalize_operation_models(raw)


def check_mock_results(doc: Mapping[str, Any],
                       models_by_connector: Mapping[str, Mapping[str, OperationSpec]],
                       ) -> tuple[list[MockViolation], int]:
    """Validate the connector steps of a playbook document.

    ``doc`` is a parsed ``playbooks.yaml`` (``{"playbooks": [...]}``).
    ``models_by_connector`` maps connector name to its operation models. Steps
    whose connector is not in the mapping are skipped, so a scenario that calls
    another connector is checked by that connector's own repo.

    Returns ``(violations, checked)``: the payloads that failed and how many
    were validated.
    """
    violations: list[MockViolation] = []
    checked = 0
    for pb in doc.get("playbooks", []):
        pb_name = str(pb.get("name", "?"))
        for step in pb.get("steps", []):
            if step.get("type") != "connector":
                continue
            connector = step.get("connector")
            if connector not in models_by_connector:
                continue
            step_name = str(step.get("name", step.get("id", "?")))
            mock = step.get("mock_result")
            if not isinstance(mock, Mapping):
                violations.append(MockViolation(pb_name, step_name, connector, "?",
                                                "connector step has no mock_result"))
                continue
            op = str(mock.get("operation", ""))
            models = models_by_connector[connector]
            if op not in models:
                violations.append(MockViolation(pb_name, step_name, connector, op,
                                                "no output model for this operation"))
                continue
            checked += 1
            try:
                TypeAdapter(models[op].output).validate_python(mock.get("data"))
            except ValidationError as exc:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first.get("loc", ())) or "<root>"
                violations.append(MockViolation(
                    pb_name, step_name, connector, op,
                    f"mock data fails the output model at {loc}: {first.get('msg')}"))
    return violations, checked


__all__ = [
    "MODELS_PACKAGE",
    "MODELS_SYMBOL",
    "ContractError",
    "MockViolation",
    "OperationSpec",
    "check_mock_results",
    "load_operation_models",
    "normalize_operation_models",
]
