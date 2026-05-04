/**
 * End-to-end-ish: ExamplesMenu click → onLoad → state assignment →
 * MonacoYaml's value prop updates → Monaco's setValue called.
 *
 * Uses the monaco-editor stub aliased in vitest.config.ts. We instrument
 * `editor.create` once at module load to record every setValue.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/svelte';
import * as monaco from 'monaco-editor';

const setValueSpy = vi.fn();
const valueByEditor: { current: string } = { current: '' };

const realCreate = monaco.editor.create;
(monaco.editor as any).create = (host: HTMLElement, opts: { value?: string }) => {
  const inst = realCreate(host, opts);
  valueByEditor.current = opts?.value ?? '';
  const realSet = inst.setValue.bind(inst);
  inst.setValue = (v: string) => {
    valueByEditor.current = v;
    setValueSpy(v);
    realSet(v);
  };
  inst.getValue = () => valueByEditor.current;
  return inst;
};

describe('Examples → editor wiring', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    setValueSpy.mockClear();
    valueByEditor.current = '';
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/examples')) {
        return new Response(
          JSON.stringify([
            { name: 'fixture_a', filename: 'fixture_a.yaml', preview: 'collection: A' }
          ]),
          { status: 200 }
        );
      }
      if (url.includes('/api/examples/fixture_a')) {
        return new Response(
          JSON.stringify({ name: 'fixture_a', text: 'collection: A\nplaybooks: []\n' }),
          { status: 200 }
        );
      }
      return new Response('nope', { status: 404 });
    }) as any;
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it('clicking an example pushes its YAML into the Monaco editor', async () => {
    const Harness = (await import('./__test_harness/EditorWiring.svelte')).default;
    render(Harness);

    expect(screen.getByTestId('yaml-mirror').textContent).toBe('initial');

    fireEvent.click(screen.getByRole('button', { name: 'Examples ▾' }));
    const item = await screen.findByRole('button', { name: /fixture_a/ });
    fireEvent.click(item);

    await waitFor(() => {
      expect(screen.getByTestId('yaml-mirror').textContent).toContain('collection: A');
    });
    await waitFor(() => {
      expect(setValueSpy).toHaveBeenCalledWith(expect.stringContaining('collection: A'));
    });
    expect(valueByEditor.current).toBe('collection: A\nplaybooks: []\n');
  });
});
