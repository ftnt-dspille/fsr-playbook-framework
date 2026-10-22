"""Why a playbook run failed: the one implementation.

The failing step and its error message come only from the run's step-detail
fetch (pyfsr ``playbooks.run_failure(pk)``) or pyfsr's by-name projection
(``playbooks.why_failed(playbook=...)``); the run LIST row's ``error_message``
is always empty. ``run_playbook``'s failure detail, ``why_did_playbook_fail``'s
enrichment and the ``debug_run`` workflow all read it through here.
"""
from __future__ import annotations

from typing import Any


def _field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _plain(obj: Any) -> Any:
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:  # noqa: BLE001
            pass
    return obj


def failure_of(playbooks: Any, *, pk: str | None = None,
               playbook: str | None = None) -> dict[str, Any] | None:
    """``{failing_step, error_message, status, pk}`` for a failed run, or
    ``None`` when nothing is known. ``pk`` reads that run; ``playbook`` reads
    the playbook's most recent run. Best effort: any error is ``None``, because
    a diagnosis is a bonus on top of an already-reported failure."""
    if playbooks is None or not (pk or playbook):
        return None
    try:
        raw = (playbooks.run_failure(str(pk)) if pk
               else playbooks.why_failed(playbook=playbook))
    except Exception:  # noqa: BLE001
        return None
    raw = _plain(raw)
    if raw is None:
        return None
    step = _field(raw, "failing_step")
    msg = _field(raw, "error_message")
    status = _field(raw, "status")
    if not (step or msg or status):
        return None
    run_pk = pk or _field(raw, "pk") or _field(raw, "run_pk")
    return {"failing_step": step, "error_message": msg, "status": status,
            "pk": str(run_pk) if run_pk else None}


def run_pk_of(run: Any) -> str | None:
    """A run's pk from its ``pk`` or the tail of its ``@id``."""
    if not isinstance(run, dict):
        return None
    pk = run.get("pk")
    if pk:
        return str(pk)
    at = run.get("@id")
    if at:
        parts = [p for p in str(at).split("/") if p]
        return parts[-1] if parts else None
    return None
