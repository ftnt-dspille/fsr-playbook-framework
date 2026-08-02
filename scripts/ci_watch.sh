#!/usr/bin/env bash
# Watch a GitHub Actions run to completion and FAIL LOUDLY if it fails.
#
#   ci_watch.sh --workflow publish.yml [--ref <sha-or-tag>] [--timeout 900]
#               [--label "publish to PyPI"] [--require]
#
# Why this exists: `release.sh` used to PRINT a `gh run watch ...` command and
# trust a human to run it. Nobody does. The failure mode that produced this
# script: a red `Publish to PyPI` is invisible, so `release_and_ship.sh` goes on
# to poll PyPI for its full 600s timeout and then reports "not on PyPI" -- ten
# minutes of waiting for a message that names the symptom and not one word of
# the cause. Watching turns that into a ~30s failure that links the run.
#
# Exit codes:
#   0  the run succeeded, OR gh is unavailable and --require was not passed
#   1  the run failed / was cancelled / timed out
#   2  usage error
set -euo pipefail

WORKFLOW="" ; REF="" ; TIMEOUT=900 ; LABEL="" ; REQUIRE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workflow) WORKFLOW="$2"; shift 2 ;;
        --ref)      REF="$2";      shift 2 ;;
        --timeout)  TIMEOUT="$2";  shift 2 ;;
        --label)    LABEL="$2";    shift 2 ;;
        --require)  REQUIRE=1;     shift ;;
        *) echo "ci_watch: unknown arg: $1" >&2; exit 2 ;;
    esac
done
[[ -n "$WORKFLOW" ]] || { echo "ci_watch: --workflow is required" >&2; exit 2; }
LABEL="${LABEL:-$WORKFLOW}"

say()  { printf '\033[1m>> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mWARN: %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFAIL: %s\033[0m\n' "$*" >&2; }

# --- gh must be present AND authenticated ---------------------------------
# Soft by default: a missing `gh` must not block a release on a laptop that
# cannot watch. Pass --require where an unwatched run is itself unacceptable.
if ! command -v gh >/dev/null 2>&1 || ! gh auth status >/dev/null 2>&1; then
    msg="cannot watch '$LABEL' -- gh is missing or not authenticated.
     Watch it yourself:  gh run list --workflow=$WORKFLOW --limit 5"
    if [[ "$REQUIRE" -eq 1 ]]; then fail "$msg"; exit 1; fi
    warn "$msg"
    exit 0
fi

# --- find the run ----------------------------------------------------------
# The subtle part, and the reason this is not a one-liner. A run does not exist
# the instant you push -- GitHub takes a few seconds to register it. Grabbing
# "the latest run" immediately returns the PREVIOUS run, which is almost always
# green, so the watch reports success for work it never saw. That is a false
# green on the exact signal we added this for. So: when a --ref is given, we
# poll until a run for THAT sha appears, and never settle for another.
#
# --ref matches EITHER the head sha OR the display title. A push-triggered run
# is identified by its sha; a release-triggered one shows the tag (`v0.6.9`) as
# its title, and its head sha is the tagged commit -- which is also the sha of
# the push run, so matching on sha alone cannot tell the two apart.
find_run() {
    if [[ -n "$REF" ]]; then
        gh run list --workflow="$WORKFLOW" --limit 30 \
            --json databaseId,headSha,displayTitle,url \
            -q "[.[] | select((.headSha | startswith(\"$REF\")) or (.displayTitle == \"$REF\"))] | .[0].databaseId" \
            2>/dev/null
    else
        gh run list --workflow="$WORKFLOW" --limit 1 \
            --json databaseId -q '.[0].databaseId' 2>/dev/null
    fi
}

say "waiting for '$LABEL' to appear${REF:+ (ref ${REF:0:12})}"
RUN_ID=""
for _ in $(seq 1 30); do          # up to ~90s for the run to register
    RUN_ID="$(find_run || true)"
    [[ -n "$RUN_ID" && "$RUN_ID" != "null" ]] && break
    sleep 3
done

if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
    msg="no '$LABEL' run appeared${REF:+ for ${REF:0:12}} within 90s.
     It may not be triggered for this event. Check:
       gh run list --workflow=$WORKFLOW --limit 5"
    if [[ "$REQUIRE" -eq 1 ]]; then fail "$msg"; exit 1; fi
    warn "$msg"
    exit 0
fi

URL="$(gh run view "$RUN_ID" --json url -q .url 2>/dev/null || echo "")"
say "watching '$LABEL' run $RUN_ID  ${URL}"

# --exit-status makes gh itself return non-zero on a failed conclusion, so a
# red run cannot be mistaken for a finished one. `timeout` bounds a run that
# hangs (a queued job with no available runner will otherwise sit forever).
if command -v timeout >/dev/null 2>&1; then
    WATCH=(timeout "$TIMEOUT" gh run watch "$RUN_ID" --exit-status --interval 10)
else                              # macOS without coreutils: no timeout(1)
    WATCH=(gh run watch "$RUN_ID" --exit-status --interval 10)
fi

if "${WATCH[@]}"; then
    say "'$LABEL' PASSED"
    exit 0
fi

rc=$?
fail "'$LABEL' did not pass (exit $rc).  $URL"
echo "--- failing job logs (tail) -----------------------------------------"
gh run view "$RUN_ID" --log-failed 2>/dev/null | tail -n 40 \
    || echo "(could not fetch logs -- open $URL)"
echo "---------------------------------------------------------------------"
exit 1
