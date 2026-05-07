<script lang="ts">
  import {
    extractYamlBlock,
    listExamplePrompts,
    parseChatEvent,
    type ChatEvent,
    type ChatMessage,
    type ExamplePrompt,
    type LadderRung
  } from '$lib/api';
  import { postSse } from '$lib/sse';
  import { renderMarkdown } from '$lib/md';
  import { yamlStore } from '$lib/yamlStore.svelte';
  import { onMount, tick } from 'svelte';
  import LoopTelemetry from '$lib/components/LoopTelemetry.svelte';

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
  // Non-reactive tracker — only read/written from inside the effect
  // below. Marking this $state would cause a self-triggering update
  // loop (effect_update_depth_exceeded).
  let yamlPrevMeaningful = false;
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
  // Non-reactive identity tracker — same reasoning as
  // yamlPrevMeaningful: read+written only inside the effect below.
  let lastSeededRef: Turn[] | null = null;

  $effect(() => {
    if (initialTurns !== lastSeededRef) {
      turns = [...initialTurns];
      lastSeededRef = initialTurns;
    }
  });
  let input = $state('');
  let textareaEl = $state<HTMLTextAreaElement | null>(null);
  // Auto-grow the composer up to ~12 lines so short prompts stay compact
  // and long ones don't force an internal scrollbar before the outer
  // page can scroll. Cap matches the previous max behaviour roughly.
  function autosize(el: HTMLTextAreaElement | null) {
    if (!el) return;
    el.style.height = 'auto';
    const max = 320; // px — ~12 lines at 15px/1.5
    el.style.height = Math.min(el.scrollHeight, max) + 'px';
  }
  $effect(() => {
    // Re-run whenever the bound value changes.
    void input;
    autosize(textareaEl);
  });
  let busy = $state(false);
  let err = $state<string | null>(null);
  // Session id of the active chat — captured from the first `usage`
  // SSE event of the first turn. Used to name the draft this chat
  // writes its agent revisions to. A reload mid-session keeps the same
  // id only if the backend sends it; otherwise we fall back to a
  // client-generated session-scoped id.
  let chatSessionId = $state<string | null>(null);

  // ── Loop telemetry ────────────────────────────────────────────────
  // Tracks the per-session AI authoring loop so the user can see what
  // the agent is doing in real time (validate count, error trend, ladder
  // rung, tokens, elapsed). Reset alongside the conversation.
  let ladderRungs = $state<LadderRung[]>([]);
  let ladderAchieved = $state(0);
  let ladderErrors = $state(0);
  let ladderWarnings = $state(0);
  let ladderHistory = $state<number[]>([]); // last few error counts for trend
  let validateCount = $state(0);
  let inputTokens = $state(0);
  let outputTokens = $state(0);
  let sessionStart = $state<number | null>(null);
  let elapsedMs = $state(0);

  const errorTrend = $derived.by<-1 | 0 | 1 | null>(() => {
    if (ladderHistory.length < 2) return null;
    const a = ladderHistory[ladderHistory.length - 2];
    const b = ladderHistory[ladderHistory.length - 1];
    if (b < a) return -1;
    if (b > a) return 1;
    return 0;
  });

  $effect(() => {
    if (!sessionStart) return;
    const id = setInterval(() => {
      elapsedMs = Date.now() - (sessionStart ?? Date.now());
    }, 1000);
    return () => clearInterval(id);
  });
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

  // Sample prompts for testing the agent. Sourced from the eval-task
  // corpus (python/evals/tasks/*.json) via /api/ref/example-prompts so
  // the picker stays in sync with the harness — adding a task file
  // shows up here automatically.
  let examplePrompts = $state<ExamplePrompt[]>([]);
  let promptPickerOpen = $state(false);

  // A few quick-pick prompts kept inline as a fallback for the empty
  // state when the eval list hasn't loaded yet (or the backend is
  // misconfigured).
  const FALLBACK_STARTERS = [
    'Build a hello-world playbook with one set_variable step that stores the string "hi".',
    'Add a decision step that branches on the input value being greater than 10.',
    'Why is my current YAML invalid? Walk through the diagnostics.',
    'Explain what each step in the current playbook does.'
  ];

  onMount(async () => {
    try {
      examplePrompts = await listExamplePrompts();
    } catch (e) {
      console.warn('listExamplePrompts failed', e);
    }
  });

  function useStarter(s: string) {
    input = s;
    promptPickerOpen = false;
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

    // Capture the most recently validated YAML during this turn so the
    // editor can fall back to it when the final reply omits a fenced
    // block. Eliminates the double-emit pattern (validate-then-emit).
    let lastValidatedYaml: string | null = null;

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
        if (
          ev.kind === 'tool_use' &&
          (ev.name === 'validate_yaml' || ev.name === 'compile_yaml') &&
          typeof ev.arguments?.yaml_text === 'string'
        ) {
          lastValidatedYaml = ev.arguments.yaml_text;
        }
        applyEvent(aIdx, ev);
      }
    } catch (e: any) {
      err = e?.message ?? String(e);
    } finally {
      busy = false;
      const replyText = turns[aIdx]?.text ?? '';
      // Prefer a fenced block in the reply (explicit handoff). Fall
      // back to the last YAML the agent validated this turn — it's
      // the same content, just delivered via tool args instead of
      // duplicated into prose.
      const yaml = extractYamlBlock(replyText) ?? lastValidatedYaml;
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
        if (sessionStart === null) sessionStart = Date.now();
        inputTokens += ev.input_tokens ?? 0;
        outputTokens += ev.output_tokens ?? 0;
        // Count validate calls so the user sees the loop's effort.
        for (const tc of ev.tool_calls ?? []) {
          if (tc.name === 'validate_yaml' || tc.name === 'compile_yaml') {
            validateCount += 1;
          }
        }
        break;
      case 'ladder':
        ladderRungs = ev.rungs;
        ladderAchieved = ev.achieved;
        ladderErrors = ev.error_count;
        ladderWarnings = ev.warning_count;
        ladderHistory = [...ladderHistory.slice(-5), ev.error_count];
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
    ladderRungs = [];
    ladderAchieved = 0;
    ladderErrors = 0;
    ladderWarnings = 0;
    ladderHistory = [];
    validateCount = 0;
    inputTokens = 0;
    outputTokens = 0;
    sessionStart = null;
    elapsedMs = 0;
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

<div class="flex h-full min-h-0 flex-col bg-[var(--bg-canvas)]">
  <header class="flex items-center justify-between border-b border-[var(--border-soft)] px-4 py-2.5">
    <div class="flex items-center gap-2">
      <span class="inline-block h-2 w-2 rounded-full {busy
        ? 'animate-pulse bg-emerald-400'
        : 'bg-[var(--text-faint)]'}"></span>
      <span class="text-sm font-semibold text-[var(--text-default)]">Chat</span>
      <span class="text-xs text-[var(--text-faint)]">{busy ? 'streaming…' : 'ready'}</span>
    </div>
    <button
      class="text-xs text-[var(--text-faint)] transition-colors hover:text-[var(--text-muted)]"
      onclick={reset}>reset</button
    >
  </header>

  <LoopTelemetry
    rungs={ladderRungs}
    achieved={ladderAchieved}
    errorCount={ladderErrors}
    warningCount={ladderWarnings}
    errorTrend={errorTrend}
    {validateCount}
    {inputTokens}
    {outputTokens}
    {elapsedMs}
    {busy}
  />

  <div
    bind:this={scrollEl}
    onscroll={onScroll}
    class="min-h-0 flex-1 overflow-auto scroll-smooth"
  >
    <div class="space-y-5 px-4 py-4">
      {#if !turns.length && !busy}
        <div class="space-y-3 py-2">
          <p class="text-sm leading-relaxed text-[var(--text-muted)]">
            Ask the model to build or modify the YAML. It can call tools to look up
            connectors, operations, step types, and Jinja filters from the local
            reference store.
          </p>
          <div class="space-y-2 pt-1">
            <div class="flex items-center justify-between">
              <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                Try
              </div>
              {#if examplePrompts.length > 0}
                <button
                  type="button"
                  class="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-default)]"
                  onclick={() => (promptPickerOpen = !promptPickerOpen)}
                  title="Browse all sample prompts from the eval corpus"
                >
                  {promptPickerOpen ? '× close' : `${examplePrompts.length} samples ▾`}
                </button>
              {/if}
            </div>
            {#if promptPickerOpen && examplePrompts.length > 0}
              {#each examplePrompts as p}
                <button
                  class="block w-full rounded-lg border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 px-3 py-2 text-left text-xs text-[var(--text-muted)] transition-colors hover:border-[var(--border)] hover:bg-[var(--bg-elevated)]/60 hover:text-[var(--text-default)]"
                  onclick={() => useStarter(p.prompt)}
                  title={p.notes}
                >
                  <div class="font-mono text-[11px] text-[var(--text-faint)]">
                    {p.name}{p.has_gold ? ' · gold' : ''}
                  </div>
                  <div class="mt-0.5 line-clamp-2 leading-snug">{p.prompt}</div>
                </button>
              {/each}
            {:else}
              {#each FALLBACK_STARTERS as s}
                <button
                  class="block w-full rounded-lg border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 px-3 py-2 text-left text-sm text-[var(--text-muted)] transition-colors hover:border-[var(--border)] hover:bg-[var(--bg-elevated)]/60 hover:text-[var(--text-default)]"
                  onclick={() => useStarter(s)}
                >
                  {s}
                </button>
              {/each}
            {/if}
          </div>
        </div>
      {/if}

      {#each turns as t, i}
        <div class="flex gap-3">
          <div
            class="flex h-7 w-7 flex-none items-center justify-center rounded-full text-[11px] font-semibold {t.role ===
            'user'
              ? 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
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
                    class="group rounded-md border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 transition-colors hover:border-[var(--border)]"
                  >
                    <summary
                      class="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-xs text-[var(--text-muted)]"
                    >
                      <span class="text-blue-400">⚙</span>
                      <span class="font-mono text-blue-300">{tc.name}</span>
                      <span class="text-[var(--text-faint)]"
                        >· {Object.keys(tc.arguments).length}
                        {Object.keys(tc.arguments).length === 1 ? 'arg' : 'args'}</span
                      >
                      {#if tc.result_preview}
                        <span class="ml-auto text-[10px] text-emerald-400">✓</span>
                      {:else}
                        <span class="ml-auto inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-faint)]"></span>
                      {/if}
                    </summary>
                    <div class="border-t border-[var(--border-soft)] px-2.5 py-2">
                      <div class="text-[9px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                        Arguments
                      </div>
                      <pre
                        class="mt-1 overflow-auto whitespace-pre-wrap break-all rounded bg-[var(--bg-canvas)]/60 p-2 font-mono text-[11px] text-[var(--text-muted)]">{JSON.stringify(
                          tc.arguments,
                          null,
                          2
                        )}</pre>
                      {#if tc.result_preview}
                        <div class="mt-2 text-[9px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">
                          Result
                        </div>
                        <pre
                          class="mt-1 overflow-auto whitespace-pre-wrap break-all rounded bg-[var(--bg-canvas)]/60 p-2 font-mono text-[11px] text-[var(--text-muted)]">{tc.result_preview}</pre>
                      {/if}
                    </div>
                  </details>
                {/each}
              </div>
            {/if}

            {#if t.text}
              {#if t.role === 'assistant'}
                <div class="markdown-body text-[15px] leading-relaxed text-[var(--text-default)]">
                  {@html renderMarkdown(t.text)}
                </div>
              {:else}
                <div class="rounded-lg bg-[var(--bg-panel)]/60 px-3 py-2 text-[15px] leading-relaxed text-[var(--text-default)]">
                  {t.text}
                </div>
              {/if}
            {/if}
            {#if t.role === 'assistant' && busy && i === turns.length - 1}
              <!-- Keep the bouncing dots visible for the entire turn
                   while we're still streaming, even after some text
                   has arrived. Otherwise the gap between paragraphs,
                   between text and a tool call, or while a local
                   model is mid-thought looks frozen. -->
              <div class="mt-1 flex items-center gap-1.5 py-1 text-[var(--text-faint)]">
                <span class="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--text-faint)]" style="animation-delay:0ms"></span>
                <span class="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--text-faint)]" style="animation-delay:150ms"></span>
                <span class="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--text-faint)]" style="animation-delay:300ms"></span>
                <span class="ml-1 text-[11px] italic">thinking…</span>
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

  <div class="border-t border-[var(--border-soft)] bg-[var(--bg-canvas)] p-3">
    {#if promptPickerOpen && examplePrompts.length > 0 && turns.length > 0}
      <div class="mb-2 max-h-56 space-y-1 overflow-auto rounded-lg border border-[var(--border-soft)] bg-[var(--bg-panel)]/40 p-2">
        {#each examplePrompts as p}
          <button
            class="block w-full rounded border border-transparent px-2 py-1.5 text-left text-xs text-[var(--text-muted)] hover:border-[var(--border-soft)] hover:bg-[var(--bg-elevated)]/60 hover:text-[var(--text-default)]"
            onclick={() => useStarter(p.prompt)}
            title={p.notes}
          >
            <span class="font-mono text-[10px] text-[var(--text-faint)]">{p.name}</span>
            <span class="ml-2">{p.prompt.length > 90 ? p.prompt.slice(0, 90) + '…' : p.prompt}</span>
          </button>
        {/each}
      </div>
    {/if}
    <div class="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-panel)] focus-within:border-[var(--border)] focus-within:ring-1 focus-within:ring-zinc-700">
      <textarea
        bind:this={textareaEl}
        class="block w-full resize-none rounded-lg bg-transparent px-3 py-2 text-[15px] text-[var(--text-default)] placeholder:text-[var(--text-faint)] focus:outline-none"
        placeholder="Ask the model to build or edit the YAML…"
        rows="3"
        bind:value={input}
        onkeydown={onKey}
        disabled={busy}
      ></textarea>
      <div class="flex items-center justify-between border-t border-[var(--border-soft)] px-2.5 py-1.5">
        <label
          class="flex items-center gap-1.5 text-[11px] text-[var(--text-faint)] hover:text-[var(--text-muted)] cursor-pointer"
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
        <span class="text-[11px] text-[var(--text-faint)]">⌘ / Ctrl + Enter</span>
        <div class="flex items-center gap-1.5">
          {#if examplePrompts.length > 0}
            <button
              type="button"
              class="rounded-md border border-[var(--border-soft)] bg-[var(--bg-canvas)] px-2 py-1 text-[11px] text-[var(--text-muted)] hover:border-[var(--border)] hover:text-[var(--text-default)]"
              onclick={() => (promptPickerOpen = !promptPickerOpen)}
              title="Browse {examplePrompts.length} sample prompts from the eval corpus"
            >
              {promptPickerOpen ? '× samples' : `samples (${examplePrompts.length})`}
            </button>
          {/if}
          <button
            class="rounded-md bg-emerald-700 px-3 py-1 text-xs font-medium text-emerald-50 transition-colors hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-[var(--bg-elevated)] disabled:text-[var(--text-faint)]"
            onclick={send}
            disabled={busy || !input.trim()}
          >
            {busy ? '…' : 'Send'}
          </button>
        </div>
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
