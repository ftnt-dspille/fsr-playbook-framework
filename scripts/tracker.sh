#!/usr/bin/env bash
# tracker.sh -- one-liner card ops for the SOC Assistant tracker
#
# The gh CLI's `gh issue` commands hit a Projects-classic GraphQL deprecation
# on the tracker repo, and `gh project item-edit` needs opaque field/option IDs.
# This wraps both so card ops are one-liners instead of hand-rolled API calls.
#
# Usage:
#   scripts/tracker.sh comment  <num> "body"            # post a comment
#   scripts/tracker.sh close    <num> ["reason"]        # close (completed|not_planned)
#   scripts/tracker.sh reopen   <num>                    # reopen
#   scripts/tracker.sh create   "title" "body"          # create an issue
#   scripts/tracker.sh status   <num> Todo|InProgress|Done
#   scripts/tracker.sh promise  <num> "P1 investigate|P2 gating|..."
#   scripts/tracker.sh horizon  <num> NOW|NEXT|LATER|PARKED
#   scripts/tracker.sh needsbox <num> "box-free|needs box|credential-gated"
#   scripts/tracker.sh component <num> "framework|connector|widget|..."
#   scripts/tracker.sh show     <num>                    # state + board fields
#   scripts/tracker.sh list     [status]                 # list issues (open|closed|all)
#
# Examples:
#   scripts/tracker.sh close 60 "completed"
#   scripts/tracker.sh create "Some new finding" "The body text..." promise "P2 gating" horizon NOW needsbox "box-free"
#   scripts/tracker.sh status 69 InProgress
#
set -euo pipefail

REPO="ftnt-dspille/soc-assistant-tracker"
PROJECT_ID="PVT_kwHOBe8ius4BfHXd"
PROJECT_NUM="1"
OWNER="ftnt-dspille"

# Board field IDs (Projects v2)
STATUS_FIELD="PVTSSF_lAHOBe8ius4BfHXdzhZcltA"
PROMISE_FIELD="PVTSSF_lAHOBe8ius4BfHXdzhZclwc"
HORIZON_FIELD="PVTSSF_lAHOBe8ius4BfHXdzhZclwg"
NEEDSBOX_FIELD="PVTSSF_lAHOBe8ius4BfHXdzhZclwo"
COMPONENT_FIELD="PVTSSF_lAHOBe8ius4BfHXdzhZclzM"

# Single-select option IDs (short forms)
declare -A STATUS_OPT=( [Todo]=f75ad846 [InProgress]=47fc9ee4 [Done]=98236657 )
declare -A PROMISE_OPT=(
  ["P1 investigate"]=92386ab6 ["P2 gating"]=ee160295 ["P3 reach"]=fd7e9e94
  ["P4 bottle it"]=79921915 ["Horizon (slide 16)"]=173c22ae [Infra]=ac987038 [Hygiene]=0724f09a
)
declare -A HORIZON_OPT=( [NOW]=5b618501 [NEXT]=de7be4a1 [LATER]=460ba78d [PARKED]=d13b2f98 )
declare -A NEEDSBOX_OPT=( ["box-free"]=f9c55b54 ["needs box"]=dc0a08c7 ["credential-gated"]=f9ec7acb )
declare -A COMPONENT_OPT=(
  [framework]=c2e30242 [connector]=8fc1215e [widget]=d3ba8bcb [monitor]=1b6c4a46
  [pyfsr]=88cbc450 [harness]=aaf424fd [cross-repo]=cb216349
)

# Resolve an issue number to its project item ID
item_id() {
  local num="$1"
  gh project item-list "$PROJECT_NUM" --owner "$OWNER" --limit 500 --format json 2>/dev/null \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('items', []):
    c = item.get('content', {})
    if c.get('number') == $num:
        print(item['id'])
        break
"
}

# Normalize a field value name to its option ID
resolve_opt() {
  local field="$1" value="$2"
  local -n opts="${field}_OPT"
  for key in "${!opts[@]}"; do
    if [[ "${key,,}" == "${value,,}" ]]; then
      echo "${opts[$key]}"
      return 0
    fi
  done
  echo "ERROR: unknown $field option '$value'. Valid: ${!opts[@]}" >&2
  return 1
}

cmd_comment() {
  local num="$1" body="${2:-}"
  [[ -n "$body" ]] || { echo "usage: tracker.sh comment <num> \"body\"" >&2; exit 1; }
  local tmp; tmp=$(mktemp); printf '%s' "$body" > "$tmp"
  gh api "repos/$REPO/issues/$num/comments" -F "body=@$tmp" --jq '.html_url' 2>&1
  rm -f "$tmp"
}

cmd_close() {
  local num="$1" reason="${2:-completed}"
  gh api "repos/$REPO/issues/$num" -X PATCH -f state=closed -f "state_reason=$reason" --jq '.html_url' 2>&1
  # Also set Status=Done on the board
  local iid; iid=$(item_id "$num")
  if [[ -n "$iid" ]]; then
    gh project item-edit --id "$iid" --field-id "$STATUS_FIELD" \
      --project-id "$PROJECT_ID" --single-select-option-id "${STATUS_OPT[Done]}" 2>/dev/null || true
  fi
}

