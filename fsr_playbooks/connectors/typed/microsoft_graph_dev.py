"""Typed outputs for the soarshelf ``microsoft-graph_dev`` connector.

Source: ``soarshelf/content/connectors/get-microsoft-graph-security-incidents-
with-reworked-auth/package/microsoft-graph_dev`` (info.json version 3.1.0,
label "Microsoft Graph API (fork)"). One output model per operation in its
``operations`` dict, plus the config model typed from its info.json
``configuration`` block. The models exist so playbook tooling (compiler,
linter, agent) knows what ``vars.steps.<step>.<field>`` can hold after one
of these ops runs -- connector outputs land under ``data`` in production
and directly on the step under ``--mock`` (see the linter's mock-envelope
rule).

Wire quirks the models normalize (all source-observed in operations.py
v3.1.0, none live-verified yet):

- ``search_message`` / ``del_message_bulk`` aggregate a 4-thread pool.
  Each result key (``Message_Found_List``, ``Message_Not_Found_List``,
  ``Error_List``, ``Message_Deleted_List``) is present ONLY when
  non-empty; ``Run_Time`` is a float; ``Total_Users_Processed`` counts
  ``len(params["user_list"])`` -- the string length when the caller
  passed a comma-separated string, not the user count.
- A per-user page in ``Message_Found_List`` / ``Message_Not_Found_List``
  is the RAW messages-list response with ``user_id`` injected at top
  level; a 400 from Graph lands in ``Message_Not_Found_List`` as an
  error body (``error`` key) rather than a page.
- ``del_message`` returns ``{"status_code": 204}`` (the only op that
  surfaces a bare status code).
- ``revoke_user_sessions`` returns ``{"@odata.context": ..., "value":
  true}`` with a real boolean.
- ``get_all_security_alerts`` builds its OData ``$filter`` through
  ``get_filter_query_string``, which maps ``determination`` and
  ``severity`` through the STATUS table -- both lookups miss for every
  real value, so those two filters silently drop out of the request.
- ``get_all_named_locations`` / the named-location mutators return the
  ipNamedLocation/countryNamedLocation union keyed by ``@odata.type``.
- The connector's ``execute`` injects ``config["api_version"] = "v1.0"``
  (via the constants star-import chain); the per-op ``api_version``
  param on the alert ops selects the alerts surface independently.

Provenance for every model here, until live captures land:
``Provenance: source-derived (operations.py v3.1.0), live-capture pending.``
"""
from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from .graph_common import (
    AlertComment,
    AlertUnion,
    GraphErrorEnvelope,
    ODataListPage,
    SecurityIncidentsPage,
)

#: Exact provenance string required by the m365-trial plan §8.2 for this
#: connector's models (info.json version 3.1.0).
PROVENANCE = "Provenance: source-derived (operations.py v3.1.0), live-capture pending."


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---------------------------------------------------------------------------
# Directory entities
# ---------------------------------------------------------------------------


class RiskyUser(_WireModel):
    """An identityProtection riskyUsers entity.

    ``id`` is required (present on every riskyUsers row). The P2-only
    surface means a Business Premium trial tenant 403s this op -- the
    expected first capture here is a GraphErrorEnvelope, not a page.

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema; corroborated by reference store microsoft-graph 2.2.0),
    live-capture pending.
    """

    id: str
    userPrincipalName: str | None = None
    userDisplayName: str | None = None
    isDeleted: bool | None = None
    isProcessing: bool | None = None
    riskLevel: str | None = None
    riskState: str | None = None
    riskDetail: str | None = None
    riskLastUpdatedDateTime: str | None = None


class RiskyUsersPage(ODataListPage[RiskyUser]):
    """``get_risky_users_list`` output (also its detail-op list form).

    Provenance: source-derived (operations.py v3.1.0), live-capture pending.
    """


