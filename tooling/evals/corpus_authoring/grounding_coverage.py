"""Grounding hit-rate: does the oracle cover the references the corpus makes?

The grounded reference enrichment (verify's static catch, debug_run's fix path,
grounded_help) only fires when a step-output reference reads a connector op whose
real output SHAPE is in the grounded store. The store has a handful of ops; the
corpus touches many. This module measures the gap with no model and no box:

  * for each playbook, map each connector step's jinja key -> (connector, op);
  * find every `vars.steps.<key>.<deep.path>` reference that reads a connector
    op's payload (a shape dependency the compiler can't verify on its own);
  * classify each as GROUNDED (the op is in the store) or UNGROUNDED.

The hit-rate is grounded / (grounded + ungrounded). The ungrounded ops ranked by
reference count are the priority list for growing the store: ground the op the
corpus leans on most first. This is a measurement, so its test pins the counting
logic against a synthetic corpus with a known answer, not a box."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# vars.steps.<Key>.<rest> -- capture the step key and the path after it.
_REF = re.compile(r"vars\.steps\.([A-Za-z0-9_]+)((?:\.[A-Za-z0-9_]+|\[[^\]]*\])+)")


def _key(name: str) -> str:
    """The jinja key for a step name: non-word chars -> underscore (how FSR
    renders `Get IP Reputation` as `Get_IP_Reputation`)."""
    return re.sub(r"\W", "_", str(name or "")).strip("_")


def _connector_ops(doc: dict) -> dict[str, tuple[str, str]]:
    """Map each connector step's jinja key -> (connector, operation)."""
    out: dict[str, tuple[str, str]] = {}
    for pb in (doc.get("playbooks") or []):
        for s in (pb.get("steps") or []):
            if s.get("type") in ("connector", "connector_op"):
                conn, op = s.get("connector"), s.get("operation")
                if conn and op:
                    out[_key(s.get("name"))] = (str(conn), str(op))
    return out


def _is_payload_ref(rest: str) -> bool:
    """A reference that reads into the connector envelope's payload -- the part
    whose shape the oracle grounds. `.data...`, `.data[...]`, or any deep attr.
    A bare `.status` / `.message` envelope field is not a shape dependency."""
    return rest.startswith(".data") or rest.count(".") + rest.count("[") >= 2


@dataclass
class Coverage:
    grounded: int = 0
    ungrounded: int = 0
    ungrounded_ops: Counter = field(default_factory=Counter)
    playbooks: int = 0
    playbooks_with_refs: int = 0

    @property
    def total(self) -> int:
        return self.grounded + self.ungrounded

    @property
    def hit_rate(self) -> float:
        return self.grounded / self.total if self.total else 0.0

    def merge(self, other: "Coverage") -> None:
        self.grounded += other.grounded
        self.ungrounded += other.ungrounded
        self.ungrounded_ops.update(other.ungrounded_ops)
        self.playbooks += other.playbooks
        self.playbooks_with_refs += other.playbooks_with_refs


def scan_yaml(yaml_text: str, store: Any) -> Coverage:
    """Count grounded vs ungrounded connector-op payload references in one
    decompiled playbook document. `store` answers `.shape_for(connector, op)`."""
    cov = Coverage()
    try:
        doc = yaml.safe_load(yaml_text) or {}
    except Exception:  # noqa: BLE001
        return cov
    if not isinstance(doc, dict):
        return cov
    cov.playbooks = len(doc.get("playbooks") or [])
    by_key = _connector_ops(doc)
    seen_ref = False
    for m in _REF.finditer(yaml_text):
        key, rest = m.group(1), m.group(2)
        if key not in by_key or not _is_payload_ref(rest):
            continue
        conn, op = by_key[key]
        seen_ref = True
        if store.shape_for(conn, op) is not None:
            cov.grounded += 1
        else:
            cov.ungrounded += 1
            cov.ungrounded_ops[f"{conn}:{op}"] += 1
    if seen_ref:
        cov.playbooks_with_refs = 1
    return cov


def grounding_coverage(corpus_dir: str | Path, store: Any) -> Coverage:
    """Scan every `*.yaml` in a decompiled corpus dir and aggregate coverage."""
    total = Coverage()
    for f in sorted(Path(corpus_dir).glob("*.yaml")):
        try:
            total.merge(scan_yaml(f.read_text(), store))
        except Exception:  # noqa: BLE001
            continue
    return total


def _default_store() -> Any:
    from fsr_playbooks.mcp_server import tools_verify
    return tools_verify._grounded_store()


def format_report(cov: Coverage, top: int = 15) -> str:
    lines = [
        "grounding hit-rate",
        f"  connector-op payload references : {cov.total}",
        f"  grounded (oracle covers the op) : {cov.grounded}",
        f"  ungrounded                      : {cov.ungrounded}",
        f"  hit-rate                        : {cov.hit_rate:.1%}",
        f"  distinct ungrounded ops         : {len(cov.ungrounded_ops)}",
        "",
        f"  top ungrounded ops by reference count (grow these first):",
    ]
    for op, n in cov.ungrounded_ops.most_common(top):
        lines.append(f"    {n:4d}  {op}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus_dir", help="dir of decompiled *.yaml playbooks")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    cov = grounding_coverage(args.corpus_dir, _default_store())
    print(format_report(cov, top=args.top))
