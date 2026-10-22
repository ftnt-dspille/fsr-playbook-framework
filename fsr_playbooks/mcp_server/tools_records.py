"""Record writes: ``create_record`` / ``update_record``.

Mechanism only. Who may write to which module is the host's policy, asked
through ``_shared.record_write_gate`` (the SOC assistant connector answers it
from the active persona's ``may_write`` scope). With no host policy every write
is refused. Two guards wrap every call:

  1. **Write gate** -- the tool body refuses unless the host's gate permits
     ``module``. ``precard_validate`` runs the same gate before the approval
     card is built, so an out-of-scope write is refused at proposal time
     instead of after the analyst approves it.
  2. **Approval card** -- both tools register at **tier 3**, so
     ``fsr_playbooks.llm.tools.dispatch`` returns a ``pending_approval``
     envelope and nothing is written until the analyst approves.

Before a write leaves, the module's fields are read live and three mistakes
are refused with the fix named (an unknown field, a list sent to a text field,
a picklist label the picklist lacks); a picklist label the platform refuses is
resolved to its IRI and the write retried.

Transport: the live crudhub loopback on-box, a ``.env`` pyfsr client in dev --
both via ``_shared._live_client()`` + ``live_request_with_reauth``.
"""
from __future__ import annotations

import re
from typing import Any

from fsr_playbooks.llm.tool_result import tool_err
from fsr_playbooks.mcp_server import _shared
from fsr_playbooks.mcp_server._record_lookup import live_request as _request
from fsr_playbooks.mcp_server._record_lookup import unknown_record
from fsr_playbooks.mcp_server._shared import mcp


def precard_validate(args: dict) -> dict | None:
    """Pre-card validator for ``create_record`` / ``update_record``: refuse a
    write BEFORE it becomes an approval card.

    The write gate also runs in the tool body, but a tier-3 body only runs after
    the analyst approves, so without this the analyst reviews and approves a
    write the system already knows it will refuse. This calls the same gate, so
    there is one definition of who may write where; the in-body call stays the
    backstop (a grant, an eval policy or a resumed approval re-enter there).

    Fail-open per the validator contract: anything unexpected returns ``None``
    and the call cards as before, because refusing a legitimate write is worse
    than carding a doomed one.
    """
    module = (args or {}).get("module")
    if not module or not isinstance(module, str):
        return None  # the tool body's own arg check owns this
    gate = _shared.record_write_gate(module)
    if gate is not None:
        return gate
    # An update names a record; an invented uuid used to card, be approved,
    # and only then 404 (HARDEN-4). Same fail-open contract.
    uuid = (args or {}).get("uuid")
    if isinstance(uuid, str) and uuid.strip():
        missing = unknown_record(_shared._live_client(), module, uuid.strip(),
                                 active_iri=_shared.active_record_iri())
        if missing is not None:
            return missing
    try:
        client = _shared._live_client()
        fields = (args or {}).get("fields")
        return (_unknown_fields(client, module, fields)
                or _structured_into_text(client, module, fields)
                or _bad_picklist_label(client, module, fields))
    except Exception:  # noqa: BLE001 -- fail open, the body re-checks
        return None


# Field types that hold text. A list or object sent to one is stored as the
# literal word "Array" (live: a template's inputParameters, whose real format is
# newline-separated names, saved as "Array" after an approved create).
_TEXT_TYPES = frozenset({"string", "text", "richtext", "html"})
_ATTR_CACHE: dict[tuple[str, str], dict[str, dict]] = {}


def _module_attrs(client: Any, module: str) -> dict[str, dict]:
    """``{field: attribute}`` for ``module``, read live (cached per box and
    module). Empty when the lookup fails: callers fail open."""
    key = (getattr(client, "base_url", ""), module)
    if key not in _ATTR_CACHE:
        from urllib.parse import quote
        r = _request("get", client, f"{client.base_url}/api/3/model_metadatas"
                     f"?type={quote(module)}&$relationships=true&$limit=1")
        if getattr(r, "status_code", None) != 200:
            return {}
        members = (r.json() or {}).get("hydra:member") or []
        attrs = (members[0].get("attributes") if members else None) or []
        _ATTR_CACHE[key] = {a["name"]: a for a in attrs
                            if isinstance(a, dict) and a.get("name")}
    return _ATTR_CACHE[key]


def _field_types(client: Any, module: str) -> dict[str, str]:
    """``{field: type}`` for ``module``. Empty when the lookup fails."""
    return {k: str(a.get("type") or "") for k, a in _module_attrs(client, module).items()}


