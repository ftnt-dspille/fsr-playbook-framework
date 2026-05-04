<script lang="ts">
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
    refresh();
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
          : 'bg-zinc-600';
  }
</script>

<div class="flex items-center gap-3 text-sm text-zinc-200">
  <button
    type="button"
    onclick={refresh}
    class="flex items-center gap-2 rounded-full border border-zinc-700 px-3 py-1.5 font-medium hover:bg-zinc-900"
    title={err ?? 'click to refresh'}
  >
    <span class="h-2.5 w-2.5 rounded-full {dot(backend)}"></span> backend
  </button>
  <span
    class="flex items-center gap-2 rounded-full border border-zinc-700 px-3 py-1.5 font-medium"
    title={health?.fsr.error || health?.fsr.base_url || 'FSR connection status'}
  >
    <span class="h-2.5 w-2.5 rounded-full {dot(fsr)}"></span>
    FSR
    {#if health?.fsr.base_url}
      <span class="text-zinc-500">{new URL(health.fsr.base_url).host}</span>
    {/if}
  </span>
  <span
    class="flex items-center gap-2 rounded-full border border-zinc-700 px-3 py-1.5 font-medium"
    title={llm === 'ok' ? 'ANTHROPIC_API_KEY configured' : 'set ANTHROPIC_API_KEY to enable chat'}
  >
    <span class="h-2.5 w-2.5 rounded-full {dot(llm)}"></span> LLM
  </span>
</div>
