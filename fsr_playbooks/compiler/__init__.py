"""FSR playbook YAML compiler.

Pipeline: YAML text -> parser -> IR -> resolver -> validator -> emitter -> FSR JSON.

The compiler is library-first; everything callable here can be imported
from the CLI, MCP server, or future widget without surprises. Errors are
returned as structured `CompileError` objects, never raised as bare strings.
"""
from __future__ import annotations

from .errors import CompileError, ErrorCode
from .ir import Collection, Playbook, Step
from .parser import parse_yaml
from .resolver import Resolver
from .validator import validate
from .emitter import emit
from .pipeline import compile_yaml, CompileResult

# --- Frozen public surface (REORG_PLAN Phase 0) ---------------------------
# The FortiSOAR connector imports these submodules/symbols at stable paths.
# Re-exported here so later internal file moves stay non-breaking. Do not
# drop a name from this block without a paired connector cutover.
from . import typed_walker, render_paths, skill_compiler, skill_verify
from .parser import _slugify

__all__ = [
    "CompileError", "ErrorCode",
    "Collection", "Playbook", "Step",
    "parse_yaml", "Resolver", "validate", "emit",
    "compile_yaml", "CompileResult",
    "typed_walker", "render_paths", "skill_compiler", "skill_verify",
    "_slugify",
]
