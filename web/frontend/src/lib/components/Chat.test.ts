/**
 * Reproduces the "chat sends but nothing renders" bug: streamed text
 * deltas applied to a captured object reference instead of the
 * proxy-wrapped array entry. If we regress, this test fails.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/svelte';
import Chat from './Chat.svelte';

function makeSseStream(frames: string[]): typeof fetch {
  return vi.fn(async (input: any) => {
    const url = typeof input === 'string' ? input : (input?.url ?? '');
    // The component pre-flights the LLM provider on mount. Without a
    // green health response the composer stays disabled and the
    // streamed reply never gets a chance to render. Stub it out here.
    if (url.includes('/api/llm/health')) {
      return new Response(
        JSON.stringify({ ok: true, active: 'anthropic', note: 'test stub' }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    }
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        for (const f of frames) {
          controller.enqueue(encoder.encode(f));
          await new Promise((r) => setTimeout(r, 0));
        }
        controller.close();
      }
    });
    return new Response(stream, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' }
    });
  }) as any;
}

describe('Chat', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it('renders streamed assistant text into the conversation pane', async () => {
    globalThis.fetch = makeSseStream([
      'event: text\r\ndata: {"text":"Hello "}\r\n\r\n',
      'event: text\r\ndata: {"text":"world."}\r\n\r\n',
      'event: done\r\ndata: {"stop_reason":"end_turn"}\r\n\r\n'
    ]);

    render(Chat, { props: { currentYaml: '', onYamlReplace: () => {} } });

    const textarea = screen.getByPlaceholderText(/Ask the model/i);
    await fireEvent.input(textarea, { target: { value: 'hi' } });
    // Send is gated on input.trim() AND the LLM health pre-flight
    // resolving green. Wait until both are satisfied.
    await waitFor(() => {
      const b = screen.getByRole('button', { name: /Send/ }) as HTMLButtonElement;
      if (b.disabled) throw new Error('send still disabled');
    });
    await fireEvent.click(screen.getByRole('button', { name: /Send/ }));

    await waitFor(() => {
      expect(screen.getByText(/Hello world\./)).toBeInTheDocument();
    });
  });

  it('replaces the editor when assistant emits a yaml fence', async () => {
    globalThis.fetch = makeSseStream([
      'event: text\r\ndata: {"text":"Done. "}\r\n\r\n',
      'event: text\r\ndata: {"text":"```yaml\\ncollection: X\\n```"}\r\n\r\n',
      'event: done\r\ndata: {"stop_reason":"end_turn"}\r\n\r\n'
    ]);

    let captured: string | null = null;
    render(Chat, {
      props: {
        currentYaml: '',
        onYamlReplace: (y: string) => {
          captured = y;
        }
      }
    });

    const textarea = screen.getByPlaceholderText(/Ask the model/i);
    await fireEvent.input(textarea, { target: { value: 'build me x' } });
    await waitFor(() => {
      const b = screen.getByRole('button', { name: /Send/ }) as HTMLButtonElement;
      if (b.disabled) throw new Error('send still disabled');
    });
    await fireEvent.click(screen.getByRole('button', { name: /Send/ }));

    await waitFor(() => expect(captured).toContain('collection: X'));
  });
});
