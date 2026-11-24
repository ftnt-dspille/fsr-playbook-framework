"""Shared helpers for the Microsoft-family typed connector models.

Three pieces the per-connector typed modules all need:

* the **AADSTS error envelope** the identity platform returns on the token
  endpoint (the shape ``microsoft_api_auth.py``-style modules read
  ``error``/``error_description`` out of);
* the **Defender/Graph resource error body** (``{"error": {"code", ...,
  "message"}}``) and the exact ``ConnectorError`` message formats the
  FortiSOAR Microsoft connectors wrap them into -- that string is what a
  playbook actually sees on a failed step;
* an offline **stub for the FortiSOAR connector SDK** plus a by-path loader,
  so a connector's ``operations.py`` can be imported and its ops called
  in-process (capture scripts, live tests) on a machine that has never
  installed the ``connectors.*`` runtime.

NOTE (duplication, merge later): the microsoft-graph security pair builds the
same AADSTS envelope under ``graph_common.py``. Until that module lands, the
envelope model lives here; when both exist, merge whichever copy is richer and
re-point the imports.
"""
from __future__ import annotations

import importlib
import logging
import re
import sys
import types
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AADSTSError(BaseModel):
    """Error body the Azure AD token endpoint returns on a failed token request.

    Provenance: source-derived (``microsoft_api_auth.py`` reads
    ``err_resp['error']`` + ``err_resp.get('error_description')`` off the token
    response), live-capture pending. Field set beyond those two follows the
    documented AADSTS body (``error_codes``/``trace_id``/``correlation_id``/
    ``timestamp``) and is kept optional; ``extra="allow"`` preserves anything
    else the platform adds.

    The connector surfaces this as
    ``ConnectorError('Response <status>: <reason> \\n Error Message: '
    '<error_description>')`` -- see :func:`token_error_connector_message`.
    """

    model_config = ConfigDict(extra="allow")

    error: str
    error_description: str | None = None
    error_codes: list[int] = Field(default_factory=list)
    timestamp: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None

    def aadsts_code(self) -> int | None:
        """The AADSTS error number, from ``error_codes`` or the description.

        Real descriptions lead with ``AADSTS<code>: ...``; ``error_codes`` is
        the structured form when present. Returns ``None`` when neither
        carries a number.
        """
        if self.error_codes:
            return self.error_codes[0]
        if self.error_description:
            m = re.search(r"\bAADSTS(\d{6,7})\b", self.error_description)
            if m:
                return int(m.group(1))
        return None


class DefenderErrorDetail(BaseModel):
    """The inner mapping of a Microsoft security-API resource error body.

    Provenance: source-derived (``operations.py``'s ``api_request`` reads
    ``err_resp['error']['message']``), live-capture pending. The documented
    body carries ``code`` + ``message`` (OData style); both are Optional here
    because the connector tolerates a body without ``message`` -- that path
    raises a bare ``ConnectorError("'message'")`` from the KeyError.
    """

    model_config = ConfigDict(extra="allow")

    code: str | None = None
    message: str | None = None
    target: str | None = None


class DefenderAPIError(BaseModel):
    """Error body of the Microsoft 365 Defender resource API (401/403/404/429).

    Provenance: source-derived (``operations.py``'s ``api_request`` error
    branch), live-capture pending. 404 is special on this connector: the code
    RETURNS the raw ``requests.Response`` object instead of raising, so the
    playbook sees the response object rather than this body -- see the
    ``get_incident`` model's docstring.
    """

    model_config = ConfigDict(extra="allow")

    error: DefenderErrorDetail


def connector_error_message(status_code: int, reason: str, message: str | None) -> str:
    """The exact ``ConnectorError`` string ``api_request`` raises for a failed
    resource call (``'Response [<code>:<reason> Details: <message>]'``).

    Provenance: source-derived (``operations.py`` lines formatting the error),
    live-capture pending.
    """
    return "Response [{}:{} Details: {}]".format(status_code, reason, message or "")


