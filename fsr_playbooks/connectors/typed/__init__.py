"""Typed models for connector outputs and configs.

The m365-trial plan §8.2 doctrine: one output model per operation, models
normalize REAL wire quirks (not idealized docs shapes), config models come
from the connector's own config schema, and every model cites its
provenance in its docstring. Until live captures are promoted into the
``mocks/`` fixtures, the provenance line reads "source-derived (...),
live-capture pending" and the model must be treated as unverified against
the wire.

First two connectors typed: the soarshelf Microsoft Graph security pair
(``microsoft-graph_dev`` 17 ops, ``microsoft-graph-api-security`` 5 ops).
The consumer is the playbook side: connector outputs land under
``vars.steps.<step>.data.<field>`` in production and directly on
``vars.steps.<step>.<field>`` under ``--mock`` (mock_result verbatim, no
envelope -- see the linter's mock-envelope rule).
"""
from fsr_playbooks.connectors.typed.graph_common import (
    AadstsTokenError,
    AlertComment,
    AlertUnion,
    GraphConnectorErrorText,
    GraphErrorBody,
    GraphErrorEnvelope,
    GraphInnerError,
    HostState,
    LegacySecurityAlert,
    LegacySecurityAlertsPage,
    MutationNoContentResult,
    ODataListPage,
    SecurityAlertsV2Page,
    SecurityAlertV2,
    SecurityIncident,
    SecurityIncidentsPage,
    TokenResponseErrorText,
    VendorInformation,
    extract_error_body,
    parse_graph_connector_error,
)
from fsr_playbooks.connectors.typed.microsoft_graph_api_security import (
    OPERATION_MODELS as API_SECURITY_OPERATION_MODELS,
)
from fsr_playbooks.connectors.typed.microsoft_graph_api_security import (
    AdvancedHuntingColumn,
    AdvancedHuntingResult,
    AlertResult,
    AlertsV2Page,
    MicrosoftGraphApiSecurityConfig,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
    OPERATION_MODELS as GRAPH_DEV_OPERATION_MODELS,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
    AlertCommentsPage,
    DeleteMessageResult,
    DirectoryGroup,
    DirectoryMember,
    GroupMembersPage,
    GroupsPage,
    IpRange,
    MailboxMessagePage,
    MailDeleteTarget,
    MailDeleteThreadError,
    MailEmailAddress,
    MailMessage,
    MailMessageBody,
    MailMessageFlag,
    MailRecipient,
    MailSearchThreadError,
    MessageDeleted,
    MicrosoftGraphDevConfig,
    NamedLocation,
    NamedLocationRecord,
    NamedLocationsPage,
    RevokeSessionsResult,
    RiskyUser,
    RiskyUserRecord,
    RiskyUsersPage,
    SecurityAlertResult,
    SecurityAlertsAnyVersionPage,
    ThreadedMailResult,
)
from fsr_playbooks.connectors.typed.microsoft_graph_dev import (
    IncidentsPage as GraphDevIncidentsPage,
)

__all__ = [
    "AadstsTokenError", "AlertComment", "AlertUnion",
    "GraphConnectorErrorText", "GraphErrorBody", "GraphErrorEnvelope",
    "GraphInnerError", "HostState", "LegacySecurityAlert",
    "LegacySecurityAlertsPage", "MutationNoContentResult", "ODataListPage",
    "SecurityAlertV2", "SecurityAlertsV2Page", "SecurityIncident",
    "SecurityIncidentsPage", "TokenResponseErrorText", "VendorInformation",
    "extract_error_body", "parse_graph_connector_error",
    "API_SECURITY_OPERATION_MODELS", "AdvancedHuntingColumn",
    "AdvancedHuntingResult", "AlertsV2Page", "AlertResult",
    "MicrosoftGraphApiSecurityConfig",
    "GRAPH_DEV_OPERATION_MODELS", "DeleteMessageResult", "DirectoryGroup",
    "DirectoryMember", "GroupsPage", "GroupMembersPage",
    "GraphDevIncidentsPage", "IpRange", "MailboxMessagePage",
    "MailDeleteTarget", "MailDeleteThreadError", "MailEmailAddress",
    "MailMessage", "MailMessageBody", "MailMessageFlag", "MailRecipient",
    "MailSearchThreadError", "MessageDeleted", "MicrosoftGraphDevConfig",
    "NamedLocation", "NamedLocationRecord", "NamedLocationsPage",
    "RevokeSessionsResult", "RiskyUser", "RiskyUserRecord", "RiskyUsersPage",
    "SecurityAlertResult", "SecurityAlertsAnyVersionPage",
    "AlertCommentsPage", "ThreadedMailResult",
]
