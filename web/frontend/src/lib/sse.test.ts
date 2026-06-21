import { describe, it, expect, vi } from 'vitest';
import { postSse } from './sse';

function mockFetchResponse(chunks: string[]): typeof fetch {
  return vi.fn(async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const c of chunks) controller.enqueue(encoder.encode(c));
        controller.close();
      }
    });
    return new Response(stream, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' }
    });
  }) as any;
}

describe('postSse', () => {
  it('parses crlf-delimited frames split across chunks', async () => {
    globalThis.fetch = mockFetchResponse([
      'event: text\r\ndata: {"text":"a"}\r\n\r\nevent: t',
      'ext\r\ndata: {"text":"b"}\r\n\r\n',
      'event: done\r\ndata: {"stop_reason":"end_turn"}\r\n\r\n'
    ]);

    const got: { event: string; data: string }[] = [];
    for await (const f of postSse('/api/chat', {})) got.push(f);

    expect(got.map((f) => f.event)).toEqual(['text', 'text', 'done']);
    expect(JSON.parse(got[1].data)).toEqual({ text: 'b' });
  });

  it('throws on non-2xx', async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 500 })) as any;
    await expect(async () => {
      for await (const _ of postSse('/api/chat', {})) {
        // unreachable
      }
    }).rejects.toThrow();
  });
});
