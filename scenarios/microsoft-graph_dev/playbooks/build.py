#!/usr/bin/env python3
"""Build playbooks.json from playbooks.yaml.

Compiles the YAML with the fsrpb compiler. The scenario playbooks are plain
connector playbooks - no Data Ingestion Wizard contract - so, unlike the
fortiaigate build this script is derived from, there is nothing to patch on
after the fact. The only post-compile work is deterministic housekeeping:
stamping the sample collection name with the version from the connector's
``info.json`` and pinning ``lastModifyDate`` so a rebuild is byte-identical.

The strict compile is tried first; if the catalog does not know this connector
(the reference store has not been provisioned with it - always the case in a
fresh checkout), the build falls back to ``--lax``, which demotes the
unknown-connector errors to warnings. Under ``--lax`` a genuinely misspelled
operation slips through as a warning too, so read the output.

Usage:
    python playbooks/build.py [--fsrpb /path/to/fsrpb] [--info /path/to/info.json]

``--info`` defaults to the connector package's own ``info.json`` (the directory
above ``playbooks/``), which is how the file resolves once this directory is
shipped inside the connector package. When building from a checkout that keeps
the scenarios outside the package (this repo's ``scenarios/`` staging tree),
pass the packaged ``info.json`` explicitly.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
YAML_IN = HERE / "playbooks.yaml"
JSON_OUT = HERE / "playbooks.json"

CONNECTOR = "microsoft-graph_dev"


def _freeze_timestamps(doc):
    """Pin every ``lastModifyDate`` so a rebuild is byte-identical.

    The compiler stamps each workflow with the wall-clock time of the build, so
    two runs over an unchanged source produce two different files. That noise
    hides the one-line change you actually made when reviewing, and makes it
    impossible to tell from a diff whether the compiled artefact was rebuilt or
    edited.

    The value tracks the YAML's own mtime, so it still moves when the source
    genuinely changes. ``SOURCE_DATE_EPOCH`` overrides it, per the usual
    reproducible-builds convention.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    stamp = int(epoch) if epoch and epoch.isdigit() else int(YAML_IN.stat().st_mtime)

    def walk(node):
        if isinstance(node, dict):
            if "lastModifyDate" in node:
                node["lastModifyDate"] = stamp
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    return doc


def _sync_collection_version(doc, info_path):
    """Retag the sample collection with the version from ``info.json``.

    FortiSOAR deletes a connector's sample collection on upgrade and re-imports
    it under the new name, so a collection still carrying the previous version
    leaves the appliance with a stale name - or, if the old collection was
    removed by hand, no sample playbooks at all. Keeping the name derived from
    ``info.json`` means the version only has to be bumped in one place.
    """
    info = json.loads(pathlib.Path(info_path).read_text())
    version = info.get("version")
    if not version:
        sys.stderr.write(f"warning: {info_path} has no version; collection name left as authored\n")
        return doc
    for collection in doc.get("data", []):
        name = collection.get("name") or ""
        collection["name"] = re.sub(r"\d+\.\d+\.\d+$", version, name) if re.search(
            r"\d+\.\d+\.\d+$", name) else name
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fsrpb", default="fsrpb", help="path to the fsrpb executable")
    ap.add_argument("--info", default=str(HERE.parent / "info.json"),
                    help="path to the connector's info.json (default: ../info.json)")
    args = ap.parse_args()

    def _compile(lax):
        cmd = [args.fsrpb, "compile", str(YAML_IN), "-o", str(JSON_OUT)]
        if lax:
            cmd.insert(3, "--lax")
        return subprocess.run(cmd, capture_output=True, text=True)

    proc = _compile(lax=False)
    if proc.returncode != 0 and "unknown connector" in (proc.stdout + proc.stderr):
        # The reference store has not been told about this connector yet, so
        # every step referencing it fails validation. Fall back to --lax so the
        # build still works, but say how to fix it properly - under --lax a
        # genuinely misspelled operation slips through as a warning too.
        sys.stderr.write(
            f"warning: the fsrpb catalog does not know {CONNECTOR!r}; compiling "
            f"with --lax, which also demotes real typos to warnings.\n"
            f"         fix: provision the connector into the reference store.\n",
        )
        proc = _compile(lax=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        return proc.returncode

    doc = json.loads(JSON_OUT.read_text())
    doc = _sync_collection_version(doc, args.info)
    doc = _freeze_timestamps(doc)
    JSON_OUT.write_text(json.dumps(doc, indent=2) + "\n")

    total = sum(len(c.get("workflows", [])) for c in doc.get("data", []))
    names = [c.get("name") for c in doc.get("data", [])]
    print(f"wrote {JSON_OUT} ({total} playbooks, collections={names})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