def token_error_connector_message(status_code: int, reason: str, error_description: str | None) -> str:
    """The exact ``ConnectorError`` string the token-acquisition path raises
    (``'Response <code>: <reason> \\n Error Message: <error_description>'``).

    Provenance: source-derived (``microsoft_api_auth.py``), live-capture
    pending.
    """
    return "Response {}: {} \n Error Message: {}".format(
        status_code, reason, error_description or ""
    )


_OP_ERROR_RE = re.compile(r"^Response \[(\d+):([^\]]*?) Details: (.*)\]$", re.DOTALL)


def parse_connector_error_message(text: str) -> dict[str, Any] | None:
    """Parse an op-level ``ConnectorError`` message back into its parts.

    Returns ``{"status_code", "reason", "details"}`` or ``None`` when the text
    is not the op-level format (transport errors like ``The request timed
    out`` are raised verbatim and do not match). Lets downstream tooling read
    the HTTP status a playbook step failed with without a live box.
    """
    m = _OP_ERROR_RE.match(text.strip())
    if not m:
        return None
    return {
        "status_code": int(m.group(1)),
        "reason": m.group(2),
        "details": m.group(3),
    }


def stub_fortisoar_connector_sdk(logger_prefix: str = "connector") -> bool:
    """Make ``connectors.core.connector``/``connectors.core.utils`` importable.

    A FortiSOAR connector package hard-imports the appliance runtime
    (``get_logger``, ``ConnectorError``, ``update_connnector_config``). On a
    machine without it, the stub below lets ``operations.py`` import and its
    ops run in-process -- the only three names the Microsoft connector family
    touches. When the REAL SDK is already importable it is left untouched and
    ``False`` is returned.

    This exists for offline import of captured connector sources (typed-model
    tests, capture scripts); it is NOT a runtime shim for executing playbooks.
    """
    try:
        importlib.import_module("connectors.core.connector")
        return False
    except ImportError:
        pass
    if "connectors.core.connector" in sys.modules:
        return False

    pkg = types.ModuleType("connectors")
    core = types.ModuleType("connectors.core")
    connector_mod = types.ModuleType("connectors.core.connector")
    utils_mod = types.ModuleType("connectors.core.utils")

    class ConnectorError(Exception):
        pass

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(f"{logger_prefix}.{name}")

    def update_connnector_config(*args: Any, **kwargs: Any) -> None:
        return None

    setattr(connector_mod, "ConnectorError", ConnectorError)
    setattr(connector_mod, "get_logger", get_logger)
    setattr(connector_mod, "Connector",
            type("Connector", (), {"__init__": lambda self, *a, **k: None}))
    setattr(utils_mod, "update_connnector_config", update_connnector_config)

    pkg.__path__ = []
    core.__path__ = []
    sys.modules["connectors"] = pkg
    sys.modules["connectors.core"] = core
    sys.modules["connectors.core.connector"] = connector_mod
    sys.modules["connectors.core.utils"] = utils_mod
    setattr(pkg, "core", core)
    setattr(core, "connector", connector_mod)
    setattr(core, "utils", utils_mod)
    return True


def load_connector_package(source_dir: str | Path, module_name: str) -> types.ModuleType:
    """Import a connector source directory (no ``__init__.py``, dash-named)
    as a Python package and return it with ``operations`` imported.

    FortiSOAR connector packages carry ``operations.py``/``connector.py`` at
    the top and are named with dashes, so neither ``sys.path`` imports nor
    normal package discovery apply. This registers a namespace-style module
    whose ``__path__`` is the source dir, then imports
    ``<module_name>.operations`` so its relative imports resolve.
    """
    src = Path(source_dir).expanduser().resolve()
    if not (src / "operations.py").is_file():
        raise FileNotFoundError(
            f"no operations.py under {src} -- pass the connector package dir"
        )
    if module_name in sys.modules:
        return sys.modules[module_name]
    pkg = types.ModuleType(module_name)
    pkg.__path__ = [str(src)]
    pkg.__file__ = str(src / "connector.py")
    sys.modules[module_name] = pkg
    ops = importlib.import_module(f"{module_name}.operations")
    setattr(pkg, "operations", ops)
    return pkg
