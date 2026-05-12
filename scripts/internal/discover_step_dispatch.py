"""Discover the step-type → handler dispatch in cyops-workflow.

The workflow package is shipped as Cython .so files, so source grep returns
nothing. But the modules import fine and we can introspect at runtime.

Goal: find the registry (dict / lookup) that maps step type names like
'Connector', 'Decision', 'SetVariable' to their handler callables/classes.

USAGE on the FSR appliance:
    sudo /opt/cyops-workflow/.env/bin/python /tmp/discover_step_dispatch.py

Output goes to /tmp/dispatch.json + /tmp/dispatch.log.
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

# Step type names we KNOW exist (from /api/3/workflow_step_types/). Finding any
# of these as keys in a dict, or as class names, is a strong dispatcher signal.
KNOWN_STEP_TYPES = {
    "Connector", "Decision", "SetVariable", "UpdateRecord", "FindRecord",
    "ExecuteCondition", "ManualInput", "Trigger", "Reference", "RestApi",
    "EvaluateExpression", "DownloadFile", "UploadFile", "Notify", "Approval",
    "ParallelExecution", "ManualTask", "RunScript", "AwaitForUserInput",
    "JoinSteps", "DBOperation", "WorkflowReference",
}

MODULES_TO_PROBE = [
    "workflow.eval",
    "workflow.tasks",
    "workflow.constants",
    "workflow.helper",
    "workflow.utility",
    "workflow.environment",
    "workflow.builtins",
    "workflow.builtins.convert",
    "workflow.builtins.crudhub",
    "workflow.builtins.db",
    "workflow.builtins.files",
    "workflow.builtins.http",
    "workflow.builtins.misc",
    "workflow.builtins.notify",
    "workflow.builtins.soap",
    "workflow.builtins.ssh",
    "workflow.builtins.wait",
    "workflow.contrib",
    "workflow.contrib.vault",
]


def _safe_import(modname: str):
    try:
        return __import__(modname, fromlist=["*"])
    except Exception as e:  # noqa: BLE001
        return f"<import_error: {type(e).__name__}: {e}>"


def _probe_module(modname: str) -> dict:
    mod = _safe_import(modname)
    if isinstance(mod, str):
        return {"error": mod}

    info: dict = {"file": getattr(mod, "__file__", None), "members": {}}
    for name in dir(mod):
        if name.startswith("_"):
            continue
        try:
            v = getattr(mod, name)
        except Exception:
            continue
        t = type(v).__name__
        entry: dict = {"type": t}

        if isinstance(v, dict):
            entry["len"] = len(v)
            keys = list(v.keys())[:50]
            entry["keys_sample"] = [str(k)[:80] for k in keys]
            entry["matches_step_types"] = sorted(
                set(str(k) for k in v.keys()) & KNOWN_STEP_TYPES
            )
            # If keys look like step-type names, capture value summary too
            if entry["matches_step_types"]:
                entry["value_types"] = sorted({type(x).__name__ for x in v.values()})
        elif isinstance(v, (list, tuple, set, frozenset)):
            entry["len"] = len(v)
            entry["sample"] = [str(x)[:80] for x in list(v)[:20]]
        elif inspect.isclass(v):
            entry["qualname"] = getattr(v, "__qualname__", name)
            entry["mro"] = [c.__name__ for c in v.__mro__][:6]
            entry["matches_step_type"] = name in KNOWN_STEP_TYPES
            try:
                entry["file"] = inspect.getsourcefile(v)
            except TypeError:
                entry["file"] = None
            # Methods that look like step handlers
            handler_methods = []
            for m in ("run", "execute", "process", "handle", "evaluate", "__call__"):
                fn = getattr(v, m, None)
                if callable(fn):
                    try:
                        handler_methods.append(f"{m}{inspect.signature(fn)}")
                    except (ValueError, TypeError):
                        handler_methods.append(f"{m}(?)")
            if handler_methods:
                entry["handler_methods"] = handler_methods
        elif callable(v):
            try:
                entry["signature"] = str(inspect.signature(v))
            except (ValueError, TypeError):
                entry["signature"] = "?"
        else:
            # Plain values — show the repr if cheap
            r = repr(v)
            if len(r) <= 200:
                entry["repr"] = r

        info["members"][name] = entry
    return info


def main() -> int:
    out_path = os.environ.get("DISPATCH_OUT", "/tmp/dispatch.json")
    log_path = os.environ.get("DISPATCH_LOG", "/tmp/dispatch.log")
    log_fh = open(log_path, "w")

    def log(*args):
        msg = " ".join(str(a) for a in args)
        print(msg, file=sys.stderr, flush=True)
        log_fh.write(msg + "\n")
        log_fh.flush()

    log(f"django {django.get_version()} app context up")

    out: dict = {"schema_version": 1, "modules": {}, "summary": {}}

    interesting_dicts = []
    interesting_classes = []

    for modname in MODULES_TO_PROBE:
        log(f"probing {modname} ...")
        info = _probe_module(modname)
        if "error" in info:
            log(f"  {info['error']}")
            out["modules"][modname] = info
            continue
        out["modules"][modname] = info
        for n, e in info["members"].items():
            if e.get("matches_step_types"):
                interesting_dicts.append((modname, n, e["matches_step_types"]))
            if e.get("matches_step_type"):
                interesting_classes.append((modname, n))
        log(f"  {len(info['members'])} members")

    out["summary"]["dicts_with_step_type_keys"] = [
        {"module": m, "name": n, "matches": k} for m, n, k in interesting_dicts
    ]
    out["summary"]["classes_named_after_step_types"] = [
        {"module": m, "name": n} for m, n in interesting_classes
    ]

    log(f"\n=== {len(interesting_dicts)} dicts with step-type keys ===")
    for m, n, k in interesting_dicts:
        log(f"  {m}.{n} -> {k}")
    log(f"\n=== {len(interesting_classes)} classes named after step types ===")
    for m, n in interesting_classes:
        log(f"  {m}.{n}")

    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"\nwrote {os.path.getsize(out_path)} bytes to {out_path}")
    log_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
