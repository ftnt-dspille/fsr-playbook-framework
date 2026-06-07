"""Trigger one run of each freshly-pushed demo via fsrpb, return run URLs."""
from __future__ import annotations
import subprocess, sys, time, json
from pathlib import Path

sys.path.insert(0, str(Path("/Users/dylanspille/PycharmProjects/fsr-playbook-framework/python")))
from probes import _env  # type: ignore

ALERT_UUID = "db7afbf7-d8f4-4f15-a8d1-a16e1b9beb50"
BASE = "https://10.99.249.205"

# (display name, kind, record-arg or None)
JOBS = [
    ("FSRPB Demo - Triage Alert",            "record",  f"alerts:{ALERT_UUID}"),
    ("FSRPB Demo - On Alert Create",         "on_create", None),
    ("FSRPB Demo - On Alert Status Change",  "on_update", ALERT_UUID),
    ("FSRPB Demo - Code Snippet",            "manual",  None),
    ("FSRPB Demo - Delay",                   "manual",  None),
    ("FSRPB For Each Create",                "manual",  None),
    ("FSRPB Demo - Manual Input",            "manual",  None),
    ("FSRPB Parent Caller",                  "manual",  None),
    ("FSRPB Create Alert",                   "manual",  None),
    ("FSRPB Find And Update Alert",          "manual",  None),
    ("VT IP Reputation",                     "manual",  None),
]


def fsrpb(*args: str) -> tuple[int, str]:
    r = subprocess.run(["fsrpb", *args], capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout + r.stderr)


def find_wf_uuid(client, name: str) -> str | None:
    r = client.session.get(client.base_url + "/api/3/workflows",
                           params={"name": name, "$limit": 5},
                           verify=client.verify_ssl)
    m = r.json().get("hydra:member", []) if r.status_code == 200 else []
    for w in m:
        if w.get("name") == name:
            return w["uuid"]
    return m[0]["uuid"] if m else None


def latest_run_pk(client, wf_uuid: str) -> str | None:
    r = client.session.get(
        client.base_url + "/api/wf/api/workflows/",
        params={"template_iri": f"/api/3/workflows/{wf_uuid}",
                "ordering": "-created", "limit": 1, "format": "json"},
        verify=client.verify_ssl,
    )
    m = r.json().get("hydra:member", []) if r.status_code == 200 else []
    if not m:
        return None
    return m[0].get("@id", "").rstrip("/").rsplit("/", 1)[-1]


def main() -> int:
    client = _env.get_client()
    rows = []
    for name, kind, arg in JOBS:
        print(f"=== {name} ({kind})", flush=True)
        wf_uuid = find_wf_uuid(client, name)
        if not wf_uuid:
            rows.append((name, "?", "no workflow found"))
            print(f"  no wf_uuid", flush=True)
            continue

        if kind == "record":
            rc, out = fsrpb("run-playbook", name, "--record", arg)
        elif kind == "on_create":
            # Create a fresh alert via fsrpb to fire on-create trigger
            ts = int(time.time())
            r = client.session.post(
                client.base_url + "/api/3/alerts",
                json={"name": f"FSRPB demo on-create {ts}",
                      "source": "FSRPB demo",
                      "type": {"itemValue": "Phishing"},
                      "severity": {"itemValue": "Low"},
                      "status": {"itemValue": "Open"}},
                verify=client.verify_ssl,
            )
            rc = 0 if r.status_code in (200, 201) else 1
            out = f"create alert HTTP {r.status_code}: {r.text[:150]}"
        elif kind == "on_update":
            r = client.session.put(
                client.base_url + f"/api/3/alerts/{arg}",
                json={"status": {"itemValue": "Investigating"}},
                verify=client.verify_ssl,
            )
            rc = 0 if r.status_code in (200, 204) else 1
            out = f"update alert HTTP {r.status_code}: {r.text[:150]}"
        else:
            rc, out = fsrpb("run-playbook", name)

        last_lines = "\n  ".join(out.strip().splitlines()[-3:])
        print(f"  rc={rc} {last_lines}", flush=True)
        time.sleep(4)
        pk = latest_run_pk(client, wf_uuid)
        url = f"{BASE}/playbook/{wf_uuid}/{pk}" if pk else "(no run pk)"
        rows.append((name, wf_uuid, url))
        print(f"  run URL: {url}", flush=True)

    print("\n=== SUMMARY ===")
    for name, wf_uuid, url in rows:
        print(f"{name}\n  {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
