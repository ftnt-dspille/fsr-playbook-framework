# FSR Playbook Studio — dev runner
#
# Common targets:
#   make backend     — start FastAPI on :47821 with autoreload
#   make frontend    — start Vite (Svelte) on :47822
#   make dev         — both, in parallel; Ctrl-C kills the group
#   make e2e         — run every examples/*.test.yaml against the live FSR
#   make tests       — fast pytest (excludes live + slow)
#
# Notes:
#   - Backend reads .env at the repo root (FSR_BASE_URL, ANTHROPIC_API_KEY, …).
#   - Frontend dev server proxies to the backend; keep both running.
#   - Python deps are managed by uv. `make sync` to install/update everything.
#     The Makefile uses `uv run` so it always picks the project venv at .venv/.

.PHONY: backend frontend dev e2e tests verify lint clean help sync bootstrap preflight kill-ports chat-fast chat-drive chat-calibrate

PY        := uv run python
BACKEND_DIR := web/backend
FRONTEND_DIR := web/frontend
PORT_BACKEND  := 47821
PORT_FRONTEND := 47822

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

bootstrap: ## one-command setup: fresh clone -> green, testable state (prompts as needed)
	@bash scripts/bootstrap.sh

sync: ## create .venv (if missing) and install all editable deps via uv
	@command -v uv >/dev/null || { echo "uv not on PATH; install via: brew install uv"; exit 1; }
	@[ -d .venv ] || env -u VIRTUAL_ENV uv venv --python 3.13
	@# Clear a stray VIRTUAL_ENV/conda env so deps land in THIS repo's .venv,
	@# not whatever venv the caller happened to have active.
	env -u VIRTUAL_ENV -u CONDA_PREFIX uv pip install -e ../pyfsr -e . -e ./web pytest requests-mock anyio ruff

preflight: ## check dev ports are free; print holders if not
	@for p in $(PORT_BACKEND) $(PORT_FRONTEND); do \
	  pids=$$(lsof -ti tcp:$$p -sTCP:LISTEN 2>/dev/null); \
	  if [ -n "$$pids" ]; then \
	    echo "✗ port $$p is in use by:"; ps -o pid,command -p $$pids; \
	    echo "  → run 'make kill-ports' to free them, or stop the process manually"; \
	    exit 1; \
	  fi; \
	done; \
	echo "✓ ports $(PORT_BACKEND) and $(PORT_FRONTEND) are free"

kill-ports: ## kill anything holding the dev ports
	@for p in $(PORT_BACKEND) $(PORT_FRONTEND); do \
	  pids=$$(lsof -ti tcp:$$p -sTCP:LISTEN 2>/dev/null); \
	  [ -n "$$pids" ] && { echo "killing $$pids on :$$p"; kill $$pids; sleep 0.3; kill -9 $$pids 2>/dev/null; } || echo ":$$p already free"; \
	done

backend: ## start FastAPI dev server (autoreload, :47821)
	$(PY) -m uvicorn --app-dir web backend.app:app --reload --port $(PORT_BACKEND)

frontend: ## start Vite dev server (Svelte, :47822)
	cd $(FRONTEND_DIR) && pnpm install --silent && pnpm dev

dev: preflight ## run backend + frontend together; if either dies, both stop
	@trap 'kill 0' INT TERM EXIT; \
	( $(MAKE) backend; echo "[dev] backend exited"; kill 0 ) & \
	( $(MAKE) frontend; echo "[dev] frontend exited"; kill 0 ) & \
	wait

e2e: ## run every examples/*.test.yaml against the live FSR (10/11 expected)
	cd python && uv run --project .. python -m cli e2e all

tests: ## fast pytest (excludes live + slow); incl. the offline golden-trace pin
	$(PY) -m pytest python/tests/ -q -m "not live and not slow"

