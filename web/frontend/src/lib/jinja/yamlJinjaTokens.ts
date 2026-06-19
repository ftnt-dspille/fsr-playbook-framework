/**
 * Combined YAML + Jinja Monarch tokenizer.
 *
 * Monaco's default YAML tokenizer paints `{{ ... }}` as plain string
 * content — no syntax help for templates embedded in playbook YAML.
 * This module replaces the YAML tokenizer with one that dispatches
 * into Jinja states (`{{ }}`, `{% %}`, `{# #}`) and emits the same
 * token names the Jinja theme uses (punctuation.expression, keyword,
 * variable.other, string, number, …).
 *
 * Coverage for the YAML side is intentionally pragmatic: keys,
 * scalars, comments, anchors/refs, block / flow markers, and quoted
 * strings — enough to match Monaco's default look-and-feel for the
 * kinds of YAML this app edits (FortiSOAR playbook YAML). It is NOT a
 * full YAML 1.2 reference tokenizer.
 *
 * The theme name `jinjaTheme` (defined in registerJinja) already
 * targets these tokens; the YAML-only tokens fall back to the theme's
 * inherited / default colours.
 */

export const yamlJinjaTokens = {
  defaultToken: '',
  tokenPostfix: '.yaml',

  brackets: [
    { token: 'delimiter.bracket', open: '{', close: '}' },
    { token: 'delimiter.square', open: '[', close: ']' }
  ],

  // YAML keywords (boolean / null literals)
  keywords: [
    'true', 'false', 'null', 'True', 'False', 'Null', 'NULL', 'TRUE', 'FALSE',
    'yes', 'no', 'Yes', 'No', 'YES', 'NO', '~'
  ],

  numberInteger: /(?:0|[+-]?[0-9]+)/,
  numberFloat: /(?:0|[+-]?[0-9]+)(?:\.[0-9]+)?(?:e[-+][1-9][0-9]*)?/,
  numberOctal: /0o[0-7]+/,
  numberHex: /0x[0-9a-fA-F]+/,
  numberInfinity: /[+-]?\.(?:inf|Inf|INF)/,
  numberNaN: /\.(?:nan|Nan|NAN)/,
  escapes: /\\(?:[btnfr\\"'0]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4})/,

  tokenizer: {
    root: [
      // Jinja delimiters — dispatch into dedicated states.
      [/{%-?/, { token: 'punctuation.control', next: '@jinjaTag' }],
      [/{{-?/, { token: 'punctuation.expression', next: '@jinjaExpression' }],
      [/{#/, { token: 'comment.documentation', next: '@jinjaComment' }],

      // YAML directive
      [/%[^ ]+.*$/, 'meta.directive'],

      // Document markers
      [/---/, 'operators.directivesEnd'],
      [/\.{3}/, 'operators.documentEnd'],

      // Block sequence entry
      [/[-?:](?= )/, 'operators'],

      { include: '@anchor' },
      { include: '@tagHandle' },
      { include: '@flowCollections' },
      { include: '@blockStyle' },

      // Numbers in flow context
      [/@numberInteger(?![ \t]*\S+)/, 'number'],
      [/@numberFloat(?![ \t]*\S+)/, 'number.float'],
      [/@numberOctal(?![ \t]*\S+)/, 'number.octal'],
      [/@numberHex(?![ \t]*\S+)/, 'number.hex'],
      [/@numberInfinity(?![ \t]*\S+)/, 'number.infinity'],
      [/@numberNaN(?![ \t]*\S+)/, 'number.nan'],

      // Date / time
      [/\d{4}-\d{2}-\d{2}([Tt ]\d{2}:\d{2}:\d{2}(\.\d+)?(( ?[+-]\d{2}:\d{2})|Z)?)?/, 'number.date'],

      // Map keys — must come before comments so `key #` works.
      [/(".*?"|'.*?'|[^#'"\s][^#:]*?)([ \t]*)(:)( |$)/, ['type', 'white', 'operators', 'white']],

      // Strings
      { include: '@flowScalars' },

      // Plain scalar — keyword / generic
      [/[^#]+?(?=[,\]}]|\s+#|$)/, {
        cases: {
          '@keywords': 'keyword',
          '@default': 'string'
        }
      }],

      // Comments
      [/#.*$/, 'comment']
    ],

    // ── Jinja states ────────────────────────────────────────────────
    jinjaTag: [
      [/-?%}/, { token: 'punctuation.control', next: '@pop' }],
      [
        /\b(set|if|else|elif|for|in|endfor|endif|block|endblock|filter|endfilter|macro|endmacro|with|endwith|include|extends|import|as|from|do|raw|endraw|call|endcall|autoescape|endautoescape|trans|endtrans|pluralize)\b/,
        'keyword'
      ],
      [/\b(true|false|none|True|False|None)\b/, 'constant.language'],
      [/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/, 'string'],
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
      [/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/, 'string'],
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
    ],

    // ── YAML sub-states ─────────────────────────────────────────────
    flowCollections: [
      [/\[/, '@brackets', '@array'],
      [/\{/, '@brackets', '@object']
    ],
    flowScalars: [
      [/"([^"\\]|\\.)*$/, 'string.invalid'],
      [/'([^'\\]|\\.)*$/, 'string.invalid'],
      [/'[^']*'/, 'string'],
      [/"/, 'string', '@doubleQuotedString']
    ],
    doubleQuotedString: [
      [/[^\\"]+/, 'string'],
      [/@escapes/, 'string.escape'],
      [/\\./, 'string.escape.invalid'],
      [/"/, 'string', '@pop']
    ],
    blockStyle: [[/[>|][0-9]*[+-]?$/, 'operators', '@multiString']],
    multiString: [[/^( +).+$/, 'string', '@multiStringContinued.$1']],
    multiStringContinued: [
      [/^( *).+$/, {
        cases: {
          '$1==$S2': 'string',
          '@default': { token: '@rematch', next: '@popall' }
        }
      }]
    ],
    anchor: [
      [/[&*][^ \t]+/, 'namespace']
    ],
    tagHandle: [[/![^ ]*/, 'tag']],
    array: [
      { include: '@root' },
      [/,/, 'delimiter.comma'],
      [/\]/, '@brackets', '@pop']
    ],
    object: [
      { include: '@root' },
      [/,/, 'delimiter.comma'],
      [/:/, 'operators'],
      [/\}/, '@brackets', '@pop']
    ]
  }
} as any;