class RiskyUserRecord(_WireModel):
    """``get_risky_user_details`` output: one riskyUser + ``@odata.context``.

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema), live-capture pending.
    """

    odata_context: str | None = Field(None, alias="@odata.context")
    id: str
    userPrincipalName: str | None = None
    userDisplayName: str | None = None
    isDeleted: bool | None = None
    isProcessing: bool | None = None
    riskLevel: str | None = None
    riskState: str | None = None
    riskDetail: str | None = None
    riskLastUpdatedDateTime: str | None = None


class DirectoryGroup(_WireModel):
    """A directory group (``/groups``).

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    displayName: str | None = None
    description: str | None = None
    mail: str | None = None
    mailNickname: str | None = None
    mailEnabled: bool | None = None
    securityEnabled: bool | None = None
    groupTypes: list[str] | None = None
    visibility: str | None = None
    classification: str | None = None
    createdDateTime: str | None = None
    deletedDateTime: str | None = None
    expirationDateTime: str | None = None
    renewedDateTime: str | None = None
    resourceProvisioningOptions: list[str] | None = None


class GroupsPage(ODataListPage[DirectoryGroup]):
    """``get_groups`` output (no ``group_id`` -> the /groups listing).

    With a ``group_id`` the same op returns the group's members
    (``/groups/{id}/members``) -- that is ``get_group_users``'s shape, not
    this one, despite the shared implementation.

    Provenance: source-derived (operations.py v3.1.0), live-capture pending.
    """


class DirectoryMember(_WireModel):
    """A member of a group: user, group, service principal or contact.

    ``/groups/{id}/members`` returns heterogeneous directory objects
    discriminated by ``@odata.type``; the connector's info.json shows the
    user shape only. Modeled loosely (id + the user fields the info.json
    declares) until a live capture pins the union.

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    odata_type: str | None = Field(None, alias="@odata.type")
    displayName: str | None = None
    userPrincipalName: str | None = None
    mail: str | None = None
    givenName: str | None = None
    surname: str | None = None
    jobTitle: str | None = None
    businessPhones: list[str] | None = None
    mobilePhone: str | None = None
    officeLocation: str | None = None
    preferredLanguage: str | None = None
    deletedDateTime: str | None = None


class GroupMembersPage(ODataListPage[DirectoryMember]):
    """``get_group_users`` output (``/groups/{id}/members``).

    Provenance: source-derived (operations.py v3.1.0), live-capture pending.
    """


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class SecurityAlertsAnyVersionPage(ODataListPage[AlertUnion]):
    """``get_all_security_alerts`` output for either ``api_version``.

    Items are v1 legacy alerts (``azureTenantId``) when ``api_version``
    is V1 and alerts_v2 alerts (``tenantId``) when V2 -- the union keys
    off exactly those two required fields.

    Source quirk (operations.py v3.1.0 ``get_filter_query_string``): the
    ``determination`` and ``severity`` params are mapped through the
    STATUS table and miss for every real value, so both filters silently
    disappear from the request. Filter with ``$filter``-shaped values via
    a different op or expect the unfiltered page.

    Provenance: source-derived (operations.py v3.1.0, info.json
    conditional_output_schema), live-capture pending.
    """


class SecurityAlertResult(RootModel[AlertUnion]):
    """``get_security_alert`` / ``update_security_alert`` output.

    A single alert of either generation (see ``SecurityAlertsAnyVersionPage``
    for the discriminator); dumps as the bare alert dict.
    ``update_security_alert`` PATCHes and Graph answers with the updated
    alert body.

    Provenance: source-derived (operations.py v3.1.0, info.json
    conditional_output_schema), live-capture pending.
    """


class AlertCommentsPage(ODataListPage[AlertComment]):
    """``add_comment_on_security_alert`` output.

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema), live-capture pending.
    """


# ---------------------------------------------------------------------------
# Mail (thread-pool ops)
# ---------------------------------------------------------------------------


class MailEmailAddress(_WireModel):
    """An email address entry.

    Provenance: source-derived (info.json output_schema v3.1.0),
    live-capture pending.
    """

    name: str | None = None
    address: str | None = None


class MailRecipient(_WireModel):
    """A to/cc/bcc recipient.

    Provenance: source-derived (info.json output_schema v3.1.0),
    live-capture pending.
    """

    emailAddress: MailEmailAddress | None = None


