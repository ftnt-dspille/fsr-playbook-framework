"""Console-script entry point for the `fsrpb` CLI.

The CLI implementation lives in `tooling/cli.py`, which imports its sibling
modules (`recover.py`, `picklists.py`, `agent/`, `catalog/`, ...) as top-level
modules. The `[project.scripts]` wrapper runs from an arbitrary cwd, so this
shim puts that directory on sys.path, then hands off to `cli.main`:

- source checkout (editable install, or `python fsrpb_main.py`): the
  `tooling/` directory next to this file;
- wheel or git install: the same files, shipped as package data of the
  `fsrpb_tooling` package (pyproject maps it to `tooling/`).

Keep this module dependency-free and tiny.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def _tooling_dir() -> str:
    checkout = os.path.join(_REPO_ROOT, "tooling")
    if os.path.isfile(os.path.join(checkout, "cli.py")):
        return checkout
    import importlib.util

    spec = importlib.util.find_spec("fsrpb_tooling")
    if spec is not None and spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            if os.path.isfile(os.path.join(location, "cli.py")):
                return location
    raise SystemExit(
        "fsrpb: cannot find the CLI modules (tooling/cli.py). Reinstall fsrpb, "
        "or run it from a fsr-playbook-framework checkout."
    )


def main(argv: list[str] | None = None) -> int:
    tooling = _tooling_dir()
    if tooling not in sys.path:
        sys.path.insert(0, tooling)
    from cli import main as _main

    return _main(argv)


if __name__ == "__main__":
    sys.exit(main())
