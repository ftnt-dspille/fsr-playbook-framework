/**
 * Iterative-authoring E2E — the "add a step, test it, add a step,
 * test it" journey a real user walks when building a playbook from
 * scratch.
 *
 * Exercises:
 *   • VarPathPicker (the `{x}` dynamic-value helper) on a fresh field
 *   • "+ Add next step" canvas UX to grow the playbook in-flow
 *   • Step Debugger to actually *run* the simulation against the FSR
 *     stub's Jinja-editor endpoint and observe rendered outputs
 *   • Cross-step refs via top-level `{{ vars.<name> }}` (the canonical
 *     set_variable surface — corpus-verified, NOT vars.steps.X.Y).
 *
 * Stub additions this spec depends on (see fsr_stub.py):
 *   • POST /api/wf/api/jinja-editor/   — real jinja2 render so step
 *                                        trace shows resolved values
 *   • POST /api/integration/execute/   — connector-op exec (used by
 *                                        the sibling connector_op spec;
 *                                        kept off here so this stays
 *                                        focused on the chained-vars flow)
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

test('add step → test → add step → test, dynamic values chain through', async ({ page }) => {
  await openDraft(page, DRAFT);

  // -------- Stage 1: edit "Extract" → add var "country" via dynamic-value picker

  // Wait for the canvas to render. We target step nodes by their on-canvas
  // text (the name is the visible label).
  await expect(page.getByText('On Create', { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByText('Extract', { exact: true }).first().click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await expect(inspector).toBeVisible();

  // Add a new set_variable row named "country". The placeholder input
  // + "+ Add variable" button live below the existing rows list; with
  // an empty seed there is no list yet, so "No variables defined yet"
  // shows above the add controls.
  await inspector.getByPlaceholder('new variable name').fill('country');
  await inspector.getByRole('button', { name: /^\+\s*add variable$/i }).click();

  // Now there's one var row; the {x} button next to its Monaco editor
  // claims the var pane's insert target without racing Monaco's focus
  // (see the e2e_suite_state memory's writeup of the May 2026 fix).
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  const pane = page.getByRole('dialog', { name: /variable tree pane/i });
  await expect(pane).toBeVisible();

  // The stub's /api/3/alerts returns records with a `severity` picklist
  // that the sample-records fetcher pulls in for trigger=alerts. Expand
  // records[0] and pick severity by its canonical title (every leaf
  // carries a unique `title="Insert {{ <path> }}"`).
  await pane.getByText('records[0]').first().locator('xpath=..')
    .getByRole('button', { name: /expand/i }).click();
  await expect(pane.getByText(/= High/)).toBeVisible();
  await pane.locator('button[title="Insert {{ vars.input.records[0].severity }}"]').click();

  // Autosave round-trip: the picker's setVar call → visualStore.setArgs
  // → 1s autosave debounce → PUT /api/playbooks/draft. Poll until the
  // PUT lands instead of sleeping.
  await waitForDraftYaml(DRAFT, (y) => y.includes('vars.input.records[0].severity'));

  // -------- Stage 2: "test" Extract via the Step Debugger

  // Toolbar "Step Debugger" button toggles the diagnostics drawer to the
  // debug tab. (DiagnosticsDrawer.svelte:96)
  await page.getByRole('button', { name: 'Step Debugger', exact: true }).click();

  // "Step Through" runs step_through_playbook against the current YAML.
  // Renders happen on the stub's /api/wf/api/jinja-editor/ so values
  // resolve to real strings rather than passing through verbatim.
  const stepBtn = page.getByRole('button', { name: /^step through$/i });
  await stepBtn.click();

  // Trace renders into a single <table>. The drawer also previews status
  // — wait for the rendered rows to appear instead of the
  // "Press Step Through to simulate" placeholder.
  const traceRows = page.locator('table tbody tr');
  await expect(traceRows).toHaveCount(2, { timeout: 10_000 });
  // Row 1 = trigger, Row 2 = Extract (set_variable). Extract should
  // succeed and surface its `country` output key.
  await expect(traceRows.nth(1)).toContainText('Extract');
  await expect(traceRows.nth(1)).toContainText('country');

  // -------- Stage 3: add a downstream step via the canvas "+ Add next" UX

  // Close the var pane first — it's still open and overlays the canvas,
  // so its dialog intercepts pointer events on the per-step "+" button.
  await pane.getByRole('button', { name: /close variable pane/i }).click();
  await expect(pane).toBeHidden();

  // Re-select Extract so its "+" handle becomes opaque + clickable.
  // Every step renders the button in DOM (opacity:0 by default), so
  // scope to xyflow's `data-selected="true"` wrapper to find the one
  // that's actually visible — otherwise .first() picks an invisible
  // button overlapped by the edge SVG and the click is intercepted.
  await page.getByText('Extract', { exact: true }).first().click();
  await page.locator('[data-selected="true"]')
    .getByRole('button', { name: 'Add next step' })
    .click();
  await page.getByRole('menuitem', { name: 'Set Variable' }).click();

  // New step renders with name "Set Variable" (the QUICK_TYPE label).
  // Rename to "Tag" so the trace row is recognisable.
  const newNode = page.getByText('Set Variable', { exact: true }).first();
  await expect(newNode).toBeVisible({ timeout: 10_000 });
  await newNode.click();
  await inspector.getByLabel('Step name').fill('Tag');
  await inspector.getByLabel('Step name').blur();

  // Add var "out" pointing at the previous step's `country` output.
  // Important: set_variable outputs surface at the TOP LEVEL as
  // `{{ vars.<name> }}` (FSR runtime contract, corpus-verified — see
  // jinja-picker-session-state memory), NOT `vars.steps.Extract.country`.
  await inspector.getByPlaceholder('new variable name').fill('out');
  await inspector.getByRole('button', { name: /^\+\s*add variable$/i }).click();
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  // Pane re-opens scoped to Tag. The "vars (set_variable)" group is
  // expanded by default and lists every upstream set_variable's top-
  // level outputs — `country` should appear there once verifyShapes
  // hydrates from the freshly-saved YAML.
  await expect(pane.locator('button[title="Insert {{ vars.country }}"]'))
    .toBeVisible({ timeout: 10_000 });
  await pane.locator('button[title="Insert {{ vars.country }}"]').click();

  await waitForDraftYaml(DRAFT, (y) => y.includes('{{ vars.country }}'));

  // -------- Stage 4: re-run the debugger → chain works

  await stepBtn.click();
  await expect(traceRows).toHaveCount(3, { timeout: 10_000 });
  await expect(traceRows.nth(2)).toContainText('Tag');
  // Tag's output_top_keys column should include "out".
  await expect(traceRows.nth(2)).toContainText('out');
});
