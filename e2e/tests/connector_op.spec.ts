/**
 * Connector-op execution E2E — proves a user can wire a connector
 * step's params via the dynamic-value helper, then "test" it via the
 * Step Debugger with execute_safe_ops on, and see real output_top_keys
 * come back. Mirrors how someone would prototype an enrichment flow
 * without leaving the designer.
 *
 * Stub support (see fsr_stub.py):
 *   POST /api/integration/execute/   → returns canned payload keyed by
 *                                      (connector, operation).
 *   /api/3/alerts                    → sample records used by the var
 *                                      pane so vars.input.records[0]
 *                                      has a sourceIp leaf to pick.
 *
 * Connector choice: virustotal/query_ip — `query_` prefix → risk=safe
 * per tools_discovery._op_risk (name patterns are the primary
 * classifier; category=investigation is only a fallback). So
 * step_through actually hits the stub instead of refusing on the
 * destructive-op gate, which is why apivoid/iprep doesn't work here
 * (its `iprep` name pattern is too short for the prefix table).
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml } from './helpers';

const DRAFT = `__e2e_connector_${Date.now()}`;

// Seeded with the trigger + a half-wired connector step. The spec
// fills the params.host via the dynamic-value picker (proving the
// helper works for connector args, not just set_variable rows) and
// then runs Step Through to observe the live op output.
const SEED_YAML = `\
collection: Connector Sample
description: Used by connector-op e2e
visible: true

playbooks:
  - name: enrich
    is_active: true
    steps:
      - name: On Create
        type: start_on_create
        next: Lookup IP
        arguments:
          module: alerts
      - name: Lookup IP
        type: connector
        arguments:
          connector: virustotal
          operation: query_ip
          config: ""
          params:
            ip: ""
`;

test.beforeAll(async () => { await seedDraft(DRAFT, SEED_YAML); });
test.afterAll(async () => { await deleteDraft(DRAFT); });

test('connector op: wire dynamic value into params, run, observe output', async ({ page }) => {
  await openDraft(page, DRAFT);

  await expect(page.getByText('Lookup IP', { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByText('Lookup IP', { exact: true }).first().click();

  const inspector = page.getByRole('dialog', { name: /step inspector/i });
  await expect(inspector).toBeVisible();

  // Connector args render a params section with one row per declared
  // param. Each row has its own `{x}` (aria-label="Insert variable")
  // VarPathPicker. The seed has a single param `host`, so .first() is
  // unambiguous.
  await inspector.getByRole('button', { name: /^insert variable$/i }).first().click();

  const pane = page.getByRole('dialog', { name: /variable tree pane/i });
  await expect(pane).toBeVisible();

  // Expand records[0] and pick sourceIp — proves the typed-walker
  // surfaces the trigger module's fields here too.
  await pane.getByText('records[0]').first().locator('xpath=..')
    .getByRole('button', { name: /expand/i }).click();
  await expect(pane.getByText(/= 10\.0\.0\.42/)).toBeVisible();
  await pane.locator('button[title="Insert {{ vars.input.records[0].sourceIp }}"]').click();

  await waitForDraftYaml(DRAFT, (y) =>
    y.includes('vars.input.records[0].sourceIp') && y.includes('ip:')
  );

  // Close the pane so the canvas isn't covered when we toggle the
  // diagnostics drawer.
  await pane.getByRole('button', { name: /close variable pane/i }).click();

  // -------- Test the step by running it through the debugger live

  await page.getByRole('button', { name: 'Step Debugger', exact: true }).click();
  // execute_safe_ops is OFF by default; flip it ON so the connector
  // op actually hits the stub instead of being simulated.
  await page.getByRole('checkbox', { name: /execute_safe_ops/ }).check();
  await page.getByRole('button', { name: /^step through$/i }).click();

  const traceRows = page.locator('table tbody tr');
  await expect(traceRows).toHaveCount(2, { timeout: 15_000 });
  // Trigger + Lookup IP. Lookup IP row should be ok + carry the stub's
  // canned output keys (sorted alphabetically by run_op).
  await expect(traceRows.nth(1)).toContainText('Lookup IP');
  await expect(traceRows.nth(1)).toContainText('connector');
  await expect(traceRows.nth(1)).toContainText('ok');
  // output_top_keys cell: blacklist_count, country, detections, ip, is_malicious
  await expect(traceRows.nth(1)).toContainText('country');
  await expect(traceRows.nth(1)).toContainText('detections');
});
