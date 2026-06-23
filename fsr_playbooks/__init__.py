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
__version__ = "0.4.5"

from fsr_playbooks.compiler import (
    compile_yaml, parse_yaml, validate, emit,
    CompileError, ErrorCode, Collection, Playbook, Step,
)

__all__ = [
    "__version__",
    "compile_yaml", "parse_yaml", "validate", "emit",
    "CompileError", "ErrorCode",
    "Collection", "Playbook", "Step",
]
