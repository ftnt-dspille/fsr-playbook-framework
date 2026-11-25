"""LIVE tests: read the real Office 365 Management Activity API (audit plane)
and assert every response validates through the typed models.

Requires M365_TENANT_ID / M365_CLIENT_ID / M365_CLIENT_SECRET (client
credentials with the ActivityFeed.Read permission). Like the sibling live
suites these run READ-ONLY: subscriptions are listed, never started or
stopped (the mutating paths live behind --start-subscriptions in
``fsr_playbooks.connectors.typed.capture_management_activity``).

Credentials are read from the environment first, then from the gitignored
lab env file ``~/PycharmProjects/Miscellaneous/fortisoar/scratch/.env.m365``
(override with M365_ENV_FILE) -- the file this suite's capture driver reads,
so a bare ``pytest tooling/tests/test_management_activity_live.py -q`` can
run live without exporting anything.

The audit plane went live recently, so "subscribed but zero blobs yet" is a
normal outcome: those tests SKIP, they do not fail. A fetched blob's records
MUST validate through the content type's page model -- a ValidationError is
a real model bug and fails loudly with the verbatim error. Fixtures land in
``scratch/captures/microsoft-management-activity/`` (gitignored).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from fsr_playbooks.connectors.typed.capture_management_activity import (
    _CAPTURE_DIR_NAME,
    ActivityFeedClient,
    ActivityFeedHTTPError,
    acquire_token,
    default_window,
    resolve_creds,
)
from fsr_playbooks.connectors.typed.microsoft_management_activity import (
    CONTENT_PAGE_MODELS,
    CONTENT_TYPES,
    MANAGEMENT_SCOPE,
    ContentPage,
    SubscriptionsPage,
)

pytestmark = pytest.mark.live

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO_ROOT / "scratch" / "captures" / _CAPTURE_DIR_NAME

_TENANT, _CLIENT_ID, _CLIENT_SECRET = resolve_creds()
if not (_TENANT and _CLIENT_ID and _CLIENT_SECRET):
    pytest.skip(
        "live Management Activity capture needs M365_TENANT_ID / "
        "M365_CLIENT_ID / M365_CLIENT_SECRET (env or the gitignored lab "
        ".env.m365 file)",
        allow_module_level=True,
    )


def _slug(content_id: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "-", content_id).strip("-") or "blob")[:80]


@pytest.fixture(scope="module")
def capture() -> dict[str, Any]:
    """Token + subscription list + content list for both content types,
    plus the FIRST fetchable blob of each type, all banked as fixtures."""
    token = acquire_token(_TENANT, _CLIENT_ID, _CLIENT_SECRET)
    assert token.startswith("eyJ")
    assert not token.startswith("Bearer ")
    client = ActivityFeedClient(_TENANT, token)

    resp = client.list_subscriptions()
    if resp.status_code != 200:
        pytest.fail(f"subscriptions/list failed: HTTP {resp.status_code}: "
                    f"{resp.text[:300]}")
    subscriptions = SubscriptionsPage.model_validate(resp.json()).root

    start, end = default_window(24)
    content: dict[str, list[dict[str, Any]]] = {}
    for content_type in CONTENT_TYPES:
        status = next(
            (item.status for item in subscriptions if item.contentType == content_type),
            None,
        )
        if status is None:
            content[content_type] = []
            continue
        try:
            items = client.list_content(content_type, start, end)
        except ActivityFeedHTTPError as exc:
            pytest.fail(f"content list failed for {content_type}: {exc}")
        ContentPage.model_validate(items)
        content[content_type] = items

    blobs: dict[str, list[dict[str, Any]]] = {}
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for content_type, items in content.items():
        blobs[content_type] = []
        for item in items:
            blob_resp = client.fetch_blob(item["contentUri"])
            if blob_resp.status_code != 200:
                continue
            records = blob_resp.json()
            if not isinstance(records, list):
                records = [records]
            name = (
                f"live.{content_type.split('.')[-1].lower()}."
                f"{_slug(item['contentId'])}.json"
            )
            (_OUT_DIR / name).write_text(json.dumps(records, indent=2) + "\n")
            blobs[content_type].append(
                {
                    "fixture": str(_OUT_DIR / name),
                    "contentId": item["contentId"],
                    "records": records,
                }
            )
            break  # the FIRST fetchable blob per content type is enough here
    return {
        "token_scope": MANAGEMENT_SCOPE,
        "subscriptions": subscriptions,
        "content": content,
        "blobs": blobs,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _slug(content_id: str) -> str:
    import re

    return (re.sub(r"[^A-Za-z0-9._-]+", "-", content_id).strip("-") or "blob")[:80]


class TestLiveManagementActivity:
    def test_subscriptions_list_validates(self, capture) -> None:
        subscriptions = capture["subscriptions"]
        assert subscriptions, "a tenant always has at least the subscription row"
        statuses = {item.contentType: item.status for item in subscriptions}
        missing = [ct for ct in CONTENT_TYPES if statuses.get(ct) is None]
        if missing:
            print(f"note: no subscription for {missing} (start it once, by hand)")
        for item in subscriptions:
            assert item.contentType
            if item.webhook is not None:
                assert item.webhook.status

    def test_content_list_validates_or_skips_when_empty(self, capture) -> None:
        total = sum(len(capture["content"][ct]) for ct in CONTENT_TYPES)
        if not total:
            pytest.skip(
                "no content blobs available yet for either content type "
                "(the audit plane went live recently; blobs appear within "
                "hours of the subscription start)"
            )
        for content_type in CONTENT_TYPES:
            items = capture["content"][content_type]
            if not items:
                print(f"note: {content_type} listed zero blobs in the window")
                continue
            assert items[0]["contentUri"].startswith("https://manage.office.com/")

    def test_first_blob_records_validate_through_the_models(self, capture) -> None:
        fetched = {
            ct: blobs for ct, blobs in capture["blobs"].items() if blobs
        }
        if not fetched:
            pytest.skip(
                "no content blob was fetchable for either content type yet "
                "(the audit plane went live recently; blobs appear within "
                "hours of the subscription start)"
            )
        failures: list[str] = []
        for content_type, blobs in fetched.items():
            page_model = CONTENT_PAGE_MODELS[content_type]
            for blob in blobs:
                try:
                    page_model.model_validate(blob["records"])
                except Exception as exc:
                    failures.append(f"{content_type} {blob['contentId']}: {exc}")
        if failures:
            pytest.fail(
                f"{len(failures)} blob(s) failed model validation:\n"
                + "\n".join(failures[:5])
            )

    def test_fixtures_are_banked_as_raw_record_arrays(self, capture) -> None:
        banked = [
            blob for blobs in capture["blobs"].values() for blob in blobs
        ]
        if not banked:
            pytest.skip("nothing fetchable yet; no fixtures to bank")
        for blob in banked:
            path = Path(blob["fixture"])
            assert path.is_file()
            body = json.loads(path.read_text())
            assert isinstance(body, list) and body, path
            assert body == blob["records"]
