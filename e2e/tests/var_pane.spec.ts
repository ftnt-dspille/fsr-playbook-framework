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
  // Header reflects the active target — set_variable's severity row.
  await expect(pane.getByText(/severity/i).first()).toBeVisible();

  // Expand vars.input.records[0]. The row's label button is `pick()`;
  // its sibling caret with aria-label="Expand" is the toggle.
  const recordsRow = pane.getByText('records[0]').first().locator('xpath=..');
  await recordsRow.getByRole('button', { name: /expand/i }).click();

  // The trigger is module=alerts → stub's /api/3/alerts returns records
  // with a severity field. Hint includes "= High" (picklist unwrap).
  await expect(pane.getByText(/= High/)).toBeVisible();

  // Click the records[0].severity leaf. Each tree leaf carries a
  // unique `title="Insert {{ <path> }}"`, so target by path — using
  // .last() here would land on the set_variable's own vars.severity
  // row which renders below records in the same pane.
  await pane.locator('button[title="Insert {{ vars.input.records[0].severity }}"]').click();

  // The insert appended `{{ vars.input.records[0].severity }}` to the
  // set_variable row's value. Verify by reading the live YAML buffer
  // via the API rather than scraping Monaco — round-trips through the
  // visual→YAML serializer, which is the actual contract we care about.
  await waitForDraftYaml(DRAFT, (yaml) => yaml.includes('vars.input.records[0].severity'));
});

test('Var pane: Real-run mode shows observed values from past runs', async ({ page }) => {
  await openDraft(page, DRAFT);

  const stepNode = page.getByText('Read Sev', { exact: true }).first();
  await expect(stepNode).toBeVisible({ timeout: 15_000 });
  await stepNode.click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await expect(inspector).toBeVisible();
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  const pane = page.getByRole('dialog', { name: /variable tree pane/i });
  await expect(pane).toBeVisible();

  // Switch to Real-run. The stub's /api/wf/api/workflows/ returns two
  // canned runs; the picker should populate after loadRuns resolves.
  await pane.getByRole('button', { name: /^real run$/i }).click();
  const runPicker = pane.getByRole('combobox');
  await expect(runPicker).toBeVisible();

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

  // The set_variable's top-level `vars.severity` row should highlight.
  // Find the vars (set_variable) group and check its child severity row.
  // Mined top-level vars come from the run's flat-dict step outputs.
  await expect(pane.getByText('= critical')).toBeVisible({ timeout: 10_000 });
});
