"""Offline typing gate for the Office 365 Management Activity API models.

Pins the typed models in
``fsr_playbooks/connectors/typed/microsoft_management_activity.py`` against
the docs-derived fixtures in ``fixtures/management_activity/``:

* every fixture validates through its model AND round-trips exactly
  (``model_dump(by_alias=True, exclude_unset=True) == fixture`` -- the same
  contract the graph-security and defender suites pin);
* the docs' own contradictions behave as documented (a sample subscription
  item without ``status``, an ``Add User.`` record without ``ClientIP``,
  both ``IntraSystemsId`` spellings, the undocumented ``isFulfilled``);
* the Common schema's mandatory fields are actually required.

Provenance: docs-derived (Microsoft Learn, Office 365 Management Activity
API reference + schema), live-capture pending -- the shapes pinned here
come from the two Learn pages, never from a live wire. The ``live``-marked
suite in ``tooling/tests/test_management_activity_live.py`` re-validates
the same models against the real tenant when M365 creds are available.

No network, no reference DB: green on a bare checkout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from fsr_playbooks.connectors.typed import microsoft_management_activity as m

_FIXTURES = Path(m.__file__).resolve().parents[3] / (
    "fsr_playbooks/tests/fixtures/management_activity"
)


def _load(name: str) -> Any:
    return json.loads((_FIXTURES / name).read_text())


# --- registry completeness ----------------------------------------------------


def test_operation_models_cover_the_read_surface() -> None:
    assert set(m.OPERATION_MODELS) == {
        "list_subscriptions",
        "start_subscription",
        "list_content",
        "get_content",
    }


def test_content_page_models_cover_both_enabled_content_types() -> None:
    assert set(m.CONTENT_PAGE_MODELS) == {
        "Audit.AzureActiveDirectory",
        "Audit.General",
    }
    assert m.CONTENT_TYPES == ("Audit.AzureActiveDirectory", "Audit.General")


def test_the_api_surface_constants_match_the_docs() -> None:
    assert m.MANAGE_API_ROOT == "https://manage.office.com/api/v1.0"
    assert m.MANAGEMENT_SCOPE == "https://manage.office.com/.default"


# --- every fixture validates through its model -------------------------------


def test_subscriptions_list_fixture_validates_and_binds() -> None:
    parsed = m.SubscriptionsPage.model_validate(_load("subscriptions_list.json"))
    first, second = parsed.root
    assert first.contentType == "Audit.SharePoint"
    assert first.status == "enabled"
    assert first.webhook is not None
    assert first.webhook.address == "https://webhook.myapp.com/o365/"
    # the doc sample's last item: no status key, webhook explicitly null
    assert second.contentType == "Audit.Exchange"
    assert second.status is None
    assert second.webhook is None


def test_start_subscription_fixture_validates() -> None:
    parsed = m.SubscriptionListItem.model_validate(_load("start_subscription.json"))
    assert parsed.contentType == "Audit.SharePoint"
    assert parsed.status == "enabled"
    assert parsed.webhook is not None
    assert parsed.webhook.expiration is None


def test_content_list_fixture_validates() -> None:
    parsed = m.ContentPage.model_validate(_load("content_list.json"))
    (item,) = parsed.root
    assert item.contentType == "Audit.SharePoint"
    assert item.contentId.endswith("$04")
    assert item.contentUri.startswith("https://manage.office.com/api/v1.0/")
    assert item.contentCreated == "2015-05-23T17:35:00.000Z"
    assert item.contentExpiration == "2015-05-30T17:35:00.000Z"
    assert item.isFulfilled is None


def test_content_list_with_is_fulfilled_validates() -> None:
    parsed = m.ContentPage.model_validate(_load("content_list.is_fulfilled.json"))
    assert parsed.root[0].isFulfilled is True


def test_aad_records_validate_through_both_page_models() -> None:
    body = _load("content_records_aad.json")
    exact = m.EntraAuditRecordPage.model_validate(body)
    union = m.AuditRecordPage.model_validate(body)
    assert exact.model_dump() == union.model_dump()
    logon_failed, logon_ok, admin = exact.root
    assert logon_failed.LoginStatus == -2147217390
    assert logon_failed.UserDomain == "contoso.onmicrosoft.com"
    assert logon_ok.LoginStatus == 0
    # the admin record: no ClientIP key, no LoginStatus/UserDomain, and the
    # sample's IntraSystemId spelling (the schema table says IntraSystemsId)
    assert admin.RecordType == 8
    assert admin.ClientIP is None
    assert admin.LoginStatus is None
    assert admin.IntraSystemId == "d1497f7e-15b4-49aa-83ad-11a17ca4a2f4"
    assert admin.IntraSystemsId is None
    assert admin.Actor is not None and admin.Target is not None
    assert admin.Actor[0].ID == "1cef1fdb-ff52-48c4-8e4e-dfb5ea83d357"


def test_general_records_validate_through_both_page_models() -> None:
    body = _load("content_records_general.json")
    exact = m.GeneralAuditRecordPage.model_validate(body)
    union = m.AuditRecordPage.model_validate(body)
    assert exact.model_dump() == union.model_dump()
    exchange, sharepoint, teams, dlp = exact.root
    assert exchange.RecordType == 1
    assert exchange.ResultStatus == "True"  # the documented Exchange spelling
    assert exchange.ModifiedObjectResolvedName == "auditor@contoso.example"
    assert exchange.Parameters is not None
    assert exchange.Parameters[0].Name == "Identity"
    assert sharepoint.RecordType == 6
    assert sharepoint.SourceFileName == "report.docx"
    assert sharepoint.SiteUrl.startswith("https://contoso.example-my.sharepoint.com/")
    assert teams.TeamName == "Audit Ops"
    assert teams.ChannelType == "Standard"
    assert teams.ExtraProperties is not None
    assert dlp.RecordType == 11
    assert dlp.UserKey == "DlpAgent"  # the documented DLP marker
    assert dlp.PolicyDetails is not None
    assert dlp.PolicyDetails[0]["PolicyName"] == "EU Financial Data"
    assert dlp.SensitiveInfoDetectionIsIncluded is False


def test_error_fixture_validates_through_the_api_error_model() -> None:
    parsed = m.ManagementActivityAPIError.model_validate(_load("error_af20022.json"))
    assert parsed.error.code == "AF20022"
    assert "No subscription found" in parsed.error.message


# --- round-trip contract ------------------------------------------------------

_EXACT_FIXTURES = [
    ("subscriptions_list.json", m.SubscriptionsPage),
    ("start_subscription.json", m.SubscriptionListItem),
    ("content_list.json", m.ContentPage),
    ("content_list.is_fulfilled.json", m.ContentPage),
    ("content_records_aad.json", m.AuditRecordPage),
    ("content_records_general.json", m.AuditRecordPage),
    ("error_af20022.json", m.ManagementActivityAPIError),
]


@pytest.mark.parametrize("name,model", _EXACT_FIXTURES)
def test_every_fixture_round_trips_exactly(name: str, model: Any) -> None:
    """``model_dump(by_alias=True, exclude_unset=True)`` must reproduce the
    fixture as a dict/list -- the typed layer adds and drops nothing."""
    body = _load(name)
    parsed = model.model_validate(body)
    assert parsed.model_dump(by_alias=True, exclude_unset=True) == body


def test_unknown_record_fields_ride_through_the_round_trip() -> None:
    """extra="allow" preserves keys the docs do not list (workloads add
    fields constantly; a playbook must keep reading them)."""
    body = _load("content_records_aad.json")
    body[0]["SomeFutureField"] = {"nested": [1, 2]}
    parsed = m.AuditRecordPage.model_validate(body)
    assert parsed.model_dump(by_alias=True, exclude_unset=True) == body


# --- Common schema strictness -------------------------------------------------

_MANDATORY = ("Id", "RecordType", "CreationTime", "Operation", "OrganizationId",
              "UserType", "UserKey", "Workload", "UserId")


@pytest.mark.parametrize("field", _MANDATORY)
def test_dropping_a_mandatory_common_field_fails(field: str) -> None:
    record = _load("content_records_aad.json")[0]
    del record[field]
    with pytest.raises(ValidationError):
        m.CommonAuditRecord.model_validate(record)


def test_client_ip_is_optional_despite_the_mandatory_mark() -> None:
    """The schema table marks ClientIP Mandatory, but the reference page's
    own Add User. sample omits the key and Entra events log null."""
    record = _load("content_records_aad.json")[2]
    assert "ClientIP" not in record
    assert m.CommonAuditRecord.model_validate(record).ClientIP is None
    assert m.CommonAuditRecord.model_validate({**record, "ClientIP": None})


def test_user_type_is_the_documented_enumeration() -> None:
    record = _load("content_records_aad.json")[0]
    for value in range(11):
        assert m.CommonAuditRecord.model_validate({**record, "UserType": value})
    with pytest.raises(ValidationError):
        m.CommonAuditRecord.model_validate({**record, "UserType": 11})


def test_result_status_null_and_object_id_null_are_accepted() -> None:
    record = _load("content_records_aad.json")[0]
    parsed = m.CommonAuditRecord.model_validate(
        {**record, "ResultStatus": None, "ObjectId": None}
    )
    assert parsed.ResultStatus is None and parsed.ObjectId is None


def test_webhook_key_is_required_but_nullable() -> None:
    item = _load("subscriptions_list.json")[1]
    assert m.SubscriptionListItem.model_validate(item).webhook is None
    without = {k: v for k, v in item.items() if k != "webhook"}
    with pytest.raises(ValidationError):
        m.SubscriptionListItem.model_validate(without)


# --- content list items -------------------------------------------------------


def test_is_fulfilled_is_optional_and_tolerates_the_absent_key() -> None:
    item = _load("content_list.json")[0]
    assert m.ContentListItem.model_validate(item).isFulfilled is None
    assert m.ContentListItem.model_validate({**item, "isFulfilled": False})
    with pytest.raises(ValidationError):
        m.ContentListItem.model_validate({**item, "isFulfilled": "maybe"})


def test_dropping_a_content_list_item_field_fails() -> None:
    item = _load("content_list.json")[0]
    del item["contentUri"]
    with pytest.raises(ValidationError):
        m.ContentListItem.model_validate(item)


# --- page model selection -----------------------------------------------------


def test_the_union_page_binds_each_record_by_its_schema() -> None:
    aad = m.AuditRecordPage.model_validate(_load("content_records_aad.json"))
    general = m.AuditRecordPage.model_validate(_load("content_records_general.json"))
    assert all(isinstance(r, m.EntraAuditRecord) for r in aad.root)
    assert all(isinstance(r, m.GeneralAuditRecord) for r in general.root)


def test_content_page_models_route_by_content_type() -> None:
    aad_body = _load("content_records_aad.json")
    general_body = _load("content_records_general.json")
    aad = TypeAdapter(m.CONTENT_PAGE_MODELS["Audit.AzureActiveDirectory"])
    general = TypeAdapter(m.CONTENT_PAGE_MODELS["Audit.General"])
    assert len(aad.validate_python(aad_body).root) == 3
    assert len(general.validate_python(general_body).root) == 4
    # a General record must NOT bind to the Entra page: the Base schema's
    # mandatory AzureActiveDirectoryEventType is missing there
    with pytest.raises(ValidationError):
        TypeAdapter(m.EntraAuditRecordPage).validate_python(general_body)


def test_provenance_says_docs_derived_and_pending() -> None:
    assert "docs-derived" in m.PROVENANCE
    assert "live-capture pending" in m.PROVENANCE


# --- capture-driver helpers (offline; no network) -----------------------------


def _driver() -> Any:
    from fsr_playbooks.connectors.typed import capture_management_activity as cap

    return cap


def test_driver_load_env_file_sets_missing_keys_only(tmp_path: Path) -> None:
    cap = _driver()
    env_file = tmp_path / "env"
    env_file.write_text(
        "# comment line\n"
        "M365_TENANT_ID=tenant-from-file\n"
        "M365_CLIENT_ID=client-from-file\n"
        'M365_CLIENT_SECRET="quoted-secret"\n'
        "BROKEN LINE WITHOUT EQUALS\n"
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("M365_TENANT_ID", raising=False)
        mp.delenv("M365_CLIENT_ID", raising=False)
        mp.delenv("M365_CLIENT_SECRET", raising=False)
        assert cap.load_env_file(env_file) is True
        assert os.environ["M365_TENANT_ID"] == "tenant-from-file"
        assert os.environ["M365_CLIENT_SECRET"] == "quoted-secret"


def test_driver_load_env_file_never_overrides_the_environment(
    tmp_path: Path,
) -> None:
    cap = _driver()
    env_file = tmp_path / "env"
    env_file.write_text("M365_TENANT_ID=from-file\n")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("M365_TENANT_ID", "from-env")
        assert cap.load_env_file(env_file) is True
        assert os.environ["M365_TENANT_ID"] == "from-env"


def test_driver_resolve_creds_from_env_file(tmp_path: Path) -> None:
    cap = _driver()
    env_file = tmp_path / "env"
    env_file.write_text(
        "M365_TENANT_ID=t\nM365_CLIENT_ID=c\nM365_CLIENT_SECRET=s\n"
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("M365_TENANT_ID", raising=False)
        mp.delenv("M365_CLIENT_ID", raising=False)
        mp.delenv("M365_CLIENT_SECRET", raising=False)
        assert cap.resolve_creds(env_file) == ("t", "c", "s")


def test_driver_resolve_creds_prefers_the_environment(tmp_path: Path) -> None:
    cap = _driver()
    env_file = tmp_path / "env"
    env_file.write_text(
        "M365_TENANT_ID=from-file\nM365_CLIENT_ID=c\nM365_CLIENT_SECRET=s\n"
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("M365_TENANT_ID", "from-env")
        mp.delenv("M365_CLIENT_ID", raising=False)
        mp.delenv("M365_CLIENT_SECRET", raising=False)
        assert cap.resolve_creds(env_file)[0] == "from-env"


def test_driver_resolve_creds_missing_file_still_reads_env(tmp_path: Path) -> None:
    cap = _driver()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("M365_TENANT_ID", "t")
        mp.setenv("M365_CLIENT_ID", "c")
        mp.setenv("M365_CLIENT_SECRET", "s")
        assert cap.resolve_creds(tmp_path / "nope.env") == ("t", "c", "s")


def test_driver_default_window_respects_the_documented_rules() -> None:
    cap = _driver()
    start, end = cap.default_window(24)
    assert end > start
    # the docs' datetime forms: YYYY-MM-DDTHH:MM:SS
    assert len(start) == 19 and len(end) == 19
    from datetime import datetime as _dt

    parsed_start = _dt.strptime(start, "%Y-%m-%dT%H:%M:%S")
    parsed_end = _dt.strptime(end, "%Y-%m-%dT%H:%M:%S")
    assert (parsed_end - parsed_start).total_seconds() <= 24 * 3600


def test_driver_slugify_content_id_is_filesystem_safe() -> None:
    cap = _driver()
    slug = cap._slugify_content_id(
        "492638008028$492638008028$f28ab78ad40140608012736e373933ebspo"
        "2015043022$4a81a7c326fc4aed89c62e6039ab833b$04"
    )
    assert "$" not in slug and " " not in slug
    assert len(slug) <= 80 and slug == slug.strip("-")
    assert cap._slugify_content_id("$$$") == "blob"


def test_driver_workload_counts_tally_and_mark_missing() -> None:
    cap = _driver()
    counts = cap._workload_counts(
        [
            {"Workload": "AzureActiveDirectory"},
            {"Workload": "AzureActiveDirectory"},
            {"Workload": "Exchange"},
            {},
        ]
    )
    assert counts == {
        "AzureActiveDirectory": 2,
        "Exchange": 1,
        "<missing>": 1,
    }


def test_driver_validate_records_reports_failures_verbatim() -> None:
    cap = _driver()
    good = _load("content_records_aad.json")
    assert cap._validate_records("Audit.AzureActiveDirectory", good) == []
    bad = [dict(good[0])]
    del bad[0]["Workload"]
    failures = cap._validate_records("Audit.AzureActiveDirectory", bad)
    assert len(failures) == 1
    assert failures[0].startswith("record[0]:")
    assert "Workload" in failures[0]  # the verbatim pydantic error text


def test_driver_module_exports_the_readonly_surface() -> None:
    cap = _driver()
    assert cap.MAX_PAGES >= 1
    assert set(cap._CONTENT_SLUG) == {"Audit.AzureActiveDirectory", "Audit.General"}
    assert cap._CAPTURE_DIR_NAME == "microsoft-management-activity"
