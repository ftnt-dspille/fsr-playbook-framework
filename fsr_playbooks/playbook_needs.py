"""What a playbook needs from the box's catalog, read straight from its YAML.

A targeted warm (``warmup.box_catalog(client, playbook=...)``) fetches only these:
the connectors the steps call (definition, configurations, health), the modules
record steps read or write (metadata, and the picklists their fields bind to),
and picklists named directly in Jinja (``'AlertStatus' | picklist('Open')``).

Pure and tolerant: no compile, no DB, no network. Malformed or partial YAML
yields whatever could be read; a missing reference only means a later compile
reports it, exactly as it would without a targeted warm.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

# Keys whose string value names a connector / module wherever they appear in a step.
_CONNECTOR_KEYS = frozenset({"connector"})
_MODULE_KEYS = frozenset({"module", "resource", "record_module"})
# `'ListName' | picklist('Value')` and `picklist('ListName', 'Value')` in Jinja.
_PICKLIST_FILTER = re.compile(r"""['"]([^'"]{1,120})['"]\s*\|\s*picklist\s*\(""")
_PICKLIST_CALL = re.compile(r"""picklist\s*\(\s*['"]([^'"]{1,120})['"]\s*,""")
# A module reference inside an IRI or a record path: /api/3/<module>/...
_IRI_MODULE = re.compile(r"/api/3/([A-Za-z][A-Za-z0-9_]{0,63})(?:/|\b)")
_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}$")
# Collections that are not record modules.
_NOT_MODULES = frozenset({"picklists", "picklist_names", "teams", "people", "files", "workflows",
                          "workflow_collections", "tags", "query", "upsert"})


@dataclass(frozen=True)
class PlaybookNeeds:
    connectors: frozenset[str] = field(default_factory=frozenset)
    modules: frozenset[str] = field(default_factory=frozenset)
    picklists: frozenset[str] = field(default_factory=frozenset)

    def is_empty(self) -> bool:
        return not (self.connectors or self.modules or self.picklists)


def playbook_needs(yaml_text: str) -> PlaybookNeeds:
    """The connectors, modules and picklists ``yaml_text`` refers to."""
    connectors: set[str] = set()
    modules: set[str] = set()
    picklists: set[str] = set()

    from fsr_playbooks.mcp_server._shared import load_yaml_text

    try:
        doc, _ = load_yaml_text(yaml_text, allow_grounding=False)
    except yaml.YAMLError:
        doc = None

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str):
                    if k in _CONNECTOR_KEYS and _NAME.match(v):
                        connectors.add(v)
                    elif k in _MODULE_KEYS and _NAME.match(v) and "{{" not in v:
                        modules.add(v)
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            _scan_text(node)

    def _scan_text(text: str) -> None:
        for rx in (_PICKLIST_FILTER, _PICKLIST_CALL):
            picklists.update(m.group(1) for m in rx.finditer(text))
        for m in _IRI_MODULE.finditer(text):
            if m.group(1) not in _NOT_MODULES:
                modules.add(m.group(1))

    if doc is not None:
        walk(doc)
    else:  # unparseable: still pick up what a plain scan can see
        _scan_text(yaml_text)
        connectors.update(re.findall(r"^\s*connector:\s*['\"]?([A-Za-z0-9_.\-]+)", yaml_text, re.M))
        modules.update(re.findall(r"^\s*module:\s*['\"]?([A-Za-z][A-Za-z0-9_]*)", yaml_text, re.M))

    return PlaybookNeeds(frozenset(connectors), frozenset(modules - _NOT_MODULES), frozenset(picklists))
