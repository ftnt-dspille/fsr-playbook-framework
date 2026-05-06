/**
 * Behavior tests for the editor buffer + drafts store.
 *
 * The store is a module-level singleton, so we reset its state between
 * tests rather than re-importing. localStorage is jsdom-provided.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { yamlStore } from './yamlStore.svelte';

const SAMPLE = `collection: My Pipeline
playbooks:
  - name: A
    steps:
      - id: start
        type: start
`;

const SAMPLE2 = `collection: Other
playbooks:
  - name: B
    steps:
      - id: start
        type: start
`;

beforeEach(() => {
  // Reset the singleton between tests so state from one doesn't leak.
  // Setting `text` directly skips the snapshot mechanism, which is
  // exactly what we want for cleanup.
  yamlStore.text = '';
  yamlStore.drafts = [];
  yamlStore.lastSnapshot = null;
  localStorage.clear();
});

describe('setText', () => {
  it('replaces the buffer', () => {
    yamlStore.text = 'before';
    yamlStore.setText('after', 'test');
    expect(yamlStore.text).toBe('after');
  });

  it('snapshots the previous content', () => {
    yamlStore.text = 'before';
    yamlStore.setText('after', 'loaded example: foo');
    expect(yamlStore.lastSnapshot).not.toBeNull();
    expect(yamlStore.lastSnapshot?.text).toBe('before');
    expect(yamlStore.lastSnapshot?.reason).toBe('loaded example: foo');
  });

  it('does not snapshot when previous buffer is empty', () => {
    yamlStore.text = '';
    yamlStore.setText('first content', 'init');
    expect(yamlStore.lastSnapshot).toBeNull();
  });

  it('does not snapshot when text is unchanged', () => {
    yamlStore.text = 'same';
    yamlStore.setText('same', 'noop');
    expect(yamlStore.lastSnapshot).toBeNull();
  });
});

describe('saveDraft', () => {
  it('appends a new draft', () => {
    yamlStore.text = SAMPLE;
    const d = yamlStore.saveDraft('My Pipeline');
    expect(d.name).toBe('My Pipeline');
    expect(d.text).toBe(SAMPLE);
    expect(yamlStore.drafts).toHaveLength(1);
  });

  it('replaces an existing draft with the same name', () => {
    yamlStore.text = SAMPLE;
    yamlStore.saveDraft('p');
    yamlStore.text = SAMPLE2;
    yamlStore.saveDraft('p');
    expect(yamlStore.drafts).toHaveLength(1);
    expect(yamlStore.drafts[0].text).toBe(SAMPLE2);
  });

  it('puts most-recent at the top', () => {
    yamlStore.text = SAMPLE;
    yamlStore.saveDraft('first');
    yamlStore.text = SAMPLE2;
    yamlStore.saveDraft('second');
    expect(yamlStore.drafts.map((d) => d.name)).toEqual(['second', 'first']);
  });

  it('rejects empty / whitespace names', () => {
    yamlStore.text = SAMPLE;
    expect(() => yamlStore.saveDraft('')).toThrow();
    expect(() => yamlStore.saveDraft('   ')).toThrow();
  });

  it('trims surrounding whitespace from the name', () => {
    yamlStore.text = SAMPLE;
    const d = yamlStore.saveDraft('  trimmed  ');
    expect(d.name).toBe('trimmed');
  });
});

describe('loadDraft', () => {
  it('swaps the buffer and snapshots the previous content', () => {
    yamlStore.text = SAMPLE;
    yamlStore.saveDraft('saved');
    yamlStore.text = 'mid-edit';
    yamlStore.loadDraft('saved');
    expect(yamlStore.text).toBe(SAMPLE);
    expect(yamlStore.lastSnapshot?.text).toBe('mid-edit');
    expect(yamlStore.lastSnapshot?.reason).toMatch(/loaded draft/);
  });

  it('throws on unknown draft name', () => {
    expect(() => yamlStore.loadDraft('does-not-exist')).toThrow();
  });
});

describe('deleteDraft', () => {
  it('removes the named draft', () => {
    yamlStore.text = SAMPLE;
    yamlStore.saveDraft('a');
    yamlStore.text = SAMPLE2;
    yamlStore.saveDraft('b');
    yamlStore.deleteDraft('a');
    expect(yamlStore.drafts.map((d) => d.name)).toEqual(['b']);
  });

  it('is a noop for unknown names', () => {
    yamlStore.text = SAMPLE;
    yamlStore.saveDraft('a');
    yamlStore.deleteDraft('not-here');
    expect(yamlStore.drafts).toHaveLength(1);
  });
});

describe('restoreSnapshot', () => {
  it('returns to the snapshotted buffer', () => {
    yamlStore.text = 'original';
    yamlStore.setText('replaced', 'whatever');
    yamlStore.restoreSnapshot();
    expect(yamlStore.text).toBe('original');
  });

  it('is itself undoable (cur becomes the new snapshot)', () => {
    yamlStore.text = 'A';
    yamlStore.setText('B', 'load');
    yamlStore.restoreSnapshot();
    expect(yamlStore.text).toBe('A');
    yamlStore.restoreSnapshot();
    expect(yamlStore.text).toBe('B');
  });

  it('is a noop when there is nothing to restore', () => {
    yamlStore.text = 'only';
    yamlStore.lastSnapshot = null;
    yamlStore.restoreSnapshot();
    expect(yamlStore.text).toBe('only');
  });
});

describe('reset', () => {
  it('replaces buffer with the placeholder and snapshots', () => {
    yamlStore.text = SAMPLE;
    yamlStore.reset();
    // placeholder always starts with the welcome comment
    expect(yamlStore.text).toMatch(/Welcome/);
    expect(yamlStore.lastSnapshot?.text).toBe(SAMPLE);
    expect(yamlStore.lastSnapshot?.reason).toBe('reset');
  });
});

describe('suggestedName', () => {
  it('extracts the collection name', () => {
    yamlStore.text = SAMPLE;
    expect(yamlStore.suggestedName()).toBe('My Pipeline');
  });

  it('strips quotes', () => {
    yamlStore.text = 'collection: "Quoted Name"\n';
    expect(yamlStore.suggestedName()).toBe('Quoted Name');
  });

  it('returns empty string when no collection line', () => {
    yamlStore.text = 'no collection here\n';
    expect(yamlStore.suggestedName()).toBe('');
  });
});

describe('appendDraftRevision', () => {
  it('creates a new draft with one revision when none exists', () => {
    yamlStore.appendDraftRevision('Chat: New', 'collection: A\n', 'agent', {
      message: 'build hello world',
      sessionId: 'sess1'
    });
    const d = yamlStore.drafts[0];
    expect(d.name).toBe('Chat: New');
    expect(d.text).toBe('collection: A\n');
    expect(d.revisions).toHaveLength(1);
    expect(d.revisions![0].source).toBe('agent');
    expect(d.revisions![0].message).toBe('build hello world');
    expect(d.revisions![0].sessionId).toBe('sess1');
  });

  it('appends new revisions newest-first to an existing draft', () => {
    yamlStore.appendDraftRevision('Chat: Iterate', 'collection: A\n', 'agent');
    yamlStore.appendDraftRevision('Chat: Iterate', 'collection: B\n', 'agent', {
      message: 'rename it'
    });
    const d = yamlStore.drafts[0];
    expect(d.text).toBe('collection: B\n');
    expect(d.revisions).toHaveLength(2);
    expect(d.revisions![0].text).toBe('collection: B\n');
    expect(d.revisions![1].text).toBe('collection: A\n');
  });

  it('de-dupes adjacent identical text', () => {
    yamlStore.appendDraftRevision('Chat: Same', 'X', 'agent');
    yamlStore.appendDraftRevision('Chat: Same', 'X', 'agent');
    expect(yamlStore.drafts[0].revisions).toHaveLength(1);
  });

  it('synthesizes a baseline revision when extending a legacy draft', () => {
    // Legacy shape: no revisions[] field on the draft.
    yamlStore.text = 'legacy yaml';
    yamlStore.saveDraft('Legacy');
    // Strip revisions to simulate pre-history-feature state.
    const idx = yamlStore.drafts.findIndex((d) => d.name === 'Legacy');
    yamlStore.drafts[idx] = {
      name: 'Legacy',
      text: 'legacy yaml',
      savedAt: new Date().toISOString()
    };
    yamlStore.appendDraftRevision('Legacy', 'agent edit', 'agent', {
      message: 'fix it'
    });
    const d = yamlStore.drafts.find((x) => x.name === 'Legacy')!;
    expect(d.revisions).toHaveLength(2);
    expect(d.revisions![0].text).toBe('agent edit');
    expect(d.revisions![1].text).toBe('legacy yaml');
    expect(d.revisions![1].source).toBe('user');
  });
});

describe('loadDraftRevision', () => {
  it('loads a specific historical revision into the buffer', () => {
    yamlStore.text = 'before';
    yamlStore.appendDraftRevision('Chat: H', 'rev0', 'agent');
    yamlStore.appendDraftRevision('Chat: H', 'rev1', 'agent');
    yamlStore.loadDraftRevision('Chat: H', 1);
    expect(yamlStore.text).toBe('rev0');
    expect(yamlStore.lastSnapshot?.reason).toMatch(/Chat: H revision 1/);
  });

  it('throws on out-of-range index', () => {
    yamlStore.appendDraftRevision('Chat: H2', 'rev0', 'agent');
    expect(() => yamlStore.loadDraftRevision('Chat: H2', 99)).toThrow();
  });
});
