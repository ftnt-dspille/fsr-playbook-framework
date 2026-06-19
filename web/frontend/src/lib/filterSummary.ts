/**
 * Deterministic English summarizer for FSR filter trees.
 *
 * The filter shape is the same nested AND/OR tree the FSR query API
 * uses (see `store/QUERY_API.md` §2.2). We turn it into one short
 * sentence the user can read at a glance — "on create of high-severity
 * phishing alerts that aren't escalated" instead of dumping the JSON.
 *
 * No LLM. Same code path will later feed the AI step builder so the
 * model can read existing filters in plain English.
 */

type Leaf = {
  field: string;
  operator: string;
  value: unknown;
  type?: string;
  _value?: { display?: string; itemValue?: string } | string | null;
};
type Group = { logic: 'AND' | 'OR'; filters: (Leaf | Group)[] };

function isGroup(f: Leaf | Group): f is Group {
  return (f as Group).logic !== undefined;
}

/** Operator → English connector. Picked so each leaf reads naturally
 * inline without "field operator value" (e.g. "Severity is High"
 * instead of "Severity eq High"). */
const OP_ENGLISH: Record<string, string> = {
  eq: 'is',
  neq: 'is not',
  lt: '<',
  lte: '≤',
  gt: '>',
  gte: '≥',
  in: 'is one of',
  nin: 'is not one of',
  like: 'contains',
  notlike: 'does not contain',
  contains: 'contains',
  exists: 'has',
  isnull: 'is empty',
  changed: 'changes',
  in_all: 'matches all of'
};

/** Pull a human-readable label out of a leaf's value. The FSR designer
 * stores the picklist display + itemValue alongside the raw IRI under
 * `_value`; prefer that, fall back to the literal value, then to
 * stringifying whatever is there. */
function valueLabel(leaf: Leaf): string {
  const v = leaf.value;
  const hint = leaf._value;
  if (hint && typeof hint === 'object' && hint !== null) {
    const display = (hint as { display?: string }).display;
    const item = (hint as { itemValue?: string }).itemValue;
    if (item && item.trim()) return item;
    if (display && display.trim()) return display;
  }
  if (typeof v === 'string') {
    // Strip Jinja braces for readability — the user knows it's a
    // template binding when they wrote it.
    const t = v.trim();
    if (/^\{\{.*\}\}$/.test(t)) return t.replace(/^\{\{\s*|\s*\}\}$/g, '');
    return v;
  }
  if (Array.isArray(v)) return v.map(String).join(', ');
  if (v == null) return '';
  return JSON.stringify(v);
}

/** Convert "fieldName" / "field_name" → "field name" for prose.
 * Dotted relation paths (`assets.hostname`) read better as
 * "assets's hostname" than "assets hostname". */
function humanizeField(f: string): string {
  if (!f) return '<field>';
  if (f.includes('.')) {
    const [root, ...rest] = f.split('.');
    return `${humanizeField(root)}'s ${humanizeField(rest.join('.'))}`;
  }
  return f
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .toLowerCase();
}

function leafSentence(leaf: Leaf): string {
  const field = humanizeField(leaf.field);
  const op = OP_ENGLISH[leaf.operator] ?? leaf.operator;
  if (leaf.operator === 'isnull') {
    const v = String(leaf.value).toLowerCase();
    // isnull:true → "is empty"; isnull:false → "is not empty"
    return v === 'false' ? `${field} is not empty` : `${field} is empty`;
  }
  if (leaf.operator === 'exists') return `${field} exists`;
  if (leaf.operator === 'changed') return `${field} changes`;
  return `${field} ${op} ${valueLabel(leaf)}`.trim();
}

function groupSentence(group: Group, depth: number): string {
  if (!group.filters.length) return '';
  const conn = group.logic === 'OR' ? ' or ' : ' and ';
  const parts = group.filters.map((f) =>
    isGroup(f) ? `(${groupSentence(f, depth + 1)})` : leafSentence(f)
  ).filter((s) => s.length > 0);
  return parts.join(conn);
}

/** Public: render the trigger summary in plain English. */
export function summarizeTrigger(
  triggerType: string,
  module: string | null,
  group: Group | null
): string {
  const mod = module && module.trim() ? module.trim() : 'records';
  const verb = (() => {
    switch (triggerType) {
      case 'start_on_create': return 'On create of';
      case 'start_on_update': return 'On update of';
      case 'manual_action':   return 'When an analyst runs an action on';
      case 'api_call':        return 'When the API endpoint is called for';
      case 'start':           return 'On manual run against';
      default:                return 'On';
    }
  })();
  const body = group ? groupSentence(group, 0) : '';
  if (!body) return `${verb} all ${mod}.`;
  return `${verb} ${mod} where ${body}.`;
}

/** Public: summarize a find_record query. */
export function summarizeFind(module: string | null, group: Group | null): string {
  const mod = module && module.trim() ? module.trim() : 'records';
  const body = group ? groupSentence(group, 0) : '';
  if (!body) return `Find all ${mod}.`;
  return `Find ${mod} where ${body}.`;
}
