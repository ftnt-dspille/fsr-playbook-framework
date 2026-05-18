"""
Tiny FastAPI app that mimics the FortiSOAR endpoints the FSRPB backend
hits. Used by the E2E Playwright suite — points the real backend at
this stub via FSR_BASE_URL so we exercise the full request path without
a live appliance.

Only stubs what `web/backend/routes/ref.py` actually calls:
  - GET /api/wf/api/workflows/                       (recent-runs)
  - GET /api/wf/api/workflows/{id}/                  (run-detail)
  - GET /api/wf/api/dynamic-variable/                (global-vars)
  - GET /api/3/{module}                              (sample-record)
  - GET /api/3/{module}/{id}                         (record-by-iri)
  - GET /api/auth/license/?param=licenseDetails      (pyfsr handshake)

Shape choices match the comments in the real backend:
  - picklist values keep their {itemValue, value, @type} wrapping so
    fsrValue.formatFsrValue can unwrap them client-side.
  - workflow detail returns `wf_step_logs` (the first of the three
    field-name candidates the runVarsStore probes), so the Real-run
    pane spec can assert the observed-value rendering.

Run standalone for poking:  uvicorn fsr_stub:app --port 47820
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="FSR stub for E2E")

# Canned alerts that the trigger module sample picker pulls.
_ALERTS: list[dict[str, Any]] = [
    {
        "@id": "/api/3/alerts/aaaa-1111",
        "@type": "Alert",
        "id": 101,
        "name": "Suspicious login",
        "severity": {
            "@id": "/api/3/picklists/sev-high",
            "@type": "Picklist",
            "itemValue": "High",
            "value": "High",
        },
        "status": {
            "@id": "/api/3/picklists/status-open",
            "@type": "Picklist",
            "itemValue": "Open",
            "value": "Open",
        },
        "sourceIp": "10.0.0.42",
        "destIp": "192.168.1.1",
    },
    {
        "@id": "/api/3/alerts/bbbb-2222",
        "@type": "Alert",
        "id": 102,
        "name": "Port scan",
        "severity": {
            "@id": "/api/3/picklists/sev-low",
            "@type": "Picklist",
            "itemValue": "Low",
            "value": "Low",
        },
        "sourceIp": "10.0.0.99",
    },
]

# A canned past run with step traces in the `wf_step_logs` shape.
_WORKFLOW_RUNS: list[dict[str, Any]] = [
    {
        "@id": "/api/wf/api/workflows/9001",
        "id": 9001,
        "status": "success",
        "created": "2026-05-17T09:00:00Z",
        "modified": "2026-05-17T09:00:08Z",
        "playbookName": "Demo Playbook",
        "records": ["/api/3/alerts/aaaa-1111"],
    },
    {
        "@id": "/api/wf/api/workflows/9002",
        "id": 9002,
        "status": "failed",
        "created": "2026-05-17T08:30:00Z",
        "modified": "2026-05-17T08:30:02Z",
        "playbookName": "Demo Playbook",
        "records": ["/api/3/alerts/bbbb-2222"],
    },
]

_RUN_DETAILS: dict[int, dict[str, Any]] = {
    9001: {
        "id": 9001,
        "status": "success",
        "created": "2026-05-17T09:00:00Z",
        "modified": "2026-05-17T09:00:08Z",
        "playbookName": "Demo Playbook",
        "records": ["/api/3/alerts/aaaa-1111"],
        # First of the three candidate field names runVarsStore probes
        # — confirms the trace-source ordering on a real fetch.
        "wf_step_logs": [
            {
                "name": "Find Issue",
                "result": {"data": [{"id": 555, "severity": "critical"}]},
            },
            {
                "name": "Read Sev",
                "result": {"severity": "critical"},
            },
        ],
    },
    9002: {
        "id": 9002,
        "status": "failed",
        "created": "2026-05-17T08:30:00Z",
        "records": [],
        "wf_step_logs": [],
    },
}

_GLOBAL_VARS = [
    {"name": "tenant_id", "value": "acme-prod"},
    {"name": "siem_base_url", "value": "https://siem.example.com"},
]


# --------------------------------------------------------------------- routes


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/license/")
def license_check(request: Request) -> JSONResponse:
    """pyfsr's `FortiSOAR(...)` constructor probes this endpoint to
    confirm the appliance is reachable + the credential is valid. The
    real response includes a license block; we return a minimal
    success payload."""
    return JSONResponse({"licenseDetails": {"valid": True}})


@app.get("/api/wf/api/workflows/")
def list_workflows(
    ordering: str | None = None,
    limit: int = 5,
    format: str | None = None,
    template_iri: str | None = None,
) -> dict[str, Any]:
    items = list(_WORKFLOW_RUNS)
    if ordering == "-created":
        items.sort(key=lambda x: x.get("created", ""), reverse=True)
    return {"hydra:member": items[: max(1, min(limit, 20))]}


@app.get("/api/wf/api/workflows/{run_id}/")
def get_workflow(run_id: int, format: str | None = None) -> dict[str, Any]:
    return _RUN_DETAILS.get(run_id, {"id": run_id, "status": "missing"})


@app.get("/api/wf/api/dynamic-variable/")
def global_vars() -> dict[str, Any]:
    """FSR exposes globalVars under this internal name (the user
    discovered this — not in the public API guide). Backend's
    /api/ref/global-vars wraps it."""
    return {"hydra:member": _GLOBAL_VARS}


@app.get("/api/3/{module}")
def list_records(module: str, request: Request) -> dict[str, Any]:
    """Sample-record fetcher: backend hits this with `?$limit=N&$orderby=-id`.
    We ignore the query and just return the canned set for 'alerts'."""
    if module == "alerts":
        return {"hydra:member": _ALERTS}
    return {"hydra:member": []}


@app.get("/api/3/{module}/{record_id}")
def get_record(module: str, record_id: str) -> dict[str, Any]:
    """Record-by-IRI fetcher. Match the IRI tail against our canned set."""
    for rec in _ALERTS:
        iri = rec.get("@id", "")
        if iri.endswith(f"/{record_id}"):
            return rec
    return {"error": "not found"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("FSR_STUB_PORT", "47820"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
