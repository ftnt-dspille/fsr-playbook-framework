import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/svelte';
import FilterTreeEditor from './FilterTreeEditor.svelte';

afterEach(cleanup);

/** Field catalog for the `alerts` module — minimal but representative.
 * `assets` and `assignedTo` mimic the trained store's shape where the
 * relation's "type" column literally holds the target module's name. */
const ALERTS_FIELDS = [
  { name: 'name', title: 'Name', type: 'string', operators: ['eq', 'neq', 'like', 'isnull'] },
  { name: 'severity', title: 'Severity', type: 'picklists', operators: ['eq', 'neq', 'in', 'nin', 'isnull'] },
  { name: 'assets', title: 'Assets', type: 'assets', operators: ['eq', 'neq', 'in', 'nin', 'isnull'] },
  { name: 'assignedTo', title: 'Assigned To', type: 'people', operators: ['eq', 'neq', 'in', 'nin', 'isnull'] }
];

/** Field catalog for `assets` — used when the user drills into the
 * relation. `hostname` is a primitive; `ip` too. The numeric `port`
 * exists so we can assert the operator catalog narrows on drill-in. */
const ASSETS_FIELDS = [
  { name: 'hostname', title: 'Host name', type: 'string', operators: ['eq', 'neq', 'like', 'isnull'] },
  { name: 'ip', title: 'IP address', type: 'string', operators: ['eq', 'neq', 'like', 'isnull'] },
  { name: 'port', title: 'Port', type: 'integer', operators: ['eq', 'neq', 'lt', 'lte', 'gt', 'gte', 'isnull'] }
];

