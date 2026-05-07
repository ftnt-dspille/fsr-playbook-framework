<script lang="ts">
  import { yamlStore, type Draft } from '$lib/yamlStore.svelte';

  let { onLoad }: { onLoad: (text: string, name: string) => void } = $props();

  let open = $state(false);
  // Name of the draft whose revision history is currently expanded
  // inside the menu. Null = list view.
  let viewingRevisionsOf = $state<string | null>(null);
  // Name of the draft pending delete-confirmation (inline, replaces
  // the browser's `confirm()` dialog). Null = no confirm in flight.
  let confirmingDelete = $state<string | null>(null);

  function pick(d: Draft) {
    open = false;
    yamlStore.loadDraft(d.name);
    onLoad(yamlStore.text, d.name);
  }

  function pickRevision(name: string, index: number) {
    open = false;
    yamlStore.loadDraftRevision(name, index);
    onLoad(yamlStore.text, `${name} (rev ${index})`);
  }

  function askDelete(e: MouseEvent, name: string) {
    e.stopPropagation();
    confirmingDelete = name;
  }

  function confirmDelete(e: MouseEvent, name: string) {
    e.stopPropagation();
    yamlStore.deleteDraft(name);
    if (viewingRevisionsOf === name) viewingRevisionsOf = null;
    if (confirmingDelete === name) confirmingDelete = null;
  }

  function cancelDelete(e: MouseEvent) {
    e.stopPropagation();
    confirmingDelete = null;
  }

  function fmtAge(iso: string): string {
    const then = new Date(iso).getTime();
    const sec = Math.max(1, Math.floor((Date.now() - then) / 1000));
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  }

  function sourceBadgeClass(s: 'agent' | 'user' | 'replay'): string {
    return {
      agent: 'border-amber-700/60 bg-amber-900/30 text-amber-300',
      user: 'border-emerald-700/60 bg-emerald-900/30 text-emerald-300',
      replay: 'border-blue-700/60 bg-blue-900/30 text-blue-300'
    }[s];
  }
</script>

<div class="relative">
  <button
    class="rounded border border-[var(--border)] px-2 py-0.5 text-xs hover:bg-[var(--bg-elevated)] disabled:opacity-50"
    onclick={() => (open = !open)}
    disabled={yamlStore.drafts.length === 0}
    title={yamlStore.drafts.length === 0 ? 'No saved drafts yet' : 'Open a saved draft'}
  >
    Drafts{yamlStore.activeDraftName ? `: ${yamlStore.activeDraftName}` : ''} ({yamlStore.drafts.length}) ▾
  </button>
  {#if open}
    <div
      class="absolute left-0 top-full z-50 mt-1 max-h-96 w-80 overflow-auto rounded border border-[var(--border)] bg-[var(--bg-panel)] shadow-lg"
    >
      {#if yamlStore.drafts.length === 0}
        <div class="p-3 text-xs text-[var(--text-faint)]">No saved drafts.</div>
      {:else if viewingRevisionsOf}
        {@const draft = yamlStore.drafts.find((d) => d.name === viewingRevisionsOf)}
        {#if draft}
          <div class="border-b border-[var(--border-soft)] px-3 py-2 flex items-center justify-between bg-[var(--bg-canvas)]">
            <button
              class="text-xs text-[var(--text-muted)] hover:text-[var(--text-default)]"
              onclick={() => (viewingRevisionsOf = null)}
            >
              ← Back
            </button>
            <span class="text-xs font-medium text-[var(--text-default)] truncate ml-2">
              {draft.name}
            </span>
          </div>
          {#if (draft.revisions ?? []).length === 0}
            <div class="p-3 text-xs text-[var(--text-faint)]">
              No revision history (legacy draft saved before history was introduced).
            </div>
          {:else}
            {#each draft.revisions ?? [] as rev, i}
              <button
                class="block w-full border-b border-[var(--border-soft)] px-3 py-2 text-left text-xs hover:bg-[var(--bg-elevated)]"
                onclick={() => pickRevision(draft.name, i)}
                title="Load this revision into the editor"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-[var(--text-muted)]">
                    {i === 0 ? 'latest' : `rev ${i}`} · {fmtAge(rev.savedAt)}
                  </span>
                  <span class={`rounded border px-1.5 py-0 text-[10px] uppercase ${sourceBadgeClass(rev.source)}`}>
                    {rev.source}
                  </span>
                </div>
                {#if rev.message}
                  <div class="mt-1 text-[var(--text-faint)] italic line-clamp-2">
                    “{rev.message}”
                  </div>
                {/if}
              </button>
            {/each}
          {/if}
        {/if}
      {:else}
        {#each yamlStore.drafts as d}
          {@const revCount = (d.revisions ?? []).length}
          {@const isActive = yamlStore.activeDraftName === d.name}
          <div
            class={`group flex items-center justify-between border-b border-[var(--border-soft)] hover:bg-[var(--bg-elevated)] ${isActive ? 'bg-[var(--bg-elevated)]/60' : ''}`}
          >
            <button
              class="min-w-0 flex-1 px-3 py-2 text-left text-xs"
              onclick={() => pick(d)}
            >
              <div class="flex items-center gap-1.5 font-mono text-[var(--text-default)] truncate">
                {#if isActive}
                  <span class="text-emerald-400" aria-label="currently loaded">●</span>
                {/if}
                <span class="truncate">{d.name}</span>
                {#if isActive}
                  <span class="rounded border border-emerald-700/60 bg-emerald-900/30 px-1 py-0 text-[9px] uppercase tracking-wide text-emerald-300">current</span>
                {/if}
              </div>
              <div class="mt-0.5 text-[var(--text-faint)]">
                {fmtAge(d.savedAt)}
                {#if revCount > 1}
                  · {revCount} revisions
                {/if}
              </div>
            </button>
            {#if revCount > 1}
              <button
                class="mr-1 rounded px-1.5 py-0.5 text-xs text-[var(--text-muted)] hover:bg-[var(--border)] hover:text-[var(--text-default)]"
                onclick={(e) => {
                  e.stopPropagation();
                  viewingRevisionsOf = d.name;
                }}
                title="View revision history"
                aria-label="View revisions of {d.name}"
              >
                ⏷
              </button>
            {/if}
            {#if confirmingDelete === d.name}
              <div class="mr-2 flex items-center gap-1">
                <span class="text-[10px] text-[var(--text-muted)]">Delete?</span>
                <button
                  class="rounded border border-red-700/60 bg-red-900/40 px-1.5 py-0.5 text-[10px] text-red-200 hover:bg-red-900/60"
                  onclick={(e) => confirmDelete(e, d.name)}
                  aria-label="Confirm delete {d.name}"
                >
                  Yes
                </button>
                <button
                  class="rounded border border-[var(--border)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)] hover:bg-[var(--bg-panel)]"
                  onclick={cancelDelete}
                  aria-label="Cancel delete"
                >
                  No
                </button>
              </div>
            {:else}
              <button
                class="mr-2 rounded px-1.5 py-0.5 text-xs text-[var(--text-faint)] opacity-0 hover:bg-[var(--border)] hover:text-red-300 group-hover:opacity-100"
                onclick={(e) => askDelete(e, d.name)}
                title="Delete draft"
                aria-label="Delete draft {d.name}"
              >
                ✕
              </button>
            {/if}
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
