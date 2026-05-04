<script lang="ts">
  import { yamlStore, type Draft } from '$lib/yamlStore.svelte';

  let { onLoad }: { onLoad: (text: string, name: string) => void } = $props();

  let open = $state(false);

  function pick(d: Draft) {
    open = false;
    yamlStore.loadDraft(d.name);
    onLoad(yamlStore.text, d.name);
  }

  function remove(e: MouseEvent, name: string) {
    e.stopPropagation();
    if (!confirm(`Delete draft "${name}"?`)) return;
    yamlStore.deleteDraft(name);
  }

  function fmtAge(iso: string): string {
    const then = new Date(iso).getTime();
    const sec = Math.max(1, Math.floor((Date.now() - then) / 1000));
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  }
</script>

<div class="relative">
  <button
    class="rounded border border-zinc-700 px-2 py-0.5 text-xs hover:bg-zinc-800 disabled:opacity-50"
    onclick={() => (open = !open)}
    disabled={yamlStore.drafts.length === 0}
    title={yamlStore.drafts.length === 0 ? 'No saved drafts yet' : 'Open a saved draft'}
  >
    Drafts ({yamlStore.drafts.length}) ▾
  </button>
  {#if open}
    <div
      class="absolute left-0 top-full z-50 mt-1 max-h-96 w-80 overflow-auto rounded border border-zinc-700 bg-zinc-900 shadow-lg"
    >
      {#if yamlStore.drafts.length === 0}
        <div class="p-3 text-xs text-zinc-500">No saved drafts.</div>
      {:else}
        {#each yamlStore.drafts as d}
          <div
            class="group flex items-center justify-between border-b border-zinc-800 hover:bg-zinc-800"
          >
            <button
              class="min-w-0 flex-1 px-3 py-2 text-left text-xs"
              onclick={() => pick(d)}
            >
              <div class="font-mono text-zinc-200 truncate">{d.name}</div>
              <div class="mt-0.5 text-zinc-500">{fmtAge(d.savedAt)}</div>
            </button>
            <button
              class="mr-2 rounded px-1.5 py-0.5 text-xs text-zinc-500 opacity-0 hover:bg-zinc-700 hover:text-red-300 group-hover:opacity-100"
              onclick={(e) => remove(e, d.name)}
              title="Delete draft"
              aria-label="Delete draft {d.name}"
            >
              ✕
            </button>
          </div>
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
