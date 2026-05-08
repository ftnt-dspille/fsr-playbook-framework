<script lang="ts">
  import { onMount } from 'svelte';

  type Session = {
    id: string;
    model: string | null;
    ts_first: string;
    ts_last: string;
    turn_count: number;
    total_input: number;
    total_output: number;
    est_cost_usd: number | null;
    tool_call_count: number;
    playbook_collection: string | null;
    feedback_rating: 'up' | 'down' | null;
    feedback_summary: string | null;
  };

  type Message = {
    turn: number;
    seq: number;
    ts: string;
    kind: 'user' | 'assistant_text' | 'tool_use' | 'tool_result';
    name: string | null;
    content: string | null;
  };

  type ToolCall = {
    turn: number;
    seq: number;
    name: string;
    args_chars: number | null;
    result_chars: number | null;
  };

  type Push = {
    id: number;
    ts: string;
    coll_name: string | null;
    coll_uuid: string;
    ok: number;
    http_status: number | null;
    wf_count: number | null;
    source_yaml: string | null;
  };

  type Feedback = {
    rating: 'up' | 'down';
    summary: string | null;
    tags: string | null;
    ts: string;
  };

  type SessionDetail = Session & {
    turns: Array<{ turn: number; ts: string; stop_reason: string | null }>;
    tool_calls: ToolCall[];
    messages: Message[];
    latest_push: Push | null;
    feedback: Feedback | null;
    final_yaml: string | null;
    final_yaml_source: string | null;
  };

  let sessions = $state<Session[]>([]);
  let loadingList = $state(true);
  let listError = $state<string | null>(null);

  let selectedId = $state<string | null>(null);
  let detail = $state<SessionDetail | null>(null);
  let loadingDetail = $state(false);

  let pendingRating = $state<'up' | 'down' | null>(null);
  let pendingSummary = $state('');
  let savingFeedback = $state(false);
  // Inline feedback error (replaces window.alert) + inline confirm
  // toggle (replaces window.confirm) for the Clear button.
  let feedbackErr = $state<string | null>(null);
  let confirmingClearFeedback = $state(false);
  // Inline delete-session confirm + error.
  let confirmingDeleteSession = $state(false);
  let deletingSession = $state(false);
  let deleteErr = $state<string | null>(null);

  async function loadList() {
    loadingList = true;
    listError = null;
    try {
      const r = await fetch('/api/history/sessions?limit=100');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      sessions = await r.json();
    } catch (e: any) {
      listError = String(e?.message || e);
    } finally {
      loadingList = false;
    }
  }

  async function loadDetail(id: string) {
    selectedId = id;
    loadingDetail = true;
    detail = null;
    try {
      const r = await fetch(`/api/history/sessions/${encodeURIComponent(id)}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      detail = (await r.json()) as SessionDetail;
      pendingRating = detail.feedback?.rating ?? null;
      pendingSummary = detail.feedback?.summary ?? '';
    } catch (e: any) {
      detail = null;
      console.error(e);
    } finally {
      loadingDetail = false;
    }
  }

  async function saveFeedback() {
    if (!selectedId || !pendingRating) return;
    savingFeedback = true;
    feedbackErr = null;
    try {
      const r = await fetch(
        `/api/history/sessions/${encodeURIComponent(selectedId)}/feedback`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ rating: pendingRating, summary: pendingSummary || null })
        }
      );
      if (!r.ok) throw new Error(await r.text());
      await Promise.all([loadList(), loadDetail(selectedId)]);
    } catch (e: any) {
      feedbackErr = `Failed to save feedback: ${e?.message || e}`;
    } finally {
      savingFeedback = false;
    }
  }

  async function clearFeedback() {
    if (!selectedId) return;
    confirmingClearFeedback = false;
    savingFeedback = true;
    feedbackErr = null;
    try {
      const r = await fetch(
        `/api/history/sessions/${encodeURIComponent(selectedId)}/feedback`,
        { method: 'DELETE' }
      );
      if (!r.ok) throw new Error(await r.text());
      pendingRating = null;
      pendingSummary = '';
      await Promise.all([loadList(), loadDetail(selectedId)]);
    } finally {
      savingFeedback = false;
    }
  }

  async function deleteSession() {
    if (!selectedId) return;
    deletingSession = true;
    deleteErr = null;
    const id = selectedId;
    try {
      const r = await fetch(
        `/api/history/sessions/${encodeURIComponent(id)}`,
        { method: 'DELETE' }
      );
      if (!r.ok) throw new Error(await r.text());
      // Drop the detail pane and refresh the list. Reset all the
      // per-session state we were holding for the now-gone row.
      selectedId = null;
      detail = null;
      pendingRating = null;
      pendingSummary = '';
      confirmingDeleteSession = false;
      confirmingClearFeedback = false;
      feedbackErr = null;
      await loadList();
    } catch (e: any) {
      deleteErr = `Failed to delete session: ${e?.message || e}`;
    } finally {
      deletingSession = false;
    }
  }

  function fmtTs(s: string | null | undefined): string {
    if (!s) return '';
    return new Date(s).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function fmtCost(c: number | null | undefined): string {
    if (c == null) return '—';
    if (c < 0.01) return `$${c.toFixed(4)}`;
    return `$${c.toFixed(3)}`;
  }

  function previewMessage(m: Message): string {
    const c = m.content ?? '';
    if (c.length <= 220) return c;
    return c.slice(0, 220) + '…';
  }

  function kindLabel(k: Message['kind']): string {
    return {
      user: 'You',
      assistant_text: 'Assistant',
      tool_use: 'Tool call',
      tool_result: 'Tool result'
    }[k];
  }

  function kindClass(k: Message['kind']): string {
    return {
      user: 'border-l-blue-400 bg-blue-950/20',
      assistant_text: 'border-l-emerald-400 bg-emerald-950/20',
      tool_use: 'border-l-amber-400 bg-amber-950/15',
      tool_result: 'border-l-zinc-500 bg-[var(--bg-panel)]/40'
    }[k];
  }

  onMount(loadList);
</script>

<!-- Use the layout's available height directly; the global StatusBar
     and header subtract their own space via the flex-column layout
     wrapper, so a hard `100vh - 3rem` calc here would overlap the
     footer. -->
<div class="flex h-full min-h-0">
  <aside class="w-96 shrink-0 border-r border-[var(--border-soft)] overflow-y-auto">
    <div class="sticky top-0 bg-[var(--bg-canvas)] border-b border-[var(--border-soft)] px-4 py-3 flex items-center justify-between">
      <h2 class="font-semibold">Chat sessions</h2>
      <button
        onclick={loadList}
        class="text-xs text-[var(--text-muted)] hover:text-[var(--text-default)]"
        title="Refresh"
      >
        ↻
      </button>
    </div>
    {#if loadingList}
      <div class="p-4 text-[var(--text-faint)] text-sm">Loading…</div>
    {:else if listError}
      <div class="p-4 text-red-400 text-sm">{listError}</div>
    {:else if sessions.length === 0}
      <div class="p-4 text-[var(--text-faint)] text-sm">
        No sessions yet. Start a chat from the Design tab.
      </div>
    {:else}
      <ul>
        {#each sessions as s}
          <li>
            <button
              onclick={() => loadDetail(s.id)}
              class={[
                'w-full text-left px-4 py-3 border-b border-[var(--border-soft)] hover:bg-[var(--bg-panel)]/50',
                selectedId === s.id ? 'bg-[var(--bg-panel)]/70' : ''
              ].join(' ')}
            >
              <div class="flex items-center justify-between text-xs text-[var(--text-muted)]">
                <span>{fmtTs(s.ts_last)}</span>
                <span class="flex items-center gap-1">
                  {#if s.feedback_rating === 'up'}
                    <span title="Thumbs up" class="text-emerald-400">▲</span>
                  {:else if s.feedback_rating === 'down'}
                    <span title="Thumbs down" class="text-rose-400">▼</span>
                  {/if}
                  <span>{fmtCost(s.est_cost_usd)}</span>
                </span>
              </div>
              <div class="text-sm text-[var(--text-default)] truncate font-medium mt-0.5">
                {s.playbook_collection || '(no playbook)'}
              </div>
              <div class="text-xs text-[var(--text-faint)] mt-0.5">
                {s.turn_count} turn{s.turn_count === 1 ? '' : 's'} ·
                {s.tool_call_count} tool call{s.tool_call_count === 1 ? '' : 's'} ·
                {s.model || '?'}
              </div>
              {#if s.feedback_summary}
                <div class="text-xs text-[var(--text-faint)] mt-1 italic truncate">
                  “{s.feedback_summary}”
                </div>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </aside>

  <main class="flex-1 overflow-y-auto">
    {#if !selectedId}
      <div class="h-full flex items-center justify-center text-[var(--text-faint)]">
        Pick a session on the left to see its full transcript.
      </div>
    {:else if loadingDetail}
      <div class="p-6 text-[var(--text-faint)]">Loading…</div>
    {:else if !detail}
      <div class="p-6 text-rose-400">Could not load session.</div>
    {:else}
      <div class="px-6 py-5 border-b border-[var(--border-soft)]">
        <div class="flex items-baseline justify-between">
          <div>
            <h1 class="text-lg font-semibold">
              {detail.playbook_collection || '(no playbook collection yet)'}
            </h1>
            <div class="text-xs text-[var(--text-faint)] mt-1">
              {detail.id} · {detail.model} · started {fmtTs(detail.ts_first)} ·
              ended {fmtTs(detail.ts_last)} · {detail.turn_count} turns ·
              {fmtCost(detail.est_cost_usd)} ·
              {detail.tool_calls.length} tool calls
            </div>
          </div>
          <div class="flex items-center gap-3">
            {#if detail.latest_push}
              <span
                class="text-xs text-[var(--text-muted)]"
                title="Latest push from this session"
              >
                push #{detail.latest_push.id} ·
                {detail.latest_push.ok ? '✓' : '✗'}
              </span>
            {/if}
            <a
              href={`/?session=${encodeURIComponent(detail.id)}`}
              class="rounded border border-[var(--border)] bg-[var(--bg-panel)] px-3 py-1.5 text-xs text-[var(--text-default)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
              title="Reload this conversation in the Design page (read-only replay)"
            >
              Open in Design ↗
            </a>
            {#if confirmingDeleteSession}
              <span class="flex items-center gap-1.5 text-xs">
                <span class="text-[var(--text-muted)]">Delete this session?</span>
                <button
                  onclick={deleteSession}
                  disabled={deletingSession}
                  class="rounded border border-red-700/60 bg-red-900/40 px-2 py-1 text-red-200 hover:bg-red-900/60 disabled:opacity-50"
                >
                  {deletingSession ? 'Deleting…' : 'Yes'}
                </button>
                <button
                  onclick={() => (confirmingDeleteSession = false)}
                  disabled={deletingSession}
                  class="rounded border border-[var(--border)] px-2 py-1 text-[var(--text-muted)] hover:bg-[var(--bg-panel)] disabled:opacity-50"
                >
                  No
                </button>
              </span>
            {:else}
              <button
                onclick={() => (confirmingDeleteSession = true)}
                class="rounded border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-faint)] hover:border-rose-700/60 hover:text-rose-300"
                title="Delete this chat session and its transcript"
              >
                Delete
              </button>
            {/if}
          </div>
        </div>
        {#if deleteErr}
          <div class="mt-2 rounded border border-red-700/60 bg-red-900/30 px-2 py-1 text-xs text-red-200">
            {deleteErr}
            <button class="ml-2 underline hover:text-red-100" onclick={() => (deleteErr = null)}>dismiss</button>
          </div>
        {/if}
      </div>

      <div class="px-6 py-4 border-b border-[var(--border-soft)] bg-[var(--bg-canvas)]/40">
        <div class="flex items-start gap-4">
          <div class="flex flex-col gap-2">
            <span class="text-xs uppercase tracking-wide text-[var(--text-faint)]">Rate</span>
            <div class="flex gap-2">
              <button
                onclick={() => (pendingRating = 'up')}
                class={[
                  'px-3 py-1.5 rounded border text-sm',
                  pendingRating === 'up'
                    ? 'border-emerald-500 bg-emerald-900/30 text-emerald-200'
                    : 'border-[var(--border)] hover:border-[var(--text-faint)] text-[var(--text-muted)]'
                ].join(' ')}
                title="Thumbs up"
              >
                ▲ Up
              </button>
              <button
                onclick={() => (pendingRating = 'down')}
                class={[
                  'px-3 py-1.5 rounded border text-sm',
                  pendingRating === 'down'
                    ? 'border-rose-500 bg-rose-900/30 text-rose-200'
                    : 'border-[var(--border)] hover:border-[var(--text-faint)] text-[var(--text-muted)]'
                ].join(' ')}
                title="Thumbs down"
              >
                ▼ Down
              </button>
            </div>
          </div>
          <div class="flex-1">
            <label class="text-xs uppercase tracking-wide text-[var(--text-faint)]" for="fb-summary">
              Review summary
            </label>
            <textarea
              id="fb-summary"
              bind:value={pendingSummary}
              placeholder="What worked, what broke, what should a future session investigate? (e.g. 'Picked DecisionBased for a form prompt — should have been InputBased. Validator caught it but agent looped 3 times trying to fix.')"
              class="mt-1 w-full rounded border border-[var(--border)] bg-[var(--bg-panel)] p-2 text-sm text-[var(--text-default)] placeholder:text-[var(--text-faint)] focus:border-[var(--brand)] focus:outline-none"
              rows="3"
            ></textarea>
            <div class="flex items-center justify-between mt-2">
              <span class="text-xs text-[var(--text-faint)]">
                {#if detail.feedback}
                  Last saved {fmtTs(detail.feedback.ts)}
                {:else}
                  Not yet rated.
                {/if}
              </span>
              <div class="flex items-center gap-2">
                {#if detail.feedback}
                  {#if confirmingClearFeedback}
                    <span class="flex items-center gap-1.5 text-xs">
                      <span class="text-[var(--text-muted)]">Clear feedback?</span>
                      <button
                        onclick={clearFeedback}
                        class="rounded border border-red-700/60 bg-red-900/40 px-1.5 py-0.5 text-red-200 hover:bg-red-900/60"
                      >
                        Yes
                      </button>
                      <button
                        onclick={() => (confirmingClearFeedback = false)}
                        class="rounded border border-[var(--border)] px-1.5 py-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-panel)]"
                      >
                        No
                      </button>
                    </span>
                  {:else}
                    <button
                      onclick={() => (confirmingClearFeedback = true)}
                      disabled={savingFeedback}
                      class="text-xs text-[var(--text-faint)] hover:text-rose-400 disabled:opacity-50"
                    >
                      Clear
                    </button>
                  {/if}
                {/if}
                <button
                  onclick={saveFeedback}
                  disabled={!pendingRating || savingFeedback}
                  class="btn btn-primary text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {savingFeedback ? 'Saving…' : 'Save feedback'}
                </button>
              </div>
            </div>
            {#if feedbackErr}
              <div class="mt-2 rounded border border-red-700/60 bg-red-900/30 px-2 py-1 text-xs text-red-200">
                {feedbackErr}
                <button class="ml-2 underline hover:text-red-100" onclick={() => (feedbackErr = null)}>dismiss</button>
              </div>
            {/if}
          </div>
        </div>
      </div>

      {#if detail.final_yaml}
        <details class="px-6 py-3 border-b border-[var(--border-soft)]" open>
          <summary class="cursor-pointer text-sm font-medium text-[var(--text-muted)]">
            Final playbook YAML
            <span class="ml-1 text-xs text-[var(--text-faint)]">
              ({detail.final_yaml_source ?? 'unknown source'})
            </span>
          </summary>
          <pre class="mt-3 max-h-[400px] overflow-auto rounded bg-[var(--bg-panel)] p-3 text-xs text-[var(--text-default)]">{detail.final_yaml}</pre>
        </details>
      {/if}

      <section class="px-6 py-4">
        <h2 class="text-sm font-medium text-[var(--text-muted)] mb-3">
          Transcript ({detail.messages.length} messages)
        </h2>
        {#if detail.messages.length === 0}
          <div class="text-[var(--text-faint)] text-sm">
            No per-message records for this session (older session before
            chat_messages was wired). Turn count: {detail.turn_count}.
          </div>
        {:else}
          <div class="space-y-2">
            {#each detail.messages as m}
              <div
                class={[
                  'border-l-2 rounded-r px-3 py-2 text-sm',
                  kindClass(m.kind)
                ].join(' ')}
              >
                <div class="flex items-center justify-between text-xs text-[var(--text-muted)]">
                  <span class="font-medium">
                    {kindLabel(m.kind)}{m.name ? ` · ${m.name}` : ''}
                  </span>
                  <span>turn {m.turn} · {fmtTs(m.ts)}</span>
                </div>
                {#if m.kind === 'tool_use' || m.kind === 'tool_result'}
                  <details class="mt-1" open>
                    <summary class="cursor-pointer text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)]">
                      {m.kind === 'tool_use' ? 'Arguments' : 'Result'}
                      {#if m.content}
                        · {m.content.length.toLocaleString()} chars
                      {:else}
                        · no payload
                      {/if}
                    </summary>
                    <pre class="mt-2 max-h-[300px] overflow-auto rounded bg-[var(--bg-canvas)]/60 p-2 text-xs text-[var(--text-muted)] whitespace-pre-wrap">{m.content || ''}</pre>
                  </details>
                {:else}
                  <div class="mt-1 text-[var(--text-default)] whitespace-pre-wrap">
                    {previewMessage(m)}
                  </div>
                  {#if (m.content?.length ?? 0) > 220}
                    <details class="mt-1">
                      <summary class="cursor-pointer text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)]">
                        Full message ({m.content!.length.toLocaleString()} chars)
                      </summary>
                      <div class="mt-2 text-[var(--text-default)] whitespace-pre-wrap">{m.content}</div>
                    </details>
                  {/if}
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>

      {#if detail.tool_calls.length}
        <section class="px-6 py-4 border-t border-[var(--border-soft)]">
          <h2 class="text-sm font-medium text-[var(--text-muted)] mb-3">
            Tool sequence
          </h2>
          <ol class="space-y-1 text-xs font-mono text-[var(--text-muted)]">
            {#each detail.tool_calls as t, i}
              <li>
                <span class="text-[var(--text-faint)]">{i + 1}.</span>
                <span class="text-amber-300">{t.name}</span>
                <span class="text-[var(--text-faint)]">
                  · turn {t.turn}
                  {#if t.args_chars != null} · {t.args_chars}b in{/if}
                  {#if t.result_chars != null} · {t.result_chars}b out{/if}
                </span>
              </li>
            {/each}
          </ol>
        </section>
      {/if}
    {/if}
  </main>
</div>
