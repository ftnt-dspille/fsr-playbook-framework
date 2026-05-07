<script lang="ts">
  import PageHeader from '$lib/components/PageHeader.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
</script>

<div class="flex h-full flex-col">
  <PageHeader
    eyebrow="Phase 4"
    title="Browse"
    subtitle="Discover playbooks shipped on the connected FortiSOAR — by collection, tag, last run, or full-text search."
  />
  <div class="flex-1">
    <EmptyState
      title="Browse is on the next milestone"
      description="The catalog will list every collection on the live FSR with quick-open into Design and a one-click pull-to-edit. Track progress in TODO.md (Phase 4)."
    >
      {#snippet actions()}
        <a class="btn btn-primary" href="/inventory">Open Inventory</a>
        <a class="btn" href="/">Back to Design</a>
      {/snippet}
    </EmptyState>
  </div>
</div>
