/**
 * Canvas-mutation E2E. The visual canvas is the primary authoring
 * surface — most of the bugs in this app live in the edges between
 * "click a thing on the canvas" and "the YAML serializer emits the
 * right shape". Today only `lifecycle.spec` exercises a single-field
 * rename. This spec adds:
 *   • Add a decision step via the "+ Add next step" quick-type menu.
 *   • Rename it via the inspector.
 *   • Assert it persists to the saved YAML with the right type +
 *     wiring back to the upstream step.
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml } from './helpers';

const DRAFT = `__e2e_canvas_${Date.now()}`;

const SEED_YAML = `\
collection: Canvas Sample
description: Used by canvas-mutations e2e
visible: true

playbooks:
  - name: canvas
    is_active: true
    steps:
      - name: On Create
        type: start_on_create
        next: Extract
        arguments:
          module: alerts
      - name: Extract
        type: set_variable
        vars: {}
`;

test.beforeAll(async () => { await seedDraft(DRAFT, SEED_YAML); });
test.afterAll(async () => { await deleteDraft(DRAFT); });

test('add a decision step via the canvas, rename, persists to YAML', async ({ page }) => {
  await openDraft(page, DRAFT);

  await expect(page.getByText('Extract', { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByText('Extract', { exact: true }).first().click();

  // The "+" affordance is only opaque on the selected node — scope to
  // the xyflow wrapper marked data-selected="true".
  await page.locator('[data-selected="true"]')
    .getByRole('button', { name: 'Add next step' })
    .click();
  await page.getByRole('menuitem', { name: 'Decision' }).click();

  // The new step renders with the QUICK_TYPE label "Decision".
  const newNode = page.getByText('Decision', { exact: true }).first();
  await expect(newNode).toBeVisible({ timeout: 10_000 });
  await newNode.click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await inspector.getByLabel('Step name').fill('Branch');
  await inspector.getByLabel('Step name').blur();

  // Both the type (decision) and the rename must round-trip through
  // visual→YAML serialization + autosave. The upstream Extract step's
  // `next:` should also point at the new step's name.
  await waitForDraftYaml(DRAFT, (y) =>
    y.includes('type: decision')
    && y.includes('Branch')
  );
});

test('delete a step via the inspector removes it from the YAML', async ({ page }) => {
  // Seed a fresh draft so this test isn't ordered after the previous one.
  const NAME = `__e2e_canvas_del_${Date.now()}`;
  await seedDraft(NAME, SEED_YAML);
  try {
    await openDraft(page, NAME);
    await expect(page.getByText('Extract', { exact: true })).toBeVisible({ timeout: 15_000 });
    await page.getByText('Extract', { exact: true }).first().click();

    const inspector = page.getByRole('dialog', { name: /step inspector/i });

    // Native window.confirm() guards the delete — register the
    // dialog handler BEFORE clicking so it fires for the prompt.
    page.once('dialog', (d) => d.accept());
    await inspector.getByRole('button', { name: 'Delete step' }).click();

    // Wait for the YAML to no longer contain the Extract step.
    await waitForDraftYaml(NAME, (y) => !y.includes('Extract'));
  } finally {
    await deleteDraft(NAME);
  }
});
