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

# Single source of truth for the published version. The packaging dist
# (packaging/fsr_playbooks/pyproject.toml) reads this via dynamic version, and
# the FortiSOAR connector asserts the worker imported exactly this build.
__version__ = "0.4.10"

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
