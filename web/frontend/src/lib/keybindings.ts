/**
 * Window-level keydown router. Walks the command registry for the
 * first command whose `match()` returns true, runs it, and stops
 * propagation. Components register their own commands via
 * `commands.register(...)`.
 */
import { commands, isEditableTarget } from './commands.svelte';

export function installKeybindings(): () => void {
  const onKey = (ev: KeyboardEvent) => {
    // Bail on key events from inputs / textareas — let the field
    // handle its own keystrokes. Each command can opt back in via
    // `match()` if it really wants to fire while typing (e.g. Cmd+S
    // to save while in Monaco).
    const editable = isEditableTarget(ev.target);
    for (const cmd of commands.list) {
      if (!cmd.match) continue;
      if (editable && !cmd.runInInputs) continue;
      if (!cmd.match(ev)) continue;
      // Always swallow a matching hotkey, even when the command is
      // disabled — otherwise the browser default takes over (Cmd+Z
      // history nav, Cmd+S "save page", etc.) and surprises the user.
      // Disabled simply means "no-op", not "let the browser have it".
      ev.preventDefault();
      ev.stopPropagation();
      if (cmd.enabled && !cmd.enabled()) return;
      void cmd.run();
      return;
    }
  };
  // Capture phase so we intercept before react-flow's own keydown
  // handler (which moves the focused node on arrow keys). Without
  // capture, arrow-key node navigation translated the node instead of
  // shifting the selection outline.
  window.addEventListener('keydown', onKey, true);
  return () => window.removeEventListener('keydown', onKey, true);
}