cmd_reopen() {
  local num="$1"
  gh api "repos/$REPO/issues/$num" -X PATCH -f state=open --jq '.html_url' 2>&1
}

cmd_create() {
  local title="$1" body="${2:-}"
  local labels="" promise="" horizon="" needsbox="" component=""
  shift 2 || true
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --label) labels="${labels:+$labels,}$2"; shift 2 ;;
      --promise) promise="$2"; shift 2 ;;
      --horizon) horizon="$2"; shift 2 ;;
      --needsbox) needsbox="$2"; shift 2 ;;
      --component) component="$2"; shift 2 ;;
      *) echo "unknown create flag: $1" >&2; shift ;;
    esac
  done
  local tmp; tmp=$(mktemp); printf '%s' "$body" > "$tmp"
  local url
  url=$(gh api "repos/$REPO/issues" -f title="$title" -F "body=@$tmp" ${labels:+-f labels="$labels"} --jq '.html_url')
  rm -f "$tmp"
  local num; num=$(echo "$url" | grep -oE '[0-9]+$')
  echo "$url (#$num)"
  # Link to the board project
  gh project item-add "$PROJECT_NUM" --owner "$OWNER" --url "$url" 2>/dev/null || true
  # Set board fields
  if [[ -n "$promise" ]]; then set_field "$num" PROMISE "$promise"; fi
  if [[ -n "$horizon" ]]; then set_field "$num" HORIZON "$horizon"; fi
  if [[ -n "$needsbox" ]]; then set_field "$num" NEEDSBOX "$needsbox"; fi
  if [[ -n "$component" ]]; then set_field "$num" COMPONENT "$component"; fi
  [[ -n "$promise$horizon$needsbox$component" ]] || set_field "$num" STATUS Todo
}

set_field() {
  local num="$1" field="$2" value="$3"
  local iid; iid=$(item_id "$num")
  [[ -n "$iid" ]] || { echo "no board item for #$num" >&2; return 1; }
  local fid="" oid=""
  case "$field" in
    STATUS)   fid="$STATUS_FIELD";   oid=$(resolve_opt STATUS "$value") ;;
    PROMISE)  fid="$PROMISE_FIELD";  oid=$(resolve_opt PROMISE "$value") ;;
    HORIZON)  fid="$HORIZON_FIELD";  oid=$(resolve_opt HORIZON "$value") ;;
    NEEDSBOX) fid="$NEEDSBOX_FIELD"; oid=$(resolve_opt NEEDSBOX "$value") ;;
    COMPONENT)fid="$COMPONENT_FIELD";oid=$(resolve_opt COMPONENT "$value") ;;
    *) echo "unknown field: $field" >&2; return 1 ;;
  esac
  [[ -n "$oid" ]] || return 1
  gh project item-edit --id "$iid" --field-id "$fid" \
    --project-id "$PROJECT_ID" --single-select-option-id "$oid" 2>&1 | head -1
}

cmd_status()   { set_field "$1" STATUS "$2"; }
cmd_promise()  { set_field "$1" PROMISE "$2"; }
cmd_horizon()  { set_field "$1" HORIZON "$2"; }
cmd_needsbox() { set_field "$1" NEEDSBOX "$2"; }
cmd_component() { set_field "$1" COMPONENT "$2"; }

cmd_show() {
  local num="$1"
  local state title
  state=$(gh api "repos/$REPO/issues/$num" --jq '.state' 2>/dev/null)
  title=$(gh api "repos/$REPO/issues/$num" --jq '.title' 2>/dev/null)
  echo "#$num [$state] $title"
  # Show board fields
  local iid; iid=$(item_id "$num")
  if [[ -n "$iid" ]]; then
    gh project item-list "$PROJECT_NUM" --owner "$OWNER" --limit 500 --format json 2>/dev/null \
      | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data.get('items', []):
    if item['id'] != '$iid': continue
    for fv in item.get('fieldValues', []):
        name = fv.get('name', '')
        val = fv.get('text') or fv.get('title') or ''
        if name and val:
            print(f'  {name}: {val}')
        elif name and fv.get('optionIds'):
            print(f'  {name}: (set)')
    " 2>/dev/null
  fi
}

cmd_list() {
  local state="${1:-open}"
  gh api "repos/$REPO/issues?state=$state&per_page=100" --jq '.[] | "#\(.number) [\(.state)] \(.title)"' 2>&1
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    comment)  cmd_comment "$@" ;;
    close)    cmd_close "$@" ;;
    reopen)   cmd_reopen "$@" ;;
    create)   cmd_create "$@" ;;
    status)   cmd_status "$@" ;;
    promise)  cmd_promise "$@" ;;
    horizon)  cmd_horizon "$@" ;;
    needsbox) cmd_needsbox "$@" ;;
    component) cmd_component "$@" ;;
    show)     cmd_show "$@" ;;
    list)     cmd_list "$@" ;;
    help|-h|--help) sed -n '1,30p' "$0" ;;
    *) echo "unknown command: $cmd (try --help)" >&2; exit 1 ;;
  esac
}

main "$@"
