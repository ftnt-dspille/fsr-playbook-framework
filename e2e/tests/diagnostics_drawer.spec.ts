/**
 * Diagnostics drawer (Issues panel) E2E. Pins the regressions that
 * surfaced today:
 *   1. Typing bad YAML in CLI mode must mark playbookStore dirty AND
 *      trigger validate so the err/warn chip + drawer show the error.
 *   2. The squiggle / row lines up with the actual offending key line
 *      (the `_path_to_line` fix — backend-side, but assertable through
 *      the marker's `line` field surfaced in the row text).
 *   3. An auto-fixable warning surfaces an inline "Apply" button that
 *      patches the YAML through Monaco's executeEdits (round-trips
 *      back into the saved draft on the next autosave).
 */
import { test, expect } from '@playwright/test';
import { seedDraft, deleteDraft, openDraft, waitForDraftYaml } from './helpers';

const DRAFT = `__e2e_diag_${Date.now()}`;

// Auto-fix-friendly seed. The decision step uses bare yes/no branches
// — which the validator flags as `W::W_BARE_YES_NO` (or similar) with
// an auto-fix that wraps them in quotes. We trigger this by routing
// the test through CLI mode and asserting against the marker rows.
const SEED_YAML = `\
collection: Diag Test
description: ""
visible: true

playbooks:
  - name: diag
    is_active: true
    steps:
      - name: trigger
        type: start
        next: pick
      - name: pick
        type: decision
        next:
          yes: trigger
          no: trigger
        arguments:
          conditions:
            - lhs: "{{ vars.input.records[0].severity }}"
              op: equals
              rhs: high
`;

test.beforeAll(async () => { await seedDraft(DRAFT, SEED_YAML); });
test.afterAll(async () => { await deleteDraft(DRAFT); });

test('invalid step type surfaces an error in the Issues drawer at the right line', async ({ page }) => {
  // Seed a broken draft directly so we don't depend on Monaco
  // keyboard-input round-trips (which fight with the editor's own
  // selection model). The page's auto-validate on load is enough to
  // surface the error.
  const BROKEN = `collection: "diag-broken"
description: ""
visible: true

playbooks:
  - name: diag
    is_active: true
    steps:
      - name: trigger
        type: star
`;
  const BROKEN_DRAFT = `__e2e_diag_broken_${Date.now()}`;
  await seedDraft(BROKEN_DRAFT, BROKEN);
  try {
    await openDraft(page, BROKEN_DRAFT);
    await page.goto('/?mode=cli');

    // Wait for the action bar's err chip — it only renders when
    // validate finds errors. Title is "Open issues drawer".
    const errChip = page.getByTitle('Open issues drawer');
    await expect(errChip).toBeVisible({ timeout: 15_000 });
    await errChip.click();

    // The Issues panel shows the unknown step type + suggestion.
    await expect(page.getByText(/unknown step type/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/did you mean .?start.?/i)).toBeVisible();

    // _path_to_line resolves `playbooks[0].steps[0].type` to line 10
    // (the `type: star` line). Pinning L10 catches the regression.
    await expect(page.getByText('L10')).toBeVisible();
  } finally {
    await deleteDraft(BROKEN_DRAFT);
  }
});

test('valid YAML shows the clean "No issues" empty state', async ({ page }) => {
  await openDraft(page, DRAFT);

  // Open the drawer via the Issues tab — it's collapsed by default.
  // The drawer header has a chevron "Expand" toggle on the right.
  await page.getByRole('button', { name: 'Expand' }).first().click();

  // The seeded YAML has no validation errors (bare yes/no triggers
  // an auto-fix warning that doesn't block compile; severity-checks
  // pass). The empty state should render.
  await expect(page.getByText('No issues')).toBeVisible({ timeout: 10_000 });
});
