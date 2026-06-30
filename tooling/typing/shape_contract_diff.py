#!/usr/bin/env python3
"""Cross-stage shape-contract diff (TYPING_GAP_IDENTIFICATION_PLAN Pass 2).

The compiler passes each step body around as an untyped ``dict[str, Any]``
(``Step.arguments``). Every stage pokes at it by string key, and nothing checks
that the key a *producer* stage writes is the key a *consumer* stage reads. The
F3 bug was exactly this: the resolver emitted to
``arguments.input.schema.inputVariables`` while the reference lint read
``arguments.inputVariables`` — a silent shape disagreement.

This script statically extracts, per compiler stage, the set of string keys used
in arg-dict-style accesses and classifies each as a READ or a WRITE. It then
reports the dangerous asymmetries:

  * PHANTOM READS  — a key read by a consumer stage but written by no producer
    stage (the F3 signature: the reader is looking at the wrong key).
  * DEAD WRITES    — a key written by a producer but read by no other stage
    (authored data that never reaches a consumer = a silent drop candidate).

It is a heuristic (string-key/AST, not a type system), so it over-reports; the
value is the ranked shortlist of keys to eyeball. Run:

    python tooling/typing/shape_contract_diff.py
    python tooling/typing/shape_contract_diff.py --md > docs/shape_contract_diff.md
"""
from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / "fsr_playbooks" / "compiler"

# Stage role per module. Producers write the canonical wire arguments; consumers
# read them. parser is a pre-producer (friendly→args); decompiler is the inverse.
STAGES: dict[str, str] = {
    "parser.py": "producer",
    "resolver/normalizers.py": "producer",
    "resolver/connector_args.py": "producer",
    "emitter.py": "consumer",
    "typed_walker.py": "consumer",
    "validator.py": "consumer",
    "render_analyzer.py": "consumer",
    "arg_validator.py": "consumer",
    "decompiler.py": "consumer",
}

# Variable names that, in this codebase, hold a step's arguments dict.
ARG_VARS = {"a", "args", "arguments", "step_args", "params"}

# Keys that are generic dict plumbing, not part of the step-arg contract.
IGNORE_KEYS = {"name", "id", "type", "next", "kind"}

# Phantom reads triaged 2026-06-30 as NOT latent-F3s (TYPING_GAP plan Pass 2
# triage). Each is safe for one of two reasons the static AST pass can't model:
#   * fallback-idiom — the consumer reads `a.get("friendly") or a.get("canonical")`,
#     so the resolved key is covered even after the resolver renames the friendly
#     one (typed_walker: module/modules, op/op_name, connector_name, vars).
#   * passthrough — a native/friendly key authored directly into `arguments` that
#     the emitter faithfully serializes or transforms at emit time; no producer
#     stage rewrites it, so "written by no stage" is expected, not a drop
#     (emitter: target/when/mock_result/apply_async).
# `inputs` is the real F3 and is already fixed (typed_walker reads the nested
# canonical first); its lone remaining read is a tolerated fallback.
# A NEW phantom read NOT in this set is what `--check` fails on — that is the
# signal that a fresh untyped cross-stage shape disagreement has appeared.
ACCEPTED_PHANTOM: set[str] = {
    "apply_async",
    "connector_name",
    "inputs",
    "mock_result",
    "module",
    "modules",
    "op",
    "op_name",
    "target",
    "vars",
    "when",
}


