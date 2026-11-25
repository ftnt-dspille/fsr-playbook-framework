#!/usr/bin/env python3
"""Capture live Office 365 Management Activity API fixtures (the audit plane).

NOT a soarshelf connector capture: the Management Activity API is consumed
directly over REST. The flow: mint a client-credentials token (scope
``https://manage.office.com/.default``), list current subscriptions, list
available content for Audit.AzureActiveDirectory and Audit.General
(following the ``NextPageUri`` response header), fetch every blob, write one
RAW fixture file per blob (the records array, verbatim -- the promotable
shape) plus a ``capture-index.md`` manifest, validate every record through
the typed models, and print a summary (blobs, record counts per workload,
validation failures verbatim).

Usage (from the repo root)::

    .venv/bin/python -m fsr_playbooks.connectors.typed.capture_management_activity

Credentials come from ``M365_TENANT_ID`` / ``M365_CLIENT_ID`` /
``M365_CLIENT_SECRET`` in the environment, or from the gitignored lab env
file ``~/PycharmProjects/Miscellaneous/fortisoar/scratch/.env.m365``
(override with ``--env-file`` or ``M365_ENV_FILE``). Nothing credential-ish
is ever written into the fixtures; the index lands under ``scratch/``
(gitignored).

Read-only by default: list + fetch only. ``--start-subscriptions`` opt-in
POSTs /subscriptions/start for a missing content type -- MUTATING, and the
service throttles repeated starts (15 minutes between requests), so run it
once and only when a subscription is genuinely absent. The api went live
recently: a subscription exists but no blobs yet is a NORMAL outcome and is
reported, not failed (exit 0).

Blobs expire 7 days after creation; a validation failure does NOT abort the
capture -- fixtures are banked first, failures reported verbatim after.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from fsr_playbooks.connectors.typed.microsoft_management_activity import (
    CONTENT_PAGE_MODELS,
    CONTENT_TYPES,
    MANAGE_API_ROOT,
    MANAGEMENT_SCOPE,
    ContentPage,
    SubscriptionsPage,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTDIR = REPO_ROOT / "scratch" / "captures"
DEFAULT_ENV_FILE = (
    Path.home()
    / "PycharmProjects"
    / "Miscellaneous"
    / "fortisoar"
    / "scratch"
    / ".env.m365"
)
AUTH_URL = "https://login.microsoftonline.com"
_CAPTURE_DIR_NAME = "microsoft-management-activity"
_TIMEOUT = 60

_DOCS = (
    "https://learn.microsoft.com/en-us/office/office-365-management-api/"
    "office-365-management-activity-api-reference"
)
_SCHEMA_DOCS = (
    "https://learn.microsoft.com/en-us/office/office-365-management-api/"
    "office-365-management-activity-api-schema"
)


def load_env_file(path: Path) -> bool:
    """KEY=VALUE lines into os.environ (first writer wins); True if read."""
    try:
        text = path.read_text()
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
    return True


def resolve_creds(env_file: Path | None = None) -> tuple[str, str, str]:
    """M365_* from the environment, else from the gitignored lab env file."""
    if env_file is None:
        raw = os.environ.get("M365_ENV_FILE")
        env_file = Path(raw) if raw else DEFAULT_ENV_FILE
    if env_file.is_file():
        load_env_file(env_file)
    tenant = os.environ.get("M365_TENANT_ID", "")
    client_id = os.environ.get("M365_CLIENT_ID", "")
    client_secret = os.environ.get("M365_CLIENT_SECRET", "")
    return tenant, client_id, client_secret


def acquire_token(
    tenant_id: str, client_id: str, client_secret: str, timeout: int = _TIMEOUT
) -> str:
    """Client-credentials token for the activity feed (RAW, no Bearer)."""
    resp = requests.post(
        f"{AUTH_URL}/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": MANAGEMENT_SCOPE,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"token request failed: HTTP {resp.status_code}: {resp.text[:300]}"
        )
    payload: dict[str, Any] = resp.json()
    return str(payload["access_token"])


MAX_PAGES = 5
"""Safety cap on NextPageUri hops per list_content call."""


class ActivityFeedClient:
    """Thin GET/POST client for one tenant's activity feed.

    Every call carries the bearer token and ``PublisherIdentifier`` (the
    tenant GUID) -- the docs' recommended dedicated-quota parameter.
    """

    def __init__(self, tenant_id: str, token: str, timeout: int = _TIMEOUT):
        self.tenant_id = tenant_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self.timeout = timeout

    def _root(self) -> str:
        return f"{MANAGE_API_ROOT}/{self.tenant_id}/activity/feed"

    def get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        params = dict(params or {})
        params.setdefault("PublisherIdentifier", self.tenant_id)
        return self._session.get(
            f"{self._root()}{path}", params=params, timeout=self.timeout
        )

    def post(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        params = dict(params or {})
        params.setdefault("PublisherIdentifier", self.tenant_id)
        return self._session.post(
            f"{self._root()}{path}", params=params, timeout=self.timeout
        )

    def list_subscriptions(self) -> requests.Response:
        return self.get("/subscriptions/list")

    def start_subscription(self, content_type: str) -> requests.Response:
        return self.post("/subscriptions/start", {"contentType": content_type})

    def list_content(
        self, content_type: str, start: str | None = None, end: str | None = None
    ) -> list[dict[str, Any]]:
        """One window of content list items, following NextPageUri headers.

        startTime/endTime must be both-or-neither, at most 24h apart, start
        no more than 7 days in the past (docs). Omitted means "last 24
        hours". Pagination is a RESPONSE header, capped by ``max_pages``.
        """
        params: dict[str, Any] = {"contentType": content_type}
        if start:
            params["startTime"] = start
        if end:
            params["endTime"] = end
        items: list[dict[str, Any]] = []
        seen_pages = 0
        resp = self.get("/subscriptions/content", params)
        while True:
            if resp.status_code != 200:
                raise ActivityFeedHTTPError(resp)
            seen_pages += 1
            items.extend(resp.json())
            next_uri = resp.headers.get("NextPageUri")
            if not next_uri or seen_pages >= MAX_PAGES:
                break
            resp = self._session.get(next_uri, timeout=self.timeout)
        return items

    def fetch_blob(self, content_uri: str) -> requests.Response:
        return self._session.get(content_uri, timeout=self.timeout)


class ActivityFeedHTTPError(Exception):
    """A non-200 from the activity feed; carries the parsed AF error body."""

    def __init__(self, resp: requests.Response):
        try:
            body: Any = resp.json()
        except ValueError:
            body = resp.text[:500]
        super().__init__(f"HTTP {resp.status_code}: {json.dumps(body)[:300]}")
        self.status_code = resp.status_code
        self.body = body


def default_window(hours: int) -> tuple[str, str]:
    """The docs' window rules: <= 24h apart, start <= 7 days in the past."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%S"),
        end.strftime("%Y-%m-%dT%H:%M:%S"),
    )


