/**
 * Translate raw FSR Jinja render errors into human-readable messages
 * and find the line number to mark. Ported from the widget's
 * translateJinjaError / parseErrorLineNumber / findUnclosedTagLine.
 */

export function translateJinjaError(msg: string): string {
  if (!msg) return msg;
  const lower = msg.toLowerCase();
  if (
    lower.match(
      /list\s+(?:index\s+)?(?:out of range|object\s+)?has\s+no\s+attribute|'list'\s+object\s+has\s+no\s+attribute|list index out of range/
    )
  ) {
    return `vars.input.records may be empty or doesn't have enough items — wrap with {% if vars.input.records %} to guard (original: ${msg})`;
  }
  if (lower.match(/has\s+no\s+attribute/) && !lower.match(/list/)) {
    return `A field was not found — check the variable name and make sure it exists in the input (original: ${msg})`;
  }
  if (lower.match(/no\s+filter\s+named|unknown\s+filter/)) {
    return `Unknown filter name — check spelling or browse the filter library (original: ${msg})`;
  }
  if (lower.match(/expected token|unexpected|end of statement block|end of template/)) {
    return `Syntax error in template — check for unclosed {{ }}, {% %}, or mismatched tags (original: ${msg})`;
  }
  if (lower.match(/division by zero/)) {
    return `Division by zero — the divisor evaluated to 0 (original: ${msg})`;
  }
  if (lower.match(/filter.*requires|takes.*argument|takes no arguments/)) {
    return `A filter was called with the wrong number of arguments — check the filter library for the correct signature (original: ${msg})`;
  }
  if (lower.match(/cannot convert|int\(\)|float\(\)/)) {
    return `Type error — a filter or expression received the wrong data type (original: ${msg})`;
  }
  return msg;
}

/** Pull a 1-based line number out of common Jinja error formats:
 *  "line 3", "line: 3", "(line 3)", "at line 3". Returns null if none. */
export function parseErrorLineNumber(msg: string): number | null {
  if (!msg) return null;
  const m = msg.match(/(?:^|[\s(])line[:\s]+(\d+)/i);
  return m ? parseInt(m[1], 10) : null;
}

/** Scan the template for the last line with an unclosed `{{` or `{%`
 *  — used when the engine error has no explicit line number. */
export function findUnclosedTagLine(templateText: string): number | null {
  if (!templateText) return null;
  const lines = templateText.split('\n');
  let last: number | null = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const openExpr = line.indexOf('{{') !== -1;
    const closeExpr = line.indexOf('}}') !== -1;
    const openBlock = line.indexOf('{%') !== -1;
    const closeBlock = line.indexOf('%}') !== -1;
    if ((openBlock && !closeBlock) || (openExpr && !closeExpr)) last = i + 1;
  }
  return last;
}

export interface JinjaFinding {
  line: number;
  message: string;
  severity?: 'error' | 'warning';
}

/** Static scan for structural problems Jinja itself would only catch
 *  at render time. Ported from the widget's `scanTemplate`. Runs on
 *  every keystroke so the user sees red squiggles for unclosed `{{`,
 *  `{%`, mismatched `{% end* %}`, and unknown filters without having
 *  to hit Render. `knownFilters` is the set of filter names from the
 *  filter library — pass empty / null to skip filter-name checks. */
