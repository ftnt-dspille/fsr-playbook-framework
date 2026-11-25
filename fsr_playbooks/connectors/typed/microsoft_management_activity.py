"""Typed outputs for the Office 365 Management Activity API (the audit plane).

This is NOT a soarshelf connector package: the Management Activity API is
consumed directly over REST (``https://manage.office.com/api/v1.0/{tenant_id}/
activity/feed/...``) with a client-credentials token minted against
``https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token`` with scope
``https://manage.office.com/.default`` (the ``ActivityFeed.Read`` permission).
The capture driver is ``capture_management_activity.py`` next door.

Modeled operations and their outputs (Microsoft Learn, "Office 365
Management Activity API reference" + "Office 365 Management Activity API
schema"):

* ``list_subscriptions``  (GET /subscriptions/list)  -> array of subscription
  items (contentType / status / webhook-or-null).
* ``start_subscription``  (POST /subscriptions/start) -> one subscription
  item (the same shape; the stop operation answers an empty 200 and has no
  model).
* ``list_content``        (GET /subscriptions/content) -> array of content
  blob list items (contentType / contentId / contentUri / contentCreated /
  contentExpiration). Pagination rides the ``NextPageUri`` RESPONSE HEADER,
  not the body -- a header is not modelable JSON.
* ``get_content``         (GET the contentUri) -> a JSON ARRAY of audit
  records (the blob page). Records are heterogeneous, so the page is a union
  of the two per-content-type record models below; for a known content type
  prefer the exact page model from ``CONTENT_PAGE_MODELS``.

Two content types are modeled (the subscriptions this tenant enables):
``Audit.AzureActiveDirectory`` (Microsoft Entra ID audit records) and
``Audit.General`` (everything else: Exchange, SharePoint, Teams, DLP, ...).
``Audit.General`` has no single schema of its own -- its records mix the
Common schema with whichever workload schemas apply -- so its extras below
are the documented per-workload fields, flattened as OPTIONAL (a record
carries only the schemas that apply; ``extra="allow"`` preserves the rest).

Provenance for every model here, until live captures land under
``scratch/captures/microsoft-management-activity/`` and are promoted:

    Provenance: docs-derived (Microsoft Learn, Office 365 Management
    Activity API reference + schema), live-capture pending.

Doc contradictions the models resolve (all within the two Learn pages):

* ``ClientIP`` is marked Mandatory in the Common schema table, yet the
  reference page's own "Retrieve content" sample record (``Add User.``)
  carries NO ClientIP key, and the schema page says Entra events log it as
  ``null``. Typed optional (absent or null both accepted).
* ``LoginStatus``/``UserDomain`` are marked Mandatory in the Microsoft Entra
  Account Logon schema, but they describe ONLY logon records (``RecordType``
  9/15); an Entra admin record (``Add User.``, RecordType 8) has neither.
  Typed optional.
* The subscription-list response sample's LAST item is
  ``{"contentType": "Audit.Exchange", "webhook": null}`` -- no ``status``
  key, while the table says every item has three properties. Typed optional.
* The Entra schema table spells the intra-system correlation GUID
  ``IntraSystemsId``; the reference sample record spells it
  ``IntraSystemId``. Both are typed optional so either wire spelling lands
  on a declared field.
* ``isFulfilled`` appears on real content list items but is NOT in the
  reference page's documented five properties. Typed optional with a
  caveat, pending the first capture.
* The common ``NameValuePair``/``ModifiedProperty`` complex types are
  referenced everywhere as ``Common.NameValuePair`` /
  ``Common.ModifiedProperty`` but never defined member-by-member; their
  members below come from the schema page's own prose ("the name ... the
  new value ... the previous value") and the doc samples.
"""
from __future__ import annotations

from typing import Annotated, Any, Final, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, RootModel

#: Exact provenance string for every model in this module until captures land.
PROVENANCE = (
    "Provenance: docs-derived (Microsoft Learn, Office 365 Management "
    "Activity API reference + schema), live-capture pending."
)

CONNECTOR = "microsoft-management-activity"

MANAGE_API_ROOT: Final = "https://manage.office.com/api/v1.0"
#: The only scope the activity feed accepts (ActivityFeed.Read).
MANAGEMENT_SCOPE: Final = "https://manage.office.com/.default"

