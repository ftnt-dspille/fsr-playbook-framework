#!/usr/bin/env bash
# Backend and frontend together; if either exits, both stop. `make dev` runs this.
#
# Lives in a script, not in the Makefile recipe, on purpose: a recipe line that
# mentions $(MAKE) runs even under `make -n`, so a `kill 0` there would signal
# the caller's whole process group. Here `make -n dev` only prints this one line.
#
# Each server runs in its own process group (job control), so stopping them
# signals only their groups. The make that started us is not signalled.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BACK=""
FRONT=""
stop() {
  trap - INT TERM EXIT
  for pgid in $BACK $FRONT; do kill -TERM -- "-$pgid" 2>/dev/null; done
  wait 2>/dev/null
}
trap 'stop; exit 130' INT TERM
trap stop EXIT
set -m
( make -C "$ROOT" backend; echo "[dev] backend exited" ) &
BACK=$!
( make -C "$ROOT" frontend; echo "[dev] frontend exited" ) &
FRONT=$!
wait -n
stop
