/**
 * Examples → Clone & Edit E2E.
 *
 * Examples are shipped read-only on disk (examples/) and surface in
 * the picker's "Examples" section. Saving while an example is active
 * routes through a "Clone & Edit" modal that creates a brand-new
 * draft seeded with the example's YAML. This spec exercises the
 * whole path:
 *
 *   picker → click example → Save (Clone & Edit) → modal → confirm
 *     → new draft exists in store/drafts.db
 *     → active doc switches to the new draft
 *     → the cloned YAML matches the example's source
 */
import { test, expect, request } from '@playwright/test';
import { deleteDraft, openDraft, API, APP } from './helpers';

const EXAMPLE = 'decision_branch.yaml';
const DRAFT = `__e2e_clone_${Date.now()}`;

// No beforeAll seed — the test creates the draft via the UI. Only
// cleanup the draft afterwards in case the test left one behind.
test.afterAll(async () => {
  await deleteDraft(DRAFT);
});

test('clone an example into a new draft, content matches the source', async ({ page }) => {
  // Pin the example as last-opened so the page boots into it instead
  // of a draft. openDraft sets `kind: 'draft'`; replace with an
  // example pointer before navigating so the first-load picker lands
  // on the example.
  await page.addInitScript(([n]) => {
    try {
      localStorage.setItem('fsrpb.last_opened', JSON.stringify({ kind: 'example', name: n }));
      localStorage.setItem('fsrpb.drafts.migrated_v1', '1');
    } catch {}
  }, [EXAMPLE]);
  await page.goto(APP);

  // Wait for the page to settle on the example. PlaybookHeader's Save
  // button morphs to "Clone & Edit" when an example is active —
  // that's our signal that the active document is the example.
  const cloneBtn = page.getByRole('button', { name: 'Clone & Edit' });
  await expect(cloneBtn).toBeVisible({ timeout: 15_000 });

  await cloneBtn.click();

  // The clone modal contains a Cancel button and its own Clone & Edit
  // confirm button. Anchor on Cancel to scope to the modal's <div>,
  // then fill the name field with our unique e2e draft name.
  const modal = page.locator('div', { has: page.getByRole('button', { name: 'Cancel' }) }).first();
  await modal.locator('input').first().fill(DRAFT);

  // Two "Clone & Edit" buttons exist briefly (the header trigger that
  // we already clicked, and the modal's confirm). `.last()` picks the
  // modal's confirm.
  await page.getByRole('button', { name: 'Clone & Edit' }).last().click();

  // After clone, the active doc switches to the new draft. The header
  // now shows the draft name + a "Save" button (not Clone & Edit).
  await expect(page.getByRole('button', { name: 'Save' })).toBeVisible({ timeout: 10_000 });

  // Server-side: the draft exists and its YAML matches the example.
  const ctx = await request.newContext();
  const draftResp = await ctx.get(`${API}/api/playbooks/draft/${encodeURIComponent(DRAFT)}`);
  expect(draftResp.ok()).toBe(true);
  const draftBody = await draftResp.json();
  expect(draftBody.yaml).toBeTruthy();

  const exampleResp = await ctx.get(`${API}/api/playbooks/example/${encodeURIComponent(EXAMPLE)}`);
  expect(exampleResp.ok()).toBe(true);
  const exampleBody = await exampleResp.json();
  expect(exampleBody.yaml).toBeTruthy();

  // The clone is byte-equivalent at clone time (modulo trailing
  // newlines that some endpoints normalize).
  expect(draftBody.yaml.trim()).toBe(exampleBody.yaml.trim());
  await ctx.dispose();
});
