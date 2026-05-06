<script lang="ts">
  import MonacoYaml from '$lib/components/MonacoYaml.svelte';
  import Chat from '$lib/components/Chat.svelte';
  import ExamplesMenu from '$lib/components/ExamplesMenu.svelte';
  import DraftsMenu from '$lib/components/DraftsMenu.svelte';
  import { compileYaml, pushPlaybook, validateYaml, type Marker } from '$lib/api';
  import { runStore } from '$lib/runStore.svelte';
  import { yamlStore } from '$lib/yamlStore.svelte';
  import { postSse } from '$lib/sse';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { messagesToTurns, type ReplayTurn } from '$lib/sessionReplay';

  // Two-way bind: editor edits the store directly via the effect below.
  // Wholesale replacements (load example, load draft, reset) MUST call
  // yamlStore.setText() so an auto-snapshot fires and the user can undo
  // a misclick.
  let yaml = $state(yamlStore.text);
  $effect(() => {
    yamlStore.text = yaml;
  });
  // When the store is mutated externally (loadDraft, reset, restoreSnapshot,
  // setText from another tab via storage event), pull the new value into
  // the local `yaml` so the editor re-renders.
  $effect(() => {
    if (yamlStore.text !== yaml) yaml = yamlStore.text;
  });

  // Replay mode: when the URL carries `?session=<id>`, hydrate the
  // editor + chat with the saved transcript so the user can see how
  // the original conversation played out. Replay is read-only on the
  // chat side — sending a new message starts a fresh session.
  let replayTurns = $state<ReplayTurn[]>([]);
  let replayBanner = $state<string | null>(null);

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const sid = params.get('session');
    if (!sid) return;
    try {
      const r = await fetch(`/api/history/sessions/${encodeURIComponent(sid)}`);
      if (!r.ok) {
        replayBanner = `Could not load session ${sid} (HTTP ${r.status})`;
        return;
      }
      const detail = await r.json();
      const turns = messagesToTurns(detail.messages || []);
      replayTurns = turns;
      // Pull the YAML in priority order: deployed (latest_push) →
      // last yaml block the assistant emitted in the transcript.
      const deployed = detail.latest_push?.source_yaml as string | undefined;
      if (deployed) {
        yamlStore.setText(deployed, `replay session ${sid}`);
      } else {
        // Fall back to scanning the transcript for the most recent
        // ```yaml block — same regex used by the live chat for buffer
        // replacement. Cheap inline copy to avoid pulling extractYaml
        // into this layer.
        const tail = (detail.messages || [])
          .filter((m: any) => m.kind === 'assistant_text')
          .map((m: any) => m.content || '')
          .join('\n');
        const match = tail.match(/```yaml\s*\n([\s\S]*?)```/g);
        if (match && match.length) {
          const last = match[match.length - 1].replace(/^```yaml\s*\n/, '').replace(/```$/, '');
          if (last.trim()) yamlStore.setText(last, `replay session ${sid}`);
        }
      }
      const tag = detail.playbook_collection || sid;
      replayBanner = `Replaying session ${tag} (${turns.length} turn${turns.length === 1 ? '' : 's'})`;
    } catch (e: any) {
      replayBanner = `Replay failed: ${e?.message ?? e}`;
    }
  });

  function exitReplay() {
    replayTurns = [];
    replayBanner = null;
    // Strip the query param so a refresh doesn't re-load.
    goto('/', { replaceState: true, keepFocus: true });
  }

  let markers = $state<Marker[]>([]);
  let compileJson = $state<string | null>(null);
  let drawerTab = $state<'diagnostics' | 'compile' | 'push' | 'run'>('diagnostics');
  let drawerOpen = $state(true);

  let status = $state<{ kind: 'idle' | 'ok' | 'err' | 'busy'; msg: string }>({
    kind: 'idle',
    msg: 'editing'
  });

  let debounceId: ReturnType<typeof setTimeout> | undefined;

  $effect(() => {
    void yaml;
    if (debounceId) clearTimeout(debounceId);
    debounceId = setTimeout(runValidate, 400);
  });

  async function runValidate() {
    try {
      const r = await validateYaml(yaml);
      markers = r.markers;
      const errs = markers.filter((m) => m.severity === 'error').length;
      const warns = markers.filter((m) => m.severity === 'warning').length;
      status = r.ok
        ? { kind: 'ok', msg: warns ? `valid · ${warns} warning${warns > 1 ? 's' : ''}` : 'valid' }
        : { kind: 'err', msg: `${errs} error${errs !== 1 ? 's' : ''}` };
    } catch (e: any) {
      status = { kind: 'err', msg: e?.message ?? String(e) };
    }
  }

  async function runCompile() {
    drawerTab = 'compile';
    drawerOpen = true;
    status = { kind: 'busy', msg: 'compiling…' };
    try {
      const r = await compileYaml(yaml);
      markers = r.markers;
      compileJson = r.fsr_json ? JSON.stringify(r.fsr_json, null, 2) : null;
      status = r.ok ? { kind: 'ok', msg: 'compiled' } : { kind: 'err', msg: 'compile failed' };
    } catch (e: any) {
      status = { kind: 'err', msg: e?.message ?? String(e) };
    }
  }

  function extractCollectionName(text: string): string | null {
    const m = text.match(/^\s*collection:\s*(.+?)\s*$/m);
    return m?.[1]?.replace(/^["']|["']$/g, '') ?? null;
  }

  function firstPlaybookName(text: string): string | null {
    const m = text.match(/playbooks:[\s\S]*?-\s*name:\s*(.+?)\s*$/m);
    return m?.[1]?.replace(/^["']|["']$/g, '') ?? null;
  }

  async function pushNow() {
    runStore.reset();
    runStore.status = 'pushing';
    drawerTab = 'push';
    drawerOpen = true;
    try {
      const r = await pushPlaybook(yaml);
      runStore.pushOutput = r.stdout + (r.stderr ? `\n[stderr]\n${r.stderr}` : '');
      if (!r.ok) {
        runStore.status = 'error';
        runStore.errorMsg = `push failed (exit ${r.exit_code})`;
        status = { kind: 'err', msg: `push failed (exit ${r.exit_code})` };
        return false;
      }
      status = { kind: 'ok', msg: 'pushed' };
      runStore.status = 'idle';
      return true;
    } catch (e: any) {
      runStore.status = 'error';
      runStore.errorMsg = e?.message ?? String(e);
      status = { kind: 'err', msg: runStore.errorMsg ?? 'push error' };
      return false;
    }
  }

  async function pushAndRun() {
    const ok = await pushNow();
    if (!ok) return;
    const coll = extractCollectionName(yaml);
    const pb = firstPlaybookName(yaml);
    if (!coll || !pb) {
      status = { kind: 'err', msg: 'cannot infer collection / playbook name' };
      return;
    }
    runStore.status = 'running';
    drawerTab = 'run';
    drawerOpen = true;
    try {
      for await (const frame of postSse('/api/playbook/run', { name: `${coll}:${pb}` })) {
        if (frame.event === 'log') {
          const { line } = JSON.parse(frame.data);
          runStore.logs = [...runStore.logs, line];
        } else if (frame.event === 'task_id') {
          runStore.taskId = JSON.parse(frame.data).task_id;
        } else if (frame.event === 'done') {
          const { exit_code } = JSON.parse(frame.data);
          runStore.exitCode = exit_code;
          runStore.status = exit_code === 0 ? 'done' : 'error';
        } else if (frame.event === 'error') {
          runStore.errorMsg = JSON.parse(frame.data).message;
          runStore.status = 'error';
        }
      }
    } catch (e: any) {
      runStore.errorMsg = e?.message ?? String(e);
      runStore.status = 'error';
    }
  }

  function loadExampleText(text: string, name: string) {
    yamlStore.setText(text, `loaded example: ${name}`);
    status = { kind: 'idle', msg: `loaded ${name}` };
  }

  function loadDraftText(_text: string, name: string) {
    // The DraftsMenu component already called yamlStore.loadDraft(),
    // which performs its own snapshot. Just update the status pill.
    status = { kind: 'idle', msg: `loaded draft: ${name}` };
  }

  function saveCurrentDraft() {
    const suggested = yamlStore.suggestedName();
    const name = window.prompt('Save draft as:', suggested);
    if (!name) return;
    try {
      const d = yamlStore.saveDraft(name);
      status = { kind: 'ok', msg: `saved draft: ${d.name}` };
    } catch (e: any) {
      status = { kind: 'err', msg: e?.message ?? String(e) };
    }
  }

  function undoLastReplace() {
    const snap = yamlStore.lastSnapshot;
    if (!snap) return;
    const reason = snap.reason;
    yamlStore.restoreSnapshot();
    status = { kind: 'idle', msg: `undone (${reason})` };
  }

  const dot = $derived(
    status.kind === 'ok'
      ? 'bg-green-500'
      : status.kind === 'err'
        ? 'bg-red-500'
        : status.kind === 'busy'
          ? 'bg-yellow-500'
          : 'bg-zinc-600'
  );

  const errCount = $derived(markers.filter((m) => m.severity === 'error').length);
  const warnCount = $derived(markers.filter((m) => m.severity === 'warning').length);
</script>

<div class="grid h-full grid-cols-[minmax(0,1fr)_minmax(320px,28rem)]">
  <div class="flex min-h-0 flex-col border-r border-zinc-800">
    <!-- Toolbar -->
    <div class="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-3 py-1.5 text-xs">
      <ExamplesMenu onLoad={loadExampleText} />
      <DraftsMenu onLoad={loadDraftText} />
      <button
        class="rounded border border-zinc-700 px-2 py-0.5 text-zinc-200 hover:bg-zinc-800"
        onclick={saveCurrentDraft}
        title="Save current YAML as a named draft (stored in this browser)"
      >
        Save
      </button>
      <button
        class="rounded border border-zinc-800 px-2 py-0.5 text-zinc-400 hover:bg-zinc-900"
        onclick={() => {
          yamlStore.reset();
        }}
        title="Reset to placeholder (snapshot taken; click Undo to restore)"
        >Reset</button
      >
      {#if yamlStore.lastSnapshot}
        <button
          class="rounded border border-amber-700/60 bg-amber-950/30 px-2 py-0.5 text-amber-200 hover:bg-amber-900/40"
          onclick={undoLastReplace}
          title="Restore the buffer from before: {yamlStore.lastSnapshot.reason}"
          >↶ Undo {yamlStore.lastSnapshot.reason}</button
        >
      {/if}
      <span class="ml-2 flex items-center gap-1.5">
        <span class="h-2 w-2 rounded-full {dot}"></span>
        <span class="text-zinc-300">{status.msg}</span>
      </span>
      <div class="ml-auto flex gap-2">
        <button
          class="rounded border border-zinc-700 px-2 py-0.5 hover:bg-zinc-800"
          onclick={runValidate}>Validate</button
        >
        <button
          class="rounded border border-zinc-700 px-2 py-0.5 hover:bg-zinc-800"
          onclick={runCompile}>Compile</button
        >
        <button
          class="rounded border border-zinc-700 px-2 py-0.5 hover:bg-zinc-800"
          onclick={pushNow}>Push</button
        >
        <button
          class="rounded border border-orange-900 bg-orange-950/50 px-2 py-0.5 text-orange-200 hover:bg-orange-900/40"
          onclick={pushAndRun}>Push & Run</button
        >
      </div>
    </div>

    <!-- Editor -->
    <div class="min-h-0 flex-1">
      <MonacoYaml value={yaml} onInput={(v) => (yaml = v)} {markers} />
    </div>

    <!-- Output drawer -->
    <div class="border-t border-zinc-800 bg-zinc-950/60">
      <div class="flex items-center gap-1 border-b border-zinc-800 px-2 text-xs">
        <button
          class={'border-b-2 px-2 py-1 ' +
            (drawerTab === 'diagnostics' && drawerOpen
              ? 'border-zinc-300 text-zinc-100'
              : 'border-transparent text-zinc-400 hover:text-zinc-200')}
          onclick={() => {
            drawerTab = 'diagnostics';
            drawerOpen = true;
          }}
        >
          Diagnostics
          {#if errCount}<span class="ml-1 rounded bg-red-900/60 px-1 text-red-200">{errCount}</span
            >{/if}
          {#if warnCount}<span class="ml-1 rounded bg-yellow-900/60 px-1 text-yellow-200"
              >{warnCount}</span
            >{/if}
        </button>
        <button
          class={'border-b-2 px-2 py-1 ' +
            (drawerTab === 'compile' && drawerOpen
              ? 'border-zinc-300 text-zinc-100'
              : 'border-transparent text-zinc-400 hover:text-zinc-200')}
          onclick={() => {
            drawerTab = 'compile';
            drawerOpen = true;
          }}>Compile output</button
        >
        <button
          class={'border-b-2 px-2 py-1 ' +
            (drawerTab === 'push' && drawerOpen
              ? 'border-zinc-300 text-zinc-100'
              : 'border-transparent text-zinc-400 hover:text-zinc-200')}
          onclick={() => {
            drawerTab = 'push';
            drawerOpen = true;
          }}>Push log</button
        >
        <button
          class={'border-b-2 px-2 py-1 ' +
            (drawerTab === 'run' && drawerOpen
              ? 'border-zinc-300 text-zinc-100'
              : 'border-transparent text-zinc-400 hover:text-zinc-200')}
          onclick={() => {
            drawerTab = 'run';
            drawerOpen = true;
          }}
        >
          Run log
          {#if runStore.status === 'running' || runStore.status === 'pushing'}
            <span class="ml-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-yellow-400"
            ></span>
          {/if}
        </button>
        <button
          class="ml-auto flex items-center gap-1 rounded border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          onclick={() => (drawerOpen = !drawerOpen)}
          title={drawerOpen ? 'collapse drawer' : 'expand drawer'}
        >
          <span class="text-sm">{drawerOpen ? '▾' : '▴'}</span>
          <span>{drawerOpen ? 'collapse' : 'expand'}</span>
        </button>
      </div>
      {#if drawerOpen}
        <div class="h-96 overflow-auto px-4 py-3 text-sm">
          {#if drawerTab === 'diagnostics'}
            {#if !markers.length}
              <div class="text-zinc-500">No diagnostics. The YAML parses, resolves, and validates clean.</div>
            {:else}
              <ul class="space-y-1.5">
                {#each markers as m}
                  <li class="rounded border border-zinc-800 p-2">
                    <div class="flex items-center gap-2">
                      <span
                        class={'rounded px-1.5 py-0.5 text-[10px] uppercase ' +
                          (m.severity === 'error'
                            ? 'bg-red-900/60 text-red-200'
                            : m.severity === 'warning'
                              ? 'bg-yellow-900/60 text-yellow-200'
                              : 'bg-zinc-800 text-zinc-300')}>{m.severity}</span
                      >
                      <span class="text-zinc-500">L{m.line}</span>
                      <span class="font-mono text-zinc-400">{m.code}</span>
                      {#if m.path}<span class="text-zinc-600">· {m.path}</span>{/if}
                    </div>
                    <div class="mt-1 text-zinc-200">{m.message}</div>
                    {#if m.suggestion}
                      <div class="mt-1 text-zinc-400">→ {m.suggestion}</div>
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          {:else if drawerTab === 'compile'}
            {#if compileJson}
              <pre class="whitespace-pre-wrap font-mono text-[13px] text-zinc-200">{compileJson}</pre>
            {:else}
              <div class="text-zinc-500">Click Compile to produce the FSR JSON.</div>
            {/if}
          {:else if drawerTab === 'push'}
            {#if runStore.pushOutput}
              <pre
                class="whitespace-pre-wrap font-mono text-[13px] text-zinc-200">{runStore.pushOutput}</pre>
            {:else}
              <div class="text-zinc-500">
                Push uses the FSRPlaybookYaml CLI to PUT/POST your compiled
                collection at <code>/api/3/workflow_collections/&lt;uuid&gt;</code>. Requires the
                <code>.env</code>'s FSR_BASE_URL + creds (set already if FSR pill is green).
              </div>
            {/if}
          {:else if drawerTab === 'run'}
            {#if runStore.logs.length}
              <pre
                class="whitespace-pre-wrap font-mono text-[13px] text-zinc-200">{runStore.logs.join('\n')}</pre>
              {#if runStore.taskId}
                <div class="mt-2 text-zinc-500">
                  task_id <span class="font-mono">{runStore.taskId}</span> · open the Run tab for
                  the env viewer
                </div>
              {/if}
            {:else}
              <div class="text-zinc-500">
                Push & Run pushes first, then triggers the playbook via
                <code>fsrpb run-playbook --follow</code>. Output streams here.
              </div>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  </div>

  <aside class="flex min-h-0 flex-col">
    {#if replayBanner}
      <div class="flex items-center justify-between border-b border-amber-700/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-200">
        <span>↻ {replayBanner}</span>
        <button
          onclick={exitReplay}
          class="rounded border border-amber-700/60 px-2 py-0.5 hover:border-amber-500 hover:text-amber-50"
          title="Clear replay and start fresh"
        >
          Exit replay
        </button>
      </div>
    {/if}
    <Chat
      currentYaml={yaml}
      onYamlReplace={(y) => (yaml = y)}
      initialTurns={replayTurns}
    />
  </aside>
</div>
