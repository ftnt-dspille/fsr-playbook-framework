"""Dump every workflow-step-handler registered in cyops-workflow's celery app.

Background: FortiSOAR's workflow service runs as a Django app whose step
handlers are celery tasks (`-A sealab worker`). The /api/3/workflow_step_types/
endpoint catalogs the 43 step types but only exposes a partial `arguments`
blob — no per-arg type info. To get the canonical argument schema we
introspect the actual celery task callables via `inspect.signature`.

USAGE — on the FortiSOAR appliance, as root:

    scp dump_step_types.py root@fsr:/tmp/
    sudo /opt/cyops-workflow/.env/bin/python /tmp/dump_step_types.py
    cat /tmp/step_types.log
    scp root@fsr:/tmp/step_types.json ./data/incoming/step_types.json

What it captures, per task:
  - task name (celery name, often dotted: workflow.tasks.connector)
  - module + source file
  - signature(s) — task callable, optional `run` method (Class-based tasks)
  - parameters with kind / default / annotation
  - task class qualname (Class-based) or function qualname (function-based)
  - docstring

The script is silent on missing optional modules; if it reports zero tasks
or no candidates, see EXTRA_IMPORTS below.
"""
from __future__ import annotations

import gc
import inspect
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sealab.settings")
sys.path.insert(0, "/opt/cyops-workflow/sealab")

# Modules likely to contain workflow-step task definitions. Most should
# import as side-effects of django.setup() but we eager-load common ones
# in case the celery autodiscovery hasn't run yet at script time.
EXTRA_IMPORTS = (
    "sealab.workflow.tasks",
    "sealab.workflow.tasks.connector",
    "sealab.workflow.tasks.action",
    "sealab.workflow.tasks.decision",
    "sealab.workflow.tasks.set_variable",
    "sealab.workflow.tasks.update_record",
    "sealab.workflow.tasks.workflow_reference",
    "sealab.workflow.tasks.utility",
    "sealab.workflow.tasks.utilities",
    "sealab.workflow.tasks.trigger",
    "sealab.workflow.tasks.manual_input",
    "sealab.workflow.cybersponse",
    "sealab.cybersponse",
    "workflow.tasks",
)


def _setup_django():
    import django
    django.setup()
    print(f"django {django.get_version()} app context up", file=sys.stderr)


def _eager_imports():
    for mod in EXTRA_IMPORTS:
        try:
            __import__(mod)
            print(f"  imported {mod}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {mod}: {type(e).__name__}", file=sys.stderr)


def _describe_callable(fn) -> dict:
    info = {
        "qualname": getattr(fn, "__qualname__", repr(fn)),
        "module": getattr(fn, "__module__", None),
        "doc": inspect.getdoc(fn),
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
    return info


def _collect_celery_tasks() -> dict:
    """Pull every task out of the running celery app's registry."""
    from celery import current_app
    out: dict = {}
    for name, task in current_app.tasks.items():
        # Filter to workflow-namespaced tasks; the celery registry also
        # contains framework internals (celery.chord, celery.chunks, etc.)
        # that aren't step handlers.
        is_workflow = (
            name.startswith("workflow.")
            or name.startswith("sealab.")
            or "workflow" in (task.__module__ or "").lower()
            or "sealab" in (task.__module__ or "").lower()
        )
        if not is_workflow:
            continue

        entry: dict = {"task_name": name, "module": task.__module__}

        # Class-based tasks expose `run`; function-based tasks have the
        # function as task.run too (celery wraps them). Either way, run is
        # the canonical entry point.
        run = getattr(task, "run", None)
        if callable(run):
            entry["run"] = _describe_callable(run)

        # The task object itself may have a useful __call__ signature if
        # it's a Task subclass with overridden __call__.
        call = getattr(task, "__call__", None)
        if callable(call):
            try:
                entry["task_signature"] = str(inspect.signature(call))
            except (ValueError, TypeError):
                pass

        # Class hierarchy is informative — Step / WorkflowTask base classes
        # tell us which abstract category the task belongs to.
        try:
            entry["mro"] = [c.__qualname__ for c in type(task).__mro__]
        except Exception:
            entry["mro"] = []

        out[name] = entry
    return out


def _gc_walk_step_classes() -> dict:
    """Fallback: walk gc for classes whose name suggests they're step handlers.

    Useful when celery task discovery misses class-based steps that aren't
    registered as celery tasks (some FSR step types may handle differently).
    """
    candidates: dict = {}
    for obj in gc.get_objects():
        if not inspect.isclass(obj):
            continue
        mod = getattr(obj, "__module__", "") or ""
        if not isinstance(mod, str):
            continue
        if not (mod.startswith("workflow.") or mod.startswith("sealab.")):
            continue
        qual = getattr(obj, "__qualname__", "")
        # Heuristic: classes named *Step, *Task, *Action, *Trigger
        if not any(qual.endswith(suffix) for suffix in ("Step", "Task", "Action", "Trigger", "Handler")):
            continue
        try:
            entry: dict = {"qualname": qual, "module": mod}
            try:
                entry["file"] = inspect.getsourcefile(obj)
            except TypeError:
                entry["file"] = None
            entry["mro"] = [c.__qualname__ for c in obj.__mro__]
            for method_name in ("run", "execute", "__init__", "validate_arguments"):
                m = getattr(obj, method_name, None)
                if callable(m):
                    entry[method_name] = _describe_callable(m)
            candidates[f"{mod}.{qual}"] = entry
        except Exception as e:  # noqa: BLE001
            candidates[f"{mod}.{qual}"] = {"introspect_error": repr(e)}
    return candidates


def main() -> int:
    out_path = os.environ.get("DUMP_OUT", "/tmp/step_types.json")
    log_path = os.environ.get("DUMP_LOG", "/tmp/step_types.log")
    log_fh = open(log_path, "w") if log_path else None

    def log(*args):
        msg = " ".join(str(a) for a in args)
        print(msg, file=sys.stderr, flush=True)
        if log_fh:
            log_fh.write(msg + "\n")
            log_fh.flush()

    _setup_django()
    _eager_imports()

    log("collecting celery tasks ...")
    tasks = _collect_celery_tasks()
    log(f"  {len(tasks)} workflow celery tasks captured")

    log("walking gc for class-based step handlers ...")
    classes = _gc_walk_step_classes()
    log(f"  {len(classes)} candidate step-handler classes")

    out = {
        "schema_version": 1,
        "celery_tasks": tasks,
        "step_classes": classes,
    }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
        f.write("\n")
    size = os.path.getsize(out_path)
    log(f"wrote {size} bytes to {out_path}")
    if log_fh:
        log_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
