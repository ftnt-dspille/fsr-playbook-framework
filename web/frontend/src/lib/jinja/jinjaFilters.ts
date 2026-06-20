/**
 * Jinja filter signature library — drives three features:
 *   * inline completion after `|`
 *   * hover + signature-help popups
 *   * the Filter Library palette (search by name / description, grouped
 *     by category, click to insert at the cursor).
 *
 * Ported verbatim from the widget-jinja-editor widget. Categories are
 * presentation-only; filterCategoryOrder controls palette section
 * order, and any unknown category falls into "Other".
 */

export interface FilterParameter {
  name: string;
  type: string;
  description: string;
}

export interface FilterReturn {
  type: string;
  description: string;
}

export interface FilterSignature {
  category: string;
  documentation: string;
  example: string;
  parameters: FilterParameter[];
  returnValue: FilterReturn;
}

const stringFilters: Record<string, FilterSignature> = {
  upper: {
    category: 'String',
    documentation: 'Converts a string to uppercase.',
    example: '{{ vars.input.records[0].name | upper }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The uppercase string.' }
  },
  lower: {
    category: 'String',
    documentation: 'Converts a string to lowercase.',
    example: '{{ vars.input.records[0].name | lower }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The lowercase string.' }
  },
  title: {
    category: 'String',
    documentation: 'Capitalizes the first character of each word in the string.',
    example: '{{ vars.input.records[0].name | title }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The title-cased string.' }
  },
  capitalize: {
    category: 'String',
    documentation: 'Capitalizes the first character and lowercases the rest of the string.',
    example: '{{ vars.input.records[0].description | capitalize }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The capitalized string.' }
  },
  trim: {
    category: 'String',
    documentation: 'Removes leading and trailing whitespace from a string.',
    example: '{{ vars.input.records[0].name | trim }}',
    parameters: [
      { name: 'chars', type: 'string', description: 'Characters to strip. Defaults to whitespace.' }
    ],
    returnValue: { type: 'string', description: 'The trimmed string.' }
  },
  replace: {
    category: 'String',
    documentation: 'Replaces occurrences of a substring within a given string.',
    example: "{{ vars.input.records[0].status | replace('open', 'active') }}",
    parameters: [
      { name: 'old', type: 'string', description: 'The substring to be replaced.' },
      { name: 'new', type: 'string', description: 'The substring to replace with.' },
      { name: 'count', type: 'integer', description: 'Maximum number of occurrences to replace. Optional.' }
    ],
    returnValue: { type: 'string', description: 'The string with replacements made.' }
  },
  split: {
    category: 'String',
    documentation: 'Splits a string into a list on a specified separator.',
    example: "{{ vars.input.records[0].tags | split(',') | join(', ') }}",
    parameters: [
      { name: 'separator', type: 'string', description: 'The delimiter to use for splitting.' },
      { name: 'limit', type: 'integer', description: 'Maximum number of splits to perform. Optional.' }
    ],
    returnValue: { type: 'list', description: 'A list of substrings.' }
  },
  truncate: {
    category: 'String',
    documentation: 'Truncates a string to a maximum length, appending a suffix.',
    example: '{{ vars.input.records[0].description | truncate(80) }}',
    parameters: [
      { name: 'length', type: 'integer', description: 'Maximum length of the output.' },
      { name: 'killwords', type: 'boolean', description: 'If true, cut mid-word. Optional.' },
      { name: 'end', type: 'string', description: "Suffix to append when truncated. Defaults to '...'." }
    ],
    returnValue: { type: 'string', description: 'The truncated string.' }
  },
  wordcount: {
    category: 'String',
    documentation: 'Counts the words in a string.',
    example: '{{ vars.input.records[0].description | wordcount }} words',
    parameters: [],
    returnValue: { type: 'integer', description: 'Number of words.' }
  },
  wordwrap: {
    category: 'String',
    documentation: 'Wraps a string so that each line is at most `width` characters long.',
    example: '{{ vars.input.records[0].description | wordwrap(72) }}',
    parameters: [
      { name: 'width', type: 'integer', description: 'Maximum line length.' },
      { name: 'break_long_words', type: 'boolean', description: 'Break words longer than width. Optional.' }
    ],
    returnValue: { type: 'string', description: 'The wrapped string.' }
  },
  center: {
    category: 'String',
    documentation: 'Centers a value within a given width, padding with spaces.',
    example: '{{ vars.input.records[0].name | center(40) }}',
    parameters: [{ name: 'width', type: 'integer', description: 'Total output width.' }],
    returnValue: { type: 'string', description: 'The centered string.' }
  },
  indent: {
    category: 'String',
    documentation: 'Indents each line of a string with a number of spaces.',
    example: '{{ vars.input.records[0].body | indent(4) }}',
    parameters: [
      { name: 'width', type: 'integer', description: 'Number of spaces per indent.' },
      { name: 'first', type: 'boolean', description: 'Indent the first line too. Optional.' },
      { name: 'blank', type: 'boolean', description: 'Indent blank lines too. Optional.' }
    ],
    returnValue: { type: 'string', description: 'The indented string.' }
  },
  striptags: {
    category: 'String',
    documentation: 'Strips SGML/XML tags and collapses whitespace.',
    example: '{{ vars.input.records[0].htmlBody | striptags }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The stripped string.' }
  },
  escape: {
    category: 'Encoding',
    documentation: "Replaces the characters &, <, >, ' and \" with HTML-safe sequences. Alias: e.",
    example: '{{ vars.input.records[0].userInput | escape }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The HTML-escaped string.' }
  },
  safe: {
    category: 'Encoding',
    documentation: "Marks a string as safe so it won't be escaped by autoescape.",
    example: '{{ vars.input.records[0].htmlContent | safe }}',
    parameters: [],
    returnValue: { type: 'string', description: 'A Markup-wrapped string.' }
  },
  urlencode: {
    category: 'Encoding',
    documentation: "Percent-encodes a string so it's safe for use in a URL query.",
    example: 'https://example.com/search?q={{ vars.input.records[0].query | urlencode }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The URL-encoded string.' }
  },
  urlize: {
    category: 'Encoding',
    documentation: 'Converts URLs in plain text into clickable `<a>` links.',
    example: '{{ vars.input.records[0].notes | urlize }}',
    parameters: [
      { name: 'trim_url_limit', type: 'integer', description: 'Maximum displayed URL length. Optional.' },
      { name: 'nofollow', type: 'boolean', description: 'Add rel=nofollow. Optional.' }
    ],
    returnValue: { type: 'string', description: 'HTML with linked URLs.' }
  },
  format: {
    category: 'String',
    documentation: 'Applies printf-style string formatting.',
    example: "{{ 'Hello, %s!' | format(vars.input.records[0].name) }}",
    parameters: [
      { name: 'args', type: 'any', description: 'Positional arguments substituted into the format string.' }
    ],
    returnValue: { type: 'string', description: 'The formatted string.' }
  },
  string: {
    category: 'Conversion',
    documentation: 'Converts a value to a string.',
    example: '{{ vars.input.records[0].count | string }}',
    parameters: [],
    returnValue: { type: 'string', description: 'The string representation.' }
  }
};

