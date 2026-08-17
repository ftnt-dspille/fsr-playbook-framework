# FSR Playbook Studio -- dev runner
#
# Common targets:
#   make backend     -- start FastAPI on :47821 with autoreload
#   make frontend    -- start Vite (Svelte) on :47822
#   make dev         -- both, in parallel; Ctrl-C kills the group
#   make e2e         -- run every examples/*.test.yaml against the live FSR
#   make tests       -- fast pytest (excludes live + slow)
#   make tests-random-- every offline suite under 3 randomized orders
#
# Notes:
#   - Backend reads .env at the repo root (FSR_BASE_URL, ANTHROPIC_API_KEY, …).
#   - Frontend dev server proxies to the backend; keep both running.
#   - Python deps are managed by uv. `make sync` to install/update everything.
#     The Makefile uses `uv run` so it always picks the project venv at .venv/.

.PHONY: backend frontend dev e2e tests verify lint clean help sync bootstrap preflight kill-ports chat-fast chat-drive chat-calibrate release ci-watch corpus-gate corpus-gen tool-gate mypy-gate wire-audit wire-census test-effect-probes

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
	@# pytest-randomly powers `make tests-random` (the order-dependence gate).
	env -u VIRTUAL_ENV -u CONDA_PREFIX uv pip install -e ../pyfsr -e . -e ./web pytest pytest-randomly requests-mock anyio ruff

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
	cd tooling && uv run --project .. python -m cli e2e all

tests: ## fast pytest (excludes live + slow); incl. the offline golden-trace pin
	$(PY) -m pytest tooling/tests/ -q -m "not live and not slow"

# Order-dependence gate (PLAN_testing_that_can_fail 0.3). A suite whose tests
# leak state into one another can go green for reasons unrelated to the code --
# the same "passes for the wrong reason" family as everything else in that plan,
# one level up. pytest-randomly shuffles collection; three FIXED seeds keep this
# target reproducible while still varying the order (a random seed per run turns
# a real leak into an intermittent red nobody can reproduce).
#
# It found two real leaks on the day it was added: the FSR live-client seam that
# `local_turn` rebinds and never restores, and the global approval-grant table.
RANDOM_SEEDS ?= 1 7 42
tests-random: ## run every offline suite under 3 randomized collection orders
	@for s in $(RANDOM_SEEDS); do \
	  echo "→ seed $$s"; \
	  $(VENV_PY) -m pytest fsr_playbooks/tests/ -q --randomly-seed=$$s || exit 1; \
	  $(VENV_PY) -m pytest tooling/tests/ -q -m "not live and not slow" --randomly-seed=$$s || exit 1; \
	  (cd $(CONNECTOR_DIR) && PYTHONPATH=. $(VENV_PY) -m pytest -q --randomly-seed=$$s) || exit 1; \
	done
	@echo "✓ no order-dependent tests under seeds: $(RANDOM_SEEDS)"

release: ## cut a PyPI release: make release VERSION=0.4.23 [NOTES="..."] (see RELEASING.md)
	@[ -n "$(VERSION)" ] || { echo "usage: make release VERSION=X.Y.Z [NOTES=\"...\"]"; exit 2; }
	@bash scripts/release.sh "$(VERSION)" "$(NOTES)"

ci-watch: ## Watch CI on the current commit and fail if it is red (WORKFLOW=ci.yml REF=<sha>)
	@bash scripts/ci_watch.sh --workflow "$(or $(WORKFLOW),ci.yml)" \
	    --ref "$(or $(REF),$(shell git rev-parse HEAD))" --label "$(or $(WORKFLOW),CI)"

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

