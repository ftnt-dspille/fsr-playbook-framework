/**
 * Reproduces the user-reported bug: clicking an example item should call
 * onLoad with the loaded YAML text. If this test fails, the bug is in the
 * menu component itself.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/svelte';
import ExamplesMenu from './ExamplesMenu.svelte';

describe('ExamplesMenu', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/examples')) {
        return new Response(
          JSON.stringify([
            { name: 'demo_one', filename: 'demo_one.yaml', preview: 'collection: One' },
            { name: 'demo_two', filename: 'demo_two.yaml', preview: 'collection: Two' }
          ]),
          { status: 200 }
        );
      }
      if (url.includes('/api/examples/demo_one')) {
        return new Response(
          JSON.stringify({ name: 'demo_one', text: 'collection: One\nplaybooks: []\n' }),
          { status: 200 }
        );
      }
      return new Response('not found', { status: 404 });
    }) as any;
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it('lists examples after mount and fires onLoad with file text on click', async () => {
    const onLoad = vi.fn();
    render(ExamplesMenu, { props: { onLoad } });

    // Open the menu
    fireEvent.click(screen.getByRole('button', { name: 'Examples ▾' }));

    // Wait for items to render
    const item = await screen.findByRole('button', { name: /demo_one/ });
    expect(item).toBeInTheDocument();

    // Click an item
    fireEvent.click(item);

    await waitFor(() => {
      expect(onLoad).toHaveBeenCalledTimes(1);
    });
    const [text, name] = onLoad.mock.calls[0];
    expect(name).toBe('demo_one');
    expect(text).toContain('collection: One');
  });

  it('still fires onLoad even if outside-click handler closes the menu first', async () => {
    const onLoad = vi.fn();
    render(ExamplesMenu, { props: { onLoad } });
    fireEvent.click(screen.getByRole('button', { name: 'Examples ▾' }));
    const item = await screen.findByRole('button', { name: /demo_one/ });
    fireEvent.click(item);
    await waitFor(() => expect(onLoad).toHaveBeenCalled());
  });
});
