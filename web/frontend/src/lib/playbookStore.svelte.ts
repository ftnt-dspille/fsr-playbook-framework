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
  SaveError,
  ConflictError,
  type ConflictPayload,
  type PlaybookKind,
  type PlaybookListItem,
  type DraftRevision
} from './api';
import { visualStore } from './visualEditStore.svelte';
import { playbookActions } from './playbookActions.svelte';

type ActiveDoc = {
  kind: PlaybookKind;
  name: string;
  /** YAML on disk / latest saved revision. The source of truth for
   * "what's been persisted" — `dirty` derives from comparing against
   * this snapshot. */
  savedYaml: string;
  /** Live editor buffer. Both modes read/write this. */
  yaml: string;
  /** Server's head revision id at the time of last successful load /
   *  save. Sent as `If-Match` on subsequent PUTs so the server can
   *  reject a save that would overwrite a peer tab's edit. `null`
   *  for examples (no draft head) and freshly-cloned drafts whose
   *  initial revision the client hasn't roundtripped yet. */
  revisionId: number | null;
};

/** Live state of the save mutation. Drives the header pill. */
export type SaveState =
  | 'idle'              // clean buffer; nothing to do
  | 'pending'           // debounce timer armed, waiting to fire
  | 'saving'            // PUT in flight (first attempt)
  | 'retrying'          // last attempt failed transient; backing off
  | 'error'             // permanent failure / retries exhausted; awaits user
  | 'conflict'          // peer tab raced us; server has a newer head
  | 'saved-just-now';   // fades back to 'idle' after a short delay

type State = {
  active: ActiveDoc | null;
  drafts: PlaybookListItem[];
  examples: PlaybookListItem[];
  /** Last-known revisions for the active draft, newest first. Empty
   * when active is an example or no draft loaded yet. */
  revisions: DraftRevision[];
  loading: boolean;
  saveState: SaveState;
  /** Last save error message (for the 'error' state). Null otherwise. */
  lastSaveError: string | null;
  /** Server state from the last 409 response. Drives the conflict
   *  resolution modal. Null when not in 'conflict'. */
  conflict: ConflictPayload | null;
  /** Epoch ms of the last successful save. Drives "Saved Xs ago". */
  lastSavedAt: number | null;
  /** Mirrors `saveState === 'saving' || 'retrying'` for callers that
   *  just need a boolean (existing UI / tests). */
  saving: boolean;
  /** @deprecated use `lastSaveError`. Kept for transitional callers. */
  error: string | null;
};

const state = $state<State>({
  active: null,
  drafts: [],
  examples: [],
  revisions: [],
  loading: false,
  saveState: 'idle',
  lastSaveError: null,
  conflict: null,
  lastSavedAt: null,
  saving: false,
  error: null
});

// --- Save mutation machine (module-scoped because it's mechanical
// timing state — not part of the reactive surface). ---
const SAVE_DEBOUNCE_MS = 5000;
const SAVE_MAX_RETRIES = 5;
const SAVED_FADE_MS = 3000;

let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let fadeTimer: ReturnType<typeof setTimeout> | null = null;
let inFlight = false;
let retryAttempt = 0;
/** Options the current run started with — reused for retry / queued
 *  re-runs so the same getLatestYaml / reason / auto flag stick. */
let currentOpts: SaveOpts = {};
let onlineListenerAttached = false;

type SaveOpts = { reason?: string; auto?: boolean; getLatestYaml?: () => Promise<string> };

function setSaveState(next: SaveState) {
  state.saveState = next;
  state.saving = next === 'saving' || next === 'retrying';
}

function clearTimer(t: ReturnType<typeof setTimeout> | null) {
  if (t) clearTimeout(t);
}

function scheduleFadeToIdle() {
  clearTimer(fadeTimer);
  fadeTimer = setTimeout(() => {
    if (state.saveState === 'saved-just-now') setSaveState('idle');
  }, SAVED_FADE_MS);
}

/** Single-flight save core. Manages retries; on success, re-runs itself
 *  if the buffer drifted during the await so no edit is ever lost. */
