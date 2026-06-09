<script lang="ts">
  /**
   * Bottom-of-viewport status bar (VS Code style). Replaces the
   * header health pills so the global top-nav doesn't fight for
   * horizontal space with environment indicators.
   *
   * Each segment is clickable — backend refreshes the probe, FSR
   * surfaces the configured base URL, LLM links into Settings.
   */
  import { onMount } from 'svelte';
  import { getHealth, type Health } from '$lib/api';

  let health = $state<Health | null>(null);
  let err = $state<string | null>(null);

  async function refresh() {
    try {
      health = await getHealth();
      err = null;
    } catch (e: any) {
      err = e?.message ?? String(e);
      health = null;
    }
  }

  onMount(() => {
    void refresh();
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  });

  const backend = $derived(err || !health ? 'down' : health.ok ? 'ok' : 'degraded');
  const fsr = $derived(
    !health ? 'unknown' : health.fsr.ok === true ? 'ok' : health.fsr.ok === false ? 'down' : 'unknown'
  );
  const llm = $derived(health?.llm.configured ? 'ok' : 'down');

  function dot(state: string) {
    return state === 'ok'
      ? 'bg-green-500'
      : state === 'down'
        ? 'bg-red-500'
        : state === 'degraded'
          ? 'bg-yellow-500'
          : 'bg-[var(--text-faint)]';
  }

  let fsrHost = $derived(
    health?.fsr.base_url ? new URL(health.fsr.base_url).host : null
  );
</script>

<footer class="flex items-center gap-4 border-t border-[var(--border-soft)] bg-[var(--bg-canvas)] px-3 py-1 text-[11px] text-[var(--text-muted)]">
  <button
    type="button"
    onclick={refresh}
    class="flex items-center gap-1.5 hover:text-[var(--text-default)]"
    title={err ?? 'click to refresh'}
  >
    <span class="h-1.5 w-1.5 rounded-full {dot(backend)}"></span>
    backend
  </button>
  <span
    class="flex items-center gap-1.5"
    title={health?.fsr.error || health?.fsr.base_url || 'FSR connection status'}
  >
    <span class="h-1.5 w-1.5 rounded-full {dot(fsr)}"></span>
    <span>FSR</span>
    {#if fsrHost}<span class="text-[var(--text-faint)]">·</span><span class="font-mono">{fsrHost}</span>{/if}
  </span>
  <a
    href="/settings"
    class="flex items-center gap-1.5 hover:text-[var(--text-default)]"
    title={health?.llm.configured
      ? `${health.llm.provider}${health.llm.model ? ' · ' + health.llm.model : ''}`
      : 'click to configure an LLM provider'}
  >
    <span class="h-1.5 w-1.5 rounded-full {dot(llm)}"></span>
    <span>LLM</span>
    {#if health?.llm.provider}<span class="text-[var(--text-faint)]">·</span><span class="font-mono">{health.llm.provider}</span>{/if}
  </a>

  {#if health?.secrets}
    <span
      class="ml-auto flex items-center gap-1.5"
      title={health.secrets.ok ? `secrets backend: ${health.secrets.backend}` : 'secrets backend unavailable'}
    >
      <span class="h-1.5 w-1.5 rounded-full {health.secrets.ok ? 'bg-green-500' : 'bg-red-500'}"></span>
      <span class="text-[var(--text-faint)]">{health.secrets.backend}</span>
    </span>
  {/if}
</footer>
