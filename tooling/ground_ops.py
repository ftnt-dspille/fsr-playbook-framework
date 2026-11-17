"""Ground specific connector operations into the output-shape oracle.

`ground_shapes.py` grounds every step of a whole playbook run; this grounds a
named list of connector ops directly -- run each once live, take the real
envelope ({operation, status, message, data}), and fold its SHAPE into the
persistent GroundedShapeStore. That is the recipe for growing the store toward
the ops the corpus actually leans on (see grounding_coverage.py for the ranked
gap list).

Only fixed-shape ops belong here. A passthrough op whose output depends on its
input (e.g. cyops_utilities:make_cyops_request, which returns whatever IRI you
ask for) must NOT be grounded -- a single capture would teach the oracle a shape
that does not hold for other calls. `ground_ops` grounds only ops that report
success and refuses to retain any scalar VALUE (the shape carries kind/type and
schema field names, never box data); `assert_value_free` enforces that so a
committed store leaks no provenance.

Usage (grounds the config-free, fixed-shape ops a box supports):
    FSR_ENV_FILE=.env.<box> \
      PYTHONPATH=.:tooling /path/to/pyfsr-venv/python -m ground_ops \
        --op whois-rdap:whois_ip:'{"ip":"8.8.8.8"}' \
        --op cyops_utilities:format_richtext:'{"value":"x"}'
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent.parent
STORE_PATH = REPO / "fsr_playbooks" / "_data" / "grounded_shapes.json"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

from fsr_playbooks.compiler.grounded_shapes import (  # noqa: E402
    GroundedShapeStore,
    merge_shape,
    shape_from_value,
)

# a sanitized scalar leaf carries only these structural flags -- never a
# captured value. `optional` (key absent in some observations) and `nullable`
# (null in some, typed in others) are both set by merge_shape as metadata.
_SCALAR_META = {"kind", "type", "optional", "nullable"}

# a dict KEY that matches one of these is box data wearing a schema field's
# clothes (an op that returns a map keyed by an IP / email / uuid|long-hex),
# so a committed shape built from it would leak that value as a key name.
_DATA_KEY = re.compile(
    r"^(?:\d{1,3}(?:\.\d{1,3}){3}"            # IPv4
    r"|[^@\s]+@[^@\s]+\.[^@\s]+"              # email
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"  # uuid
    r"|[0-9a-fA-F]{16,})$")                   # long hex token


def _key_looks_like_data(key: str) -> bool:
    return bool(_DATA_KEY.match(str(key).strip()))


def envelope_of(result: Any) -> dict[str, Any]:
    """A connector result as the {operation, status, message, data} envelope.
    pyfsr returns a typed ExecuteResult (pydantic), not a dict -- coerce it (the
    typed-not-dict gotcha) so the grounded shape matches what steps reference."""
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return {"operation": None, "status": "Success", "message": "", "data": result}


def assert_value_free(shape: Any, path: str = "") -> None:
    """Raise if a shape node carries anything beyond structure. Scalar leaves
    may hold only kind/type/optional; dict keys are schema field names (allowed),
    their VALUES must themselves be value-free shapes."""
    if not isinstance(shape, dict):
        raise AssertionError(f"{path or '<root>'}: non-shape node {shape!r}")
    kind = shape.get("kind")
    if kind == "scalar":
        extra = set(shape) - _SCALAR_META
        if extra:
            raise AssertionError(f"{path}: scalar carries {sorted(extra)}")
    elif kind == "list":
        assert_value_free(shape.get("item", {"kind": "scalar", "type": "any"}),
                          f"{path}[]")
    elif kind == "object":
        for k, v in (shape.get("keys") or {}).items():
            if _key_looks_like_data(k):
                raise AssertionError(f"{path}.{k}: key looks like box data")
            assert_value_free(v, f"{path}.{k}")
    # 'unknown' and other kinds carry only a reason, no value -- fine.


def run_op(client: Any, connector: str, operation: str,
           params: dict | None) -> dict[str, Any]:
    res = client.connectors.execute(connector=connector, operation=operation,
                                    params=params or {})
    return envelope_of(res)


def ground_ops(specs: list[tuple[str, str, dict]], *, store_path: Path = STORE_PATH,
               client: Any = None) -> tuple[list[dict], GroundedShapeStore]:
    """Run each (connector, operation, params) live and fold its envelope shape
    into the store. Returns a per-op report and the updated store (saved)."""
    if client is None:
        from probes._env import get_client
        client = get_client()
    if client is None:
        raise SystemExit("no live client; set FSR_ENV_FILE to a box .env")
    store = GroundedShapeStore.load(store_path)
    report: list[dict] = []
    for connector, operation, params in specs:
        key = f"{connector}:{operation}"
        try:
            env = run_op(client, connector, operation, params)
        except Exception as exc:  # noqa: BLE001
            report.append({"op": key, "result": "error", "detail": str(exc)[:200]})
            continue
        status = str(env.get("status", "")).lower()
        if status and status != "success":
            report.append({"op": key, "result": "skip",
                           "detail": env.get("message") or status})
            continue
        # Verify the shape BEFORE touching the store: observe() mutates in
        # place, so checking its return value would already have folded an
        # unsafe shape in. Compute the exact shape observe() would store
        # (measure + merge with any prior) and gate on it.
        measured = shape_from_value(env)
        prior = store.shape_for(connector, operation)
        candidate = measured if prior is None else merge_shape(prior, measured)
        try:
            assert_value_free(candidate)
        except AssertionError as exc:
            report.append({"op": key, "result": "unsafe", "detail": str(exc)})
            continue
        store.observe(connector, operation, env)  # safe: checked above
        report.append({"op": key, "result": "grounded"})
    # save only when every attempted op is accounted for and none was unsafe,
    # and at least one grounded -- an unsafe op never enters the store above,
    # but refusing to save on any 'unsafe' is the belt to that suspenders.
    if (any(r["result"] == "grounded" for r in report)
            and not any(r["result"] == "unsafe" for r in report)):
        store.save(store_path)
    return report, store


def _parse_spec(raw: str) -> tuple[str, str, dict]:
    """connector:operation[:json-params] -- the first two colons split the
    connector and operation; the remainder (if any) is a JSON params object."""
    parts = raw.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"spec must be connector:operation[:params], got {raw!r}")
    connector, operation = parts[0], parts[1]
    params = json.loads(parts[2]) if len(parts) > 2 and parts[2].strip() else {}
    return connector, operation, params


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--op", action="append", required=True,
                    help="connector:operation:'{json params}'")
    args = ap.parse_args()
    specs = [_parse_spec(o) for o in args.op]
    report, store = ground_ops(specs)
    for r in report:
        print(f"  {r['result']:9} {r['op']}" + (f"  -- {r['detail']}" if r.get("detail") else ""))
    print(f"store now has {len(store)} ops")