# The structure/contract suite -- deterministic order (no:randomly) so a prompt
# edit that breaks assembly/routing reddens here in ~2s before any live spend.
CHAT_FAST_TESTS := \
	fsr_playbooks/tests/test_triage_prompt.py \
	fsr_playbooks/tests/test_triage_prompt_enrichment_offer.py \
	fsr_playbooks/tests/test_triage_preflight.py \
	fsr_playbooks/tests/test_low_signal_gate.py \
	fsr_playbooks/tests/test_triage_discipline.py \
	fsr_playbooks/tests/test_intent_slice_and_params.py \
	fsr_playbooks/tests/test_build_prompt_skeleton.py \
	fsr_playbooks/tests/test_playbook_offer.py \
	fsr_playbooks/tests/test_enhancement_offer.py \
	tooling/tests/test_evals_enhance_delivery.py \
	tooling/tests/test_run_turn.py \
	tooling/tests/test_catalog_tools.py \
	tooling/tests/test_emitter.py \
	tooling/tests/test_chat_review.py \
	tooling/tests/test_golden_traces_pin.py \
	tooling/tests/test_lever_coverage.py \
	tooling/tests/test_build_fidelity.py \
	tooling/tests/test_build_fidelity_golden.py \
	tooling/tests/test_hunt_depth.py

chat-fast: ## fast OFFLINE chat structure/contract guards (no API; ~2s)
	$(PY) -m pytest $(CHAT_FAST_TESTS) -q -p no:randomly
chat-drive: ## live: drive+score one scenario (SCENARIO=<fixture> or MSG="...")
	@if [ -n "$(SCENARIO)" ]; then \
		$(PY) tooling/cli.py chat-drive --task "$(SCENARIO)"; \
	elif [ -n "$(MSG)" ]; then \
		$(PY) tooling/cli.py chat-drive --message "$(MSG)"; \
	else \
		echo "usage: make chat-drive SCENARIO=<fixture-name>  |  MSG=\"...\""; exit 2; \
	fi

chat-calibrate: ## live: capability gate over every investigation fixture (costs credits)
	$(PY) tooling/evals/calibrate_investigation.py $(if $(SCENARIO),--only $(SCENARIO),)

enhance-live: ## live: enhance-DELIVERY gate -- drive every enhance_scenario, grade emit_enhancement_offer vs prose (SCENARIO=<name> RUNS=n CONFIG=name). Needs .env + deployed connector.
	$(PY) tooling/evals/enhance_live.py $(if $(SCENARIO),--only $(SCENARIO),) $(if $(RUNS),--runs $(RUNS),) $(if $(CONFIG),--config $(CONFIG),)

lint: ## ruff lint (pyflakes F-rules) over fsr_playbooks + tooling
	uv run ruff check fsr_playbooks/ tooling/

# The connector + Angular widget both consume fsr_playbooks, so the green-check that
# matters is fsr_playbooks + the connector's offline suite -- both run on THIS repo's
# .venv, which carries the editable fsr_playbooks install and its deps (yaml, anthropic).
# (Do NOT use `uv run --extra test` in the connector: it builds an isolated env
#  without fsr_playbooks, so its whole suite errors on ModuleNotFound.)
VENV_PY  := $(CURDIR)/.venv/bin/python
CONNECTOR_DIR := ../ConnectorsV2/fsr-playbook-builder

# The eval harness registers the connector's triage tools (get_record,
# search_module_records) only when it can find the checkout, and without them
# every invest_* fixture is unservable -- calibrate refuses to run rather than
# report a corpus of 0.0s. This Makefile already knows where the connector is,
# so default the var it looks for instead of making each caller export it.
# `?=` still yields to an explicitly-set environment value.
export FSR_CONNECTOR_REPO ?= $(abspath $(CONNECTOR_DIR))

corpus-gate: ## round-trip fidelity gate over the committed corpus (box-free). CORPUS_DIR=… MIN_PASS=… to measure a real box pull
	FSRPB_DEV=1 $(VENV_PY) scripts/corpus_gate.py \
	  $(if $(CORPUS_DIR),--corpus-dir $(CORPUS_DIR),) \
	  $(if $(MIN_PASS),--min-pass $(MIN_PASS),)

