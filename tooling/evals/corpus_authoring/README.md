# Playbook agent eval

Measures whether an agent driving the `fsr-agentic-toolkit` MCP tools can author
and repair FortiSOAR playbooks. Two scales:

- **The standard intelligence eval (`run_golden.py`) -- start here.** Six
  `claude -p` drives (3 authoring + 3 repair) over three committed, synthetic
  golden playbooks (`golden/*.yaml`). Fixed, portable (no local corpus, no
  connector-install noise), cheap enough to run routinely, and the same tasks
  every run. It is the standard scorecard for playbook-building intelligence.

      FSRPB_DEV=1 .venv/bin/python -m tooling.evals.corpus_authoring.run_golden \
          --out <local out> --env-file <box>

  Each golden probes one intelligence-relevant structure: `g1` multi-branch
  decision, `g2` loop/for_each, `g3` connector + record write. The repair half
  injects one deterministic defect per playbook (unknown-next / orphan step /
  missing required field) and grades detected / repaired / structure_preserved.

- **The full-corpus sweep (below) -- occasional, large.** Drives the authoring
  (`run_eval.py`) and repair (`run_repair.py`) loops across the real
  191-playbook corpus. Hundreds of subscription drives; run deliberately, not
  routinely.

## Full-corpus sweep

Measures authoring/repair against the structure of **real** FortiSOAR playbooks,
across the whole corpus (not a handful of curated fixtures).

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
