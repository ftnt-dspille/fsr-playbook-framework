<script lang="ts">
  import MonacoYaml from '$lib/components/MonacoYaml.svelte';
  import Chat from '$lib/components/Chat.svelte';
  import EditWorkspace from '$lib/components/EditWorkspace.svelte';
  import PlaybookHeader from '$lib/components/PlaybookHeader.svelte';
  import BuildBar from '$lib/components/BuildBar.svelte';
  import DiagnosticsDrawer from '$lib/components/DiagnosticsDrawer.svelte';
  import { visualStore } from '$lib/visualEditStore.svelte';
  import { playbookStore } from '$lib/playbookStore.svelte';
  import { playbookActions } from '$lib/playbookActions.svelte';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { messagesToTurns, type ReplayTurn } from '$lib/sessionReplay';
  import { commands, modPressed, fmtHotkey } from '$lib/commands.svelte';
  import { installKeybindings } from '$lib/keybindings';
  import CommandPalette from '$lib/components/CommandPalette.svelte';
  import ShortcutHelp from '$lib/components/ShortcutHelp.svelte';

  // Active-doc sync + debounced autosave + auto-verify all live on
  // `playbookStore`. Registering them here scopes the effects to this
  // component's lifecycle. The test harness calls the same hook so the
  // effect graph stays single-sourced.
  playbookStore.bindAutosave({
    getLatestYaml: getActiveYaml,
    onActiveLoaded: (yaml) => {
      // Push freshly-loaded drafts into visualStore so flipping to
      // Design shows the right canvas. Fire-and-forget — parse errors
      // are surfaced by the canvas itself.
      void visualStore.loadFromYaml(yaml).catch(() => {});
    }
  });

  function onYamlInput(v: string) { playbookStore.replaceYaml(v, 'monaco'); }

  /** Flush hook for PlaybookHeader.save(): grab the freshest YAML from
   *  whichever mode is active. In Design, flushing dirty canvas edits
   *  pushes the rendered YAML into `playbookStore` via `renderToYaml`,
   *  so the canonical read is always `playbookStore.currentYaml`. */
  async function getActiveYaml(): Promise<string> {
    if (mode === 'design' && visualStore.state.graph && visualStore.state.dirty) {
      await visualStore.renderToYaml();
    }
    return playbookStore.currentYaml;
  }

  // Replay mode: when the URL carries `?session=<id>`, hydrate the
  // editor + chat with the saved transcript so the user can see how
  // the original conversation played out. Replay is read-only on the
  // chat side — sending a new message starts a fresh session.
  let replayTurns = $state<ReplayTurn[]>([]);
  let replayBanner = $state<string | null>(null);

  // First-visit greeting: when Chat opens with no replay session, seed
  // a single assistant turn so the panel isn't a blank prompt-and-pray.
  // Using `as any` because the Chat component owns its richer Turn shape
  // (segments + tools + push); this lightweight greeting only needs the
  // shared `role` + `text` fields ReplayTurn already covers.
  const GREETING_TURNS: ReplayTurn[] = [
    {
      role: 'assistant',
      text:
        "Hi — I'm here to help you author FortiSOAR playbooks.\n\n" +
        "I've loaded a sample playbook on the canvas to get you started. " +
        "You can:\n" +
        "  • describe what you want and I'll write/edit YAML for you,\n" +
        "  • ask me to compile, validate, or push the current draft,\n" +
        "  • or paste an existing FSR playbook and I'll explain it.\n\n" +
        "Switch to Design at any time to see the visual graph."
    } as ReplayTurn
  ];

  /** Pick the freshest turn list for Chat: replay turns when a session
   * is being replayed (banner non-null), greeting turns on first
   * visit, empty list once the user has typed something. */
  let chatInitialTurns = $derived(
    replayTurns.length > 0 ? replayTurns : GREETING_TURNS
  );

  // Studio top-level mode toggle: Design (visual canvas) or CLI
  // (chat-driven YAML authoring + console). The legacy `/edit` route
  // redirects here with `?mode=design`. Default is Design.
  let mode: 'design' | 'cli' = $state('design');
  let modeError: string | null = $state(null);
  let switching = $state(false);

  /** Sync the active YAML across stores when toggling mode so the
   *  same playbook follows the user between Design (canvas) and CLI
   *  (Monaco). The canonical buffer is `playbookStore.currentYaml`; on
   *  Design→CLI we flush any unsaved canvas edits into it. */
  async function setMode(target: 'design' | 'cli') {
    if (target === mode || switching) return;
    modeError = null;
    switching = true;
    try {
      if (target === 'cli') {
        // Design → CLI: render any unsaved canvas edits — renderToYaml
        // writes straight into the canonical buffer.
        if (visualStore.state.graph && visualStore.state.dirty) {
          await visualStore.renderToYaml();
        }
      } else {
        // CLI → Design: push the canonical buffer through the parser
        // into visualStore so the canvas reflects it.
        const text = playbookStore.currentYaml;
        if (text) {
          const r = await visualStore.loadFromYaml(text);
          if (!r.ok) { modeError = r.message ?? 'parse failed'; return; }
        }
      }
      mode = target;
      const url = target === 'cli' ? '/?mode=cli' : '/';
      if (typeof history !== 'undefined') history.replaceState(null, '', url);
    } finally {
      switching = false;
    }
  }

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const m = params.get('mode');
    if (m === 'cli') mode = 'cli';
    else if (m === 'design' || m === 'edit') mode = 'design';

    // Refresh-aware autoload. PlaybookHeader runs its own refresh on
    // mount; wait one tick so its bucket lists are populated, then:
    //   1. prefer the playbook the user was last editing (persisted by
    //      `playbookStore.open`),
    //   2. fall back to the most recently modified draft,
    //   3. fall back to the first example for true first-visit users.
    // Any branch is skipped when the user already has something active
    // (e.g. arrived via a deep link / replay session).
    setTimeout(async () => {
      if (playbookStore.state.active) return;

      // PlaybookHeader's bucket refresh is async; on cold-boot it may not
      // have populated state.drafts/examples by 50ms. Poll up to ~3s so
      // the auto-open below sees real lists instead of empty fallbacks
      // (otherwise a returning user lands on the welcome empty state).
      const deadline = Date.now() + 3000;
      while (
        Date.now() < deadline &&
        playbookStore.state.drafts.length === 0 &&
        playbookStore.state.examples.length === 0
      ) {
        await new Promise((r) => setTimeout(r, 50));
      }
      if (playbookStore.state.active) return;

      const last = playbookStore.readLastOpened();
      if (last) {
        // The pointer can dangle (draft was deleted on another browser /
        // example was renamed). Validate against the live buckets first.
        const stillExists =
          last.kind === 'draft'
            ? playbookStore.state.drafts.some((d) => d.name === last.name)
            : playbookStore.state.examples.some((e) => e.name === last.name);
        if (stillExists) {
          await playbookStore.open(last.kind, last.name);
          return;
        }
      }

      // No (valid) pointer — open the most recently modified draft so a
      // dev-db restart or a fresh browser still lands the user on real
      // work instead of the welcome example.
      if (playbookStore.state.drafts.length > 0) {
        const newest = [...playbookStore.state.drafts].sort((a, b) =>
          (b.updated_ts ?? '').localeCompare(a.updated_ts ?? '')
        )[0];
        await playbookStore.open('draft', newest.name);
        return;
      }

      // True first-visit: drop on the first example so the canvas isn't blank.
      if (playbookStore.state.examples.length > 0) {
        await playbookStore.open('example', playbookStore.state.examples[0].name);
      }
    }, 50);

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
        // Persist as a server-side draft and make it active so Save
        // updates this draft in place rather than prompting.
        await playbookStore.createDraft(draftName, finalYaml);
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

  // Diagnostics / Fixes / Compile-JSON state lives on `playbookActions`
  // so Design and CLI share one source of truth (the BuildBar fires
  // actions, the DiagnosticsDrawer reads results). Markers also feed
  // the Monaco gutter when the user is on CLI.
  let drawerTab = $state<'diagnostics' | 'fixes' | 'deploy'>('diagnostics');
  // Monaco editor + namespace handles, populated via MonacoYaml's onEditor.
  // DiagnosticsList uses these to apply per-row fixes via executeEdits so
  // each fix lands in the editor's undo stack (Cmd-Z reverts cleanly).
  // Only the CLI-mounted Monaco populates these; in Design mode they
  // stay null and the per-row Apply buttons self-disable.
  let monacoEditor = $state<any>(null);
  let monacoNs = $state<any>(null);
  // Drawer starts collapsed so the canvas/Monaco gets the full viewport
  // on first paint. User opens it explicitly (Compile / Push / a marker
  // surfaces or via the Diagnostics tab in BuildBar).
  let drawerOpen = $state(false);
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

  // Auto-validate on every YAML edit, debounced. Drives the markers
   // surface for both Monaco's gutter and the diagnostics drawer.
  let debounceId: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    void playbookStore.currentYaml;
    if (debounceId) clearTimeout(debounceId);
    debounceId = setTimeout(() => playbookActions.validate(), 400);
  });

  function showDrawer(tab: 'diagnostics' | 'fixes' | 'deploy') {
    drawerTab = tab;
    drawerOpen = true;
  }

  // ---- Global keyboard shortcuts + command palette --------------------
  // Page-scope commands: navigation + run + help. Node-scope commands
  // (Delete / Test step) register from EditWorkspace where the
  // selection state lives. The keybindings module walks the registry
  // on every keydown and runs the first matcher.
  onMount(() => {
    const teardownKeys = installKeybindings();
    const teardownCmds = commands.registerMany([
      {
        id: 'palette.open',
        label: 'Open command palette',
        hotkey: fmtHotkey(['Mod', 'K']),
        group: 'Navigation',
        runInInputs: true,  // Cmd+K should work even while typing
        match: (ev) => modPressed(ev) && ev.key.toLowerCase() === 'k',
        run: () => { commands.paletteOpen = true; },
      },
      {
        id: 'modal.dismiss',
        label: 'Close palette / help',
        hotkey: 'Esc',
        group: 'Navigation',
        runInInputs: true,
        enabled: () => commands.paletteOpen || commands.helpOpen,
        match: (ev) => ev.key === 'Escape' && !modPressed(ev),
        run: () => {
          commands.paletteOpen = false;
          commands.helpOpen = false;
        },
      },
      {
        id: 'help.toggle',
        label: 'Show keyboard shortcuts',
        hotkey: '?',
        group: 'Help',
        // `?` is Shift+/ on most layouts; we only fire when no input is
        // focused (keybindings.ts already gates editable targets out
        // unless the command explicitly opts in).
        match: (ev) => !modPressed(ev) && !ev.altKey && ev.key === '?',
        run: () => { commands.helpOpen = !commands.helpOpen; },
      },
      {
        id: 'file.save',
        label: 'Save playbook',
        hotkey: fmtHotkey(['Mod', 'S']),
        group: 'File',
        runInInputs: true,  // Cmd+S should always save, even from Monaco
        match: (ev) => modPressed(ev) && ev.key.toLowerCase() === 's',
        enabled: () => !!playbookStore.state.active && !playbookStore.isExample,
        run: async () => {
          // Mirror PlaybookHeader.onSave: flush visual edits into the
          // canonical buffer first, then persist.
          try {
            const latest = await getActiveYaml();
            if (typeof latest === 'string') playbookStore.replaceYaml(latest);
          } catch {}
          await playbookStore.save({ reason: 'cmd+s' });
        },
      },
      {
        id: 'edit.undo',
        label: 'Undo',
        hotkey: fmtHotkey(['Mod', 'Z']),
        group: 'Edit',
        match: (ev) => modPressed(ev) && !ev.shiftKey && ev.key.toLowerCase() === 'z',
        enabled: () => visualStore.state.undoStack.length > 0,
        run: () => { visualStore.undo(); },
      },
      {
        id: 'edit.redo',
        label: 'Redo',
        hotkey: fmtHotkey(['Shift', 'Mod', 'Z']),
        group: 'Edit',
        match: (ev) => modPressed(ev) && ev.shiftKey && ev.key.toLowerCase() === 'z',
        enabled: () => visualStore.state.redoStack.length > 0,
        run: () => { visualStore.redo(); },
      },
      {
        id: 'run.push',
        label: 'Push playbook to FSR',
        hotkey: fmtHotkey(['Mod', 'Enter']),
        group: 'Run',
        match: (ev) => modPressed(ev) && ev.key === 'Enter',
        enabled: () => !!playbookStore.state.active,
        run: async () => { await playbookActions.push(); },
      },
      {
        id: 'nav.toggleMode',
        label: 'Toggle Design / CLI',
        hotkey: fmtHotkey(['Mod', '/']),
        group: 'Navigation',
        match: (ev) => modPressed(ev) && ev.key === '/',
        run: () => { void setMode(mode === 'design' ? 'cli' : 'design'); },
      },
      {
        id: 'nav.pickPlaybook',
        label: 'Open playbook picker',
        hotkey: fmtHotkey(['Mod', 'P']),
        group: 'Navigation',
        match: (ev) => modPressed(ev) && ev.key.toLowerCase() === 'p',
        run: () => {
          // PlaybookHeader owns the picker; emit a custom event it
          // listens for. Lightest-weight wire-up that doesn't require
          // lifting picker state to the page.
          window.dispatchEvent(new CustomEvent('fsrpb:open-playbook-picker'));
        },
      },
    ]);
    return () => { teardownKeys(); teardownCmds(); };
  });

