/**
 * Editor buffer + saved drafts.
 *
 * Lives outside the Author component so it survives navigation to
 * /run, /browse, /history. Persisted to localStorage so it also
 * survives a refresh / tab close.
 *
 * Three layers:
 *   1. `text`           — the live editor buffer. Auto-saved to LS on
 *                         every change.
 *   2. `lastSnapshot`   — what the buffer was *just before* the last
 *                         destructive action (load example, load draft,
 *                         reset). One slot, overwritten each time;
 *                         enough to undo a misclick.
 *   3. `drafts[]`       — explicitly-named saves. User-managed.
 *
 * Wholesale buffer replacements MUST go through `setText()` so the
 * snapshot fires; raw assignment (`yamlStore.text = …`) skips the
 * safety net.
 */

const PLACEHOLDER = `# Welcome — try one of these to get started:
#   1. Edit this YAML and watch the right-rail Diagnostics update live.
#   2. Ask the chat: "build a hello-world playbook with one set_variable step"
#   3. Click Compile to see structured errors. Push/Run need a live FSR (.env).

collection: Hello World
playbooks:
  - name: Hello
    steps:
      - name: trigger
        type: start
        next: end
      - name: end
        type: end
`;

const LS_TEXT = 'fsrpb.editor.text';
const LS_DRAFTS = 'fsrpb.editor.drafts';
const LS_SNAPSHOT = 'fsrpb.editor.snapshot';
const LS_ACTIVE_DRAFT = 'fsrpb.editor.activeDraftName';

/** One revision of a draft. The latest revision is the draft's
 *  "current" text; older revisions form the history users browse to
 *  see how an agent iterated on the YAML.
 *  - source='agent': written by the chat agent
 *  - source='user': manually saved by the user
 *  - source='replay': hydrated from a saved chat session
 */
export interface DraftRevision {
  text: string;
  savedAt: string; // ISO-8601
  source: 'agent' | 'user' | 'replay';
  message?: string; // user prompt that caused an agent revision; or save reason
  sessionId?: string; // chat session id, when produced by an agent turn
}

export interface Draft {
  name: string;
  /** Latest revision text. Always equals revisions[0].text. Kept on
   *  the Draft so legacy callers don't have to reach into revisions[]. */
  text: string;
  savedAt: string; // ISO-8601 of the latest revision
  /** Newest-first history. Older drafts (pre-history) start with a
   *  single synthesized revision the first time they're touched. */
  revisions?: DraftRevision[];
}

export interface Snapshot {
  text: string;
  reason: string; // "loaded example: foo.yaml", "loaded draft: bar", "reset"
  takenAt: string;
}

function lsGet<T>(key: string, fallback: T): T {
  if (typeof localStorage === 'undefined') return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function lsSet(key: string, value: unknown): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // QuotaExceeded etc. — fail silently, the in-memory state still works.
  }
}

function lsGetString(key: string): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function lsSetString(key: string, value: string): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

class YamlStore {
  text = $state<string>(lsGetString(LS_TEXT) ?? PLACEHOLDER);
  drafts = $state<Draft[]>(lsGet<Draft[]>(LS_DRAFTS, []));
  lastSnapshot = $state<Snapshot | null>(lsGet<Snapshot | null>(LS_SNAPSHOT, null));
  /** Name of the draft the buffer is currently tracking, if any. Set
   *  by `loadDraft` / `loadDraftRevision` / `saveDraft`; cleared on
   *  `reset()` so a fresh canvas doesn't silently overwrite an old
   *  draft. The Save button uses this to update-in-place instead of
   *  prompting for a new name on every click. */
  activeDraftName = $state<string | null>(
    lsGetString(LS_ACTIVE_DRAFT) ?? null,
  );

  constructor() {
    // Persist live edits to LS. $effect.root keeps this alive for the
    // lifetime of the module, which is what we want — the store is a
    // singleton.
    if (typeof window !== 'undefined') {
      $effect.root(() => {
        $effect(() => {
          lsSetString(LS_TEXT, this.text);
        });
        $effect(() => {
          lsSet(LS_DRAFTS, this.drafts);
        });
        $effect(() => {
          lsSet(LS_SNAPSHOT, this.lastSnapshot);
        });
        $effect(() => {
          if (this.activeDraftName) {
            lsSetString(LS_ACTIVE_DRAFT, this.activeDraftName);
          } else {
            try { localStorage.removeItem(LS_ACTIVE_DRAFT); } catch {}
          }
        });
      });
    }
  }

