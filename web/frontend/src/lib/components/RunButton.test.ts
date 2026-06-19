/**
 * Coverage for the Run split-button's menu positioning. Pins the
 * regressions surfaced in the editor:
 *   - menu uses `position: fixed` so an `overflow-hidden` ancestor
 *     (editor toolbar / build bar) can't clip it.
 *   - left coord stays inside the viewport even when the caret button
 *     is flush against either edge.
 *   - menu's top sits flush against the caret's bottom (no gap).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import RunButton from './RunButton.svelte';

beforeEach(() => {
  cleanup();
  try { localStorage.removeItem('fsrpb.run.last'); } catch {}
});

afterEach(() => {
  vi.restoreAllMocks();
});

function stubCaretRect(rect: Partial<DOMRect>): void {
  const full: DOMRect = {
    x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0,
    width: 0, height: 0, toJSON: () => ({}),
    ...rect,
  } as DOMRect;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(full);
}

async function openMenu(): Promise<HTMLElement> {
  const caret = screen.getByRole('button', { name: 'Run options' });
  await fireEvent.click(caret);
  return screen.getByRole('menu');
}

const MENU_WIDTH = 256;
const VIEWPORT_W = 1280;

describe('RunButton menu positioning', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', {
      configurable: true, value: VIEWPORT_W,
    });
  });

  it('uses fixed positioning so an overflow-hidden parent cannot clip it', async () => {
    stubCaretRect({ right: 800, bottom: 40 });
    render(RunButton, { props: {} });
    const menu = await openMenu();
    // Tailwind utilities aren't compiled in jsdom, so we assert the
    // class is present rather than the resolved computed style.
    expect(menu.className.split(/\s+/)).toContain('fixed');
  });

  it('right-aligns the menu to the caret button when there is room', async () => {
    stubCaretRect({ right: 800, bottom: 40 });
    render(RunButton, { props: {} });
    const menu = await openMenu();
    // left = caret.right - MENU_WIDTH = 800 - 256 = 544
    expect(menu.style.left).toBe('544px');
  });

  it('clamps the left coord so the menu does not run off the LEFT edge', async () => {
    // Caret near the left edge of a narrow pane — `caret.right - width`
    // would be negative without the floor.
    stubCaretRect({ right: 120, bottom: 40 });
    render(RunButton, { props: {} });
    const menu = await openMenu();
    expect(parseInt(menu.style.left, 10)).toBeGreaterThanOrEqual(4);
  });

  it('clamps the left coord so the menu does not run off the RIGHT edge', async () => {
    // Caret flush against the viewport right — clamp to keep a 4px gutter.
    stubCaretRect({ right: VIEWPORT_W + 50, bottom: 40 });
    render(RunButton, { props: {} });
    const menu = await openMenu();
    const left = parseInt(menu.style.left, 10);
    expect(left + MENU_WIDTH).toBeLessThanOrEqual(VIEWPORT_W - 4 + 1); // +1 slack
  });

  it('places the menu flush against the caret bottom (no gap)', async () => {
    stubCaretRect({ right: 800, bottom: 42 });
    render(RunButton, { props: {} });
    const menu = await openMenu();
    expect(menu.style.top).toBe('42px');
  });

  it('renders all four run variants in the menu', async () => {
    stubCaretRect({ right: 800, bottom: 40 });
    render(RunButton, { props: {} });
    await openMenu();
    expect(screen.getByRole('menuitem', { name: /Push only/ })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: /Push & Run/ })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: /Mock run/ })).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: /Live run/ })).toBeTruthy();
  });

  it('portals the open menu directly into <body> (escapes flex stacking)', async () => {
    // Regression: the inactive-playbook banner lives inside the same
    // <main class="relative"> as the toolbar, so a menu rendered inline
    // ends up under the banner. Portaling to <body> takes the menu out
    // of every ancestor's stacking context.
    stubCaretRect({ right: 800, bottom: 40 });
    const { container } = render(RunButton, { props: {} });
    const menu = await openMenu();
    // The menu's nearest portal host should be a direct child of <body>,
    // NOT inside the component's render container.
    expect(container.contains(menu)).toBe(false);
    let cursor: HTMLElement | null = menu;
    while (cursor && cursor.parentElement !== document.body) {
      cursor = cursor.parentElement;
    }
    expect(cursor?.parentElement).toBe(document.body);
  });

  it('removes the portaled menu from <body> when closed', async () => {
    stubCaretRect({ right: 800, bottom: 40 });
    render(RunButton, { props: {} });
    const caret = screen.getByRole('button', { name: 'Run options' });
    await fireEvent.click(caret);
    const beforeBodyChildren = document.body.children.length;
    await fireEvent.click(caret);
    expect(document.body.children.length).toBeLessThan(beforeBodyChildren);
  });

  it('toggles closed when the caret is clicked again', async () => {
    stubCaretRect({ right: 800, bottom: 40 });
    render(RunButton, { props: {} });
    const caret = screen.getByRole('button', { name: 'Run options' });
    await fireEvent.click(caret);
    expect(screen.queryByRole('menu')).not.toBeNull();
    await fireEvent.click(caret);
    expect(screen.queryByRole('menu')).toBeNull();
  });
});