def _field_picklist(attr: dict) -> str | None:
    """The picklist a field takes its values from (e.g. 'AlertClosureReason'),
    or None. Same reading as the catalog warm."""
    ds = attr.get("dataSource") or {}
    if not isinstance(ds, dict):
        return None
    for f in (ds.get("query") or {}).get("filters", []) or []:
        if isinstance(f, dict) and f.get("field") == "listName__name":
            v = f.get("value")
            if isinstance(v, str):
                return v
    return None


def _stored_examples(client: Any, module: str, field: str) -> list[str]:
    """Up to two non-empty values other records of ``module`` hold in ``field``."""
    r = _request("get", client, f"{client.base_url}/api/3/{module}?$limit=20")
    if getattr(r, "status_code", None) != 200:
        return []
    out: list[str] = []
    for rec in (r.json() or {}).get("hydra:member") or []:
        v = rec.get(field)
        if isinstance(v, str) and v.strip() and v != "Array" and v not in out:
            out.append(v)
        if len(out) == 2:
            break
    return out


# Record keys the platform accepts on a write that the module's attribute list
# does not declare (it lists only the fields the module defines).
_SYSTEM_WRITABLE = frozenset({"recordTags", "tenant", "fsrQueue", "owners", "conflict"})


def _unknown_fields(client: Any, module: str, fields: dict) -> dict | None:
    """Refuse a field the module does not have, naming the ones it does.

    The platform ignores an unknown key and answers 200, so the write "worked"
    and changed nothing. Live: `outputTemplateJson` for `outputTemplateJSON`,
    approved twice, and the template never saved. Fails open when the module's
    fields cannot be read."""
    if client is None or not isinstance(fields, dict):
        return None
    attrs = _module_attrs(client, module)
    if not attrs:
        return None
    bad = [k for k in fields if isinstance(k, str) and not k.startswith("@")
           and k not in attrs and k not in _SYSTEM_WRITABLE]
    if not bad:
        return None
    from fsr_playbooks.mcp_server.tools_triage import _nearest_field_names
    names = sorted(attrs)
    near = {k: _nearest_field_names(k, names) for k in bad}
    hint = "; ".join(f"{k!r}: did you mean {', '.join(repr(n) for n in v)}?" if v
                     else f"{k!r}: no close match" for k, v in near.items())
    return tool_err(
        "unknown_field",
        f"{module} records have no field {', '.join(repr(k) for k in bad)}, so the "
        f"write would change nothing ({hint}). Field names are case-sensitive.",
        fields=bad, suggestions=near, module=module)


def _structured_into_text(client: Any, module: str, fields: dict) -> dict | None:
    """Refuse a list or object sent to a text field, naming the format the
    module's records actually use. Coercing would guess the format (JSON?
    one per line?), and the platform's own answer is to save "Array"."""
    if client is None or not isinstance(fields, dict):
        return None
    bad = [k for k, v in fields.items() if isinstance(v, (list, dict))
           and not _is_link(v)]
    if not bad:
        return None
    types = _field_types(client, module)
    bad = [k for k in bad if types.get(k) in _TEXT_TYPES]
    if not bad:
        return None
    field = bad[0]
    examples = _stored_examples(client, module, field)
    return tool_err(
        "not_text",
        f"{field!r} is a text field on {module}; send it as a string. A list or "
        "object would be saved as the word 'Array'."
        + (" Other records hold it like this: "
           + "; ".join(repr(e[:120]) for e in examples) + "." if examples else ""),
        field=field, fields=bad, module=module, examples=examples)


def _bad_picklist_label(client: Any, module: str, fields: dict) -> dict | None:
    """Refuse a label its field's picklist does not have, naming the ones it
    does. Live, an unattended close staged closureReason "Benign" (the alert
    picklist has "False Positive"); the card was approved, the write was
    refused, and the alert stayed open. Caught here, the model picks a real
    value before anyone is asked to approve. Labels match case-insensitively,
    as the write resolves them; an IRI or an empty value passes. Fails open
    when the field or its picklist cannot be read."""
    if client is None or not isinstance(fields, dict):
        return None
    attrs = _module_attrs(client, module)
    for field, raw in fields.items():
        label = raw.get("itemValue") if isinstance(raw, dict) else raw
        if not isinstance(label, str) or not label.strip() or label.startswith("/api/"):
            continue
        picklist = _field_picklist(attrs.get(field) or {})
        if not picklist:
            continue
        valid = [str(i["itemValue"]) for i in _picklist_items(client, picklist)]
        if valid and label.strip().lower() not in {v.strip().lower() for v in valid}:
            return tool_err(
                "bad_picklist_value",
                f"{field!r} takes a value from the {picklist!r} picklist; {label!r} "
                f"is not one of them. Valid values: {', '.join(valid)}.",
                field=field, picklist=picklist, valid_values=valid, module=module)
    return None


