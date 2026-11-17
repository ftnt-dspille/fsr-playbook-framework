import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  listVisualFiles,
  getVisualFile,
  getVisualFromBuffer,
  callMcpTool
} from './api';

let fetchMock: any;

beforeEach(() => {
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function ok(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body)
  });
}

describe('listVisualFiles', () => {
  it('GETs /api/visual/list and returns the body', async () => {
    fetchMock.mockReturnValue(ok({ count: 2, files: [{ name: 'a.yaml', size: 10 }, { name: 'b.yaml', size: 20 }] }));
    const r = await listVisualFiles();
    expect(fetchMock).toHaveBeenCalledWith('/api/visual/list');
    expect(r.count).toBe(2);
    expect(r.files[0].name).toBe('a.yaml');
  });

  it('throws on non-2xx', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500 });
    await expect(listVisualFiles()).rejects.toThrow(/visual\/list 500/);
  });
});

describe('getVisualFile', () => {
  it('encodes path and returns the graph', async () => {
    fetchMock.mockReturnValue(ok({ playbooks: [], errors: [], layout_present: false, source: { yaml: '' } }));
    const r = await getVisualFile('decision branch.yaml');
    expect(fetchMock).toHaveBeenCalledWith('/api/visual/file?path=decision%20branch.yaml');
    expect(r.playbooks).toEqual([]);
  });
});

describe('getVisualFromBuffer', () => {
  it('POSTs the text body', async () => {
    fetchMock.mockReturnValue(ok({ playbooks: [], errors: [], layout_present: false, source: { yaml: 'x' } }));
    await getVisualFromBuffer('foo: 1');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/visual/');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ text: 'foo: 1' });
  });
});

describe('callMcpTool', () => {
  it('POSTs to /api/mcp/<tool> and returns the response', async () => {
    fetchMock.mockReturnValue(ok({ ok: true, tool: 'find_connector', result: { matches: [{ name: 'jira' }] } }));
    const r = await callMcpTool<{ matches: { name: string }[] }>('find_connector', { q: 'jira' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/mcp/find_connector');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ q: 'jira' });
    expect(r.ok).toBe(true);
    expect(r.result?.matches[0].name).toBe('jira');
  });

  it('url-encodes tool names', async () => {
    fetchMock.mockReturnValue(ok({ ok: true, tool: 'foo bar', result: {} }));
    await callMcpTool('foo bar', {});
    expect(fetchMock.mock.calls[0][0]).toBe('/api/mcp/foo%20bar');
  });
});
