"""Shapes shared by the Microsoft Graph security connectors.

Covers the Graph entities both soarshelf connectors return (security
incidents, the two alert generations, alert comments) plus the two error
envelopes a live tenant produces: the AADSTS body the token endpoint
returns on a rejected client credential, and the nested ``error`` envelope
the Graph resource endpoints return on 401/403/404/429.

Every model is ``extra="allow"``: Graph adds fields constantly and a
playbook must keep reading them, so unknown keys are preserved (and a
``model_dump(by_alias=True)`` round-trips the wire dict verbatim). Wire
keys are aliased to pythonic names; ``populate_by_name`` accepts both.

Provenance markers follow the m365-trial plan §8.2: until a live capture
lands under ``scratch/captures/<connector>/<op>.json`` and is promoted
into ``mocks/``, a model is ``source-derived`` from the connector's
operations.py/info.json (with the reference store as corroboration) and
must be treated as unverified against the wire.
"""
from __future__ import annotations

import re
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, RootModel

T = TypeVar("T")

_TOKEN_ERROR_TEXT_RE = re.compile(
    r"^Response (?P<status>\d+): (?P<reason>.*?)\s*\n\s*Error Message: (?P<msg>.*)$",
    re.DOTALL,
)

#: Exact provenance string for shapes both connectors share. Versions are
#: the two connector packages' info.json versions.
SHARED_PROVENANCE = (
    "Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0, "
    "operations.py microsoft-graph-api-security v1.0.0), live-capture pending."
)


