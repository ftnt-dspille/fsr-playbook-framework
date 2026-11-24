"""Typed models for the microsoft-365-defender connector (FortiSOAR 1.2.x).

The connector talks to the Microsoft 365 Defender API at
``api.security.microsoft.com`` (NOT Graph): ``/api/incidents`` +
``/api/advancedhunting/run``, OAuth2 client-credentials or authorization-code
against ``login.microsoftonline.com/<tenant>/oauth2/v2.0/token`` with scope
``https://api.security.microsoft.com/.default offline_access``.

Models per operation -- outputs are what playbooks consume via
``vars.steps.<step>``, so the compiler/linter/agent tooling is the consumer.
Every model cites its provenance until live captures land:

    Provenance: source-derived (operations.py), live-capture pending.

Wire quirks the models normalize (all source-derived, none invented):

* ``incidentId``/``redirectIncidentId`` arrive as int or str depending on the
  surface -- normalized to ``str`` (the connector's own ``id`` param is text).
* ``tags``/``comments``/``alerts`` may be ``null`` on fresh incidents --
  normalized to empty lists.
* unset TEXT params arrive as ``""`` from the platform (the connector's own
  sample playbook passes ``top: ""``/``get_all_records: ""``) -- optional
  params normalize ``""`` to ``None``; ``get_all_records: ""`` is the
  CHECKED-OFF checkbox and means ``False``, not the default ``True``.
* ``update_incident`` returns ``True`` (not a dict) whenever the PATCH body is
  empty -- ``api_request`` maps an empty body to ``True``; the union model
  accepts both.
* a **404 is NOT an error** on this connector: ``api_request`` RETURNS the raw
  ``requests.Response`` object for 404 instead of raising, so
  ``get_incident``/``update_incident`` on a bad id hand the playbook a
  response object. Not representable as JSON; documented here, normalization
  pending a capture.
* under ``get_all_records=True`` the merged list response keeps the FIRST
  page's ``@odata.nextLink`` -- stale (that page was already fetched);
  following it re-fetches page 2.
* ``list_incidents`` datetimes must carry fractional seconds
  (``convert_date_time`` parses only ``%Y-%m-%dT%H:%M:%S.%fZ``); anything
  else raises ``ConnectorError`` before any HTTP call.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .defender_common import AADSTSError, DefenderAPIError  # noqa: F401  (re-exported)

CONNECTOR = "microsoft-365-defender"

# constant.py STATUS keys -- also the info.json select/multiselect options.
StatusOption = Literal["Active", "Resolved", "In Progress", "Redirected"]

# constant.py CLASSIFICATION keys (display values; the wire values the map
# produces are TruePositive / InformationalExpectedActivity / FalsePositive).
ClassificationOption = Literal[
    "TruePositive", "Informational, expected activity", "FalsePositive"
]

# constant.py DETERMINATION keys. Quirk worth keeping visible: the display
# value "Not enough data to validate" maps to the wire value "120".
DeterminationOption = Literal[
    "Multistage attack",
    "Malicious user activity",
    "Compromised account",
    "Malware",
    "Phishing",
    "Unwanted software",
    "Other",
    "Security test",
    "Line-of-business application",
    "Confirmed activity",
    "Not malicious",
    "Not enough data to validate",
]

# info.json onchange: the determinations each classification offers.
_DETERMINATION_BY_CLASSIFICATION: dict[str, frozenset] = {
    "TruePositive": frozenset(
        {"Multistage attack", "Malicious user activity", "Compromised account",
         "Malware", "Phishing", "Unwanted software", "Other"}
    ),
    "Informational, expected activity": frozenset(
        {"Security test", "Line-of-business application", "Confirmed activity", "Other"}
    ),
    "FalsePositive": frozenset(
        {"Not malicious", "Not enough data to validate", "Other"}
    ),
}

_DEFENDER_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"

_CTIME_FMT = "%a %b %d %H:%M:%S %Y"

# Advanced-hunting result cells are typed per column at query time: strings,
# numbers, booleans, and dynamic (nested JSON) values. Strict scalars keep
# "123" a string instead of a lossy int coercion.
CellValue: TypeAlias = StrictStr | StrictInt | StrictFloat | StrictBool | dict[str, Any] | list[Any] | None


def _as_id_str(value: Any) -> Any:
    """incidentId/redirectIncidentId arrive as int or str; normalize to str."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("incident id must be an int or str, not a bool")
    return value if isinstance(value, str) else str(value)