ENTRA_CONTENT_TYPE: Final = "Audit.AzureActiveDirectory"
GENERAL_CONTENT_TYPE: Final = "Audit.General"
#: The two subscriptions this tenant enables (modeled ones).
CONTENT_TYPES: Final = (ENTRA_CONTENT_TYPE, GENERAL_CONTENT_TYPE)


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Subscription + content list items (reference page samples)
# ---------------------------------------------------------------------------


class ManagementActivityWebhook(_WireModel):
    """The webhook block of a subscription item.

    ``expiration`` is ``null`` in the doc sample; ``authId`` is absent when
    not configured. ``status`` is enabled / disabled / expired.

    Provenance: docs-derived (reference page, "Start a subscription" and
    "List current subscriptions" samples), live-capture pending.
    """

    status: str | None = None
    address: str | None = None
    authId: str | None = None
    expiration: str | None = None


class SubscriptionListItem(_WireModel):
    """One item of ``/subscriptions/list`` (and of the /start response).

    ``webhook`` is documented as always present but ``null`` when the
    subscription has no webhook -- required key, nullable value. ``status``
    is enabled / disabled; the reference sample's last item omits it
    entirely (see the module docstring), so it is optional here.

    Provenance: docs-derived (reference page, "List current subscriptions"),
    live-capture pending.
    """

    contentType: str
    status: str | None = None
    webhook: ManagementActivityWebhook | None


class SubscriptionsPage(RootModel[list[SubscriptionListItem]]):
    """``list_subscriptions`` output: a JSON array of subscription items.

    Provenance: docs-derived (reference page, "List current subscriptions"),
    live-capture pending.
    """


class ContentListItem(_WireModel):
    """One content blob listed by ``/subscriptions/content``.

    The reference page documents exactly five properties (contentType,
    contentId, contentUri, contentCreated, contentExpiration).
    ``isFulfilled`` is NOT among them but shows up on real responses
    (community-observed; pending capture) -- typed optional with that
    caveat rather than left to ``extra="allow"`` so a playbook can branch
    on it without reaching into extras.

    Provenance: docs-derived (reference page, "List available content"),
    live-capture pending.
    """

    contentType: str
    contentId: str
    contentUri: str
    contentCreated: str
    contentExpiration: str
    isFulfilled: bool | None = None


class ContentPage(RootModel[list[ContentListItem]]):
    """``list_content`` output: a JSON array of content blob list items.

    A truncated listing adds the next page's URL as the ``NextPageUri``
    RESPONSE header (not body JSON) -- follow it until a response without
    the header arrives.

    Provenance: docs-derived (reference page, "List available content"),
    live-capture pending.
    """


# ---------------------------------------------------------------------------
# Common schema (schema page, "Common schema" section)
# ---------------------------------------------------------------------------

#: The Common schema ``UserType`` enumeration, values 0-10 exactly as the
#: schema page's table lists them. NOTE the table's own caveat: for Entra
#: events an administrator is still reported as 0 (Regular).
UserTypeValue = Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

#: The Common schema ``AuditLogScope`` enumeration (0 online, 1 onprem).
AuditLogScopeValue = Literal[0, 1]


class AppAccessContext(_WireModel):
    """The Common schema ``AppAccessContext`` complex type (all optional).

    Provenance: docs-derived (schema page, "Complex Type AppAccessContext"),
    live-capture pending.
    """

    AADSessionId: str | None = None
    APIId: str | None = None
    ClientAppId: str | None = None
    ClientAppName: str | None = None
    CorrelationId: str | None = None
    UniqueTokenId: str | None = None
    IssuedAtTime: str | None = None


#: Type alias for :class:`AppAccessContext`, referenced inside
#: ``CommonAuditRecord`` below. WHY the alias exists: the model's field name
#: IS the wire key ``AppAccessContext``, and with PEP 563 string annotations
#: pydantic evaluates that annotation against the class namespace, where the
#: field's own default (``None``) shadows the class name -- a bare
#: ``AppAccessContext: AppAccessContext | None`` field crashes at import
#: with "unsupported operand type(s) for |: 'NoneType' and 'NoneType'".
#: Referencing the type through this module-level alias avoids the shadow.
_AppAccessContextType = AppAccessContext


class NameValuePair(_WireModel):
    """The ubiquitous ``Common.NameValuePair`` complex type.

    The schema page references it everywhere but never defines its members;
    the doc samples show ``{"Name": ..., "Value": ...}`` with string values,
    so ``Value`` is an optional string here.

    Provenance: docs-derived (schema page references + reference page
    sample), live-capture pending.
    """

    Name: str
    Value: str | None = None


