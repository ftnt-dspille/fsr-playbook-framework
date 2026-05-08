/**
 * Coverage for the shared validate / compile / push / push-and-run
 * pipeline. Both Design and CLI route through this module — these
 * tests pin the contract (state mutations, error handling, and the
 * collection/playbook-name extraction the run path depends on).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { playbookActions } from './playbookActions.svelte';
import { playbookStore } from './playbookStore.svelte';
import { runStore } from './runStore.svelte';

let originalFetch: typeof fetch;
let calls: { url: string; method: string; body: any }[];

beforeEach(() => {
  originalFetch = globalThis.fetch;
  calls = [];
  // Reset shared state between tests.
  playbookStore.reset();
  runStore.reset();
  playbookActions.state.markers = [];
  playbookActions.state.fixes = [];
  playbookActions.state.compileJson = null;
  playbookActions.state.status = { kind: 'idle', msg: 'editing' };
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockFetch(handler: (url: string, init?: RequestInit) => any) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({
      url,
      method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(String(init.body)) : null
    });
    const out = handler(url, init);
    if (out instanceof Response) return out;
    return new Response(JSON.stringify(out), { status: 200 });
  }) as any;
}

/** Convenience: drop a YAML buffer into the store so playbookActions
 * can pull it out. Skips the network round-trip a real `open()` does. */
function seedYaml(yaml: string) {
  playbookStore.state.active = {
    kind: 'draft',
    name: 'fixture',
    savedYaml: yaml,
    yaml
  };
}

describe('playbookActions', () => {
  it('validate() with no playbook loaded is a no-op (idle status)', async () => {
    mockFetch(() => { throw new Error('should not call /api'); });
    await playbookActions.validate();
    expect(playbookActions.state.markers).toEqual([]);
    expect(playbookActions.state.status.kind).toBe('idle');
  });

  it('validate() ok with warnings surfaces the warn count', async () => {
    seedYaml('valid: yaml\n');
    mockFetch((url) => {
      if (url === '/api/yaml/validate') return {
        ok: true,
        markers: [
          { line: 1, col: 1, severity: 'warning', code: 'X', message: 'meh', path: '', suggestion: null }
        ],
        fixes: []
      };
      throw new Error(`unexpected ${url}`);
    });
    await playbookActions.validate();
    expect(playbookActions.state.status).toMatchObject({ kind: 'ok', msg: 'valid · 1 warning' });
    expect(playbookActions.warningCount).toBe(1);
  });

  it('validate() failure summarises error count', async () => {
    seedYaml('broken\n');
    mockFetch((url) => {
      if (url === '/api/yaml/validate') return {
        ok: false,
        markers: [
          { line: 1, col: 1, severity: 'error', code: 'A', message: 'bad', path: '', suggestion: null },
          { line: 2, col: 1, severity: 'error', code: 'B', message: 'also bad', path: '', suggestion: null }
        ],
        fixes: []
      };
      throw new Error(`unexpected ${url}`);
    });
    await playbookActions.validate();
    expect(playbookActions.state.status).toMatchObject({ kind: 'err', msg: '2 errors' });
    expect(playbookActions.errorCount).toBe(2);
  });

  it('compile() stores the JSON output for the drawer to render', async () => {
    seedYaml('collection: X\n');
    mockFetch((url) => {
      if (url === '/api/yaml/compile') return {
        ok: true,
        markers: [],
        fsr_json: { collection: 'X', playbooks: [] }
      };
      throw new Error(`unexpected ${url}`);
    });
    await playbookActions.compile();
    expect(playbookActions.state.compileJson).toContain('"collection"');
    expect(playbookActions.state.status.kind).toBe('ok');
  });

  it('push() routes stdout/stderr into runStore.pushOutput and flips status on failure', async () => {
    seedYaml('collection: X\nplaybooks:\n  - name: P\n');
    mockFetch((url, init) => {
      if (url === '/api/playbook/push' && init?.method === 'POST') return {
        ok: false, exit_code: 2, stdout: '', stderr: 'boom'
      };
      throw new Error(`unexpected ${url}`);
    });
    const ok = await playbookActions.push();
    expect(ok).toBe(false);
    expect(runStore.status).toBe('error');
    expect(runStore.pushOutput).toBe('boom');
    expect(playbookActions.state.status.kind).toBe('err');
  });

  it('pushAndRun() short-circuits when push fails', async () => {
    seedYaml('collection: X\nplaybooks:\n  - name: P\n');
    mockFetch((url) => {
      if (url === '/api/playbook/push') return { ok: false, exit_code: 1, stdout: '', stderr: 'nope' };
      // /api/playbook/run should NEVER be hit — push failed.
      if (url === '/api/playbook/run') throw new Error('run should not be invoked');
      throw new Error(`unexpected ${url}`);
    });
    await playbookActions.pushAndRun();
    expect(runStore.status).toBe('error');
    // No SSE call recorded.
    expect(calls.find((c) => c.url === '/api/playbook/run')).toBeUndefined();
  });

  it('pushAndRun() reports a clear error when collection/playbook can\'t be inferred', async () => {
    seedYaml('# comment only, no collection or playbooks\n');
    mockFetch((url) => {
      if (url === '/api/playbook/push') return { ok: true, exit_code: 0, stdout: '', stderr: '' };
      throw new Error(`unexpected ${url}`);
    });
    await playbookActions.pushAndRun();
    expect(playbookActions.state.status).toMatchObject({
      kind: 'err',
      msg: expect.stringMatching(/cannot infer/i)
    });
  });
});