const collectionFilters: Record<string, FilterSignature> = {
  length: {
    category: 'Collection',
    documentation: 'Returns the length of a string, list, or dictionary. Alias: count.',
    example: '{{ vars.input.records | length }} records',
    parameters: [],
    returnValue: { type: 'integer', description: 'The length of the object.' }
  },
  first: {
    category: 'Collection',
    documentation: 'Returns the first item of a sequence.',
    example: '{{ vars.input.records | first }}',
    parameters: [],
    returnValue: { type: 'any', description: 'The first element.' }
  },
  last: {
    category: 'Collection',
    documentation: 'Returns the last item of a sequence.',
    example: '{{ vars.input.records | last }}',
    parameters: [],
    returnValue: { type: 'any', description: 'The last element.' }
  },
  reverse: {
    category: 'Collection',
    documentation: 'Reverses the order of items in a sequence or string.',
    example: '{% for r in vars.input.records | reverse %}{{ r.name }}\n{% endfor %}',
    parameters: [],
    returnValue: { type: 'any', description: 'The reversed sequence.' }
  },
  sort: {
    category: 'Collection',
    documentation: 'Sorts a sequence. Use `attribute` to sort a list of objects.',
    example: "{% for r in vars.input.records | sort(attribute='name') %}{{ r.name }}\n{% endfor %}",
    parameters: [
      { name: 'reverse', type: 'boolean', description: 'Sort descending. Optional.' },
      { name: 'case_sensitive', type: 'boolean', description: 'Case-sensitive comparison. Optional.' },
      { name: 'attribute', type: 'string', description: 'Sort by this attribute. Optional.' }
    ],
    returnValue: { type: 'list', description: 'A sorted list.' }
  },
  unique: {
    category: 'Collection',
    documentation: 'Removes duplicates from a sequence, preserving order.',
    example: "{{ vars.input.records | map(attribute='status') | unique | join(', ') }}",
    parameters: [
      { name: 'case_sensitive', type: 'boolean', description: 'Case-sensitive comparison. Optional.' },
      { name: 'attribute', type: 'string', description: 'Deduplicate by this attribute. Optional.' }
    ],
    returnValue: { type: 'list', description: 'A list of unique items.' }
  },
  join: {
    category: 'Collection',
    documentation: 'Concatenates a list of strings with a specified separator.',
    example: "{{ vars.input.records | map(attribute='name') | join(', ') }}",
    parameters: [
      { name: 'separator', type: 'string', description: 'The string to use as a separator.' },
      { name: 'attribute', type: 'string', description: 'Optional attribute to use when joining a list of objects.' }
    ],
    returnValue: { type: 'string', description: 'The joined string.' }
  },
  map: {
    category: 'Collection',
    documentation: 'Applies a filter or extracts an attribute from each item in a sequence.',
    example: "{{ vars.input.records | map(attribute='name') | join(', ') }}",
    parameters: [
      { name: 'filter_or_attribute', type: 'string', description: "Filter name or 'attribute=NAME' selector." }
    ],
    returnValue: { type: 'list', description: 'A list of mapped values.' }
  },
  select: {
    category: 'Collection',
    documentation: 'Filters a sequence, keeping items where the test passes.',
    example: "{{ [1, 2, 3, 4] | select('odd') | list }}",
    parameters: [{ name: 'test', type: 'string', description: "Name of the test to apply (e.g. 'even')." }],
    returnValue: { type: 'list', description: 'Items that pass the test.' }
  },
  reject: {
    category: 'Collection',
    documentation: 'Filters a sequence, dropping items where the test passes.',
    example: "{{ [1, 2, 3, 4] | reject('odd') | list }}",
    parameters: [{ name: 'test', type: 'string', description: 'Name of the test to apply.' }],
    returnValue: { type: 'list', description: 'Items that failed the test.' }
  },
  selectattr: {
    category: 'Collection',
    documentation: 'Filters a sequence of objects by applying a test to one of their attributes.',
    example: "{% for r in vars.input.records | selectattr('status', 'equalto', 'open') %}{{ r.name }}\n{% endfor %}",
    parameters: [
      { name: 'attribute', type: 'string', description: 'Attribute to inspect.' },
      { name: 'test', type: 'string', description: "Test name (e.g. 'equalto'). Optional." },
      { name: 'value', type: 'any', description: 'Value passed to the test. Optional.' }
    ],
    returnValue: { type: 'list', description: 'Matching objects.' }
  },
  rejectattr: {
    category: 'Collection',
    documentation: 'Filters a sequence of objects, dropping ones whose attribute passes the test.',
    example: "{% for r in vars.input.records | rejectattr('status', 'equalto', 'closed') %}{{ r.name }}\n{% endfor %}",
    parameters: [
      { name: 'attribute', type: 'string', description: 'Attribute to inspect.' },
      { name: 'test', type: 'string', description: 'Test name. Optional.' },
      { name: 'value', type: 'any', description: 'Value passed to the test. Optional.' }
    ],
    returnValue: { type: 'list', description: 'Objects that failed the test.' }
  },
  groupby: {
    category: 'Collection',
    documentation: 'Groups a sequence of objects by a shared attribute value.',
    example: "{% for status, records in vars.input.records | groupby('status') %}{{ status }}: {{ records | length }}\n{% endfor %}",
    parameters: [{ name: 'attribute', type: 'string', description: 'The attribute to group by.' }],
    returnValue: { type: 'list', description: 'List of (grouper, list) pairs.' }
  },
  batch: {
    category: 'Collection',
    documentation: 'Batches items into chunks of a fixed size.',
    example: "{% for chunk in vars.input.records | batch(3) %}{{ chunk | map(attribute='name') | join(', ') }}\n{% endfor %}",
    parameters: [
      { name: 'linecount', type: 'integer', description: 'Items per batch.' },
      { name: 'fill_with', type: 'any', description: 'Value used to pad the last batch. Optional.' }
    ],
    returnValue: { type: 'list', description: 'A list of batches.' }
  },
  slice: {
    category: 'Collection',
    documentation: 'Splits a sequence into a fixed number of slices.',
    example: "{% for col in vars.input.records | slice(2) %}{{ col | map(attribute='name') | join(', ') }}\n{% endfor %}",
    parameters: [
      { name: 'slices', type: 'integer', description: 'Number of slices to produce.' },
      { name: 'fill_with', type: 'any', description: 'Value used to pad short slices. Optional.' }
    ],
    returnValue: { type: 'list', description: 'A list of slices.' }
  },
  list: {
    category: 'Conversion',
    documentation: 'Converts a value to a list (useful after map/select/unique).',
    example: "{{ vars.input.records | map(attribute='name') | list }}",
    parameters: [],
    returnValue: { type: 'list', description: 'A materialised list.' }
  },
  min: {
    category: 'Collection',
    documentation: 'Returns the smallest item of a sequence.',
    example: "{{ vars.input.records | map(attribute='severity') | min }}",
    parameters: [
      { name: 'case_sensitive', type: 'boolean', description: 'Case-sensitive comparison. Optional.' },
      { name: 'attribute', type: 'string', description: 'Compare by this attribute. Optional.' }
    ],
    returnValue: { type: 'any', description: 'The smallest item.' }
  },
  max: {
    category: 'Collection',
    documentation: 'Returns the largest item of a sequence.',
    example: "{{ vars.input.records | map(attribute='severity') | max }}",
    parameters: [
      { name: 'case_sensitive', type: 'boolean', description: 'Case-sensitive comparison. Optional.' },
      { name: 'attribute', type: 'string', description: 'Compare by this attribute. Optional.' }
    ],
    returnValue: { type: 'any', description: 'The largest item.' }
  },
  sum: {
    category: 'Collection',
    documentation: 'Sums a sequence of numbers.',
    example: "Total: {{ vars.input.records | sum(attribute='count') }}",
    parameters: [
      { name: 'attribute', type: 'string', description: 'Sum this attribute when operating on objects. Optional.' },
      { name: 'start', type: 'number', description: 'Initial value. Optional (defaults to 0).' }
    ],
    returnValue: { type: 'number', description: 'The sum of the values.' }
  },
  random: {
    category: 'Collection',
    documentation: 'Picks a random element from a sequence.',
    example: '{{ vars.input.records | random }}',
    parameters: [],
    returnValue: { type: 'any', description: 'A random element.' }
  }
};