  /** Replace the buffer wholesale, snapshotting the previous content
   *  so the user can undo. Use this for any "load" operation. */
  setText(next: string, reason: string): void {
    if (this.text && this.text !== next) {
      this.lastSnapshot = {
        text: this.text,
        reason,
        takenAt: new Date().toISOString(),
      };
    }
    this.text = next;
  }

  /** Reset to the placeholder welcome YAML, snapshotting current. */
  reset(): void {
    this.setText(PLACEHOLDER, 'reset');
    // A reset is a fresh canvas — don't keep a stale draft tracking
    // pointer that would later cause Save to overwrite an unrelated draft.
    this.activeDraftName = null;
  }

  /** Append a revision to a named draft, creating the draft if it
   *  doesn't exist yet. Most-recently-revised drafts sort to the top.
   *  De-dupes adjacent identical text (so the same YAML stamped
   *  multiple times in a single agent turn doesn't pollute history).
   */
  appendDraftRevision(
    name: string,
    text: string,
    source: DraftRevision['source'],
    options?: { message?: string; sessionId?: string }
  ): Draft {
    const trimmed = name.trim();
    if (!trimmed) throw new Error('draft name is required');
    const now = new Date().toISOString();
    const newRev: DraftRevision = {
      text,
      savedAt: now,
      source,
      ...(options?.message ? { message: options.message } : {}),
      ...(options?.sessionId ? { sessionId: options.sessionId } : {}),
    };
    const existing = this.drafts.find((d) => d.name === trimmed);
    let draft: Draft;
    if (existing) {
      const prevRevs = existing.revisions ?? [
        // Synthesize a baseline for legacy drafts that pre-date the
        // revision history. Without it, the first agent revision shows
        // no prior context to diff against.
        { text: existing.text, savedAt: existing.savedAt, source: 'user' as const },
      ];
      // De-dupe adjacent identical text.
      if (prevRevs[0]?.text === text) {
        return existing;
      }
      draft = {
        name: trimmed,
        text,
        savedAt: now,
        revisions: [newRev, ...prevRevs],
      };
    } else {
      draft = {
        name: trimmed,
        text,
        savedAt: now,
        revisions: [newRev],
      };
    }
    const others = this.drafts.filter((d) => d.name !== trimmed);
    this.drafts = [draft, ...others];
    return draft;
  }

  /** Backward-compat shorthand: a manual user save = one revision tagged 'user'. */
  saveDraft(name: string): Draft {
    const d = this.appendDraftRevision(name, this.text, 'user');
    this.activeDraftName = d.name;
    return d;
  }

  /** Load a named draft's current (latest) revision into the buffer. */
  loadDraft(name: string): void {
    const draft = this.drafts.find((d) => d.name === name);
    if (!draft) throw new Error(`no draft named ${name}`);
    this.setText(draft.text, `loaded draft: ${name}`);
    this.activeDraftName = draft.name;
  }

  /** Load a specific historical revision of a draft into the buffer.
   *  Doesn't mutate the draft — it's pure replay; if the user wants to
   *  branch from there, they save again. */
  loadDraftRevision(name: string, index: number): void {
    const draft = this.drafts.find((d) => d.name === name);
    if (!draft || !draft.revisions || !draft.revisions[index]) {
      throw new Error(`no revision ${index} on draft ${name}`);
    }
    this.setText(
      draft.revisions[index].text,
      `loaded ${name} revision ${index}`,
    );
    this.activeDraftName = draft.name;
  }

  deleteDraft(name: string): void {
    this.drafts = this.drafts.filter((d) => d.name !== name);
    if (this.activeDraftName === name) this.activeDraftName = null;
  }

  /** Restore the auto-snapshot taken before the last destructive
   *  action. The current buffer becomes the new snapshot, so undo
   *  itself is undoable. */
  restoreSnapshot(): void {
    const snap = this.lastSnapshot;
    if (!snap) return;
    const cur = this.text;
    this.text = snap.text;
    this.lastSnapshot = {
      text: cur,
      reason: 'undo',
      takenAt: new Date().toISOString(),
    };
  }

  /** Best-effort: parse the `collection: <name>` line out of YAML to
   *  suggest a default draft name. */
  suggestedName(): string {
    const m = this.text.match(/^\s*collection\s*:\s*(.+?)\s*$/m);
    return m ? m[1].replace(/['"]/g, '').trim() : '';
  }
}

export const yamlStore = new YamlStore();
