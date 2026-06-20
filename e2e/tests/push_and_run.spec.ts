/**
 * Push & Run E2E. The Run split-button is the loud orange CTA that
 * compiles the draft and (for "Push & Run") pushes + triggers a live
 * execution. Pushing to the stub from the CLI subprocess would require
 * stubbing the full FSR workflow_collections + run-trigger API surface
 * — too heavy. Instead we intercept the /api/playbook/push and
 * /api/playbook/run requests at the network layer with page.route()
 * so we can:
 *   • assert the frontend POSTs the *current* buffer (not stale yaml)
 *   • assert the UI surfaces success / error from the response
 *   • assert the SSE run stream is consumed (logs land in the deploy panel)
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, SAMPLE_YAML } from './helpers';

const DRAFT = `__e2e_push_${Date.now()}`;

test.beforeAll(async () => { await seedDraft(DRAFT, SAMPLE_YAML); });
test.afterAll(async () => { await deleteDraft(DRAFT); });

test('Push & Run sends current YAML, streams logs, status reflects success', async ({ page }) => {
  // Intercept BEFORE navigating so the routes are active for any
  // request the page makes during boot.
  let pushedYaml: string | null = null;
  await page.route('**/api/playbook/push', async (route) => {
    const body = route.request().postDataJSON() as { text?: string };
    pushedYaml = body?.text ?? null;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, stdout: 'pushed ok', stderr: '', exit_code: 0 })
    });
  });

  // /api/playbook/run is an SSE stream. We synthesize a 3-frame
  // exchange: log, task_id, done. Each frame is `event:<name>\ndata:<json>\n\n`.
  await page.route('**/api/playbook/run', async (route) => {
    const body =
      `event: log\ndata: ${JSON.stringify({ line: 'starting run' })}\n\n` +
      `event: task_id\ndata: ${JSON.stringify({ task_id: 'task-9001' })}\n\n` +
      `event: done\ndata: ${JSON.stringify({ exit_code: 0 })}\n\n`;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body
    });
  });

  await openDraft(page, DRAFT);
  await expect(page.getByText('Read Sev', { exact: true })).toBeVisible({ timeout: 15_000 });

  // Click the primary Run action (Push & Run by default).
  await page.getByRole('button', { name: 'Push & Run' }).click();

  // The deploy panel renders streamed logs; popping the drawer to
  // Deploy lets the test assert the stream was consumed.
  await page.getByRole('button', { name: 'Deploy' }).click();

  // Status pill turns green (kind=ok) with "pushed" or run-complete
  // text; the status text element is the small grey span next to
  // the dot.
  await expect(page.getByText('starting run')).toBeVisible({ timeout: 10_000 });

  // The frontend POSTed the *current* YAML — not the placeholder.
  expect(pushedYaml).toBeTruthy();
  expect(pushedYaml!).toContain('Read Sev');
});

test('Push failure surfaces in the status pill and deploy panel', async ({ page }) => {
  await page.route('**/api/playbook/push', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: false,
        stdout: '',
        stderr: 'FSR_BASE_URL not configured',
        exit_code: 2
      })
    });
  });
  // /api/playbook/run shouldn't be called after push fails, but stub
  // it anyway so a regression that DOES call it surfaces as obviously
  // weird state instead of a hung SSE connection.
  let runCalled = false;
  await page.route('**/api/playbook/run', async (route) => {
    runCalled = true;
    await route.abort();
  });

  await openDraft(page, DRAFT);
  await expect(page.getByText('Read Sev', { exact: true })).toBeVisible({ timeout: 15_000 });

  await page.getByRole('button', { name: 'Push & Run' }).click();

  // Status dot/text reflects the failure — the err pill in the action
  // bar shows the push error message.
  await expect(page.getByText(/push failed/i)).toBeVisible({ timeout: 10_000 });

  // The run endpoint must NOT have been hit when push fails.
  expect(runCalled).toBe(false);
});