_CONTENT_SLUG = {
    "Audit.AzureActiveDirectory": "azuread",
    "Audit.General": "general",
}


def _slugify_content_id(content_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", content_id).strip("-")
    return slug[:80] or "blob"


def _workload_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        workload = record.get("Workload") or "<missing>"
        counts[str(workload)] += 1
    return dict(sorted(counts.items()))


def _validate_records(content_type: str, records: list[dict[str, Any]]) -> list[str]:
    """Validate every record through the content type's page model.

    Returns the verbatim pydantic error strings (empty when all pass).
    """
    page_model = CONTENT_PAGE_MODELS[content_type]
    failures: list[str] = []
    for index, record in enumerate(records):
        try:
            page_model.model_validate([record])
        except Exception as exc:  # the verbatim error IS the deliverable
            failures.append(f"record[{index}]: {exc}")
    return failures


def capture(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    out_dir: Path,
    hours: int = 24,
    max_blobs: int = 20,
    start_missing: bool = False,
) -> dict[str, Any]:
    """One full read-only capture pass; returns the summary dict."""
    token = acquire_token(tenant_id, client_id, client_secret)
    client = ActivityFeedClient(tenant_id, token)
    out_dir.mkdir(parents=True, exist_ok=True)

    resp = client.list_subscriptions()
    if resp.status_code != 200:
        raise ActivityFeedHTTPError(resp)
    subscriptions = SubscriptionsPage.model_validate(resp.json()).root
    subscribed = {item.contentType: item.status for item in subscriptions}

    start, end = default_window(hours)
    summary: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tenant_id": tenant_id,
        "window": {"start": start, "end": end},
        "subscriptions": {
            ct: subscribed.get(ct) for ct in CONTENT_TYPES
        },
        "content_types": {},
    }

    for content_type in CONTENT_TYPES:
        status = subscribed.get(content_type)
        type_summary: dict[str, Any] = {"subscription_status": status, "blobs": []}
        if status is None and start_missing:
            started = client.start_subscription(content_type)
            type_summary["start_attempt"] = {
                "status_code": started.status_code,
                "body": started.text[:300],
            }
            status = "start-requested"
        if status is None:
            print(f"  {content_type}: no subscription (use --start-subscriptions once)")
            summary["content_types"][content_type] = type_summary
            continue
        try:
            items = client.list_content(content_type, start, end)
            ContentPage.model_validate(items)
        except ActivityFeedHTTPError as exc:
            type_summary["error"] = str(exc)
            print(f"  {content_type}: list failed: {exc}")
            summary["content_types"][content_type] = type_summary
            continue
        print(f"  {content_type}: {len(items)} content blob(s) listed")
        for item in items[:max_blobs]:
            blob_resp = client.fetch_blob(item["contentUri"])
            if blob_resp.status_code != 200:
                type_summary["blobs"].append(
                    {
                        "contentType": content_type,
                        "contentId": item["contentId"],
                        "error": f"HTTP {blob_resp.status_code}: "
                        f"{blob_resp.text[:200]}",
                    }
                )
                continue
            records = blob_resp.json()
            if not isinstance(records, list):
                records = [records]
            failures = _validate_records(content_type, records)
            name = (
                f"{_CONTENT_SLUG.get(content_type, 'blob')}."
                f"{_slugify_content_id(item['contentId'])}.json"
            )
            (out_dir / name).write_text(json.dumps(records, indent=2) + "\n")
            type_summary["blobs"].append(
                {
                    "contentType": content_type,
                    "fixture": name,
                    "contentId": item["contentId"],
                    "contentCreated": item.get("contentCreated"),
                    "record_count": len(records),
                    "workloads": _workload_counts(records),
                    "validation_failures": len(failures),
                    "failure_messages": failures,
                }
            )
        summary["content_types"][content_type] = type_summary
    return summary


