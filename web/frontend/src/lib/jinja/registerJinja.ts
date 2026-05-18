/**
 * Idempotent registration of the Jinja language for Monaco.
 *
 * Registers (on language id "jinja"):
 *   - tokenizer + language configuration
 *   - dark (jinjaTheme) + light (jinjaThemeLight) themes
 *   - filter completion (triggered after `|`)
 *   - filter hover + signature-help
 *   - snippet completion
 *   - keyword + `vars.*` / `loop.*` variable completion
 *
 * AND (on language id "yaml") — so the same filter / snippet / keyword
 * completions and signature help fire inside `{{ … }}` / `{% … %}`
 * regions of YAML files. Member-access completions for typed paths
 * (`vars.steps.X.…`) are handled separately by jinjaPathCompletions.
 *
 * Tracks disposables on the monaco namespace so a re-run replaces the
 * previous registrations rather than stacking them.
 */
import {
  languageDefinition,
  type JinjaLanguageDefinition
} from './jinjaLanguage';
import { filterSignatures, type FilterSignature } from './jinjaFilters';
import { snippets, type JinjaSnippet } from './jinjaSnippets';
import { registerJinjaQuickFixes } from './jinjaQuickFixes';

// Track per-monaco-namespace registrations in a module-local WeakMap.
// Attaching directly to the monaco import would fail with "Cannot
// assign to property of [object Module]" because the ES module
// namespace object is frozen.
const registered = new WeakSet<object>();
const registrationsByMonaco = new WeakMap<object, Array<{ dispose: () => void }>>();

/** Shared parsed-input context for `.` / `[` member completions —
 *  ported from the widget's `currentInputContext`. The Jinja test
 *  modal's Input pane pushes its parsed JSON in here; the member
 *  provider reads it when the user types `vars.input.records[0].`. */
let currentInputContext: Record<string, unknown> | null = null;
export function setInputContext(ctx: unknown): void {
  currentInputContext =
    ctx && typeof ctx === 'object' && !Array.isArray(ctx)
      ? (ctx as Record<string, unknown>)
      : null;
}

export function registerJinja(monaco: any): void {
  if (!monaco || registered.has(monaco)) return;
  registered.add(monaco);

  teardownPrevious(monaco);
  const disposables: Array<{ dispose: () => void }> = [];
  registrationsByMonaco.set(monaco, disposables);
  const track = (d: any) => {
    if (d && typeof d.dispose === 'function') disposables.push(d);
    return d;
  };

  // ── language id "jinja" ────────────────────────────────────────────
  monaco.languages.register({ id: languageDefinition.id });
  track(
    monaco.languages.setMonarchTokensProvider(languageDefinition.id, {
      tokenizer: languageDefinition.tokenizer
    })
  );
  if (languageDefinition.configuration) {
    track(
      monaco.languages.setLanguageConfiguration(
        languageDefinition.id,
        languageDefinition.configuration
      )
    );
  }
  monaco.editor.defineTheme(languageDefinition.theme.name, {
    base: languageDefinition.theme.base,
    inherit: languageDefinition.theme.inherit,
    rules: languageDefinition.theme.rules,
    colors: languageDefinition.theme.colors
  });
  monaco.editor.defineTheme(languageDefinition.themeLight.name, {
    base: languageDefinition.themeLight.base,
    inherit: languageDefinition.themeLight.inherit,
    rules: languageDefinition.themeLight.rules,
    colors: languageDefinition.themeLight.colors
  });

  // Editors in this app are created with `theme: 'vs-dark'` (built-in)
  // — so define overrides for `vs-dark` and `vs` that inherit from the
  // built-in palette and layer the jinja token rules on top. This
  // colors `{{ … }}` content inside both the standalone jinja language
  // AND the YAML buffer (which emits the same jinja token names via
  // yamlJinjaTokens).
  monaco.editor.defineTheme('vs-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: languageDefinition.theme.rules,
    colors: {}
  });
  monaco.editor.defineTheme('vs', {
    base: 'vs',
    inherit: true,
    rules: languageDefinition.themeLight.rules,
    colors: {}
  });
  // `defineTheme` updates the theme registry but Monaco doesn't
  // automatically re-tokenize editors that were created with that
  // theme name — colors are baked at create time. Re-set the active
  // theme to force a redraw with the new rules. We try to keep
  // whatever theme the host is currently using; falling back to
  // 'vs-dark' covers the no-existing-editors case.
  try {
    const current = (monaco.editor as any)._themeService?.getColorTheme?.()?.themeName;
    monaco.editor.setTheme(current || 'vs-dark');
  } catch {
    monaco.editor.setTheme('vs-dark');
  }

  // jinja-language providers
  track(registerSnippetProvider(monaco, 'jinja', snippets));
  track(registerFilterCompletionProvider(monaco, 'jinja', filterSignatures));
  track(registerVariableCompletionProvider(monaco, 'jinja'));
  track(registerFilterHoverProvider(monaco, 'jinja', filterSignatures));
  track(registerSignatureHelpProvider(monaco, 'jinja', filterSignatures));

  // yaml-embedded providers (filter completion + hover + signature help
  // inside `{{ … }}` / `{% … %}` only — guards are inside the providers).
  track(registerFilterCompletionProvider(monaco, 'yaml', filterSignatures));
  track(registerFilterHoverProvider(monaco, 'yaml', filterSignatures));
  track(registerSignatureHelpProvider(monaco, 'yaml', filterSignatures));
  track(registerVariableCompletionProvider(monaco, 'yaml'));
  track(registerJinjaSnippetProviderInYaml(monaco, snippets));

  // Member-access (`.` / `[`) completions backed by setInputContext —
  // walks the parsed input JSON to show available keys/indices.
  // Registered on BOTH jinja and yaml so the modal's template editor
  // (jinja) AND the main YAML editor get input-aware suggestions.
  track(registerMemberCompletionProvider(monaco, 'jinja'));
  track(registerMemberCompletionProvider(monaco, 'yaml'));

  // Quick fixes (Monaco light-bulb) for our jinja markers — appends
  // closers, suggests nearest filter name, deletes orphan end tags.
  track(registerJinjaQuickFixes(monaco));
}