def _is_link(v: Any) -> bool:
    """A relation value (an IRI or a read tool's {iri|@id} stub), or a list of them."""
    if isinstance(v, list):
        return bool(v) and all(_is_link(x) for x in v)
    if isinstance(v, dict):
        return any(isinstance(v.get(k), str) and v[k].startswith("/api/") for k in ("iri", "@id"))
    return isinstance(v, str) and v.startswith("/api/")


def _link_value(v: Any) -> Any:
    """A relation as FortiSOAR takes it: the IRI string.

    Models copy the `{iri, uuid, label}` shape the read tools hand back and
    write `{"iri": "/api/3/..."}` (or `{"@id": ...}`) as a field value. On a box
    the record then lands unlinked. The meaning is unambiguous, so the write
    takes the IRI rather than refusing.
    """
    if isinstance(v, list):
        return [_link_value(x) for x in v]
    if isinstance(v, dict):
        for k in ("iri", "@id"):
            iri = v.get(k)
            if isinstance(iri, str) and iri.startswith("/api/"):
                return iri
    return v


def _link_fields(fields: dict) -> dict:
    return {k: _link_value(v) for k, v in fields.items()}


# The platform's refusal of a picklist field names both the field and its
# picklist: 'The "outputType" field is required to have a value from the
# "ztpfOutputType" picklist.' Quotes may arrive escaped inside a JSON string.
_PICKLIST_REFUSAL = re.compile(
    r'The \\?"(?P<field>[A-Za-z0-9_]+)\\?" field is required to have a value '
    r'from the \\?"(?P<picklist>[^"\\]+)\\?" picklist')
_PICKLIST_RETRIES = 4


def _picklist_items(client: Any, name: str) -> list[dict]:
    """``[{itemValue, iri}]`` of picklist ``name``, read live from the box."""
    from urllib.parse import quote
    r = _request("get", client, f"{client.base_url}/api/3/picklist_names"
                 f"?name={quote(name)}&$relationships=true&$limit=1")
    if getattr(r, "status_code", None) != 200:
        return []
    members = (r.json() or {}).get("hydra:member") or []
    items = (members[0].get("picklists") if members else None) or []
    return [{"itemValue": i.get("itemValue"), "iri": i.get("@id")}
            for i in items if isinstance(i, dict) and i.get("itemValue") and i.get("@id")]


def _picklist_fix(client: Any, r: Any, body: dict) -> dict | None:
    """When ``r`` is the platform refusing a picklist field, the fix.

    Live, a template create sent ``outputType: "Text"``; the field takes the
    picklist item's IRI, and the write failed. The refusal names the picklist,
    so the label is looked up there. Returns None when ``r`` is some other
    response, ``{hit: True, field, iri, value}`` when the value is one of the
    picklist's labels, else ``{hit: False, field, picklist, value, valid_values}``.
    """
    if getattr(r, "status_code", None) != 400:
        return None
    m = _PICKLIST_REFUSAL.search(getattr(r, "text", "") or "")
    if not m:
        return None
    field, picklist = m.group("field"), m.group("picklist")
    raw = body.get(field)
    label = raw.get("itemValue") if isinstance(raw, dict) else raw
    items = _picklist_items(client, picklist)
    hit = next((i for i in items if isinstance(label, str)
                and i["itemValue"].strip().lower() == label.strip().lower()), None)
    if hit and hit["iri"] != raw:
        return {"hit": True, "field": field, "iri": hit["iri"], "value": hit["itemValue"]}
    return {"hit": False, "field": field, "picklist": picklist, "value": raw,
            "valid_values": [i["itemValue"] for i in items]}


