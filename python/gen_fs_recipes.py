#!/usr/bin/env python3
"""Generate Fabric Studio ``scenarios.yaml`` recipes from ``noc_scenarios.json``.

One source of truth: the NOC manifest
(``fsr_playbooks/mcp_server/noc_scenarios.json``) owns each scenario's baseline
preconditions (``baseline.*``) and its fault (``induce.*``). This script emits
the matching FS seed-check recipes so the two never drift (the decision in
``docs/plans/NOC_SCENARIO_CATALOG.md`` follow-up: *generate from manifest*).

For each scenario ``<id>`` it emits, all ``enabled: false`` (opt-in):

  * ``noc-baseline-<id>[-<side>]`` — NON-destructive preconditions (a working
    tunnel / FAZ logging / FMG registration). One recipe per ``setup_<side>``
    key (``setup_hq``/``setup_branch``), or a single ``noc-baseline-<id>`` for a
    plain ``setup`` list.
  * ``noc-fault-<id>`` — the destructive ``induce.setup`` with ``induce.teardown``
    as the revert.

``${VAR}`` tokens in the CLI lines become ``params_schema`` entries; examples are
filled from the scenario's ``target.*`` block where the value is concrete (not a
``${...}`` placeholder).

Usage:
    python python/gen_fs_recipes.py                  # print to stdout
    python python/gen_fs_recipes.py --out recipes.yaml
    python python/gen_fs_recipes.py --scenario vpn_tunnel_down
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "fsr_playbooks" / "mcp_server" / "noc_scenarios.json"

_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _load_manifest() -> dict[str, dict[str, Any]]:
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _flatten_target(target: dict[str, Any]) -> dict[str, str]:
    """Flatten target.{hq,branch,shared}.* into {VALUE_STRING} examples.

    Concrete values (not ``${...}``) are keyed by the placeholder name we expect
    to see in the CLI — we can't know which ``${VAR}`` a value maps to, so we
    only surface them as a free-form 'known values' hint in each param example.
    """
    known: dict[str, str] = {}
    for group in target.values():
        if not isinstance(group, dict):
            continue
        for k, v in group.items():
            if isinstance(v, str) and not v.startswith("${") and not k.startswith("_"):
                known[k] = v
    return known


def _vars_in(lines: list[str]) -> list[str]:
    seen: list[str] = []
    for line in lines:
        for m in _VAR_RE.findall(line):
            if m not in seen:
                seen.append(m)
    return seen


def _params_schema(varnames: list[str], known: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for v in varnames:
        # Best-effort example: match the var name (case-insensitive) against a
        # concrete target value; else leave blank for the operator to fill.
        example = ""
        low = v.lower()
        for kk, vv in known.items():
            if kk.lower() in low or low in kk.lower():
                example = vv
                break
        out.append({
            "name": v,
            "label": v.replace("_", " ").title(),
            "example": example,
            "required": True,
        })
    return out


def _recipe(slug: str, name: str, description: str, setup: list[str],
            *, destructive: bool, teardown: list[str] | None,
            probe: dict[str, Any] | None, params: list[dict[str, Any]]) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "slug": slug,
        "name": name,
        "capability": "cli",
        "is_template": True,
        "is_destructive": destructive,
        "enabled": False,
        "description": description,
        "scope": {"device_types": ["FGT"]},
    }
    if params:
        rec["params_schema"] = params
    rec["setup"] = list(setup)
    if teardown:
        rec["teardown"] = list(teardown)
    rec["wait_seconds"] = 3
    if probe and probe.get("command"):
        rec["probe"] = {"command": probe["command"]}
    rec["timeout_s"] = 60
    return rec


def generate(only: str | None = None) -> list[dict[str, Any]]:
    manifest = _load_manifest()
    recipes: list[dict[str, Any]] = []
    for sid, sc in manifest.items():
        if only and sid != only:
            continue
        known = _flatten_target(sc.get("target") or {})

        baseline = sc.get("baseline") or {}
        bcomment = baseline.get("comment", "")
        probe = baseline.get("probe")
        # One recipe per setup_<side>, or a single plain `setup`.
        side_keys = sorted(k for k in baseline if k.startswith("setup_"))
        if not side_keys and isinstance(baseline.get("setup"), list):
            side_keys = ["setup"]
        for sk in side_keys:
            setup = baseline.get(sk) or []
            if not setup:
                continue
            side = sk[len("setup_"):] or ""
            slug = f"noc-baseline-{sid.replace('_', '-')}" + (f"-{side}" if side else "")
            desc = bcomment
            if baseline.get("assert_up"):
                desc += f"  ASSERT: {baseline['assert_up']}"
            recipes.append(_recipe(
                slug, f"NOC baseline: {sid}" + (f" ({side})" if side else ""),
                desc, setup, destructive=False, teardown=None,
                probe=probe, params=_params_schema(_vars_in(setup), known)))

        induce = sc.get("induce") or {}
        isetup = induce.get("setup") or []
        if isetup:
            slug = f"noc-fault-{sid.replace('_', '-')}"
            recipes.append(_recipe(
                slug, f"NOC fault: {sid}", induce.get("comment", ""),
                isetup, destructive=True, teardown=induce.get("teardown"),
                probe=None, params=_params_schema(_vars_in(isetup), known)))
    return recipes


def _dump_yaml(recipes: list[dict[str, Any]]) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        sys.exit("PyYAML required: pip install pyyaml (or run inside the .venv)")

    class _S(yaml.SafeDumper):
        pass

    # Block style, preserve insertion order, don't sort keys.
    header = (
        "# GENERATED by python/gen_fs_recipes.py from "
        "fsr_playbooks/mcp_server/noc_scenarios.json — DO NOT HAND-EDIT.\n"
        "# Paste/merge into fabric_studio_fixer/backend/seed_checks/scenarios.yaml.\n"
        "# All recipes ship enabled:false (opt-in). Baselines are non-destructive\n"
        "# preconditions; faults (is_destructive:true) need the baseline applied first.\n"
    )
    body = yaml.dump(recipes, Dumper=_S, sort_keys=False,
                     default_flow_style=False, width=100, indent=2)
    return header + body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", help="only this scenario id")
    ap.add_argument("--out", help="write to this path (default: stdout)")
    args = ap.parse_args(argv)
    recipes = generate(args.scenario)
    if not recipes:
        print("no recipes generated (check --scenario / manifest)", file=sys.stderr)
        return 1
    text = _dump_yaml(recipes)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {len(recipes)} recipe(s) -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