function teardownPrevious(monaco: any) {
  const prev = registrationsByMonaco.get(monaco);
  if (!prev) return;
  for (const d of prev) {
    try {
      d.dispose();
    } catch {
      // best-effort
    }
  }
  registrationsByMonaco.set(monaco, []);
}

// ── helpers ────────────────────────────────────────────────────────────

function rangeAt(position: any, word: any) {
  return {
    startLineNumber: position.lineNumber,
    endLineNumber: position.lineNumber,
    startColumn: word.startColumn,
    endColumn: word.endColumn
  };
}

function hasOpenDelimiter(text: string, open: string, close: string): boolean {
  const lastOpen = text.lastIndexOf(open);
  if (lastOpen === -1) return false;
  const lastClose = text.lastIndexOf(close);
  return lastClose < lastOpen;
}

function insideJinja(model: any, position: any): { tag: boolean; expr: boolean } {
  const fullUpTo: string = model.getValueInRange({
    startLineNumber: 1,
    startColumn: 1,
    endLineNumber: position.lineNumber,
    endColumn: position.column
  });
  return {
    tag: hasOpenDelimiter(fullUpTo, '{%', '%}'),
    expr: hasOpenDelimiter(fullUpTo, '{{', '}}')
  };
}

function buildFilterCompletionItem(
  monaco: any,
  key: string,
  signature: FilterSignature,
  range: any
) {
  const paramString = signature.parameters
    .map((p) => `${p.name}: ${p.type}`)
    .join(', ');
  const signatureString = `${key}(${paramString}) → ${signature.returnValue.type}`;
  return {
    label: key,
    kind: monaco.languages.CompletionItemKind.Function,
    documentation: {
      value: [
        '```jinja2',
        signatureString,
        '```',
        signature.documentation,
        '',
        'Parameters:',
        ...signature.parameters.map(
          (p) => `- ${p.name} (${p.type}): ${p.description}`
        ),
        '',
        'Returns:',
        `${signature.returnValue.type}: ${signature.returnValue.description}`
      ].join('\n')
    },
    detail: signature.documentation,
    insertText: signature.parameters.length > 0 ? `${key}($0)` : `${key} `,
    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
    range,
    command:
      signature.parameters.length > 0
        ? {
            id: 'editor.action.triggerParameterHints',
            title: 'Trigger Parameter Hints'
          }
        : undefined
  };
}