describe('FilterTreeEditor — related-module drill-in', () => {
  it('hides the sub-field picker until the user picks a relation field', () => {
    const onChange = vi.fn();
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'name', operator: 'eq', value: 'foo', type: 'primitive' }
        ]},
        onChange,
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => []
      }
    });
    // Primary picker exists — accessible name reflects the current
    // field (`name`) when one is selected.
    expect(screen.getByRole('button', { name: /^name/i }))
      .toBeTruthy();
    // No sub-field button yet — the leaf is on a primitive `name` field.
    expect(screen.queryByRole('button', { name: /assets field/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /people field/i })).toBeNull();
  });

  it('shows the "→ <relation> field…" button when a relation is picked', () => {
    const onChange = vi.fn();
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'assets', operator: 'eq', value: '', type: 'object' }
        ]},
        onChange,
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => ASSETS_FIELDS
      }
    });
    expect(screen.getByRole('button', { name: /assets field/i })).toBeTruthy();
  });

  it('calls getRelatedFields with the related module name', () => {
    const getRelated = vi.fn(() => ASSETS_FIELDS);
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'assets', operator: 'eq', value: '', type: 'object' }
        ]},
        onChange: vi.fn(),
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: getRelated
      }
    });
    // Initial render plus button render both consult the resolver.
    expect(getRelated).toHaveBeenCalled();
    expect(getRelated.mock.calls.some((args: unknown[]) => args[0] === 'assets')).toBe(true);
  });

  it('writes "<relation>.<subfield>" + narrows the operator catalog when the user drills in', async () => {
    const onChange = vi.fn();
    render(FilterTreeEditor, {
      props: {
        // Start with a relation picked but no sub-field, and an
        // operator (`eq`) that's valid for the relation but ALSO valid
        // for the integer `port` we'll drill into below.
        group: { logic: 'AND' as const, filters: [
          { field: 'assets', operator: 'eq', value: '', type: 'object' }
        ]},
        onChange,
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => ASSETS_FIELDS
      }
    });
    // Open the sub-field picker.
    await fireEvent.click(screen.getByRole('button', { name: /assets field/i }));
    const dialog = screen.getByRole('dialog', { name: /assets field picker/i });
    // Pick `hostname` (a string field).
    await fireEvent.click(within(dialog).getByRole('button', { name: /hostname/i }));

    expect(onChange).toHaveBeenCalled();
    const last = onChange.mock.calls.at(-1)![0];
    expect(last.filters[0].field).toBe('assets.hostname');
    // hostname is a string type → wire-level value type is `primitive`.
    expect(last.filters[0].type).toBe('primitive');
    // `eq` was valid for the relation AND for hostname → preserved.
    expect(last.filters[0].operator).toBe('eq');
  });

  it('snaps the operator to the first valid op when the prior op is invalid for the new sub-field', async () => {
    const onChange = vi.fn();
    render(FilterTreeEditor, {
      props: {
        // Relation has `like` in its operator list (custom catalog
        // pretending the user added it). `like` is NOT valid for the
        // integer `port` field we'll drill into.
        group: { logic: 'AND' as const, filters: [
          { field: 'assets', operator: 'like', value: '', type: 'object' }
        ]},
        onChange,
        fields: [
          ...ALERTS_FIELDS.filter((x) => x.name !== 'assets'),
          { name: 'assets', title: 'Assets', type: 'assets',
            operators: ['eq', 'neq', 'like', 'isnull'] }
        ],
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => ASSETS_FIELDS
      }
    });
    await fireEvent.click(screen.getByRole('button', { name: /assets field/i }));
    const dialog = screen.getByRole('dialog', { name: /assets field picker/i });
    await fireEvent.click(within(dialog).getByRole('button', { name: /\bport\b/i }));

    const last = onChange.mock.calls.at(-1)![0];
    expect(last.filters[0].field).toBe('assets.port');
    // `port`'s operator catalog doesn't contain `like` — should snap
    // to the first valid operator (eq).
    expect(last.filters[0].operator).toBe('eq');
  });

  it('treats fields whose `type` is a known module as relations (sorts them under "Related modules")', async () => {
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: '', operator: 'eq', value: '', type: 'primitive' }
        ]},
        onChange: vi.fn(),
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => []
      }
    });
    // Open the primary picker.
    await fireEvent.click(screen.getByRole('button', { name: /pick field/i }));
    const dialog = screen.getByRole('dialog', { name: /^field picker$/i });
    expect(within(dialog).getByText(/related modules/i)).toBeTruthy();
    // Both relation fields should be selectable as buttons (the row
    // also shows the related module name as the type column, which is
    // why a plain text search would match twice).
    expect(within(dialog).getByRole('button', { name: /assets/i })).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: /assignedTo/i })).toBeTruthy();
  });

  it('auto-scopes a group when every leaf shares a relation prefix', () => {
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'assets.hostname', operator: 'like', value: 'prod', type: 'primitive' },
          { field: 'assets.ip', operator: 'eq', value: '10.1.1.1', type: 'primitive' },
        ]},
        onChange: vi.fn(),
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => ASSETS_FIELDS
      }
    });
    // The relation chip surfaces in the group header.
    expect(screen.getByText('assets', { selector: 'code' })).toBeTruthy();
    // Primary picker is suppressed for both rows since they're
    // implicitly scoped — only the sub-field picker remains.
    expect(screen.queryAllByRole('button', { name: /^assets$/ })).toHaveLength(0);
    // Sub-field pickers ARE present for each leaf — labels show the
    // already-picked sub-fields.
    expect(screen.getByRole('button', { name: /hostname/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^ip/i })).toBeTruthy();
  });

  it('does not auto-scope when leaves mix different relations', () => {
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'assets.hostname', operator: 'eq', value: 'foo', type: 'primitive' },
          { field: 'assignedTo.name', operator: 'eq', value: 'me', type: 'primitive' },
        ]},
        onChange: vi.fn(),
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => []
      }
    });
    // No relation chip — heterogeneous prefixes.
    const groupHeaders = screen.queryAllByText('assets', { selector: 'code' });
    expect(groupHeaders).toHaveLength(0);
  });

  it('"+ condition" pre-seeds the relation prefix when scope is inferred', async () => {
    const onChange = vi.fn();
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'assets.hostname', operator: 'eq', value: 'foo', type: 'primitive' },
        ]},
        onChange,
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => ASSETS_FIELDS
      }
    });
    await fireEvent.click(screen.getByRole('button', { name: '+ condition' }));
    const last = onChange.mock.calls.at(-1)![0];
    // The new leaf should arrive with the relation prefix already
    // baked in so the user only has to pick the sub-field.
    expect(last.filters[1].field).toBe('assets.');
  });

  it('"+ condition" leaves field empty when no relation scope is inferred', async () => {
    const onChange = vi.fn();
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'name', operator: 'eq', value: 'foo', type: 'primitive' },
        ]},
        onChange,
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        getRelatedFields: () => []
      }
    });
    await fireEvent.click(screen.getByRole('button', { name: '+ condition' }));
    const last = onChange.mock.calls.at(-1)![0];
    expect(last.filters[1].field).toBe('');
  });

  it('does not infer scope when the prefix is unknown to the module catalog', () => {
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: 'foo.bar', operator: 'eq', value: 'baz', type: 'primitive' },
        ]},
        onChange: vi.fn(),
        fields: ALERTS_FIELDS,
        // `foo` is NOT in moduleNames, so even though every leaf
        // shares the `foo.` prefix it isn't a real relation.
        moduleNames: ['alerts', 'assets'],
        getRelatedFields: () => []
      }
    });
    expect(screen.queryByText('foo', { selector: 'code' })).toBeNull();
  });

  it('hides relations entirely when allowRelatedModules=false', async () => {
    render(FilterTreeEditor, {
      props: {
        group: { logic: 'AND' as const, filters: [
          { field: '', operator: 'eq', value: '', type: 'primitive' }
        ]},
        onChange: vi.fn(),
        fields: ALERTS_FIELDS,
        moduleNames: ['alerts', 'assets', 'people'],
        allowRelatedModules: false,
        getRelatedFields: () => []
      }
    });
    await fireEvent.click(screen.getByRole('button', { name: /pick field/i }));
    const dialog = screen.getByRole('dialog', { name: /^field picker$/i });
    expect(within(dialog).queryByText(/related modules/i)).toBeNull();
    // Plain `name` is still shown — the picker isn't empty.
    expect(within(dialog).getByText('name')).toBeTruthy();
  });
});
