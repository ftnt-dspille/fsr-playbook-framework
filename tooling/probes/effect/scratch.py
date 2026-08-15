"""A scratch playbook on the box: seed it, read its ground truth, purge it.

The probes mutate a real playbook, so they need one they are allowed to break.
Each probe gets its OWN collection (`_fsrpb_effect_<slug>`) because the
resolver's uuid5 is keyed on the collection name and FSR reserves deleted
UUIDs -- sharing one name across probes turns the second push into a 409.

Ground truth is read back through the API, never inferred from what we sent:
the whole point is that the connector's claim and the box's state are separate
facts.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(ROOT / "tooling"))

from probes._env import get_client  # noqa: E402

DB = ROOT / "data" / "fsr_reference.db"
COLLECTION_PREFIX = "_fsrpb_effect_"
WORKFLOW_PREFIX = "ep_"


class SeedError(RuntimeError):
    """The scratch playbook could not be put on the box -- probe cannot run."""


# ── seed ──────────────────────────────────────────────────────────────

def push_yaml(yaml_text: str) -> None:
    """Compile + push a playbook through the same path `fsrpb push` uses."""
    from fsr_playbooks.compiler import compile_yaml as _compile
    from e2e.runner import _push, _PushError

    result = _compile(yaml_text, DB)
    if not result.ok:
        msgs = "; ".join(f"{e.code.value}: {e.message}" for e in result.errors)
        raise SeedError(f"compile failed: {msgs}")
    coll = result.fsr_json["data"][0]
    client = get_client()
    if client is None:
        raise SeedError("no live client (FSR_BASE_URL / auth not configured)")
    with tempfile.TemporaryDirectory() as td:
        try:
            _push(client, coll, Path(td))
        except _PushError as exc:
            raise SeedError(f"push failed: {exc}") from exc


# ── ground truth ──────────────────────────────────────────────────────

def read_collection(name: str) -> dict | None:
    """The collection as the BOX holds it, workflows and steps expanded."""
    client = get_client()
    if client is None:
        return None
    url = (f"{client.base_url}/api/3/workflow_collections"
           f"?name={name}&$limit=1&$relationships=true")
    r = client.session.get(url, verify=client.verify_ssl, timeout=30)
    if r.status_code != 200:
        return None
    members = r.json().get("hydra:member", [])
    if not members:
        return None
    coll = members[0]
    expanded = []
    for wf in coll.get("workflows", []):
        if isinstance(wf, str):
            wr = client.session.get(client.base_url + wf + "?$relationships=true",
                                    verify=client.verify_ssl, timeout=30)
            if wr.status_code == 200:
                expanded.append(wr.json())
        elif isinstance(wf, dict):
            expanded.append(wf)
    coll["workflows"] = expanded
    return coll


def read_workflow(iri: str) -> dict | None:
    """Re-read ONE workflow by IRI -- the after-state of an applied edit."""
    client = get_client()
    if client is None:
        return None
    r = client.session.get(client.base_url + iri + "?$relationships=true",
                           verify=client.verify_ssl, timeout=30)
    return r.json() if r.status_code == 200 else None


def only_workflow(coll: dict | None) -> dict | None:
    wfs = [w for w in (coll or {}).get("workflows", []) if isinstance(w, dict)]
    return wfs[0] if len(wfs) == 1 else (wfs[0] if wfs else None)


def step_names(wf: dict | None) -> list[str]:
    return [s.get("name", "") for s in (wf or {}).get("steps", [])
            if isinstance(s, dict)]


def step_by_name(wf: dict | None, name: str) -> dict | None:
    for s in (wf or {}).get("steps", []):
        if isinstance(s, dict) and s.get("name") == name:
            return s
    return None


def step_arg(wf: dict | None, step: str, key: str) -> Any:
    """One rendered argument off a named step -- A5's terminal effect.

    Connector-step args nest under `arguments.params`; native steps put them
    at `arguments` top level. Look in both rather than assuming, because a
    probe that reads the wrong level reports "unchanged" for a write that
    landed (the exact false negative this suite must not produce).
    """
    st = step_by_name(wf, step)
    args = st.get("arguments") if isinstance(st, dict) else None
    if not isinstance(args, dict):
        return None
    params = args.get("params")
    if isinstance(params, dict) and key in params:
        return params[key]
    return args.get(key)


def route_count(wf: dict | None) -> int:
    return len([r for r in (wf or {}).get("routes", []) if isinstance(r, dict)])


# ── purge ─────────────────────────────────────────────────────────────

def purge(collection: str) -> None:
    """Hard-delete one scratch collection and its workflows.

    Client-side prefix filtering is NOT optional: FSR silently ignores unknown
    query filters and returns everything, and trusting a server-side filter
    once hard-deleted every workflow on an appliance. Nothing outside
    `_fsrpb_effect_*` / `ep_*` is ever passed to a delete here.
    """
    client = get_client()
    if client is None:
        return
    if not collection.startswith(COLLECTION_PREFIX):
        raise ValueError(f"refusing to purge a non-scratch collection: {collection!r}")
    try:
        r = client.session.get(
            f"{client.base_url}/api/3/workflow_collections?name={collection}&$limit=10",
            verify=client.verify_ssl, timeout=30)
        uuids = [c["uuid"] for c in (r.json().get("hydra:member", []) if r.status_code == 200 else [])
                 if c.get("uuid") and str(c.get("name", "")).startswith(COLLECTION_PREFIX)]
        if uuids:
            client.session.delete(
                f"{client.base_url}/api/3/delete/workflow_collections?$hardDelete=true",
                json={"ids": uuids}, verify=client.verify_ssl, timeout=30)

        wr = client.session.get(f"{client.base_url}/api/3/workflows?$limit=500",
                                verify=client.verify_ssl, timeout=30)
        if wr.status_code == 200:
            wf_uuids = [w["uuid"] for w in wr.json().get("hydra:member", [])
                        if isinstance(w.get("name"), str)
                        and w["name"].startswith(WORKFLOW_PREFIX) and w.get("uuid")]
            if wf_uuids:
                client.session.delete(
                    f"{client.base_url}/api/3/delete/workflows?$hardDelete=true",
                    json={"ids": wf_uuids}, verify=client.verify_ssl, timeout=30)
    except Exception:  # noqa: BLE001 -- cleanup is best-effort
        pass


def seed(collection: str, yaml_text: str) -> dict:
    """Purge, push, and hand back the box's own view of what landed.

    Returns `{collection, workflow, iri, uuid, yaml}`. Raises `SeedError` when
    the playbook is not on the box afterwards -- a probe must never grade a
    write against a seed that never happened.
    """
    purge(collection)
    push_yaml(yaml_text)
    coll = read_collection(collection)
    wf = only_workflow(coll)
    if not wf or not wf.get("@id"):
        raise SeedError(f"pushed {collection} but could not read it back")
    return {"collection": collection, "workflow": wf, "iri": wf["@id"],
            "uuid": wf.get("uuid"), "yaml": yaml_text}
