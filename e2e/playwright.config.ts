import { defineConfig } from '@playwright/test';

/**
 * E2E config. Starts three processes on DEDICATED ports that don't
 * overlap with the dev environment (dev is on 4782X — e2e is on 4792X):
 *
 *   1. FSR stub  (port 47920) — canned FortiSOAR endpoints, see fsr_stub.py
 *   2. Backend   (port 47921) — real FastAPI app pointed at the stub
 *   3. Frontend  (port 47922) — `vite dev`, /api proxied to backend
 *
 * Reuses an existing server only if one is ALREADY on those e2e
 * ports — never collides with a running `pnpm dev` session.
 */
const REUSE = process.env.REUSE !== '0';
const REPO_ROOT = new URL('..', import.meta.url).pathname.replace(/\/$/, '');

const STUB_PORT = 47920;
const BACKEND_PORT = 47921;
const FRONTEND_PORT = 47922;

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,           // shared backend → serialize
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  },
  webServer: [
    {
      command: `python3 ${REPO_ROOT}/e2e/fsr_stub.py`,
      url: `http://localhost:${STUB_PORT}/health`,
      reuseExistingServer: REUSE,
      timeout: 15_000,
      env: { FSR_STUB_PORT: String(STUB_PORT) }
    },
    {
      command:
        `cd ${REPO_ROOT}/web && ` +
        `FSR_BASE_URL=http://127.0.0.1:${STUB_PORT} ` +
        `FSR_API_KEY=stub-key ` +
        `FSR_VERIFY_SSL=false ` +
        `PYTHONPATH=${REPO_ROOT}/python ` +
        `python3 -m uvicorn backend.app:app --port ${BACKEND_PORT} --log-level warning`,
      url: `http://localhost:${BACKEND_PORT}/api/health`,
      reuseExistingServer: REUSE,
      timeout: 30_000
    },
    {
      command:
        `cd ${REPO_ROOT}/web/frontend && ` +
        `VITE_PORT=${FRONTEND_PORT} ` +
        `VITE_API_TARGET=http://localhost:${BACKEND_PORT} ` +
        `pnpm dev`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: REUSE,
      timeout: 60_000
    }
  ],
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }]
});