# The 5 `mode=tool_selection` fixtures. Deliberately NOT the whole 36-task
# corpus: the other 31 are either saturated YAML authoring that corpus-gate
# already covers, or investigation tasks whose tool loop leans hard on a live
# appliance -- when that box degrades, their scores slide and read as "the
# agent regressed" when nothing about the agent changed. These 5 terminate on
# the first correct tool call, so they barely touch the box and stay honest.
TOOL_GATE_TASKS := select_run_playbook,select_build_offer,select_enhance_offer,select_diagnose_failure,select_run_playbook_neutral
# 20260814T115728Z: agentic_frank 20/20, and the first baseline that SAYS WHAT
# IT WAS TAKEN ON -- offline=True, tool_substrate=framework+connector,
# record_substrate=empty. Its predecessor (20260813T153315Z) predates those
# fields entirely, so every diff against it compared against an unknown world;
# `delta_vs` now prints a SUBSTRATE MISMATCH banner instead of letting that
# pass. Run this gate with FSR_CONNECTOR_REPO set to match the pin, or expect
# (and read) the banner.
# Captured after two corrections that the diff itself surfaced: a corrupt
# reference DB that made `find_operation` raise intermittently, and a
# `no_spiral` gate that counted five lookups of five DIFFERENT step types as a
# spiral.
# data/eval_runs/ is gitignored, so a fresh checkout has no baseline to diff
# against and must capture its own before a delta means anything.
TOOL_GATE_BASELINE ?= 20260817T153958Z

tool-gate: ## which tool does the agent reach for? Run after ANY tool-description / system-prompt / tool-set change -- nothing else covers routing. BASELINE=<run_id> REPEAT=3 OFFLINE=1
	@echo "note: the score is composite (#127), so a row can CLIMB, not just"
	@echo "      drop: terminal_tool_reached + offer_timing +"
	@echo "      appropriate_approval_requests + no_spiral. Every run is saved;"
	@echo "      re-baseline with 'make tool-gate BASELINE=' and pin the new id."
	@echo "      OFFLINE=1 binds the tools to the simulated client (no box)."
	@echo "      2026-08-13: offline reproduced the live baseline exactly, 20/20."
	@echo "      A SUBSTRATE MISMATCH banner means the two runs saw different"
	@echo "      worlds -- fix that before reading a single cell."
	FSR_TIMEOUT=$${FSR_TIMEOUT:-60} PYTHONUNBUFFERED=1 $(VENV_PY) tooling/cli.py evals \
	  --tasks $(TOOL_GATE_TASKS) --save $(if $(OFFLINE),--offline,) \
	  $(if $(REPEAT),--repeat $(REPEAT),) \
	  $(if $(TOOL_GATE_BASELINE),--baseline $(TOOL_GATE_BASELINE),)

test-effect-probes: ## LIVE: does the affordance actually WRITE? Seeds a scratch playbook, drives the widget's exact payload, re-reads the box. ONLY=A5,A2,A3 RUNS=2 DUMP=dir FSR_ENV_FILE=.env.159
	@echo "▶ effect probes -- every verdict is a box read, never a card or an ok flag."
	@echo "  BLOCKED = the card under test never appeared, so the write path was"
	@echo "  not exercised (usually #132). That exits non-zero on purpose."
	PYTHONPATH=. $(VENV_PY) -W ignore tooling/probes/effect/runner.py \
	  $(if $(ONLY),--only $(ONLY),) $(if $(RUNS),--runs $(RUNS),) \
	  $(if $(DUMP),--dump $(DUMP),)

wire-audit: ## LIVE: validate every playbook on the box against the wire models + measure semantic round-trip fidelity. Read-only. Run after any wire/decompiler/emitter change. LIMIT=… FILTER=…
	PYTHONPATH=. $(VENV_PY) -W ignore tooling/probes/probe_wire_shapes.py \
	  $(if $(LIMIT),--limit $(LIMIT),)
	PYTHONPATH=. $(VENV_PY) -W ignore tooling/probes/probe_mapping_fidelity.py \
	  $(if $(LIMIT),--limit $(LIMIT),) $(if $(FILTER),--filter $(FILTER),)

wire-census: ## LIVE: regenerate the committed shape census the box-free conformance test reads
	PYTHONPATH=. $(VENV_PY) -W ignore tooling/probes/probe_wire_shapes.py \
	  --census fsr_playbooks/tests/fixtures/wire_shape_census.json

corpus-triage: ## COMPILABILITY triage over a corpus (box-free): which real playbooks fail to compile, grouped by cause. corpus-gate measures fidelity; this measures acceptance. CORPUS_DIR=… TOP=… MIN_PASS=… ARGS='--markdown'
	FSRPB_DEV=1 $(VENV_PY) scripts/corpus_compile_triage.py \
	  $(if $(CORPUS_DIR),--corpus-dir $(CORPUS_DIR),) \
	  $(if $(TOP),--top $(TOP),) \
	  $(if $(MIN_PASS),--min-pass $(MIN_PASS),) $(ARGS)

