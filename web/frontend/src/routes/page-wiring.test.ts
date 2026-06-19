/**
 * Page-level integration coverage. Mounts a harness that mirrors the
 * effect graph in `src/routes/+page.svelte` and drives `playbookStore`
 * + simulated Monaco input to pin contracts that broke this session:
 *
 *  1. Switching drafts must NOT clobber the new draft with the
 *     previous draft's edited buffer (the bug where typing into A
 *     then clicking B left A's text in B's slot).
 *  2. CLI keystrokes must mark `playbookStore.dirty` so Save enables
 *     and autosave / auto-verify arm.
 *  3. Round-trip: store mutations update the local `yaml`, and
 *     local edits update the store.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import { flushSync, tick } from 'svelte';
import PageWiringHarness from '$lib/__test_harness/PageWiringHarness.svelte';
import { playbookStore } from '$lib/playbookStore.svelte';

const YAML_A = 'collection: "a"\nplaybooks:\n- name: a\n  steps:\n  - name: s\n    type: start\n';
const YAML_B = 'collection: "b"\nplaybooks:\n- name: b\n  steps:\n  - name: s\n    type: start\n';

function stubFetch() {
  // Stub draft GETs only — open() does network IO.
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/playbooks/draft/A')) {
      return new Response(JSON.stringify({ name: 'A', yaml: YAML_A }));
    }
    if (url.includes('/api/playbooks/draft/B')) {
      return new Response(JSON.stringify({ name: 'B', yaml: YAML_B }));
    }
    if (url.includes('/api/playbooks/draft/A/revisions')) {
      return new Response(JSON.stringify({ revisions: [] }));
    }
    if (url.includes('/api/playbooks/draft/B/revisions')) {
      return new Response(JSON.stringify({ revisions: [] }));
    }
    if (url.includes('/revisions')) {
      return new Response(JSON.stringify({ revisions: [] }));
    }
    return new Response('{}', { status: 404 });
  }) as any;
}

type HarnessAPI = { getYaml: () => string; typeIntoEditor: (v: string) => void };

function mountHarness(): HarnessAPI {
  let api: HarnessAPI | null = null;
  render(PageWiringHarness as any, { props: { onReady: (a: HarnessAPI) => { api = a; } } });
  flushSync();
  if (!api) throw new Error('harness onReady did not fire');
  return api;
}

beforeEach(() => {
  cleanup();
  stubFetch();
  // Reset stores so each test starts from a clean slate.
  playbookStore.reset();
});

describe('page wiring — draft switch', () => {
  it('switching to a freshly-loaded draft displays that draft\'s yaml', async () => {
    const api = mountHarness();
    await playbookStore.open('draft', 'A');
    flushSync();
    expect(api.getYaml()).toBe(YAML_A);
    expect(playbookStore.state.active?.yaml).toBe(YAML_A);

    await playbookStore.open('draft', 'B');
    flushSync();
    expect(api.getYaml()).toBe(YAML_B);
    expect(playbookStore.state.active?.yaml).toBe(YAML_B);
  });

  it('typing into A then switching to B does NOT clobber B with A\'s buffer', async () => {
    const api = mountHarness();
    await playbookStore.open('draft', 'A');
    flushSync();

    // Simulate the user typing — this is what the previous bug exploited:
    // an effect on `yaml` also wrote to playbookStore, so when the
    // active-sync effect later swapped state.active to B, the stale
    // `yaml` got written into B's slot.
    api.typeIntoEditor(YAML_A + '\n# edited\n');
    flushSync();
    expect(playbookStore.dirty).toBe(true);
    expect(playbookStore.state.active?.name).toBe('A');
    expect(playbookStore.state.active?.yaml).toContain('# edited');

    // Now switch to draft B.
    await playbookStore.open('draft', 'B');
    flushSync();

    // The freshly-loaded B yaml must be intact — NOT polluted by A's
    // edited buffer.
    expect(api.getYaml()).toBe(YAML_B);
    expect(playbookStore.state.active?.name).toBe('B');
    expect(playbookStore.state.active?.yaml).toBe(YAML_B);
    expect(playbookStore.state.active?.yaml).not.toContain('# edited');
  });
});

describe('page wiring — dirty propagation', () => {
  it('typing marks the active draft dirty', async () => {
    const api = mountHarness();
    await playbookStore.open('draft', 'A');
    flushSync();
    expect(playbookStore.dirty).toBe(false);

    api.typeIntoEditor(YAML_A + '# k\n');
    flushSync();
    expect(playbookStore.dirty).toBe(true);
  });

  it('the dirty flag clears once the buffer matches savedYaml again', async () => {
    const api = mountHarness();
    await playbookStore.open('draft', 'A');
    flushSync();

    api.typeIntoEditor(YAML_A + 'x');
    flushSync();
    expect(playbookStore.dirty).toBe(true);

    api.typeIntoEditor(YAML_A);
    flushSync();
    expect(playbookStore.dirty).toBe(false);
  });
});

describe('page wiring — store↔editor round-trip', () => {
  it('mutating playbookStore externally updates the local yaml', async () => {
    const api = mountHarness();
    // Simulate a programmatic write (e.g. revision restore, replay
    // hydration). bindings.yaml derives from playbookStore.currentYaml
    // so the editor reflects it on the next tick.
    await playbookStore.open('draft', 'A');
    flushSync();
    playbookStore.replaceYaml('hello: world\n', 'test mutation');
    await tick();
    flushSync();
    expect(api.getYaml()).toBe('hello: world\n');
  });
});
