#!/usr/bin/env bash
# Pre-commit hook: run fsrpb checks on every staged playbook YAML.
#
# Install:
#   ln -s ../../scripts/external/pre-commit.fsrpb.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# What it runs (per staged YAML under examples/ or matching *.yaml in
# a known recipe path):
#   1. fsrpb validate              — compiler errors + linter rules
#   2. fsrpb resolve --json (best  — connector-installed + picklist
#      effort; skipped offline)      checks against the live FSR
#
# All checks are read-only; nothing mutates the FSR.

set -euo pipefail

# Resolve repo root + the python entrypoint regardless of where the
# hook fires from (worktree vs main checkout).
ROOT="$(git rev-parse --show-toplevel)"
PY="${ROOT}/python/cli.py"

if [[ ! -f "$PY" ]]; then
  echo "fsrpb pre-commit: cli.py not found at $PY — skipping" >&2
  exit 0
fi

mapfile -t YAML_FILES < <(
  git diff --cached --name-only --diff-filter=ACM \
  | grep -E '\.ya?ml$' \
  | grep -E '(^|/)(examples|recipes|playbooks)/' \
  || true
)

if [[ ${#YAML_FILES[@]} -eq 0 ]]; then
  exit 0
fi

echo "fsrpb pre-commit: checking ${#YAML_FILES[@]} playbook YAML(s)…"

failed=0
for f in "${YAML_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then continue; fi
  echo "  → $f"

  if ! python "$PY" validate "$f" >/dev/null 2>&1; then
    echo "    ✗ validate failed:"
    python "$PY" validate "$f" 2>&1 | sed 's/^/      /'
    failed=$((failed + 1))
    continue
  fi

  # `resolve` is best-effort: if no live FSR, it short-circuits with
  # "prechecks skipped" which we treat as success.
  if ! python "$PY" resolve "$f" --json >/dev/null 2>&1; then
    echo "    ! resolve flagged issues (live FSR):"
    python "$PY" resolve "$f" 2>&1 | sed 's/^/      /'
    failed=$((failed + 1))
  fi
done

if [[ $failed -gt 0 ]]; then
  echo "fsrpb pre-commit: $failed file(s) failed; commit aborted."
  echo "  bypass with: git commit --no-verify  (don't ship broken YAML)"
  exit 1
fi
echo "fsrpb pre-commit: ok"