async function runSave(opts: SaveOpts): Promise<{ ok: boolean; message?: string }> {
  if (inFlight) {
    // Edits during in-flight: just leave the buffer dirty. The current
    // run's success path checks `yaml !== savedYaml` and recurses.
    return { ok: false, message: 'save already in flight' };
  }
  if (!state.active) return { ok: false, message: 'no playbook loaded' };
  if (state.active.kind === 'example') {
    return { ok: false, message: 'examples are read-only — clone to a draft first' };
  }

  // Let the caller (autosave from the page) flush a peer surface
  // (e.g. visual canvas) so we save the freshest YAML rather than the
  // pre-flush buffer.
  if (opts.getLatestYaml) {
    try {
      const latest = await opts.getLatestYaml();
      if (typeof latest === 'string' && latest !== state.active.yaml) {
        state.active.yaml = latest;
      }
    } catch { /* fall back to current buffer */ }
  }

  if (state.active.yaml === state.active.savedYaml) {
    setSaveState('idle');
    return { ok: true, message: 'no changes' };
  }

  inFlight = true;
  currentOpts = opts;
  setSaveState(retryAttempt > 0 ? 'retrying' : 'saving');
  const name = state.active.name;
  const snapshotYaml = state.active.yaml;

  // Send the current revisionId so the server can detect a peer-tab
  // race. Skipped when null (first save after create, or an explicit
  // Overwrite resolution that cleared it).
  const ifMatch = state.active.revisionId;
  try {
    const resp = await putDraft(name, snapshotYaml, {
      reason: opts.reason,
      auto: opts.auto,
      ifMatch: typeof ifMatch === 'number' ? ifMatch : null,
    });
    if (state.active && state.active.name === name) {
      state.active.savedYaml = snapshotYaml;
      state.active.revisionId = resp.revision_id;
    }
    state.lastSaveError = null;
    state.error = null;
    state.conflict = null;
    state.lastSavedAt = Date.now();
    retryAttempt = 0;
    setSaveState('saved-just-now');
    scheduleFadeToIdle();
    listDraftRevisions(name)
      .then((rl) => { if (state.active?.name === name) state.revisions = rl.revisions; })
      .catch(() => {});
    void playbookStore.refresh();
    inFlight = false;
    if (state.active && state.active.yaml !== state.active.savedYaml) {
      void runSave(opts);
    }
    return { ok: true };
  } catch (e) {
    inFlight = false;

    // 409: peer tab beat us. Park the buffer + server state in
    // `state.conflict` for the resolution UI; don't retry — the user
    // must choose Overwrite vs Reload.
    if (e instanceof ConflictError) {
      state.conflict = e.payload;
      state.lastSaveError = e.message;
      state.error = state.lastSaveError;
      retryAttempt = 0;
      setSaveState('conflict');
      return { ok: false, message: e.message };
    }

    const err = e as Error & { transient?: boolean };
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
    const transient = (err instanceof SaveError && err.transient) || offline;
    state.lastSaveError = err.message ?? 'save failed';
    state.error = state.lastSaveError;

    if (transient && retryAttempt < SAVE_MAX_RETRIES) {
      retryAttempt++;
      setSaveState('retrying');
      const delay = Math.min(30_000, 1000 * 2 ** (retryAttempt - 1));
      clearTimer(retryTimer);
      retryTimer = setTimeout(() => { void runSave(currentOpts); }, delay);
      return { ok: false, message: state.lastSaveError ?? undefined };
    }

    retryAttempt = 0;
    setSaveState('error');
    return { ok: false, message: state.lastSaveError ?? undefined };
  }
}

/** Attach the navigator online listener once. When the browser comes
 *  back online while we're in 'error', kick a retry automatically. */
