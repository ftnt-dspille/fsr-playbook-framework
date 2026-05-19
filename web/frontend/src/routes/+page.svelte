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
  import { yamlStore } from '$lib/yamlStore.svelte';
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

  // playbookStore is the unified active-document source. When the user
  // picks a playbook in the PlaybookHeader, mirror the YAML into the
  // legacy yamlStore (which Chat / DiagnosticsList / DeployPanel read)
  // so existing wiring keeps working without a wholesale refactor.
  // Tracks `playbookStore.state.active?.name` as the change key so we
  // only sync on document change, not on every keystroke (which would
  // fight the user-edit effect above).
  let lastSyncedKey: string | null = $state(null);
  $effect(() => {
    const a = playbookStore.state.active;
    const key = a ? `${a.kind}:${a.name}` : null;
    if (key === lastSyncedKey) return;
    lastSyncedKey = key;
    if (a) {
      yamlStore.setText(a.yaml, `loaded ${a.kind}: ${a.name}`);
      yaml = a.yaml;
      // Push into visualStore too so flipping to Design shows the
      // newly-picked playbook on the canvas instead of whatever was
      // loaded last. Fire-and-forget — parse errors are surfaced by
      // the canvas itself.
      void visualStore.loadFromYaml(a.yaml).catch(() => {});
    }
  });

  // Debounced auto-save: visual canvas edits (or any other source that
  // flips a `dirty` flag) get flushed → playbookStore → backend after
  // ~1 s of quiet. Without this, refreshing the page loses every edit
  // since visualStore.save() was never wired to a UI button. We don't
  // touch read-only example docs; they must be cloned first.
  let autosaveTimer: ReturnType<typeof setTimeout> | null = null;
  let autosaveInFlight = false;
  $effect(() => {
    // Track all the dirty sources so any of them rearms the timer.
    const dirty = visualStore.state.dirty || playbookStore.dirty;
    const active = playbookStore.state.active;
    if (!dirty || !active || active.kind === 'example') return;
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(async () => {
      if (autosaveInFlight) return;
      autosaveInFlight = true;
      try {
        const latest = await getActiveYaml();
        if (typeof latest === 'string') playbookStore.setYaml(latest);
        await playbookStore.save({ reason: 'autosave', auto: true });
        // Clear visualStore's dirty flag once persisted — otherwise a
        // second mutation right after a save doesn't re-arm this effect
        // (dirty was already true → no state change → no re-run), so
        // the second change would sit unsaved until the next dirty
        // toggle. visualStore doesn't clear it itself because edit ops
        // only ever set true.
        visualStore.state.dirty = false;
        // Refresh render-path diagnostics so badges, the drawer, and
        // the toolbar pill reflect the just-saved buffer. Fire-and-
        // forget — the UI surfaces it reactively when it lands. Skip
        // when already running so a rapid second autosave doesn't
        // pile up overlapping analyze calls.
        if (!playbookActions.analyzeBusy) {
          void playbookActions.analyze();
        }
      } catch {
        // Surface via the normal error channels; manual save still
        // available if the user wants to retry.
      } finally {
        autosaveInFlight = false;
      }
    }, 1000);
  });

  /** Flush hook for PlaybookHeader.save(): grab the freshest YAML from
   * whichever mode is active so the buffer doesn't lag behind the UI. */
  async function getActiveYaml(): Promise<string> {
    if (mode === 'design' && visualStore.state.graph) {
      const rendered = visualStore.state.dirty
        ? await visualStore.renderToYaml()
        : null;
      return rendered ?? visualStore.state.graph.source.yaml;
    }
    return yamlStore.text;
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

  /** Sync the active YAML across the two stores when toggling mode so
   * the same playbook follows the user. Without this, Design loads
   * from `/api/visual/list` and CLI reads `yamlStore.text` — two
   * disconnected buckets. */
  async function setMode(target: 'design' | 'cli') {
    if (target === mode || switching) return;
    modeError = null;
    switching = true;
    try {
      if (target === 'cli') {
        // Design → CLI: pull current visual graph YAML into yamlStore
        // (rendering through the emitter when there are unsaved canvas
        // edits so CLI sees the latest).
        if (visualStore.state.graph) {
          const rendered = visualStore.state.dirty
            ? await visualStore.renderToYaml()
            : null;
          const next = rendered ?? visualStore.state.graph.source.yaml;
          if (next && next !== yamlStore.text) {
            yamlStore.setText(next, 'switch from Design');
            yaml = next;
          }
        }
      } else {
        // CLI → Design: push the CLI buffer through the parser into
        // visualStore so the canvas reflects it. Fall back gracefully
        // when the buffer is empty/placeholder.
        const text = yamlStore.text;
        const current = visualStore.state.graph?.source.yaml;
        if (text && text !== current) {
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

    // One-time migration: copy any localStorage drafts into the server
    // drafts table so they show up in PlaybookHeader's bucketed picker
    // alongside Design's drafts. The migration flag lives in localStorage
    // so we only run it once per browser. Existing server drafts with
    // the same name win (we don't overwrite); migration is best-effort
    // and logs to status on failure rather than blocking page mount.
    if (typeof localStorage !== 'undefined' && !localStorage.getItem('fsrpb.drafts.migrated_v1')) {
      try {
        const r = await playbookStore.migrateLocalDrafts(yamlStore.drafts);
        if (r.migrated > 0) {
          // Surface the migration count through the shared status pill
          // (BuildBar reads playbookActions.status). The user sees
          // `migrated N local draft(s)` once and can move on.
          playbookActions.state.status = {
            kind: 'ok',
            msg: `migrated ${r.migrated} local draft${r.migrated === 1 ? '' : 's'}`
          };
        }
        localStorage.setItem('fsrpb.drafts.migrated_v1', new Date().toISOString());
      } catch (e) {
        console.warn('localStorage drafts migration failed:', e);
      }
    }

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

  // Diagnostics / Fixes / Compile-JSON state lives on `playbookActions`
  // so Design and CLI share one source of truth (the BuildBar fires
  // actions, the DiagnosticsDrawer reads results). Markers also feed
  // the Monaco gutter when the user is on CLI.
  let drawerTab = $state<'diagnostics' | 'fixes' | 'compile' | 'deploy' | 'debug'>('diagnostics');
  // Monaco editor + namespace handles, populated via MonacoYaml's onEditor.
  // FixesPanel uses these to apply text edits with executeEdits so each
  // fix lands in the editor's own undo stack (Cmd-Z reverts cleanly).
  // Only the CLI-mounted Monaco populates these; in Design mode they
  // stay null and DiagnosticsDrawer disables the Fixes apply button.
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
    void yaml;
    if (debounceId) clearTimeout(debounceId);
    debounceId = setTimeout(() => playbookActions.validate(), 400);
  });

  function showDrawer(tab: 'diagnostics' | 'fixes' | 'compile' | 'deploy' | 'debug') {
    drawerTab = tab;
    drawerOpen = true;
  }

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
            value={yaml}
            onInput={(v) => (yaml = v)}
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
          currentYaml={yaml}
          onYamlReplace={(y) => (yaml = y)}
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
    onYamlReplace={(v) => (yaml = v)}
  />
</div>
</div>
