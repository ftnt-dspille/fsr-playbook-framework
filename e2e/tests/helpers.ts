/**
 * Shared E2E helpers. All cross-test setup goes through these so the
 * specs themselves stay narrow and behavioural.
 *
 * Lifecycle pattern: each spec creates a uniquely-named draft via the
 * real PUT /api/playbooks/draft/{name} endpoint (against the live
 * backend, which writes to data/drafts.db), then deletes it in
 * afterAll. Test names use a timestamp so re-runs don't collide if
 * a prior cleanup was interrupted.
 */
import { request, type Page } from '@playwright/test';

// E2E uses dedicated ports (4792X) so it never collides with a dev
// session running on 4782X. Keep in sync with e2e/playwright.config.ts.
export const API = 'http://localhost:47921';
export const APP = 'http://localhost:47922';

/** Create-or-replace a draft via the backend's PUT route. */
export async function seedDraft(name: string, yaml: string): Promise<void> {
  const ctx = await request.newContext();
  const r = await ctx.put(`${API}/api/playbooks/draft/${encodeURIComponent(name)}`, {
    data: { yaml, reason: 'e2e setup', auto: false }
  });
  if (!r.ok()) throw new Error(`seedDraft(${name}) failed: ${r.status()}`);
  await ctx.dispose();
}

export async function deleteDraft(name: string): Promise<void> {
  const ctx = await request.newContext();
  await ctx.delete(`${API}/api/playbooks/draft/${encodeURIComponent(name)}`);
  await ctx.dispose();
}

/** Poll GET /api/playbooks/draft/{name} until `predicate(yaml)` returns
 *  true, or the timeout elapses. Replaces blind `waitForTimeout(1500)`
 *  autosave waits — the test passes the moment the server has the
 *  expected content, and surfaces a useful failure when it doesn't. */
export async function waitForDraftYaml(
  name: string,
  predicate: (yaml: string) => boolean,
  opts: { timeoutMs?: number; intervalMs?: number } = {}
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 8_000;
  const intervalMs = opts.intervalMs ?? 100;
  const ctx = await request.newContext();
  try {
    const deadline = Date.now() + timeoutMs;
    let lastYaml = '';
    while (Date.now() < deadline) {
      const r = await ctx.get(`${API}/api/playbooks/draft/${encodeURIComponent(name)}`);
      if (r.ok()) {
        const body = await r.json();
        lastYaml = (body.yaml ?? '') as string;
        if (predicate(lastYaml)) return lastYaml;
      }
      await new Promise((res) => setTimeout(res, intervalMs));
    }
    throw new Error(
      `waitForDraftYaml(${name}) timed out after ${timeoutMs}ms.\n` +
        `Last yaml:\n${lastYaml}`
    );
  } finally {
    await ctx.dispose();
  }
}

/** Pin the localStorage `last_opened` pointer so the page boots into
 *  the named draft instead of guessing. Run BEFORE navigating. */
export async function openDraft(page: Page, name: string): Promise<void> {
  await page.addInitScript(([n]) => {
    try {
      localStorage.setItem('fsrpb.last_opened', JSON.stringify({ kind: 'draft', name: n }));
      // Skip the one-time migration so the boot path doesn't slow down.
      localStorage.setItem('fsrpb.drafts.migrated_v1', '1');
    } catch {}
  }, [name]);
  await page.goto(APP);
}

/** Sample YAML used across multiple specs. Collection-wrapper shape
 *  (what the backend parser consumes); start-on-create alerts trigger →
 *  set_variable. Picked so the variable pane has a non-trivial scope —
 *  the stub FSR's /api/3/alerts returns records whose `severity`
 *  picklist gets unwrapped by formatFsrValue. */
export const SAMPLE_YAML = `\
collection: E2E Sample
description: Used by Playwright specs
visible: true

playbooks:
  - name: e2e_sample
    is_active: true
    steps:
      - name: On Create
        type: start_on_create
        next: Read Sev
        arguments:
          module: alerts
      - name: Read Sev
        type: set_variable
        vars:
          severity: ""
`;