class AccessCollector(ast.NodeVisitor):
    """Collect (key, role) for string-key accesses on arg-dict-ish receivers."""

    def __init__(self) -> None:
        self.reads: set[str] = set()
        self.writes: set[str] = set()

    @staticmethod
    def _recv_is_argish(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in ARG_VARS
        # `.arguments` / `step.arguments`
        if isinstance(node, ast.Attribute):
            return node.attr in {"arguments"} or node.attr in ARG_VARS
        return False

    @staticmethod
    def _str_key(node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self._recv_is_argish(node.value):
            key = self._str_key(node.slice)
            if key:
                # Store context: assignment target => write, else read.
                if isinstance(node.ctx, ast.Store):
                    self.writes.add(key)
                else:
                    self.reads.add(key)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # a.get("X") / a.pop("X") / a.setdefault("X", ...)
        if (isinstance(node.func, ast.Attribute)
                and self._recv_is_argish(node.func.value)
                and node.args):
            key = self._str_key(node.args[0])
            if key:
                meth = node.func.attr
                if meth in {"get", "pop"}:
                    self.reads.add(key)
                elif meth == "setdefault":
                    self.writes.add(key)
        self.generic_visit(node)


def collect(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    c = AccessCollector()
    c.visit(tree)
    return c.reads - IGNORE_KEYS, c.writes - IGNORE_KEYS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true", help="emit a markdown report")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero on a phantom read not in ACCEPTED_PHANTOM "
                         "(CI ratchet for new cross-stage shape disagreements)")
    args = ap.parse_args()

    reads_by_stage: dict[str, set[str]] = {}
    writes_by_stage: dict[str, set[str]] = {}
    role: dict[str, str] = {}
    for rel, rol in STAGES.items():
        p = COMPILER / rel
        if not p.exists():
            continue
        r, w = collect(p)
        reads_by_stage[rel] = r
        writes_by_stage[rel] = w
        role[rel] = rol

    producers = [s for s in role if role[s] == "producer"]
    consumers = [s for s in role if role[s] == "consumer"]
    all_writes: set[str] = set().union(*(writes_by_stage[s] for s in producers)) if producers else set()
    all_writes |= set().union(*(writes_by_stage[s] for s in consumers)) if consumers else set()

    # PHANTOM READS: read by a consumer, written by no stage at all.
    phantom: dict[str, list[str]] = defaultdict(list)
    for s in consumers:
        for k in reads_by_stage[s]:
            if k not in all_writes:
                phantom[k].append(s)

    if args.check:
        new = sorted(k for k in phantom if k not in ACCEPTED_PHANTOM)
        stale = sorted(ACCEPTED_PHANTOM - set(phantom))
        if new:
            print("FAIL: new phantom read(s) — a consumer reads an arg key no "
                  "producer writes (latent F3). Triage, then add to "
                  "ACCEPTED_PHANTOM if safe:", file=sys.stderr)
            for k in new:
                print(f"  - {k} — read by: {', '.join(sorted(phantom[k]))}",
                      file=sys.stderr)
            return 1
        if stale:
            print("WARN: ACCEPTED_PHANTOM entries no longer seen as phantom "
                  f"(prune them): {', '.join(stale)}", file=sys.stderr)
        print("OK: no new phantom reads.")
        return 0

    # DEAD WRITES: written by a producer, read by no other stage.
    all_reads: set[str] = set().union(*(reads_by_stage[s] for s in role)) if role else set()
    dead: dict[str, list[str]] = defaultdict(list)
    for s in producers:
        for k in writes_by_stage[s]:
            if k not in all_reads:
                dead[k].append(s)

    key_matrix: dict[str, dict[str, str]] = defaultdict(dict)
    for s in role:
        for k in reads_by_stage[s]:
            key_matrix[k][s] = key_matrix[k].get(s, "") + "R"
        for k in writes_by_stage[s]:
            key_matrix[k][s] = key_matrix[k].get(s, "") + "W"

    out = print
    if args.md:
        lines: list[str] = []
        out = lambda *a: lines.append(" ".join(str(x) for x in a))  # noqa: E731

    out("# Shape-contract diff (Pass 2)\n")
    out(f"Stages analyzed: {len(role)} "
        f"({len(producers)} producer, {len(consumers)} consumer)\n")

    out("## PHANTOM READS — read by a consumer, written by no stage")
    out("_The F3 signature: the reader is looking at a key nothing produces._\n")
    if phantom:
        for k in sorted(phantom):
            out(f"- `{k}` — read by: {', '.join(sorted(phantom[k]))}")
    else:
        out("- (none)")
    out("")

    out("## DEAD WRITES — written by a producer, read by no other stage")
    out("_Authored data that may never reach a consumer (silent-drop candidate)._\n")
    if dead:
        for k in sorted(dead):
            out(f"- `{k}` — written by: {', '.join(sorted(dead[k]))}")
    else:
        out("- (none)")
    out("")

    out("## Key x stage matrix (R=read, W=write)\n")
    hdr = ["key"] + [s.replace("resolver/", "").replace(".py", "") for s in role]
    out("| " + " | ".join(hdr) + " |")
    out("|" + "|".join(["---"] * len(hdr)) + "|")
    for k in sorted(key_matrix):
        row = [k] + [key_matrix[k].get(s, "") for s in role]
        out("| " + " | ".join(row) + " |")

    if args.md:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
