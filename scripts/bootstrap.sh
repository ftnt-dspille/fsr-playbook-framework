#!/usr/bin/env bash
# One-command setup: fresh clone -> green, testable state.
#
#   make bootstrap            # interactive
#   ./scripts/bootstrap.sh    # same
#
# Idempotent: every step detects "already done" and skips. Prompts only when
# it genuinely needs input; honors env-var overrides so it can run unattended:
#   PYFSR_REPO=<git-url>      pyfsr sibling to clone if ../pyfsr is missing
#   FSR_DB_SRC=<path>         reference DB to copy into store/ if missing
#   NONINTERACTIVE=1          never prompt; take defaults / skip optional steps
set -uo pipefail

# A venv activated for some OTHER project (VIRTUAL_ENV / conda) hijacks
# `uv pip install` so deps land in the wrong env and this repo's .venv stays
# empty. Clear them so every uv command targets THIS project's .venv.
unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV 2>/dev/null || true

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DB="$ROOT/store/fsr_reference.db"
PYFSR_DIR="$ROOT/../pyfsr"

# --- pretty + prompt helpers ----------------------------------------------
say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$*"; exit 1; }

interactive() { [ -z "${NONINTERACTIVE:-}" ] && [ -t 0 ]; }

ask() {  # ask "prompt" "default" -> echoes answer (default if non-interactive/blank)
    local prompt="$1" default="${2:-}" ans=""
    if interactive; then
        read -r -p "    $prompt${default:+ [$default]}: " ans
    fi
    printf '%s' "${ans:-$default}"
}

confirm() {  # confirm "prompt" -> returns 0 for yes (default yes; auto-yes when non-interactive)
    interactive || return 0
    local ans; read -r -p "    $1 [Y/n]: " ans
    case "${ans:-y}" in [yY]*) return 0;; *) return 1;; esac
}

# --- 1. uv ----------------------------------------------------------------
say "1/6  toolchain (uv)"
if command -v uv >/dev/null 2>&1; then
    ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"
elif command -v brew >/dev/null 2>&1 && confirm "uv not found — install via brew?"; then
    brew install uv || die "brew install uv failed"
    ok "uv installed"
else
    die "uv required. Install: https://docs.astral.sh/uv/  (or 'brew install uv')"
fi

# --- 2. pyfsr sibling -----------------------------------------------------
say "2/6  pyfsr sibling (../pyfsr)"
if [ -d "$PYFSR_DIR" ]; then
    ok "present at $PYFSR_DIR"
else
    repo="${PYFSR_REPO:-}"
    [ -z "$repo" ] && repo="$(ask 'pyfsr git URL to clone (blank to skip)' '')"
    if [ -n "$repo" ]; then
        git clone "$repo" "$PYFSR_DIR" || die "clone failed: $repo"
        ok "cloned pyfsr"
    else
        warn "skipped — 'make sync' will fail without ../pyfsr (set PYFSR_REPO or clone it manually)"
    fi
fi

# --- 3. deps (venv + editable installs) -----------------------------------
say "3/6  python deps (uv venv + editable installs)"
make sync || die "make sync failed (is ../pyfsr present?)"
ok "deps installed (.venv)"

# --- 4. reference DB ------------------------------------------------------
say "4/6  reference store ($DB)"
if [ -f "$DB" ]; then
    ok "present ($(du -h "$DB" | cut -f1))"
else
    src="${FSR_DB_SRC:-}"
    if [ -z "$src" ] && interactive; then
        echo "    The 63MB reference DB is gitignored. Choose how to provide it:"
        echo "      [c] copy from a path you were given   [b] build from a live FSR box   [s] skip"
        choice="$(ask 'c/b/s' 'c')"
    else
        choice=$([ -n "$src" ] && echo c || echo s)
    fi
    case "$choice" in
        c|C)
            [ -z "$src" ] && src="$(ask 'path to fsr_reference.db' '')"
            [ -f "$src" ] || die "no file at: $src"
            mkdir -p "$ROOT/store"; cp "$src" "$DB"; ok "copied DB into store/" ;;
        b|B)
            [ -f "$ROOT/.env" ] || { warn ".env needed to reach a live box — set it up in step 5 first, then re-run with choice [b]"; }
            say "    building reference store (fsrpb probe --all) — needs live FSR creds in .env"
            uv run fsrpb probe --all || die "probe failed (check .env creds / box reachability)"
            ok "reference store built" ;;
        *)
            warn "skipped — reference/discovery tools and some fsr_core tests need the DB" ;;
    esac
fi

# --- 5. .env (live-only) --------------------------------------------------
say "5/6  .env (only needed for live probing / execution)"
if [ -f "$ROOT/.env" ]; then
    ok ".env present"
elif confirm "create .env from .env.example now? (offline work doesn't need it)"; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    base="$(ask 'FSR_BASE_URL (blank to fill later)' '')"
    key="$(ask 'FSR_API_KEY (blank to fill later)' '')"
    [ -n "$base" ] && { /usr/bin/sed -i.bak "s|^FSR_BASE_URL=.*|FSR_BASE_URL=$base|" "$ROOT/.env"; }
    [ -n "$key" ]  && { /usr/bin/sed -i.bak "s|^FSR_API_KEY=.*|FSR_API_KEY=$key|" "$ROOT/.env"; }
    rm -f "$ROOT/.env.bak"
    ok ".env created (edit it any time)"
else
    warn "skipped — copy .env.example to .env when you need live access"
fi

# --- 6. green-check -------------------------------------------------------
say "6/6  green-check (framework core test suite)"
if uv run python -m pytest fsr_core/tests/ -q; then
    echo
    ok "BOOTSTRAP COMPLETE — framework core is green."
    echo "    Next: 'fsrpb verify examples/<file>.yaml', or open this repo in an MCP"
    echo "    client (.mcp.json auto-registers fsr-read + fsrpb). See docs/FRAMEWORK_HANDOFF.md."
else
    echo
    warn "core tests did not fully pass — most often the reference DB is missing (step 4)."
    warn "Provide the DB and re-run 'make bootstrap'. See docs/FRAMEWORK_HANDOFF.md."
    exit 1
fi
