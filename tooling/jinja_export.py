"""Export every Jinja filter, global and test registered on a FortiSOAR box.

    make jinja-export INSTANCE=<pyfsr instance alias>
    PYTHONPATH=. .venv/bin/python -m tooling.jinja_export --instance <alias> [-o path]

What it does, over the instance's SSH profile (``[instances.<alias>.appliance]``
in ``~/.pyfsr/instances.toml``):

  1. copies ``scripts/internal/dump_jinja_filters.py`` to the box (mode 0600),
  2. runs it with the workflow service's own interpreter
     (``/opt/cyops-workflow/.env/bin/python``, as root), which boots the
     workflow Django app and introspects the live ``jinja2.Environment``:
     every filter / global / test with qualname, module, docstring and
     ``inspect.signature()``,
  3. reads the JSON it wrote back, removes both temp files,
  4. stamps the FortiSOAR build (``rpm -q cyops-workflow``) and writes the
     result to ``data/incoming/filters.json``.

Then load it into the reference DB and refresh the evidence:

    PYTHONPATH=. .venv/bin/python -m tooling.probes.probe_jinja_backend
    make jinja-probe INSTANCE=<alias>

The script is copied rather than piped on stdin because the SSH transport may
write a sudo password to stdin first, which Python would read as source.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DUMP_SCRIPT = REPO_ROOT / "scripts" / "internal" / "dump_jinja_filters.py"
DEFAULT_OUT = REPO_ROOT / "data" / "incoming" / "filters.json"
WORKFLOW_PY = "/opt/cyops-workflow/.env/bin/python"
REMOTE_SCRIPT = "/tmp/fsrpb_dump_jinja_filters.py"
REMOTE_OUT = "/tmp/filters.json"  # where dump_jinja_filters.py writes


def _transport(alias: str):
    from pyfsr.instances import InstanceRegistry

    return InstanceRegistry.load().transport(alias)


def _check(res, what: str) -> str:
    if not res.ok:
        raise SystemExit(f"{what} failed ({res.returncode}): {res.stderr.strip()[-500:]}")
    return res.stdout


def fsr_build(t) -> str:
    """``cyops-workflow-8.0.0-6034``-style build stamp for the evidence rows."""
    res = t.run(["rpm", "-q", "cyops-workflow"], timeout=30)
    return res.stdout.strip().removesuffix(".el9.x86_64") if res.ok else "unknown"


def export(alias: str) -> dict:
    t = _transport(alias)
    _check(t.run(["sh", "-c", f"umask 077; cat > {REMOTE_SCRIPT}"],
                 input_text=DUMP_SCRIPT.read_text(), timeout=60), "upload")
    try:
        res = t.run([WORKFLOW_PY, REMOTE_SCRIPT], sudo=True, timeout=600)
        _check(res, "dump_jinja_filters.py")
        raw = _check(t.run(["cat", REMOTE_OUT], sudo=True, timeout=60), "read export")
    finally:
        t.run(["rm", "-f", REMOTE_SCRIPT], timeout=30)
        t.run(["rm", "-f", REMOTE_OUT], sudo=True, timeout=30)
    data = json.loads(raw[raw.index("{"):])
    data["_meta"] = {
        "fsr_build": fsr_build(t),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {k: len(data.get(k) or {}) for k in ("filters", "globals", "tests")},
    }
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", required=True, help="pyfsr instance alias with an appliance SSH profile")
    ap.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    data = export(args.instance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1, sort_keys=True))
    m = data["_meta"]
    print(f"[jinja-export] {m['fsr_build']}: {m['counts']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
