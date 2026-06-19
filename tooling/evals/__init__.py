"""LLM-evaluation harness for FSR playbook authoring.

`python/eval/` runs a fixed task set through one or more LLM providers
and scores each candidate playbook against the success ladder
(Compiles: parses + static checks pass, Runs: live FSR executes,
Works: post-run assertions hold) plus an optional gold-fixture
byte-equality check. Output is a structured matrix the demo can publish as
"LLM-agnostic by measurement, not claim."

Sub-modules:
  scoring   — pure scoring functions over a candidate YAML.
  tasks     — declarative task fixtures (prompt + gold + assertions).
  providers — pluggable model callables (anthropic, openai, lmstudio,
              echo for hermetic testing).
  harness   — task × model × score matrix runner.
"""
from __future__ import annotations
