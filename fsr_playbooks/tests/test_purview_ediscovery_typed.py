"""Offline tests for the typed models of the ``microsoft-purview-ediscovery``
connector (m365-trial plan doctrine: one output model per operation the
sample playbook uses).

The contract under test:

- ``OPERATION_MODELS`` covers every operation the sample playbook references,
  and every registered model is a pydantic model;
- every model validates a representative output payload (the same shapes the
  playbook's ``mock_result`` blocks carry) and round-trips it exactly;
- the models stay source-derived: the provenance line says the payloads come
  from the connector's own operations.py and info.json output schemas, and no
  model docstring claims live verification before a capture has landed;
- the behavioral quirks the playbook leans on are pinned: the
  ``create_custodians`` per-row status contract (``custodian_id`` null exactly
  on failed rows), the connector's page envelope, and the wait-op envelopes
  (``kicked`` / ``elapsed_seconds`` / ``polls`` / terminal ``operation``).

No network, no reference DB: this suite must stay green on a checkout with no
``data/fsr_reference.db`` and no tenant.
"""
from __future__ import annotations

import inspect

from pydantic import BaseModel, TypeAdapter

from fsr_playbooks.connectors.typed.microsoft_purview_ediscovery import (
    OPERATION_MODELS,
    PROVENANCE,
    CaseOperation,
    CasesPage,
    CustodiansBulkResult,
    DeletedSearchResult,
    EdiscoverySearch,
    ExportResultOperation,
    PurgeResult,
    SearchStatisticsResult,
    WaitForOperationResult,
    WaitSearchStatisticsResult,
)

#: Every operation the sample playbook (scenarios/microsoft-purview-ediscovery)
#: runs through this connector, in playbook order.
PLAYBOOK_OPS = [
    "list_cases",
    "create_case",
    "create_custodians",
    "create_custodian_user_source",
    "list_searches",
    "create_search",
    "wait_for_search_statistics",
    "delete_search",
    "purge_data",
    "wait_for_operation",
    "export_result",
]


def test_provenance_is_source_derived() -> None:
    """The models are honest about not being live-captured yet."""
    assert "source-derived" in PROVENANCE
    assert "live-capture pending" in PROVENANCE
    assert "live-verified" not in PROVENANCE


def test_no_model_docstring_claims_live_verification() -> None:
    """No model may claim live verification before a capture has landed."""
    for name, model in OPERATION_MODELS.items():
        for klass in (model, *model.__mro__):
            doc = (klass.__doc__ or "").lower()
            assert "live-verified" not in doc, (
                f"{name}: {klass.__name__} claims live verification"
            )


def test_registry_covers_the_playbook_ops() -> None:
    """Every op the playbook references has a model, and models are models."""
    missing = [op for op in PLAYBOOK_OPS if op not in OPERATION_MODELS]
    assert not missing, f"no typed model for {missing}"
    for name, model in OPERATION_MODELS.items():
        assert inspect.isclass(model) and issubclass(model, BaseModel), (
            f"{name}: registry entry is not a pydantic model"
        )


# ---- representative payloads (the shapes the playbook mocks carry) --------


def test_cases_page_round_trip() -> None:
    """``list_cases``: the connector's own page envelope, not Graph's."""
    payload = {
        "items": [
            {
                "@odata.type": "microsoft.graph.security.ediscoveryCase",
                "id": "00000000-0000-0000-0000-00000000c002",
                "displayName": "Quarterly audit hold",
                "description": "Standing legal hold for the quarterly audit.",
                "status": "active",
                "createdDateTime": "2026-11-03T08:00:00.0000000Z",
                "lastModifiedDateTime": "2026-11-20T14:12:00.0000000Z",
            },
        ],
        "count": 1,
        "pages": 1,
    }
    page = TypeAdapter(CasesPage).validate_python(payload)
    assert page.items[0].id == "00000000-0000-0000-0000-00000000c002"
    assert page.next_link is None
    # Round-trip over the declared fields; the Graph @odata.type rides in the
    # model's extra bag (extra="allow") rather than a declared field.
    dumped = page.model_dump(exclude_unset=True)
    assert dumped["items"][0]["displayName"] == "Quarterly audit hold"
    assert dumped["count"] == 1 and dumped["pages"] == 1
    assert page.items[0].model_extra == {
        "@odata.type": "microsoft.graph.security.ediscoveryCase",
    }


def test_ediscovery_search_defaults() -> None:
    """A search without an estimate has no lastEstimateStatisticsOperation."""
    search = TypeAdapter(EdiscoverySearch).validate_python({
        "id": "00000000-0000-0000-0000-00000000f103",
        "displayName": "Phishing incident response - search",
        "contentQuery": 'subject:"payroll update"',
        "dataSourceScopes": "none",
    })
    assert search.lastEstimateStatisticsOperation is None
    assert search.dataSourceScopes == "none"


