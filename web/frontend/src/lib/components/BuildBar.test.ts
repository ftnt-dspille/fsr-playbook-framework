/**
 * Coverage for the consolidated CLI action bar. Pins:
 *  - No Validate / Compile / Verify buttons (all auto-run or removed).
 *  - The ⋯ overflow exposes Re-validate / Re-analyze as escape valves.
 *  - The err/warn chip opens the drawer when there's something to see.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import BuildBar from './BuildBar.svelte';
import { playbookActions } from '../playbookActions.svelte';

beforeEach(() => {
  cleanup();
  playbookActions.state.markers = [];
  playbookActions.state.fixes = [];
  playbookActions.state.diagnostics = [];
  playbookActions.state.verify = null;
});

describe('BuildBar', () => {
  it('does not render Validate / Compile / Verify buttons', () => {
    render(BuildBar, { props: {} });
    expect(screen.queryByRole('button', { name: 'Validate' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Compile' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Verify' })).toBeNull();
  });

  it('does not render the standalone verify ✓ / ✗ pill', () => {
    playbookActions.state.verify = {
      ready_to_push: true,
      required_fixes: [],
      warnings: [],
      evidence: {}
    } as any;
    render(BuildBar, { props: {} });
    expect(screen.queryByText('verify ✓')).toBeNull();
  });

  it('overflow menu Re-validate calls playbookActions.validate', async () => {
    const spy = vi.spyOn(playbookActions, 'validate').mockResolvedValue();
    render(BuildBar, { props: {} });
    await fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Re-validate' }));
    expect(spy).toHaveBeenCalledOnce();
    spy.mockRestore();
  });

  it('overflow menu Re-analyze calls playbookActions.analyze', async () => {
    const spy = vi.spyOn(playbookActions, 'analyze').mockResolvedValue();
    render(BuildBar, { props: {} });
    await fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: /Re-analyze/ }));
    expect(spy).toHaveBeenCalledOnce();
    spy.mockRestore();
  });

  it('overflow menu Re-verify calls playbookActions.runVerify', async () => {
    const spy = vi.spyOn(playbookActions, 'runVerify').mockResolvedValue();
    render(BuildBar, { props: {} });
    await fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: /Re-verify/ }));
    expect(spy).toHaveBeenCalledOnce();
    spy.mockRestore();
  });

  it('err/warn chip opens the drawer when issues are present', async () => {
    playbookActions.state.markers = [
      { line: 1, col: 1, severity: 'error', code: 'E1', message: 'x', path: 'p', suggestion: null }
    ];
    const onShowDrawer = vi.fn();
    render(BuildBar, { props: { onShowDrawer } });
    const chip = screen.getByTitle('Open issues drawer');
    await fireEvent.click(chip);
    expect(onShowDrawer).toHaveBeenCalledWith('diagnostics');
  });
});