def _write(method: str, client: Any, url: str, module: str, verb: str,
           fields: dict) -> dict:
    """POST/PUT ``fields``, resolving any picklist label the platform refuses
    (one refusal names one field, so a few rounds at most)."""
    try:
        refused = (_unknown_fields(client, module, fields)
                   or _structured_into_text(client, module, fields))
    except Exception:  # noqa: BLE001 -- a failed type lookup must not block the write
        refused = None
    if refused is not None:
        return refused
    body = _link_fields(fields)
    resolved: dict[str, str] = {}
    for _ in range(_PICKLIST_RETRIES):
        try:
            r = _request(method, client, url, json=body)
        except Exception as exc:  # noqa: BLE001
            return tool_err("transport_error", f"{method.upper()} {url} failed: {exc}", url=url)
        try:
            fix = _picklist_fix(client, r, body)
        except Exception:  # noqa: BLE001 -- a failed lookup reports the original refusal
            fix = None
        if fix is None:
            break
        if not fix["hit"]:
            valid = fix["valid_values"]
            return tool_err(
                "bad_picklist_value",
                f"{fix['field']!r} takes a value from the {fix['picklist']!r} picklist"
                + (f"; {fix['value']!r} is not one of them" if fix["value"] is not None else
                   " and none was given")
                + (f". Valid values: {', '.join(map(str, valid))}." if valid else "."),
                field=fix["field"], picklist=fix["picklist"], valid_values=valid,
                url=url, module=module)
        body = {**body, fix["field"]: fix["iri"]}
        resolved[fix["field"]] = fix["value"]
    out = _result(r, url, module, verb)
    if resolved and out.get("ok"):
        out["resolved_picklists"] = resolved
    return out


def _result(r: Any, url: str, module: str, verb: str) -> dict:
    """Shape a crudhub/pyfsr write response into the tool's flat result dict."""
    status = getattr(r, "status_code", None)
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        body = None
    if status not in (200, 201):
        msg = ""
        if isinstance(body, dict):
            msg = body.get("error") or body.get("message") or ""
        if not msg:
            msg = (getattr(r, "text", "") or f"HTTP {status}")[:500]
        return tool_err(f"http_{status}", msg, url=url, module=module)
    rec = body if isinstance(body, dict) else {}
    return {
        "ok": True, "module": module, "action": verb,
        "iri": rec.get("@id"),
        "uuid": rec.get("uuid") or rec.get("id"),
        "id": rec.get("id"),
        "record": rec,
        "url": url,
    }


@mcp.tool()
def create_record(module: str = "", fields: dict | None = None) -> dict[str, Any]:
    """Create one FortiSOAR record in ``module`` with the given ``fields``.

    An approval-carded write the host's write policy must permit (in the SOC
    assistant: the active persona lists ``module`` in its ``may_write`` scope);
    the call is then surfaced to the analyst as an approval card before
    anything is written.

    Args:
      module: bare module name to create in (e.g. ``ztpf_templates``).
      fields: a JSON object of field -> value for the new record. FortiSOAR
        applies module defaults for any field omitted.

    Returns: ``{ok, module, action, iri, uuid, record, url}`` on success, else
      ``{ok: false, code, message}`` -- including ``write_not_permitted`` when the
      write policy does not cover ``module``.
    """
    if not module or not isinstance(module, str):
        return tool_err("missing_module",
                        "create_record requires a non-empty module name")
    if not isinstance(fields, dict) or not fields:
        return tool_err("missing_fields",
                        "create_record requires a non-empty fields object")
    gate = _shared.record_write_gate(module)
    if gate is not None:
        return gate
    client = _shared._live_client()
    if client is None:
        return tool_err("no_fsr_configured",
                        "no FSR instance is configured for record writes")
    url = f"{client.base_url}/api/3/{module}"
    return _write("post", client, url, module, "create", fields)


@mcp.tool()
def update_record(module: str = "", uuid: str = "",
                  fields: dict | None = None) -> dict[str, Any]:
    """Update fields on one FortiSOAR record (``PUT /api/3/<module>/<uuid>``).

    An approval-carded write -- same guards as ``create_record``. Only the
    supplied ``fields`` are changed; omitted fields are left as-is.

    Args:
      module: bare module name the record lives in (e.g. ``ztpf_templates``).
      uuid: the record's UUID (not the per-module sequential ``id``).
      fields: a JSON object of field -> new value.

    Returns: ``{ok, module, action, iri, uuid, record, url}`` on success, else
      ``{ok: false, code, message}`` (``write_not_permitted`` when out of scope).
    """
    if not module or not isinstance(module, str):
        return tool_err("missing_module",
                        "update_record requires a non-empty module name")
    if not uuid or not isinstance(uuid, str):
        return tool_err("missing_uuid",
                        "update_record requires the record uuid")
    if not isinstance(fields, dict) or not fields:
        return tool_err("missing_fields",
                        "update_record requires a non-empty fields object")
    gate = _shared.record_write_gate(module)
    if gate is not None:
        return gate
    client = _shared._live_client()
    if client is None:
        return tool_err("no_fsr_configured",
                        "no FSR instance is configured for record writes")
    url = f"{client.base_url}/api/3/{module}/{uuid}"
    return _write("put", client, url, module, "update", fields)
