#!/usr/bin/env bash
# Cut an fsr_playbooks release the standard way (see RELEASING.md), with guards.
#
#   scripts/release.sh 0.4.23 ["release notes text"]
#
# The published version is derived ENTIRELY from the git tag (hatch-vcs). This
# script tags `vX.Y.Z`, pushes it, and cuts a GitHub Release -- the
# `Publish to PyPI` workflow fires on the release and uploads the wheel via
# Trusted Publishing (OIDC). No version literal is bumped anywhere.
#
# Guards (each a way past releases drifted):
#   * must be on `main` with a clean tree
#   * VERSION must be a bare X.Y.Z and strictly greater than PyPI's latest
#     (PyPI rejects re-uploads; tag-without-release once stranded 0.4.21)
#   * tag vX.Y.Z must not already exist
#   * fast tests must pass before tagging
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
NOTES="${2:-}"
[[ -n "$VERSION" ]] || { echo "usage: release.sh X.Y.Z [notes]" >&2; exit 2; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "release: VERSION must be a bare X.Y.Z (no 'v'), got '$VERSION'" >&2; exit 2; }
TAG="v$VERSION"

# --- remote pointing at the framework GitHub repo --------------------------
REMOTE="$(git remote -v | awk '/ftnt-dspille\/fsr-playbook-framework.*\(push\)/{print $1; exit}')"
REMOTE="${REMOTE:-origin}"

# --- branch + clean tree ---------------------------------------------------
[[ "$(git branch --show-current)" == "main" ]] || { echo "release: must be on main" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "release: working tree not clean" >&2; exit 1; }

# --- HEAD must not already carry a version tag ------------------------------
#
# #158. setuptools-scm derives the version from the tags on the commit being
# built, and when a commit carries more than one it does NOT take the one you
# just pushed -- it took the LOWER. That is silent: `release.sh 0.6.41` passed
# every guard above (v0.6.41 was genuinely new, and 0.6.41 genuinely beat
# PyPI's latest), the workflow went green, a GitHub Release for v0.6.41 exists
# -- and the wheel on PyPI is 0.6.40, because v0.6.40 was already sitting on
# HEAD. We only got away with it because the content was identical.
#
# The fix is upstream of all of that: a release needs a commit of its own. If
# HEAD is already tagged, there is nothing new to release from here.
EXISTING_ON_HEAD="$(git tag --points-at HEAD | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true)"
if [[ -n "$EXISTING_ON_HEAD" ]]; then
    echo "release: HEAD already carries a version tag:" >&2
    printf '  %s\n' $EXISTING_ON_HEAD >&2
    echo "  Tagging $TAG on this same commit would put two version tags on one" >&2
    echo "  commit, and setuptools-scm then publishes the LOWER one -- silently," >&2
    echo "  with a green workflow and a GitHub Release for the version you asked" >&2
    echo "  for. That is #158; it shipped 0.6.40 when 0.6.41 was requested." >&2
    echo "" >&2
    echo "  A release needs its own commit. Either land the change you meant to" >&2
    echo "  release, or -- if HEAD really is the content you want -- that content" >&2
    echo "  is already tagged, so check whether it needs releasing at all." >&2
    exit 1
fi

# --- tag must be new -------------------------------------------------------
#
# A tag can exist WITHOUT the version ever having been published: the publish
# workflow fires on a GitHub *release*, not on a tag push, so a tag pushed by
# hand strands. Nine of them (v0.6.30-v0.6.38) exist on this repo for exactly
# that reason, and the bare "pick the next version" message sent a reader
# looking for a wheel that was never built. Say which case this is.
tag_refusal() {
    local where="$1"
    echo "release: tag $TAG already $where." >&2
    if [[ "$PUBLISHED_AT_TAG_CHECK" == "yes" ]]; then
        echo "  PyPI serves $VERSION, so this version is already out -- pick a higher one." >&2
    else
        echo "  PyPI does NOT serve $VERSION (latest is ${LATEST_AT_TAG_CHECK:-unknown})." >&2
        echo "  That is a STRANDED tag: the publish workflow fires on a GitHub" >&2
        echo "  release, not on a tag push, so tagging by hand builds nothing." >&2
        echo "  Pick the next unused version -- do not try to reuse this tag." >&2
    fi
    exit 1
}
# One PyPI read, used to tell "already released" from "tagged but never built".
_PYPI_JSON="$(curl -s --max-time 15 https://pypi.org/pypi/fsr-playbooks/json || echo "")"
LATEST_AT_TAG_CHECK="$(printf '%s' "$_PYPI_JSON" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["info"]["version"])' 2>/dev/null || echo "")"
PUBLISHED_AT_TAG_CHECK="$(printf '%s' "$_PYPI_JSON" \
    | VERSION="$VERSION" python3 -c 'import sys,json,os;print("yes" if (json.load(sys.stdin).get("releases") or {}).get(os.environ["VERSION"]) else "no")' 2>/dev/null || echo "unknown")"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    tag_refusal "exists locally"
