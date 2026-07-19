"""End-to-end compile entry: YAML text -> FSR JSON dict + errors.

Library-first: this is what every consumer (CLI, MCP, widget) calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .arg_validator import ArgValidator
from .corpus_validator import CorpusValidator
from .emitter import emit
from .errors import CompileError, ErrorCode
from .ir import Collection
from .linter import lint
from .parser import parse_yaml
from .connector_output_refs import rewrite_connector_output_refs
from .reference_lint import reference_lint
from .resolver import Resolver
from .teaching import enrich_diagnostics
from .validator import validate


# Step fields the compiler/parser/emitter rely on. If the loaded `ir.Step`
# is missing any of these, an install is half-overwritten (a stale wheel
# shadowing the editable repo — pilot E10) and compiles will crash with an
# opaque `TypeError: Step.__init__() got an unexpected keyword argument …`
# mid-run. We assert it loudly at the entrypoint instead.
_EXPECTED_STEP_FIELDS = frozenset({
    "id", "type", "name", "arguments", "next", "branches",
    "unlabeled_next", "comment", "description", "for_each",
})

_self_check_error: Optional[str] = None
_self_checked = False


def _self_check() -> Optional[str]:
    """Detect a half-overwritten / shadowed `fsr_playbooks` install (E10).

    Two cheap probes, run once and cached:

    1. The loaded `ir` and `parser` modules must come from the same package
       directory. A stale wheel shadowing the editable repo splits them.
    2. The loaded `ir.Step` dataclass must carry every field the compiler
       passes to it. A stale `ir.py` missing (e.g.) `description` is the exact
       corruption that crashed the pilot at compile time.

    Returns a human-readable problem string, or None when healthy.
    """
    global _self_checked, _self_check_error
    if _self_checked:
        return _self_check_error

    problem: Optional[str] = None
    try:
        from dataclasses import fields as _dc_fields

        from . import ir as _ir_mod
        from . import parser as _parser_mod
        from .ir import Step as _Step

        ir_dir = Path(getattr(_ir_mod, "__file__", "") or "").resolve().parent
        parser_dir = Path(getattr(_parser_mod, "__file__", "") or "").resolve().parent
        if ir_dir != parser_dir:
            problem = (
                "fsr_playbooks install looks split: ir.py loaded from "
                f"{ir_dir} but parser.py from {parser_dir}. A stale "
                "fsr_playbooks (e.g. an old wheel in site-packages) is "
                "shadowing the editable repo — `pip uninstall fsr_playbooks` "
                "the stale copy or reinstall `-e .`."
            )
        else:
            have = {f.name for f in _dc_fields(_Step)}
            missing = _EXPECTED_STEP_FIELDS - have
            if missing:
                problem = (
                    f"loaded ir.Step is missing fields {sorted(missing)} that "
                    f"the compiler depends on (loaded from {ir_dir}). This is a "
                    "half-overwritten install — reinstall fsr_playbooks "
                    "(`pip install -e .`) and remove any stale copy."
                )
    except Exception as e:  # pragma: no cover - defensive
        problem = f"fsr_playbooks self-check failed to run: {e!r}"

    _self_check_error = problem
    _self_checked = True
    return problem


@dataclass
class CompileResult:
    fsr_json: Optional[dict[str, Any]] = None
    errors: list[CompileError] = field(default_factory=list)
    ir: Optional[Collection] = None

    @property
    def ok(self) -> bool:
        blocking = [e for e in self.errors if e.severity != "warning"]
        return not blocking and self.fsr_json is not None

    @property
    def warnings(self) -> list[CompileError]:
        return [e for e in self.errors if e.severity == "warning"]


def compile_yaml(
    text: str, db_path: Path,
    lax_codes: Optional[set[str]] = None,
    reference_lint_enabled: bool = True,
) -> CompileResult:
    """Compile YAML to FSR JSON.

    lax_codes: iterable of ErrorCode values (or their str) to demote from
    error → warning before blocking checks fire. Use for round-trip Path B
    where unknown_param / unknown_connector should not block emission.

    reference_lint_enabled: run the compile-time reference lint (default on),
    which adds *warnings* for unresolvable `vars.steps.X.foo` references. Pass
    False for round-trip / decompile paths where producer shapes are partial.
    """
    self_check_problem = _self_check()
    if self_check_problem is not None:
        return CompileResult(errors=[CompileError(
            code=ErrorCode.INTERNAL,
            message=self_check_problem,
            path="<install>",
        )])

    # Accept every spelling of a code: the ErrorCode enum, its ``str()``
    # (``"ErrorCode.UNKNOWN_PARAM"``), its ``.value`` (``"unknown_param"``), and
    # its ``.name`` (``"UNKNOWN_PARAM"``). A caller passing the friendly
    # ``.value`` string used to silently never match (the scan only compared
    # ``str(e.code)``), so a lax request was quietly ignored.
    def _code_forms(c: Any) -> set[str]:
        forms = {str(c)}
        val, name = getattr(c, "value", None), getattr(c, "name", None)
        if val is not None:
            forms.add(str(val))
        if name is not None:
            forms.add(str(name))
        return forms

    lax_set: set[str] = set()
    for c in lax_codes or set():
        lax_set |= _code_forms(c)

    def _demote(errs: list[CompileError]) -> list[CompileError]:
        if not lax_set:
            return errs
        for e in errs:
            if e.severity == "error" and _code_forms(e.code) & lax_set:
                e.severity = "warning"
        return errs

    coll, errs = parse_yaml(text)
    errs = _demote(errs)
    parse_blocking = [e for e in errs if e.severity != "warning"]
    if parse_blocking or coll is None:
        # Even on parse failure we attempt the raw-text linter so the
        # caller sees the foot-gun cause when the parser bails out on
        # a derived symptom (e.g. branches mapping that became {True:}).
        lint_errs = lint(text, coll)
        return CompileResult(errors=errs + lint_errs, ir=coll)

    all_warnings: list[CompileError] = [e for e in errs if e.severity == "warning"]

    def _blocked(errs: list[CompileError]) -> CompileResult:
        # Attach teaching examples to errors on high-foot-gun step types (0b).
        enrich_diagnostics(coll, errs)
        return CompileResult(errors=errs, ir=coll)

    lint_errs = _demote(lint(text, coll))
    if any(e.severity != "warning" for e in lint_errs):
        return _blocked(lint_errs)
    all_warnings.extend(lint_errs)

    def _has_blocking(errs: list[CompileError]) -> bool:
        _demote(errs)
        blocking = [e for e in errs if e.severity != "warning"]
        all_warnings.extend(e for e in errs if e.severity == "warning")
        return bool(blocking)

    resolver = Resolver(db_path)
    try:
        errs = resolver.resolve(coll)
        if _has_blocking(errs):
            return _blocked(errs)
        errs = ArgValidator(resolver.conn).validate(coll)
        if not _has_blocking(errs):
            errs = CorpusValidator(resolver.conn).validate(coll)
    finally:
        resolver.close()
    if _has_blocking(errs):
        return _blocked(errs)

    # Connector-output ref repair (warn-and-fix): rewrite
    # `vars.steps.<connstep>.<x>` → `.data.<field>` so a connector op's output
    # actually flows onward. Runs on the resolved IR BEFORE validate() and the
    # reference lint so they see the CORRECTED refs (no double-report), and
    # mutates the IR so `emit()` ships the fixed reference.
    all_warnings.extend(rewrite_connector_output_refs(coll, db_path))

    errs = _demote(validate(coll))
    if _has_blocking(errs):
        return _blocked(errs)

    # Reference lint (warning-only): catch a bad `vars.steps.X.foo` offline.
    # Runs last, on a fully-resolved IR, and never blocks — see reference_lint.
    if reference_lint_enabled:
        all_warnings.extend(reference_lint(coll, existing=all_warnings))
    enrich_diagnostics(coll, all_warnings)

    return CompileResult(fsr_json=emit(coll), errors=all_warnings, ir=coll)