const numberFilters: Record<string, FilterSignature> = {
  abs: {
    category: 'Number',
    documentation: 'Returns the absolute value of a number.',
    example: '{{ vars.input.records[0].delta | abs }}',
    parameters: [],
    returnValue: { type: 'number', description: 'The absolute value.' }
  },
  round: {
    category: 'Number',
    documentation: 'Rounds a number to a given precision.',
    example: '{{ vars.input.records[0].score | round(2) }}',
    parameters: [
      { name: 'precision', type: 'integer', description: 'Number of decimal places. Optional.' },
      { name: 'method', type: 'string', description: "'common', 'ceil', or 'floor'. Optional." }
    ],
    returnValue: { type: 'number', description: 'The rounded number.' }
  },
  int: {
    category: 'Number',
    documentation: 'Converts a value to an integer, with a fallback default.',
    example: '{{ vars.input.records[0].count | int(0) }}',
    parameters: [
      { name: 'default', type: 'integer', description: 'Value returned when conversion fails. Optional.' },
      { name: 'base', type: 'integer', description: 'Numeric base for string inputs. Optional.' }
    ],
    returnValue: { type: 'integer', description: 'The integer value.' }
  },
  float: {
    category: 'Number',
    documentation: 'Converts a value to a float, with a fallback default.',
    example: '{{ vars.input.records[0].ratio | float(0.0) }}',
    parameters: [
      { name: 'default', type: 'number', description: 'Value returned when conversion fails. Optional.' }
    ],
    returnValue: { type: 'number', description: 'The float value.' }
  }
};