fi
if git ls-remote --tags "$REMOTE" "$TAG" | grep -q "$TAG"; then
    tag_refusal "is on $REMOTE"
fi

# --- VERSION must beat PyPI's latest --------------------------------------
LATEST="$(curl -s --max-time 15 https://pypi.org/pypi/fsr-playbooks/json \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["info"]["version"])' 2>/dev/null || echo "")"
if [[ -n "$LATEST" ]]; then
    HIGHER="$(printf '%s\n%s\n' "$LATEST" "$VERSION" | sort -V | tail -1)"
    if [[ "$VERSION" == "$LATEST" || "$HIGHER" != "$VERSION" ]]; then
        echo "release: VERSION $VERSION is not greater than PyPI latest $LATEST" >&2
        echo "         (PyPI rejects re-uploads -- pick a higher version)" >&2; exit 1
    fi
    echo ">> PyPI latest is $LATEST; releasing $VERSION"
else
    echo ">> WARN: could not read PyPI latest (offline?) -- skipping the floor check" >&2
fi

# --- tests before tagging --------------------------------------------------
echo ">> running fast tests"
make tests

# --- push main, then WAIT ON CI before making anything permanent -----------
# Order matters. Pushing main is reversible; a tag + GitHub Release is not, and
# the release is what triggers the PyPI upload. So CI is gated BEFORE the tag:
# a red main should stop a release, not be discovered after one.
#
# This gate was added on 2026-08-02 after `ci_watch.sh` was pointed at main for
# the first time and found it had been RED for five consecutive runs -- across
# releases 0.6.6, 0.6.7 and 0.6.8, every one of which published and shipped to a
# box. `publish.yml` builds and uploads; it does not run the tests. So the whole
# chain was green-looking while the test workflow was failing the entire time.
#
# SKIP_CI_WATCH=1 releases anyway. Deliberately an env var and not a flag: it
# should read as an exception someone chose, in the shell history, not as an
# option on equal footing with the default.
echo ">> pushing main to $REMOTE"
git push "$REMOTE" main
MAIN_SHA="$(git rev-parse HEAD)"

if [[ "${SKIP_CI_WATCH:-0}" == "1" ]]; then
    echo ">> SKIP_CI_WATCH=1 -- NOT waiting for CI. You are releasing untested main."
else
    bash "$ROOT/scripts/ci_watch.sh" --workflow ci.yml --ref "$MAIN_SHA" \
        --label "CI on main" || {
        echo "release: CI is red on main -- NOTHING was tagged or released." >&2
        echo "  Fix it, or release anyway with:  SKIP_CI_WATCH=1 $0 $VERSION" >&2
        exit 1
    }
fi

# --- tag, release, and watch the upload ------------------------------------
echo ">> tagging $TAG and pushing it to $REMOTE"
git tag "$TAG"
git push "$REMOTE" "$TAG"

[[ -n "$NOTES" ]] || NOTES="Release $TAG. See CHANGELOG / commit history."
echo ">> cutting GitHub release $TAG (triggers Publish to PyPI)"
gh release create "$TAG" --title "$TAG" --notes "$NOTES"

# Watched, not printed. The old code echoed a `gh run watch` command for a human
# to run, which meant a failed upload surfaced downstream as `release_and_ship`
# polling PyPI for its full 600s timeout and then reporting "not on PyPI" -- the
# symptom, ten minutes late, with nothing about the cause.
bash "$ROOT/scripts/ci_watch.sh" --workflow publish.yml --ref "$TAG" \
    --label "Publish to PyPI ($TAG)" || {
    echo "release: the PyPI upload for $TAG FAILED. The tag and GitHub Release" >&2
    echo "  exist, so this version is now BURNT -- PyPI rejects re-uploads of a" >&2
    echo "  version it has already seen, and a re-run publishing the same tag" >&2
    echo "  cannot succeed. Fix the workflow and release the NEXT patch." >&2
    exit 1
}
echo ">> then bump the connector pin + ship. Prefer the one command that waits for"
echo "   PyPI to actually serve the wheel before shipping:"
echo "     cd ../../ConnectorsV2/fsr-playbook-builder && make release-ship FW=$VERSION"
