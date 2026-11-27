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
_DETERMINATION_BY_CLASSIFICATION: dict[str, frozenset[str]] = {
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

    ``expiresOn`` is an **epoch-float** (``time() + expires_in``), normalized
    to ``float`` here from float/int/numeric-string. Live-capture-corrected
    (2026-11): an earlier read claimed a ctime STRING; that is wrong --
    ``convert_ts_epoch`` runs ``ctime(ts)`` on the stored value, which
    requires a NUMBER (it produces the ctime string internally and parses it
    back), so a preseeded ctime string crashes the op with a ValueError.
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
    expiresOn: float | None = None
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

    @field_validator("expiresOn", mode="before")
    @classmethod
    def _epoch_float_expires_on(cls, value: Any) -> Any:
        """The stored value is what ``time() + expires_in`` produced: a NUMBER
        (``convert_ts_epoch`` runs ``ctime()`` on it, so a ctime STRING or any
        non-numeric form crashes the op). Numeric strings are tolerated --
        ``convert_ts_epoch`` floats them itself."""
        if value is None or isinstance(value, float):
            return value
        if isinstance(value, bool):
            raise ValueError("expiresOn must be an epoch number, not a bool")
        if isinstance(value, int):
            return float(value)
        if isinstance(value, str):
            return float(value)  # raises ValueError -> clean ValidationError
        raise ValueError(
            "expiresOn must be an epoch float (time.time() + seconds), not "
            f"{type(value).__name__}"
        )

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


class AlertDevice(BaseModel):
    """One device block inside an alert's ``devices[]``.

    Provenance: live-verified on 8.0.1 (incident detail with alerts expanded);
    sanitized. ``mdatpDeviceId`` is the id the machines API keys on, so it is
    the link from an incident to :func:`get_machine`.
    """

    model_config = ConfigDict(extra="allow")

    mdatpDeviceId: str | None = None
    aadDeviceId: str | None = None
    deviceDnsName: str | None = None
    osPlatform: str | None = None
    version: str | None = None
    osProcessor: str | None = None
    osBuild: int | None = None
    healthStatus: str | None = None
    riskScore: str | None = None
    onboardingStatus: str | None = None
    firstSeen: str | None = None
    loggedOnUsers: list[Any] = Field(default_factory=list)

    _coerce_null_users = field_validator("loggedOnUsers", mode="before")(_none_to_empty_list)


class IncidentAlert(BaseModel):
    """One alert bundled into an incident.

    Provenance: source-derived (operations.py), live-capture pending -- field
    set from the info.json ``output_schema``; values kept ``str`` rather than
    Literal because only a capture can pin the enumerations (severity,
    serviceSource, detectionSource, ...). ``resolvedTime`` is null for active
    alerts; ``devices`` is a list of device objects (see :class:`AlertDevice`).
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
    devices: list[AlertDevice] = Field(default_factory=list)
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
body is empty (``api_request`` returns ``True`` for an empty body).

The same empty-body quirk as the graph-security pair's
``graph_common.MutationNoContentResult``; this union keeps the dict side
typed to the connector's own output_schema instead of a bare dict."""


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


# ---- machine (endpoint) operations -------------------------------------
#
# The machines API shares the unified host (api.security.microsoft.com) but
# needs a token minted for the WindowsDefenderATP resource; the connector mints
# that token itself (machine_ops.py, connector 1.3.0+). Every machine action is
# asynchronous: the POST returns the machine action record (status Pending)
# and the caller polls get_machine_action until a terminal status.

MACHINE_ID_PATTERN = r"^[0-9a-fA-F]{40}$"
MACHINE_ACTION_ID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
MACHINE_ACTION_TERMINAL_STATUSES = ("Succeeded", "Failed", "Cancelled", "TimeOut")


class ListMachinesParams(BaseModel):
    """``list_machines`` params. ``filter`` is an OData ``$filter``; ``top`` a count.

    Provenance: live-verified on 8.0.1 (params as the connector sent them in
    the scenario D runs). Blank TEXT params arrive as ``""`` from the platform
    -- normalized to None.
    """

    model_config = ConfigDict(extra="allow")

    filter: StrictStr | None = None
    top: StrictInt | None = Field(default=None, ge=1)

    _blank_filter = field_validator("filter", mode="before")(_blank_to_none)

    @field_validator("top", mode="before")
    @classmethod
    def _blank_top(cls, value: Any) -> Any:
        if value in ("", None):
            return None
        if isinstance(value, str):
            return int(value)
        return value


class MachineIdParams(BaseModel):
    """Params for the ops that address one device by its 40-hex machine id.

    Provenance: live-verified on 8.0.1 (the isolate, release, scan, package and
    app-execution ops ran with these params).
    """

    model_config = ConfigDict(extra="allow")

    id: StrictStr = Field(pattern=MACHINE_ID_PATTERN)
    comment: StrictStr | None = None

    _blank_comment = field_validator("comment", mode="before")(_blank_to_none)


class IsolateMachineParams(MachineIdParams):
    """``isolate_machine`` params. Full cuts all traffic but the Defender channel.

    Provenance: live-verified on 8.0.1 (Full and Selective isolation ran).
    """

    isolation_type: Literal["Full", "Selective"] = "Full"

    @field_validator("isolation_type", mode="before")
    @classmethod
    def _blank_isolation(cls, value: Any) -> Any:
        return "Full" if value in ("", None) else value


class RunAVScanParams(MachineIdParams):
    """``run_av_scan`` params. Quick is the platform default.

    Provenance: live-verified on 8.0.1 (a Quick scan ran to Succeeded).
    """

    scan_type: Literal["Quick", "Full"] = "Quick"

    @field_validator("scan_type", mode="before")
    @classmethod
    def _blank_scan(cls, value: Any) -> Any:
        return "Quick" if value in ("", None) else value


class GetMachineActionParams(BaseModel):
    """``get_machine_action`` params: the GUID the action operation returned.

    Provenance: live-verified on 8.0.1 (polled to a terminal status).
    """

    model_config = ConfigDict(extra="allow")

    id: StrictStr = Field(pattern=MACHINE_ACTION_ID_PATTERN)


class Machine(BaseModel):
    """``get_machine`` output (one element of ``list_machines`` ``value``).

    Provenance: live-verified on 8.0.1 (machines list + machine detail);
    sanitized. ``extra="allow"`` keeps the rest of the Defender record.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: StrictStr
    computerDnsName: str | None = None
    osPlatform: str | None = None
    osBuild: int | None = None
    healthStatus: str | None = None
    onboardingStatus: str | None = None
    riskScore: str | None = None
    exposureLevel: str | None = None
    firstSeen: str | None = None
    lastSeen: str | None = None
    lastIpAddress: str | None = None
    lastExternalIpAddress: str | None = None
    agentVersion: str | None = None
    machineTags: list[str] = Field(default_factory=list)

    _coerce_null_tags = field_validator("machineTags", mode="before")(_none_to_empty_list)


class MachineListResponse(BaseModel):
    """``list_machines`` output: the OData collection of machines.

    Provenance: live-verified on 8.0.1 (machines list); sanitized.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    odata_context: str | None = Field(default=None, alias="@odata.context")
    value: list[Machine]


class MachineAction(BaseModel):
    """A machine action record: the POST result of every action op, and the
    ``get_machine_action`` poll result.

    Provenance: live-verified on 8.0.1 (isolate, unisolate, AV scan, package
    collection, app-execution restriction); sanitized. ``status`` walks
    Pending -> InProgress -> one of :data:`MACHINE_ACTION_TERMINAL_STATUSES`.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    odata_context: str | None = Field(default=None, alias="@odata.context")
    id: StrictStr
    type: str | None = None
    status: Literal["Pending", "InProgress", "Succeeded", "Failed", "Cancelled", "TimeOut"]
    machineId: str | None = None
    computerDnsName: str | None = None
    requestor: str | None = None
    requestorComment: str | None = None
    requestSource: str | None = None
    scope: str | None = None
    errorHResult: int | None = None
    creationDateTimeUtc: str | None = None
    lastUpdateDateTimeUtc: str | None = None
    commands: list[Any] = Field(default_factory=list)

    _coerce_null_commands = field_validator("commands", mode="before")(_none_to_empty_list)


#: Per-op PARAM models. The graph-security pair types its params only in the
#: docstrings; this connector's params carry real platform quirks (blank-string
#: TEXT params, the unchecked-checkbox ``get_all_records: ""``, the
#: microseconds-only datetime format, the classification/determination pair),
#: so they get first-class models AND a registry.
OP_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "list_incidents": ListIncidentsParams,
    "get_incident": GetIncidentParams,
    "update_incident": UpdateIncidentParams,
    "advanced_hunting": AdvancedHuntingParams,
    "list_machines": ListMachinesParams,
    "get_machine": MachineIdParams,
    "isolate_machine": IsolateMachineParams,
    "unisolate_machine": MachineIdParams,
    "run_av_scan": RunAVScanParams,
    "collect_investigation_package": MachineIdParams,
    "restrict_app_execution": MachineIdParams,
    "unrestrict_app_execution": MachineIdParams,
    "get_machine_action": GetMachineActionParams,
}

#: Per-op OUTPUT models -- same name/shape as the graph-security pair's
#: ``OPERATION_MODELS`` so the shared suites can route uniformly.
#: ``update_incident`` maps to the UNION (dict or the empty-body ``True``),
#: not a single model class.
OPERATION_MODELS: dict[str, Any] = {
    "list_incidents": IncidentListResponse,
    "get_incident": GetIncidentResponse,
    "update_incident": UpdateIncidentResponse,
    "advanced_hunting": AdvancedHuntingResponse,
    "list_machines": MachineListResponse,
    "get_machine": Machine,
    "isolate_machine": MachineAction,
    "unisolate_machine": MachineAction,
    "run_av_scan": MachineAction,
    "collect_investigation_package": MachineAction,
    "restrict_app_execution": MachineAction,
    "unrestrict_app_execution": MachineAction,
    "get_machine_action": MachineAction,
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
    "AlertDevice",
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
    "ListMachinesParams",
    "MachineIdParams",
    "IsolateMachineParams",
    "RunAVScanParams",
    "GetMachineActionParams",
    "Machine",
    "MachineListResponse",
    "MachineAction",
    "MACHINE_ACTION_TERMINAL_STATUSES",
    "OP_PARAM_MODELS",
    "OPERATION_MODELS",
]
