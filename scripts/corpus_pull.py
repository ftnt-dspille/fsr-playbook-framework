"""F4 — re-pull stock playbooks from a live box and reproduce the compile failures.

The original 10-playbook corpus was never saved (only the 5 clean ones became
synthesized fixtures), so the offending YAML no longer exists locally. Widening
the compiler on the strength of a remembered error string would be guessing at
the wire contract; this re-pulls the real documents so the fix has evidence.

Writes every FAILING playbook's wire JSON + decompiled YAML to an output dir so
they can be installed as fixtures.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

os.environ.setdefault("FSRPB_DEV", "1")

from pyfsr import FortiSOAR  # noqa: E402

from fsr_playbooks._db import default_db_path  # noqa: E402
from fsr_playbooks.compiler import compile_yaml  # noqa: E402
from fsr_playbooks.compiler.decompiler import decompile_to_yaml  # noqa: E402

DB = default_db_path()

# The local reference DB holds a fraction of the box's connectors, so
# "unknown connector: 'x'" is a LOCAL GAP, not a compiler-strictness bug. F4 is
# about the other classes (set_variable key allowlists, parameter shadowing),
# which are connector-independent — so bucket the noise out rather than letting
# it drown the signal.
def is_db_gap(msg: str) -> bool:
    return ("unknown connector" in msg
            or "unknown operation" in msg
            or "not in reference DB" in msg)

ENV = sys.argv[1] if len(sys.argv) > 1 else (
    "/Users/dylanspille/WebstormProjects/fsr_all_widgets/"
    "fortisoar-widget-harness/.env.159")
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 400
OUT = Path(__file__).parent / "f4_failing"
OUT.mkdir(exist_ok=True)

client = FortiSOAR.from_env_file(ENV)
print(f"box={client.appliance if hasattr(client, 'appliance') else ENV}", flush=True)

# Playbooks live in /api/3/workflows; each carries its steps inline.
# $relationships=true is REQUIRED: without it a workflow row carries no
# steps[]/routes[], and the decompiler would see an empty graph.
page = client.get("/api/3/workflows",
                  params={"$limit": LIMIT, "$relationships": "true"})
rows = page.get("hydra:member") if isinstance(page, dict) else page
print(f"pulled {len(rows)} workflows", flush=True)

ok = 0
failures: list[dict] = []
db_gaps: list[str] = []
classes: Counter = Counter()

for wf in rows:
    name = wf.get("name") or wf.get("uuid")
    try:
        # decompile() takes a WorkflowCollection export envelope, not a bare
        # workflow row — wrap each playbook as a one-workflow collection.
        env = {"data": [{"name": "F4 pull", "description": "",
                         "visible": True, "workflows": [wf]}]}
        y = decompile_to_yaml(env, DB)
    except Exception as e:  # noqa: BLE001
        classes["decompile:" + type(e).__name__] += 1
        failures.append({"name": name, "phase": "decompile",
                         "error": f"{type(e).__name__}: {e}", "wf": wf})
        continue
    try:
        res = compile_yaml(y, DB)
        # Only severity="error" blocks a compile. The result also carries
        # lint WARNINGS (missing button_label, absent mock_result, picklist
        # IRIs the local DB cannot resolve) — counting those as failures
        # would inflate "stock content does not compile" with style notes.
        errs = [e for e in (getattr(res, "errors", None) or [])
                if getattr(e, "severity", "error") == "error"]
        if errs:
            raise RuntimeError(" ;; ".join(
                f"[{getattr(e,'code','?')}] {getattr(e,'message',e)}" for e in errs))
        ok += 1
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if is_db_gap(msg):
            db_gaps.append(name)
            classes["(local DB gap — not a compiler bug)"] += 1
            continue
        # Bucket by the shape of the message, not the specific identifier, so
        # the same class over different fields lands together.
        key = msg.split("]")[0].lstrip("[")[:70]
        classes["compile:" + key] += 1
        failures.append({"name": name, "phase": "compile", "error": msg,
                         "yaml": y, "wf": wf})

print(f"\ncompiled OK : {ok}/{len(rows)}")
print(f"local DB gaps (ignored): {len(db_gaps)}")
print(f"real failures: {len(failures)}")
print("\n── failure classes ───────────────────────────")
for k, n in classes.most_common():
    print(f"{n:4d}  {k}")

# Group by the SHAPE of the message (identifiers stripped) so the triage list
# is "how many distinct compiler gaps" rather than "how many playbooks".
import re
def shape(msg: str) -> str:
    m = msg.split(" ;; ")[0]
    m = re.sub(r"'[^']*'", "'X'", m)
    m = re.sub(r"`[^`]*`", "`X`", m)
    m = re.sub(r"\bstep '[^']*'", "step 'X'", m)
    return m[:150]

shapes: Counter = Counter()
examples: dict[str, str] = {}
for f in failures:
    k = shape(f["error"])
    shapes[k] += 1
    examples.setdefault(k, f["name"])

print("\n── distinct failure shapes (count, example playbook) ─────────")
for k, n in shapes.most_common():
    print(f"{n:4d}  {k}")
    print(f"      e.g. {examples[k]}")

for i, f in enumerate(failures):
    stem = "".join(c if c.isalnum() else "_" for c in str(f["name"]))[:60]
    (OUT / f"{i:02d}_{stem}.json").write_text(json.dumps(f["wf"], indent=2))
    if f.get("yaml"):
        (OUT / f"{i:02d}_{stem}.yaml").write_text(f["yaml"])
print(f"\nwrote {len(failures)} failing playbooks to {OUT}")