def _none_to_empty_list(value: Any) -> Any:
    return [] if value is None else value


def _blank_to_none(value: Any) -> Any:
    """The platform hands unset TEXT params as "" (sample playbooks pass
    ``top: ""``); that is "not provided", not an empty value."""
    return None if value == "" else value


class DefenderConnectorConfig(BaseModel):
    """Configuration the ops see, typed from info.json ``configuration``.

    Provenance: source-derived (operations.py), live-capture pending -- field
    set, option lists and defaults from info.json ``configuration.fields``
    (mirrored in the reference store ``connectors.config_schema_json``);
    normalization mirrors ``microsoft_api_auth.MicrosoftAuth.__init__``.

    Normalizations: ``resource`` is normalized the way MicrosoftAuth does it
    (``http://`` -> ``https://``, bare host -> ``https://<host>``) and has a
    trailing slash stripped (the connector does NOT strip it -- a
    trailing-slash resource would produce ``//api/...`` endpoints). The
    runtime-managed keys (``accessToken``/``expiresOn``/``refresh_token``/
    ``config_id``) are written back by the connector itself
    (``microsoft_api_auth.check``), not typed by a user.

    ``expiresOn`` is a **ctime string** ("Mon Nov 24 10:00:00 2026"), not an
    epoch -- ``convert_ts_epoch`` parses it back with ``%a %b %d %H:%M:%S %Y``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    auth_type: Literal[
        "On behalf of User - Delegated Permission",
        "Without a User - Application Permission",
    ] = "Without a User - Application Permission"
    resource: str = "https://api.security.microsoft.com"
    tenant_id: str
    client_id: str
    client_secret: str
    code: str | None = None
    redirect_url: str | None = None
    verify_ssl: bool = True

    # runtime-managed by microsoft_api_auth.check / validate_token
    accessToken: str | None = None
    expiresOn: str | None = None
    refresh_token: str | None = None
    config_id: str | None = None

    @field_validator("resource", mode="after")
    @classmethod
    def _normalize_resource(cls, value: str) -> str:
        host = value.strip()
        if host.startswith("http://"):
            host = "https://" + host[len("http://"):]
        elif not host.startswith("https://"):
            host = "https://" + host
        return host.rstrip("/")

    @field_validator("expiresOn", mode="after")
    @classmethod
    def _ctime_expires_on(cls, value: str | None) -> str | None:
        if value is not None:
            datetime.strptime(value, _CTIME_FMT)  # raises on drift from ctime()
        return value

    @model_validator(mode="after")
    def _delegated_needs_code(self) -> DefenderConnectorConfig:
        if self.auth_type == "On behalf of User - Delegated Permission" and not self.code:
            raise ValueError(
                "auth_type 'On behalf of User - Delegated Permission' requires "
                "'code' (the authorization code from the consent step)"
            )
        return self


class ListIncidentsParams(BaseModel):
    """``list_incidents`` params, typed from info.json + operation_params.

    Provenance: source-derived (operations.py), live-capture pending -- names,
    types and options from info.json parameters / reference-store
    ``operation_params`` (connector ``microsoft-365-defender``); the filter
    assembly is from ``list_incidents`` itself.

    Quirks: ``lastUpdateTime``/``createdTime`` MUST carry fractional seconds
    (``convert_date_time`` parses only ``%Y-%m-%dT%H:%M:%S.%fZ``; a bare
    ``...Z`` raises ``ConnectorError`` before any HTTP call). ``skip`` is a
    TEXT param on the wire schema (not integer). An unknown ``status`` value
    flows through ``STATUS.get`` as ``None`` and becomes the literal OData
    ``status eq 'None'`` -- the Literal below refuses it instead. The op
    builds ``lastUpdateTime ge <ts>`` UNQUOTED; the connector's own sample
    playbook instead passes whole comparisons via ``query``. When
    ``get_all_records`` is true (the info.json default, applied by the
    platform), ``skip`` and ``top`` are ignored entirely; NOTE that an
    in-process caller (capture script, test) must pass it explicitly because
    no platform applies defaults for it.
    """

    model_config = ConfigDict(extra="allow")

    lastUpdateTime: str | None = None
    createdTime: str | None = None
    status: list[StatusOption] | StatusOption | None = None
    assignedTo: str | None = None
    query: str | None = None
    skip: str | None = None
    top: int | None = None
    get_all_records: bool = True

    _blank_params = field_validator(
        "lastUpdateTime", "createdTime", "status", "assignedTo",
        "query", "skip", "top", mode="before",
    )(_blank_to_none)

    @field_validator("lastUpdateTime", "createdTime", mode="after")
    @classmethod
    def _microsecond_format(cls, value: str | None) -> str | None:
        if value is not None:
            datetime.strptime(value, _DEFENDER_DATETIME_FMT)  # the only accepted form
        return value

    @field_validator("get_all_records", mode="before")
    @classmethod
    def _blank_checkbox(cls, value: Any) -> Any:
        # "" is the platform's UNCHECKED checkbox -> False (the sample
        # playbook "Fetch Incidents For Mapping" passes exactly that).
        if value == "":
            return False
        return value


class GetIncidentParams(BaseModel):
    """``get_incident`` params: ``id`` (text, required).

    Provenance: source-derived (operations.py), live-capture pending. An empty
    id would concatenate ``INCIDENT`` ("/api/incidents/") into the COLLECTION
    url -- i.e. a disguised ``list_incidents`` -- so it is refused here.
    """

    model_config = ConfigDict(extra="allow")

    id: str

    @field_validator("id", mode="after")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id must be non-empty (an empty id GETs the collection)")
        return value


class UpdateIncidentParams(BaseModel):
    """``update_incident`` params, typed from info.json + constant.py maps.

    Provenance: source-derived (operations.py), live-capture pending -- the
    classification/determination pairing below is the info.json ``onchange``
    contract (the connector itself does not enforce it; it sends whatever
    maps over, and the API rejects an incompatible pair).

    ``tags`` is ONE csv string on the wire (the op splits on ","), not a list.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    status: StatusOption | None = None
    assignedTo: str | None = None
    classification: ClassificationOption | None = None
    determination: DeterminationOption | None = None
    tags: str | None = None
    comment: str | None = None

    _blank_params = field_validator(
        "id", "status", "assignedTo", "classification",
        "determination", "tags", "comment", mode="before",
    )(_blank_to_none)

    @field_validator("id", mode="after")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id must be non-empty (an empty id PATCHes the collection)")
        return value

    @model_validator(mode="after")
    def _determination_matches_classification(self) -> UpdateIncidentParams:
        if self.determination and not self.classification:
            raise ValueError(
                "determination requires classification (info.json onchange)"
            )
        if self.determination and self.classification:
            allowed = _DETERMINATION_BY_CLASSIFICATION.get(self.classification, frozenset())
            if self.determination not in allowed:
                raise ValueError(
                    f"determination {self.determination!r} is not offered under classification "
                    f"{self.classification!r} (info.json onchange)"
                )
        return self


