"""Introspect every callable in workflow.eval.FUNCTION_MAP.

This is the canonical step-handler registry. Each step type's
`args_schema_json.script` ends with one of these keys, e.g.
  Decision     -> cond
  SetVariable  -> set_multiple
  Connector    -> connector

USAGE on the FSR appliance:
    sudo /opt/cyops-workflow/.env/bin/python /tmp/dump_function_map.py
    scp root@fsr:/tmp/function_map.json ./store/incoming/

Captures per entry: signature, parameters w/ kinds & defaults,
docstring, source file (where available — many will be Cython .so
which Python introspection still signatures via __text_signature__).
"""
from __future__ import annotations

import inspect
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sealab.settings")
sys.path.insert(0, "/opt/cyops-workflow/sealab")

import django  # noqa: E402
django.setup()

from workflow.eval import FUNCTION_MAP  # noqa: E402


def _describe(fn) -> dict:
    info: dict = {
        "qualname": getattr(fn, "__qualname__", repr(fn)),
        "module": getattr(fn, "__module__", None),
        "doc": inspect.getdoc(fn),
        "type": type(fn).__name__,
    }
    try:
        info["file"] = inspect.getsourcefile(fn)
    except TypeError:
        info["file"] = None
    try:
        sig = inspect.signature(fn)
        info["signature"] = str(sig)
        info["parameters"] = [
            {
                "name": p.name,
                "kind": p.kind.name,
                "default": None if p.default is p.empty else repr(p.default),
                "annotation": None if p.annotation is p.empty else str(p.annotation),
            }
            for p in sig.parameters.values()
        ]
    except (ValueError, TypeError) as e:
        info["signature_error"] = str(e)
        # Try __text_signature__ for Cython callables
        info["text_signature"] = getattr(fn, "__text_signature__", None)
    return info


def main() -> int:
    out_path = os.environ.get("DUMP_OUT", "/tmp/function_map.json")
    log_path = os.environ.get("DUMP_LOG", "/tmp/function_map.log")
    log_fh = open(log_path, "w")

    def log(*args):
        msg = " ".join(str(a) for a in args)
        print(msg, file=sys.stderr, flush=True)
        log_fh.write(msg + "\n")
        log_fh.flush()

    log(f"FUNCTION_MAP has {len(FUNCTION_MAP)} entries")
    out: dict = {"schema_version": 1, "function_map": {}}
    for name, fn in FUNCTION_MAP.items():
        out["function_map"][name] = _describe(fn)
        sig = out["function_map"][name].get("signature") or out["function_map"][name].get("signature_error", "?")
        log(f"  {name}: {sig}")

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"\nwrote {os.path.getsize(out_path)} bytes to {out_path}")
    log_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