def _write_index(out_dir: Path, summary: dict[str, Any]) -> Path:
    lines = [
        "# microsoft-management-activity capture index",
        "",
        f"captured_at: {summary['captured_at']}",
        f"tenant: {summary['tenant_id']}",
        f"window: {summary['window']['start']} .. {summary['window']['end']}",
        "",
        "Provenance: docs-derived (Microsoft Learn, Office 365 Management",
        "Activity API reference + schema), live-capture pending. Fixtures",
        "are RAW records arrays; promote sanitized shapes into the typed",
        "module's mocks only by hand.",
        "",
        "| content type | subscription | blobs | records | validation |",
        "| --- | --- | --- | --- | --- |",
    ]
    for content_type, type_summary in summary["content_types"].items():
        blobs = [
            blob for blob in type_summary.get("blobs", []) if "record_count" in blob
        ]
        records = sum(blob["record_count"] for blob in blobs)
        failures = sum(blob["validation_failures"] for blob in blobs)
        lines.append(
            f"| {content_type} | {type_summary.get('subscription_status')} "
            f"| {len(blobs)} | {records} "
            f"| {len(blobs) - failures}/{len(blobs)} blobs clean |"
        )
    lines += ["", "## Blobs", ""]
    for content_type, type_summary in summary["content_types"].items():
        for blob in type_summary.get("blobs", []):
            if "error" in blob:
                lines.append(f"- {content_type}: ERROR {blob['error']}")
                continue
            workloads = ", ".join(
                f"{name}={count}" for name, count in blob["workloads"].items()
            )
            lines.append(
                f"- `{blob['fixture']}`: {blob['record_count']} records "
                f"({workloads or 'none'}), {blob['validation_failures']} "
                f"validation failure(s)"
            )
    lines += ["", "## Validation failures (verbatim)", ""]
    for type_summary in summary["content_types"].values():
        for blob in type_summary.get("blobs", []):
            for failure in blob.get("failure_messages", []):
                lines.append(f"- [{blob['contentType']}] {failure}")
    path = out_dir / "capture-index.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture live Office 365 Management Activity API "
        "fixtures into scratch/captures/microsoft-management-activity/"
    )
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="KEY=VALUE file for the M365_* vars (default: the gitignored "
        "lab .env.m365, used only when the vars are not already set)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="content window length in hours (1-24; the docs cap a window "
        "at 24h and 7 days back)",
    )
    parser.add_argument(
        "--max-blobs",
        type=int,
        default=20,
        help="fetch at most this many blobs per content type",
    )
    parser.add_argument(
        "--start-subscriptions",
        action="store_true",
        help="MUTATING: POST /subscriptions/start for a missing content "
        "type (15-minute service throttling between starts)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.hours <= 24:
        parser.error("--hours must be 1..24 (the docs cap a window at 24h)")

    tenant_id, client_id, client_secret = resolve_creds(args.env_file)
    if not (tenant_id and client_id and client_secret):
        parser.error(
            "set M365_TENANT_ID / M365_CLIENT_ID / M365_CLIENT_SECRET (env "
            "or the gitignored lab .env.m365 file)"
        )

    out_dir = args.outdir / _CAPTURE_DIR_NAME
    print(f"capturing the management activity feed into {out_dir}")
    summary = capture(
        tenant_id,
        client_id,
        client_secret,
        out_dir,
        hours=args.hours,
        max_blobs=args.max_blobs,
        start_missing=args.start_subscriptions,
    )

    total_blobs = 0
    total_records = 0
    workload_totals: Counter[str] = Counter()
    print("\nsummary:")
    for content_type, type_summary in summary["content_types"].items():
        blobs = [
            blob for blob in type_summary.get("blobs", []) if "record_count" in blob
        ]
        records = sum(blob["record_count"] for blob in blobs)
        total_blobs += len(blobs)
        total_records += records
        for count in blobs:
            workload_totals.update(count["workloads"])
        print(
            f"  {content_type}: subscription={type_summary.get('subscription_status')}"
            f" blobs={len(blobs)} records={records}"
        )
    print(f"  total: {total_blobs} blob(s), {total_records} record(s)")
    if workload_totals:
        print(
            "  workloads: "
            + ", ".join(
                f"{name}={count}" for name, count in sorted(workload_totals.items())
            )
            + " (Note: Audit.General mixes workloads)"
        )
        print("  (per-workload counts above span BOTH content types)")

    index_path = _write_index(out_dir, summary)
    failure_lines = [
        f"{blob['fixture']} {failure}"
        for type_summary in summary["content_types"].values()
        for blob in type_summary.get("blobs", [])
        for failure in blob.get("failure_messages", [])
    ]
    if failure_lines:
        print(f"\nvalidation failures ({len(failure_lines)}, verbatim):")
        for line in failure_lines[:20]:
            print(f"  {line}")
        if len(failure_lines) > 20:
            print(f"  ... {len(failure_lines) - 20} more (all in capture-index.md)")
    else:
        print("\nvalidation failures: none")
    print(f"index: {index_path}")
    print("done: fixtures under " + str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
