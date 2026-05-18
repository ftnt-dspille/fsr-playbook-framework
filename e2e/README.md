# E2E tests

Full-stack Playwright suite. Drives a real Chromium against a real
backend, with a stubbed FortiSOAR appliance so the suite is hermetic
(no live FSR creds required).

## Stack

```
Chromium (Playwright)
  ↓
vite dev :47822   ← frontend
  ↓ /api proxy
uvicorn :47821    ← backend (FastAPI)
  ↓ FSR_BASE_URL=http://127.0.0.1:47820
fsr_stub.py :47820 ← canned FortiSOAR endpoints
```

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

## Adding scenarios

The FSR stub returns canned alerts + 2 workflow runs (see top of
`fsr_stub.py`). To exercise a new backend → FSR call path, extend the
stub there, then write the spec against the new shape. Keep the stub
shape aligned with what the real appliance returns — see
`web/backend/routes/ref.py` for the request shapes the backend issues.
