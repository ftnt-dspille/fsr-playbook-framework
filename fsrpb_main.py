"""Console-script entry point for the `fsrpb` CLI.

The CLI implementation lives in `python/cli.py`, which (along with its sibling
modules `recover.py`, `picklists.py`, …) is part of the legacy `python/` layout
and is NOT installed as an importable package. The `[project.scripts]` wrapper
runs from an arbitrary cwd, so we bootstrap `python/` onto sys.path here, then
hand off to `cli.main`. Keep this module dependency-free and tiny.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)


def main(argv: list[str] | None = None) -> int:
    from cli import main as _main

    return _main(argv)


if __name__ == "__main__":
    sys.exit(main())