class _WireModel(BaseModel):
    """Base for every Graph wire model: keep unknown keys, dump wire keys."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ODataListPage(_WireModel, Generic[T]):
    """A Graph collection response: ``value`` plus the OData control keys.

    ``@odata.nextLink`` appears only when more pages exist; ``@odata.count``
    only when the caller passed ``$count=true`` (both connectors expose
    that as a checkbox/text param). ``fetch_all_records`` in the
    microsoft-graph-api-security connector strips ``@odata.nextLink`` when
    ``getAllRecords`` is set, so a getAllRecords capture has no nextLink.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    operations.py microsoft-graph-api-security v1.0.0), live-capture pending.
    """

    odata_context: str | None = Field(None, alias="@odata.context")
    odata_next_link: str | None = Field(None, alias="@odata.nextLink")
    odata_count: int | None = Field(None, alias="@odata.count")
    value: list[T]


class GraphInnerError(_WireModel):
    """``error.innerError`` of a Graph resource error body.

    Carries the request correlation ids a support thread will ask for.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    operations.py microsoft-graph-api-security v1.0.0), live-capture pending.
    """

    date: str | None = None
    request_id: str | None = Field(None, alias="request-id")
    client_request_id: str | None = Field(None, alias="client-request-id")


class GraphErrorBody(_WireModel):
    """The ``error`` object of a Graph resource error body.

    ``code`` is Graph's stable-ish machine code: ``Forbidden`` /
    ``AccessDenied`` for missing application permissions, ``NotFoundError``
    for a bad id, ``TooManyRequests`` (or ``applicationThrottled``) for a
    429. The microsoft-graph-api-security connector retries 429s itself
    (10 retries, 10s apart) before surfacing anything.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    operations.py microsoft-graph-api-security v1.0.0), live-capture pending.
    """

    code: str | None = None
    message: str | None = None
    innerError: GraphInnerError | None = None


class GraphErrorEnvelope(_WireModel):
    """The JSON body Graph returns on 401/403/404/429 at the resource.

    Both connectors wrap this into a ``ConnectorError`` string rather than
    returning it, so the envelope describes what the RAISED text embeds --
    capture fixtures may hold the raw body when an op 403s.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    operations.py microsoft-graph-api-security v1.0.0), live-capture pending.
    """

    error: GraphErrorBody


class AadstsTokenError(_WireModel):
    """The token endpoint's error body (AADSTS codes), flattened.

    Both connectors' ``acquire_token_with_client_credentials`` read
    ``error`` + ``error_description`` out of this shape and wrap them into
    ``Response <status>: <reason> \\n Error Message: <error_description>``.
    Common codes: 7000215 (bad client secret), 700016 (app not found in
    tenant), 90019 (expired secret), 700082 (expired token).

    Provenance: source-derived (microsoft_api_auth.py microsoft-graph_dev
    v3.1.0, microsoft_api_auth.py microsoft-graph-api-security v1.0.0),
    live-capture pending.
    """

    error: str
    error_description: str | None = None
    error_codes: list[int] | None = None
    timestamp: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None
    error_uri: str | None = None

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


class TokenResponseErrorText(_WireModel):
    """The ConnectorError text both auth modules raise for a failed token
    request: ``Response <status>: <reason> \\n Error Message: <description>``.

    Provenance: source-derived (microsoft_api_auth.py microsoft-graph_dev
    v3.1.0, microsoft_api_auth.py microsoft-graph-api-security v1.0.0),
    live-capture pending.
    """

    status: int
    reason: str
    error_message: str

    @classmethod
    def parse(cls, text: str) -> TokenResponseErrorText | None:
        m = _TOKEN_ERROR_TEXT_RE.match(text.strip())
        if not m:
            return None
        return cls(
            status=int(m.group("status")),
            reason=m.group("reason").strip(),
            error_message=m.group("msg").strip(),
        )


class AlertComment(_WireModel):
    """One analyst comment on an alerts_v2 alert.

    Provenance: source-derived (info.json output_schema, microsoft-graph_dev
    v3.1.0), live-capture pending.
    """

    comment: str | None = None
    createdDateTime: str | None = None
    createdByDisplayName: str | None = None


class VendorInformation(_WireModel):
    """``vendorInformation`` of a legacy (v1) security alert.

    Provenance: source-derived (info.json output_schema, microsoft-graph_dev
    v3.1.0), live-capture pending.
    """

    provider: str | None = None
    providerVersion: str | None = None
    subProvider: str | None = None
    vendor: str | None = None


class HostState(_WireModel):
    """One ``hostStates`` entry of a legacy (v1) security alert.

    Provenance: source-derived (info.json output_schema, microsoft-graph_dev
    v3.1.0), live-capture pending.
    """

    fqdn: str | None = None
    isAzureAdJoined: bool | None = None
    isAzureAdRegistered: bool | None = None
    isHybridAzureDomainJoined: bool | None = None
    netBiosName: str | None = None
    os: str | None = None
    privateIpAddress: str | None = None
    publicIpAddress: str | None = None
    riskScore: str | None = None


class LegacySecurityAlert(_WireModel):
    """A v1.0 ``/security/alerts`` entity (the ``api_version=V1`` branch).

    The v1 alert is what ``/security/incidents?$expand=alerts`` embeds and
    what the microsoft-graph_dev connector returns on its V1 path. Graph is
    retiring the v1 alert surface; fields listed in the connector's
    info.json but not modeled here (fileStates, malwareStates, ...) still
    pass through under ``extra="allow"``.

    ``azureTenantId`` is required: it is the field that discriminates this
    generation from a v2 alert in the union models.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    info.json output_schema; corroborated by reference store microsoft-graph
    2.2.0), live-capture pending.
    """

    azureTenantId: str
    odata_context: str | None = Field(None, alias="@odata.context")
    id: str | None = None
    activityGroupName: str | None = None
    assignedTo: str | None = None
    category: str | None = None
    closedDateTime: str | None = None
    cloudAppStates: list[dict[str, Any]] | None = None
    comments: list[Any] | None = None
    confidence: int | None = None
    createdDateTime: str | None = None
    description: str | None = None
    detectionIds: list[str] | None = None
    eventDateTime: str | None = None
    feedback: str | None = None
    fileStates: list[dict[str, Any]] | None = None
    hostStates: list[HostState] | None = None
    incidentIds: list[str] | None = None
    lastEventDateTime: str | None = None
    lastModifiedDateTime: str | None = None
    recommendedActions: list[str] | None = None
    riskScore: str | None = None
    severity: str | None = None
    sourceMaterials: list[str] | None = None
    status: str | None = None
    tags: list[str] | None = None
    title: str | None = None
    vendorInformation: VendorInformation | None = None
    vulnerabilityStates: list[dict[str, Any]] | None = None


class SecurityAlertV2(_WireModel):
    """A ``/security/alerts_v2`` entity (the Microsoft 365 Defender alert).

    Returned by microsoft-graph_dev's ``api_version=V2`` branch and by the
    whole alert surface of microsoft-graph-api-security. ``tenantId`` is
    required: it discriminates this generation from a v1 alert in the
    union models. ``evidence`` is a heterogeneous list of
    ``@odata.type``-tagged evidence resources (user, device, mailbox,
    url, ...); typing the union is deferred to a live capture.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    operations.py microsoft-graph-api-security v1.0.0, info.json
    output_schema), live-capture pending.
    """

    tenantId: str
    id: str | None = None
    title: str | None = None
    status: str | None = None
    category: str | None = None
    classification: str | None = None
    determination: str | None = None
    severity: str | None = None
    assignedTo: str | None = None
    actorDisplayName: str | None = None
    alertWebUrl: str | None = None
    incidentId: str | None = None
    incidentWebUrl: str | None = None
    detectorId: str | None = None
    detectionSource: str | None = None
    serviceName: str | None = None
    serviceSource: str | None = None
    productName: str | None = None
    productVersion: str | None = None
    alertPolicyId: str | None = None
    providerAlertId: str | None = None
    firstActivityDateTime: str | None = None
    lastActivityDateTime: str | None = None
    lastUpdateDateTime: str | None = None
    createdDateTime: str | None = None
    resolvedDateTime: str | None = None
    description: str | None = None
    recommendedActions: str | None = None
    threatDisplayName: str | None = None
    threatFamilyName: str | None = None
    mitreTechniques: list[str] | None = None
    systemTags: list[str] | None = None
    comments: list[AlertComment] | None = None
    evidence: list[dict[str, Any]] | None = None
    # additionalData is an object on the wire; connector v3.1.0's info.json
    # declares it as a bare string in one variant -- tolerate both.
    additionalData: dict[str, Any] | str | None = None


#: Both alert generations in one union, for ops whose ``api_version`` param
#: picks the generation at runtime (microsoft-graph_dev's alert ops).
AlertUnion = LegacySecurityAlert | SecurityAlertV2

#: alerts_v2 list page (microsoft-graph-api-security get_security_alerts,
#: microsoft-graph_dev get_all_security_alerts with api_version=V2).
SecurityAlertsV2Page = ODataListPage[SecurityAlertV2]

#: Legacy v1 alert list page (microsoft-graph_dev get_all_security_alerts
#: with api_version=V1).
LegacySecurityAlertsPage = ODataListPage[LegacySecurityAlert]


class SecurityIncident(_WireModel):
    """A ``/security/incidents`` entity (Microsoft 365 Defender incident).

    ``alerts`` is only present when the caller asked for
    ``$expand=alerts`` (microsoft-graph_dev's ``fetchAlerts`` checkbox,
    microsoft-graph-api-security's ``expandAlerts``). The expanded alert
    entries' exact generation is pending a live capture, so they pass
    through as dicts.

    Provenance: source-derived (operations.py microsoft-graph_dev v3.1.0,
    operations.py microsoft-graph-api-security v1.0.0), live-capture pending.
    """

    id: str
    title: str | None = None
    status: str | None = None
    severity: str | None = None
    classification: str | None = None
    determination: str | None = None
    assignedTo: str | None = None
    createdDateTime: str | None = None
    lastUpdateDateTime: str | None = None
    firstActivityDateTime: str | None = None
    lastActivityDateTime: str | None = None
    incidentWebUrl: str | None = None
    redirectIncidentId: str | None = None
    resolvingComment: str | None = None
    comments: list[AlertComment] | None = None
    customTags: list[str] | None = None
    alerts: list[dict[str, Any]] | None = None
    tenantId: str | None = None


#: /security/incidents list page (both connectors' get_security_incidents).
SecurityIncidentsPage = ODataListPage[SecurityIncident]


class MutationNoContentResult(RootModel[bool | dict[str, Any]]):
    """What a PATCH that Graph answers with 204 No Content surfaces as.

    The microsoft-graph-api-security ``api_request`` helper returns the
    literal ``True`` when a success status carries an empty body, so its
    mutating ops (update_security_incident, and the unregistered
    update_security_alert) yield ``True`` in practice -- NOT the field
    echo its info.json output_schema advertises. If Graph ever returns a
    body, the parsed dict passes through instead.

    Provenance: source-derived (operations.py microsoft-graph-api-security
    v1.0.0, api_request empty-body branch), live-capture pending.
    """


class GraphThrottleMeta(_WireModel):
    """Fields a 429 body / Retry-After response carries, for fixtures.

    The microsoft-graph-api-security connector retries 429s internally
    (10 x 10s) and then raises; microsoft-graph_dev raises immediately.

    Provenance: source-derived (operations.py microsoft-graph-api-security
    v1.0.0, api_request retry loop), live-capture pending.
    """

    retry_after_seconds: int | None = None


def parse_graph_connector_error(text: str) -> GraphConnectorErrorText | None:
    """Parse the two ConnectorError text shapes the graph-security pair raises.

    microsoft-graph-api-security ``api_request`` raises
    ``Microsoft Graph Error | Status=<int> | Code=<str> | Message=<str>``
    where Code/Message come out of the GraphErrorEnvelope body (or
    ``NonJSONResponse`` / the raw text when the body was not JSON).

    microsoft-graph_dev ``api_request`` raises
    ``Fail To request API <url> response is :b'<json bytes>' with reason:
    <Reason>`` — the JSON body is embedded as a bytes repr and the status is
    only present as the requests reason word (live-proven shape: Graph
    security endpoints 403 "Account is not provisioned" land here).
    """
    m = re.match(
        r"^Microsoft Graph Error \| Status=(?P<status>\d+) "
        r"\| Code=(?P<code>.*?) \| Message=(?P<message>.*)$",
        text.strip(),
        re.DOTALL,
    )
    if m:
        return GraphConnectorErrorText(
            status=int(m.group("status")),
            code=m.group("code"),
            message=m.group("message"),
        )
    m = re.match(
        r"^Fail To request API (?P<url>\S+) response is :b?'?(?P<body>.*?)'?;"
        r"? with reason: (?P<reason>[A-Za-z ]+)$",
        text.strip(),
        re.DOTALL,
    )
    if m:
        reason_to_status = {
            "Unauthorized": 401,
            "Forbidden": 403,
            "NotFound": 404,
            "BadRequest": 400,
            "Conflict": 409,
            "TooManyRequests": 429,
            "InternalServerError": 500,
        }
        # the reason is the requests HTTP phrase ("Not Found"); strip spaces
        status = reason_to_status.get(m.group("reason").replace(" ", ""), 0)
        # the embedded body carries the authoritative code/message
        body = extract_error_body(m.group("body"))
        code = ""
        message = m.group("body")[:300]
        if body:
            err = body.get("error", body)
            code = str(err.get("code", ""))
            message = str(err.get("message", message))
        return GraphConnectorErrorText(
            status=status,
            code=code,
            message=message,
        )
    return None


class GraphConnectorErrorText(_WireModel):
    """The microsoft-graph-api-security ConnectorError text, typed.

    Provenance: source-derived (operations.py microsoft-graph-api-security
    v1.0.0), live-capture pending.
    """

    status: int
    code: str
    message: str


def extract_error_body(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON error body embedded in an
    error string (microsoft-graph_dev embeds ``response.content`` raw)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start:end + 1]
    import json

    try:
        parsed = json.loads(candidate)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


__all__ = [
    "SHARED_PROVENANCE",
    "ODataListPage",
    "GraphInnerError",
    "GraphErrorBody",
    "GraphErrorEnvelope",
    "AadstsTokenError",
    "TokenResponseErrorText",
    "AlertComment",
    "VendorInformation",
    "HostState",
    "LegacySecurityAlert",
    "SecurityAlertV2",
    "AlertUnion",
    "SecurityAlertsV2Page",
    "LegacySecurityAlertsPage",
    "SecurityIncident",
    "SecurityIncidentsPage",
    "MutationNoContentResult",
    "GraphThrottleMeta",
    "GraphConnectorErrorText",
    "parse_graph_connector_error",
    "extract_error_body",
]
