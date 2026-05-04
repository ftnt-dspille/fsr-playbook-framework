<script lang="ts">
  import {
    extractYamlBlock,
    parseChatEvent,
    type ChatEvent,
    type ChatMessage
  } from '$lib/api';
  import { postSse } from '$lib/sse';

  type ToolCall = {
    call_id: string;
    name: string;
    arguments: Record<string, unknown>;
    result_preview?: string;
  };

  type Turn = {
    role: 'user' | 'assistant';
    text: string;
    tools?: ToolCall[];
  };

  let {
    currentYaml,
    onYamlReplace
  }: {
    currentYaml: string;
    onYamlReplace: (yaml: string) => void;
  } = $props();

  let turns = $state<Turn[]>([]);
  let input = $state('');
  let busy = $state(false);
  let err = $state<string | null>(null);

  const STARTERS = [
    'Build a hello-world playbook with one set_variable step that stores the string "hi".',
    'Add a decision step that branches on the input value being greater than 10.',
    'Why is my current YAML invalid? Walk through the diagnostics.',
    'Explain what each step in the current playbook does.'
  ];

  function useStarter(s: string) {
    input = s;
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    input = '';
    err = null;
    busy = true;
    turns = [...turns, { role: 'user', text }];
    const assistant: Turn = { role: 'assistant', text: '', tools: [] };
    turns = [...turns, assistant];

    const history: ChatMessage[] = turns
      .slice(0, -1)
      .map((t) => ({ role: t.role, content: t.text }));

    try {
      for await (const frame of postSse('/api/chat', {
        messages: history,
        current_yaml: currentYaml
      })) {
        const ev = parseChatEvent(frame.event, frame.data);
        if (!ev) continue;
        applyEvent(assistant, ev);
        turns = [...turns];
      }
    } catch (e: any) {
      err = e?.message ?? String(e);
    } finally {
      busy = false;
      const yaml = extractYamlBlock(assistant.text);
      if (yaml) onYamlReplace(yaml);
    }
  }

  function applyEvent(a: Turn, ev: ChatEvent) {
    switch (ev.kind) {
      case 'text':
        a.text += ev.text;
        break;
      case 'tool_use':
        a.tools = [
          ...(a.tools ?? []),
          { call_id: ev.call_id, name: ev.name, arguments: ev.arguments }
        ];
        break;
      case 'tool_result': {
        const tc = a.tools?.find((t) => t.call_id === ev.call_id);
        if (tc) tc.result_preview = ev.result_preview;
        break;
      }
      case 'error':
        err = ev.message;
        break;
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      send();
    }
  }

  function reset() {
    turns = [];
    err = null;
  }
</script>

<div class="flex h-full min-h-0 flex-col">
  <div class="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5 text-xs">
    <span class="font-semibold text-zinc-300">Chat</span>
    <button class="text-zinc-500 hover:text-zinc-300" onclick={reset}>reset</button>
  </div>

  <div class="min-h-0 flex-1 overflow-auto p-3 text-sm">
    {#if !turns.length && !busy}
      <div class="space-y-2">
        <p class="text-xs text-zinc-400">
          Ask the model to build or modify the YAML. It can call tools to look up
          connectors, operations, step types, and Jinja filters from the local
          reference store.
        </p>
        <div class="space-y-1.5">
          {#each STARTERS as s}
            <button
              class="block w-full rounded border border-zinc-800 bg-zinc-900/50 px-2 py-1.5 text-left text-xs text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800"
              onclick={() => useStarter(s)}
            >
              {s}
            </button>
          {/each}
        </div>
      </div>
    {/if}
    {#each turns as t}
      <div class="mb-3">
        <div class="mb-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
          {t.role}
        </div>
        {#if t.tools && t.tools.length}
          <div class="mb-1 space-y-1">
            {#each t.tools as tc}
              <details class="rounded border border-zinc-800 bg-zinc-900/50 px-2 py-1 text-xs">
                <summary class="cursor-pointer">
                  <span class="text-blue-400">🔧 {tc.name}</span>
                  <span class="text-zinc-500"
                    >({Object.keys(tc.arguments).length} args)</span
                  >
                </summary>
                <pre class="mt-1 overflow-auto text-[11px] text-zinc-400">{JSON.stringify(
                    tc.arguments,
                    null,
                    2
                  )}</pre>
                {#if tc.result_preview}
                  <div class="mt-1 text-[10px] uppercase text-zinc-500">result</div>
                  <pre class="overflow-auto text-[11px] text-zinc-300">{tc.result_preview}</pre>
                {/if}
              </details>
            {/each}
          </div>
        {/if}
        {#if t.text}
          <div class="whitespace-pre-wrap text-zinc-200">{t.text}</div>
        {/if}
      </div>
    {/each}
    {#if err}
      <div class="rounded border border-red-900 bg-red-950/40 p-2 text-xs text-red-300">
        {err}
      </div>
    {/if}
  </div>

  <div class="border-t border-zinc-800 p-2">
    <textarea
      class="block w-full resize-none rounded border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm focus:border-zinc-600 focus:outline-none"
      placeholder="Ask the model to build or edit the YAML…  ⌘/Ctrl+Enter to send"
      rows="3"
      bind:value={input}
      onkeydown={onKey}
      disabled={busy}
    ></textarea>
    <div class="mt-1 flex items-center justify-between text-xs text-zinc-500">
      <span>{busy ? 'streaming…' : 'idle'}</span>
      <button
        class="rounded border border-zinc-700 px-2 py-0.5 hover:bg-zinc-800 disabled:opacity-50"
        onclick={send}
        disabled={busy || !input.trim()}>Send</button
      >
    </div>
  </div>
</div>
