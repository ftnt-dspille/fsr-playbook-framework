/**
 * Render an FSR record-field value as a human-readable string for the
 * variable picker / sample preview.
 *
 * FSR stores picklist values (severity, status, type, …) as objects of
 * shape `{ "@id": …, "@type": "Picklist", "itemValue": "High", "value": "High" }`.
 * Display the `itemValue` (the user-visible label), not the raw JSON.
 *
 * For lookup/relation fields (objects with `@id` referencing another
 * record), show the IRI tail as a stable identifier.
 */
export function formatFsrValue(v: unknown): string {
  if (v === null || v === undefined) return String(v);
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (Array.isArray(v)) {
    if (v.length === 0) return '[]';
    return `[${v.length} × ${formatFsrValue(v[0])}]`;
  }
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>;
    // Picklist: pull the display label.
    if (typeof o.itemValue === 'string' && o.itemValue) return o.itemValue;
    // Linked record / lookup: show the IRI's last segment.
    if (typeof o['@id'] === 'string' && o['@id'].startsWith('/api/')) {
      const tail = (o['@id'] as string).split('/').filter(Boolean).pop();
      return tail ?? String(o['@id']);
    }
    // Small generic object — fall through to JSON.
    try { return JSON.stringify(o); } catch { return '<object>'; }
  }
  return String(v);
}

/** Truncate at `max` chars, with an ellipsis. */
export function truncate(s: string, max = 40): string {
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}
