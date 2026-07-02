"""Extract the Ansible Jinja filter/test namespace for the FSR filter catalog.

FortiSOAR playbooks execute through an Ansible-based Jinja engine, so the
effective filter set is ``jinja2 builtins ∪ the Ansible filter namespace ∪
FSR-custom``. The widget-derived catalog (``extract_jinja_filters.js``) only
covers the palette the Jinja-editor widget lists, which omits most of the
Ansible set (``json_query``, ``ternary``, ``to_json``, ``combine``, ``zip``…)
— the §G false-positive source in AGENT_HARDENING_PLAN.md.

Run under an env that has the full ``ansible`` bundle (ansible-core +
community collections), e.g.:

    uv run --with ansible python tooling/extract_ansible_filters.py

Prints a JSON object ``{"ansible_filters": {name: provenance},
"ansible_tests": {name: provenance}}`` to stdout; merge it into
``fsr_playbooks/_data/jinja_filters.json`` (see that file's ``_comment``).
Provenance = the collection the plugin came from (``ansible.builtin`` /
``community.general`` / …), short names only (playbooks use the short form).
"""
from __future__ import annotations

import json
import sys


# Collections plausibly present on an FSR box's Ansible engine. Random
# vendor collections (ovirt, netapp, …) come with the full `ansible` bundle
# in the dump env but are NOT on the appliance — including them would trade
# false positives for false negatives.
_COLLECTIONS = ("ansible.builtin", "community.general")


def _ansible_doc_names(plugin_type: str) -> dict[str, str]:
    """Short-name → collection via ``ansible-doc -t <type> -l -j``.

    ``filter_loader.all()`` only enumerates ansible.builtin (collection
    plugins need a full loader/collection-path init); the CLI sees everything.
    """
    import subprocess

    raw = subprocess.run(
        ["ansible-doc", "-t", plugin_type, "-l", "-j"],
        check=True, capture_output=True, text=True).stdout
    names: dict[str, str] = {}
    for fqcn in json.loads(raw):
        collection, _, short = str(fqcn).rpartition(".")
        collection = ".".join(collection.split(".")[:2])
        if collection in _COLLECTIONS:
            # ansible.builtin sorts first, so it wins short-name collisions
            names.setdefault(short, collection)
    return names


def _collect() -> dict[str, dict[str, str]]:
    return {"ansible_filters": _ansible_doc_names("filter"),
            "ansible_tests": _ansible_doc_names("test")}


def main() -> int:
    data = _collect()
    json.dump(data, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    print(f"filters={len(data['ansible_filters'])} tests={len(data['ansible_tests'])}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
