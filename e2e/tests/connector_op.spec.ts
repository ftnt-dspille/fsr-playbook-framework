/**
 * Connector-op authoring E2E — proves a user can wire a connector
 * step's params via the dynamic-value helper, and the wiring round-
 * trips through autosave to the backend's draft store. Connector
 * params have a different inspector layout than set_variable rows,
 * so this validates the VarPathPicker plays nicely with that surface.
 *
 * Stub support (see fsr_stub.py):
 *   /api/3/alerts → sample records that make vars.input.records[0]
 *                   carry a sourceIp leaf to pick.
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

test('connector op: wire dynamic value into params, autosave persists', async ({ page }) => {
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

  // records[0] auto-expands once the trigger sample loads — pick
  // sourceIp directly via the leaf's insert-template title.
  await expect(pane.getByRole('button', { name: 'records[0]' })).toBeVisible();
  await pane.locator('button[title="Insert {{ vars.input.records[0].sourceIp }}"]').click();

  await waitForDraftYaml(DRAFT, (y) =>
    y.includes('vars.input.records[0].sourceIp') && y.includes('ip:')
  );

  // Close the pane so it doesn't shadow the canvas / inspector.
  await pane.getByRole('button', { name: /close variable pane/i }).click();
  await expect(pane).toBeHidden();

  // Reload — the wiring must survive a fresh page load (autosave already
  // persisted; this asserts it actually re-hydrates correctly).
  await page.reload();
  await expect(page.getByText('Lookup IP', { exact: true })).toBeVisible({ timeout: 15_000 });
});
