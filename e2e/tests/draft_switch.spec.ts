/**
 * E2E: switching drafts must NOT clobber the new draft with the
 * previous draft's edited buffer. Pins the regression where typing
 * into A then clicking B in the picker left A's text in B's slot
 * (and on the next autosave wrote A's content into B on the server).
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml, API } from './helpers';
import { request } from '@playwright/test';

const STAMP = Date.now();
const DRAFT_A = `__e2e_switch_a_${STAMP}`;
const DRAFT_B = `__e2e_switch_b_${STAMP}`;

const YAML_A = `\
collection: E2E A
description: ""
visible: true

playbooks:
  - name: a
    is_active: true
    steps:
      - name: start
        type: start
`;

const YAML_B = `\
collection: E2E B
description: ""
visible: true

playbooks:
  - name: b
    is_active: true
    steps:
      - name: start
        type: start
`;

test.beforeAll(async () => {
  await seedDraft(DRAFT_A, YAML_A);
  await seedDraft(DRAFT_B, YAML_B);
});

test.afterAll(async () => {
  await deleteDraft(DRAFT_A);
  await deleteDraft(DRAFT_B);
});

test('typing into A then switching to B leaves B unpolluted', async ({ page }) => {
  await openDraft(page, DRAFT_A);
  // Use the URL query string to land directly on CLI mode so we have
  // a Monaco editor to type into instead of the visual canvas.
  await page.goto('/?mode=cli');

  // Wait for the editor to mount with draft A's content.
  await expect(page.getByText('E2E A')).toBeVisible({ timeout: 15_000 });

  // Type a comment line by focusing the editor and inserting text.
  // Monaco renders inside an iframe-like container — click first so it
  // takes focus.
  const editor = page.locator('.monaco-editor').first();
  await editor.click();
  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# polluted by A');

  // Wait until autosave has persisted the edit to A.
  await waitForDraftYaml(DRAFT_A, (y) => y.includes('# polluted by A'));

  // Now switch to draft B via the picker. The picker is rendered as
  // a list of <button>s, not menuitems.
  const picker = page.getByRole('button', { name: new RegExp(DRAFT_A) }).first();
  await picker.click();
  await page.getByRole('button', { name: new RegExp(DRAFT_B) }).first().click();

  // The editor must now show draft B's content — and crucially, NOT
  // A's edited line.
  await expect(page.getByText('E2E B')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('.monaco-editor', { hasText: '# polluted by A' })).toHaveCount(0);

  // Server-side: B's persisted yaml must remain untouched.
  const ctx = await request.newContext();
  const r = await ctx.get(`${API}/api/playbooks/draft/${encodeURIComponent(DRAFT_B)}`);
  expect(r.ok()).toBe(true);
  const body = await r.json();
  expect(body.yaml).not.toContain('# polluted by A');
  expect(body.yaml).toContain('E2E B');
  await ctx.dispose();
});
