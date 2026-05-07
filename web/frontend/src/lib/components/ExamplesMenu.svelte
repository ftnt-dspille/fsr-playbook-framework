<script lang="ts">
  import { onMount } from 'svelte';
  import { listExamples, loadExample, type ExampleEntry } from '$lib/api';

  let { onLoad }: { onLoad: (text: string, name: string) => void } = $props();

  let items = $state<ExampleEntry[]>([]);
  let open = $state(false);
  let err = $state<string | null>(null);

  onMount(async () => {
    try {
      items = await listExamples();
    } catch (e: any) {
      err = e?.message ?? String(e);
    }
  });

  async function pick(name: string) {
    open = false;
    const ex = await loadExample(name);
    onLoad(ex.text, ex.name);
  }
</script>

<div class="relative">
  <button
    class="rounded border border-[var(--border)] px-2 py-0.5 text-xs hover:bg-[var(--bg-elevated)]"
    onclick={() => (open = !open)}
  >
    Examples ▾
  </button>
  {#if open}
    <div
      class="absolute left-0 top-full z-50 mt-1 max-h-96 w-80 overflow-auto rounded border border-[var(--border)] bg-[var(--bg-panel)] shadow-lg"
    >
      {#if err}
        <div class="p-3 text-xs text-red-300">{err}</div>
      {:else if !items.length}
        <div class="p-3 text-xs text-[var(--text-faint)]">No examples found.</div>
      {:else}
        {#each items as ex}
          <button
            class="block w-full border-b border-[var(--border-soft)] px-3 py-2 text-left text-xs hover:bg-[var(--bg-elevated)]"
            onclick={() => pick(ex.name)}
          >
            <div class="font-mono text-[var(--text-default)]">{ex.name}</div>
            {#if ex.preview}
              <div class="mt-0.5 truncate text-[var(--text-faint)]">{ex.preview}</div>
            {/if}
          </button>
        {/each}
      {/if}
    </div>
  {/if}
</div>

<svelte:window
  onclick={(e) => {
    if (open && !(e.target as HTMLElement).closest('.relative')) open = false;
  }}
/>
