#!/usr/bin/env bash
# hook_pass_cache.sh <id> -- <command...>
#
# Run a slow pre-commit gate (pytest-fast, mypy) once per CONTENT, not once per
# stage. The same gate is configured at pre-commit AND pre-push (pre-push is the
# net for a --no-verify commit), so a normal commit-then-push ran it twice on
# identical code.
#
#   pre-commit stage: run the command. On a pass, record the git TREE it ran on
#     (the index tree: pre-commit stashes unstaged edits, so the hook sees exactly
#     what is being committed) -- but only when no untracked file could have
#     influenced the run.
#   pre-push stage (PRE_COMMIT_TO_REF set): if the pushed commit's tree has a
#     recorded pass for this gate, skip; otherwise run the command as before.
#
# A tree hash names the exact content, so a hit means "this gate already passed
# on byte-identical files". The record lives in the git common dir (never
# committed, shared by worktrees). Bypass the cache: HOOK_PASS_CACHE=0.
set -uo pipefail

id="${1:?usage: hook_pass_cache.sh <id> -- <command...>}"; shift
[ "${1:-}" = "--" ] && shift
[ "$#" -gt 0 ] || { echo "hook_pass_cache: no command for $id" >&2; exit 2; }

common="$(git rev-parse --git-common-dir 2>/dev/null)" || exec "$@"
dir="$common/fsr-hook-pass/$id"

if [ "${HOOK_PASS_CACHE:-1}" = 0 ]; then exec "$@"; fi

record() {  # $1 = tree
  mkdir -p "$dir" && date -u +%Y-%m-%dT%H:%M:%SZ > "$dir/$1"
}

untracked_clean() {
  # An untracked file (a new test not yet added, a stray module) can change what
  # a run sees without being in the tree. Only cache a run that saw nothing extra.
  [ -z "$(git ls-files --others --exclude-standard 2>/dev/null | head -1)" ]
}

if [ -n "${PRE_COMMIT_TO_REF:-}" ]; then
  tree="$(git rev-parse -q --verify "${PRE_COMMIT_TO_REF}^{tree}" 2>/dev/null || true)"
  if [ -n "$tree" ] && [ -f "$dir/$tree" ]; then
    echo "$id: passed on this exact tree at commit ($(cat "$dir/$tree")); not re-run"
    exit 0
  fi
  "$@"; rc=$?
  # The push stage runs on the working tree. Record only when that IS the pushed
  # tree (clean checkout of the pushed commit).
  if [ "$rc" = 0 ] && [ -n "$tree" ] && [ "$(git rev-parse HEAD^{tree} 2>/dev/null)" = "$tree" ] \
      && git diff --quiet HEAD 2>/dev/null && untracked_clean; then
    record "$tree"
  fi
  exit "$rc"
fi

"$@"; rc=$?
if [ "$rc" = 0 ] && git diff --quiet 2>/dev/null && untracked_clean; then
  tree="$(git write-tree 2>/dev/null || true)"
  [ -n "$tree" ] && record "$tree"
fi
exit "$rc"
