"""Tool registry — wraps existing mcp_server.py functions.

Phase 2 v1: read-only authoring tools only. No `run_op`, no `push`, no
destructive actions. Live FSR calls (render_jinja, get_run_env,
list_configured_connectors) are allowed because they're read-only and
gated by the user's `.env`.

Schema generation is deliberately small: we map Python type hints to
the JSON Schema subset Anthropic accepts. If a tool's signature drifts
beyond what we cover, add the case here rather than papering over it.
"""
from __future__ import annotations

import inspect
import sys
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, get_args, get_origin

_PYTHON_DIR = Path(__file__).resolve().parents[2] / "python"
# Repo layout: FSRPlaybookYaml/python/, web/backend/llm/tools.py
# parents[2] = web/, so we need parents[3] for repo root, then /python.
_PYTHON_DIR = Path(__file__).resolve().parents[3] / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

import mcp_server  # noqa: E402


# Allow-list. Names match attribute names on `mcp_server`.
SAFE_TOOLS: list[str] = [
    "find_connector",
    "find_operation",
    "get_op_schema",
    "get_step_type",
    "find_jinja_filter",
    "find_jinja_pattern",
    "get_filter_examples",
    "search_playbooks",
    "validate_yaml",
    "compile_yaml",
    "list_configured_connectors",
    "list_picklists",
    "picklist_for_field",
    "resolve_picklist_value",
]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]


def _py_type_to_json(tp: Any) -> dict[str, Any]:
    """Map a Python annotation to a minimal JSON Schema fragment."""
    if tp is inspect.Parameter.empty or tp is Any:
        return {}
    origin = get_origin(tp)
    args = get_args(tp)

    if origin is typing.Union or (origin is None and args):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _py_type_to_json(non_none[0])
        # union of primitives → leave loose
        return {}
    if origin in (list, typing.List):
        inner = args[0] if args else Any
        return {"type": "array", "items": _py_type_to_json(inner) or {}}
    if origin in (dict, typing.Dict):
        return {"type": "object"}
    if tp is str:
        return {"type": "string"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is list:
        return {"type": "array"}
    if tp is dict:
        return {"type": "object"}
    return {}


def _build_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, p in sig.parameters.items():
        schema = _py_type_to_json(p.annotation)
        if p.default is inspect.Parameter.empty:
            required.append(name)
        else:
            schema = {**schema, "default": p.default} if schema else {"default": p.default}
        props[name] = schema or {}
    return {"type": "object", "properties": props, "required": required}


def _resolve(name: str) -> Callable[..., Any]:
    fn = getattr(mcp_server, name, None)
    if fn is None or not callable(fn):
        raise KeyError(f"unknown tool: {name}")
    return fn


def build_registry() -> dict[str, ToolSpec]:
    out: dict[str, ToolSpec] = {}
    for name in SAFE_TOOLS:
        fn = _resolve(name)
        desc = inspect.getdoc(fn) or f"{name} (no docstring)"
        # First-paragraph only; Anthropic limits description length implicitly.
        short = desc.strip().split("\n\n", 1)[0]
        out[name] = ToolSpec(
            name=name,
            description=short,
            input_schema=_build_schema(fn),
            fn=fn,
        )
    return out


REGISTRY = build_registry()


def anthropic_tools() -> list[dict[str, Any]]:
    """Anthropic's tool-use schema shape."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in REGISTRY.values()
    ]


def openai_tools() -> list[dict[str, Any]]:
    """OpenAI / LM Studio function-calling schema shape. Same registry,
    different envelope: `{type:"function", function:{name, description, parameters}}`."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in REGISTRY.values()
    ]


def dispatch(name: str, arguments: dict[str, Any]) -> Any:
    spec = REGISTRY.get(name)
    if spec is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return spec.fn(**(arguments or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # surface to LLM as a tool result, not a 500
        return {"error": f"{type(e).__name__}: {e}"}
