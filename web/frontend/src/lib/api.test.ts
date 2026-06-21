import { describe, it, expect } from 'vitest';
import { extractYamlBlock, parseChatEvent } from './api';

describe('extractYamlBlock', () => {
  it('returns null when no fence', () => {
    expect(extractYamlBlock('hello world')).toBeNull();
  });

  it('extracts a simple yaml block', () => {
    const md = 'sure:\n```yaml\nfoo: 1\n```\n';
    expect(extractYamlBlock(md)).toBe('foo: 1\n');
  });

  it('returns the LAST block when multiple', () => {
    const md = '```yaml\na: 1\n```\n\n```yaml\nb: 2\n```\n';
    expect(extractYamlBlock(md)).toBe('b: 2\n');
  });

  it('accepts ```yml as well', () => {
    expect(extractYamlBlock('```yml\nx: 1\n```')).toBe('x: 1\n');
  });
});

describe('parseChatEvent', () => {
  it('parses text events', () => {
    expect(parseChatEvent('text', '{"text":"hi"}')).toEqual({ kind: 'text', text: 'hi' });
  });

  it('parses tool_use events', () => {
    const ev = parseChatEvent(
      'tool_use',
      '{"name":"find_connector","arguments":{"q":"jira"},"call_id":"c1"}'
    );
    expect(ev).toMatchObject({
      kind: 'tool_use',
      name: 'find_connector',
      call_id: 'c1'
    });
  });

  it('parses done events', () => {
    expect(parseChatEvent('done', '{"stop_reason":"end_turn"}')).toEqual({
      kind: 'done',
      stop_reason: 'end_turn'
    });
  });

  it('returns null on unknown event names', () => {
    expect(parseChatEvent('huh', '{}')).toBeNull();
  });

  it('returns null on bad JSON', () => {
    expect(parseChatEvent('text', 'not-json')).toBeNull();
  });
});
