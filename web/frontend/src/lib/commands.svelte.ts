/**
 * Central command registry shared by the keyboard-shortcut layer and
 * the Cmd+K command palette.
 *
 * Components register/unregister Command entries on mount; the global
 * keydown handler in `keybindings.ts` walks the registry to find a
 * matching `match(ev)` and runs it, and the CommandPalette component
 * presents the same list as a searchable popup.
 *
 * `match` is a free-form predicate (not a literal key string) so each
 * command owns its own matching logic — that handles modifier
 * variations (Cmd/Ctrl), platform differences, and "only when input
 * focused" gating without growing a parser here.
 */
import type { Snippet } from 'svelte';

export type Command = {
  /** Stable id, used to de-dupe re-registrations across remounts. */
  id: string;
  label: string;
  /** Human-readable shortcut text shown in the palette + help overlay
   *  (e.g. `⌘S`, `Del`, `?`). Pure display — match() owns key logic. */
  hotkey?: string;
  /** Predicate fired against window keydown events. Return true to run
   *  this command. Omit for palette-only commands. */
  match?: (ev: KeyboardEvent) => boolean;
  /** Opt-in to firing even when the user is typing in an input /
   *  textarea / Monaco. Default false — most commands shouldn't eat
   *  keystrokes meant for a field. Use for Esc-style close commands
   *  and Cmd+S-style global saves. */
  runInInputs?: boolean;
  /** Bucket for grouping in the palette + help overlay. */
  group?: 'File' | 'Edit' | 'Navigation' | 'Run' | 'Help';
  /** Disabled commands stay listed but greyed out, so users can see
   *  what's available even when not actionable. */
  enabled?: () => boolean;
  run: () => void | Promise<void>;
};

type State = {
  commands: Command[];
  paletteOpen: boolean;
  helpOpen: boolean;
};

const state: State = $state({
  commands: [],
  paletteOpen: false,
  helpOpen: false,
});

export const commands = {
  get list() { return state.commands; },
  get paletteOpen() { return state.paletteOpen; },
  set paletteOpen(v: boolean) { state.paletteOpen = v; },
  get helpOpen() { return state.helpOpen; },
  set helpOpen(v: boolean) { state.helpOpen = v; },

  /** Add or replace a command by id. Returns a teardown function the
   *  caller should fire on unmount. */
  register(cmd: Command): () => void {
    const idx = state.commands.findIndex((c) => c.id === cmd.id);
    if (idx >= 0) state.commands[idx] = cmd;
    else state.commands = [...state.commands, cmd];
    return () => this.unregister(cmd.id);
  },

  registerMany(cmds: Command[]): () => void {
    const teardowns = cmds.map((c) => this.register(c));
    return () => teardowns.forEach((t) => t());
  },

  unregister(id: string): void {
    state.commands = state.commands.filter((c) => c.id !== id);
  },

  /** Run a command by id; no-op when missing or disabled. Used by the
   *  palette's click-to-run path. */
  async runById(id: string): Promise<void> {
    const cmd = state.commands.find((c) => c.id === id);
    if (!cmd) return;
    if (cmd.enabled && !cmd.enabled()) return;
    await cmd.run();
  },
};

/** Convenience: is the user typing in an input / textarea / contenteditable?
 *  Most shortcuts want to skip in that case so they don't eat keystrokes
 *  meant for a field. Save (Cmd+S) is the usual exception. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  // Monaco renders an offscreen <textarea> that's caught above, but
  // also flags itself with `.monaco-editor` ancestors — defensive guard.
  return !!target.closest('.monaco-editor');
}

/** Format a modifier-aware hotkey for display, picking the platform's
 *  preferred symbol. Pure display — wiring uses `match()`. */
export function fmtHotkey(parts: string[]): string {
  const isMac = typeof navigator !== 'undefined'
    && /Mac|iPhone|iPad/.test(navigator.platform);
  return parts
    .map((p) => p === 'Mod' ? (isMac ? '⌘' : 'Ctrl') : p)
    .join(isMac ? '' : '+');
}

/** Cross-platform modifier check: Cmd on macOS, Ctrl elsewhere. */
export function modPressed(ev: KeyboardEvent): boolean {
  const isMac = typeof navigator !== 'undefined'
    && /Mac|iPhone|iPad/.test(navigator.platform);
  return isMac ? ev.metaKey : ev.ctrlKey;
}

// Snippet is unused for now but re-exported so callers don't have to
// import it from svelte just to use the registry.
export type { Snippet };
