# Corpus-driven authoring eval

Measures whether an agent driving the `fsr-agentic-toolkit` MCP tools can author
playbooks that match the structure of **real** FortiSOAR playbooks, across the
whole corpus (not a handful of curated fixtures).

The gap this fills: the 49-task matrix grades curated authoring fixtures; the
real 191-playbook corpus is only used by the static fidelity/compilability
gates. Nothing drove the authoring loop across real playbooks. This does.

## Pipeline

1. **Task-gen** (`sample_corpus.py` + `derive.py`) -- deterministic, box-free,
   no LLM. Each real playbook: wire JSON -> `decompile_to_yaml` ->
   `compile_yaml(...).ir` -> derive a prose `spec` + `ir_assertions` (the same
   grading vocabulary the framework matrix uses). The sampler keeps only
   assertions the source playbook itself satisfies (self-check), and only tasks
   with a substantive requirement. Tasks are bucketed by the known coverage
   gaps (child_playbook / approval / loop / code / decision / large / ...) and
   sampled stratified.
2. **Driver** (`drive.py`) -- Claude Code (`claude -p`, your subscription)
   drives the toolkit's MCP tools with each task's spec; the authored YAML is
   extracted from the transcript.
3. **Grader** (`grade.py`) -- the authored YAML is scored `draft` (compiles) +
   `verified` (`verify_playbook.ready_to_push`) + `ir_assertions`, aggregated by
   bucket.

## Local-only data

The corpus (`scratch/f4_failing/`, a real box pull) and the derived task files
are **local only** -- they carry real-box provenance and are never committed.
Only the code here is tracked. Point the sampler at the corpus explicitly:

    FSRPB_DEV=1 .venv/bin/python -m tooling.evals.corpus_authoring.sample_corpus \
        --corpus-dir scratch/f4_failing --out <local dir> --per-bucket 2

## Known v1 limitations

- The trigger assertion is weak: every playbook resolves to a `start` trigger
  because the on-create/post-create nuance lives in the start step's arguments,
  not its type. Meaningful structure (connector ops, loops, child-playbook
  references, decisions, manual inputs) is captured.
- `matches_example` byte-fidelity is intentionally NOT graded (it measures
  formatting, not competence -- see `ir_assertions.py`).