def test_create_custodians_row_contract() -> None:
    """``create_custodians`` never aborts the batch: one row per address.

    ``custodian_id`` is null exactly on failed rows, and failed rows carry
    the error; created rows may carry a warning when the hold could not be
    started. The CSV of resolved ids is what the search binds.
    """
    payload = {
        "case_id": "00000000-0000-0000-0000-00000000c009",
        "requested": 3,
        "created_count": 1,
        "exists_count": 1,
        "failed_count": 1,
        "results": [
            {"email": "alice@contoso.example", "status": "created",
             "custodian_id": "00000000-0000-0000-0000-00000000d001"},
            {"email": "bob@contoso.example", "status": "exists",
             "custodian_id": "00000000-0000-0000-0000-00000000d002"},
            {"email": "not-an-address", "status": "failed",
             "custodian_id": None,
             "error": "Email must be the custodian's SMTP address"},
            {"email": "erin@contoso.example", "status": "created",
             "custodian_id": "00000000-0000-0000-0000-00000000d003",
             "warning": "custodian created but applyHold failed: 409"},
        ],
        "custodian_ids": "00000000-0000-0000-0000-00000000d001,"
                         "00000000-0000-0000-0000-00000000d002,"
                         "00000000-0000-0000-0000-00000000d003",
    }
    result = TypeAdapter(CustodiansBulkResult).validate_python(payload)
    assert [row.status for row in result.results] == [
        "created", "exists", "failed", "created"]
    failed = result.results[2]
    assert failed.custodian_id is None and failed.error is not None
    warned = result.results[3]
    assert warned.warning is not None and warned.status == "created"
    assert result.custodian_ids.count(",") == 2


def test_wait_for_operation_envelope() -> None:
    """``wait_for_operation``: elapsed + polls + the terminal operation."""
    payload = {
        "case_id": "00000000-0000-0000-0000-00000000c009",
        "operation_id": "00000000-0000-0000-0000-00000000f202",
        "elapsed_seconds": 20.0,
        "polls": 2,
        "operation": {
            "id": "00000000-0000-0000-0000-00000000f202",
            "action": "purgeData",
            "status": "succeeded",
            "percentProgress": 100,
            "createdDateTime": "2026-11-25T09:35:00.0000000Z",
            "completedDateTime": "2026-11-25T09:35:20.0000000Z",
        },
    }
    result = TypeAdapter(WaitForOperationResult).validate_python(payload)
    assert result.polls == 2 and result.elapsed_seconds == 20.0
    assert result.operation.status == "succeeded"
    assert isinstance(result.operation, CaseOperation)


def test_wait_for_search_statistics_envelope() -> None:
    """``wait_for_search_statistics``: kicked flag + the statistics block."""
    stats = {
        "indexedItemCount": 128,
        "indexedItemsSize": 134217728,
        "unindexedItemCount": 4,
        "unindexedItemsSize": 1048576,
        "mailboxCount": 2,
        "siteCount": 0,
    }
    payload = {
        "case_id": "00000000-0000-0000-0000-00000000c009",
        "search_id": "00000000-0000-0000-0000-00000000f103",
        "estimated": True,
        "kicked": True,
        "elapsed_seconds": 20.0,
        "operation": {
            "id": "00000000-0000-0000-0000-00000000f201",
            "action": "estimateStatistics",
            "status": "succeeded",
            "percentProgress": 100,
            "statisticsOptions": "includeUnindexedStats, locationsWithoutHits",
            **stats,
        },
        "lastEstimateStatistics": stats,
    }
    result = TypeAdapter(WaitSearchStatisticsResult).validate_python(payload)
    assert result.kicked is True
    assert result.lastEstimateStatistics["indexedItemCount"] == 128
    # The annotation is the shared CaseOperation; the estimate flavor is
    # pinned by the action, not by the python class.
    assert result.operation.action == "estimateStatistics"
    assert result.operation.indexedItemCount == 128


def test_get_search_statistics_allows_a_never_estimated_search() -> None:
    """``get_search_statistics`` on a search with no estimate: both None."""
    payload = {
        "case_id": "00000000-0000-0000-0000-00000000c009",
        "search_id": "00000000-0000-0000-0000-00000000f103",
        "estimated": False,
        "operation": None,
        "lastEstimateStatistics": None,
    }
    result = TypeAdapter(SearchStatisticsResult).validate_python(payload)
    assert result.estimated is False
    assert result.operation is None and result.lastEstimateStatistics is None


def test_purge_and_export_operations() -> None:
    """Purge/export outputs are the created operations (202 Location
    followed), and a completed export carries exportFileMetadata."""
    purge = TypeAdapter(PurgeResult).validate_python({
        "id": "00000000-0000-0000-0000-00000000f202",
        "action": "purgeData",
        "status": "running",
        "percentProgress": 10,
        "createdDateTime": "2026-11-25T09:35:00.0000000Z",
        "status_code": 202,
    })
    assert purge.action == "purgeData" and purge.status_code == 202

    export = TypeAdapter(ExportResultOperation).validate_python({
        "id": "00000000-0000-0000-0000-00000000f203",
        "action": "exportResult",
        "status": "succeeded",
        "percentProgress": 100,
        "displayName": "Export of Phishing incident response",
        "exportFormat": "pst",
        "exportLocation": "responsiveLocations",
        "completedDateTime": "2026-11-25T09:36:30.0000000Z",
        "exportFileMetadata": [
            {"downloadUrl": "https://contoso.example/ediscovery-exports/export-1.zip",
             "fileName": "export-1.zip", "size": 5242880},
        ],
        "status_code": 202,
    })
    meta = export.exportFileMetadata[0]
    assert meta.fileName == "export-1.zip" and meta.size == 5242880
    assert meta.downloadUrl.startswith("https://contoso.example/")


def test_delete_search_no_body_envelope() -> None:
    """``delete_search``: a 204 DELETE answers the connector's status pair."""
    payload = {"status_code": 204, "status": "success"}
    result = TypeAdapter(DeletedSearchResult).validate_python(payload)
    assert result.status_code == 204 and result.status == "success"


def test_operation_status_is_the_v1_enumeration() -> None:
    """The status Literal carries the v1.0 caseOperation statuses."""
    for status in ("pending", "running", "succeeded", "failed",
                   "partiallySucceeded"):
        op = TypeAdapter(CaseOperation).validate_python(
            {"id": "op", "status": status})
        assert op.status == status
