/**
 * Coverage for the merged Issues view (markers + auto-fixable warnings).
 * Pins the consolidation that replaced the separate Fixes tab: when a
 * Fix lines up with a Marker (line + code) the Apply button appears on
 * that row; unmatched Fixes get their own row at the end.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import DiagnosticsList from './DiagnosticsList.svelte';
import type { Marker, Fix } from '../api';

function marker(over: Partial<Marker> = {}): Marker {
  return {
    line: 5,
    col: 1,
    severity: 'warning',
    code: 'W001',
    message: 'bare yes',
    path: 'playbooks[0].steps[0]',
    suggestion: null,
    ...over
  };
}

function fix(over: Partial<Fix> = {}): Fix {
  return {
    line: 5,
    col: 1,
    end_line: 5,
    end_col: 10,
    original: 'next: yes',
    replacement: 'next: "yes"',
    code: 'W001',
    message: 'quote yes',
    severity: 'warning',
    ...over
  };
}

function mockEditor() {
  const executeEdits = vi.fn();
  const editor = {
    executeEdits,
    pushUndoStop: vi.fn(),
    getValue: () => 'new-yaml',
    revealRangeInCenter: vi.fn(),
    setSelection: vi.fn(),
    focus: vi.fn()
  };
  class Range {
    constructor(public sl: number, public sc: number, public el: number, public ec: number) {}
  }
  return { editor, monaco: { Range }, executeEdits };
}

beforeEach(() => cleanup());

describe('DiagnosticsList', () => {
  it('shows the clean empty state when no markers or fixes', () => {
    render(DiagnosticsList, { props: { markers: [] } });
    expect(screen.getByText('No diagnostics')).toBeTruthy();
  });

  it('renders one row per marker', () => {
    render(DiagnosticsList, {
      props: { markers: [marker(), marker({ line: 7, code: 'W002', message: 'em-dash' })] }
    });
    expect(screen.getByText('bare yes')).toBeTruthy();
    expect(screen.getByText('em-dash')).toBeTruthy();
  });

  it('inlines an Apply button on a marker when a matching fix exists', async () => {
    const { editor, monaco, executeEdits } = mockEditor();
    const onApplied = vi.fn();
    render(DiagnosticsList, {
      props: { markers: [marker()], fixes: [fix()], editor, monaco, onApplied }
    });
    const apply = screen.getByRole('button', { name: 'Apply' });
    await fireEvent.click(apply);
    expect(executeEdits).toHaveBeenCalledOnce();
    expect(onApplied).toHaveBeenCalledWith('new-yaml');
  });

  it('appends unmatched fixes as their own rows', () => {
    const { editor, monaco } = mockEditor();
    render(DiagnosticsList, {
      props: {
        markers: [marker()],
        fixes: [fix(), fix({ line: 20, code: 'W099', message: 'orphan fix' })],
        editor,
        monaco
      }
    });
    // Orphan fix should appear as a "fix" row below the matched marker.
    expect(screen.getByText('orphan fix')).toBeTruthy();
  });

  it('disables Apply when no editor refs are passed (Design mode)', () => {
    render(DiagnosticsList, { props: { markers: [marker()], fixes: [fix()] } });
    const apply = screen.getByRole('button', { name: 'Apply' }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
  });

  it('"Fix all" appears with >1 fixes and applies bottom-up', async () => {
    const { editor, monaco, executeEdits } = mockEditor();
    render(DiagnosticsList, {
      props: {
        markers: [],
        fixes: [
          fix({ line: 3, code: 'A' }),
          fix({ line: 9, code: 'B' })
        ],
        editor,
        monaco
      }
    });
    const all = screen.getByRole('button', { name: 'Fix all' });
    await fireEvent.click(all);
    expect(executeEdits).toHaveBeenCalledOnce();
    // Operations should be sorted line-desc (9 then 3) so earlier offsets
    // remain valid as later edits land.
    const [, ops] = executeEdits.mock.calls[0];
    expect((ops as any[]).map((o) => o.range.sl)).toEqual([9, 3]);
  });
});
