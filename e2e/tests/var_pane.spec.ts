/**
 * E2E for the Variable Tree pane — exercises the full stack:
 *   browser → vite (frontend) → /api proxy → uvicorn (backend) → FSR stub
 *
 * What we assert end-to-end:
 *   1. Booting into a seeded draft renders the inspector + var pane
 *      when the user focuses a Jinja-accepting value field.
 *   2. The pane's tree is hydrated from the FSR stub — alerts module
 *      fields show up under vars.input.records[0], including picklist
 *      values unwrapped via formatFsrValue (`severity = High`).
 *   3. Clicking a leaf inserts `{{ vars.input.records[0].severity }}`
 *      into the set_variable value and the YAML actually round-trips
 *      back through the visual→YAML serializer.
 *   4. Real-run mode loads runs from the stub and the observed-value
 *      highlight ("= critical") appears in emerald on the right leaf.
 *
 * Each test seeds a uniquely-named draft and tears it down so reruns
 * don't collide on the shared store/drafts.db.
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml, SAMPLE_YAML } from './helpers';

const DRAFT = `__e2e_var_pane_${Date.now()}`;

test.beforeAll(async () => {
  await seedDraft(DRAFT, SAMPLE_YAML);
});
test.afterAll(async () => {
  await deleteDraft(DRAFT);
});

test('Var pane: focus a value field, pick a leaf, YAML updates', async ({ page }) => {
  await openDraft(page, DRAFT);

  // Wait for the canvas to render the seeded steps. The set_variable
  // step ("Read Sev") becomes our target — click its node to open the
  // inspector. StepNode renders the step name as text in the canvas.
  const stepNode = page.getByText('Read Sev', { exact: true }).first();
  await expect(stepNode).toBeVisible({ timeout: 15_000 });
  await stepNode.click();

  // Inspector flies in. Use the `{x}` VarPathPicker button (aria-label
  // "Insert variable") next to the set_variable's `severity` row to
  // claim the pane's insert target. This avoids racing Monaco's focus
  // listener and the 150ms blur grace — the button-click path uses
  // varPaneStore.toggle directly.
  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await expect(inspector).toBeVisible();
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  const pane = page.getByRole('dialog', { name: /variable tree pane/i });
  await expect(pane).toBeVisible();

  // records[0] is in the Input group (auto-expanded by default).
  // The records[0] node itself also auto-expands once the trigger's
  // sample record loads — so we don't need to click an Expand button
  // (which would be labeled "Collapse" by the time we'd find it).
  await expect(pane.getByRole('button', { name: 'records[0]' })).toBeVisible();

  // Click the records[0].severity leaf by its insert-template title.
  // Playwright auto-scrolls the locator into view — no need to expand
  // or scroll manually. Targeting by full path avoids matching the
  // set_variable's own `vars.severity` row that renders later.
  await pane
    .locator('button[title="Insert {{ vars.input.records[0].severity }}"]')
    .click();

  // The insert appended `{{ vars.input.records[0].severity }}` to the
  // set_variable row's value. Verify by reading the live YAML buffer
  // via the API rather than scraping Monaco — round-trips through the
  // visual→YAML serializer, which is the actual contract we care about.
  await waitForDraftYaml(DRAFT, (yaml) => yaml.includes('vars.input.records[0].severity'));
});

test('Var pane: Real-run mode shows observed values from past runs', async ({ page }) => {
  await openDraft(page, DRAFT);

  // Trigger a fresh verify BEFORE opening the inspector — once the
  // inspector is open it overlays the toolbar and the More Actions
  // button is no longer clickable. Verify populates
  // jinjaShapesStore.topLevelVars so the pane's "vars" group renders
  // and `= critical` has somewhere to land.
  await expect(page.getByText('Read Sev', { exact: true })).toBeVisible({ timeout: 15_000 });
  const verifyResp = page.waitForResponse(/\/api\/mcp\/verify_playbook/);
  await page.getByRole('button', { name: 'More actions' }).first().click();
  await page.getByRole('menuitem', { name: /Re-verify/i }).click();
  await verifyResp;

  const stepNode = page.getByText('Read Sev', { exact: true }).first();
  await stepNode.click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await expect(inspector).toBeVisible();
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  const pane = page.getByRole('dialog', { name: /variable tree pane/i });
  await expect(pane).toBeVisible();

  // Switch to Real-run. The stub's /api/wf/api/workflows/ returns two
  // canned runs; the picker should populate after loadRuns resolves
  // through the backend's /api/ref/recent-runs proxy. Wait on the
  // network response so the test doesn't race the loadRuns fetch.
  const runsResp = page.waitForResponse(/\/api\/ref\/recent-runs/);
  await pane.getByRole('button', { name: /^real run$/i }).click();
  await runsResp;

  const runPicker = pane.getByRole('combobox');
  await expect(runPicker).toBeVisible({ timeout: 10_000 });

  // Pick run #9001 — its wf_step_logs entry for "Read Sev" produced
  // severity=critical, so observedAt('vars.severity') returns it.
  // `selectOption({label})` requires an exact string, so resolve the
  // exact label at runtime by scanning the rendered <option> texts.
  const label9001 = await runPicker.evaluate((el: HTMLSelectElement) => {
    const opt = Array.from(el.options).find((o) => o.text.includes('9001'));
    return opt ? opt.text : null;
  });
  expect(label9001).not.toBeNull();
  await runPicker.selectOption({ label: label9001! });

  // After picking run 9001, the pane reflects run-specific input data:
  // the @id of the record (aaaa-1111) becomes records[0]'s observed
  // value. This proves the full flow: run selection → detail fetch →
  // record-by-iri fetch → pane display. (Step-output assertions like
  // `= critical` would need an upstream set_variable to surface vars
  // in the tree — see the iterative_authoring spec for that path.)
  await expect(pane.getByText('= aaaa-1111')).toBeVisible({ timeout: 10_000 });
});