class AdvancedHuntingParams(BaseModel):
    """``advanced_hunting`` params: ``Query`` (capital Q on the wire, required).

    Provenance: source-derived (operations.py), live-capture pending. The
    connector's sample playbook passes KQL like ``search DeviceName: "abc"``.
    An empty Query POSTs an empty body (``check_payload`` drops falsy values)
    and the API answers 400 -- refused here.
    """

    model_config = ConfigDict(extra="allow")

    Query: str

    @field_validator("Query", mode="after")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Query must be non-empty (an empty body answers 400)")
        return value


class IncidentComment(BaseModel):
    """One incident comment.

    Provenance: source-derived (operations.py), live-capture pending -- shape
    from the update_incident ``output_schema`` in info.json; ``createdBy`` may
    be null for system-generated comments (pending capture).
    """

    model_config = ConfigDict(extra="allow")

    comment: str
    createdBy: str | None = None
    createdTime: str | None = None


class Evidence(BaseModel):
    """One incident/alert entity (evidence row).

    Provenance: source-derived (operations.py), live-capture pending -- the
    declared fields are the ACCOUNT variant the info.json ``output_schema``
    shows; evidence is polymorphic on the wire (device/file/url/mailbox
    variants carry other keys), so ``extra="allow"`` preserves them instead of
    dropping data playbooks may read.
    """

    model_config = ConfigDict(extra="allow")

    entityType: str
    evidenceCreationTime: str | None = None
    verdict: str | None = None
    remediationStatus: str | None = None
    accountName: str | None = None
    userSid: str | None = None
    aadUserId: str | None = None
    userPrincipalName: str | None = None