class ModifiedProperty(_WireModel):
    """The ``Common.ModifiedProperty`` complex type (admin events).

    Members from the schema page's prose: the modified property's name, its
    new value and its previous value.

    Provenance: docs-derived (schema page prose), live-capture pending.
    """

    Name: str
    NewValue: str | None = None
    OldValue: str | None = None


class IdentityTypeValuePair(_WireModel):
    """The Entra ``Actor``/``Target`` entry (``Self.IdentityTypeValuePair``).

    ``Type`` is the ``IdentityType`` enum value (the schema page lists the
    member names without numeric values, so it stays an int).

    Provenance: docs-derived (schema page, "Complex Type
    IdentityTypeValuePair"), live-capture pending.
    """

    ID: str
    Type: int


class CommonAuditRecord(_WireModel):
    """The Common schema every audit record starts with.

    Required per the schema table: Id, RecordType, CreationTime, Operation,
    OrganizationId, UserType, UserKey, Workload, UserId. Exceptions to the
    table's own mandatory marks (documented above):

    * ``ClientIP`` is marked Mandatory but the reference sample's ``Add
      User.`` record omits the key and Entra events log it as null ->
      optional.
    * ``ResultStatus`` / ``ObjectId`` / ``Scope`` / ``AppAccessContext``
      are the table's optional four.

    ``CreationTime`` is kept a STRING on purpose (wire form
    ``2015-06-29T20:03:19``, UTC without offset or fraction; some workloads
    add fractions): parsing it into a datetime would impose a format the
    docs do not pin. ``RecordType`` is an int -- the AuditLogRecordType
    enum is huge and keeps growing, so pinning a Literal would go stale;
    the member-name mapping lives in the schema page's table.

    Provenance: docs-derived (schema page, "Common schema" + reference page
    "Retrieve content" sample), live-capture pending.
    """

    Id: str
    RecordType: int
    CreationTime: str
    Operation: str
    OrganizationId: str
    UserType: UserTypeValue
    UserKey: str
    Workload: str
    UserId: str
    ClientIP: str | None = None
    ResultStatus: str | None = None
    ObjectId: str | None = None
    Scope: AuditLogScopeValue | None = None
    AppAccessContext: _AppAccessContextType | None = None


# ---------------------------------------------------------------------------
# Audit.AzureActiveDirectory extras (Entra Base + Entra + Account Logon)
# ---------------------------------------------------------------------------


class EntraAuditRecord(CommonAuditRecord):
    """A Microsoft Entra ID audit record (Audit.AzureActiveDirectory blobs).

    Extras are the three documented Entra schemas, flattened:

    * Microsoft Entra ID Base schema -- ``AzureActiveDirectoryEventType``
      is the schema's one Mandatory field (0 AccountLogon, 1
      AzureApplicationAuditEvent; the enum table gives member names without
      values, so it stays an int), plus the ExtendedProperties and
      ModifiedProperties collections.
    * Microsoft Entra schema -- Actor/Target (IdentityTypeValuePair
      collections), ActorContextId, ActorIpAddress, InterSystemsId,
      IntraSystemsId/IntraSystemId (both spellings exist: schema table vs
      reference sample), SupportTicketId, TargetContextId.
    * Microsoft Entra Account Logon schema -- Application, Client,
      LoginStatus, UserDomain. The table marks LoginStatus/UserDomain
      Mandatory, but they describe logon records only; an admin record
      (``Add User.``) carries neither, so they are optional here.

    Provenance: docs-derived (schema page, Entra sections + reference page
    "Retrieve content" sample), live-capture pending.
    """

    AzureActiveDirectoryEventType: int
    ExtendedProperties: list[NameValuePair] | None = None
    ModifiedProperties: list[ModifiedProperty] | None = None
    Actor: list[IdentityTypeValuePair] | None = None
    ActorContextId: str | None = None
    ActorIpAddress: str | None = None
    InterSystemsId: str | None = None
    IntraSystemsId: str | None = None
    IntraSystemId: str | None = None
    SupportTicketId: str | None = None
    Target: list[IdentityTypeValuePair] | None = None
    TargetContextId: str | None = None
    Application: str | None = None
    Client: str | None = None
    LoginStatus: int | None = None
    UserDomain: str | None = None


# ---------------------------------------------------------------------------
# Audit.General extras (Exchange admin / SharePoint / Teams / DLP schemas)
# ---------------------------------------------------------------------------


