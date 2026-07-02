"""Typed model for the ``connector`` step envelope (the keystone).

The connector step is the most-authored type and the shared backbone for the
whole **connector family**: Connector, Code Snippet, Utilities, and Send Email
all route through the same connector dispatcher
(``script: /wf/workflow/tasks/connector``). Each carries a static envelope
plus a per-operation params payload::

    arguments:
      connector:       <name>     # required — the connector to call
      operation:       <op>       # required — the operation to invoke
      config:          <name>     # optional — a named connector config (default "")
      version:         <ver>      # auto-stamped from the catalog; authors never set it
      agent:           <name>     # optional — bind to a FortiSOAR Agent (fortigate, edge)
      params:          {…}        # the per-op arguments — DYNAMIC, from the live catalog
      operationTitle:  "FSR: …"   # the designer label; re-derived from the catalog

This layer types the **static envelope** so an agent can introspect "what does a
connector step take?" via ``get_step_arg_schema("connector")`` (was ``None`` --
the discover gap this closes). It is *validation-only*: a wrong-typed envelope
scalar (e.g. ``connector: 123``, ``config: ["x"]``) becomes a clean ``BAD_VALUE``
instead of riding through. ``params`` stays ``Any`` -- its real schema is the
live per-op catalog, surfaced at runtime via the resolver's strong catalog checks
(unknown op/param, enum, conditional-visibility, conditional-required) and to
agents via ``fsrpb find op``. Reproducing that dynamic shape statically would be
both wrong (it is per-install) and redundant.

DESIGN SPLIT (the manual_input lesson, applied up front):
  * The typed model owns the **envelope schema** (introspection) + scalar
    validation. It does NOT shadow the resolver's richer messages.
  * The resolver (``_resolve_connector_args``) owns the runtime catalog checks:
    missing ``connector``/``operation`` -> ``MISSING_FIELD`` with a precise
    message, unknown connector/op -> difflib "did you mean", the auto-lift of
    flat params into ``params:`` with a teaching warning, param/enum/visibility/
    required checks. Those stay there -- they're better than pydantic's generic
    errors and they need the catalog.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict

from ...errors import CompileError  # noqa: F401  (re-exported for symmetry)
from ..base import StrictArgs
from .._bridge import validate_args


class ConnectorArgs(StrictArgs):
    """Typed view of a connector step's static envelope.

    `connector` and `operation` are required at runtime (the resolver enforces
    missing -> ``MISSING_FIELD`` with the precise "connector step requires
    arguments.connector" message), but are declared **Optional** here so
    pydantic does NOT emit its generic "Field required" and shadow that richer
    resolver message (the manual_input lesson). A present-but-wrong-typed value
    (e.g. ``connector: 123``) is still a clean ``BAD_VALUE``. `config`/
    `version`/`agent`/`operationTitle` are optional strings. `params` is
    ``Any`` -- the per-op payload whose real schema is the live catalog
    (``fsrpb find op``). The rest of the envelope (`step_variables`,
    `pickFromTenant`, `mock_result`, `useMockOutput`, `condition`, `name`)
    rides through ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    connector: Optional[str] = None
    operation: Optional[str] = None
    config: Optional[str] = None
    version: Optional[str] = None
    agent: Optional[str] = None
    operationTitle: Optional[str] = None
    params: Optional[Any] = None


def expand_connector(
    args: Any, path: str, errors: list[CompileError],
) -> Optional[dict]:
    """Type-validate a connector step's envelope scalars.

    Validation-only: always returns ``None`` (the resolver's
    ``_resolve_connector_args`` owns the full transform -- catalog lookup,
    version stamping, auto-lift, and all the op/param checks -- so
    ``step.arguments`` is untouched). A bad envelope scalar (e.g.
    ``connector: 123``) appends a ``BAD_VALUE`` and leaves the step for the
    resolver's richer checks to also run. Does NOT re-validate `connector`/
    `operation` presence (the resolver's ``MISSING_FIELD`` message is more
    precise than pydantic's "Field required") -- it only flags a present-but-
    wrong-typed value.
    """
    if not isinstance(args, dict):
        return None
    validate_args(ConnectorArgs, args, f"{path}.arguments", errors)
    return None
