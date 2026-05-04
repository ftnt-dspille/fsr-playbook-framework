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
      - id: trigger
        type: start
        next: stop
      - id: stop
        type: stop
`;

const LS_TEXT = 'fsrpb.editor.text';
const LS_DRAFTS = 'fsrpb.editor.drafts';
const LS_SNAPSHOT = 'fsrpb.editor.snapshot';

export interface Draft {
  name: string;
  text: string;
  savedAt: string; // ISO-8601
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
  }

  /** Save the current buffer as a named draft. Replaces if name
   *  already exists. Most-recently-saved drafts sort to the top. */
  saveDraft(name: string): Draft {
    const trimmed = name.trim();
    if (!trimmed) throw new Error('draft name is required');
    const draft: Draft = {
      name: trimmed,
      text: this.text,
      savedAt: new Date().toISOString(),
    };
    const others = this.drafts.filter((d) => d.name !== trimmed);
    this.drafts = [draft, ...others];
    return draft;
  }

  /** Load a named draft into the buffer, snapshotting current. */
  loadDraft(name: string): void {
    const draft = this.drafts.find((d) => d.name === name);
    if (!draft) throw new Error(`no draft named ${name}`);
    this.setText(draft.text, `loaded draft: ${name}`);
  }

  deleteDraft(name: string): void {
    this.drafts = this.drafts.filter((d) => d.name !== name);
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