class GeneralAuditRecord(CommonAuditRecord):
    """A mixed-workload audit record (Audit.General blobs).

    ``Audit.General`` has no single schema: its records carry the Common
    schema plus whichever workload schemas produced them. The extras below
    are the documented per-workload fields, ALL optional (a record carries
    only the schemas that apply):

    * Exchange Admin schema -- ModifiedObjectResolvedName, Parameters,
      ModifiedProperties, ExternalAccess (the schema's one Mandatory field),
      OriginatingServer, OrganizationName. DeviceId / TokenObjectId /
      TokenTenantId are on the same table but describe Entra-token-carrying
      cmdlets; left to extras pending a capture that shows them.
    * SharePoint Base schema -- Site, ItemType, EventSource, SourceName,
      UserAgent, MachineDomainInfo, MachineId, ListItemUniqueId, ListId,
      ApplicationId, ApplicationDisplayName, IsWorkflow.
    * SharePoint file operations -- SiteUrl, SourceRelativeUrl,
      SourceFileName, SourceFileExtension, DestinationRelativeUrl,
      DestinationFileName, DestinationFileExtension, UserSharedWith,
      SharingType.
    * Microsoft Teams schema (scalar fields + ExtraProperties only; the
      complex Member/Message/HostedContent collections stay loose under
      extra="allow" pending captures) -- TeamName, TeamGuid, ChannelGuid,
      ChannelName, ChannelType, MessageId, MessageSizeInBytes, Action,
      AddOnName, AddOnType, TabType, CallId, Name, NewValue, OldValue,
      ExtraProperties.
    * DLP schema -- SharePointMetaData, ExchangeMetaData, EndpointMetaData
      (complex types kept loose), ExceptionInfo, PolicyDetails (complex),
      SensitiveInfoDetectionIsIncluded. DLP records always carry
      ``UserKey="DlpAgent"``.

    Unknown workload fields ride through ``extra="allow"`` unchanged.

    Provenance: docs-derived (schema page, per-workload sections),
    live-capture pending.
    """

    # Exchange Admin schema
    ModifiedObjectResolvedName: str | None = None
    # LIVE-CAPTURE REBASELINED 2026-11-25: the schema page documents
    # Parameters as a list of Common.NameValuePair, but the wire also
    # delivers a PLAIN STRING on SecurityComplianceCenter-workload records
    # (single-line cmdlet text, e.g. '-Organization "..." -SkipValidations
    # "True"'; observed on 5 records of one Audit.General blob). Accept both.
    Parameters: list[NameValuePair] | str | None = None
    # NonPIIParameters: not in the schema docs; wire-observed on the same
    # SecurityComplianceCenter records (PII-snipped copy of the cmdlet text).
    NonPIIParameters: list[NameValuePair] | str | None = None
    ModifiedProperties: list[ModifiedProperty] | None = None
    ExternalAccess: bool | None = None
    OriginatingServer: str | None = None
    OrganizationName: str | None = None
    # SharePoint Base schema
    Site: str | None = None
    ItemType: str | None = None
    EventSource: str | None = None
    SourceName: str | None = None
    UserAgent: str | None = None
    MachineDomainInfo: str | None = None
    MachineId: str | None = None
    ListItemUniqueId: str | None = None
    ListId: str | None = None
    ApplicationId: str | None = None
    ApplicationDisplayName: str | None = None
    IsWorkflow: bool | None = None
    # SharePoint file operations
    SiteUrl: str | None = None
    SourceRelativeUrl: str | None = None
    SourceFileName: str | None = None
    SourceFileExtension: str | None = None
    DestinationRelativeUrl: str | None = None
    DestinationFileName: str | None = None
    DestinationFileExtension: str | None = None
    UserSharedWith: str | None = None
    SharingType: str | None = None
    # Microsoft Teams schema (scalar subset; see docstring)
    TeamName: str | None = None
    TeamGuid: str | None = None
    ChannelGuid: str | None = None
    ChannelName: str | None = None
    ChannelType: str | None = None
    MessageId: str | None = None
    MessageSizeInBytes: int | None = None
    Action: str | None = None
    AddOnName: str | None = None
    AddOnType: int | None = None
    TabType: str | None = None
    CallId: str | None = None
    Name: str | None = None
    NewValue: str | None = None
    OldValue: str | None = None
    ExtraProperties: list[NameValuePair] | None = None
    # DLP schema (complex collections kept loose pending captures)
    SharePointMetaData: dict[str, Any] | None = None
    ExchangeMetaData: dict[str, Any] | None = None
    EndpointMetaData: dict[str, Any] | None = None
    ExceptionInfo: str | None = None
    PolicyDetails: list[dict[str, Any]] | None = None
    SensitiveInfoDetectionIsIncluded: bool | None = None


