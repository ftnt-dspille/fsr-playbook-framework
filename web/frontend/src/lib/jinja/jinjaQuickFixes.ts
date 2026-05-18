/**
 * Monaco quick-fix (code-action) provider for Jinja markers.
 *
 * Each finding in jinjaErrors carries a stable phrase that we match
 * here to offer a one-click correction:
 *
 *   - "Unclosed block tag …"            → append ` %}` to the line
 *   - "Unclosed expression …"           → append ` }}` to the line
 *   - "{% X %} on line N was never …"   → append `{% endX %}` after the
 *                                         template
 *   - "Unexpected {% endX %} — no …"    → delete the orphan tag
 *   - "Unknown filter \"X\" …"          → replace with closest known
 *                                         filter name (Levenshtein)
 *
 * "X was not found in the test input" warnings have no quick fix —
 * the fix lives in the input JSON, not the template.
 */
import { filterSignatures } from './jinjaFilters';

const FIX_KIND = 'quickfix';

export function registerJinjaQuickFixes(monaco: any): { dispose: () => void } {
  const provider = {
    provideCodeActions(model: any, _range: any, context: any) {
      const actions: any[] = [];
      const filterNames = Object.keys(filterSignatures);
      for (const m of context.markers as any[]) {
        const text: string = m.message || '';

        // Unclosed `{%` — append ` %}` (or `%}` if line already ends
        // in whitespace) at end of the marked line.
        if (text.startsWith('Unclosed block tag')) {
          actions.push(closerAction(monaco, model, m, '%}', "Close with ' %}'"));
          continue;
        }

        // Unclosed `{{` — append ` }}` (same trailing-space rule).
        if (text.startsWith('Unclosed expression')) {
          actions.push(closerAction(monaco, model, m, '}}', "Close with ' }}'"));
          continue;
        }

        // Unclosed block opener — append `{% endX %}` after end of file.
        const noClose = text.match(/^\{% (\w+) %\} on line \d+ was never closed with \{% (end\w+) %\}/);
        if (noClose) {
          const closer = noClose[2];
          actions.push(appendEndTagAction(monaco, model, m, closer));
          continue;
        }

        // Orphan `{% endX %}` — delete it.
        const orphan = text.match(/^Unexpected \{% (end\w+) %\}/);
        if (orphan) {
          actions.push(deleteOrphanAction(monaco, model, m));
          continue;
        }

        // Unknown filter — suggest the nearest known name.
        const filt = text.match(/^Unknown filter "(\w+)"/);
        if (filt) {
          const wrong = filt[1];
          const guess = closestName(wrong, filterNames);
          if (guess && guess !== wrong) {
            actions.push(replaceWordAction(monaco, model, m, wrong, guess));
          }
        }
      }
      return {
        actions,
        dispose() {}
      };
    }
  };

  const disposers: Array<{ dispose: () => void }> = [
    monaco.languages.registerCodeActionProvider('jinja', provider),
    monaco.languages.registerCodeActionProvider('yaml', provider)
  ];
  return {
    dispose() {
      for (const d of disposers) d.dispose();
    }
  };
}

// ── action builders ───────────────────────────────────────────────────

function closerAction(monaco: any, model: any, marker: any, suffix: string, title: string) {
  // Append at the last non-whitespace position so a line that
  // already ends in spaces (e.g. `{% endfor   `) doesn't end up with
  // doubled whitespace (`{% endfor   %}`). Trim trailing whitespace
  // and insert the closer right after the last visible character,
  // with exactly one separating space.
  const lineNum = marker.startLineNumber;
  const line: string = model.getLineContent(lineNum);
  const trimmed = line.replace(/\s+$/, '');
  const trimEndCol = trimmed.length + 1; // 1-based: column AFTER the last non-ws char
  const lineMaxCol = model.getLineMaxColumn(lineNum);
  return {
    title,
    kind: FIX_KIND,
    diagnostics: [marker],
    isPreferred: true,
    edit: {
      edits: [
        {
          resource: model.uri,
          versionId: model.getVersionId(),
          textEdit: {
            // Replace the trailing-whitespace span (possibly empty)
            // with ` ` + closer, guaranteeing single-space padding.
            range: new monaco.Range(lineNum, trimEndCol, lineNum, lineMaxCol),
            text: ' ' + suffix
          }
        }
      ]
    }
  };
}

function appendEndTagAction(monaco: any, model: any, marker: any, closer: string) {
  const lastLine = model.getLineCount();
  const lastCol = model.getLineMaxColumn(lastLine);
  return {
    title: `Append {% ${closer} %} at end of template`,
    kind: FIX_KIND,
    diagnostics: [marker],
    isPreferred: true,
    edit: {
      edits: [
        {
          resource: model.uri,
          versionId: model.getVersionId(),
          textEdit: {
            range: new monaco.Range(lastLine, lastCol, lastLine, lastCol),
            text: `\n{% ${closer} %}`
          }
        }
      ]
    }
  };
}

function deleteOrphanAction(monaco: any, model: any, marker: any) {
  // Delete the whole offending line — the orphan `{% endX %}` likely
  // sits on its own line; if it doesn't, this is still the simplest
  // reasonable fix and lands in the undo stack.
  const ln = marker.startLineNumber;
  const startCol = 1;
  const endCol = model.getLineMaxColumn(ln);
  const needsNextLineCut = ln < model.getLineCount();
  return {
    title: 'Delete the orphan tag',
    kind: FIX_KIND,
    diagnostics: [marker],
    edit: {
      edits: [
        {
          resource: model.uri,
          versionId: model.getVersionId(),
          textEdit: {
            range: new monaco.Range(
              ln,
              startCol,
              needsNextLineCut ? ln + 1 : ln,
              needsNextLineCut ? 1 : endCol
            ),
            text: ''
          }
        }
      ]
    }
  };
}

function replaceWordAction(
  monaco: any,
  model: any,
  marker: any,
  wrong: string,
  right: string
) {
  // Find the wrong word on the marker's line.
  const line: string = model.getLineContent(marker.startLineNumber);
  const idx = line.indexOf(wrong);
  if (idx < 0) return null;
  return {
    title: `Replace with '${right}'`,
    kind: FIX_KIND,
    diagnostics: [marker],
    isPreferred: true,
    edit: {
      edits: [
        {
          resource: model.uri,
          versionId: model.getVersionId(),
          textEdit: {
            range: new monaco.Range(
              marker.startLineNumber,
              idx + 1,
              marker.startLineNumber,
              idx + 1 + wrong.length
            ),
            text: right
          }
        }
      ]
    }
  };
}

// ── Levenshtein for filter-name suggestion ────────────────────────────

function closestName(input: string, candidates: string[]): string | null {
  let best: string | null = null;
  let bestD = Infinity;
  const lower = input.toLowerCase();
  for (const c of candidates) {
    const d = levenshtein(lower, c.toLowerCase());
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  // Only suggest when "close enough" — protects against random guesses.
  return best && bestD <= Math.max(2, Math.floor(input.length / 3)) ? best : null;
}

function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const prev = new Array(b.length + 1);
  const curr = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
  }
  return prev[b.length];
}
