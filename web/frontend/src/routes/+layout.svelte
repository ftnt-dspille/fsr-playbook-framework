<script lang="ts">
  import '../app.css';
  import HealthPill from '$lib/components/HealthPill.svelte';
  let { children } = $props();
</script>

<div class="flex h-full flex-col">
  <header class="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
    <div class="flex items-center gap-4">
      <span class="font-semibold">FSR Playbook Studio</span>
      <nav class="flex gap-3 text-sm text-zinc-400">
        <a href="/" class="hover:text-zinc-100">Design</a>
        <a href="/run" class="hover:text-zinc-100">Run</a>
        <a href="/browse" class="hover:text-zinc-100">Browse</a>
        <a href="/inventory" class="hover:text-zinc-100">Inventory</a>
        <a href="/history" class="hover:text-zinc-100">History</a>
        <a href="/capabilities" class="hover:text-zinc-100">Capabilities</a>
        <a href="/docs" class="hover:text-zinc-100">Docs</a>
        <a href="/settings" class="hover:text-zinc-100">Settings</a>
      </nav>
    </div>
    <HealthPill />
  </header>
  <main class="min-h-0 flex-1">{@render children()}</main>
</div>