</script>

<div class="flex h-full flex-col">
<PlaybookHeader
  {getActiveYaml}
  {mode}
  modeBusy={switching}
  onModeChange={setMode}
/>
{#if modeError}
  <div class="border-b border-red-300 bg-red-50 px-4 py-1 text-[11px] text-red-800">
    Mode switch failed: {modeError}
  </div>
{/if}

<div class="flex min-h-0 flex-1 flex-col">
  {#if mode === 'design'}
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <EditWorkspace onShowDrawer={showDrawer} />
    </div>
  {:else}
    <BuildBar onShowDrawer={showDrawer} />
    <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(320px,28rem)] overflow-hidden">
      <div class="flex min-h-0 flex-col border-r border-[var(--border-soft)]">
        <div class="min-h-0 flex-1">
          <MonacoYaml
            value={playbookStore.currentYaml}
            onInput={onYamlInput}
            markers={playbookActions.markers}
            onEditor={(ed, mn) => {
              monacoEditor = ed;
              monacoNs = mn;
            }}
          />
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
          currentYaml={playbookStore.currentYaml}
          onYamlReplace={onYamlInput}
          initialTurns={chatInitialTurns}
        />
      </aside>
    </div>
  {/if}

  <DiagnosticsDrawer
    open={drawerOpen}
    tab={drawerTab}
    heightPx={drawerHeightPx}
    onTabChange={(t) => { drawerTab = t; drawerOpen = true; }}
    onToggle={() => (drawerOpen = !drawerOpen)}
    onResize={startDrawerDrag}
    monacoEditor={mode === 'cli' ? monacoEditor : null}
    monacoNs={mode === 'cli' ? monacoNs : null}
    onYamlReplace={onYamlInput}
  />
</div>
</div>

<!-- Cmd+K palette + `?` shortcut help. Mounted at the page root so
     they overlay everything. Both subscribe to the same command
     registry, so newly-registered commands surface here automatically. -->
<CommandPalette />
<ShortcutHelp />
