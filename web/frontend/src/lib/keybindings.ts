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
      if (cmd.enabled && !cmd.enabled()) continue;
      // Default: skip when typing in a field. Commands that need to
      // fire there set their `match()` to inspect the target itself.
      if (editable && !cmd.match(ev)) continue;
      if (!cmd.match(ev)) continue;
      ev.preventDefault();
      ev.stopPropagation();
      void cmd.run();
      return;
    }
  };
  window.addEventListener('keydown', onKey);
  return () => window.removeEventListener('keydown', onKey);
}
