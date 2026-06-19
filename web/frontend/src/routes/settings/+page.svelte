<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getProviders, patchProvider, testProvider, listProviderModels, setActiveProvider,
    type ProvidersResponse, type ProviderView
  } from '$lib/api';

  import PageHeader from '$lib/components/PageHeader.svelte';
  import ThemeSwitcher from '$lib/components/ThemeSwitcher.svelte';
  let snapshot = $state<ProvidersResponse | null>(null);
  let loading = $state(false);
  let err = $state<string | null>(null);
  let selected = $state<string>('lmstudio');

  // Form state — separate from saved snapshot so the user can probe
  // before clobbering config.
  let formBase = $state('');
  let formKey = $state('');
  let formModel = $state('');
  let testStatus = $state<'idle' | 'testing' | 'ok' | 'fail'>('idle');
  let testMsg = $state<string>('');
  let models = $state<string[]>([]);
  let modelsErr = $state<string | null>(null);
  let saveMsg = $state<string>('');

  async function refresh() {
    loading = true;
    err = null;
    try {
      snapshot = await getProviders();
      // Default `selected` to whichever provider is currently active
      // server-side, falling back to whatever the user already chose.
      // Without this the page mounted on a hardcoded "lmstudio" even
      // when the user had been using Anthropic — the form looked
      // empty/stale and any model-list fetch hit the wrong backend.
      const active = snapshot.active_provider;
      if (active && snapshot.providers[active]) {
        selected = active;
      } else if (!snapshot.providers[selected]) {
        // The hardcoded default isn't registered (e.g. headless
        // install). Fall back to the first provider the server knows.
        const first = Object.keys(snapshot.providers)[0];
        if (first) selected = first;
      }
      hydrateForm();
      // Auto-probe the saved config so the user sees whether the
      // stored key/URL is currently valid the moment they open the
      // page. No button — explicit `Test` was misleading (the form
      // value could pass while the saved key was rejected).
      void runLiveCheck();
    } catch (e: any) {
      err = e?.message ?? String(e);
    } finally {
      loading = false;
    }
  }

  async function runLiveCheck() {
    if (!snapshot?.providers[selected]?.configured) {
      testStatus = 'idle';
      testMsg = '';
      return;
    }
    testStatus = 'testing';
    testMsg = '';
    try {
      // No form overrides — probe whatever is *actually* saved so the
      // status reflects what `/api/chat` would use.
      const result = await testProvider(selected, {});
      if (result.ok) {
        testStatus = 'ok';
        testMsg = result.latency_ms != null
          ? `Saved credentials reachable (${result.latency_ms} ms)${result.note ? ' — ' + result.note : ''}`
          : (result.note ?? 'Saved credentials reachable.');
      } else {
        testStatus = 'fail';
        testMsg = result.error ?? 'unknown error';
      }
    } catch (e: any) {
      testStatus = 'fail';
      testMsg = e?.message ?? String(e);
    }
  }

  function hydrateForm() {
    if (!snapshot) return;
    const p = snapshot.providers[selected];
    if (!p) return;
    formBase = p.base_url ?? '';
    formKey = '';  // never round-tripped; user types fresh or leaves blank
    formModel = p.model ?? '';
  }

  function changeProvider(name: string) {
    selected = name;
    testStatus = 'idle';
    testMsg = '';
    saveMsg = '';
    models = [];
    modelsErr = null;
    hydrateForm();
    void runLiveCheck();
  }

  async function save() {
    saveMsg = 'saving…';
    try {
      const patch: any = {
        base_url: formBase || undefined,
        model: formModel || undefined
      };
      if (formKey) patch.api_key = formKey;
      await patchProvider(selected, patch);
      saveMsg = 'saved';
      formKey = '';  // wipe the typed key so it's not lingering in the DOM
      await refresh();
    } catch (e: any) {
      saveMsg = `save failed: ${e?.message ?? String(e)}`;
    }
  }

  async function loadModels() {
    modelsErr = null;
    try {
      const r = await listProviderModels(selected, {
        base_url: formBase || undefined,
        api_key: formKey || undefined
      });
      if (r.ok) {
        models = r.models;
        if (formModel === '' && models.length > 0) formModel = models[0];
      } else {
        models = [];
        modelsErr = r.error ?? 'unknown error';
      }
    } catch (e: any) {
      modelsErr = e?.message ?? String(e);
    }
  }

  let confirmingClearKey = $state(false);

  function askClearKey() {
    confirmingClearKey = true;
  }
  async function confirmClearKey() {
    confirmingClearKey = false;
    await patchProvider(selected, { clear_api_key: true });
    await refresh();
  }
  function cancelClearKey() {
    confirmingClearKey = false;
  }

  async function makeActive() {
    if (!formModel) {
      saveMsg = 'pick a model first';
      return;
    }
    await setActiveProvider(selected, formModel);
    saveMsg = 'set as active';
    await refresh();
  }

  onMount(refresh);

  const current = $derived<ProviderView | null>(
    snapshot ? snapshot.providers[selected] ?? null : null
  );
  const isActive = $derived(snapshot?.active_provider === selected);
