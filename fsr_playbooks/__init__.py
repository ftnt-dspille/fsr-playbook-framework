"""fsr_playbooks — portable agent loop + compiler + reference store.

Surface is intentionally small. Anything that needs FastAPI / Starlette /
SSE / uvicorn / global app state lives in the consumer (web/backend or
the FortiSOAR connector), not here. CI guards against re-introducing
web-framework deps by failing the build if `fastapi`/`starlette`/
`sse_starlette`/`uvicorn` is imported anywhere under `fsr_playbooks/`.

See FSR_CONNECTOR_PLAN.md and docs/plans/FSR_CORE_EXTRACTION_AUDIT.md
for the extraction plan and the protocols that consumers must supply.
"""
from __future__ import annotations

# Version comes from the git tag, stamped into the wheel metadata at build time
# by hatch-vcs (packaging/fsr_playbooks/pyproject.toml). We read it back from the
# installed distribution metadata — there is no hardcoded version in the tree, so
# the tag is the single source of truth and can never drift. A raw source checkout
# that was never installed has no metadata; fall back to a sentinel.
try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    __version__ = _pkg_version("fsr_playbooks")
except PackageNotFoundError:  # pragma: no cover - source checkout without an install
    __version__ = "0.0.0+unknown"

from fsr_playbooks.compiler import (
    compile_yaml, parse_yaml, validate, emit,
    CompileError, ErrorCode, Collection, Playbook, Step,
)

__all__ = [
    "__version__",
    "compile_yaml", "parse_yaml", "validate", "emit",
    "CompileError", "ErrorCode",
    "Collection", "Playbook", "Step",
    # Lazily-exposed (see __getattr__): the full pre-submit gate + its check
    # catalog. Importing them pulls in the mcp_server package, so they're
    # deferred — `compile_yaml` users (e.g. the connector runtime) don't pay
    # for it unless they ask.
    "verify", "CHECK_GROUPS",
]


def __getattr__(name: str):
    """Lazy re-export of the verify gate so `from fsr_playbooks import verify`
    works without eagerly importing the mcp_server package at module load.

    `verify` is the single forcing-function gate (compile → typed walk →
    per-step schema → optional live probe) with `disable_checks` toggles —
    the method an SDK like pyfsr should call to validate a playbook before
    pushing. `CHECK_GROUPS` is the toggle catalog (group → diagnostic codes).
    """
    if name == "verify":
        from fsr_playbooks.mcp_server.tools_verify import verify_playbook
        return verify_playbook
    if name == "CHECK_GROUPS":
        from fsr_playbooks.mcp_server.tools_verify import CHECK_GROUPS
        return CHECK_GROUPS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
