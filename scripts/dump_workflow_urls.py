"""Dump every URL pattern registered with the workflow service's Django app.

The PHP API service handles `/api/3/*` reads, but workflow collection
imports/triggers/exports live on the Python workflow service
(/opt/cyops-workflow/sealab, gunicorn). Its routes don't show up in
`php bin/console debug:router`. This script asks Django directly.

USAGE on the FSR appliance:
    sudo /opt/cyops-workflow/.env/bin/python /tmp/dump_workflow_urls.py
    cat /tmp/workflow_urls.log

Output: every URL pattern + the view callable that handles it. We're
hunting for routes containing 'import', 'collection', 'trigger',
'export'. The view qualname tells us which controller class handles
uniqueness/validation — that's where the constraint rules live.
"""
from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sealab.settings")
sys.path.insert(0, "/opt/cyops-workflow/sealab")

import django  # noqa: E402
django.setup()

from django.urls import get_resolver  # noqa: E402


def _qual(cb) -> str:
    if cb is None:
        return "?"
    qn = getattr(cb, "__qualname__", None) or getattr(cb, "__name__", None) or repr(cb)
    mod = getattr(cb, "__module__", "?")
    return f"{mod}.{qn}"


def _walk(resolver, prefix: str = "") -> list[tuple[str, str, list[str]]]:
    out: list[tuple[str, str, list[str]]] = []
    for p in getattr(resolver, "url_patterns", []):
        pat = str(getattr(p, "pattern", p))
        if hasattr(p, "url_patterns"):
            out += _walk(p, prefix + pat)
        else:
            methods: list[str] = []
            cb = getattr(p, "callback", None)
            cls = getattr(cb, "view_class", None) or getattr(cb, "cls", None)
            if cls is not None:
                methods = sorted(set(
                    m.upper() for m in (
                        "get", "post", "put", "patch", "delete", "head", "options"
                    ) if hasattr(cls, m)
                ))
            out.append((prefix + pat, _qual(cb), methods))
    return out


def main() -> int:
    out_path = os.environ.get("URLS_OUT", "/tmp/workflow_urls.log")
    rows = _walk(get_resolver())
    with open(out_path, "w") as f:
        for path, view, methods in rows:
            line = f"{','.join(methods) or '?':<25} {path:<60}  {view}"
            f.write(line + "\n")
    print(f"wrote {len(rows)} routes to {out_path}", file=sys.stderr)

    # Also surface the highlight reel directly to stderr so the user sees
    # the candidates without needing to grep.
    print("\n=== candidates: import / collection / trigger / export ===",
          file=sys.stderr)
    rx = re.compile(r"import|collection|trigger|export|workflow|playbook", re.I)
    for path, view, methods in rows:
        if rx.search(path) or rx.search(view):
            print(f"  {','.join(methods) or '?':<20} {path:<60}  {view}",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
