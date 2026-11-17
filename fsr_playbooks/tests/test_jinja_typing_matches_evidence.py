"""The compiler's hand-curated filter output types must not contradict the live
evidence in jinja_filter_probes (the proof captured by `make jinja-probe`).

This catches the class of bug we shipped with: resolveRange declared "object"
when it returns the mapped value or None, and picklist declared "string" when
it returns the whole item dict. A declared type that the box never produces is
wrong by construction.
"""
from __future__ import annotations

import sqlite3

import pytest

from fsr_playbooks._db import default_db_path

# compiler FSR vocab -> the Python type names type_debug reports. Markup is a
# str subclass; generator/combinations/… are the lazy form of "list".
_FSR_TO_PY = {
    "string": {"str", "Markup"},
    "integer": {"int"},
    "number": {"float", "int"},
    "boolean": {"bool", "NoneType"},
    "list": {"list", "generator", "combinations", "permutations", "product", "map", "zip"},
    "object": {"dict"},
}


def _hand_curated() -> dict[str, str]:
    from fsr_playbooks.compiler import jinja_typing

    out = {}
    for name, (_in, _out) in jinja_typing._HAND_CURATED.items():
        if _out:
            out[name] = _out
    return out


def _evidence() -> dict[str, set[str]]:
    db = default_db_path()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT filter_name, output_type FROM jinja_filter_probes "
            "WHERE ok=1 AND output_type IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        return {}
    ev: dict[str, set[str]] = {}
    for name, ot in rows:
        ev.setdefault(name, set()).add(ot)
    return ev


_EV = _evidence()


@pytest.mark.skipif(not _EV, reason="no jinja_filter_probes evidence in the slim DB")
@pytest.mark.parametrize("name,declared", sorted(_hand_curated().items()))
def test_declared_output_type_is_observed(name, declared):
    observed = _EV.get(name)
    if not observed:
        pytest.skip(f"no live evidence for {name}")
    # A filter that returns None on a miss/bad input (most FSR filters do) does
    # not thereby contradict its declared type for good input.
    observed = observed - {"NoneType"} or observed
    allowed = _FSR_TO_PY.get(declared, set()) | {"NoneType"}
    assert observed & allowed, (
        f"{name}: compiler declares output '{declared}' ({allowed}), but the box only "
        f"ever returned {sorted(observed)} -- update _HAND_CURATED or re-probe")