function ensureOnlineListener() {
  if (onlineListenerAttached) return;
  if (typeof window === 'undefined') return;
  onlineListenerAttached = true;
  window.addEventListener('online', () => {
    if (state.saveState === 'error' && state.active && state.active.yaml !== state.active.savedYaml) {
      playbookStore.retrySave();
    }
  });
}

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
  /** The single authoritative read of the active YAML buffer. Returns
   *  `''` when no document is loaded so callers don't need to guard
   *  `state.active` themselves. */
  get currentYaml() { return state.active?.yaml ?? ''; },
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
        yaml: fetched.yaml,
        revisionId: kind === 'draft' ? (fetched as { revision_id?: number }).revision_id ?? null : null
      };
      state.revisions = [];
      // A previous draft's error / conflict must not bleed into the
      // newly-opened doc's pill.
      state.lastSaveError = null;
      state.error = null;
      state.conflict = null;
      retryAttempt = 0;
      clearTimer(retryTimer);
      setSaveState('idle');
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
   * mutation. Does NOT persist. `source` is a free-form tag (e.g.
   * "monaco", "visual-render", "revision-restore") that exists for
   * future telemetry / debugging — it does not affect behavior. */
  replaceYaml(next: string, _source?: string): void {
    if (!state.active) return;
    if (state.active.yaml === next) return;
    state.active.yaml = next;
  },

  /** Persist the live buffer as a new revision on the active draft.
   *  Flushes any debounce timer + waits for the save to settle (or
   *  enter 'error'), then returns. Goes through the same retry-aware
   *  state machine the autosave uses.
   *
   *  Used by the manual Save button — autosave should call
   *  `requestSave` instead so rapid edits coalesce. */
  async save(opts: { reason?: string; auto?: boolean; getLatestYaml?: () => Promise<string> } = {}): Promise<{ ok: boolean; message?: string }> {
    clearTimer(debounceTimer);
    debounceTimer = null;
    return runSave(opts);
  },

  /** Schedule a save: arms (or re-arms) the debounce timer so a flurry
   *  of edits coalesces into one PUT. Cheap to call from every
   *  keystroke / canvas mutation. */
  requestSave(opts: SaveOpts = {}): void {
    ensureOnlineListener();
    if (!state.active || state.active.kind === 'example') return;
    currentOpts = opts;
    setSaveState('pending');
    clearTimer(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      void runSave(opts);
    }, SAVE_DEBOUNCE_MS);
  },

  /** Resolve the 'conflict' state. Two modes:
   *   - 'overwrite': drop the If-Match and PUT again, blowing away
   *     the peer's edits. Use when the current buffer is what the user
   *     intends to ship.
   *   - 'reload': discard the local buffer and adopt the server's
   *     YAML. Use when the peer's edit is the one to keep.
   *
   *  Either way clears the conflict state. */
  async resolveConflict(mode: 'overwrite' | 'reload'): Promise<{ ok: boolean; message?: string }> {
    if (state.saveState !== 'conflict' || !state.conflict || !state.active) {
      return { ok: false, message: 'no active conflict' };
    }
    if (mode === 'reload') {
      const server = state.conflict;
      state.active.yaml = server.server_yaml;
      state.active.savedYaml = server.server_yaml;
      state.active.revisionId = server.server_revision_id;
      state.conflict = null;
      state.lastSaveError = null;
      state.error = null;
      setSaveState('idle');
      // Refresh revisions so the Revisions drawer reflects the peer's save.
      listDraftRevisions(state.active.name)
        .then((rl) => { if (state.active) state.revisions = rl.revisions; })
        .catch(() => {});
      return { ok: true };
    }
    // overwrite: adopt the server's head id so our next PUT's If-Match
    // matches; then run the save unconditionally.
    state.active.revisionId = state.conflict.server_revision_id;
    state.conflict = null;
    state.lastSaveError = null;
    state.error = null;
    setSaveState('idle');
    return runSave(currentOpts);
  },

  /** User clicked "Retry" after a failure. Clear the error and kick a
   *  fresh save immediately. */
  retrySave(): { ok: boolean } {
    if (state.saveState !== 'error' && state.saveState !== 'retrying') {
      return { ok: false };
    }
    clearTimer(retryTimer);
    retryAttempt = 0;
    state.lastSaveError = null;
    state.error = null;
    void runSave(currentOpts);
    return { ok: true };
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

  /** Register the page-level reactivity that turns user edits into
   *  persisted state: a debounced autosave + an active-doc-loaded
   *  hook for the page to wire downstream stores (e.g. visualStore).
   *
   *  Must be called from a Svelte component `<script>` so the inner
   *  `$effect` calls attach to that component's lifecycle.
   *
   *  @param opts.getLatestYaml Returns the freshest YAML across all
   *    editor surfaces — the page passes a mode-aware getter that
   *    renders the Design canvas when active. Defaults to
   *    `currentYaml`.
   *  @param opts.onActiveLoaded Fires when the active doc identity
   *    changes, so callers can mirror the buffer into peer stores. */
  bindAutosave(opts: {
    getLatestYaml?: () => Promise<string>;
    onActiveLoaded?: (yaml: string) => void;
  } = {}): void {
    // Active-doc-identity tracker: fire onActiveLoaded only when
    // `kind:name` changes, not on every keystroke.
    let lastSyncedKey: string | null = null;
    $effect(() => {
      const a = state.active;
      const key = a ? `${a.kind}:${a.name}` : null;
      if (key === lastSyncedKey) return;
      lastSyncedKey = key;
      if (a) opts.onActiveLoaded?.(a.yaml);
    });

    // Autosave: any source of dirtiness (CLI keystroke or visual edit)
    // arms the save mutation. The mutation owns debounce timing,
    // single-flight, retries, and error state — this effect just says
    // "there's work to do".
    $effect(() => {
      const dirty = visualStore.state.dirty || this.dirty;
      const active = state.active;
      if (!dirty || !active || active.kind === 'example') return;
      this.requestSave({
        reason: 'autosave',
        auto: true,
        getLatestYaml: opts.getLatestYaml
      });
    });

    // After each successful save, fire analyze + verify so badges /
    // status dot reflect the freshly-persisted buffer, and clear the
    // visualStore dirty flag so a quick second edit can re-arm.
    let lastSavedAtSeen: number | null = null;
    $effect(() => {
      const t = state.lastSavedAt;
      if (t === null || t === lastSavedAtSeen) return;
      lastSavedAtSeen = t;
      // markSaved both clears the dirty flag AND snapshots the current
      // graph as the "saved" baseline, so a subsequent undo back to
      // this state correctly resolves dirty=false.
      visualStore.markSaved();
      if (!playbookActions.analyzeBusy) void playbookActions.analyze();
      if (!playbookActions.verifyBusy) void playbookActions.runVerify();
    });
  },

  /** Clear the active doc (used by replay flows / explicit "new").
   *  Also cancels any in-flight or scheduled save — the buffer is
   *  gone, so there's nothing left to persist. */
  reset(): void {
    clearTimer(debounceTimer); debounceTimer = null;
    clearTimer(retryTimer);    retryTimer = null;
    clearTimer(fadeTimer);     fadeTimer = null;
    inFlight = false;
    retryAttempt = 0;
    currentOpts = {};
    state.active = null;
    state.revisions = [];
    state.error = null;
    state.lastSaveError = null;
    state.conflict = null;
    state.lastSavedAt = null;
    setSaveState('idle');
  },

};
