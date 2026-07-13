#!/usr/bin/env bash
# Cut an fsr_playbooks release the standard way (see RELEASING.md), with guards.
#
#   scripts/release.sh 0.4.23 ["release notes text"]
#
# The published version is derived ENTIRELY from the git tag (hatch-vcs). This
# script tags `vX.Y.Z`, pushes it, and cuts a GitHub Release — the
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

# --- tag must be new -------------------------------------------------------
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "release: tag $TAG already exists locally — pick the next version" >&2; exit 1
fi
if git ls-remote --tags "$REMOTE" "$TAG" | grep -q "$TAG"; then
    echo "release: tag $TAG already on $REMOTE" >&2; exit 1
fi

# --- VERSION must beat PyPI's latest --------------------------------------
LATEST="$(curl -s --max-time 15 https://pypi.org/pypi/fsr-playbooks/json \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["info"]["version"])' 2>/dev/null || echo "")"
if [[ -n "$LATEST" ]]; then
    HIGHER="$(printf '%s\n%s\n' "$LATEST" "$VERSION" | sort -V | tail -1)"
    if [[ "$VERSION" == "$LATEST" || "$HIGHER" != "$VERSION" ]]; then
        echo "release: VERSION $VERSION is not greater than PyPI latest $LATEST" >&2
        echo "         (PyPI rejects re-uploads — pick a higher version)" >&2; exit 1
    fi
    echo ">> PyPI latest is $LATEST; releasing $VERSION"
else
    echo ">> WARN: could not read PyPI latest (offline?) — skipping the floor check" >&2
fi

# --- tests before tagging --------------------------------------------------
echo ">> running fast tests"
make tests

# --- tag, push, release ----------------------------------------------------
echo ">> tagging $TAG and pushing main + tag to $REMOTE"
git push "$REMOTE" main
git tag "$TAG"
git push "$REMOTE" "$TAG"

[[ -n "$NOTES" ]] || NOTES="Release $TAG. See CHANGELOG / commit history."
echo ">> cutting GitHub release $TAG (triggers Publish to PyPI)"
gh release create "$TAG" --title "$TAG" --notes "$NOTES"

echo ">> release created. Watch the publish workflow:"
echo "   gh run watch \$(gh run list --workflow=publish.yml --limit 1 --json databaseId -q '.[0].databaseId')"
echo ">> then bump the connector pin: fsr-playbooks==$VERSION (its build preflight verifies symbols)."
