"""Typed outputs for the ``microsoft-purview-ediscovery`` connector.

Source: the ``microsoft-purview-ediscovery`` connector repo (private)
(info.json version 1.0.0, label "Microsoft Purview eDiscovery"). The
connector talks to the Microsoft Graph **v1.0 security namespace**
(``/v1.0/security/cases/ediscoveryCases``), NOT the beta
``/compliance/ediscovery`` surface, with application-only client
credentials through MSAL.

One output model per operation the sample playbook uses, plus the v1.0
resource shapes those outputs carry (ediscoveryCase, ediscoveryCustodian,
userSource, ediscoverySearch, the caseOperation family and
exportFileMetadata). The models exist so playbook tooling (compiler,
linter, agent) knows what ``vars.steps.<step>.<field>`` can hold after one
of these ops runs -- connector outputs land under ``data`` in production
and directly on the step under ``--mock`` (see the linter's mock-envelope
rule).

Wire quirks the models normalize (all source-derived from the connector's
operations.py v1.0.0 and the v1.0 resource docs, none live-verified yet):

- collection ops return the connector's own page envelope
  ``{items, count, pages, next_link}`` -- NOT the raw Graph ``value`` page;
  ``next_link`` is present only when a ``limit`` stopped the merge early.
- long-running actions (purge, export, estimate, add-to-review-set) answer
  ``202`` and the connector follows the ``Location`` header to the created
  operation resource; an action answered without a Location collapses to
  ``{status_code, status}`` (``status`` ``success`` for 204, ``accepted``
  otherwise).
- ``wait_for_search_statistics`` kicks ``estimateStatistics`` itself when
  the search has no recent estimate; its ``lastEstimateStatistics`` is the
  six-field statistics block of the terminal estimate operation.
- ``create_custodians`` never raises on a bad address: its ``results`` row
  carries ``status`` ``created`` | ``exists`` | ``failed`` and, on failure,
  ``error`` (plus ``custodian_id: null``); ``custodian_ids`` is the CSV of
  every resolved id.

Provenance for every model here, until live captures land:
``Provenance: source-derived (operations.py v1.0.0, info.json output_schema),
live-capture pending.``
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

#: Exact provenance string for this connector's models (info.json version
#: 1.0.0).
PROVENANCE = ("Provenance: source-derived (operations.py v1.0.0, info.json "
              "output_schema), live-capture pending.")


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---------------------------------------------------------------------------
# Case operations (the 202/Location family; the search section expands one)
# ---------------------------------------------------------------------------

OperationStatus = Literal["pending", "running", "succeeded", "failed",
                          "partiallySucceeded"]


class ExportFileMetadata(_WireModel):
    """One file of a finished export.

    ``downloadUrl`` is a pre-authenticated URL Graph hands out once the
    export completes; ``size`` is in bytes.

    Provenance: source-derived (operations.py v1.0.0 export_result, info.json
    output_schema), live-capture pending.
    """

    downloadUrl: str | None = None
    fileName: str | None = None
    size: int | None = None


class CaseOperation(_WireModel):
    """The caseOperation family: estimate, purge, export, addToReviewSet.

    ``statisticsOptions`` belongs to the estimate flavor, the export body
    fields plus ``exportFileMetadata`` to the export flavor. ``search`` is
    present when the caller expanded it (list_case_operations always does).

    Provenance: source-derived (operations.py v1.0.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    action: Literal["estimateStatistics", "purgeData", "exportResult",
                    "addToReviewSet", "holdReminder", "applyHold",
                    "removeHold", "unknownFutureValue"] | None = None
    status: OperationStatus | None = None
    percentProgress: int | None = None
    createdDateTime: str | None = None
    completedDateTime: str | None = None
    statisticsOptions: str | None = None
    indexedItemCount: int | None = None
    indexedItemsSize: int | None = None
    unindexedItemCount: int | None = None
    unindexedItemsSize: int | None = None
    mailboxCount: int | None = None
    siteCount: int | None = None
    displayName: str | None = None
    description: str | None = None
    exportFormat: Literal["pst", "msg"] | None = None
    exportLocation: Literal["responsiveLocations",
                            "nonresponsiveLocations"] | None = None
    cloudAttachmentVersion: Literal["latest", "recent10", "recent100",
                                    "all"] | None = None
    documentVersion: Literal["latest", "recent10", "recent100",
                             "all"] | None = None
    exportFileMetadata: list[ExportFileMetadata] | None = None
    search: dict[str, Any] | None = None


class EstimateOperation(CaseOperation):
    """``lastEstimateStatisticsOperation`` of a search: the estimate flavor
    of the caseOperation family, carrying the statistics fields once it
    succeeded."""


class PurgeResult(CaseOperation):
    """``purge_data`` output: the created purgeData operation (the connector
    followed the 202 Location)."""


class ExportResultOperation(CaseOperation):
    """``export_result`` output: the created exportResult operation."""


class OperationsPage(_WireModel):
    """``list_case_operations`` output (the connector's page envelope; the
    ops carry ``search`` because the op always expands it)."""

    items: list[CaseOperation]
    count: int
    pages: int
    next_link: str | None = None


class WaitForOperationResult(_WireModel):
    """``wait_for_operation`` output."""

    case_id: str
    operation_id: str
    elapsed_seconds: float
    polls: int
    operation: CaseOperation


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------

CaseStatus = Literal["active", "pendingDelete", "closing", "closed"]


class EdiscoveryCase(_WireModel):
    """A ``microsoft.graph.security.ediscoveryCase``.

    ``closedDateTime`` appears only on closed cases; ``externalId`` only
    when the case was created with one.

    Provenance: source-derived (operations.py v1.0.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    displayName: str
    description: str | None = None
    status: CaseStatus | None = None
    externalId: str | None = None
    createdDateTime: str | None = None
    lastModifiedDateTime: str | None = None
    closedDateTime: str | None = None


class CasesPage(_WireModel):
    """``list_cases`` output: the connector's own page envelope, not the
    raw Graph ``value`` page (EdiscoveryClient.list_all)."""

    items: list[EdiscoveryCase]
    count: int
    pages: int
    next_link: str | None = None


class CreatedCase(_WireModel):
    """``create_case`` output: the created case body (Graph answers a POST
    with the full resource)."""

    id: str
    displayName: str
    description: str | None = None
    status: CaseStatus | None = None
    createdDateTime: str | None = None
    lastModifiedDateTime: str | None = None


# ---------------------------------------------------------------------------
# Custodians
# ---------------------------------------------------------------------------

CustodianStatus = Literal["active", "released"]
HoldStatus = Literal["applied", "applying", "removing", "notApplied",
                     "unknownFutureValue"]


class EdiscoveryCustodian(_WireModel):
    """A ``microsoft.graph.security.ediscoveryCustodian``.

    Provenance: source-derived (operations.py v1.0.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    email: str
    displayName: str | None = None
    status: CustodianStatus | None = None
    holdStatus: HoldStatus | None = None
    createdDateTime: str | None = None
    lastModifiedDateTime: str | None = None
    releasedDateTime: str | None = None


class CustodiansPage(_WireModel):
    """``list_custodians`` output (the connector's page envelope)."""

    items: list[EdiscoveryCustodian]
    count: int
    pages: int
    next_link: str | None = None


class CustodianCreateResult(_WireModel):
    """``create_custodian`` output: the created custodian plus whether the
    connector managed to start the hold on its sources."""

    custodian: EdiscoveryCustodian
    hold_applied: bool


class CustodianRow(_WireModel):
    """One per-email row of ``create_custodians.results``.

    ``custodian_id`` is null exactly when ``status`` is ``failed``; the
    ``error`` text is present only on failed rows and ``warning`` only when
    the custodian was created but its applyHold call did not.

    Provenance: source-derived (operations.py v1.0.0 create_custodians),
    live-capture pending.
    """

    email: str
    custodian_id: str | None = None
    status: Literal["created", "exists", "failed"]
    error: str | None = None
    warning: str | None = None


class CustodiansBulkResult(_WireModel):
    """``create_custodians`` output."""

    case_id: str
    requested: int
    created_count: int
    exists_count: int
    failed_count: int
    results: list[CustodianRow]
    custodian_ids: str


class UserSource(_WireModel):
    """A ``microsoft.graph.security.userSource`` (a custodian's mailbox and
    OneDrive).

    Provenance: source-derived (operations.py v1.0.0, info.json
    output_schema), live-capture pending.
    """

    id: str
    email: str | None = None
    displayName: str | None = None
    holdStatus: HoldStatus | None = None
    includedSources: str | None = None
    siteWebUrl: str | None = None
    createdDateTime: str | None = None


class SiteSource(_WireModel):
    """A ``microsoft.graph.security.siteSource`` (a SharePoint site)."""

    id: str
    displayName: str | None = None
    holdStatus: HoldStatus | None = None
    site: dict[str, Any] | None = None
    createdDateTime: str | None = None


# ---------------------------------------------------------------------------
# Searches
# ---------------------------------------------------------------------------

DataSourceScope = Literal[
    "none", "allTenantMailboxes", "allTenantSites", "allCaseCustodians",
    "allCaseNoncustodialDataSources",
]


class EdiscoverySearch(_WireModel):
    """A ``microsoft.graph.security.ediscoverySearch``.

    ``lastEstimateStatisticsOperation`` is present only when the caller
    expanded it and the search has been estimated at least once.

    Provenance: source-derived (operations.py v1.0.0 get_search, info.json
    output_schema), live-capture pending.
    """

    id: str
    displayName: str
    description: str | None = None
    contentQuery: str | None = None
    dataSourceScopes: DataSourceScope | None = None
    lastEstimateStatisticsOperation: EstimateOperation | None = None
    createdDateTime: str | None = None
    lastModifiedDateTime: str | None = None


class SearchesPage(_WireModel):
    """``list_searches`` output (the connector's page envelope)."""

    items: list[EdiscoverySearch]
    count: int
    pages: int
    next_link: str | None = None


class SearchCreateResult(_WireModel):
    """``create_search`` output: the created search plus every
    additionalSource the connector attached after creation."""

    search: EdiscoverySearch
    additional_sources: list[dict[str, Any]]


class DeletedSearchResult(_WireModel):
    """``delete_search`` output: the connector's no-body envelope (a 204
    DELETE answers no body, so the op collapses to the status pair)."""

    status_code: int
    status: Literal["success"]


class SearchStatisticsResult(_WireModel):
    """``get_search_statistics`` output.

    ``operation`` is the last estimate operation and is null when the search
    has never been estimated; ``lastEstimateStatistics`` then is null too.

    Provenance: source-derived (operations.py v1.0.0), live-capture pending.
    """

    case_id: str
    search_id: str
    estimated: bool
    operation: CaseOperation | None = None
    lastEstimateStatistics: dict[str, Any] | None = None


class WaitSearchStatisticsResult(_WireModel):
    """``wait_for_search_statistics`` output.

    ``kicked`` is True when the op had to start the estimateStatistics
    action itself; ``lastEstimateStatistics`` carries the six statistics
    fields of the terminal estimate operation.

    Provenance: source-derived (operations.py v1.0.0), live-capture pending.
    """

    case_id: str
    search_id: str
    estimated: bool
    kicked: bool
    elapsed_seconds: float
    operation: CaseOperation
    lastEstimateStatistics: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Op -> model registry (consumed by tests and the mock loader)
# ---------------------------------------------------------------------------

OPERATION_MODELS: dict[str, Any] = {
    "list_cases": CasesPage,
    "create_case": CreatedCase,
    "get_case": EdiscoveryCase,
    "create_custodian": CustodianCreateResult,
    "create_custodians": CustodiansBulkResult,
    "list_custodians": CustodiansPage,
    "create_custodian_user_source": UserSource,
    "create_custodian_site_source": SiteSource,
    "create_search": SearchCreateResult,
    "list_searches": SearchesPage,
    "get_search": EdiscoverySearch,
    "delete_search": DeletedSearchResult,
    "run_estimate_statistics": EstimateOperation,
    "get_search_statistics": SearchStatisticsResult,
    "wait_for_search_statistics": WaitSearchStatisticsResult,
    "wait_for_operation": WaitForOperationResult,
    "list_case_operations": OperationsPage,
    "export_result": ExportResultOperation,
    "purge_data": PurgeResult,
}

__all__ = [
    "PROVENANCE",
    "EdiscoveryCase", "CasesPage", "CreatedCase",
    "EdiscoveryCustodian", "CustodiansPage", "CustodianCreateResult",
    "CustodianRow", "CustodiansBulkResult",
    "UserSource", "SiteSource",
    "EdiscoverySearch", "SearchesPage", "SearchCreateResult",
    "DeletedSearchResult",
    "ExportFileMetadata", "CaseOperation", "EstimateOperation",
    "OperationsPage", "PurgeResult", "ExportResultOperation",
    "WaitForOperationResult", "WaitSearchStatisticsResult",
    "SearchStatisticsResult",
    "OPERATION_MODELS",
]