class MailMessageBody(_WireModel):
    """``body`` of a message.

    Provenance: source-derived (info.json output_schema v3.1.0),
    live-capture pending.
    """

    contentType: str | None = None
    content: str | None = None


class MailMessageFlag(_WireModel):
    """``flag`` of a message.

    Provenance: source-derived (info.json output_schema v3.1.0),
    live-capture pending.
    """

    flagStatus: str | None = None


class MailMessage(_WireModel):
    """A mailbox message entity from ``/users/{id}/messages``.

    Provenance: source-derived (operations.py v3.1.0 search_message,
    info.json output_schema), live-capture pending.
    """

    id: str
    subject: str | None = None
    bodyPreview: str | None = None
    body: MailMessageBody | None = None
    sender: MailRecipient | None = None
    from_: MailRecipient | None = Field(None, alias="from")
    toRecipients: list[MailRecipient] | None = None
    ccRecipients: list[MailRecipient] | None = None
    bccRecipients: list[MailRecipient] | None = None
    replyTo: list[MailRecipient] | None = None
    receivedDateTime: str | None = None
    sentDateTime: str | None = None
    createdDateTime: str | None = None
    lastModifiedDateTime: str | None = None
    changeKey: str | None = None
    categories: list[str] | None = None
    hasAttachments: bool | None = None
    internetMessageId: str | None = None
    conversationId: str | None = None
    conversationIndex: str | None = None
    importance: str | None = None
    parentFolderId: str | None = None
    isDeliveryReceiptRequested: bool | None = None
    isReadReceiptRequested: bool | None = None
    isRead: bool | None = None
    isDraft: bool | None = None
    webLink: str | None = None
    inferenceClassification: str | None = None
    flag: MailMessageFlag | None = None


class MailboxMessagePage(_WireModel):
    """One user's messages response inside the thread-pool aggregation.

    Quirks (ThreadRunner.api_call, operations.py v3.1.0): ``user_id`` is
    injected at TOP level of the raw odata response; a 400 response lands
    here as the error body (``error`` key, ``value`` absent) under
    ``Message_Not_Found_List``; an empty mailbox page keeps
    ``value: []``.

    Provenance: source-derived (operations.py v3.1.0 ThreadRunner),
    live-capture pending.
    """

    user_id: str
    odata_context: str | None = Field(None, alias="@odata.context")
    value: list[MailMessage] | None = None
    error: GraphErrorEnvelope | None = None


class MailSearchThreadError(_WireModel):
    """One failed per-user lookup inside ``search_message``.

    ``error_msg`` is the parsed Graph error body on a 403 and the bare
    status code otherwise.

    Provenance: source-derived (operations.py v3.1.0 ThreadRunner),
    live-capture pending.
    """

    user_id: str
    error_msg: int | str | dict[str, Any]


class MailDeleteTarget(_WireModel):
    """The ``user_list`` entry ``del_message_bulk`` echoes back.

    Provenance: source-derived (operations.py v3.1.0 del_message_bulk),
    live-capture pending.
    """

    user_id: str
    message_id: str


class MessageDeleted(_WireModel):
    """One successful delete inside ``del_message_bulk``.

    ``msg_deleted`` is the literal string ``"Yes"``.

    Provenance: source-derived (operations.py v3.1.0 ThreadRunner),
    live-capture pending.
    """

    msg_deleted: str
    user_id: MailDeleteTarget


class MailDeleteThreadError(_WireModel):
    """One failed delete inside ``del_message_bulk``.

    ``error_msg`` is always the bare status code on the delete path.

    Provenance: source-derived (operations.py v3.1.0 ThreadRunner),
    live-capture pending.
    """

    user_id: MailDeleteTarget
    error_msg: int