class IncidentAlert(BaseModel):
    """One alert bundled into an incident.

    Provenance: source-derived (operations.py), live-capture pending -- field
    set from the info.json ``output_schema``; values kept ``str`` rather than
    Literal because only a capture can pin the enumerations (severity,
    serviceSource, detectionSource, ...). ``resolvedTime`` is null for active
    alerts; ``devices`` is a list of device-ID strings.
    """

    model_config = ConfigDict(extra="allow")

    alertId: str
    providerAlertId: str | None = None
    incidentId: str | None = None
    serviceSource: str | None = None
    creationTime: str | None = None
    lastUpdatedTime: str | None = None
    resolvedTime: str | None = None
    firstActivity: str | None = None
    lastActivity: str | None = None
    title: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    severity: str | None = None
    investigationId: str | None = None
    investigationState: str | None = None
    classification: str | None = None
    determination: str | None = None
    detectionSource: str | None = None
    detectorId: str | None = None
    assignedTo: str | None = None
    actorName: str | None = None
    threatFamilyName: str | None = None
    mitreTechniques: list[str] = Field(default_factory=list)
    devices: list[str] = Field(default_factory=list)
    entities: list[Evidence] = Field(default_factory=list)

    _coerce_null_lists = field_validator(
        "mitreTechniques", "devices", "entities", mode="before",
    )(_none_to_empty_list)

    _coerce_incident_id = field_validator("incidentId", mode="before")(_as_id_str)


class Incident(BaseModel):
    """One Defender incident (list item and ``get_incident`` body).

    Provenance: source-derived (operations.py), live-capture pending -- field
    set from the info.json ``output_schema``. ``assignedTo`` is null while an
    incident is unassigned; ``classification``/``determination`` may be null
    or "Unknown" before triage; ``redirectIncidentId`` is "" when not
    redirected. ``incidentId`` is normalized to str (the wire may send int --
    pending capture confirms which).
    """

    model_config = ConfigDict(extra="allow")

    incidentId: str
    incidentUri: str | None = None
    redirectIncidentId: str | None = None
    incidentName: str | None = None
    createdTime: str | None = None
    lastUpdateTime: str | None = None
    assignedTo: str | None = None
    classification: str | None = None
    determination: str | None = None
    status: str | None = None
    severity: str | None = None
    tags: list[str] = Field(default_factory=list)
    comments: list[IncidentComment] = Field(default_factory=list)
    alerts: list[IncidentAlert] = Field(default_factory=list)

    _coerce_null_lists = field_validator(
        "tags", "comments", "alerts", mode="before",
    )(_none_to_empty_list)

    _coerce_ids = field_validator(
        "incidentId", "redirectIncidentId", mode="before",
    )(_as_id_str)


