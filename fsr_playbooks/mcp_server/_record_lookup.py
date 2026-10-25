"""Record lookup helpers shared by the record, hunt and write tools.

When a model names a record that does not exist, these turn the refusal into
something it can act on: the record the conversation is on, the module's most
recent records, and a near-miss uuid when the guess was a real one copied
wrong. Pure over a live client; the active record comes from the host
(``_shared.active_record_iri``).
"""
from __future__ import annotations

import re
from typing import Any

from fsr_playbooks.mcp_server import _shared


def live_request(method: str, client: Any, url: str, **kwargs):
    """``client.session.<method>(url, **kwargs)`` with transparent re-auth."""
    return _shared.live_request_with_reauth(method, client, url, **kwargs)


def _row_label(m: dict) -> str:
    label = (m.get("name") or m.get("title") or m.get("subject")
             or m.get("displayName") or m.get("hostname")
             or m.get("description"))
    return str(label)[:120] if label else str(m.get("@id", "")).rsplit("/", 1)[-1]


def recent_records(client: Any, module: str, n: int = 5) -> list[dict[str, Any]]:
    """The ``n`` most recently modified records of ``module`` as
    ``{iri, uuid, label}`` -- the real candidates to hand a model that named a
    record that does not exist. Best effort: ``[]`` on any failure."""
    base = f"{client.base_url}"
    try:
        r = live_request("post", client, f"{base}/api/query/{module}?$limit={n}",
                         json={"sort": [{"field": "modifyDate",
                                         "direction": "DESC"}]})
        if getattr(r, "status_code", None) != 200:
            # Some modules refuse a server-side sort; any page beats none.
            r = live_request("get", client, f"{base}/api/3/{module}?$limit={n}")
        if getattr(r, "status_code", None) != 200:
            return []
        members = (r.json() or {}).get("hydra:member") or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in members[:n]:
        if isinstance(m, dict) and m.get("@id"):
            out.append({"iri": m["@id"], "uuid": m.get("uuid"),
                        "label": _row_label(m)})
    return out


def record_candidates(client: Any, module: str,
                      active_iri: str | None = None) -> list[dict[str, Any]]:
    """Real records to offer in place of an invented one: the record the
    conversation is mounted on first (when it is in ``module``), then the
    module's most recent records, de-duplicated."""
    out: list[dict[str, Any]] = []
    if active_iri and f"/api/3/{module}/" in active_iri:
        out.append({"iri": active_iri,
                    "uuid": active_iri.rstrip("/").rsplit("/", 1)[-1],
                    "label": "the record this conversation is on"})
    for c in recent_records(client, module):
        if not any(c["iri"] == k["iri"] for k in out):
            out.append(c)
    return out


# A guessed uuid is usually a real one copied wrong: on the box the model
# turned run group ...214b into ...214f and was told the run group did not
# exist. The real IRI was sitting in the record on screen.
_NEAR_UUID_MAX = 2


def _differs(a: str, b: str) -> int:
    if len(a) != len(b):
        return 99
    return sum(x != y for x, y in zip(a.lower(), b.lower()))


def near_uuid(client: Any, module: str, guess: str, active_iri: str | None,
              candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The real ``module`` record whose uuid is within two characters of
    ``guess``: from the candidates, then every ``/api/3/<module>/<uuid>`` IRI
    the record on screen carries. None when nothing is that close."""
    if not (module and guess):
        return None
    prefix = f"/api/3/{module}/"
    pool = [c["iri"] for c in candidates if str(c.get("iri", "")).startswith(prefix)]
    if client and active_iri:
        try:
            r = live_request("get", client,
                             f"{client.base_url}{active_iri}?$relationships=true")
            if getattr(r, "status_code", None) == 200:
                pool += re.findall(rf"/api/3/{re.escape(module)}/[0-9a-fA-F-]{{36}}", r.text)
        except Exception:  # noqa: BLE001 -- best effort; the refusal stands without it
            pass
    best = None
    for iri in dict.fromkeys(pool):
        real = iri.rsplit("/", 1)[-1]
        d = _differs(real, guess)
        if 0 < d <= _NEAR_UUID_MAX and (best is None or d < best[0]):
            best = (d, iri, real)
    if best is None:
        return None
    return {"iri": best[1], "uuid": best[2], "differs_by": best[0]}


def did_you_mean_text(near: dict[str, Any]) -> str:
    return (f" Did you mean {near['iri']}? It differs from the uuid you sent by "
            f"{near['differs_by']} character(s): copy it exactly.")


def unknown_record(client: Any, module: str, uuid: str,
                   *, active_iri: str | None = None,
                   nothing_ran: bool = True) -> dict[str, Any] | None:
    """``None`` when ``/api/3/<module>/<uuid>`` exists OR existence could not be
    established; else an ``unknown_record`` refusal naming real candidates.

    HARDEN-4 (invented identifiers): a made-up record uuid used to reach the
    analyst as an approval card, or come back as a bare "no record at ...", and
    the model's next move was another guess. The candidates -- the record the
    conversation is mounted on, then the module's most recent records -- turn
    the refusal into something it can act on. Refuses ONLY on a clean 404: a
    blinking box must never read as "no such record".
    """
    if not (client and module and uuid):
        return None
    try:
        r = live_request("get", client,
                         f"{client.base_url}/api/3/{module}/{uuid}")
    except Exception:  # noqa: BLE001
        return None
    if getattr(r, "status_code", None) != 404:
        return None
    candidates = record_candidates(client, module, active_iri)
    near = near_uuid(client, module, uuid, active_iri, candidates)
    msg = (f"no {module} record has uuid {uuid!r}"
           + (" -- nothing was run and no approval was requested" if nothing_ran
              else "")
           + ". Do NOT retry with a guessed uuid: use one of `candidates`, or "
           f"find the record with search_module_records(module={module!r}, "
           "q=...). A record's display id (#123) is not its uuid.")
    out: dict[str, Any] = {"ok": False, "code": "unknown_record",
           "module": module, "uuid": uuid, "message": msg,
           "candidates": candidates}
    if near:
        out["message"] += did_you_mean_text(near)
        out["did_you_mean"] = near
    return out