class ThreadedMailResult(_WireModel):
    """The thread-pool aggregation dict both mail ops return.

    Each list key is present ONLY when non-empty (``api_result`` skips
    empty lists); ``Run_Time`` is wall-clock seconds as a float;
    ``Total_Users_Processed`` is ``len(params["user_list"])`` -- the
    string length, not the user count, when user_list arrived as a
    comma-separated string.

    Provenance: source-derived (operations.py v3.1.0 ThreadCreate.api_result),
    live-capture pending.
    """

    message_found_list: list[MailboxMessagePage] | None = Field(
        None, alias="Message_Found_List"
    )
    message_not_found_list: list[MailboxMessagePage] | None = Field(
        None, alias="Message_Not_Found_List"
    )
    error_list: list[MailSearchThreadError | MailDeleteThreadError] | None = Field(
        None, alias="Error_List"
    )
    message_deleted_list: list[MessageDeleted] | None = Field(
        None, alias="Message_Deleted_List"
    )
    run_time: float = Field(alias="Run_Time")
    total_users_processed: int = Field(alias="Total_Users_Processed")


class DeleteMessageResult(_WireModel):
    """``del_message`` output: the only op returning a bare status code.

    Provenance: source-derived (operations.py v3.1.0 del_message), live-capture
    pending.
    """

    status_code: int


# ---------------------------------------------------------------------------
# Identity / conditional access
# ---------------------------------------------------------------------------


class RevokeSessionsResult(_WireModel):
    """``revoke_user_sessions`` output.

    Graph returns ``{"@odata.context": ..., "value": true}``; the connector
    passes the parsed body through. A string ``"true"`` is coerced so a
    sloppy wire/fixture variant still validates.

    Provenance: source-derived (operations.py v3.1.0 revoke_user_sessions,
    info.json output_schema), live-capture pending.
    """

    odata_context: str | None = Field(None, alias="@odata.context")
    value: bool

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_bool(cls, v: Any) -> Any:
        if isinstance(v, str) and v.lower() == "true":
            return True
        return v


class IpRange(_WireModel):
    """One CIDR range of a named location.

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema), live-capture pending.
    """

    odata_type: str | None = Field(None, alias="@odata.type")
    cidrAddress: str | None = None


class NamedLocation(_WireModel):
    """A conditionalAccess namedLocation (IP or country flavor).

    ``ipRanges`` belongs to ``#microsoft.graph.ipNamedLocation``;
    ``countriesAndRegions`` / ``countryLookupMethod`` /
    ``includeUnknownCountriesAndRegions`` belong to
    ``#microsoft.graph.countryNamedLocation``. ``isTrusted`` true means
    the block/unblock mutators refuse the location
    ("Specified named location is trusted...").

    Provenance: source-derived (operations.py v3.1.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    odata_type: str | None = Field(None, alias="@odata.type")
    displayName: str | None = None
    createdDateTime: str | None = None
    modifiedDateTime: str | None = None
    isTrusted: bool | None = None
    ipRanges: list[IpRange] | None = None
    countriesAndRegions: list[str] | None = None
    countryLookupMethod: str | None = None
    includeUnknownCountriesAndRegions: bool | None = None


class NamedLocationsPage(ODataListPage[NamedLocation]):
    """``get_all_named_locations`` output.

    Provenance: source-derived (operations.py v3.1.0), live-capture pending.
    """


class NamedLocationRecord(_WireModel):
    """A single named location: create_ip_range_location / block_new_ips /
    unblock_new_ips output (create POSTs, the mutators PATCH, Graph answers
    each with the location body plus ``@odata.context``).

    Provenance: source-derived (operations.py v3.1.0), live-capture pending.
    """

    odata_context: str | None = Field(None, alias="@odata.context")
    id: str
    odata_type: str | None = Field(None, alias="@odata.type")
    displayName: str | None = None
    createdDateTime: str | None = None
    modifiedDateTime: str | None = None
    isTrusted: bool | None = None
    ipRanges: list[IpRange] | None = None


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


class IncidentsPage(SecurityIncidentsPage):
    """``get_security_incidents`` output.

    ``$expand=alerts`` is requested when the ``fetchAlerts`` checkbox is
    on (its default is true), so the incidents in a capture typically
    carry ``alerts``. ``$count`` is sent only when the ``count`` text
    param is truthy.

    Provenance: source-derived (operations.py v3.1.0), live-capture pending.
    """


# ---------------------------------------------------------------------------
# Config (typed from info.json "configuration", v3.1.0)
# ---------------------------------------------------------------------------

AUTH_APP_PERMISSION: Final = "Without a User - Application Permission"
AUTH_DELEGATED: Final = "On behalf of User - Delegate Permission"
AUTH_CERTIFICATE: Final = "Certificate Based Authentication"


class MicrosoftGraphDevConfig(_WireModel):
    """Config model typed from the connector's info.json configuration
    schema (v3.1.0), plus the runtime keys the connector itself stores
    into the config dict.

    Branch visibility (info.json ``onchange``): ``code``/``redirect_url``
    belong to the delegated branch, ``thumbprint``/``private_key`` to the
    certificate branch. The runtime keys (``accessToken``, ``expiresOn`` as
    a ctime string, ``refresh_token``, ``config_id``) are written back by
    ``validate_token``/``check`` -- they are not user-entered.
    ``api_version`` is NOT a config field: the connector's ``execute``
    injects ``"v1.0"`` on every call.

    Provenance: source-derived (info.json configuration schema v3.1.0,
    connector.py execute), live-capture pending.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    auth_type: Literal[
        "Without a User - Application Permission",
        "On behalf of User - Delegate Permission",
        "Certificate Based Authentication",
    ] = AUTH_APP_PERMISSION
    resource: str = "https://graph.microsoft.com"
    tenant: str
    client_id: str
    client_secret: str | None = None
    code: str | None = None
    redirect_url: str | None = None
    thumbprint: str | None = None
    private_key: dict[str, Any] | str | None = None
    verify_ssl: bool = True

    accessToken: str | None = None
    expiresOn: str | None = None
    refresh_token: str | None = None
    config_id: str | None = None
    api_version: Literal["v1.0"] | None = None
    connector_info: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Op -> model registry (consumed by tests and the mock loader)
