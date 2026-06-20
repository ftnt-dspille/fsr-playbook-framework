#!/usr/bin/env bash
# Publish a SANITIZED snapshot of this repo to the PUBLIC GitHub mirror.
#
# You work in ONE folder (this repo). This script builds a throwaway scrubbed
# copy from the committed HEAD tree, then force-pushes it as a single
# fresh-history commit to GitHub. Nothing sensitive ever enters public history
# because every publish is a squashed snapshot — not a history rewrite.
#
# What it strips (keep this list current as the repo grows):
#   - all state/runtime DBs + data dumps + captures (HAR, probe_results, eval_runs)
#   - the reference catalog is shipped SLIM: published connector corpus + jinja/
#     step reference only; instance-derived tables (modules, picklists,
#     module_fields, connector_icons, param_type_probes, connector_health) dropped
#   - internal planning/strategic docs + decks + infra scripts
#   - live infra strings (10.99.x, *.forticloud.com, internal gitlab) -> placeholders
#
# Usage:
#   scripts/publish_public.sh            # build, verify, push to GitHub
#   scripts/publish_public.sh --dry-run  # build + verify only; print tree; no push
#
# Requires: gh (authed as the repo owner), sqlite3, the local full
# data/fsr_reference.db present.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
GH_OWNER="${GH_OWNER:-ftnt-dspille}"
GH_REPO="${GH_REPO:-fsr-playbook-framework}"
REF_DB="$SRC/data/fsr_reference.db"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
echo ">> building sanitized snapshot in $BUILD"

# 1. export the committed tree (tracked files only — no untracked junk, no .git)
git -C "$SRC" archive HEAD | tar -x -C "$BUILD"
cd "$BUILD"

# 2. DROP — data blobs, captures, internal/strategic/planning docs, infra scripts
rm -f  fsrpb.db tooling/store/playbooks.db data/drafts.db data/store.db data/fsr_reference.json
rm -rf data/eval_runs data/probe_results data/incoming
rm -rf docs/archive docs/plans docs/research docs/corpus_audit scripts/internal
rm -f  docs/build_deck.py docs/FSR_Playbook_AI_Deepdive.pptx fsrpb_presentation.pptx \
       PRESENTATION_OUTLINE.md FSR_CONNECTOR_PLAN.md scripts/external/build_presentation.py