export function scanTemplate(
  templateText: string,
  knownFilters: Set<string> | null = null
): JinjaFinding[] {
  const findings: JinjaFinding[] = [];
  if (!templateText) return findings;
  const lines = templateText.split('\n');
  // FSR's Jinja only uses inline `{% set name = value %}` — no
  // `{% set %}…{% endset %}` capture form — so `set` is NOT tracked
  // as a block opener and `endset` is NOT a valid closer.
  const openingTags = new Set([
    'if', 'for', 'block', 'macro', 'call', 'filter', 'with'
  ]);
  const closingTagMap: Record<string, string> = {
    endif: 'if',
    endfor: 'for',
    endblock: 'block',
    endmacro: 'macro',
    endcall: 'call',
    endfilter: 'filter',
    endwith: 'with'
  };
  // Walk EVERY `{% … %}` and `{{ … }}` on each line. The widget's
  // original scan only inspected the first pair per line and so the
  // for-loop's inner `{% if %}…{% endif %}` confused the block stack
  // for any outer block. Iterating each tag pair fixes that without
  // changing the rules.
  const blockStack: Array<{ tag: string; line: number }> = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;

    // Block tags `{% … %}`
    let cursor = 0;
    while (cursor < line.length) {
      const open = line.indexOf('{%', cursor);
      if (open === -1) break;
      const close = line.indexOf('%}', open + 2);
      if (close === -1) {
        findings.push({ line: lineNum, message: 'Unclosed block tag — did you mean {% … %}?' });
        break;
      }
      const content = line
        .slice(open + 2, close)
        .replace(/^-/, '')
        .replace(/-$/, '')
        .trim();
      const tagMatch = content.match(/^(\w+)/);
      const tagName = tagMatch ? tagMatch[1] : null;
      if (tagName && openingTags.has(tagName)) {
        blockStack.push({ tag: tagName, line: lineNum });
      } else if (tagName && closingTagMap[tagName]) {
        const expected = closingTagMap[tagName];
        if (blockStack.length === 0 || blockStack[blockStack.length - 1].tag !== expected) {
          findings.push({
            line: lineNum,
            message: `Unexpected {% ${tagName} %} — no matching {% ${expected} %} found`
          });
        } else {
          blockStack.pop();
        }
      }
      // Anything else (`else`, `elif`, `set`, `include`, …) is a
      // continuation or leaf — no stack change.
      cursor = close + 2;
    }

    // Expressions `{{ … }}`
    cursor = 0;
    while (cursor < line.length) {
      const open = line.indexOf('{{', cursor);
      if (open === -1) break;
      const close = line.indexOf('}}', open + 2);
      if (close === -1) {
        findings.push({ line: lineNum, message: 'Unclosed expression — did you mean {{ … }}?' });
        break;
      }
      if (knownFilters && knownFilters.size > 0) {
        const expr = line.slice(open + 2, close);
        const matches = expr.match(/\|\s*(\w+)/g);
        if (matches) {
          for (const fm of matches) {
            const fname = fm.replace(/\|\s*/, '');
            if (!knownFilters.has(fname)) {
              findings.push({
                line: lineNum,
                message: `Unknown filter "${fname}" — check spelling or see the filter library`
              });
              break;
            }
          }
        }
      }
      cursor = close + 2;
    }
  }
  for (const opener of blockStack) {
    findings.push({
      line: opener.line,
      message: `{% ${opener.tag} %} on line ${opener.line} was never closed with {% end${opener.tag} %}`
    });
  }
  return findings;
}

/** Walk a dotted/bracket path against a JS object. Returns
 *  `{ found: true, value }` or `{ found: false }`. Ported verbatim
 *  from the widget's `resolveInputPath`. */
export function resolveInputPath(
  obj: unknown,
  pathStr: string
): { found: true; value: unknown } | { found: false } {
  if (!obj || !pathStr) return { found: false };
  const segments: string[] = [];
  let current = pathStr;
  while (current) {
    const dotIdx = current.indexOf('.');
    const bracketIdx = current.indexOf('[');
    if (dotIdx === -1 && bracketIdx === -1) {
      segments.push(current);
      break;
    }
    if (dotIdx !== -1 && (bracketIdx === -1 || dotIdx < bracketIdx)) {
      segments.push(current.slice(0, dotIdx));
      current = current.slice(dotIdx + 1);
    } else if (bracketIdx !== -1) {
      if (bracketIdx > 0) segments.push(current.slice(0, bracketIdx));
      const closeIdx = current.indexOf(']', bracketIdx);
      if (closeIdx === -1) return { found: false };
      segments.push('[' + current.slice(bracketIdx + 1, closeIdx) + ']');
      current = current.slice(closeIdx + 1);
      if (current.startsWith('.')) current = current.slice(1);
    }
  }
  let val: any = obj;
  for (const seg of segments) {
    if (seg.startsWith('[')) {
      const idx = parseInt(seg.slice(1, -1), 10);
      if (!Array.isArray(val) || idx < 0 || idx >= val.length) return { found: false };
      val = val[idx];
    } else {
      if (val == null || typeof val !== 'object' || !(seg in val)) return { found: false };
      val = val[seg];
    }
  }
  return { found: true, value: val };
}

/** Collect names bound by `{% set/for/with/macro %}` tags. Template-
 *  local names shouldn't get flagged as missing from input. */
