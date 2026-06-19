/**
 * Iterative-authoring E2E — the "add a step, wire its inputs, add
 * another step that consumes the previous one's output" journey a
 * real user walks when building a playbook from scratch.
 *
 * Exercises:
 *   • VarPathPicker (the `{x}` helper) on a fresh field
 *   • "+ Add next step" canvas affordance to grow the playbook in-flow
 *   • Cross-step refs via top-level `{{ vars.<name> }}` — the canonical
 *     set_variable surface (corpus-verified, NOT vars.steps.X.Y)
 *   • Auto-verify driving jinjaShapesStore so downstream steps see
 *     upstream set_variable outputs in their var pane.
 *
 * Both wirings are asserted via the persisted YAML (autosave →
 * draft store → GET back). No reliance on the Step Debugger (removed
 * in the May 2026 UI consolidation).
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml } from './helpers';

const DRAFT = `__e2e_iterative_${Date.now()}`;

// Trigger + one empty set_variable. The spec fills the variable, then
// adds a second set_variable that consumes the first's output.
const SEED_YAML = `\
collection: Iterative Sample
description: Used by iterative-authoring e2e
visible: true

playbooks:
  - name: iterative
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

test('add step → wire input → add downstream step → chain through vars', async ({ page }) => {
  await openDraft(page, DRAFT);

  // -------- Stage 1: edit "Extract" → add var "country" via dynamic-value picker

  await expect(page.getByText('On Create', { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByText('Extract', { exact: true }).first().click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await expect(inspector).toBeVisible();

  // Add a new set_variable row named "country". The placeholder input
  // + "+ Add variable" button live below the existing rows list.
  await inspector.getByPlaceholder('new variable name').fill('country');
  await inspector.getByRole('button', { name: /^\+\s*add variable$/i }).click();

  // {x} button claims the var pane's insert target.
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  const pane = page.getByRole('dialog', { name: /variable tree pane/i });
  await expect(pane).toBeVisible();

  // records[0] auto-expands once the alerts sample loads — click the
  // severity leaf directly.
  await expect(pane.getByRole('button', { name: 'records[0]' })).toBeVisible();
  await pane.locator('button[title="Insert {{ vars.input.records[0].severity }}"]').click();

  // Autosave round-trip: VarPathPicker → visualStore.setArgs →
  // 1s debounce → PUT /api/playbooks/draft → SQLite.
  await waitForDraftYaml(DRAFT, (y) => y.includes('vars.input.records[0].severity'));

  // -------- Stage 2: add a downstream step via the canvas "+ Add next" UX

  // Close the var pane — its dialog overlays the canvas and would
  // intercept clicks on the per-step "+" button.
  await pane.getByRole('button', { name: /close variable pane/i }).click();
  await expect(pane).toBeHidden();

  // Re-select Extract so its "+" affordance becomes opaque + clickable.
  // Scope to xyflow's `data-selected="true"` wrapper to avoid the
  // invisible default-state button that's overlapped by the edge SVG.
  await page.getByText('Extract', { exact: true }).first().click();
  await page.locator('[data-selected="true"]')
    .getByRole('button', { name: 'Add next step' })
    .click();
  await page.getByRole('menuitem', { name: 'Set Variable' }).click();

  // New step lands with the QUICK_TYPE label "Set Variable" — rename
  // to "Tag" so the assertions can target it by name.
  const newNode = page.getByText('Set Variable', { exact: true }).first();
  await expect(newNode).toBeVisible({ timeout: 10_000 });
  await newNode.click();
  await inspector.getByLabel('Step name').fill('Tag');
  await inspector.getByLabel('Step name').blur();

  // Wait for the rename to round-trip through autosave.
  await waitForDraftYaml(DRAFT, (y) => y.includes('Tag'));

  // -------- Stage 3: wire Tag's input to Extract's `country` output

  // Add var "out" that uses the previous step's `country` output.
  // FSR runtime exposes set_variable outputs at the TOP LEVEL as
  // `{{ vars.<name> }}` — NOT `vars.steps.Extract.country`.
  await inspector.getByPlaceholder('new variable name').fill('out');
  await inspector.getByRole('button', { name: /^\+\s*add variable$/i }).click();
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  // The vars (set_variable) group renders once auto-verify hydrates
  // jinjaShapesStore.topLevelVars. The newly-added `country` should
  // appear there. Click it via its insert-template title — Playwright
  // auto-scrolls + auto-waits for the locator to exist.
  await expect(pane.locator('button[title="Insert {{ vars.country }}"]'))
    .toBeVisible({ timeout: 15_000 });
  await pane.locator('button[title="Insert {{ vars.country }}"]').click();

  // Final assertion: both wirings landed in the saved draft.
  await waitForDraftYaml(
    DRAFT,
    (y) => y.includes('{{ vars.country }}')
        && y.includes('vars.input.records[0].severity')
  );
});
