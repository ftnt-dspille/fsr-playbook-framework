<script lang="ts">
  import {
    extractYamlBlock,
    parseChatEvent,
    type ChatEvent,
    type ChatMessage
  } from '$lib/api';
  import { postSse } from '$lib/sse';
  import { renderMarkdown } from '$lib/md';
  import { yamlStore } from '$lib/yamlStore.svelte';
  import { tick } from 'svelte';

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
    onYamlReplace,
    initialTurns = []
  }: {
    currentYaml: string;
    onYamlReplace: (yaml: string) => void;
    /** Pre-populate the chat history (e.g. when replaying a session
     *  loaded from /api/history). Mutating this array after mount has
     *  no effect; pass a fresh prop value to replace. */
    initialTurns?: Turn[];
  } = $props();

  // "Empty" YAML buffers we should NOT send as agent context — sending
  // them causes the agent to extend the scaffold instead of authoring
  // fresh. Heuristic: blank, comment-only, or the welcome placeholder
  // (detected by the marker comment that yamlStore.PLACEHOLDER opens
  // with). Authors with a real playbook in the editor pass the check.
  function isMeaningfulYaml(text: string): boolean {
    const stripped = text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'))
      .join('\n');
    if (stripped.length < 40) return false;
    if (text.includes('# Welcome — try one of these to get started:')) return false;
    if (text.includes('# ... rest of your current workflow content ...')) return false;
    return true;
  }

  // User-controlled override. Defaults to "include only when the
  // buffer looks meaningful". User can flip both ways. Initialized
  // false; the effect below seeds it from the live `currentYaml`
  // prop on first run (Svelte 5 won't track the prop in $state init).
  let includeYaml = $state(false);
  // Re-sync the default whenever the upstream buffer changes between
  // empty and meaningful (e.g. user types real YAML, or resets back to
  // placeholder). Only auto-flip when the current toggle matches the
  // previous default — so an explicit user choice sticks.
  let yamlPrevMeaningful = $state(false);
  $effect(() => {
    const nowMeaningful = isMeaningfulYaml(currentYaml);
    if (nowMeaningful !== yamlPrevMeaningful) {
      // Author flipped the buffer state; re-evaluate default unless
      // they've explicitly diverged.
      if (includeYaml === yamlPrevMeaningful) {
        includeYaml = nowMeaningful;
      }
      yamlPrevMeaningful = nowMeaningful;
    }
  });

  let turns = $state<Turn[]>([]);
  // Re-seed `turns` whenever the parent passes a fresh `initialTurns`
  // reference. Tracks identity (not contents) so live edits to a stable
  // array don't clobber the running session.
  let lastSeededRef = $state<Turn[] | null>(null);

  $effect(() => {
    if (initialTurns !== lastSeededRef) {
      turns = [...initialTurns];
      lastSeededRef = initialTurns;
    }
  });
  let input = $state('');
  let busy = $state(false);
  let err = $state<string | null>(null);
  // Session id of the active chat — captured from the first `usage`
  // SSE event of the first turn. Used to name the draft this chat
  // writes its agent revisions to. A reload mid-session keeps the same
  // id only if the backend sends it; otherwise we fall back to a
  // client-generated session-scoped id.
  let chatSessionId = $state<string | null>(null);
  // Display name of the draft this chat writes to. Picked once per
  // session: the first non-trivial collection name we see in agent
  // YAML output, fallback to a session-id based label.
  let draftName = $state<string | null>(null);

  function pickDraftName(yaml: string, sessionId: string | null): string {
    const m = yaml.match(/^\s*collection\s*:\s*(.+?)\s*$/m);
    const coll = m?.[1]?.replace(/['"]/g, '').trim();
    if (coll) return `Chat: ${coll}`;
    if (sessionId) return `Chat: ${sessionId.slice(0, 8)}`;
    return 'Chat: (unnamed)';
  }

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
    turns.push({ role: 'user', text });
    turns.push({ role: 'assistant', text: '', tools: [] });
    // IMPORTANT: hold the index, not the object. Svelte 5 wraps array
    // entries in reactive proxies on push; a captured object reference
    // is the unwrapped original and mutations bypass reactivity.
    const aIdx = turns.length - 1;

    const history: ChatMessage[] = turns
      .slice(0, -1)
      .map((t) => ({ role: t.role, content: t.text }));

    try {
      for await (const frame of postSse('/api/chat', {
        messages: history,
        // Only send the editor YAML when the user wants it as context.
        // Sending the placeholder scaffold biases the agent into
        // extending it rather than authoring fresh.
        current_yaml: includeYaml ? currentYaml : ''
      })) {
        const ev = parseChatEvent(frame.event, frame.data);
        if (!ev) continue;
        applyEvent(aIdx, ev);
      }
    } catch (e: any) {
      err = e?.message ?? String(e);
    } finally {
      busy = false;
      const replyText = turns[aIdx]?.text ?? '';
      const yaml = extractYamlBlock(replyText);
      if (yaml) {
        // Persist this turn's YAML as a new revision on the session's
        // draft so the user can see how the agent iterated. Keeps the
        // editor buffer in sync (legacy behavior); the revision history
        // is in addition, not a replacement.
        const name = draftName ?? pickDraftName(yaml, chatSessionId);
        draftName = name;
        try {
          yamlStore.appendDraftRevision(name, yaml, 'agent', {
            message: text,
            sessionId: chatSessionId ?? undefined,
          });
        } catch (e) {
          console.warn('appendDraftRevision failed', e);
        }
        onYamlReplace(yaml);
      } else {
        // Authoring intent + no extractable YAML = "didn't add the
        // playbook to the UI" failure mode (chat_review detector
        // `no_editor_update`). Surface it inline so the user sees it
        // immediately instead of having to thumb-down + review later.
        const looksLikeAuthoring = /\b(build|create|make|draft|add|write|edit|fix|update)\b.*\b(playbook|yaml|step|workflow)\b/i.test(text);
        if (looksLikeAuthoring) {
          // Likely cause: agent put YAML in a non-yaml fence (```yml is
          // accepted, ```YAML is, but plain ``` and other tags aren't).
          const wrongFence = /```(?!ya?ml\b)[A-Za-z0-9_+-]*\s*\n[\s\S]*?(collection:|playbooks:|type:\s+set_variable)[\s\S]*?```/i
            .test(replyText);
          err = wrongFence
            ? "The reply contained YAML-shaped content but in a non-yaml code fence — the editor wasn't updated. Ask the agent to wrap it in ```yaml … ```."
            : "The reply didn't include a ```yaml block — the editor wasn't updated. If you wanted a playbook, ask the agent to emit the full YAML inside a ```yaml fenced block.";
        }
      }
    }
  }

  function applyEvent(idx: number, ev: ChatEvent) {
    const a = turns[idx];
    if (!a) return;
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
      case 'usage':
        // The very first usage event of the chat tells us the
        // session id; subsequent turns reuse it so all revisions on
        // the same session land under the same draft.
        if (!chatSessionId) chatSessionId = ev.session_id;
        break;
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

  // Auto-scroll the conversation pane as content streams in.
  let scrollEl: HTMLDivElement | undefined = $state(undefined);
  let stickToBottom = $state(true);

  function onScroll() {
    if (!scrollEl) return;
    const slack = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight;
    stickToBottom = slack < 40;
  }

  $effect(() => {
    // Track changes to the visible turn count + the latest text length.
    void turns.length;
    void turns[turns.length - 1]?.text?.length;
    void turns[turns.length - 1]?.tools?.length;
    if (!stickToBottom) return;
    tick().then(() => {
      if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    });
  });
</script>

<div class="flex h-full min-h-0 flex-col bg-zinc-950">
  <header class="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5">
    <div class="flex items-center gap-2">
      <span class="inline-block h-2 w-2 rounded-full {busy
        ? 'animate-pulse bg-emerald-400'
        : 'bg-zinc-600'}"></span>
      <span class="text-sm font-semibold text-zinc-200">Chat</span>
      <span class="text-xs text-zinc-500">{busy ? 'streaming…' : 'ready'}</span>
    </div>
    <button
      class="text-xs text-zinc-500 transition-colors hover:text-zinc-300"
      onclick={reset}>reset</button
    >
  </header>

  <div
    bind:this={scrollEl}
    onscroll={onScroll}
    class="min-h-0 flex-1 overflow-auto scroll-smooth"
  >
    <div class="space-y-5 px-4 py-4">
      {#if !turns.length && !busy}
        <div class="space-y-3 py-2">
          <p class="text-sm leading-relaxed text-zinc-400">
            Ask the model to build or modify the YAML. It can call tools to look up
            connectors, operations, step types, and Jinja filters from the local
            reference store.
          </p>
          <div class="space-y-2 pt-1">
            <div class="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Try
            </div>
            {#each STARTERS as s}
              <button
                class="block w-full rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-left text-sm text-zinc-300 transition-colors hover:border-zinc-700 hover:bg-zinc-800/60 hover:text-zinc-100"
                onclick={() => useStarter(s)}
              >
                {s}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      {#each turns as t, i}
        <div class="flex gap-3">
          <div
            class="flex h-7 w-7 flex-none items-center justify-center rounded-full text-[11px] font-semibold {t.role ===
            'user'
              ? 'bg-zinc-800 text-zinc-300'
              : 'bg-emerald-900/60 text-emerald-200 ring-1 ring-emerald-800'}"
            title={t.role}
          >
            {t.role === 'user' ? 'You' : 'AI'}
          </div>
          <div class="min-w-0 flex-1">
            {#if t.tools && t.tools.length}
              <div class="mb-2 space-y-1.5">
                {#each t.tools as tc}
                  <details
                    class="group rounded-md border border-zinc-800 bg-zinc-900/40 transition-colors hover:border-zinc-700"
                  >
                    <summary
                      class="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-xs text-zinc-300"
                    >
                      <span class="text-blue-400">⚙</span>
                      <span class="font-mono text-blue-300">{tc.name}</span>
                      <span class="text-zinc-500"
                        >· {Object.keys(tc.arguments).length}
                        {Object.keys(tc.arguments).length === 1 ? 'arg' : 'args'}</span
                      >
                      {#if tc.result_preview}
                        <span class="ml-auto text-[10px] text-emerald-400">✓</span>
                      {:else}
                        <span class="ml-auto inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-500"></span>
                      {/if}
                    </summary>
                    <div class="border-t border-zinc-800 px-2.5 py-2">
                      <div class="text-[9px] font-semibold uppercase tracking-wider text-zinc-500">
                        Arguments
                      </div>
                      <pre
                        class="mt-1 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-950/60 p-2 font-mono text-[11px] text-zinc-300">{JSON.stringify(
                          tc.arguments,
                          null,
                          2
                        )}</pre>
                      {#if tc.result_preview}
                        <div class="mt-2 text-[9px] font-semibold uppercase tracking-wider text-zinc-500">
                          Result
                        </div>
                        <pre
                          class="mt-1 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-950/60 p-2 font-mono text-[11px] text-zinc-300">{tc.result_preview}</pre>
                      {/if}
                    </div>
                  </details>
                {/each}
              </div>
            {/if}

            {#if t.text}
              {#if t.role === 'assistant'}
                <div class="markdown-body text-[15px] leading-relaxed text-zinc-100">
                  {@html renderMarkdown(t.text)}
                </div>
              {:else}
                <div class="rounded-lg bg-zinc-900/60 px-3 py-2 text-[15px] leading-relaxed text-zinc-100">
                  {t.text}
                </div>
              {/if}
            {:else if t.role === 'assistant' && busy && i === turns.length - 1}
              <div class="flex items-center gap-1.5 py-1 text-zinc-500">
                <span class="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500" style="animation-delay:0ms"></span>
                <span class="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500" style="animation-delay:150ms"></span>
                <span class="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500" style="animation-delay:300ms"></span>
              </div>
            {/if}
          </div>
        </div>
      {/each}

      {#if err}
        <div class="rounded-lg border border-red-900/70 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {err}
        </div>
      {/if}
    </div>
  </div>

  <div class="border-t border-zinc-800 bg-zinc-950 p-3">
    <div class="rounded-lg border border-zinc-800 bg-zinc-900 focus-within:border-zinc-600 focus-within:ring-1 focus-within:ring-zinc-700">
      <textarea
        class="block w-full resize-none rounded-lg bg-transparent px-3 py-2 text-[15px] text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        placeholder="Ask the model to build or edit the YAML…"
        rows="3"
        bind:value={input}
        onkeydown={onKey}
        disabled={busy}
      ></textarea>
      <div class="flex items-center justify-between border-t border-zinc-800 px-2.5 py-1.5">
        <label
          class="flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 cursor-pointer"
          title="When on, the editor's current YAML is sent to the model as
context. Turn off to author a brand-new playbook from scratch — sending
a scaffold biases the model into extending it rather than starting fresh."
        >
          <input
            type="checkbox"
            bind:checked={includeYaml}
            class="h-3 w-3 cursor-pointer accent-emerald-600"
          />
          include YAML as context
        </label>
        <span class="text-[11px] text-zinc-500">⌘ / Ctrl + Enter</span>
        <button
          class="rounded-md bg-emerald-700 px-3 py-1 text-xs font-medium text-emerald-50 transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
          onclick={send}
          disabled={busy || !input.trim()}
        >
          {busy ? '…' : 'Send'}
        </button>
      </div>
    </div>
  </div>
</div>

<style>
  /* Scoped markdown styling — readable, compact, dark theme. */
  :global(.markdown-body p) {
    margin: 0.5rem 0;
  }
  :global(.markdown-body p:first-child) {
    margin-top: 0;
  }
  :global(.markdown-body p:last-child) {
    margin-bottom: 0;
  }
  :global(.markdown-body h1),
  :global(.markdown-body h2),
  :global(.markdown-body h3),
  :global(.markdown-body h4) {
    font-weight: 600;
    margin: 1rem 0 0.4rem;
    color: rgb(244 244 245);
    line-height: 1.3;
  }
  :global(.markdown-body h1) { font-size: 1.15rem; }
  :global(.markdown-body h2) { font-size: 1.05rem; }
  :global(.markdown-body h3) { font-size: 0.95rem; color: rgb(212 212 216); }
  :global(.markdown-body h4) { font-size: 0.9rem; color: rgb(212 212 216); }
  :global(.markdown-body ul),
  :global(.markdown-body ol) {
    margin: 0.5rem 0;
    padding-left: 1.4rem;
  }
  :global(.markdown-body ul) { list-style: disc; }
  :global(.markdown-body ol) { list-style: decimal; }
  :global(.markdown-body li) {
    margin: 0.2rem 0;
  }
  :global(.markdown-body strong) {
    color: rgb(244 244 245);
    font-weight: 600;
  }
  :global(.markdown-body em) {
    color: rgb(228 228 231);
    font-style: italic;
  }
  :global(.markdown-body code) {
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 0.85em;
    background: rgb(39 39 42);
    color: rgb(244 244 245);
    padding: 0.1em 0.35em;
    border-radius: 0.25rem;
  }
  :global(.markdown-body pre) {
    margin: 0.6rem 0;
    padding: 0.7rem 0.85rem;
    background: rgb(9 9 11);
    border: 1px solid rgb(39 39 42);
    border-radius: 0.4rem;
    overflow-x: auto;
    line-height: 1.45;
  }
  :global(.markdown-body pre code) {
    background: transparent;
    padding: 0;
    font-size: 0.82rem;
    color: rgb(228 228 231);
  }
  :global(.markdown-body hr) {
    border: 0;
    border-top: 1px solid rgb(39 39 42);
    margin: 1rem 0;
  }
  :global(.markdown-body blockquote) {
    margin: 0.5rem 0;
    padding-left: 0.8rem;
    border-left: 2px solid rgb(63 63 70);
    color: rgb(161 161 170);
  }
  :global(.markdown-body a) {
    color: rgb(96 165 250);
    text-decoration: underline;
  }
  :global(.markdown-body table) {
    border-collapse: collapse;
    margin: 0.5rem 0;
    font-size: 0.9em;
  }
  :global(.markdown-body th),
  :global(.markdown-body td) {
    border: 1px solid rgb(39 39 42);
    padding: 0.3rem 0.6rem;
  }
  :global(.markdown-body th) {
    background: rgb(24 24 27);
    font-weight: 600;
  }
</style>
