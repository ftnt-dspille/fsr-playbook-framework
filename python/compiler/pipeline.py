"""End-to-end compile entry: YAML text -> FSR JSON dict + errors.

Library-first: this is what every consumer (CLI, MCP, widget) calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .arg_validator import ArgValidator
from .emitter import emit
from .errors import CompileError
from .ir import Collection
from .parser import parse_yaml
from .resolver import Resolver
from .validator import validate


@dataclass
class CompileResult:
    fsr_json: Optional[dict[str, Any]] = None
    errors: list[CompileError] = field(default_factory=list)
    ir: Optional[Collection] = None

    @property
    def ok(self) -> bool:
        return not self.errors and self.fsr_json is not None


def compile_yaml(text: str, db_path: Path) -> CompileResult:
    coll, errs = parse_yaml(text)
    if errs or coll is None:
        return CompileResult(errors=errs, ir=coll)

    resolver = Resolver(db_path)
    try:
        errs = resolver.resolve(coll)
        if errs:
            return CompileResult(errors=errs, ir=coll)
        errs = ArgValidator(resolver.conn).validate(coll)
    finally:
        resolver.close()
    if errs:
        return CompileResult(errors=errs, ir=coll)

    errs = validate(coll)
    if errs:
        return CompileResult(errors=errs, ir=coll)

    return CompileResult(fsr_json=emit(coll), ir=coll)
