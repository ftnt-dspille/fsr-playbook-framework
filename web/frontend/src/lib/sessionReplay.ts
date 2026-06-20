/**
 * Convert a saved chat session (rows from /api/history/sessions/{id}.messages)
 * into the Turn[] shape Chat.svelte renders live.
 *
 * Per-row schema (chat_messages):
 *   { turn, seq, ts, kind: 'user' | 'assistant_text' | 'tool_use' | 'tool_result',
 *     name, content }
 *
 * Reconstruction:
 *   - Each `user` row → its own Turn{role: 'user'}.
 *   - Each turn's assistant blocks (`assistant_text` + `tool_use` rows) collapse
 *     into a single Turn{role: 'assistant'}. text concatenates assistant_text
 *     content; tools[] collects tool_use entries.
 *   - `tool_result` rows match a tool_use by tool_use_id (the chat backend
 *     stores it on the result row's `name` field) and populate result_preview.
 *
 * The conversion is lossy in one place: if the agent emitted assistant_text
 * AFTER a tool_result within the same turn (typical reply pattern), all of
 * that turn's assistant_text gets concatenated into one block, which mirrors
 * what live Chat.svelte does — assistant text accumulates while tools fire
 * in parallel.
 */

export type ReplayTool = {
  call_id: string;
  name: string;
  arguments: Record<string, unknown>;
  result_preview?: string;
};

export type ReplayTurn = {
  role: 'user' | 'assistant';
  text: string;
  tools?: ReplayTool[];
};

export type SavedMessage = {
  turn: number;
  seq: number;
  ts: string;
  kind: 'user' | 'assistant_text' | 'tool_use' | 'tool_result';
  name: string | null;
  content: string | null;
};

function parseToolArgs(content: string | null): Record<string, unknown> {
  if (!content) return {};
  try {
    const parsed = JSON.parse(content);
    return typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, unknown>)
      : { value: parsed };
  } catch {
    return { _raw: content };
  }
}

function trimResult(content: string | null, max = 800): string {
  if (!content) return '';
  return content.length > max ? content.slice(0, max) + '\n…[truncated]' : content;
}

export function messagesToTurns(messages: SavedMessage[]): ReplayTurn[] {
  if (!messages?.length) return [];
  // Sort by (turn, seq) defensively; the API already does this but caller
  // may have re-ordered.
  const sorted = [...messages].sort((a, b) =>
    a.turn !== b.turn ? a.turn - b.turn : a.seq - b.seq
  );

  const turns: ReplayTurn[] = [];
  // Index of the current assistant turn within `turns`, per chat-turn number.
  let currentAssistant: ReplayTurn | null = null;
  let currentTurnNo: number | null = null;
  // Lookup of tool calls by their tool_use_id (stored as `name` on tool_use
  // rows when persisted with the parent id). We fall back to call_id-by-order
  // for older rows that stored only the tool name.
  const toolByCallId = new Map<string, ReplayTool>();
  // Pending tool_use rows by turn — used when the row's `name` IS the tool
  // name (older logging) and we need to splice tool_result back to it by
  // sequence order rather than id.
  const toolsByTurnInOrder = new Map<number, ReplayTool[]>();

  for (const m of sorted) {
    if (m.kind === 'user') {
      // A user row closes any pending assistant turn.
      currentAssistant = null;
      currentTurnNo = m.turn;
      turns.push({ role: 'user', text: m.content ?? '' });
      continue;
    }

    // Open a new assistant turn lazily on first non-user row of a turn.
    if (m.turn !== currentTurnNo || !currentAssistant) {
      currentAssistant = { role: 'assistant', text: '', tools: [] };
      currentTurnNo = m.turn;
      turns.push(currentAssistant);
    }

    if (m.kind === 'assistant_text') {
      currentAssistant.text += m.content ?? '';
    } else if (m.kind === 'tool_use') {
      const args = parseToolArgs(m.content);
      const toolName = m.name ?? '(unknown)';
      // For chat_messages stored by chat.py, tool_use rows put the tool
      // *name* in `name`. We don't have a separate call_id, so we
      // synthesise one from (turn, seq) for matching with results.
      const callId = `${m.turn}:${m.seq}`;
      const tool: ReplayTool = { call_id: callId, name: toolName, arguments: args };
      currentAssistant.tools = currentAssistant.tools ?? [];
      currentAssistant.tools.push(tool);
      toolByCallId.set(callId, tool);
      const list = toolsByTurnInOrder.get(m.turn) ?? [];
      list.push(tool);
      toolsByTurnInOrder.set(m.turn, list);
    } else if (m.kind === 'tool_result') {
      // chat.py stores tool_use_id in `name` on tool_result rows. If a
      // matching tool was registered by id, populate it. Otherwise fall
      // back to "the next un-resulted tool in this turn", which handles
      // the older logging shape.
      const byId = m.name ? toolByCallId.get(m.name) : undefined;
      if (byId) {
        byId.result_preview = trimResult(m.content);
      } else {
        const list = toolsByTurnInOrder.get(m.turn) ?? [];
        const next = list.find((t) => t.result_preview === undefined);
        if (next) next.result_preview = trimResult(m.content);
      }
    }
  }

  // Drop any trailing empty assistant turns (e.g. recorded UsageEvent
  // without text/tools — shouldn't happen but defensive).
  return turns.filter(
    (t) => t.role === 'user' || t.text || (t.tools && t.tools.length > 0)
  );
}