function registerSnippetProvider(
  monaco: any,
  languageId: string,
  snips: JinjaSnippet[]
) {
  return monaco.languages.registerCompletionItemProvider(languageId, {
    provideCompletionItems: (model: any, position: any) => {
      const word = model.getWordUntilPosition(position);
      const range = rangeAt(position, word);
      return {
        suggestions: snips.map((s) => ({
          label: s.label,
          kind: monaco.languages.CompletionItemKind.Snippet,
          insertText: s.insertText,
          detail: s.detail,
          documentation: s.detail,
          insertTextRules: s.asSnippet
            ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
            : undefined,
          range
        }))
      };
    }
  });
}

/** In YAML, fire snippet suggestions only when the cursor is in an
 *  empty word position on a line that already has Jinja markers or is
 *  obviously a value position. We do NOT want every YAML key to
 *  trigger the full Jinja snippet list. Heuristic: only when the
 *  cursor is inside `{{ }}` / `{% %}` OR the line trims to start with
 *  one of `{%`, `{{`. */
function registerJinjaSnippetProviderInYaml(monaco: any, snips: JinjaSnippet[]) {
  return monaco.languages.registerCompletionItemProvider('yaml', {
    provideCompletionItems: (model: any, position: any) => {
      const ctx = insideJinja(model, position);
      if (!ctx.tag && !ctx.expr) return { suggestions: [] };
      const word = model.getWordUntilPosition(position);
      const range = rangeAt(position, word);
      return {
        suggestions: snips.map((s) => ({
          label: s.label,
          kind: monaco.languages.CompletionItemKind.Snippet,
          insertText: s.insertText,
          detail: s.detail,
          documentation: s.detail,
          insertTextRules: s.asSnippet
            ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
            : undefined,
          range
        }))
      };
    }
  });
}

function registerFilterCompletionProvider(
  monaco: any,
  languageId: string,
  filters: Record<string, FilterSignature>
) {
  return monaco.languages.registerCompletionItemProvider(languageId, {
    triggerCharacters: ['|', ' '],
    provideCompletionItems: (model: any, position: any) => {
      const linePrefix = model
        .getLineContent(position.lineNumber)
        .substring(0, position.column - 1);
      if (!/\|\s*$/.test(linePrefix)) return { suggestions: [] };
      // In YAML, only inside a jinja expression / tag.
      if (languageId === 'yaml') {
        const ctx = insideJinja(model, position);
        if (!ctx.tag && !ctx.expr) return { suggestions: [] };
      }
      const word = model.getWordUntilPosition(position);
      const range = rangeAt(position, word);
      const suggestions = Object.entries(filters).map(([key, signature]) =>
        buildFilterCompletionItem(monaco, key, signature, range)
      );
      return { suggestions };
    }
  });
}

function registerVariableCompletionProvider(monaco: any, languageId: string) {
  const keywords = [
    'if', 'elif', 'else', 'endif',
    'for', 'in', 'endfor',
    'set', 'block', 'endblock',
    'macro', 'endmacro', 'include', 'extends',
    'with', 'endwith', 'filter', 'endfilter',
    'raw', 'endraw', 'and', 'or', 'not', 'is'
  ];
  const rootSuggestions = [
    { text: 'vars', detail: 'Top-level Jinja context' },
    { text: 'vars.input', detail: 'Trigger input payload' },
    { text: 'vars.input.records', detail: 'Input record list' },
    { text: 'vars.input.records[0]', detail: 'First input record' },
    { text: 'vars.steps', detail: 'Previous playbook step outputs' },
    { text: 'loop', detail: 'Current loop context (index, first, last, …)' },
    { text: 'loop.index', detail: '1-based loop index' },
    { text: 'loop.index0', detail: '0-based loop index' },
    { text: 'loop.first', detail: 'True on the first iteration' },
    { text: 'loop.last', detail: 'True on the last iteration' }
  ];

  return monaco.languages.registerCompletionItemProvider(languageId, {
    triggerCharacters: [' ', '{'],
    provideCompletionItems: (model: any, position: any) => {
      const lineUpTo: string = model
        .getLineContent(position.lineNumber)
        .substring(0, position.column - 1);
      const ctx = insideJinja(model, position);
      if (!ctx.tag && !ctx.expr) return { suggestions: [] };
      // Suppress mid-filter — the filter provider owns that completion path.
      if (/\|\s*[\w]*$/.test(lineUpTo)) return { suggestions: [] };

      const word = model.getWordUntilPosition(position);
      const range = rangeAt(position, word);
      const suggestions: any[] = [];
      rootSuggestions.forEach((s) => {
        suggestions.push({
          label: s.text,
          kind: monaco.languages.CompletionItemKind.Variable,
          insertText: s.text,
          detail: s.detail,
          range
        });
      });
      if (ctx.tag) {
        keywords.forEach((kw) => {
          suggestions.push({
            label: kw,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: kw,
            range
          });
        });
      }
      return { suggestions };
    }
  });
}

