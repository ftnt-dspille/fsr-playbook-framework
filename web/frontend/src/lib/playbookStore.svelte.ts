/**
 * Unified active-playbook store for Studio.
 *
 * Replaces the per-mode ownership of "the active YAML" — yamlStore.text
 * for CLI and visualStore.filePath/source.yaml for Design — with one
 * authoritative document that both modes read from and write to.
 *
 * The actual YAML byte stream lives here. visualStore still owns the
 * parsed graph + edit operations (drag/drop, addNode, etc.); on the
 * Design save path the graph is rendered to YAML through the emitter
 * and pushed back into this store.
 *
 * Backed by the /api/playbooks endpoints (Phase A): one server-side
 * drafts table with revisions, plus the read-only examples/ directory.
 */
import {
  listPlaybooks,
  getExample,
  getDraft,
  putDraft,
  listDraftRevisions,
  getDraftRevision,
  cloneExample as cloneExampleApi,
  deleteDraft as deleteDraftApi,
  type PlaybookKind,
  type PlaybookListItem,
  type DraftRevision
} from './api';

type ActiveDoc = {
  kind: PlaybookKind;
  name: string;
  /** YAML on disk / latest saved revision. The source of truth for
   * "what's been persisted" — `dirty` derives from comparing against
   * this snapshot. */
  savedYaml: string;
  /** Live editor buffer. Both modes read/write this. */
  yaml: string;
};

type State = {
  active: ActiveDoc | null;
  drafts: PlaybookListItem[];
  examples: PlaybookListItem[];
  /** Last-known revisions for the active draft, newest first. Empty
   * when active is an example or no draft loaded yet. */
  revisions: DraftRevision[];
  loading: boolean;
  saving: boolean;
  error: string | null;
};

const state = $state<State>({
  active: null,
  drafts: [],
  examples: [],
  revisions: [],
  loading: false,
  saving: false,
  error: null
});

function bucket(items: PlaybookListItem[]) {
  const drafts: PlaybookListItem[] = [];
  const examples: PlaybookListItem[] = [];
  for (const it of items) {
    if (it.kind === 'draft') drafts.push(it);
    else examples.push(it);
  }
  return { drafts, examples };
}

