/**
 * Compile E2E: the seeded draft is a minimal-but-valid playbook;
 * the compile endpoint should produce a clean FSR-shaped JSON with
 * no error-level markers.
 *
 * Asserts at the API level (not the UI Compile button) because the
 * diagnostics drawer is a render concern; the contract that matters
 * is "valid YAML → backend compile → workflow JSON". We hit it
 * directly through the backend the e2e fixture is already running.
 */
import { test, expect } from '@playwright/test';
import { SAMPLE_YAML } from './helpers';

test('compile a valid playbook returns fsr_json with no error markers', async ({ request }) => {
  const r = await request.post('http://localhost:47821/api/yaml/compile', {
    data: { text: SAMPLE_YAML }
  });
  expect(r.ok()).toBe(true);
  const body = await r.json();
  // Compile returns `{ ok, fsr_json, markers }`. Markers carry `severity`
  // ('error' | 'warning' | 'info'); warnings are acceptable, errors are not.
  const errors = (body.markers ?? []).filter((m: any) => m.severity === 'error');
  expect(errors).toEqual([]);
  expect(body.ok).toBe(true);
  expect(body.fsr_json).toBeTruthy();
  // fsr_json is a workflow_collections envelope:
  //   { data: [{ workflows: [{ steps: [...] }] }] }
  // Two seeded YAML steps → ≥2 emitted in the first workflow.
  const wf = body.fsr_json?.data?.[0]?.workflows?.[0];
  expect(Array.isArray(wf?.steps)).toBe(true);
  expect(wf.steps.length).toBeGreaterThanOrEqual(2);
});

test('compile bad YAML surfaces an error marker instead of crashing', async ({ request }) => {
  const r = await request.post('http://localhost:47821/api/yaml/compile', {
    data: { text: 'name: broken\nsteps: not-a-list\n' }
  });
  // Even malformed input gets a 200 with markers — the editor
  // relies on this so the inspector can render quick-fixes.
  expect(r.ok()).toBe(true);
  const body = await r.json();
  const errors = (body.markers ?? []).filter((m: any) => m.severity === 'error');
  expect(errors.length).toBeGreaterThan(0);
});