function registerFilterHoverProvider(
  monaco: any,
  languageId: string,
  filters: Record<string, FilterSignature>
) {
  return monaco.languages.registerHoverProvider(languageId, {
    provideHover: (model: any, position: any) => {
      const word = model.getWordAtPosition(position);
      if (!word) return null;
      // In YAML, only show the filter hover when inside a `{{ … }}`
      // or `{% … %}` region — otherwise a plain word like "upper"
      // appearing in description text shouldn't pop the filter card.
      if (languageId === 'yaml') {
        const ctx = insideJinja(model, position);
        if (!ctx.tag && !ctx.expr) return null;
      }
      const signature = filters[word.word];
      if (!signature) return null;
      const contents = [
        { value: `**Function:** \`${word.word}\`` },
        { value: `**Documentation:** ${signature.documentation}` },
        { value: `**Example:** \`${signature.example}\`` },
        { value: `**Parameters:**` }
      ];
      signature.parameters.forEach((p) => {
        contents.push({
          value: `- **${p.name}** (*${p.type}*): ${p.description}`
        });
      });
      contents.push({
        value: `**Returns:** \`${signature.returnValue.type}\`: ${signature.returnValue.description}`
      });
      return {
        contents,
        range: new monaco.Range(
          position.lineNumber,
          word.startColumn,
          position.lineNumber,
          word.endColumn
        )
      };
    }
  });
}

function registerSignatureHelpProvider(
  monaco: any,
  languageId: string,
  filters: Record<string, FilterSignature>
) {
  return monaco.languages.registerSignatureHelpProvider(languageId, {
    signatureHelpTriggerCharacters: ['(', ','],
    provideSignatureHelp: (model: any, position: any) => {
      if (languageId === 'yaml') {
        const ctx = insideJinja(model, position);
        if (!ctx.tag && !ctx.expr) return null;
      }
      const textUntilPosition: string = model.getValueInRange({
        startLineNumber: 1,
        startColumn: 1,
        endLineNumber: position.lineNumber,
        endColumn: position.column
      });
      const match = textUntilPosition.match(/([a-zA-Z0-9_]+)\s*\(([^)]*)$/);
      if (!match) return null;
      const [, functionName, paramsString] = match;
      const signature = filters[functionName];
      if (!signature) return null;
      const activeParameter = paramsString.split(',').length - 1;
      const signatureInfo = {
        label: `${functionName}(${signature.parameters
          .map((p) => `${p.name}: ${p.type}`)
          .join(', ')}) → ${signature.returnValue.type}`,
        documentation: signature.documentation,
        parameters: signature.parameters.map((p) => ({
          label: `${p.name}: ${p.type}`,
          documentation: p.description
        }))
      };
      return {
        value: {
          signatures: [signatureInfo],
          activeSignature: 0,
          activeParameter
        },
        dispose: () => {}
      };
    }
  });
}

// ── member-access completions (input-JSON-aware) ─────────────────────

function registerMemberCompletionProvider(monaco: any, languageId: string) {
  return monaco.languages.registerCompletionItemProvider(languageId, {
    triggerCharacters: ['.', '['],
    provideCompletionItems: (model: any, position: any) => {
      if (!currentInputContext) return { suggestions: [] };
      const ctx = insideJinja(model, position);
      if (!ctx.tag && !ctx.expr) return { suggestions: [] };

      const lineUpTo: string = model
        .getLineContent(position.lineNumber)
        .substring(0, position.column - 1);
      const parsed = parseAccessorPath(lineUpTo);
      if (!parsed) return { suggestions: [] };
      const target = navigateObject(currentInputContext, parsed.tokens);
      if (target === undefined || target === null) return { suggestions: [] };

      const word = model.getWordUntilPosition(position);
      const range = rangeAt(position, word);
      return {
        suggestions: buildMemberSuggestions(monaco, target, parsed.separator, parsed.partial, range)
      };
    }
  });
}