export const playbookStore = {
  get state() { return state; },
  get yaml() { return state.active?.yaml ?? ''; },
  get dirty() {
    return !!state.active && state.active.yaml !== state.active.savedYaml;
  },
  get isExample() { return state.active?.kind === 'example'; },

  /** Refresh the picker contents. Cheap (single GET) so callers can
   * fire-and-forget after any mutation. */
  async refresh(): Promise<void> {
    try {
      const r = await listPlaybooks();
      const { drafts, examples } = bucket(r.items);
      state.drafts = drafts;
      state.examples = examples;
    } catch (e) {
      state.error = (e as Error).message;
    }
  },

  /** Load a playbook into the active slot. Discards the current edit
   * buffer; callers responsible for `if (dirty) confirm(…)`. */
  async open(kind: PlaybookKind, name: string): Promise<void> {
    state.loading = true;
    state.error = null;
    try {
      const fetched = kind === 'draft' ? await getDraft(name) : await getExample(name);
      state.active = {
        kind,
        name,
        savedYaml: fetched.yaml,
        yaml: fetched.yaml
      };
      state.revisions = [];
      if (kind === 'draft') {
        try {
          const rl = await listDraftRevisions(name);
          state.revisions = rl.revisions;
        } catch { /* missing revisions is non-fatal */ }
      }
      // Pin "last opened" so a refresh restores the playbook the user
      // was working on instead of dropping them on the welcome example.
      try {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('fsrpb.last_opened', JSON.stringify({ kind, name }));
        }
      } catch { /* localStorage full / disabled — fall back silently */ }
    } catch (e) {
      state.error = (e as Error).message;
    } finally {
      state.loading = false;
    }
  },

  /** Read the persisted "last opened" pointer. Returns null when the
   * pointer is missing, malformed, or localStorage is unavailable. */
  readLastOpened(): { kind: PlaybookKind; name: string } | null {
    if (typeof localStorage === 'undefined') return null;
    try {
      const raw = localStorage.getItem('fsrpb.last_opened');
      if (!raw) return null;
      const v = JSON.parse(raw);
      if (v && (v.kind === 'draft' || v.kind === 'example') && typeof v.name === 'string') {
        return v;
      }
    } catch { /* corrupted — ignore */ }
    return null;
  },

  /** Update the live buffer. Cheap; called on every keystroke or graph
   * mutation. Does NOT persist. */
  setYaml(next: string): void {
    if (!state.active) return;
    if (state.active.yaml === next) return;
    state.active.yaml = next;
  },

  /** Persist the live buffer as a new revision on the active draft.
   * `auto=true` flags it as a system-fired snapshot (mode switch /
   * picker change / deploy). Examples have no save path — they must be
   * cloned first. */
  async save(opts: { reason?: string; auto?: boolean } = {}): Promise<{ ok: boolean; message?: string }> {
    if (!state.active) return { ok: false, message: 'no playbook loaded' };
    if (state.active.kind === 'example') {
      return { ok: false, message: 'examples are read-only — clone to a draft first' };
    }
    state.saving = true;
    state.error = null;
    try {
      await putDraft(state.active.name, state.active.yaml, opts);
      state.active.savedYaml = state.active.yaml;
      // Refresh revisions so the drawer reflects the new entry.
      const rl = await listDraftRevisions(state.active.name);
      state.revisions = rl.revisions;
      // Picker `updated_ts` likely changed too.
      void this.refresh();
      return { ok: true };
    } catch (e) {
      state.error = (e as Error).message;
      return { ok: false, message: state.error ?? undefined };
    } finally {
      state.saving = false;
    }
  },

  /** Convenience: snapshot the current buffer as an auto-revision and
   * keep editing. No-op when there's no draft loaded or buffer matches
   * the saved YAML. */
  async autoSnapshot(reason: string): Promise<void> {
    if (!state.active || state.active.kind !== 'draft') return;
    if (state.active.yaml === state.active.savedYaml) return;
    await this.save({ reason, auto: true });
  },

  /** Clone an example into a new draft and immediately make it active. */
  async cloneExample(example: string, draft: string): Promise<{ ok: boolean; message?: string }> {
    state.error = null;
    try {
      await cloneExampleApi(example, draft);
      await this.refresh();
      await this.open('draft', draft);
      return { ok: true };
    } catch (e) {
      state.error = (e as Error).message;
      return { ok: false, message: state.error ?? undefined };
    }
  },

  /** Create a brand-new empty draft. */
  async createDraft(name: string, yaml: string = ''): Promise<{ ok: boolean; message?: string }> {
    state.error = null;
    try {
      await putDraft(name, yaml, { reason: 'created', auto: false });
      await this.refresh();
      await this.open('draft', name);
      return { ok: true };
    } catch (e) {
      state.error = (e as Error).message;
      return { ok: false, message: state.error ?? undefined };
    }
  },

  async deleteDraft(name: string): Promise<{ ok: boolean; message?: string }> {
    state.error = null;
    try {
      await deleteDraftApi(name);
      if (state.active?.kind === 'draft' && state.active.name === name) {
        state.active = null;
        state.revisions = [];
      }
      await this.refresh();
      return { ok: true };
    } catch (e) {
      state.error = (e as Error).message;
      return { ok: false, message: state.error ?? undefined };
    }
  },

  /** Load a specific revision into the live buffer (without writing).
   * The user can then Save to promote it back to head, or discard. */
  async loadRevision(id: number): Promise<{ ok: boolean; message?: string }> {
    if (!state.active || state.active.kind !== 'draft') {
      return { ok: false, message: 'no draft active' };
    }
    try {
      const r = await getDraftRevision(state.active.name, id);
      state.active.yaml = r.yaml;
      return { ok: true };
    } catch (e) {
      return { ok: false, message: (e as Error).message };
    }
  },

  /** Clear the active doc (used by replay flows / explicit "new"). */
  reset(): void {
    state.active = null;
    state.revisions = [];
    state.error = null;
  },

  /** Push localStorage-era drafts into the server table so they appear
   * in PlaybookHeader alongside Design drafts. Skips any name already
   * present on the server (no overwrite) and reports `{migrated, skipped}`
   * counts so callers can surface a status message.
   *
   * Called once per browser via the `fsrpb.drafts.migrated_v1` flag —
   * exposed here as a method (not free-floating in +page.svelte) so it
   * can be unit-tested without rendering the page. */
  async migrateLocalDrafts(
    localDrafts: { name: string; text?: string; revisions?: { text: string }[] }[]
  ): Promise<{ migrated: number; skipped: number }> {
    await this.refresh();
    const serverNames = new Set(state.drafts.map((d) => d.name));
    let migrated = 0;
    let skipped = 0;
    for (const d of localDrafts) {
      if (serverNames.has(d.name)) { skipped++; continue; }
      const text = d.text ?? d.revisions?.[0]?.text;
      if (!text) { skipped++; continue; }
      try {
        await putDraft(d.name, text, {
          reason: 'migrated from localStorage', auto: false
        });
        migrated++;
      } catch {
        skipped++;
      }
    }
    if (migrated > 0) await this.refresh();
    return { migrated, skipped };
  }
};
