"""Drive one BUILD -> RUN -> VERIFY task through Claude Code + the toolkit MCP.

The one agentic dimension the authoring and repair drives cannot measure: after
an agent WRITES to the box, does it close the loop -- read the effect back and
confirm the write actually landed, rather than trusting that a call returned ok?
That is the question behind verify_effect, and it only shows on a drive that
actually publishes and runs a playbook.

This drive hands the agent a goal ("make this alert's field end up X"), lets it
author, gate, publish and run through the toolkit, and grades the tool sequence
with effect_verification (did a readback follow the last write). The harness owns
the disposable target: it creates a throwaway alert before the drive and deletes
it (and the published collection) after, so a shared box is left as it was.

Live-only: creating/deleting records and running claude -p need the box and a
Claude login. `--plan` prints exactly what a live run would do and writes NOTHING
(it never even constructs a client). Mechanics are pinned by fake-transcript
tests; the live path is unrun until a live pass, like the workshop e2e specs.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from . import drive, effect_verification

PREAMBLE = (
    "You operate a FortiSOAR box through its toolkit MCP tools. Goal: make the "
    "alert at {iri} end up with its {field} equal to {want!r}.\n"
    "Author a short playbook that sets it, gate the draft, publish it as the "
    "collection {collection!r}, run it on that alert, then CONFIRM on the box that "
    "{field} is now {want!r}. Read the box rather than guessing; do not trust a "
    "call's own 'ok' as proof the field changed. End by stating whether {field} "
    "is set.\n\n"
)


def _client():
    """A live pyfsr client from FSR_* env. Constructs a connection (validates the
    key against the box), so it is NEVER called on the --plan path."""
    from pyfsr import EnvConfig

    return EnvConfig.from_env().client()


def _iri_of(rec) -> str:
    if isinstance(rec, dict):
        return str(rec.get("@id") or rec.get("iri") or rec.get("id") or "")
    return str(getattr(rec, "iri", "") or getattr(rec, "id", "") or "")


def make_test_alert(client, *, name: str) -> str:
    """Create a disposable alert and return its IRI (live)."""
    rec = client.post("/api/3/alerts", data={"name": name})
    return _iri_of(rec)


def cleanup(client, *, iri: str, collection: str) -> list[str]:
    """Best-effort removal of the test record and the published collection (live).
    Never raises: cleanup failure must not mask the drive result."""
    removed: list[str] = []
    try:
        rows = client.query("workflow_collections", {"name": collection}) or {}
        for c in (rows.get("hydra:member") or rows.get("data") or []):
            cid = _iri_of(c)
            if cid:
                client.delete(cid)
                removed.append(cid)
    except Exception:  # noqa: BLE001 -- best effort
        pass
    if iri:
        try:
            client.delete(iri)
            removed.append(iri)
        except Exception:  # noqa: BLE001
            pass
    return removed


def drive_build_run(task: dict, work: Path, model: str = "claude-sonnet-5-5",
                    timeout: int = 1800) -> dict:
    """Run one build->run->verify task; grade the readback discipline."""
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    cfg = drive._mcp_config(work)
    prompt = PREAMBLE.format(**task)
    cmd = ["claude", "-p", prompt, "--model", model,
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(cfg), "--strict-mcp-config",
           "--allowedTools", drive._ALLOWED]
    proc = subprocess.run(cmd, cwd=work, text=True, capture_output=True, timeout=timeout)
    events = drive._events(proc.stdout)
    (work / f"{task['id']}.brv.transcript.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events))
    yaml_text, tools = drive._extract_yaml(events)
    ev = effect_verification.grade_effect_verification(tools)
    return {
        "id": task["id"],
        "tools": tools,
        "authored_yaml": yaml_text,
        "wrote": ev["wrote"],
        "verified": ev["verified"],
        "used_verify_effect": ev["used_intended"],
        "effect": ev,
        "rc": proc.returncode,
        "stderr_tail": proc.stderr[-1500:],
    }


def _plan_text(task: dict) -> str:
    return (
        "BUILD-RUN-VERIFY drive PLAN (no box writes, no model call)\n"
        f"  collection : {task['collection']}\n"
        f"  field/want : {task['field']} = {task['want']!r}\n"
        "  live steps that WOULD run:\n"
        "    1. create a disposable alert (the target)\n"
        "    2. claude -p drives: author -> gate -> publish -> run -> confirm\n"
        "    3. grade: did a readback (verify_effect/get/query) follow the last write\n"
        "    4. cleanup: delete the published collection and the test alert\n"
        "  prompt the agent would get:\n"
        + "    " + PREAMBLE.format(iri="/api/3/alerts/<created-at-run-time>", **{
            k: task[k] for k in ("field", "want", "collection")}).replace("\n", "\n    ")
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="output dir (local only)")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--env-file", help="file of KEY=VALUE box creds (FSR_*); never printed")
    ap.add_argument("--field", default="description")
    ap.add_argument("--want", default="verified by eval")
    ap.add_argument("--plan", action="store_true", help="print the plan; write nothing, no client")
    ap.add_argument("--keep", action="store_true", help="skip cleanup (leave the test objects)")
    args = ap.parse_args(argv)

    collection = f"eval-brv-{int(time.time())}"
    task = {"id": "brv_set_field", "field": args.field, "want": args.want,
            "collection": collection}

    if args.plan:
        print(_plan_text(task))
        return 0

    if args.env_file:
        for line in Path(args.env_file).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not (os.environ.get("FSR_BASE_URL") and os.environ.get("FSR_API_KEY")):
        ap.error("FSR_BASE_URL and FSR_API_KEY must be set (the toolkit's box)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = _client()
    iri = make_test_alert(client, name=f"{collection}-target")
    task["iri"] = iri
    try:
        run = drive_build_run(task, out / "work", model=args.model)
    finally:
        removed = [] if args.keep else cleanup(client, iri=iri, collection=collection)
    run["cleanup_removed"] = removed
    (out / "build_run_verify.json").write_text(json.dumps(run, indent=2, default=str))
    print(f"  {run['id']:20} wrote={run['wrote']!s:5} verified={run['verified']!s:5} "
          f"used_verify_effect={run['used_verify_effect']}")
    print("  tools:", " -> ".join(run["tools"]) or "(none)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