type AccessorToken = { type: 'key'; value: string } | { type: 'index'; value: number };

function parseAccessorPath(
  line: string
): { tokens: AccessorToken[]; separator: '.' | '['; partial: string } | null {
  const re =
    /((?:[A-Za-z_$][A-Za-z0-9_$]*)(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[(?:\d+|'[^']*'|"[^"]*")\])*)(\.|\[)([A-Za-z_$][A-Za-z0-9_$]*)?$/;
  const m = line.match(re);
  if (!m) return null;
  const chain = m[1];
  const separator = m[2] as '.' | '[';
  const partial = m[3] || '';
  const tokens: AccessorToken[] = [];
  const tokRe = /([A-Za-z_$][A-Za-z0-9_$]*)|\[(\d+)\]|\['([^']*)'\]|\["([^"]*)"\]/g;
  for (const tm of chain.matchAll(tokRe)) {
    if (tm[1] !== undefined) tokens.push({ type: 'key', value: tm[1] });
    else if (tm[2] !== undefined) tokens.push({ type: 'index', value: parseInt(tm[2], 10) });
    else if (tm[3] !== undefined) tokens.push({ type: 'key', value: tm[3] });
    else if (tm[4] !== undefined) tokens.push({ type: 'key', value: tm[4] });
  }
  if (tokens.length === 0) return null;
  return { tokens, separator, partial };
}

function navigateObject(ctx: unknown, tokens: AccessorToken[]): unknown {
  let cur: any = ctx;
  for (const tok of tokens) {
    if (cur === null || cur === undefined) return undefined;
    if (tok.type === 'key') {
      if (typeof cur !== 'object' || Array.isArray(cur)) return undefined;
      cur = cur[tok.value];
    } else {
      if (!Array.isArray(cur)) return undefined;
      cur = cur[tok.value];
    }
  }
  return cur;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function escapeSingleQuotes(s: string): string {
  return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function describeValue(v: unknown): string {
  if (v === null) return 'null';
  if (v === undefined) return 'undefined';
  if (Array.isArray(v)) return `array (${v.length})`;
  if (typeof v === 'object') return `object (${Object.keys(v as object).length} keys)`;
  if (typeof v === 'string') {
    const p = v.length > 40 ? v.slice(0, 37) + '…' : v;
    return `string "${p}"`;
  }
  return `${typeof v}: ${v}`;
}

function memberKind(monaco: any, value: unknown) {
  if (Array.isArray(value)) return monaco.languages.CompletionItemKind.Variable;
  if (isPlainObject(value)) return monaco.languages.CompletionItemKind.Module;
  return monaco.languages.CompletionItemKind.Field;
}

function buildMemberSuggestions(
  monaco: any,
  target: unknown,
  separator: '.' | '[',
  partial: string,
  range: any
): any[] {
  const out: any[] = [];
  if (target === null || target === undefined) return out;

  if (Array.isArray(target)) {
    if (separator === '[') {
      const cap = Math.min(target.length, 50);
      for (let i = 0; i < cap; i++) {
        out.push({
          label: String(i),
          kind: monaco.languages.CompletionItemKind.Value,
          insertText: String(i),
          detail: describeValue(target[i]),
          sortText: String(i).padStart(6, '0'),
          range
        });
      }
      if (target.length > 0 && isPlainObject(target[0])) {
        Object.keys(target[0] as object).forEach((key) => {
          out.push({
            label: "'" + key + "'",
            kind: monaco.languages.CompletionItemKind.Field,
            insertText: "'" + escapeSingleQuotes(key) + "'",
            detail: 'first-element key — ' + describeValue((target[0] as any)[key]),
            sortText: 'zz_' + key,
            range
          });
        });
      }
    }
    return out;
  }
  if (!isPlainObject(target)) return out;
  const partialLower = partial.toLowerCase();
  for (const key of Object.keys(target)) {
    if (partialLower && !key.toLowerCase().startsWith(partialLower)) continue;
    const value = (target as any)[key];
    if (separator === '.') {
      if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(key)) continue;
      out.push({
        label: key,
        kind: memberKind(monaco, value),
        insertText: key,
        detail: describeValue(value),
        range
      });
    } else {
      out.push({
        label: "'" + key + "'",
        kind: memberKind(monaco, value),
        insertText: "'" + escapeSingleQuotes(key) + "'",
        detail: describeValue(value),
        range
      });
    }
  }
  return out;
}
