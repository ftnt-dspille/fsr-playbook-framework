"""One-shot: hard-purge each demo collection and re-push fresh.

Sequence per playbook (only this order yields fresh workflow_step PKs):
  1. GET the workflow's step UUIDs.
  2. Hard-delete the *workflow* (frees the trigger-step FK).
  3. Hard-delete each step UUID individually.
  4. Hard-delete the collection (cleans the parent record).
  5. fsrpb push --mode replace to re-create everything fresh.
"""
from __future__ import annotations
import subprocess, sys, os
from pathlib import Path

sys.path.insert(0, str(Path("/Users/dylanspille/PycharmProjects/fsr-playbook-framework/python")))
from probes import _env  # type: ignore

EXAMPLES = Path("/Users/dylanspille/PycharmProjects/fsr-playbook-framework/examples")

DEMOS = [
    ("demo_alert_action.yaml",          "FSRPB Demo Alert Action"),
    ("demo_alert_on_create.yaml",       "FSRPB Demo Alert On Create"),
    ("demo_alert_on_status_change.yaml","FSRPB Demo Alert On Status Change"),
    ("demo_code_snippet.yaml",          "FSRPB Demo Code Snippet"),
    ("demo_delay.yaml",                 "FSRPB Demo Delay"),
    ("demo_for_each.yaml",              "FSRPB Demo For Each"),
    ("demo_manual_input.yaml",          "FSRPB Demo Manual Input"),
    ("demo_parent_child.yaml",          "FSRPB Demo Parent Child"),
    ("demo_pure_logic.yaml",            "FSRPB Demo Pure Logic"),
    ("demo_record_create.yaml",         "FSRPB Demo Record Create"),
    ("demo_record_find_update.yaml",    "FSRPB Demo Record CRUD"),
    ("demo_virustotal_ip.yaml",         "FSRPB Demo VirusTotal"),
]


def hard_purge(client, coll_name: str) -> tuple[int, int]:
    """Returns (workflows_deleted, steps_deleted)."""
    # 1. Find collection
    r = client.session.get(
        client.base_url + "/api/3/workflow_collections",
        params={"name": coll_name}, verify=client.verify_ssl,
    )
    members = r.json().get("hydra:member", []) if r.status_code == 200 else []
    if not members:
        return (0, 0)
    coll_uuid = members[0]["uuid"]
    coll_iri = f"/api/3/workflow_collections/{coll_uuid}"

    # 2. Get all workflows in that collection (with steps)
    wfs_r = client.session.get(
        client.base_url + "/api/3/workflows",
        params={"collection": coll_iri, "$relationships": "true", "$limit": 100},
        verify=client.verify_ssl,
    )
    workflows = wfs_r.json().get("hydra:member", []) if wfs_r.status_code == 200 else []

    all_step_uuids = []
    wf_uuids = []
    for wf in workflows:
        wf_uuids.append(wf["uuid"])
        for s in wf.get("steps") or []:
            if s.get("uuid"):
                all_step_uuids.append(s["uuid"])

    # 3. Hard-delete workflows first (frees trigger-step FK)
    if wf_uuids:
        client.session.delete(
            client.base_url + "/api/3/delete/workflows?$hardDelete=true",
            json={"ids": wf_uuids}, verify=client.verify_ssl,
        )

    # 4. Hard-delete each step UUID individually
    if all_step_uuids:
        client.session.delete(
            client.base_url + "/api/3/delete/workflow_steps?$hardDelete=true",
            json={"ids": all_step_uuids}, verify=client.verify_ssl,
        )

    # 5. Hard-delete the collection
    client.session.delete(
        client.base_url + "/api/3/delete/workflow_collections?$hardDelete=true",
        json={"ids": [coll_uuid]}, verify=client.verify_ssl,
    )

    return (len(wf_uuids), len(all_step_uuids))


def main() -> int:
    client = _env.get_client()
    for fname, coll_name in DEMOS:
        print(f"=== {coll_name} ({fname})", flush=True)
        try:
            wf_n, step_n = hard_purge(client, coll_name)
            print(f"  purged: {wf_n} workflow(s), {step_n} step(s)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  purge ERROR: {e}", flush=True)
        path = EXAMPLES / fname
        r = subprocess.run(["fsrpb", "push", "--mode", "replace", str(path)],
                           capture_output=True, text=True)
        last = (r.stdout + r.stderr).strip().splitlines()[-2:]
        for line in last:
            print(f"  {line}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
