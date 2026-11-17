/**
 * Status-dot E2E. The green/red dot in the action bar is the SINGLE
 * ready-to-push indicator after this session's consolidation (no
 * Verify button, no separate verify pill). It's fed by auto-validate
 * (every keystroke), auto-analyze (on autosave), and auto-verify (on
 * autosave). This spec pins the contract:
 *   • A clean draft → green dot, status "verified" / "valid".
 *   • A draft with an invalid step type → red dot once validate runs.
 *   • Reverting the YAML → dot returns to green.
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft } from './helpers';

const CLEAN_YAML = `\
collection: "status-clean"
description: ""
visible: true

playbooks:
  - name: clean
    is_active: true
    steps:
      - name: trigger
        type: start
`;

const BROKEN_YAML = `\
collection: "status-broken"
description: ""
visible: true

playbooks:
  - name: broken
    is_active: true
    steps:
      - name: trigger
        type: star
`;

const CLEAN_DRAFT = `__e2e_dot_clean_${Date.now()}`;
const BROKEN_DRAFT = `__e2e_dot_broken_${Date.now()}`;

test.beforeAll(async () => {
  await seedDraft(CLEAN_DRAFT, CLEAN_YAML);
  await seedDraft(BROKEN_DRAFT, BROKEN_YAML);
});
test.afterAll(async () => {
  await deleteDraft(CLEAN_DRAFT);
  await deleteDraft(BROKEN_DRAFT);
});

// The dot is a small <span> with a `bg-green-500` / `bg-red-500`
// class. Use the surrounding span's `title` (which mirrors the
// status.msg) so the assertion reads as user-visible text.
async function dotColorClass(page: import('@playwright/test').Page): Promise<string> {
  // The action bar's status pill is the only element with a colored
  // dot and a title containing the verify result.
  return await page
    .locator('span.h-2.w-2.rounded-full')
    .first()
    .evaluate((el) => Array.from(el.classList).find((c) => c.startsWith('bg-')) ?? '');
}

test('clean draft → green dot', async ({ page }) => {
  await openDraft(page, CLEAN_DRAFT);
  await expect(page.getByText('trigger', { exact: true })).toBeVisible({ timeout: 15_000 });

  // Auto-validate fires on load (debounced 400ms). Wait for the dot
  // to settle into ok/green.
  await expect.poll(
    () => dotColorClass(page),
    { timeout: 10_000 }
  ).toBe('bg-green-500');
});

test('invalid step type → red dot', async ({ page }) => {
  await openDraft(page, BROKEN_DRAFT);
  await expect(page.getByText('trigger', { exact: true })).toBeVisible({ timeout: 15_000 });

  await expect.poll(
    () => dotColorClass(page),
    { timeout: 10_000 }
  ).toBe('bg-red-500');
});
