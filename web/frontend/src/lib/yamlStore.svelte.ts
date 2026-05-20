/**
 * Monaco editor buffer.
 *
 * Holds just the live YAML text. Persisted to localStorage so it
 * survives a refresh while no draft is active. Drafts, revisions, and
 * the "active document" pointer all live on `playbookStore` (the
 * server-backed source of truth) — this store is purely the editor's
 * working buffer.
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
    // QuotaExceeded etc. — fail silently, the in-memory buffer still works.
  }
}

class YamlStore {
  text = $state<string>(lsGetString(LS_TEXT) ?? PLACEHOLDER);

  constructor() {
    if (typeof window !== 'undefined') {
      $effect.root(() => {
        $effect(() => {
          lsSetString(LS_TEXT, this.text);
        });
      });
    }
  }

  /** Replace the buffer wholesale. `reason` is accepted for legacy
   * call-site parity but no longer drives snapshotting — Monaco's own
   * undo stack covers the Cmd-Z case. */
  setText(next: string, _reason?: string): void {
    this.text = next;
  }
}

export const yamlStore = new YamlStore();
