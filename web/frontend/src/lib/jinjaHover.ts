/**
 * Monaco hover provider for Jinja `{{ vars.steps.X.foo }}` paths.
 *
 * Complements yamlHover.ts (which surfaces step-args docs on
 * `arguments:`). This provider walks backward/forward from the cursor
 * to find the enclosing Jinja expression, resolves the typed Shape via
 * jinjaPathCompletions.resolveJinjaPathType, and shows the type as a
 * markdown popup.
 *
 * Only handles `vars.steps.*` for now — `vars.input.records[0].*`
 * could be added once a module-aware field type catalog is wired in.
 */
import { resolveJinjaPathType, shapeLabel } from './jinjaPathCompletions';
import { extractTriggerModule } from './triggerModuleFields.svelte';
import type { Shape } from './shapeStubs';

/** Render the body of the hover popup: the type label, plus — when
 *  the shape is an object — a fenced list of the keys at this level
 *  (with their types). Lists show the element type; scalars/none/
 *  unknown render only the type label. */
function renderBody(shape: Shape): string {
  const label = shapeLabel(shape);
  if (shape.kind === 'object') {
    const rows = Object.entries(shape.keys ?? {})
      .slice(0, 24) // cap to keep the popup scannable on wide shapes
      .map(([k, v]) => `- \`${k}\` — _${shapeLabel(v)}_`)
      .join('\n');
    return rows
      ? `_type:_ \`${label}\`\n\n**keys:**\n${rows}`
      : `_type:_ \`${label}\``;
  }
  if (shape.kind === 'list' && shape.item.kind === 'object') {
    const rows = Object.entries(shape.item.keys ?? {})
      .slice(0, 24)
      .map(([k, v]) => `- \`${k}\` — _${shapeLabel(v)}_`)
      .join('\n');
    return rows
      ? `_type:_ \`${label}\`\n\n**item keys:**\n${rows}`
      : `_type:_ \`${label}\``;
  }
  return `_type:_ \`${label}\``;
}

/** From a single line of text + cursor column, extract the full
 *  dotted-bracket path under the cursor IF it sits inside a `{{ ... }}`
 *  expression. Returns null otherwise. */
export function extractPathAtCursor(
  line: string,
  column: number
): string | null {
  // column is 1-based per Monaco; convert to a 0-based index.
  const i = column - 1;
  const lastOpen = line.lastIndexOf('{{', i);
  if (lastOpen === -1) return null;
  const nextClose = line.indexOf('}}', i);
  // The cursor must be inside an unclosed pair OR before the closing braces.
  // If there's a `}}` between `{{` and the cursor, we're outside the expr.
  const closeBeforeCursor = line.indexOf('}}', lastOpen);
  if (closeBeforeCursor !== -1 && closeBeforeCursor < i) return null;
  void nextClose;
  // Find the contiguous path token under the cursor. Allowed chars:
  // identifier chars, dots, brackets, quoted strings inside brackets.
  // We grow leftward from the cursor through valid path chars, then
  // rightward.
  const pathChar = (ch: string) => /[A-Za-z0-9_.\[\]'"]/.test(ch);
  let lo = i;
  while (lo > 0 && pathChar(line[lo - 1])) lo--;
  let hi = i;
  while (hi < line.length && pathChar(line[hi])) hi++;
  const token = line.slice(lo, hi);
  if (!token || !token.startsWith('vars.')) return null;
  return token;
}

/** Recognize `vars.input.records[N].<field>` and return a markdown
 *  body describing it as a record field on the trigger module (when
 *  the YAML has one). Returns null when the path doesn't match. */
function renderInputRecordHover(
  path: string,
  yamlText: string
): string | null {
  const m = path.match(/^vars\.input\.records\[\d+\](?:\.([A-Za-z_][\w]*)|\['([^']+)'\])?$/);
  if (!m) return null;
  const field = m[1] ?? m[2];
  const mod = extractTriggerModule(yamlText);
  const moduleLabel = mod ? `module \`${mod}\`` : 'trigger record';
  if (!field) return `_type:_ \`${moduleLabel}\``;
  return `_type:_ record field on ${moduleLabel}\n\n\`${field}\``;
}

export function registerJinjaHover(monaco: any): { dispose: () => void } {
  return monaco.languages.registerHoverProvider('yaml', {
    provideHover(model: any, position: any) {
      const line: string = model.getLineContent(position.lineNumber);
      const path = extractPathAtCursor(line, position.column);
      if (!path) return null;
      // vars.input.records — handled separately (no Shape in the store).
      if (path.startsWith('vars.input.records')) {
        const yamlText = model.getValue?.() ?? '';
        const body = renderInputRecordHover(path, yamlText);
        if (!body) return null;
        return { contents: [{ value: `**${path}**\n\n${body}`, isTrusted: true }] };
      }
      const shape = resolveJinjaPathType(path);
      if (!shape) return null;
      const md = `**${path}**\n\n${renderBody(shape)}`;
      return { contents: [{ value: md, isTrusted: true }] };
    }
  });
}
