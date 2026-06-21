/**
 * Jinja language definition for Monaco — tokenizer, language config,
 * dark + light themes. Ported from the widget-jinja-editor widget.
 *
 * The tokenizer and the theme rule list are tightly coupled: tokens
 * named here (punctuation.control, variable.other, …) must match the
 * theme rules below or text falls back to the editor's default color.
 */

export interface JinjaTheme {
  name: string;
  base: 'vs' | 'vs-dark' | 'hc-black' | 'hc-light';
  inherit: boolean;
  rules: Array<{ token: string; foreground?: string; fontStyle?: string }>;
  colors: Record<string, string>;
}

export interface JinjaLanguageDefinition {
  id: string;
  tokenizer: Record<string, Array<[RegExp, string | { token: string; next?: string }]>>;
  configuration: any;
  theme: JinjaTheme;
  themeLight: JinjaTheme;
}

export const languageDefinition: JinjaLanguageDefinition = {
  id: 'jinja',
  tokenizer: {
    root: [
      [/{%-?/, { token: 'punctuation.control', next: '@jinjaTag' }],
      [/{{-?/, { token: 'punctuation.expression', next: '@jinjaExpression' }],
      [/{#/, { token: 'comment.documentation', next: '@jinjaComment' }]
    ],
    jinjaTag: [
      [/-?%}/, { token: 'punctuation.control', next: '@pop' }],
      [
        /\b(set|if|else|elif|for|in|endfor|endif|block|endblock|filter|endfilter|macro|endmacro|with|endwith|include|extends|import|as|from|do|raw|endraw|call|endcall|autoescape|endautoescape|trans|endtrans|pluralize)\b/,
        'keyword'
      ],
      [/\b(true|false|none|True|False|None)\b/, 'constant.language'],
      [/["](?:[^"\\]|\\.)*["]|['](?:[^'\\]|\\.)*[']/, 'string'],
      [/\b\d+(\.\d+)?\b/, 'number'],
      [/\b(and|or|not|in|is)\b/, 'keyword.operator'],
      [/[=!<>]=?|[+\-*/%]/, 'operator'],
      [/\b[a-zA-Z_][a-zA-Z0-9_]*\b/, 'variable.other'],
      [/\|/, 'operator'],
      [/\./, 'delimiter']
    ],
    jinjaExpression: [
      [/-?}}/, { token: 'punctuation.expression', next: '@pop' }],
      [/\b(true|false|none|True|False|None)\b/, 'constant.language'],
      [/["](?:[^"\\]|\\.)*["]|['](?:[^'\\]|\\.)*[']/, 'string'],
      [/\b\d+(\.\d+)?\b/, 'number'],
      [/\b(and|or|not|in|is|if|else)\b/, 'keyword.operator'],
      [/[=!<>]=?|[+\-*/%]/, 'operator'],
      [/\b[a-zA-Z_][a-zA-Z0-9_]*\b/, 'variable.other'],
      [/\|/, 'operator'],
      [/\./, 'delimiter']
    ],
    jinjaComment: [
      [/#}/, { token: 'comment.documentation', next: '@pop' }],
      [/[^#]+/, 'comment.documentation'],
      [/#+/, 'comment.documentation']
    ]
  },
  configuration: {
    comments: { blockComment: ['{#', '#}'] },
    brackets: [
      ['{%', '%}'],
      ['{{', '}}'],
      ['{#', '#}'],
      ['{', '}'],
      ['[', ']'],
      ['(', ')']
    ],
    autoClosingPairs: [
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '"', close: '"', notIn: ['string'] },
      { open: "'", close: "'", notIn: ['string'] }
    ],
    surroundingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '"', close: '"' },
      { open: "'", close: "'" }
    ],
    wordPattern:
      /(-?\d*\.\d\w*)|([^\`\~\!\@\#\%\^\&\*\(\)\-\=\+\[\{\]\}\\\|\;\:\'\"\,\.\<\>\/\?\s]+)/g,
    onEnterRules: [
      {
        beforeText:
          /^\s*\{%-?\s*(if|for|block|macro|with|filter|call|raw|autoescape|trans)\b[^%]*-?%\}\s*$/,
        afterText: /^\s*\{%-?\s*end\w+-?%\}/,
        action: { indentAction: 2 } // IndentAction.IndentOutdent
      }
    ]
  },
  theme: {
    name: 'jinjaTheme',
    base: 'vs-dark',
    inherit: false,
    rules: [
      { token: 'comment.documentation', foreground: '6A9955', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'C678DD' },
      { token: 'variable.other', foreground: 'E06C75' },
      { token: 'string', foreground: '98C379' },
      { token: 'number', foreground: 'B5CEA8' },
      { token: 'keyword.operator', foreground: 'C678DD' },
      { token: 'operator', foreground: '56B6C2' },
      { token: 'punctuation.control', foreground: 'C99C6E' },
      { token: 'punctuation.expression', foreground: '61AFEF' },
      { token: 'constant.language', foreground: 'D19A66' },
      { token: 'delimiter', foreground: 'ABB2BF' }
    ],
    colors: { 'editor.foreground': '#FFFFFF' }
  },
  themeLight: {
    name: 'jinjaThemeLight',
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'comment.documentation', foreground: '267F99', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'AF00DB' },
      { token: 'variable.other', foreground: 'C0392B' },
      { token: 'string', foreground: '2E7D32' },
      { token: 'number', foreground: '0D47A1' },
      { token: 'keyword.operator', foreground: 'AF00DB' },
      { token: 'operator', foreground: '0078A8' },
      { token: 'punctuation.control', foreground: '7D5A00' },
      { token: 'punctuation.expression', foreground: '1565C0' },
      { token: 'constant.language', foreground: 'B45309' },
      { token: 'delimiter', foreground: '383A42' }
    ],
    colors: { 'editor.foreground': '#000000', 'editor.background': '#ffffff' }
  }
};

/** Block-opening tags → matching closer. enhanceJinjaEditor reads this
 *  to offer `{% endX %}` insertion when the user finishes typing an
 *  opening `{% if … %}` etc. */
export const blockTagPairs: Record<string, string> = {
  if: 'endif',
  for: 'endfor',
  block: 'endblock',
  macro: 'endmacro',
  with: 'endwith',
  filter: 'endfilter',
  call: 'endcall',
  raw: 'endraw',
  autoescape: 'endautoescape',
  trans: 'endtrans'
};
