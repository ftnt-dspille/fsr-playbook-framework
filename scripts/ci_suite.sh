#!/usr/bin/env bash
# The ONE definition of the checks CI runs. .github/workflows/ci.yml calls
# these steps and scripts/release.sh calls `all`, so the release gate and the
# CI gate cannot drift into two different suites.
#
# Usage: scripts/ci_suite.sh <lint|types|tests-pkg|tests-tooling|all>
#   PY=<python>   interpreter with the deps installed (default: python3)
#   RUFF=<cmd>    ruff command (default: uvx ruff@0.15.20, pinned to pre-commit)
#
# types = `mypy` (fsr_playbooks/compiler, must be clean) + the ratchet gate
# (scripts/mypy_gate.py, fails on NEW errors in llm/ + mcp_server/). mypy is
# pinned to the uv.lock version because the baseline was measured on it.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-python3}"
RUFF="${RUFF:-uvx ruff@0.15.20}"
export PYTHONPATH="tooling${PYTHONPATH:+:$PYTHONPATH}"

step_lint()          { $RUFF check fsr_playbooks tooling conftest.py; }
step_types()         { "$PY" -m mypy && "$PY" scripts/mypy_gate.py; }
step_tests_pkg()     { "$PY" -m pytest fsr_playbooks/tests -q -m "not live and not slow"; }
# Own process: the two suites resolve different reference DBs and the root
# conftest refuses to collect both at once.
step_tests_tooling() { "$PY" -m pytest tooling/tests -q -m "not live and not slow"; }

case "${1:-}" in
  lint)          step_lint ;;
  types)         step_types ;;
  tests-pkg)     step_tests_pkg ;;
  tests-tooling) step_tests_tooling ;;
  all) step_lint; step_types; step_tests_pkg; step_tests_tooling ;;
  *) echo "usage: $0 <lint|types|tests-pkg|tests-tooling|all>" >&2; exit 2 ;;
esac
