/**
 * Playbook lifecycle E2E: seed a draft → load it in the app → make an
 * edit through the visual editor → autosave round-trip → reload → assert
 * the change persisted in the backend's drafts.db.
 *
 * This is the "smoke test" for the whole edit pipeline:
 *   visualStore mutation → playbookActions → YAML re-serialize →
 *   autosave 1s debounce → PUT /api/playbooks/draft/<name> → SQLite.
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml, SAMPLE_YAML } from './helpers';

const DRAFT = `__e2e_lifecycle_${Date.now()}`;

test.beforeAll(async () => { await seedDraft(DRAFT, SAMPLE_YAML); });
test.afterAll(async () => { await deleteDraft(DRAFT); });

test('Edit set_variable name → autosave → reload → change persists', async ({ page }) => {
  await openDraft(page, DRAFT);

  // Find the set_variable step and rename it via the inspector.
  const stepNode = page.getByText('Read Sev', { exact: true }).first();
  await expect(stepNode).toBeVisible({ timeout: 15_000 });
  await stepNode.click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  const nameInput = inspector.getByLabel('Step name');
  await nameInput.fill('Read Severity');
  await nameInput.blur();

  // Autosave is debounced 1s — poll the backend until the new name lands
  // (or the helper times out at 8s with a useful "last yaml" dump).
  await waitForDraftYaml(DRAFT, (yaml) => yaml.includes('Read Severity'));

  // Reload — the renamed step should still be there.
  await page.reload();
  await expect(page.getByText('Read Severity', { exact: true })).toBeVisible({ timeout: 15_000 });
});
