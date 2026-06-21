export interface JinjaSnippet {
  label: string;
  detail: string;
  insertText: string;
  asSnippet?: boolean;
}

export const snippets: JinjaSnippet[] = [
  { label: 'if', detail: 'Conditional block', insertText: '{% if ${1:condition} %}\n\t$0\n{% endif %}', asSnippet: true },
  { label: 'if-else', detail: 'Conditional with else branch', insertText: '{% if ${1:condition} %}\n\t${2}\n{% else %}\n\t${0}\n{% endif %}', asSnippet: true },
  { label: 'if-elif-else', detail: 'Conditional chain', insertText: '{% if ${1:condition} %}\n\t${2}\n{% elif ${3:other_condition} %}\n\t${4}\n{% else %}\n\t${0}\n{% endif %}', asSnippet: true },
  { label: 'for', detail: 'Iterate over a collection', insertText: '{% for ${1:item} in ${2:collection} %}\n\t$0\n{% endfor %}', asSnippet: true },
  { label: 'for-else', detail: 'Iterate with fallback when empty', insertText: '{% for ${1:item} in ${2:collection} %}\n\t${3}\n{% else %}\n\t${0:No items}\n{% endfor %}', asSnippet: true },
  { label: 'for-index', detail: 'Iterate with loop.index', insertText: '{% for ${1:item} in ${2:collection} %}\n\t{{ loop.index }}. {{ ${1:item} }}$0\n{% endfor %}', asSnippet: true },
  { label: 'set', detail: 'Assign a variable', insertText: '{% set ${1:name} = ${2:value} %}$0', asSnippet: true },
  { label: 'macro', detail: 'Define a reusable macro', insertText: '{% macro ${1:name}(${2:args}) %}\n\t$0\n{% endmacro %}', asSnippet: true },
  { label: 'block', detail: 'Define an overridable block', insertText: '{% block ${1:name} %}\n\t$0\n{% endblock %}', asSnippet: true },
  { label: 'filter', detail: 'Apply a filter to a block of text', insertText: '{% filter ${1:upper} %}\n\t$0\n{% endfilter %}', asSnippet: true },
  { label: 'raw', detail: 'Literal text, ignore Jinja syntax inside', insertText: '{% raw %}\n\t$0\n{% endraw %}', asSnippet: true },
  { label: 'include', detail: 'Include another template', insertText: '{% include "${1:template}" %}$0', asSnippet: true },
  { label: 'extends', detail: 'Extend a parent template', insertText: '{% extends "${1:base.html}" %}$0', asSnippet: true },
  { label: 'expression', detail: 'Print an expression — {{ … }}', insertText: '{{ $0 }}', asSnippet: true },
  { label: 'comment', detail: 'Jinja comment — {# … #}', insertText: '{# $0 #}', asSnippet: true },
  { label: 'ternary', detail: 'Inline conditional expression', insertText: '{{ ${1:value_if_true} if ${2:condition} else ${3:value_if_false} }}$0', asSnippet: true },
  { label: 'default', detail: 'Value or fallback via default filter', insertText: "{{ ${1:value} | default(${2:'-'}) }}$0", asSnippet: true },
  { label: 'records-loop', detail: 'Loop over vars.input.records', insertText: '{% for record in vars.input.records %}\n\t{{ record.${1:name} }}$0\n{% endfor %}', asSnippet: true }
];