export function collectLocalNames(templateText: string): Set<string> {
  const names = new Set<string>();
  if (!templateText) return names;
  const tagRegex = /\{%-?\s*([\s\S]*?)\s*-?%\}/g;
  for (const m of templateText.matchAll(tagRegex)) {
    const body = m[1].trim();
    let sm: RegExpMatchArray | null;
    if ((sm = body.match(/^set\s+([A-Za-z_][\w]*(?:\s*,\s*[A-Za-z_][\w]*)*)\s*=/))) {
      sm[1].split(',').forEach((n) => names.add(n.trim()));
    } else if ((sm = body.match(/^for\s+([A-Za-z_][\w]*(?:\s*,\s*[A-Za-z_][\w]*)*)\s+in\s+/))) {
      sm[1].split(',').forEach((n) => names.add(n.trim()));
    } else if ((sm = body.match(/^with\s+([A-Za-z_][\w]*)\s*=/))) {
      names.add(sm[1]);
    } else if ((sm = body.match(/^macro\s+[A-Za-z_][\w]*\s*\(([^)]*)\)/))) {
      sm[1].split(',').forEach((p) => {
        const name = p.split('=')[0].trim();
        if (name) names.add(name);
      });
    }
  }
  return names;
}

/** Pre-render input-data validation: for every `{{ path | … }}`
 *  expression, strip filters and check the head path resolves in
 *  `inputData`. Locally-bound names (set/for/with/macro) are skipped.
 *  Mirrors the widget's `checkInputPaths`. */
export function checkInputPaths(
  templateText: string,
  inputData: unknown
): JinjaFinding[] {
  const findings: JinjaFinding[] = [];
  if (!templateText || !inputData) return findings;
  const lines = templateText.split('\n');
  const seen = new Set<string>();
  const local = collectLocalNames(templateText);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const m of line.matchAll(/\{\{([^}]*)\}\}/g)) {
      let expr = m[1].trim();
      const pipe = expr.indexOf('|');
      if (pipe !== -1) expr = expr.slice(0, pipe).trim();
      if (
        !expr ||
        expr.startsWith('loop.') ||
        expr.startsWith('range(') ||
        expr.match(/^['"`]/) ||
        expr.match(/^\d+(\.\d+)?$/) ||
        expr.match(/^(true|false|none)$/i) ||
        expr.match(/^(if|for|with|macro|call|set|block|extends|include)\s/i)
      ) continue;
      const root = expr.match(/^([A-Za-z_][\w]*)/);
      if (root && local.has(root[1])) continue;
      if (seen.has(expr)) continue;
      seen.add(expr);
      const res = resolveInputPath(inputData, expr);
      if (!res.found) {
        findings.push({
          line: i + 1,
          message: `"${expr}" was not found in the test input — check the field name`,
          severity: 'warning'
        });
      }
    }
  }
  return findings;
}

/** Apply a list of findings as Monaco markers. Pass [] to clear. */
export function applyJinjaFindings(
  editor: any,
  monaco: any,
  findings: JinjaFinding[]
): void {
  if (!editor || !monaco) return;
  const model = editor.getModel();
  if (!model) return;
  const markers = findings.map((f) => {
    const lineContent: string = model.getLineContent(f.line) || '';
    const startCol = lineContent.search(/\S/) + 1 || 1;
    const endCol = lineContent.length + 1;
    return {
      severity:
        f.severity === 'warning' ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error,
      message: f.message,
      startLineNumber: f.line,
      startColumn: startCol,
      endLineNumber: f.line,
      endColumn: endCol
    };
  });
  monaco.editor.setModelMarkers(model, 'jinja-render', markers);
}

/** Apply (or clear) a red error marker on the template editor at the
 *  given 1-based line. Pass `line = null` to clear. */
export function setJinjaErrorMarker(
  editor: any,
  monaco: any,
  line: number | null,
  message: string
): void {
  if (!editor || !monaco) return;
  const model = editor.getModel();
  if (!model) return;
  if (!line) {
    monaco.editor.setModelMarkers(model, 'jinja-render', []);
    return;
  }
  const lineContent: string = model.getLineContent(line) || '';
  const startCol = lineContent.search(/\S/) + 1 || 1;
  const endCol = lineContent.length + 1;
  monaco.editor.setModelMarkers(model, 'jinja-render', [
    {
      severity: monaco.MarkerSeverity.Error,
      message,
      startLineNumber: line,
      startColumn: startCol,
      endLineNumber: line,
      endColumn: endCol
    }
  ]);
}
