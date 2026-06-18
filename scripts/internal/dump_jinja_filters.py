"""Dump every Jinja2 filter / global / test registered in the cyops-workflow env.

USAGE — on the FortiSOAR appliance, as root:

    scp dump_jinja_filters.py root@fsr:/tmp/
    sudo /opt/cyops-workflow/.env/bin/python /tmp/dump_jinja_filters.py \
        > /tmp/filters.json 2> /tmp/filters.log
    cat /tmp/filters.log
    scp root@fsr:/tmp/filters.json ./data/incoming/filters.json

The script:
  1. Boots Django (DJANGO_SETTINGS_MODULE=sealab.settings) so registered apps
     and any module-level Environment construction has run.
  2. Tries to import a handful of likely jinja-setup modules (silent on miss).
  3. Walks gc for jinja2.Environment instances + checks Django TEMPLATES.
  4. Picks the env with the most filters (the workflow one, not stock Django).
  5. Dumps name + qualname + module + file + docstring + signature + parameters
     for every entry in env.filters, env.globals, env.tests.

If the script reports "no jinja2.Environment objects in memory" it means the
env is built lazily per render. In that case:
    grep -rln "jinja2" /opt/cyops-workflow/sealab/
to find the module that creates it, then add that module path to the
EXTRA_IMPORTS list below and rerun.

Output is JSON on stdout; log/diagnostics on stderr.
"""
from __future__ import annotations

import gc
import inspect
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sealab.settings")
sys.path.insert(0, "/opt/cyops-workflow/sealab")

# Edit these if the gc walk comes up empty — common alternatives are listed.
EXTRA_IMPORTS = (
    "sealab.utils.jinja",
    "sealab.jinja",
    "sealab.workflow.jinja",
    "sealab.dynamic_value",
    "sealab.dynamic_values",
    "sealab.template",
    "sealab.workflow.template",
    "sealab.api.jinja_editor",
    "sealab.workflow.template_engine",
)


def _setup_django() -> None:
    import django
    django.setup()
    print(f"django {django.get_version()} app context up", file=sys.stderr)


def _eager_imports() -> None:
    for mod in EXTRA_IMPORTS:
        try:
            __import__(mod)
            print(f"imported {mod}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 — silent miss is the design
            # Print only the type to keep the log small; many of these will miss.
            print(f"  skip {mod}: {type(e).__name__}", file=sys.stderr)


def _collect_envs():
    import jinja2
    envs = [o for o in gc.get_objects() if isinstance(o, jinja2.Environment)]
    try:
        from django.template import engines
        for name in engines:
            inner = getattr(engines[name], "env", None)
            if isinstance(inner, jinja2.Environment):
                envs.append(inner)
                print(f"  + Django engine '{name}' → env", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"  django.template.engines lookup failed: {e!r}", file=sys.stderr)
    return list({id(e): e for e in envs}.values())


def _describe(fn) -> dict:
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


def main() -> int:
    _setup_django()
    _eager_imports()

    envs = _collect_envs()
    print(f"found {len(envs)} Environment instance(s)", file=sys.stderr)
    if not envs:
        sys.stderr.write(
            "no jinja2.Environment objects in memory — env may be built "
            "per-call. grep /opt/cyops-workflow/sealab for 'jinja2' to find "
            "the constructing module and add it to EXTRA_IMPORTS.\n"
        )
        return 2

    env = max(envs, key=lambda e: len(e.filters))
    print(
        f"using env with {len(env.filters)} filters, "
        f"{len(env.globals)} globals, {len(env.tests)} tests",
        file=sys.stderr,
    )

    out_path = os.environ.get("DUMP_OUT", "/tmp/filters.json")
    out: dict = {"filters": {}, "globals": {}, "tests": {}, "schema_version": 1}
    for bucket in ("filters", "globals", "tests"):
        registry = getattr(env, bucket)
        items = list(registry.items())
        print(f"  introspecting {len(items)} {bucket}...", file=sys.stderr, flush=True)
        for name, fn in items:
            try:
                out[bucket][name] = _describe(fn)
            except BaseException as e:  # noqa: BLE001 — catch literally anything per-entry
                out[bucket][name] = {"introspect_error": f"{type(e).__name__}: {e}"}
        print(f"    {bucket} done ({len(out[bucket])} captured)",
              file=sys.stderr, flush=True)

    # Write to file directly — avoids any sudo-redirect weirdness and lets us
    # see the byte count immediately.
    print(f"writing {out_path} ...", file=sys.stderr, flush=True)
    try:
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2, default=str)
            f.write("\n")
    except BaseException as e:  # noqa: BLE001
        print(f"WRITE FAILED: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        raise
    size = os.path.getsize(out_path)
    print(f"wrote {size} bytes to {out_path}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
