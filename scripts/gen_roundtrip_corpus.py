#!/usr/bin/env python3
"""Generate the committed round-trip fidelity corpus (box-free).

Why this exists — the honest version: the F4 pull's clean playbooks were never
written out (only the 1,389 FAILING ones survived, in a gitignored scratch dir),
so a fidelity gate that needs playbooks which *compile* had nothing to diff. See
`docs/plans/playbook-compiler-fidelity-and-agent-surface.md` §3.1a. Rather than
block on a fresh box pull (gated by the R1 licensing review), this synthesizes a
small, committed corpus that exercises the two field-classes we have *already
watched get silently deleted* — `steps[].for_each` and declared playbook
`parameters` — plus clean baselines and the envelope-sugar hoist.

Each fixture is a real FSR *wire* collection envelope: curated YAML is compiled
through the real pipeline (so the step-type UUIDs and argument shapes are the
genuine ones), then ENRICHED with the server metadata a `?$relationships=true`
pull carries (`@id`, `uuid`, `createDate`, `owners`, `recordTags`, and an
expanded `stepType` dict on the trigger). That noise is the point: the gate's
normalizer must project past it, so the corpus has to contain it. The committed
artifact is the static JSON — this generator is kept only to extend/refresh it.

    FSRPB_DEV=1 .venv/bin/python scripts/gen_roundtrip_corpus.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from fsr_playbooks._db import PACKAGED_SLIM_DB
from fsr_playbooks.compiler import compile_yaml
from fsr_playbooks.compiler.roundtrip import roundtrip

OUT_DIR = Path(__file__).resolve().parent.parent / (
    "fsr_playbooks/tests/fixtures/roundtrip_corpus")

# A stable, fake step-type UUID so the enrichment is deterministic (the real one
# already lives in the IRI we replace; the dict form only needs a uuid to match).
_EXPANDED_STEPTYPE = "ea155646-3821-4542-9702-b246da430a8d"

# (filename, one-line intent, YAML). Every snippet is known-good against the
# packaged slim DB; the generator asserts each compiles AND round-trips clean.
CORPUS: list[tuple[str, str, str]] = [
    (
        "for_each_loop",
        "LOSSY CLASS #1 — a looping step; for_each must survive the round-trip",
        """
collection: Corpus
playbooks:
  - name: Escalate Every Open Incident
    steps:
      - name: Start
        type: start_on_create
        module: incidents
        next: Find Open
      - name: Find Open
        type: find_record
        module: incidents
        query: {logic: AND, filters: []}
        next: Escalate Each
      - name: Escalate Each
        type: set_variable
        for_each:
          item: "{{ vars.steps.Find_Open }}"
          parallel: false
          condition: "{{ vars.item.severity != 'Low' }}"
        vars:
          sev: "{{ vars.item.severity }}"
""",
    ),
    (
        "declared_parameters",
        "LOSSY CLASS #2 — top-level declared parameters (the manual-trigger form)",
        """
collection: Corpus
playbooks:
  - name: Block Indicator
    parameters:
      indicatorValue: string
      actionReason: string
    steps:
      - name: Start
        type: start
        next: Note
      - name: Note
        type: set_variable
        vars:
          echo: "{{ vars.input.params.indicatorValue }}"
""",
    ),
    (
        "envelope_sugar",
        "Universal step-envelope keys (when / ignore_errors) must hoist back out",
        """
collection: Corpus
playbooks:
  - name: Conditional Set
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Set
      - name: Set
        type: set_variable
        when: "{{ vars.score > 70 }}"
        ignore_errors: true
        vars:
          foo: bar
""",
    ),
    (
        "linear_baseline",
        "Clean baseline — a plain linear playbook with no lossy structures",
        """
collection: Corpus
playbooks:
  - name: Simple Note
    steps:
      - name: Start
        type: start_on_create
        module: alerts
        next: Set A
      - name: Set A
        type: set_variable
        vars: {a: "1"}
        next: Set B
      - name: Set B
        type: set_variable
        vars: {b: "2"}