rm -f  web/PLAN.md web/ARCHITECTURE_HARDENING_PLAN.md web/UI_CONSOLIDATION_PLAN.md
# Root-level planning/strategy docs are internal by default (docs/plans/ is
# already stripped wholesale above). Glob, not named files, so a NEW *_PLAN.md
# at the repo root can't leak silently the way the regex check won't catch
# strategic content. NB: this also drops the previously-public REORG_PLAN.md
# and PYFSR_MIGRATION_PLAN.md from future snapshots.
rm -f  ./*_PLAN.md
rm -f  docs/AGENTIC_IR_ARCHITECTURE_REVIEW.md docs/AGENT_DATA_AUDIT.md docs/AGENT_DATA_GAPS.md \
       docs/AGENT_PROMPT_ADHERENCE.md docs/AGENT_TOOL_USAGE.md \
       docs/CONTINUE_DYNAMIC_TRIAGE.md docs/CONTINUE_TRIAGE_BEHAVIOR_FIXES.md docs/EVAL_PROMPTS.md \
       docs/FRAMEWORK_HANDOFF.md docs/CHAT_DEV_RUNBOOK.md
rm -f  TODO.md DEMO.md CLAUDE.md
rm -f  scripts/publish_public.sh   # internal tooling; also contains infra regexes
rm -rf scripts/git-hooks           # internal git hooks; pre-push carries the internal git host
find . -type d -name node_modules -prune -exec rm -rf {} + 2>/dev/null || true

# 3. SLIM the reference catalog (ship published corpus; drop instance-derived data)
if [[ ! -f "$REF_DB" ]]; then echo "!! missing $REF_DB (the full local catalog) — cannot build slim DB" >&2; exit 1; fi
cp -f "$REF_DB" data/fsr_reference.db
sqlite3 data/fsr_reference.db <<'SQL'
BEGIN;
DELETE FROM modules; DELETE FROM module_fields; DELETE FROM picklists;
DELETE FROM connector_icons; DELETE FROM param_type_probes; DELETE FROM connector_health;
DELETE FROM playbook_steps; DELETE FROM verifications; DELETE FROM jinja_expressions;
DELETE FROM api_endpoints; DELETE FROM api_endpoint_params; DELETE FROM api_endpoint_examples;
DELETE FROM recipes; DELETE FROM playbooks_seen; DELETE FROM _probe_runs;
DELETE FROM fsr_fts; DELETE FROM connector_op_defs;
COMMIT;
VACUUM;
SQL

# 4. REDACT live infra strings in remaining text files
python3 - <<'PY'
import re, pathlib
pats = [
    (re.compile(r"\b10\.99\.\d+\.\d+\b"), "<your-fortisoar-host>"),
    (re.compile(r"[a-z0-9-]+\.us-west-1\.fortisoc\.forticloud\.com"), "<your-fortisoar-host>"),
    (re.compile(r"\b[a-z0-9]+\.forticloud\.com"), "<your-fortisoar-host>"),
    # Any internal Fortinet host — *.fortilab.fortinet.com (gitlab, AI gateway,
    # …) and *.fndn.fortinet.net (Gitea). Broad on purpose so a new internal
    # hostname can't leak the way the AI gateway nearly did. Public Fortinet
    # URLs (repo.fortisoar.fortinet.com, sample @fortinet.com emails) don't
    # match these suffixes and are left alone.
    (re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.fortilab\.fortinet\.com"), "<internal-host>"),
    (re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.fndn\.fortinet\.net"), "<internal-git-host>"),
]
exts = {".py",".md",".ts",".svelte",".json",".yaml",".yml",".html",".sh",".txt",".cfg",".toml",".har"}
for p in pathlib.Path(".").rglob("*"):
    if not p.is_file() or p.suffix not in exts: continue
    try: t = p.read_text(encoding="utf-8")
    except Exception: continue
    n = t
    for rx, repl in pats: n = rx.sub(repl, n)
    if n != t: p.write_text(n, encoding="utf-8")
PY

# 5. allow the slim reference DB to ship (the repo gitignores *.db)
printf '\n# public mirror: ship the sanitized slim reference catalog\n!data/fsr_reference.db\n' >> .gitignore

# 6. VERIFY — no infra leaks, no stray data blobs
INFRA=$( { grep -rE "10\.99\.[0-9]+\.[0-9]+|us-west-1\.fortisoc\.forticloud\.com|[a-z0-9]+\.forticloud\.com|fortilab\.fortinet\.com|fndn\.fortinet\.net|svl-devops-gitlab01" . 2>/dev/null || true; } | { grep -av "fsr_reference.db" || true; } | wc -l | tr -d ' ')
BLOBS=$( { find . \( -name '*.db' ! -name 'fsr_reference.db' \) -o -name '*.har' -o -name 'fsr_reference.json' 2>/dev/null || true; } | wc -l | tr -d ' ')
echo ">> verify: infra-bearing text files=$INFRA  stray-blobs=$BLOBS  files=$(find . -type f | wc -l | tr -d ' ')  size=$(du -sh . | cut -f1)"
if [[ "$INFRA" != "0" || "$BLOBS" != "0" ]]; then echo "!! sanitation check FAILED — refusing to publish" >&2; exit 1; fi

if [[ "$DRY_RUN" == "1" ]]; then
    echo ">> --dry-run: snapshot built and verified at $BUILD (not pushed). Top level:"; ls -1
    trap - EXIT; echo ">> left build dir in place for inspection: $BUILD"; exit 0
fi

# 7. commit fresh history + force-push to GitHub (create repo on first run)
git init -q
git add -A
git -c user.name="Dylan Spille" -c user.email="dcspille@gmail.com" \
    commit -q -m "Public release — FSR Playbook Framework (sanitized snapshot)"
if ! gh repo view "$GH_OWNER/$GH_REPO" >/dev/null 2>&1; then
    echo ">> creating public repo $GH_OWNER/$GH_REPO"
    gh repo create "$GH_OWNER/$GH_REPO" --public --description "YAML → FortiSOAR playbook compiler + reference store, Svelte editor, MCP server" >/dev/null
fi
git remote add github "https://github.com/$GH_OWNER/$GH_REPO.git" 2>/dev/null || \
    git remote set-url github "https://github.com/$GH_OWNER/$GH_REPO.git"
git branch -M main
git push --force github main
echo ">> published https://github.com/$GH_OWNER/$GH_REPO"