# ── Chat Intelligence tuning loop (docs/plans/CHAT_INTELLIGENCE_PLAN.md) ──
# chat-fast   = A4 cheap loop: offline STRUCTURE/contract guards (no API, secs).
#               Reach for this by default while tuning prompts/tools/intents;
#               it pins prompt assembly, intent routing, tool registry, the
#               gate→lever map (A3) and the golden-trace contract (A6).
# chat-drive  = live A1/A2: drive ONE scenario, score+render-validate, verdict.
# chat-calibrate = live capability gate over the whole investigation fixture set.
# chat-drive/chat-calibrate need .env FSR creds + ANTHROPIC_API_KEY + a reachable
# deployed connector; chat-fast needs neither.
SCENARIO ?=
MSG ?=

# The structure/contract suite — deterministic order (no:randomly) so a prompt
# edit that breaks assembly/routing reddens here in ~2s before any live spend.
CHAT_FAST_TESTS := \
	fsr_core/tests/test_triage_prompt.py \
	fsr_core/tests/test_triage_prompt_enrichment_offer.py \
	fsr_core/tests/test_triage_preflight.py \
	fsr_core/tests/test_low_signal_gate.py \
	fsr_core/tests/test_intent_slice_and_params.py \
	fsr_core/tests/test_build_prompt_skeleton.py \
	fsr_core/tests/test_playbook_offer.py \
	python/tests/test_run_turn.py \
	python/tests/test_catalog_tools.py \
	python/tests/test_emitter.py \
	python/tests/test_chat_review.py \
	python/tests/test_golden_traces_pin.py \
	python/tests/test_lever_coverage.py \
	python/tests/test_build_fidelity.py \
	python/tests/test_build_fidelity_golden.py

chat-fast: ## fast OFFLINE chat structure/contract guards (no API; ~2s)
	$(PY) -m pytest $(CHAT_FAST_TESTS) -q -p no:randomly
chat-drive: ## live: drive+score one scenario (SCENARIO=<fixture> or MSG="...")
	@if [ -n "$(SCENARIO)" ]; then \
		$(PY) python/cli.py chat-drive --task "$(SCENARIO)"; \
	elif [ -n "$(MSG)" ]; then \
		$(PY) python/cli.py chat-drive --message "$(MSG)"; \
	else \
		echo "usage: make chat-drive SCENARIO=<fixture-name>  |  MSG=\"...\""; exit 2; \
	fi

chat-calibrate: ## live: capability gate over every investigation fixture (costs credits)
	$(PY) python/evals/calibrate_investigation.py $(if $(SCENARIO),--only $(SCENARIO),)

lint: ## ruff lint (pyflakes F-rules) over fsr_core + python
	uv run ruff check fsr_core/ python/

# The connector + Angular widget both consume fsr_core, so the green-check that
# matters is fsr_core + the connector's offline suite — both run on THIS repo's
# .venv, which carries the editable fsr_core install and its deps (yaml, anthropic).
# (Do NOT use `uv run --extra test` in the connector: it builds an isolated env
#  without fsr_core, so its whole suite errors on ModuleNotFound.)
VENV_PY  := $(CURDIR)/.venv/bin/python
CONNECTOR_DIR := /Users/dylanspille/PycharmProjects/ConnectorsV2/fsr-playbook-builder

verify: ## green-check for the fsr_core + connector axis (offline)
	@echo "→ [1/2] fsr_core tests"
	$(VENV_PY) -m pytest fsr_core/tests/ -q
	@echo "→ [2/2] connector suite (offline; live tests self-skip)"
	cd $(CONNECTOR_DIR) && PYTHONPATH=. $(VENV_PY) -m pytest -q
	@echo "✓ verify passed"
	@echo "  (Angular widget has its own toolchain in WebStorm — not verifiable here.)"

clean: ## remove pycache + node_modules build leftovers (NOT node_modules itself)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND_DIR)/.svelte-kit $(FRONTEND_DIR)/dist

publish-public:        ## Build sanitized snapshot and force-push to the public GitHub mirror
	scripts/publish_public.sh

publish-public-dry:    ## Build + verify the sanitized snapshot only (no push)
	scripts/publish_public.sh --dry-run
