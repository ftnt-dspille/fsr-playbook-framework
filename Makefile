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

.PHONY: backend frontend dev e2e tests clean help sync preflight kill-ports

PY        := uv run python
BACKEND_DIR := web/backend
FRONTEND_DIR := web/frontend
PORT_BACKEND  := 47821
PORT_FRONTEND := 47822

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync: ## create .venv (if missing) and install all editable deps via uv
	@command -v uv >/dev/null || { echo "uv not on PATH; install via: brew install uv"; exit 1; }
	@[ -d .venv ] || uv venv --python 3.13
	uv pip install -e ../pyfsr -e . -e ./web pytest requests-mock anyio

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

tests: ## fast pytest (excludes live + slow)
	$(PY) -m pytest python/tests/ -q -m "not live and not slow"

clean: ## remove pycache + node_modules build leftovers (NOT node_modules itself)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND_DIR)/.svelte-kit $(FRONTEND_DIR)/dist
