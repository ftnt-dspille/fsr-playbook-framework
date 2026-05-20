# E2E tests

Full-stack Playwright suite. Drives a real Chromium against a real
backend, with a stubbed FortiSOAR appliance so the suite is hermetic
(no live FSR creds required).

## Stack

```
Chromium (Playwright)
  ↓
vite dev :47922   ← frontend (dedicated e2e port, dev runs on :47822)
  ↓ /api proxy
uvicorn :47921    ← backend (FastAPI, dedicated e2e port, dev on :47821)
  ↓ FSR_BASE_URL=http://127.0.0.1:47920
fsr_stub.py :47920 ← canned FortiSOAR endpoints (dedicated e2e port)
```

E2E runs on the 4792X range so it can run alongside a developer's
`pnpm dev` session (4782X range) without colliding.

The backend writes to `store/drafts.db` (real, shared with dev). Specs
use unique `__e2e_<timestamp>` draft names and clean up in `afterAll`.

## First-time setup

```sh
cd e2e
pnpm install
pnpm install-browsers   # downloads Chromium
```

The backend + frontend startup commands assume the repo's normal
Python + pnpm environments are set up — see the repo README.

## Run

```sh
pnpm test            # headless
pnpm test:headed     # watch it click around
pnpm test:debug      # Playwright inspector
```

Set `REUSE=0` to force a fresh boot of all three services (default
reuses anything already on the right port — handy when you have
`pnpm dev` already running).

## What's covered

| Spec | Scenario |
|---|---|
| `lifecycle.spec.ts` | Load draft → rename step → autosave → reload → persists. |
| `var_pane.spec.ts`  | Focus value field → pane opens, hydrated from stub FSR → leaf click writes YAML; Real-run mode shows observed values. |
| `compile.spec.ts`   | Backend compile contract: valid YAML → clean diagnostics; malformed YAML → error diagnostics (no crash). |
| `draft_switch.spec.ts` | Typing into draft A then switching to draft B must NOT leak A's buffer into B (page-effect race regression). |
| `examples_clone.spec.ts` | Open an example → Clone & Edit → new draft is created server-side with content byte-equivalent to the example source. |
| `connector_op.spec.ts` | Wire a dynamic value into a connector step's params via the var pane; autosave persists across reload. |
| `iterative_authoring.spec.ts` | Add step → wire input → add downstream step → consume upstream `vars.<name>` (chain-through). |
| `push_and_run.spec.ts` | Push & Run sends the current YAML; SSE log stream lands in the deploy panel; failure surfaces in the status pill. |
| `diagnostics_drawer.spec.ts` | Invalid step type surfaces in the Issues drawer at the right line; clean YAML shows the "No issues" empty state. |
| `status_dot.spec.ts` | Status pill dot is green for a clean draft, red for an invalid one (single ready-to-push indicator). |
| `canvas_mutations.spec.ts` | Add a decision step via the canvas "+ Add next" menu; delete a step via the inspector; both round-trip to YAML. |
| `mode_swap.spec.ts` | Design edits show up in CLI Monaco; mode round-trip preserves content. |

## Adding scenarios

The FSR stub returns canned alerts + 2 workflow runs (see top of
`fsr_stub.py`). To exercise a new backend → FSR call path, extend the
stub there, then write the spec against the new shape. Keep the stub
shape aligned with what the real appliance returns — see
`web/backend/routes/ref.py` for the request shapes the backend issues.
