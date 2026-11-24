"""Typed outputs for the soarshelf ``microsoft-graph-api-security`` connector.

Source: ``soarshelf/content/connectors/manage-graph-security-incidents-and-
alerts/package/microsoft-graph-api-security`` (info.json version 1.0.0).
Five registered operations (``update_security_alert`` exists in
operations.py but is NOT in the ``operations`` dict, so it is not a
surface). One output model per registered op, plus the config model typed
from its info.json ``configuration`` block.

Wire quirks the models normalize (all source-observed in operations.py
v1.0.0, none live-verified yet):

- ``api_request`` returns the literal ``True`` when a success status
  carries an empty body -- PATCH /security/incidents/{id} answers 204, so
  ``update_security_incident`` yields ``True``, not the field echo its
  info.json output_schema advertises (``MutationNoContentResult``).
- ``api_request`` RETURNS the raw ``requests.Response`` on a 404 instead
  of raising: a bad ``alertID`` does not produce a ConnectorError, it
  produces whatever the runtime serializes a Response to. Treat 404 as a
  failure in playbook logic explicitly (``GraphErrorEnvelope`` documents
  the body Graph would have sent).
- 429 is retried internally (10 retries, 10s apart) before anything
  surfaces; a surfaced throttling error already exhausted ~100s.
- ``get_security_incidents`` clamps ``top`` to 50
  (``min(int(requested_top), 50)``); ``getAllRecords`` follows
  ``@odata.nextLink`` and then STRIPS it from the result.
- ``$count=true`` adds the ``ConsistencyLevel: eventual`` header.
- ``run_advanced_hunting`` POSTs to the BETA surface
  (``/beta/security/runHuntingQuery``) and expects the KQL columns in
  ``Schema`` with rows in ``Results``. The op param is lowercase
  ``query`` (the connector's sample playbooks, borrowed from
  microsoft-365-defender, show a capitalized ``Query`` -- that belongs to
  the other connector).
- Endpoints are hardcoded: ``/v1.0/security/alerts_v2``,
  ``/v1.0/security/incidents``, ``/beta/security/runHuntingQuery`` --
  unlike microsoft-graph_dev there is no ``api_version`` anywhere.

Provenance for every model here, until live captures land:
``Provenance: source-derived (operations.py v1.0.0), live-capture pending.``
"""
from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from .graph_common import (
    MutationNoContentResult,
    SecurityAlertsV2Page,
    SecurityAlertV2,
    SecurityIncidentsPage,
)

#: Exact provenance string required by the m365-trial plan §8.2 for this
#: connector's models (info.json version 1.0.0).
PROVENANCE = "Provenance: source-derived (operations.py v1.0.0), live-capture pending."


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class IncidentsPage(SecurityIncidentsPage):
    """``get_security_incidents`` output.

    ``top`` is clamped to 50 and only sent when truthy; ``$expand=alerts``
    rides along when ``expandAlerts`` is set; ``$count=true`` only when
    ``includeCount`` is set (and flips the request to eventual
    consistency). With ``getAllRecords`` the op follows ``@odata.nextLink``
    and strips it from the final result -- a getAllRecords-shaped page has
    context+value and NO nextLink.

    Provenance: source-derived (operations.py v1.0.0), live-capture pending.
    """


class AlertsV2Page(SecurityAlertsV2Page):
    """``get_security_alerts`` output (alerts_v2).

    ``$top``/``$skip``/``$filter`` pass through; ``includeCount`` adds
    ``$count=true``; ``getAllRecords`` follows the nextLink chain and
    strips it.

    Provenance: source-derived (operations.py v1.0.0), live-capture pending.
    """


class AlertResult(RootModel[SecurityAlertV2]):
    """``get_security_alert`` output: one alerts_v2 alert, bare.

    404 quirk: ``api_request`` RETURNS the ``requests.Response`` on a 404
    instead of raising, so a bad ``alertID`` never reaches this model --
    guard the playbook step before reading fields (documented; a typed
    Response is not modelable).

    Provenance: source-derived (operations.py v1.0.0), live-capture pending.
    """


class AdvancedHuntingColumn(_WireModel):
    """One column of a hunting query result's ``Schema``.

    Provenance: source-derived (operations.py v1.0.0 run_advanced_hunting;
    Graph runHuntingQuery response shape), live-capture pending.
    """

    name: str
    type: str | None = None


class AdvancedHuntingResult(_WireModel):
    """``run_advanced_hunting`` output.

    ``Schema`` names+types the columns; ``Results`` rows carry the KQL
    projections verbatim (heterogeneous scalars/arrays), so rows stay
    dicts pending captures. Note the payload key is capitalized ``Query``
    while the op PARAM is lowercase ``query``; ``timespan`` must be one of
    the constant.py TIMESPAN keys (e.g. ``Last 30 Days`` -> ``P30D``) or
    it silently drops out of the payload.

    Provenance: source-derived (operations.py v1.0.0), live-capture pending.
    """

    schema_: list[AdvancedHuntingColumn] | None = Field(None, alias="Schema")
    results: list[dict[str, Any]] | None = Field(None, alias="Results")


# ---------------------------------------------------------------------------
# Config (typed from info.json "configuration", v1.0.0)
# ---------------------------------------------------------------------------

AUTH_APP_PERMISSION: Final = "Without a User - Application Permission"
AUTH_DELEGATED: Final = "On behalf of User - Delegated Permission"


class MicrosoftGraphApiSecurityConfig(_WireModel):
    """Config model typed from the connector's info.json configuration
    schema (v1.0.0), plus the runtime keys the connector itself stores.

    NOTE the tenant field name: ``tenant_id`` here, ``tenant`` in
    microsoft-graph_dev -- the two connectors are not config-compatible.
    Both auth branches show the same visible fields (info.json onchange
    differs only by the delegated branch adding ``code``/``redirect_url``).
    The runtime keys (``accessToken``, ``expiresOn`` as a ctime string,
    ``refresh_token``, ``config_id``) are written back by
    ``get_session``/``validate_token``; ``connector_info`` is passed
    alongside the config on this connector, not stored inside it.

    Provenance: source-derived (info.json configuration schema v1.0.0,
    connector.py execute), live-capture pending.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    auth_type: Literal[
        "Without a User - Application Permission",
        "On behalf of User - Delegated Permission",
    ] = AUTH_APP_PERMISSION
    resource: str = "https://graph.microsoft.com"
    tenant_id: str
    client_id: str
    client_secret: str | None = None
    code: str | None = None
    redirect_url: str | None = None
    verify_ssl: bool = True

    accessToken: str | None = None
    expiresOn: str | None = None
    refresh_token: str | None = None
    config_id: str | None = None


# ---------------------------------------------------------------------------
# Op -> model registry (consumed by tests and the mock loader)
# ---------------------------------------------------------------------------

OPERATION_MODELS: dict[str, Any] = {
    "get_security_incidents": IncidentsPage,
    "get_security_alerts": AlertsV2Page,
    "get_security_alert": AlertResult,
    "update_security_incident": MutationNoContentResult,
    "run_advanced_hunting": AdvancedHuntingResult,
}

__all__ = [
    "PROVENANCE",
    "IncidentsPage",
    "AlertsV2Page",
    "AlertResult",
    "AdvancedHuntingColumn",
    "AdvancedHuntingResult",
    "MicrosoftGraphApiSecurityConfig",
    "AUTH_APP_PERMISSION", "AUTH_DELEGATED",
    "OPERATION_MODELS",
]
