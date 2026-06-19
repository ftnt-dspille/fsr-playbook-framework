/**
 * Coverage for the consolidated drawer surface. Pins:
 *  - Tab buttons are Issues + Deploy only (no Diagnostics/Fixes/Compile/Debug).
 *  - Legacy tab ids ('fixes', 'compile') reroute to Issues so any
 *    leftover callers don't render an empty pane.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import DiagnosticsDrawer from './DiagnosticsDrawer.svelte';
import { playbookActions } from '../playbookActions.svelte';

function baseProps(over: Partial<Record<string, any>> = {}) {
  return {
    open: true,
    tab: 'diagnostics' as any,
    heightPx: 300,
    onTabChange: () => {},
    onToggle: () => {},
    onResize: () => {},
    ...over
  };
}

beforeEach(() => {
  cleanup();
  playbookActions.state.markers = [];
  playbookActions.state.fixes = [];
  playbookActions.state.diagnostics = [];
});

describe('DiagnosticsDrawer', () => {
  it('renders exactly two tabs: Issues and Deploy', () => {
    render(DiagnosticsDrawer, { props: baseProps() });
    expect(screen.getByRole('button', { name: /Issues/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Deploy/ })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Diagnostics$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Fixes/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Compile/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Step Debugger/ })).toBeNull();
  });

  it('legacy tab="fixes" reroutes to the Issues panel (empty state)', () => {
    render(DiagnosticsDrawer, { props: baseProps({ tab: 'fixes' }) });
    expect(screen.getByText('No issues')).toBeTruthy();
  });

  it('legacy tab="compile" reroutes to the Issues panel (empty state)', () => {
    render(DiagnosticsDrawer, { props: baseProps({ tab: 'compile' }) });
    expect(screen.getByText('No issues')).toBeTruthy();
  });

  it('section headers only appear when both sections have content', () => {
    // Markers only → no headers.
    playbookActions.state.markers = [
      { line: 1, col: 1, severity: 'error', code: 'E1', message: 'm', path: 'p', suggestion: null }
    ];
    const { unmount } = render(DiagnosticsDrawer, { props: baseProps() });
    expect(screen.queryByText('Syntax')).toBeNull();
    expect(screen.queryByText('Data flow')).toBeNull();
    unmount();

    // Both present → both headers appear.
    playbookActions.state.diagnostics = [
      { kind: 'k', severity: 'error', step_id: 's', message: 'df' } as any
    ];
    render(DiagnosticsDrawer, { props: baseProps() });
    expect(screen.getByText('Syntax')).toBeTruthy();
    expect(screen.getByText('Data flow')).toBeTruthy();
  });

  it('shows an error count badge on the Issues tab', () => {
    playbookActions.state.markers = [
      { line: 1, col: 1, severity: 'error', code: 'E1', message: 'boom', path: 'p', suggestion: null }
    ];
    render(DiagnosticsDrawer, { props: baseProps() });
    expect(screen.getByText('1')).toBeTruthy();
  });
});