class EntraAuditRecordPage(RootModel[list[EntraAuditRecord]]):
    """A whole Audit.AzureActiveDirectory blob: an array of Entra records.

    Provenance: docs-derived (reference page, "Retrieve content" sample),
    live-capture pending.
    """


class GeneralAuditRecordPage(RootModel[list[GeneralAuditRecord]]):
    """A whole Audit.General blob: an array of mixed-workload records.

    Provenance: docs-derived (reference page, "Retrieve content" sample
    shape), live-capture pending.
    """


#: One element of a content blob: an Entra record whenever the Entra Base
#: schema's mandatory ``AzureActiveDirectoryEventType`` is present, anything
#: else a mixed-workload record. LEFT-TO-RIGHT on purpose: both members are
#: extra="allow", so smart-union would tie and pick arbitrarily;
#: left-to-right makes Entra shapes bind deterministically.
AuditRecordElement = Annotated[
    EntraAuditRecord | GeneralAuditRecord,
    Field(union_mode="left_to_right"),
]


class AuditRecordPage(RootModel[list[AuditRecordElement]]):
    """``get_content`` output for any content type: an array of records.

    Elements bind through :class:`AuditRecordElement` (Entra first). When the
    blob's content type is known, prefer the exact page model from
    :data:`CONTENT_PAGE_MODELS`.

    Provenance: docs-derived (reference page, "Retrieve content" sample),
    live-capture pending.
    """


# ---------------------------------------------------------------------------
# Error envelope (reference page, "Errors")
# ---------------------------------------------------------------------------


class ActivityAPIErrorBody(_WireModel):
    """The ``error`` object of a failed activity feed call.

    ``code`` is an ``AF``-prefixed service code (AF10001 .. AF50000), not
    an HTTP status: AF20022 "No subscription found for the specified
    content type", AF20050 "The specified content does not exist",
    AF429 throttling, ...

    Provenance: docs-derived (reference page, "Errors" table), live-capture
    pending.
    """

    code: str
    message: str


class ManagementActivityAPIError(_WireModel):
    """The error body the activity feed returns on a failed call.

    Provenance: docs-derived (reference page, "Errors"), live-capture
    pending.
    """

    error: ActivityAPIErrorBody


#: Exact page model per content type -- what a capture/driver should use
#: when it knows which blob a record array came from.
CONTENT_PAGE_MODELS: dict[str, Any] = {
    ENTRA_CONTENT_TYPE: EntraAuditRecordPage,
    GENERAL_CONTENT_TYPE: GeneralAuditRecordPage,
}

#: Op -> model registry (same key shape as the connector typed modules:
#: the activity feed's REST operations). ``stop_subscription`` answers an
#: empty 200 and has no model.
OPERATION_MODELS: dict[str, Any] = {
    "list_subscriptions": SubscriptionsPage,
    "start_subscription": SubscriptionListItem,
    "list_content": ContentPage,
    "get_content": AuditRecordPage,
}

RecordPage: TypeAlias = EntraAuditRecordPage | GeneralAuditRecordPage
"""Either per-content-type page model (use via ``TypeAdapter``)."""

__all__ = [
    "PROVENANCE",
    "CONNECTOR",
    "MANAGE_API_ROOT",
    "MANAGEMENT_SCOPE",
    "ENTRA_CONTENT_TYPE",
    "GENERAL_CONTENT_TYPE",
    "CONTENT_TYPES",
    "ManagementActivityWebhook",
    "SubscriptionListItem",
    "SubscriptionsPage",
    "ContentListItem",
    "ContentPage",
    "UserTypeValue",
    "AuditLogScopeValue",
    "AppAccessContext",
    "NameValuePair",
    "ModifiedProperty",
    "IdentityTypeValuePair",
    "CommonAuditRecord",
    "EntraAuditRecord",
    "GeneralAuditRecord",
    "EntraAuditRecordPage",
    "GeneralAuditRecordPage",
    "AuditRecordElement",
    "AuditRecordPage",
    "ActivityAPIErrorBody",
    "ManagementActivityAPIError",
    "CONTENT_PAGE_MODELS",
    "OPERATION_MODELS",
    "RecordPage",
]