class IncidentListResponse(BaseModel):
    """``list_incidents`` output: an OData collection of incidents.

    Provenance: source-derived (operations.py), live-capture pending -- shape
    from info.json ``output_schema`` plus ``fetch_all_records``.

    Quirk: with ``get_all_records=True`` the op merges every page's ``value``
    but the merged body KEEPS the first page's ``@odata.nextLink`` -- stale,
    that page was already fetched; following it re-fetches page 2. The
    fixture here is a final page (no ``nextLink``).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    odata_context: str | None = Field(default=None, alias="@odata.context")
    value: list[Incident]
    odata_next_link: str | None = Field(default=None, alias="@odata.nextLink")


GetIncidentResponse: TypeAlias = Incident
"""``get_incident`` output: a single incident body (the 404 case returns a raw
``requests.Response`` instead -- see the module docstring)."""


class UpdateIncidentResult(BaseModel):
    """``update_incident`` dict output, typed from its ``output_schema``.

    Provenance: source-derived (operations.py), live-capture pending -- the
    declared fields are the info.json ``output_schema``; the PATCH may return
    the FULL incident instead, which still validates here (extra="allow"
    retains the additional keys).
    """

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    assignedTo: str | None = None
    classification: str | None = None
    determination: str | None = None
    tags: list[str] = Field(default_factory=list)
    comments: list[IncidentComment] = Field(default_factory=list)

    _coerce_null_lists = field_validator(
        "tags", "comments", mode="before",
    )(_none_to_empty_list)


UpdateIncidentResponse: TypeAlias = UpdateIncidentResult | Literal[True]
"""``update_incident`` output: the updated fields, OR ``True`` when the PATCH
body is empty (``api_request`` returns ``True`` for an empty body)."""


class AHDatasetStat(BaseModel):
    """One ``dataset_statistics`` entry of an advanced-hunting run.

    Provenance: source-derived (operations.py), live-capture pending -- shape
    from info.json ``output_schema``.
    """

    model_config = ConfigDict(extra="allow")

    table_row_count: int | None = None
    table_size: int | None = None


class AHStats(BaseModel):
    """The ``Stats`` block of an advanced-hunting response.

    Provenance: source-derived (operations.py), live-capture pending -- shape
    from info.json ``output_schema``. ``ExecutionTime`` is a number in the
    documented samples (the schema placeholder is a string, so both are
    accepted). ``resource_usage`` is kept a loose mapping: its deep
    cache/cpu/memory structure carries no playbook value and a capture will
    pin it.
    """

    model_config = ConfigDict(extra="allow")

    ExecutionTime: float | str | None = None
    dataset_statistics: list[AHDatasetStat] = Field(default_factory=list)
    resource_usage: dict[str, Any] | None = None

    _coerce_null_lists = field_validator("dataset_statistics", mode="before")(
        _none_to_empty_list
    )


class AHSchemaColumn(BaseModel):
    """One column of an advanced-hunting result ``Schema``.

    Provenance: source-derived (operations.py), live-capture pending -- shape
    from info.json ``output_schema`` (``Name``/``Type`` per column, KQL types
    such as ``DateTime``/``string``/``int``/``real``).
    """

    model_config = ConfigDict(extra="allow")

    Name: str
    Type: str


class AdvancedHuntingResponse(BaseModel):
    """``advanced_hunting`` output.

    Provenance: source-derived (operations.py), live-capture pending -- shape
    from info.json ``output_schema``. ``Results`` rows are typed per column at
    query time (see :data:`CellValue`); a row's keys match the ``Schema``
    names. A syntactically bad query is a 400 error body (see
    :class:`~fsr_playbooks.connectors.typed.defender_common.DefenderAPIError`),
    not this shape.
    """

    model_config = ConfigDict(extra="allow")

    Schema: list[AHSchemaColumn] = Field(default_factory=list)
    Results: list[dict[str, CellValue]] = Field(default_factory=list)
    Stats: AHStats | None = None

    _coerce_null_lists = field_validator("Schema", "Results", mode="before")(
        _none_to_empty_list
    )


OP_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "list_incidents": ListIncidentsParams,
    "get_incident": GetIncidentParams,
    "update_incident": UpdateIncidentParams,
    "advanced_hunting": AdvancedHuntingParams,
}

OP_OUTPUT_MODELS: dict[str, Any] = {
    "list_incidents": IncidentListResponse,
    "get_incident": GetIncidentResponse,
    "update_incident": UpdateIncidentResponse,
    "advanced_hunting": AdvancedHuntingResponse,
}

__all__ = [
    "CONNECTOR",
    "AADSTSError",
    "DefenderAPIError",
    "DefenderConnectorConfig",
    "ListIncidentsParams",
    "GetIncidentParams",
    "UpdateIncidentParams",
    "AdvancedHuntingParams",
    "Incident",
    "IncidentAlert",
    "IncidentComment",
    "Evidence",
    "IncidentListResponse",
    "GetIncidentResponse",
    "UpdateIncidentResult",
    "UpdateIncidentResponse",
    "AdvancedHuntingResponse",
    "AHStats",
    "AHSchemaColumn",
    "AHDatasetStat",
    "CellValue",
    "OP_PARAM_MODELS",
    "OP_OUTPUT_MODELS",
]
