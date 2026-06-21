/**
 * Per-editor runtime behaviors that can't be expressed declaratively
 * via setLanguageConfiguration:
 *
 *   - Auto-close the multi-character Jinja delimiters `{{ }}`, `{% %}`,
 *     `{# #}` — the auto-closer inserts two padding spaces and parks
 *     the cursor between them.
 *   - After typing an opening block tag like `{% if x %}`, offer the
 *     matching `{% endif %}` on the next line as a snippet (Tab
 *     accepts).
 *   - Paired backspace: when the cursor sits between an opened/closed
 *     Jinja pair with no body, Backspace deletes the whole pair.
 *
 * Idempotent per editor (guard flag) and self-cleaning on dispose.
 *
 * Works inside both `jinja` and `yaml` models — gates by the model's
 * language id so a non-jinja-aware buffer (python, json) isn't touched.
 */
import { blockTagPairs } from './jinjaLanguage';

const JINJA_LANGS = new Set(['jinja', 'yaml']);

export function enhanceJinjaEditor(editor: any, monaco: any): void {
  if (!editor || (editor as any).__jinjaEnhanced) return;
  (editor as any).__jinjaEnhanced = true;

  let suppressNext = false;

  const typeDisposable = editor.onDidType((ch: string) => {
    if (suppressNext) {
      suppressNext = false;
      return;
    }
    if (ch !== '{' && ch !== '%' && ch !== '#') return;
    const model = editor.getModel();
    if (!model || !JINJA_LANGS.has(model.getLanguageId())) return;

    const position = editor.getPosition();
    const line: string = model.getLineContent(position.lineNumber);
    const col: number = position.column;
    const justTyped = line.substring(col - 3, col - 1);

    let pair: { opener: string; closer: string } | null = null;
    if (justTyped === '{{') pair = { opener: '{{', closer: '}}' };
    else if (justTyped === '{%') pair = { opener: '{%', closer: '%}' };
    else if (justTyped === '{#') pair = { opener: '{#', closer: '#}' };
    if (!pair) return;

    const after = line.substring(col - 1, col - 1 + pair.closer.length);
    if (after === pair.closer) return;

    if (pair.opener !== '{#' && insideComment(model, position)) return;

    const insert = '  ' + pair.closer;
    suppressNext = true;
    editor.executeEdits('jinja-autoclose', [
      {
        range: new monaco.Range(
          position.lineNumber,
          position.column,
          position.lineNumber,
          position.column
        ),
        text: insert,
        forceMoveMarkers: true
      }
    ]);
    editor.setPosition({
      lineNumber: position.lineNumber,
      column: position.column + 1
    });
  });

  const blockCloseDisposable = editor.onDidType((ch: string) => {
    if (ch !== '}') return;
    const model = editor.getModel();
    if (!model || !JINJA_LANGS.has(model.getLanguageId())) return;

    const position = editor.getPosition();
    const line: string = model.getLineContent(position.lineNumber);
    const upToCursor = line.substring(0, position.column - 1);
    if (!upToCursor.endsWith('%}')) return;

    const tagMatch = upToCursor.match(/\{%-?\s*(\w+)\b[^%]*-?%\}\s*$/);
    if (!tagMatch) return;
    const tagName = tagMatch[1];
    const closer = blockTagPairs[tagName];
    if (!closer) return;

    const remaining: string = model.getValueInRange({
      startLineNumber: position.lineNumber,
      startColumn: position.column,
      endLineNumber: model.getLineCount(),
      endColumn: model.getLineMaxColumn(model.getLineCount())
    });
    if (new RegExp('\\{%-?\\s*' + closer + '\\b').test(remaining)) return;

    const contribution = editor.getContribution('snippetController2');
    if (!contribution || typeof contribution.insert !== 'function') return;
    contribution.insert('\n\t$0\n{% ' + closer + ' %}');
  });

  // Padded form (auto-closer inserts two spaces) checked first.
  const autoClosePairs: Array<{
    left: string;
    right: string;
    deleteLeft: number;
    deleteRight: number;
  }> = [
    { left: '{{ ', right: ' }}', deleteLeft: 3, deleteRight: 3 },
    { left: '{% ', right: ' %}', deleteLeft: 3, deleteRight: 3 },
    { left: '{# ', right: ' #}', deleteLeft: 3, deleteRight: 3 },
    { left: '{{', right: '}}', deleteLeft: 2, deleteRight: 2 },
    { left: '{%', right: '%}', deleteLeft: 2, deleteRight: 2 },
    { left: '{#', right: '#}', deleteLeft: 2, deleteRight: 2 }
  ];

  const deleteDisposable = editor.onKeyDown((e: any) => {
    if (e.keyCode !== monaco.KeyCode.Backspace) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const model = editor.getModel();
    if (!model || !JINJA_LANGS.has(model.getLanguageId())) return;
    const sel = editor.getSelection();
    if (!sel.isEmpty()) return;
    const pos = editor.getPosition();
    const line: string = model.getLineContent(pos.lineNumber);
    const col = pos.column;
    const pair = autoClosePairs.find(
      (p) =>
        line.substring(col - 1 - p.left.length, col - 1) === p.left &&
        line.substring(col - 1, col - 1 + p.right.length) === p.right
    );
    if (!pair) return;
    e.preventDefault();
    e.stopPropagation();
    editor.executeEdits('jinja-autodeletepair', [
      {
        range: new monaco.Range(
          pos.lineNumber,
          col - pair.deleteLeft,
          pos.lineNumber,
          col + pair.deleteRight
        ),
        text: '',
        forceMoveMarkers: true
      }
    ]);
  });

  const disposeListener = editor.onDidDispose(() => {
    typeDisposable.dispose();
    blockCloseDisposable.dispose();
    deleteDisposable.dispose();
    disposeListener.dispose();
  });
}

function insideComment(model: any, position: any): boolean {
  const textUntil: string = model.getValueInRange({
    startLineNumber: 1,
    startColumn: 1,
    endLineNumber: position.lineNumber,
    endColumn: position.column
  });
  const lastOpen = textUntil.lastIndexOf('{#');
  if (lastOpen === -1) return false;
  const lastClose = textUntil.lastIndexOf('#}');
  return lastClose < lastOpen;
}