""",
    ),
]


# The real F4 shape: `parameters: []` at the top level, everything declared on
# the TRIGGER step's `inputVariables`. The YAML dialect materializes params to
# the top-level list, so this shape can only be built as hand-authored wire
# JSON — which is also how test_decompiler_parameters_from_trigger.py builds it.
_TRIGGER_UUID = "e77eec41-6212-468a-9128-63a2cead869c"
_TRIGGER_STEPTYPE = "f4ca4d1c-8b1c-4a2a-9b53-9d0a2a5a1a11"


def _trigger_declared_params_fixture() -> dict:
    wf = {
        "name": "Action - Domain - Unblock", "description": "", "isActive": True,
        "parameters": [],  # empty top-level — the whole point of this shape
        "triggerStep": f"/api/3/workflow_steps/{_TRIGGER_UUID}",
        "steps": [
            {
                "uuid": _TRIGGER_UUID, "name": "Start",
                "stepType": f"/api/3/workflow_step_types/{_TRIGGER_STEPTYPE}",
                "arguments": {
                    "route": "177547a1-b3cb-47ca-a186-743a675a79c4",
                    "title": "Action - Domain - Unblock",
                    "resources": ["indicators"],
                    "inputVariables": [
                        {"name": n, "type": "string", "label": n}
                        for n in ("actionReason", "inputIndicatorValue")
                    ],
                },
            },
            {
                "uuid": "5f8ddf88-42e8-4b69-aff4-9fc07775a234", "name": "Add note",
                "stepType": "/api/3/workflow_step_types/"
                            "f4ca4d1c-8b1c-4a2a-9b53-9d0a2a5a1a22",
                "arguments": {},
            },
        ],
        "routes": [],
    }
    return {"data": [{"name": "Corpus", "description": "", "visible": True,
                      "workflows": [wf]}]}


def _enrich(env: dict) -> dict:
    """Add the server-side metadata a live `?$relationships=true` pull carries.

    The gate must ignore every key added here — that is exactly what makes the
    corpus a real test of the projection rather than of the compiler's own
    output shape.
    """
    env = copy.deepcopy(env)
    coll = env["data"][0]
    coll.update({
        "@id": "/api/3/workflow_collections/00000000-0000-0000-0000-000000000000",
        "@type": "WorkflowCollection",
        "uuid": "00000000-0000-0000-0000-000000000000",
        "createDate": 1700000000, "modifyDate": 1700000001,
        "createUser": "/api/3/people/admin", "modifyUser": "/api/3/people/admin",
        "owners": [], "recordTags": [], "versions": [],
    })
    for wf in coll["workflows"]:
        wf.update({
            "@id": "/api/3/workflows/11111111-1111-1111-1111-111111111111",
            "createDate": 1700000000, "modifyDate": 1700000001,
            "owners": [], "recordTags": [], "versions": [],
        })
        for i, st in enumerate(wf.get("steps", [])):
            st.setdefault("@id", f"/api/3/workflow_steps/step-{i}")
            st.setdefault("uuid", st.get("uuid") or f"step-uuid-{i}")
            # Expand the FIRST step's stepType IRI into the nested-dict shape the
            # live relationships API returns, so the dict path of the normalizer
            # is exercised alongside the IRI-string path.
            if i == 0 and isinstance(st.get("stepType"), str):
                st["stepType"] = {
                    "@id": st["stepType"],
                    "uuid": st["stepType"].rsplit("/", 1)[-1] or _EXPANDED_STEPTYPE,
                }
    return env


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, intent, yaml_text in CORPUS:
        res = compile_yaml(yaml_text, PACKAGED_SLIM_DB)
        hard = [e.message for e in res.errors if e.severity != "warning"]
        assert res.ok, f"{name}: fixture YAML does not compile: {hard}"

        env = _enrich(res.fsr_json)

        # A generated fixture that does not itself round-trip clean would bake a
        # false failure into the gate. Refuse to write one.
        ok, diffs = roundtrip(env, PACKAGED_SLIM_DB)
        assert ok, f"{name}: enriched fixture does not round-trip clean: {diffs}"

        payload = {"_intent": intent, "envelope": env}
        (OUT_DIR / f"{name}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n")
        written += 1
        print(f"  wrote {name}.json  — {intent}")

    # Hand-authored appliance shape (params on the trigger, empty top-level).
    intent = ("LOSSY CLASS #2 (real F4 shape) — parameters declared on the "
              "trigger's inputVariables with an empty top-level list")
    env = _enrich(_trigger_declared_params_fixture())
    ok, diffs = roundtrip(env, PACKAGED_SLIM_DB)
    assert ok, f"trigger_parameters: does not round-trip clean: {diffs}"
    (OUT_DIR / "trigger_parameters.json").write_text(
        json.dumps({"_intent": intent, "envelope": env},
                   indent=2, sort_keys=True) + "\n")
    written += 1
    print(f"  wrote trigger_parameters.json  — {intent}")

    print(f"corpus: {written} fixtures -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
