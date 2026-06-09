/**
 * Tests for the Monaco hover provider registered by registerYamlHover.
 *
 * The provider:
 *   1. Triggers when the cursor is on `arguments:` OR any key under it.
 *   2. Walks upward to find the enclosing step's `type:` at the same indent
 *      as `arguments:`.
 *   3. Fetches /api/ref/step-args/<type> (cached per type) and returns
 *      the markdown as a hover.
 *
 * We exercise it directly against a captured provider + fake model.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

/** yamlHover holds a module-scope helpCache. Re-import per test via
 *  vi.resetModules so each case starts with an empty cache; otherwise
 *  the first test's fetched markdown leaks into later tests' results. */
async function captureProvider() {
  vi.resetModules();
  const { registerYamlHover } = await import('./yamlHover');
  const captured: { provider?: any } = {};
  const monaco = {
    languages: {
      registerHoverProvider: (_lang: string, p: any) => {
        captured.provider = p;
        return { dispose: () => {} };
      }
    }
  };
  registerYamlHover(monaco);
  return captured.provider!;
}

function modelFromLines(lines: string[]) {
  return { getLineContent: (n: number) => lines[n - 1] ?? '' };
}

const fetchSpy = vi.fn();

beforeEach(() => {
  fetchSpy.mockReset();
  // The provider memoizes results in a module-scope Map; we need a
  // fresh provider per test so the cache doesn't leak between assertions.
  (globalThis as any).fetch = fetchSpy;
});

describe('registerYamlHover — enclosing-type discovery', () => {
  const YAML = [
    '  - id: s1',
    '    type: connector',
    '    arguments:',
    '      connector: jira',
    '      operation: create_issue',
    '  - id: s2',
    '    type: set_variable',
    '    arguments:',
    '      arg_list:',
    '        - name: x'
  ];

  it('hover on `arguments:` resolves to the sibling type and fetches help', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ type: 'connector', markdown: '# connector', spec: { summary: 's' } })
    });
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(YAML), {
      lineNumber: 3, // `    arguments:`
      column: 5
    });
    expect(fetchSpy).toHaveBeenCalledWith('/api/ref/step-args/connector');
    expect(result).toEqual({
      contents: [{ value: '# connector', isTrusted: true }]
    });
  });

  it('hover on a key under arguments: walks up to find type:', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ type: 'connector', markdown: '## docs', spec: { summary: '' } })
    });
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(YAML), {
      lineNumber: 4, // `      connector: jira`
      column: 7
    });
    expect(fetchSpy).toHaveBeenCalledWith('/api/ref/step-args/connector');
    expect(result?.contents[0].value).toBe('## docs');
  });

  it('hover in step 2 resolves to set_variable, not the earlier connector step', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ type: 'set_variable', markdown: 'sv-docs', spec: { summary: '' } })
    });
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(YAML), {
      lineNumber: 8, // `    arguments:` of step 2
      column: 5
    });
    expect(fetchSpy).toHaveBeenCalledWith('/api/ref/step-args/set_variable');
    expect(result?.contents[0].value).toBe('sv-docs');
  });

  it('hover on a blank line returns null', async () => {
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(['', '   ']), {
      lineNumber: 1,
      column: 1
    });
    expect(result).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('hover on a top-level non-arguments line returns null', async () => {
    const lines = ['collection: T', 'playbooks:', '  - name: P'];
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(lines), {
      lineNumber: 1,
      column: 3
    });
    expect(result).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('returns null when /api/ref/step-args responds non-ok', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, json: async () => ({}) });
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(YAML), {
      lineNumber: 3,
      column: 5
    });
    expect(result).toBeNull();
  });

  it('returns null when the help payload has no markdown', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ type: 'connector', markdown: null, spec: { summary: '' } })
    });
    const provider = await captureProvider();
    const result = await provider.provideHover(modelFromLines(YAML), {
      lineNumber: 3,
      column: 5
    });
    expect(result).toBeNull();
  });

  it('caches help per step-type (second hover does not re-fetch)', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'connector', markdown: 'cached', spec: { summary: '' } })
    });
    const provider = await captureProvider();
    const model = modelFromLines(YAML);
    await provider.provideHover(model, { lineNumber: 3, column: 5 });
    await provider.provideHover(model, { lineNumber: 4, column: 7 });
    // Both hovers resolve to step type `connector`; second should hit cache.
    const connectorCalls = fetchSpy.mock.calls.filter(
      ([url]) => url === '/api/ref/step-args/connector'
    );
    expect(connectorCalls.length).toBe(1);
  });
});
