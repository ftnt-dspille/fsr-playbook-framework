"""fsr_playbooks -- portable agent loop + compiler + reference store.

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
# installed distribution metadata -- there is no hardcoded version in the tree, so
# the tag is the single source of truth and can never drift. A raw source checkout
# that was never installed has no metadata; fall back to a sentinel.
# The distribution is named `fsr-playbooks` when built for PyPI, but a DEV
# checkout installs this package via the repo's own `fsrpb` project instead --
# so no `fsr_playbooks` distribution exists there at all. Asking only for
# `fsr_playbooks` therefore found nothing real, and the only thing that ever
# answered was a stale `fsr_playbooks.egg-info` left in the repo root by an old
# build. importlib.metadata scans sys.path, and cwd is on sys.path, so
# `__version__` silently became A FUNCTION OF THE WORKING DIRECTORY: 0.4.10 when
# pytest ran from this repo, "0.0.0+unknown" from anywhere else. That is what
# tripped the connector's version guard across ~68 unrelated tests.
#
# Ask for the real distributions, most-specific first, and stop at the first
# hit. Keep the sentinel for a genuine source checkout, but treat it as
# "unknown", never as a version you can compare.
try:  # pragma: no cover - trivial import shim
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version
except ImportError:  # pragma: no cover
    PackageNotFoundError = Exception  # type: ignore[assignment,misc]
    _pkg_version = None  # type: ignore[assignment]

__version__ = "0.0.0+unknown"
if _pkg_version is not None:
    for _dist in ("fsr-playbooks", "fsr_playbooks", "fsrpb"):
        try:
            __version__ = _pkg_version(_dist)
            break
        except PackageNotFoundError:
            continue
    del _dist


def version_is_known() -> bool:
    """False when the version could not be resolved from installed metadata.

    Callers that gate on a version (the connector pins an exact
    `fsr-playbooks`) must branch on THIS rather than string-comparing
    `__version__`, so an unresolvable environment reports "I don't know"
    instead of silently failing a comparison against a sentinel.
    """
    return __version__ != "0.0.0+unknown"

from fsr_playbooks.compiler import (
    Collection,
    CompileError,
    ErrorCode,
    Playbook,
    Step,
    compile_yaml,
    emit,
    parse_yaml,
    validate,
)

__all__ = [
    "__version__",
    "compile_yaml", "parse_yaml", "validate", "emit",
    "CompileError", "ErrorCode",
    "Collection", "Playbook", "Step",
    # Lazily-exposed (see __getattr__): the full pre-submit gate + its check
    # catalog. Importing them pulls in the mcp_server package, so they're
    # deferred -- `compile_yaml` users (e.g. the connector runtime) don't pay
    # for it unless they ask.
    "verify", "CHECK_GROUPS",
]


def __getattr__(name: str):
    """Lazy re-export of the verify gate so `from fsr_playbooks import verify`
    works without eagerly importing the mcp_server package at module load.

    `verify` is the single forcing-function gate (compile → typed walk →
    per-step schema → optional live probe) with `disable_checks` toggles --
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
