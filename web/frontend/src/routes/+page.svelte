<script lang="ts">
  import MonacoYaml from '$lib/components/MonacoYaml.svelte';
  import Chat from '$lib/components/Chat.svelte';
  import ExamplesMenu from '$lib/components/ExamplesMenu.svelte';
  import DraftsMenu from '$lib/components/DraftsMenu.svelte';
  import Console from '$lib/components/Console.svelte';
  import DeployPanel from '$lib/components/DeployPanel.svelte';
  import DiagnosticsList from '$lib/components/DiagnosticsList.svelte';
  import FixesPanel from '$lib/components/FixesPanel.svelte';
  import { compileYaml, pushPlaybook, validateYaml, type Marker, type Fix } from '$lib/api';
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
      // Server-derived final YAML: push.source_yaml → last YAML-bearing
      // tool_use → last fenced ```yaml block. Save it as a draft so it
      // shows up in the Drafts menu and the editor tracks it (Save will
      // update-in-place rather than prompt).
      const finalYaml = detail.final_yaml as string | undefined;
      if (finalYaml && finalYaml.trim()) {
        const draftName = `Chat: ${detail.playbook_collection || sid.slice(0, 8)}`;
        yamlStore.appendDraftRevision(draftName, finalYaml, 'replay', {
          sessionId: sid,
          message: `replay of session ${sid}`,
        });
        // loadDraft both seeds the buffer and sets activeDraftName, so
        // Save updates this draft instead of prompting.
        yamlStore.loadDraft(draftName);
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
  let fixes = $state<Fix[]>([]);
  let compileJson = $state<string | null>(null);
  let drawerTab = $state<'diagnostics' | 'fixes' | 'compile' | 'deploy'>('diagnostics');
  // Monaco editor + namespace handles, populated via MonacoYaml's onEditor.
  // FixesPanel uses these to apply text edits with executeEdits so each
  // fix lands in the editor's own undo stack (Cmd-Z reverts cleanly).
  let monacoEditor = $state<any>(null);
  let monacoNs = $state<any>(null);
  let drawerOpen = $state(true);
  // User-resizable drawer height. Stored in px (clamped on every drag).
  // Defaults to ~55vh on first paint so there's room to read; persists
  // across reloads via localStorage.
  let drawerHeightPx = $state<number>(
    (() => {
      if (typeof localStorage === 'undefined' || typeof window === 'undefined') return 480;
      const saved = Number(localStorage.getItem('fsrpb.drawer.h') ?? '');
      if (Number.isFinite(saved) && saved >= 200) return saved;
      return Math.round(window.innerHeight * 0.55);
    })(),
  );
  $effect(() => {
    try { localStorage.setItem('fsrpb.drawer.h', String(drawerHeightPx)); } catch {}
  });

  function startDrawerDrag(e: PointerEvent) {
    e.preventDefault();
    const startY = e.clientY;
    const startH = drawerHeightPx;
    const minH = 160;
    const maxH = Math.max(240, window.innerHeight - 120);
    function onMove(ev: PointerEvent) {
      // Dragging UP (clientY decreases) should grow the drawer.
      const next = Math.min(maxH, Math.max(minH, startH + (startY - ev.clientY)));
      drawerHeightPx = next;
    }
    function onUp() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

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
      fixes = r.fixes ?? [];
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
    drawerTab = 'deploy';
    drawerOpen = true;
    try {
      const r = await pushPlaybook(yaml);
      // Merge stdout + stderr into one clean stream. Most fsrpb push
      // output goes to stderr (status lines), and the leading "[stderr]"
      // label was just visual noise when stdout was empty. Trim outer
      // whitespace so the console doesn't open with a blank top line.
      const out = (r.stdout || '').trim();
      const errBlock = (r.stderr || '').trim();
      runStore.pushOutput = [out, errBlock].filter(Boolean).join('\n');
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
    drawerTab = 'deploy';
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

  // Inline rename UI state — replaces window.prompt for first-save.
  let namingDraft = $state(false);
  let draftNameInput = $state('');
  let draftNameInputEl = $state<HTMLInputElement | null>(null);

  function saveCurrentDraft() {
    // If the buffer is already tracking a draft (loaded from drafts menu
    // or saved earlier this session), update it in place — no prompt.
    if (yamlStore.activeDraftName) {
      try {
        const d = yamlStore.saveDraft(yamlStore.activeDraftName);
        status = { kind: 'ok', msg: `saved draft: ${d.name}` };
      } catch (e: any) {
        status = { kind: 'err', msg: e?.message ?? String(e) };
      }
      return;
    }
    // Fresh canvas — open the inline naming row instead of window.prompt.
    draftNameInput = yamlStore.suggestedName();
    namingDraft = true;
    queueMicrotask(() => draftNameInputEl?.focus());
  }

  function commitDraftName() {
    const name = draftNameInput.trim();
    if (!name) {
      namingDraft = false;
      return;
    }
    try {
      const d = yamlStore.saveDraft(name);
      status = { kind: 'ok', msg: `saved draft: ${d.name}` };
      namingDraft = false;
    } catch (e: any) {
      status = { kind: 'err', msg: e?.message ?? String(e) };
    }
  }

  function onDraftNameKey(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitDraftName();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      namingDraft = false;
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
          : 'bg-[var(--text-faint)]'
  );

  const errCount = $derived(markers.filter((m) => m.severity === 'error').length);
  const warnCount = $derived(markers.filter((m) => m.severity === 'warning').length);
</script>

<div class="grid h-full grid-cols-[minmax(0,1fr)_minmax(320px,28rem)]">
  <div class="flex min-h-0 flex-col border-r border-[var(--border-soft)]">
    <!-- Toolbar -->
    <div class="flex flex-wrap items-center gap-2 border-b border-[var(--border-soft)] px-3 py-1.5 text-xs">
      <ExamplesMenu onLoad={loadExampleText} />
      <DraftsMenu onLoad={loadDraftText} />
      {#if namingDraft}
        <input
          bind:this={draftNameInputEl}
          bind:value={draftNameInput}
          onkeydown={onDraftNameKey}
          onblur={commitDraftName}
          placeholder="Draft name…"
          class="rounded border border-[var(--border)] bg-[var(--bg-panel)] px-2 py-0.5 text-[var(--text-default)] focus:outline-none focus:ring-1 focus:ring-zinc-600"
          size="22"
        />
      {:else}
        <button
          class="rounded border border-[var(--border)] px-2 py-0.5 text-[var(--text-default)] hover:bg-[var(--bg-elevated)]"
          onclick={saveCurrentDraft}
          title={yamlStore.activeDraftName
            ? `Update draft: ${yamlStore.activeDraftName}`
            : 'Save current YAML as a named draft (stored in this browser)'}
        >
          {yamlStore.activeDraftName ? `Save · ${yamlStore.activeDraftName}` : 'Save'}
        </button>
      {/if}
      <button
        class="rounded border border-[var(--border-soft)] px-2 py-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-panel)]"
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
        <span class="text-[var(--text-muted)]">{status.msg}</span>
      </span>
      <div class="ml-auto flex gap-2">
        <button
          class="rounded border border-[var(--border)] px-2 py-0.5 hover:bg-[var(--bg-elevated)]"
          onclick={runValidate}>Validate</button
        >
        <button
          class="rounded border border-[var(--border)] px-2 py-0.5 hover:bg-[var(--bg-elevated)]"
          onclick={runCompile}>Compile</button
        >
        <button
          class="rounded border border-[var(--border)] px-2 py-0.5 hover:bg-[var(--bg-elevated)]"
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
      <MonacoYaml
        value={yaml}
        onInput={(v) => (yaml = v)}
        {markers}
        onEditor={(ed, mn) => {
          monacoEditor = ed;
          monacoNs = mn;
        }}
      />
    </div>

    <!-- Output drawer -->
    <div class="border-t border-[var(--border-soft)] bg-[var(--bg-panel)]">
      {#if drawerOpen}
        <!-- Drag handle: pull up to grow the drawer, down to shrink. -->
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize output drawer"
          class="group relative flex h-1.5 cursor-ns-resize items-center justify-center bg-transparent hover:bg-[var(--brand)]/20"
          onpointerdown={startDrawerDrag}
        >
          <span class="h-0.5 w-12 rounded-full bg-[var(--border)] group-hover:bg-[var(--brand)]"></span>
        </div>
      {/if}
      <div class="flex items-center gap-1 border-b border-[var(--border-soft)] px-2 py-1.5">
        {#each [
          { id: 'diagnostics', label: 'Diagnostics' },
          { id: 'fixes', label: 'Fixes' },
          { id: 'compile', label: 'Compile' },
          { id: 'deploy', label: 'Deploy' }
        ] as t}
          {@const active = drawerTab === t.id && drawerOpen}
          <button
            class={'group relative flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ' +
              (active
                ? 'bg-[var(--bg-elevated)] text-[var(--text-default)] shadow-[0_0_0_1px_var(--border)]'
                : 'text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]/50 hover:text-[var(--text-default)]')}
            onclick={() => {
              drawerTab = t.id as typeof drawerTab;
              drawerOpen = true;
            }}
          >
            <span>{t.label}</span>
            {#if t.id === 'fixes' && fixes.length}
              <span class="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-emerald-200">{fixes.length}</span>
            {:else if t.id === 'diagnostics'}
              {#if errCount}
                <span class="rounded-md border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-rose-300">{errCount}</span>
              {/if}
              {#if warnCount}
                <span class="rounded-md border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-amber-200">{warnCount}</span>
              {/if}
            {:else if t.id === 'deploy' && (runStore.status === 'running' || runStore.status === 'pushing')}
              <span class="relative flex h-1.5 w-1.5">
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-70"></span>
                <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-400"></span>
              </span>
            {/if}
          </button>
        {/each}
        <button
          class="ml-auto flex items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-muted)] hover:border-[var(--text-faint)] hover:text-[var(--text-default)]"
          onclick={() => (drawerOpen = !drawerOpen)}
          title={drawerOpen ? 'collapse drawer' : 'expand drawer'}
          aria-expanded={drawerOpen}
        >
          <svg viewBox="0 0 12 12" class="h-2.5 w-2.5 transition-transform {drawerOpen ? '' : 'rotate-180'}" fill="currentColor" aria-hidden="true">
            <path d="M2 7.5l4-3 4 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
          <span>{drawerOpen ? 'Collapse' : 'Expand'}</span>
        </button>
      </div>
      {#if drawerOpen}
        <div class="fade-in" style="height: {drawerHeightPx}px">
          {#if drawerTab === 'diagnostics'}
            <div class="h-full overflow-auto">
              <DiagnosticsList {markers} />
            </div>
          {:else if drawerTab === 'fixes'}
            <div class="h-full overflow-hidden">
              <FixesPanel
                {fixes}
                editor={monacoEditor}
                monaco={monacoNs}
                onApplied={(v) => (yaml = v)}
              />
            </div>
          {:else if drawerTab === 'compile'}
            <Console
              text={compileJson ?? ''}
              emptyTitle="No compile output yet"
              emptyHint="Press Compile to produce the FortiSOAR JSON the wire format pushes to /api/3/workflow_collections."
            />
          {:else if drawerTab === 'deploy'}
            <DeployPanel />
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