const valueFilters: Record<string, FilterSignature> = {
  default: {
    category: 'Value',
    documentation: 'Returns a default value if the variable is undefined or empty. Alias: d.',
    example: "{{ vars.input.records[0].name | default('Unknown') }}",
    parameters: [
      { name: 'default_value', type: 'any', description: 'Value returned when the input is missing.' },
      { name: 'boolean', type: 'boolean', description: 'If true, falsy values also use the default. Optional.' }
    ],
    returnValue: { type: 'any', description: 'The variable value or the default.' }
  },
  tojson: {
    category: 'Encoding',
    documentation: 'Serialises a value to JSON.',
    example: '{{ vars.input.records[0] | tojson(indent=2) }}',
    parameters: [
      { name: 'indent', type: 'integer', description: 'Indent level for pretty-printing. Optional.' }
    ],
    returnValue: { type: 'string', description: 'A JSON string.' }
  },
  pprint: {
    category: 'Encoding',
    documentation: 'Pretty-prints a value for debugging.',
    example: '{{ vars.input.records[0] | pprint }}',
    parameters: [],
    returnValue: { type: 'string', description: 'A human-readable representation.' }
  },
  attr: {
    category: 'Value',
    documentation: 'Returns the named attribute of an object (like obj.name but dynamic).',
    example: "{{ vars.input.records[0] | attr('name') }}",
    parameters: [{ name: 'name', type: 'string', description: 'The attribute name.' }],
    returnValue: { type: 'any', description: 'The attribute value.' }
  },
  items: {
    category: 'Collection',
    documentation: 'Yields (key, value) pairs of a dictionary for use in loops.',
    example: '{% for key, val in vars.input.records[0] | items %}{{ key }}: {{ val }}\n{% endfor %}',
    parameters: [],
    returnValue: { type: 'list', description: 'A list of [key, value] pairs.' }
  },
  dictsort: {
    category: 'Collection',
    documentation: 'Sorts a dictionary and yields (key, value) pairs.',
    example: '{% for key, val in vars.input.records[0] | dictsort %}{{ key }}: {{ val }}\n{% endfor %}',
    parameters: [
      { name: 'case_sensitive', type: 'boolean', description: 'Case-sensitive comparison. Optional.' },
      { name: 'by', type: 'string', description: "Sort by 'key' or 'value'. Optional." }
    ],
    returnValue: { type: 'list', description: 'A list of [key, value] pairs in order.' }
  }
};

export const filterSignatures: Record<string, FilterSignature> = {
  ...stringFilters,
  ...collectionFilters,
  ...numberFilters,
  ...valueFilters
};

export const filterCategoryOrder = [
  'String',
  'Collection',
  'Number',
  'Value',
  'Encoding',
  'Conversion',
  'Other'
];
