# FSR Playbook Studio — dev runner
#
# Common targets:
#   make backend     — start FastAPI on :8000 with autoreload
#   make frontend    — start Vite (Svelte) on :5173
#   make dev         — both, in parallel; Ctrl-C kills the group
#   make e2e         — run every examples/*.test.yaml against the live FSR
#   make tests       — fast pytest (excludes live + slow)
#
# Notes:
#   - Backend reads .env at the repo root (FSR_BASE_URL, ANTHROPIC_API_KEY, …).
#   - Frontend dev server proxies to the backend; keep both running.
#   - Python deps are managed by uv. `make sync` to install/update everything.
#     The Makefile uses `uv run` so it always picks the project venv at .venv/.

.PHONY: backend frontend dev e2e tests clean help sync

PY        := uv run python
BACKEND_DIR := web/backend
FRONTEND_DIR := web/frontend
PORT_BACKEND  := 8000
PORT_FRONTEND := 5173

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync: ## create .venv (if missing) and install all editable deps via uv
	@command -v uv >/dev/null || { echo "uv not on PATH; install via: brew install uv"; exit 1; }
	@[ -d .venv ] || uv venv --python 3.13
	uv pip install -e ../pyfsr -e . -e ./web pytest requests-mock anyio

backend: ## start FastAPI dev server (autoreload, :8000)
	$(PY) -m uvicorn --app-dir web backend.app:app --reload --port $(PORT_BACKEND)

frontend: ## start Vite dev server (Svelte, :5173)
	cd $(FRONTEND_DIR) && pnpm install --silent && pnpm dev

dev: ## run backend + frontend together; Ctrl-C kills both
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

e2e: ## run every examples/*.test.yaml against the live FSR (10/11 expected)
	cd python && uv run --project .. python -m cli e2e all

tests: ## fast pytest (excludes live + slow)
	$(PY) -m pytest python/tests/ -q -m "not live and not slow"

clean: ## remove pycache + node_modules build leftovers (NOT node_modules itself)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND_DIR)/.svelte-kit $(FRONTEND_DIR)/dist
