import { defineConfig } from '@playwright/test';

/**
 * E2E config. Starts three processes in order:
 *
 *   1. FSR stub  (port 47820) — canned FortiSOAR endpoints, see fsr_stub.py
 *   2. Backend   (port 47821) — real FastAPI app pointed at the stub
 *   3. Frontend  (port 47822) — `vite dev`, /api proxied to backend
 *
 * Reuses an existing server if one is already running on the right
 * port — convenient for `pnpm dev` users who already have the backend
 * up. Set REUSE=0 to force a fresh boot.
 */
const REUSE = process.env.REUSE !== '0';
const REPO_ROOT = new URL('..', import.meta.url).pathname.replace(/\/$/, '');

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,           // shared backend → serialize
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL: 'http://localhost:47822',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  },
  webServer: [
    {
      command: `python3 ${REPO_ROOT}/e2e/fsr_stub.py`,
      url: 'http://localhost:47820/health',
      reuseExistingServer: REUSE,
      timeout: 15_000,
      env: { FSR_STUB_PORT: '47820' }
    },
    {
      command:
        `cd ${REPO_ROOT}/web && ` +
        `FSR_BASE_URL=http://127.0.0.1:47820 ` +
        `FSR_API_KEY=stub-key ` +
        `FSR_VERIFY_SSL=false ` +
        `PYTHONPATH=${REPO_ROOT}/python ` +
        `python3 -m uvicorn backend.app:app --port 47821 --log-level warning`,
      url: 'http://localhost:47821/api/health',
      reuseExistingServer: REUSE,
      timeout: 30_000
    },
    {
      command: `cd ${REPO_ROOT}/web/frontend && pnpm dev`,
      url: 'http://localhost:47822',
      reuseExistingServer: REUSE,
      timeout: 60_000
    }
  ],
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }]
});
