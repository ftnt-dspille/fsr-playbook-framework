<script lang="ts">
  import { onMount } from 'svelte';
  import {
    getProviders, patchProvider, testProvider, listProviderModels, setActiveProvider,
    type ProvidersResponse, type ProviderView
  } from '$lib/api';

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
      hydrateForm();
    } catch (e: any) {
      err = e?.message ?? String(e);
    } finally {
      loading = false;
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
  }

  async function runTest() {
    testStatus = 'testing';
    testMsg = '';
    try {
      const result = await testProvider(selected, {
        base_url: formBase || undefined,
        api_key: formKey || undefined
      });
      if (result.ok) {
        testStatus = 'ok';
        testMsg = result.latency_ms != null
          ? `Reachable (${result.latency_ms} ms)${result.note ? ' — ' + result.note : ''}`
          : (result.note ?? 'Reachable.');
      } else {
        testStatus = 'fail';
        testMsg = result.error ?? 'unknown error';
      }
    } catch (e: any) {
      testStatus = 'fail';
      testMsg = e?.message ?? String(e);
    }
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
      const r = await listProviderModels(selected);
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

  async function clearKey() {
    if (!confirm('Delete the saved API key for this provider?')) return;
    await patchProvider(selected, { clear_api_key: true });
    await refresh();
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

<div class="mx-auto max-w-3xl p-6 text-zinc-100">
  <h1 class="mb-1 text-2xl font-semibold">Settings</h1>
  <p class="mb-6 text-sm text-zinc-400">
    Configure which LLM the chat uses. Keys are stored in your OS secret store
    ({snapshot?.secrets?.backend ?? '…'}), never in the browser.
  </p>

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
                 ? 'border-zinc-300 bg-zinc-800'
                 : 'border-zinc-700 hover:bg-zinc-900'}"
      >
        {p.name}
        {#if snapshot?.active_provider === p.name}
          <span class="ml-1 rounded bg-green-700 px-1.5 text-xs">active</span>
        {:else if p.configured}
          <span class="ml-1 rounded bg-zinc-700 px-1.5 text-xs">ready</span>
        {/if}
      </button>
    {/each}
  </div>

  {#if current}
    <div class="space-y-5 rounded border border-zinc-800 bg-zinc-900/50 p-5">
      {#if selected === 'lmstudio'}
        <label class="block">
          <span class="mb-1 block text-sm text-zinc-300">Base URL</span>
          <input
            type="text"
            bind:value={formBase}
            placeholder="http://localhost:1234/v1"
            class="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
          />
        </label>
      {/if}

      <label class="block">
        <span class="mb-1 block flex items-center justify-between text-sm text-zinc-300">
          <span>API key</span>
          {#if current.api_key_set}
            <button type="button" onclick={clearKey} class="text-xs text-zinc-400 underline hover:text-zinc-200">
              clear saved key
            </button>
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
          class="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
        />
      </label>

      <div class="flex items-center gap-3">
        <button
          type="button"
          onclick={runTest}
          class="rounded bg-zinc-700 px-3 py-1.5 text-sm hover:bg-zinc-600"
          disabled={testStatus === 'testing'}
        >
          {testStatus === 'testing' ? 'Testing…' : 'Test connection'}
        </button>
        {#if testStatus === 'ok'}
          <span class="text-sm text-green-400">✓ {testMsg}</span>
        {:else if testStatus === 'fail'}
          <span class="text-sm text-red-400">✗ {testMsg}</span>
        {/if}
      </div>

      <div class="border-t border-zinc-800 pt-4">
        <div class="flex items-center gap-3">
          <label class="flex-1 block">
            <span class="mb-1 block text-sm text-zinc-300">Model</span>
            {#if models.length > 0}
              <select
                bind:value={formModel}
                class="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
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
                class="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm font-mono"
              />
            {/if}
          </label>
          <button
            type="button"
            onclick={loadModels}
            class="mt-5 rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-900"
            disabled={selected === 'lmstudio' && testStatus !== 'ok' && !current.configured}
            title={selected === 'lmstudio' && testStatus !== 'ok' && !current.configured
              ? 'Test the connection first'
              : ''}
          >
            Load models
          </button>
        </div>
        {#if modelsErr}
          <p class="mt-2 text-sm text-red-400">{modelsErr}</p>
        {/if}
      </div>

      <div class="flex items-center gap-3 border-t border-zinc-800 pt-4">
        <button
          type="button"
          onclick={save}
          class="rounded bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500"
        >
          Save
        </button>
        <button
          type="button"
          onclick={makeActive}
          class="rounded border border-zinc-700 px-4 py-2 text-sm hover:bg-zinc-900"
          disabled={isActive}
        >
          {isActive ? 'Active' : 'Set as active'}
        </button>
        {#if saveMsg}
          <span class="text-sm text-zinc-400">{saveMsg}</span>
        {/if}
      </div>
    </div>
  {/if}

  {#if loading && !snapshot}
    <p class="text-sm text-zinc-500">Loading…</p>
  {/if}
</div>
