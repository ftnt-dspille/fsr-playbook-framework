"""Semantic round-trip diff: FSR JSON -> IR -> FSR JSON.

A perfect byte-equivalent round trip is impossible -- FSR carries
metadata (timestamps, ownership, layout) that the IR doesn't model.
Instead we check **semantic equivalence**: same steps, same arguments,
same routing graph. That is the property the compiler must preserve.
"""
from __future__ import annotations

from typing import Any

from .decompiler import decompile
from .emitter import emit
from .wire import as_record_list


def _to_uuid_or_iri(field: Any) -> str:
    """Normalize live-API expanded dicts and export-side IRI strings to a uuid.

    `?$relationships=true` returns nested dicts in place of IRIs; the export
    JSON keeps IRI strings. Both reach this normalizer; treat them the same.
    """
    if isinstance(field, dict):
        return field.get("uuid") or ""
    if isinstance(field, str):
        return field.rsplit("/", 1)[-1]
    return ""


def _step_type_key(field: Any) -> str:
    """For semantic comparison, what matters is the step-type uuid, not whether
    the response shape was an IRI or an expanded dict."""
    if isinstance(field, dict):
        return field.get("uuid", "") or ""
    if isinstance(field, str):
        return field.rsplit("/", 1)[-1]
    return ""


def _normalize_workflow(wf: dict[str, Any]) -> dict[str, Any]:
    """Strip fields that are layout/metadata-only and won't survive round trip."""
    steps = as_record_list(wf.get("steps"), path="workflow.steps")
    steps_by_uuid = {s.get("uuid"): s for s in steps}
    norm_steps = []
    for s in steps:
        args = dict(s.get("arguments") or {})
        # for_each is a wire-level args key but conceptually a separate
        # construct -- lift it out so it's compared as its own thing and
        # arguments-diffs aren't drowned by for_each contents.
        fe = args.pop("for_each", None)
        if isinstance(fe, dict) and not fe:
            fe = None
        norm_steps.append({
            "name": s.get("name"),
            "stepType": _step_type_key(s.get("stepType")),
            "arguments": args,
            "for_each": fe,
        })
    norm_steps.sort(key=lambda x: (x["name"] or "", x["stepType"] or ""))

    norm_routes = []
    for r in as_record_list(wf.get("routes"), path="workflow.routes"):
        s_uuid = _to_uuid_or_iri(r.get("sourceStep"))
        t_uuid = _to_uuid_or_iri(r.get("targetStep"))
        # FSR treats label="" and label=None equivalently; normalize.
        label = r.get("label")
        if label == "":
            label = None
        norm_routes.append({
            "src_name": (steps_by_uuid.get(s_uuid) or {}).get("name"),
            "tgt_name": (steps_by_uuid.get(t_uuid) or {}).get("name"),
            "label": label,
        })
    norm_routes.sort(key=lambda x: (x["src_name"] or "", x["tgt_name"] or "", x["label"] or ""))

    trigger_uuid = _to_uuid_or_iri(wf.get("triggerStep"))
    trigger_name = (steps_by_uuid.get(trigger_uuid) or {}).get("name")

    raw_params = wf.get("parameters") or []
    if isinstance(raw_params, list):
        params = [p for p in raw_params if isinstance(p, str)]
    else:
        params = []

    # Union in the trigger step's inputVariables -- the decompiler does the
    # same (decompiler.py:1174-1182). FSR is inconsistent: some playbooks
    # have an empty top-level `parameters` but declare inputs on the trigger
    # step. Without this union the normalizer sees fewer params than the
    # decompiler produced, and every such workflow false-fails round-trip.
    trigger_step = steps_by_uuid.get(trigger_uuid) or {}
    trigger_args = trigger_step.get("arguments") or {}
    seen = set(params)
    for iv in trigger_args.get("inputVariables") or []:
        if not isinstance(iv, dict):
            continue
        pname = iv.get("name")
        if isinstance(pname, str) and pname and pname not in seen:
            seen.add(pname)
            params.append(pname)
    params = sorted(params)

    return {
        "name": wf.get("name"),
        "description": wf.get("description") or "",
        "tag": wf.get("tag") or "",
        "trigger_step_name": trigger_name,
        "parameters": params,
        "steps": norm_steps,
        "routes": norm_routes,
    }


def normalize_collection(fsr_json: dict[str, Any]) -> dict[str, Any]:
    coll = as_record_list(fsr_json.get("data"), path="data")[0]
    return {
        "name": coll.get("name"),
        "description": coll.get("description") or "",
        "workflows": sorted(
            (_normalize_workflow(w)
             for w in as_record_list(coll.get("workflows"),
                                     path="collection.workflows")),
            key=lambda x: x["name"] or "",
        ),
    }


def diff(original: dict, regenerated: dict, path: str = "") -> list[str]:
    """Walk two normalized dicts and produce a list of human-readable diffs."""
    diffs: list[str] = []
    if type(original) is not type(regenerated):
        diffs.append(f"{path}: type mismatch ({type(original).__name__} vs {type(regenerated).__name__})")
        return diffs
    if isinstance(original, dict):
        keys = set(original) | set(regenerated)
        for k in sorted(keys):
            if k not in original:
                diffs.append(f"{path}.{k}: only in regenerated -> {regenerated[k]!r:.200}")
            elif k not in regenerated:
                diffs.append(f"{path}.{k}: only in original -> {original[k]!r:.200}")
            else:
                diffs += diff(original[k], regenerated[k], f"{path}.{k}")
    elif isinstance(original, list):
        if len(original) != len(regenerated):
            diffs.append(f"{path}: list length {len(original)} vs {len(regenerated)}")
        for i, (a, b) in enumerate(zip(original, regenerated)):
            diffs += diff(a, b, f"{path}[{i}]")
    else:
        if original != regenerated:
            diffs.append(f"{path}: {original!r} != {regenerated!r}")
    return diffs


def roundtrip(fsr_json: dict[str, Any], db_path) -> tuple[bool, list[str]]:
    ir = decompile(fsr_json, db_path)
    regen = emit(ir)
    a = normalize_collection(fsr_json)
    b = normalize_collection(regen)
    diffs = diff(a, b, "collection")
    return (not diffs), diffs
