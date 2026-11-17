import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { varPaneStore, type VarPaneTarget } from './varPaneStore.svelte';

function target(id: string, insert: (s: string) => void = () => {}): VarPaneTarget {
  return { id, label: id, insert };
}

beforeEach(() => varPaneStore.close());
afterEach(() => vi.useRealTimers());

describe('varPaneStore', () => {
  it('starts closed with no target', () => {
    expect(varPaneStore.open).toBe(false);
    expect(varPaneStore.target).toBeNull();
  });

  it('focusField opens the pane and sets the target', () => {
    const t = target('a');
    varPaneStore.focusField(t);
    expect(varPaneStore.open).toBe(true);
    expect(varPaneStore.target?.id).toBe('a');
  });

  it('toggle on the same target closes; toggle on a new target swaps', () => {
    const a = target('a');
    const b = target('b');
    varPaneStore.toggle(a);
    expect(varPaneStore.target?.id).toBe('a');
    varPaneStore.toggle(a); // same → close
    expect(varPaneStore.open).toBe(false);
    expect(varPaneStore.target).toBeNull();
    varPaneStore.toggle(b);
    expect(varPaneStore.target?.id).toBe('b');
  });

  it('insert delegates to the active target', () => {
    const spy = vi.fn();
    varPaneStore.focusField(target('a', spy));
    varPaneStore.insert('{{ vars.x }}');
    expect(spy).toHaveBeenCalledExactlyOnceWith('{{ vars.x }}');
  });

  it('insert is a no-op when no target is focused', () => {
    expect(() => varPaneStore.insert('{{ vars.x }}')).not.toThrow();
  });

  it('blurField closes the pane after the grace window', () => {
    vi.useFakeTimers();
    varPaneStore.focusField(target('a'));
    varPaneStore.blurField('a');
    expect(varPaneStore.open).toBe(true); // still open inside grace
    vi.advanceTimersByTime(160);
    expect(varPaneStore.open).toBe(false);
    expect(varPaneStore.target).toBeNull();
  });

  it('focusField cancels a pending blur close (tab-between-fields case)', () => {
    vi.useFakeTimers();
    varPaneStore.focusField(target('a'));
    varPaneStore.blurField('a');
    varPaneStore.focusField(target('b')); // refocus before grace expires
    vi.advanceTimersByTime(500);
    expect(varPaneStore.open).toBe(true);
    expect(varPaneStore.target?.id).toBe('b');
  });

  it('blurField after target was already swapped is a no-op', () => {
    vi.useFakeTimers();
    varPaneStore.focusField(target('a'));
    varPaneStore.focusField(target('b')); // swap to b
    varPaneStore.blurField('a');           // stale blur for a
    vi.advanceTimersByTime(500);
    expect(varPaneStore.open).toBe(true);
    expect(varPaneStore.target?.id).toBe('b');
  });

  it('close clears state and cancels any pending blur', () => {
    vi.useFakeTimers();
    varPaneStore.focusField(target('a'));
    varPaneStore.blurField('a');
    varPaneStore.close();
    expect(varPaneStore.open).toBe(false);
    expect(varPaneStore.target).toBeNull();
    vi.advanceTimersByTime(500);
    expect(varPaneStore.open).toBe(false); // still closed; grace fired against null
  });
});
