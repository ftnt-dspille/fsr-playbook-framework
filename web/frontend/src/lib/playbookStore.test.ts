import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { playbookStore } from './playbookStore.svelte';

let originalFetch: typeof fetch;
let calls: { url: string; method: string; body: unknown }[];

beforeEach(() => {
  originalFetch = globalThis.fetch;
  calls = [];
  // Reset store between tests so prior `active` doesn't leak.
  playbookStore.reset();
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

describe('playbookStore', () => {
  it('refresh() splits items into draft + example buckets', async () => {
    mockFetch((url) => {
      if (url === '/api/playbooks') return {
        count: 3,
        items: [
          { kind: 'draft', name: 'wip', size: 100, updated_ts: '2026-05-08' },
          { kind: 'example', name: 'a.yaml', size: 200, updated_ts: '2026-05-01' },
          { kind: 'example', name: 'b.yaml', size: 300, updated_ts: '2026-05-02' }
        ]
      };
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.refresh();
    expect(playbookStore.state.drafts).toHaveLength(1);
    expect(playbookStore.state.examples).toHaveLength(2);
    expect(playbookStore.state.drafts[0].name).toBe('wip');
  });

  it('open() loads a draft + its revisions', async () => {
    mockFetch((url) => {
      if (url === '/api/playbooks/draft/wip') return {
        kind: 'draft', name: 'wip', yaml: 'a: 1\n',
        created_ts: 't1', updated_ts: 't2'
      };
      if (url === '/api/playbooks/draft/wip/revisions') return {
        count: 2,
        revisions: [
          { id: 7, reason: 'manual save', is_auto: false, created_ts: 't2', size: 4 },
          { id: 6, reason: 'created', is_auto: false, created_ts: 't1', size: 4 }
        ]
      };
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('draft', 'wip');
    expect(playbookStore.state.active?.kind).toBe('draft');
    expect(playbookStore.state.active?.name).toBe('wip');
    expect(playbookStore.currentYaml).toBe('a: 1\n');
    expect(playbookStore.state.revisions).toHaveLength(2);
    expect(playbookStore.dirty).toBe(false);
  });

  it('open() loads an example without trying to fetch revisions', async () => {
    mockFetch((url) => {
      if (url.startsWith('/api/playbooks/example/')) return {
        kind: 'example', name: 'sample.yaml', yaml: 'b: 2\n'
      };
      if (url.includes('/revisions')) {
        // Should NOT happen for examples.
        throw new Error('examples have no revisions endpoint');
      }
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('example', 'sample.yaml');
    expect(playbookStore.state.active?.kind).toBe('example');
    expect(playbookStore.isExample).toBe(true);
    expect(playbookStore.state.revisions).toEqual([]);
  });

  it('setYaml + save: dirty toggles, PUT body matches contract', async () => {
    mockFetch((url, init) => {
      if (url === '/api/playbooks/draft/wip' && (init?.method ?? 'GET') === 'GET') {
        return { kind: 'draft', name: 'wip', yaml: 'a: 1\n', created_ts: 't', updated_ts: 't' };
      }
      if (url === '/api/playbooks/draft/wip' && init?.method === 'PUT') {
        return { ok: true, revision_id: 99, updated_ts: 't3' };
      }
      if (url === '/api/playbooks/draft/wip/revisions') {
        return { count: 1, revisions: [{ id: 99, reason: 'manual save', is_auto: false, created_ts: 't3', size: 6 }] };
      }
      if (url === '/api/playbooks') {
        return { count: 0, items: [] };
      }
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('draft', 'wip');
    expect(playbookStore.dirty).toBe(false);
    playbookStore.replaceYaml('a: 99\n');
    expect(playbookStore.dirty).toBe(true);

    const r = await playbookStore.save({ reason: 'test save' });
    expect(r.ok).toBe(true);
    expect(playbookStore.dirty).toBe(false);

    const put = calls.find((c) => c.method === 'PUT');
    expect(put?.body).toEqual({ yaml: 'a: 99\n', reason: 'test save', auto: false });
  });

  it('save() is a no-op when buffer matches savedYaml (no duplicate revisions)', async () => {
    mockFetch((url, init) => {
      if (url === '/api/playbooks/draft/wip' && (init?.method ?? 'GET') === 'GET') {
        return { kind: 'draft', name: 'wip', yaml: 'a: 1\n', created_ts: 't', updated_ts: 't' };
      }
      if (url === '/api/playbooks/draft/wip' && init?.method === 'PUT') {
        return { ok: true, revision_id: 99, updated_ts: 't3' };
      }
      if (url === '/api/playbooks/draft/wip/revisions') {
        return { count: 1, revisions: [{ id: 99, reason: 'manual save', is_auto: false, created_ts: 't3', size: 6 }] };
      }
      if (url === '/api/playbooks') return { count: 0, items: [] };
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('draft', 'wip');
    playbookStore.replaceYaml('a: 99\n');
    const r1 = await playbookStore.save({ reason: 'first' });
    expect(r1.ok).toBe(true);
    const putsAfterFirst = calls.filter((c) => c.method === 'PUT').length;
    expect(putsAfterFirst).toBe(1);

    // Clicking Save again with no further edits must NOT mint a second revision.
    const r2 = await playbookStore.save({ reason: 'second' });
    expect(r2.ok).toBe(true);
    expect(r2.message).toBe('no changes');
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1);

    // And a third click stays a no-op.
    await playbookStore.save({ reason: 'third' });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1);

    // After a real edit, Save resumes persisting.
    playbookStore.replaceYaml('a: 100\n');
    await playbookStore.save({ reason: 'fourth' });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(2);
  });

  it('save() refuses while viewing an example', async () => {
    mockFetch((url) => {
      if (url.startsWith('/api/playbooks/example/')) return {
        kind: 'example', name: 'sample.yaml', yaml: 'b: 2\n'
      };
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('example', 'sample.yaml');
    const r = await playbookStore.save();
    expect(r.ok).toBe(false);
    expect(r.message).toMatch(/clone/i);
  });

  it('autoSnapshot fires only when dirty + on a draft', async () => {
    mockFetch((url, init) => {
      if (url === '/api/playbooks/draft/wip' && (init?.method ?? 'GET') === 'GET') {
        return { kind: 'draft', name: 'wip', yaml: 'a: 1\n', created_ts: 't', updated_ts: 't' };
      }
      if (url === '/api/playbooks/draft/wip' && init?.method === 'PUT') {
        return { ok: true, revision_id: 50, updated_ts: 't2' };
      }
      if (url === '/api/playbooks/draft/wip/revisions') {
        return { count: 0, revisions: [] };
      }
      if (url === '/api/playbooks') return { count: 0, items: [] };
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('draft', 'wip');
    // Clean → no PUT.
    await playbookStore.autoSnapshot('mode-switch');
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0);

    // Dirty → PUT with auto:true.
    playbookStore.replaceYaml('a: 2\n');
    await playbookStore.autoSnapshot('mode-switch');
    const put = calls.find((c) => c.method === 'PUT');
    expect((put?.body as any).auto).toBe(true);
    expect((put?.body as any).reason).toBe('mode-switch');
  });

  it('cloneExample posts to from-example endpoint and opens the new draft', async () => {
    mockFetch((url, init) => {
      if (url === '/api/playbooks/draft/from-example' && init?.method === 'POST') {
        return { ok: true, name: 'my_clone', revision_id: 1, from_example: 'src.yaml' };
      }
      if (url === '/api/playbooks') {
        return { count: 1, items: [{ kind: 'draft', name: 'my_clone', size: 10, updated_ts: 't' }] };
      }
      if (url === '/api/playbooks/draft/my_clone' && (init?.method ?? 'GET') === 'GET') {
        return { kind: 'draft', name: 'my_clone', yaml: 'cloned: yes\n', created_ts: 't', updated_ts: 't' };
      }
      if (url === '/api/playbooks/draft/my_clone/revisions') {
        return { count: 1, revisions: [{ id: 1, reason: 'cloned from example: src.yaml', is_auto: false, created_ts: 't', size: 10 }] };
      }
      throw new Error(`unexpected ${url}`);
    });

    const r = await playbookStore.cloneExample('src.yaml', 'my_clone');
    expect(r.ok).toBe(true);
    expect(playbookStore.state.active?.name).toBe('my_clone');
    const post = calls.find((c) => c.method === 'POST');
    expect(post?.body).toEqual({ example: 'src.yaml', draft: 'my_clone' });
  });

  it('loadRevision swaps the buffer without persisting', async () => {
    mockFetch((url, init) => {
      if (url === '/api/playbooks/draft/wip' && (init?.method ?? 'GET') === 'GET') {
        return { kind: 'draft', name: 'wip', yaml: 'head\n', created_ts: 't', updated_ts: 't' };
      }
      if (url === '/api/playbooks/draft/wip/revisions' && (init?.method ?? 'GET') === 'GET') {
        return { count: 0, revisions: [] };
      }
      if (url === '/api/playbooks/draft/wip/revisions/42') {
        return { id: 42, yaml: 'old: revision\n', reason: null, is_auto: false, created_ts: 't' };
      }
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('draft', 'wip');
    const r = await playbookStore.loadRevision(42);
    expect(r.ok).toBe(true);
    expect(playbookStore.currentYaml).toBe('old: revision\n');
    expect(playbookStore.dirty).toBe(true); // differs from saved head
  });

  it('open() persists a "last opened" pointer that readLastOpened recovers', async () => {
    mockFetch((url) => {
      if (url === '/api/playbooks/draft/persisted') return {
        kind: 'draft', name: 'persisted', yaml: 'a\n', created_ts: 't', updated_ts: 't'
      };
      if (url === '/api/playbooks/draft/persisted/revisions') return { count: 0, revisions: [] };
      throw new Error(`unexpected ${url}`);
    });

    // Clear any leftover pointer from another test before we assert.
    try { localStorage.removeItem('fsrpb.last_opened'); } catch {}
    expect(playbookStore.readLastOpened()).toBeNull();

    await playbookStore.open('draft', 'persisted');
    expect(playbookStore.readLastOpened()).toEqual({ kind: 'draft', name: 'persisted' });
  });

  it('readLastOpened returns null when the localStorage entry is malformed', () => {
    try { localStorage.setItem('fsrpb.last_opened', 'not json'); } catch {}
    expect(playbookStore.readLastOpened()).toBeNull();
    try { localStorage.setItem('fsrpb.last_opened', '{"kind":"banana","name":"x"}'); } catch {}
    expect(playbookStore.readLastOpened()).toBeNull();
    try { localStorage.removeItem('fsrpb.last_opened'); } catch {}
  });

  it('deleteDraft clears the active doc if the deleted name matched', async () => {
    mockFetch((url, init) => {
      if (url === '/api/playbooks/draft/throwaway' && (init?.method ?? 'GET') === 'GET') {
        return { kind: 'draft', name: 'throwaway', yaml: 'x\n', created_ts: 't', updated_ts: 't' };
      }
      if (url === '/api/playbooks/draft/throwaway/revisions') {
        return { count: 0, revisions: [] };
      }
      if (url === '/api/playbooks/draft/throwaway' && init?.method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      if (url === '/api/playbooks') return { count: 0, items: [] };
      throw new Error(`unexpected ${url}`);
    });

    await playbookStore.open('draft', 'throwaway');
    expect(playbookStore.state.active).toBeTruthy();
    const r = await playbookStore.deleteDraft('throwaway');
    expect(r.ok).toBe(true);
    expect(playbookStore.state.active).toBeNull();
  });
});