</script>

<div class="flex h-full flex-col text-[var(--text-default)]">
  <PageHeader
    eyebrow="Configuration"
    title="Settings"
    subtitle="Configure which LLM the chat uses. Keys are stored in your OS secret store ({snapshot?.secrets?.backend ?? '…'}), never in the browser."
  />
  <div class="mx-auto w-full max-w-3xl flex-1 overflow-auto p-6 fade-in">

  <!-- Quick links to reference pages that used to live in the top nav.
       Capabilities + Docs got demoted (rare-use); keeping them in the
       top nav cluttered the chrome for everyone. -->
  <section class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
    <a href="/capabilities" class="rounded-md border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-2 text-xs hover:bg-[var(--bg-canvas)]">
      <div class="font-medium text-[var(--text-default)]">Capabilities</div>
      <div class="mt-0.5 text-[10px] text-[var(--text-faint)]">FSR connectors / step types / picklists indexed in the reference store.</div>
    </a>
    <a href="/docs" class="rounded-md border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-2 text-xs hover:bg-[var(--bg-canvas)]">
      <div class="font-medium text-[var(--text-default)]">Docs</div>
      <div class="mt-0.5 text-[10px] text-[var(--text-faint)]">Studio reference + authoring guides.</div>
    </a>
    <div class="flex items-center justify-between rounded-md border border-[var(--border-soft)] bg-[var(--bg-elev)] px-3 py-2 text-xs">
      <div>
        <div class="font-medium text-[var(--text-default)]">Theme</div>
        <div class="mt-0.5 text-[10px] text-[var(--text-faint)]">Editor color scheme.</div>
      </div>
      <ThemeSwitcher />
    </div>
  </section>

  {#if err}
    <div class="mb-4 rounded border border-red-700 bg-red-900/40 p-3 text-sm">
      {err}
    </div>
  {/if}

  {#if snapshot && !snapshot.secrets.ok}
    <div class="mb-4 rounded border border-yellow-700 bg-yellow-900/30 p-3 text-sm">
      <strong>Secret store unavailable:</strong> {snapshot.secrets.backend}.
      On a headless Linux box, install <code>gnome-keyring</code> or set
      <code>FSR_STUDIO_SECRETS_FALLBACK=encrypted_file</code>.
    </div>
  {/if}

  <div class="mb-6 flex gap-2">
    {#each Object.values(snapshot?.providers ?? {}) as p (p.name)}
      <button
        type="button"
        onclick={() => changeProvider(p.name)}
        class="rounded border px-3 py-1.5 text-sm
               {selected === p.name
                 ? 'border-[var(--brand)] bg-[var(--bg-elevated)]'
                 : 'border-[var(--border)] hover:bg-[var(--bg-panel)]'}"
      >
        {p.name}
        {#if snapshot?.active_provider === p.name}
          <span class="ml-1 rounded bg-green-700 px-1.5 text-xs">active</span>
        {:else if p.configured}
          <span class="ml-1 rounded bg-[var(--border)] px-1.5 text-xs">ready</span>
        {/if}
      </button>
    {/each}
  </div>

  {#if current}
    <div class="space-y-5 rounded border border-[var(--border-soft)] bg-[var(--bg-panel)]/50 p-5">
      {#if selected === 'lmstudio'}
        <label class="block">
          <span class="mb-1 block text-sm text-[var(--text-muted)]">Base URL</span>
          <input
            type="text"
            bind:value={formBase}
            placeholder="http://localhost:1234/v1"
            class="w-full rounded border border-[var(--border)] bg-[var(--bg-canvas)] px-3 py-2 text-sm font-mono"
          />
        </label>
      {/if}

      <label class="block">
        <span class="mb-1 block flex items-center justify-between text-sm text-[var(--text-muted)]">
          <span>API key</span>
          {#if current.api_key_set}
            {#if confirmingClearKey}
              <span class="flex items-center gap-1.5 text-xs">
                <span class="text-[var(--text-muted)]">Delete saved key?</span>
                <button type="button" onclick={confirmClearKey}
                  class="rounded border border-red-700/60 bg-red-900/40 px-1.5 py-0.5 text-red-200 hover:bg-red-900/60">
                  Yes
                </button>
                <button type="button" onclick={cancelClearKey}
                  class="rounded border border-[var(--border)] px-1.5 py-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-panel)]">
                  No
                </button>
              </span>
            {:else}
              <button type="button" onclick={askClearKey} class="text-xs text-[var(--text-muted)] underline hover:text-[var(--text-default)]">
                clear saved key
              </button>
            {/if}
          {/if}
        </span>
        <input
          type="password"
          bind:value={formKey}
          placeholder={current.api_key_set
            ? '•••••••••• (configured — type to replace)'
            : selected === 'lmstudio'
            ? 'lm-studio (placeholder; LM Studio ignores it)'
            : 'sk-ant-…'}
          class="w-full rounded border border-[var(--border)] bg-[var(--bg-canvas)] px-3 py-2 text-sm font-mono"
        />
      </label>

      <!-- Live status of the SAVED credentials. Runs automatically on
           page load, provider change, and after Save. No button — what
           the chat uses is the only thing worth showing. -->
      {#if current.configured}
        <div class="flex items-center gap-2 text-sm">
          {#if testStatus === 'testing'}
            <span class="text-[var(--text-muted)]">Checking saved credentials…</span>
          {:else if testStatus === 'ok'}
            <span class="text-green-400">✓ {testMsg}</span>
          {:else if testStatus === 'fail'}
            <span class="text-red-400">✗ {testMsg}</span>
          {/if}
        </div>
      {/if}

      <div class="border-t border-[var(--border-soft)] pt-4">
        <div class="flex items-center gap-3">
          <label class="flex-1 block">
            <span class="mb-1 block text-sm text-[var(--text-muted)]">Model</span>
            {#if models.length > 0}
              <select
                bind:value={formModel}
                class="w-full rounded border border-[var(--border)] bg-[var(--bg-canvas)] px-3 py-2 text-sm font-mono"
              >
                {#each models as m}
                  <option value={m}>{m}</option>
                {/each}
              </select>
            {:else}
              <input
                type="text"
                bind:value={formModel}
                placeholder={selected === 'lmstudio' ? 'load models to choose' : 'claude-sonnet-4-5-…'}
                class="w-full rounded border border-[var(--border)] bg-[var(--bg-canvas)] px-3 py-2 text-sm font-mono"
              />
            {/if}
          </label>
          <button
            type="button"
            onclick={loadModels}
            class="mt-5 rounded border border-[var(--border)] px-3 py-2 text-sm hover:bg-[var(--bg-panel)]"
            disabled={selected === 'lmstudio' && !current.configured}
            title={selected === 'lmstudio' && !current.configured
              ? 'Set base URL + Save first'
              : ''}
          >
            Load models
          </button>
        </div>
        {#if modelsErr}
          <p class="mt-2 text-sm text-red-400">{modelsErr}</p>
        {/if}
      </div>

      <div class="flex items-center gap-3 border-t border-[var(--border-soft)] pt-4">
        <button
          type="button"
          onclick={save}
          class="rounded bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500"
        >
          Save
        </button>
        <!-- When this provider is already the one chat uses, the tab
             pill above shows an "active" badge — duplicate it here as
             a disabled button would just be confusing. Only show the
             verb when switching is actually possible. -->
        {#if !isActive}
          <button
            type="button"
            onclick={makeActive}
            class="rounded border border-[var(--border)] px-4 py-2 text-sm hover:bg-[var(--bg-panel)]"
          >
            Use this provider for chat
          </button>
        {/if}
        {#if saveMsg}
          <span class="text-sm text-[var(--text-muted)]">{saveMsg}</span>
        {/if}
      </div>
    </div>
  {/if}

  {#if loading && !snapshot}
    <p class="text-sm text-[var(--text-faint)]">Loading…</p>
  {/if}
  </div>
</div>