# ---------------------------------------------------------------------------

OPERATION_MODELS: dict[str, Any] = {
    "get_risky_users_list": RiskyUsersPage,
    "get_risky_user_details": RiskyUserRecord,
    "get_all_security_alerts": SecurityAlertsAnyVersionPage,
    "get_security_alert": SecurityAlertResult,
    "update_security_alert": SecurityAlertResult,
    "add_comment_on_security_alert": AlertCommentsPage,
    "get_groups": GroupsPage,
    "get_group_users": GroupMembersPage,
    "search_message": ThreadedMailResult,
    "del_message": DeleteMessageResult,
    "del_message_bulk": ThreadedMailResult,
    "revoke_user_sessions": RevokeSessionsResult,
    "get_all_named_locations": NamedLocationsPage,
    "block_new_ips": NamedLocationRecord,
    "unblock_new_ips": NamedLocationRecord,
    "create_ip_range_location": NamedLocationRecord,
    "get_security_incidents": IncidentsPage,
}

__all__ = [
    "PROVENANCE",
    "RiskyUser", "RiskyUsersPage", "RiskyUserRecord",
    "DirectoryGroup", "GroupsPage",
    "DirectoryMember", "GroupMembersPage",
    "SecurityAlertsAnyVersionPage", "SecurityAlertResult",
    "AlertCommentsPage",
    "MailEmailAddress", "MailRecipient", "MailMessageBody", "MailMessageFlag",
    "MailMessage", "MailboxMessagePage", "MailSearchThreadError",
    "MailDeleteTarget", "MessageDeleted", "MailDeleteThreadError",
    "ThreadedMailResult", "DeleteMessageResult",
    "RevokeSessionsResult",
    "IpRange", "NamedLocation", "NamedLocationsPage", "NamedLocationRecord",
    "IncidentsPage",
    "MicrosoftGraphDevConfig",
    "AUTH_APP_PERMISSION", "AUTH_DELEGATED", "AUTH_CERTIFICATE",
    "OPERATION_MODELS",
]
