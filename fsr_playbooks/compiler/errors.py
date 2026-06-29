"""Structured compiler errors.

Errors are data — code, location, message, and an optional suggestion.
Consumers (CLI, MCP, widget) format them their own way; the compiler
itself never prints.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    PARSE_ERROR = "parse_error"
    MISSING_FIELD = "missing_field"
    UNKNOWN_STEP_TYPE = "unknown_step_type"
    UNKNOWN_CONNECTOR = "unknown_connector"
    UNKNOWN_OPERATION = "unknown_operation"
    UNKNOWN_PARAM = "unknown_param"
    UNKNOWN_NEXT_STEP = "unknown_next_step"
    DUPLICATE_STEP_ID = "duplicate_step_id"
    NO_TRIGGER = "no_trigger"
    BAD_VALUE = "bad_value"
    # Jinja diagnostics — emitted by the compile-path jinja check (the real
    # jinja2 parser, via jinja_checks.check_jinja). Syntax errors block; an
    # unknown filter/test name is a warning (the catalog is a curated subset).
    JINJA_SYNTAX_ERROR = "jinja_syntax_error"
    UNKNOWN_JINJA_FILTER = "unknown_jinja_filter"
    INSTANCE_MISMATCH = "instance_mismatch"  # catalog warmed from a different SOAR
    STALE_CATALOG = "stale_catalog"          # catalog is behind the live SOAR
    INTERNAL = "internal"                    # tooling/install fault, not the YAML


@dataclass
class CompileError:
    code: ErrorCode
    message: str
    path: str = ""              # YAML-ish dotted path, e.g. "playbooks[0].steps[2]"
    suggestion: Optional[str] = None
    near: Optional[str] = None  # "did you mean X" candidate
    severity: str = "error"     # "error" blocks compilation; "warning" does not

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "path": self.path,
            "suggestion": self.suggestion,
            "near": self.near,
            "severity": self.severity,
        }