corpus-gen: ## regenerate the committed round-trip corpus fixtures
	FSRPB_DEV=1 $(VENV_PY) scripts/gen_roundtrip_corpus.py

mypy: ## mypy type-check over fsr_playbooks/compiler (default config; not --strict)
	$(VENV_PY) -m mypy

mypy-gate: ## ratchet gate: fail on NEW mypy errors in llm/ + mcp_server/ (baseline docs/typing/mypy_ratchet.json)
	$(VENV_PY) scripts/mypy_gate.py

doctor: ## environment preflight: version resolution, pyfsr floor, reference DB
	$(VENV_PY) -m fsr_playbooks.doctor

# The reference store is in WAL mode, so it is a THREE-file database. Restoring
# it with a plain `cp` leaves the previous `-wal`/`-shm` beside the fresh file
# and SQLite replays that stale journal into it on the next open -- the restore
# reads clean, then the very first process to touch it corrupts it. That is how
# this store got corrupted three times in three days; each "recurrence" was the
# repair. Always restore through this target.
#
# `.recover` is deliberately NOT offered as the fix: it produces a file that
# passes integrity_check while stranding unattributable rows in lost_and_found
# (it silently dropped 9 fortisiem operations once), and merging the old tables
# back with INSERT OR IGNORE doubles every table lacking a unique constraint.
# A known-good .bak is the answer whenever one exists.
db-restore: ## restore data/fsr_reference.db from FROM=<backup> (default .db.bak), WAL-safely
	@set -eu; \
	src="$(if $(FROM),$(FROM),data/fsr_reference.db.bak)"; \
	dst=data/fsr_reference.db; \
	test -f "$$src" || { echo "no such backup: $$src"; exit 2; }; \
	sqlite3 "$$src" "pragma quick_check;" | grep -qx ok \
	  || { echo "REFUSING: backup is itself corrupt: $$src"; exit 2; }; \
	if [ -f "$$dst" ]; then \
	  if sqlite3 "$$dst" "pragma quick_check;" 2>/dev/null | grep -qx ok; then \
	    kind=prev; else kind=corrupt; fi; \
	  stamp=data/fsr_reference.$$kind-$$(date +%Y%m%dT%H%M%S).db.bak; \
	  echo "→ setting aside current store ($$kind) as $$stamp"; mv "$$dst" "$$stamp"; \
	fi; \
	rm -f "$$dst-wal" "$$dst-shm"; \
	cp "$$src" "$$dst"; \
	sqlite3 "$$dst" "pragma quick_check;" | grep -qx ok \
	  || { echo "restore FAILED integrity check"; exit 1; }; \
	echo "✓ restored $$dst from $$src"; \
	$(VENV_PY) -m fsr_playbooks.doctor

verify: ## green-check for the fsr_playbooks + connector axis (offline)
	@echo "→ [0/5] environment doctor"
	@# FIRST, and fail-fast. Every check here once presented as a product bug:
	@# a cwd-dependent version tripped the connector's guard across ~68 tests,
	@# an ancient pyfsr broke suite collection, and an empty reference DB makes
	@# broken YAML validate clean. Diagnosing those from the test output costs
	@# hours; diagnosing them from here costs one line.
	$(VENV_PY) -m fsr_playbooks.doctor
	@echo "→ [1/5] mypy (fsr_playbooks/compiler)"
	$(VENV_PY) -m mypy
	@echo "→ [2/5] mypy ratchet (fsr_playbooks/llm + mcp_server)"
	$(VENV_PY) scripts/mypy_gate.py
	@echo "→ [3/5] fsr_playbooks tests"
	$(VENV_PY) -m pytest fsr_playbooks/tests/ -q
	@echo "→ [4/5] connector suite (offline; live tests self-skip)"
	cd $(CONNECTOR_DIR) && PYTHONPATH=. $(VENV_PY) -m pytest -q
	@echo "✓ verify passed"
	@echo "  (Angular widget has its own toolchain in WebStorm -- not verifiable here.)"

clean: ## remove pycache + node_modules build leftovers (NOT node_modules itself)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND_DIR)/.svelte-kit $(FRONTEND_DIR)/dist
