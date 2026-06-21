<script lang="ts">
  /**
   * Retired in favor of the unified Studio workspace at `/`.
   * This page now redirects so existing bookmarks keep working.
   */
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  onMount(() => {
    goto('/', { replaceState: true });
  });
</script>

<div class="flex h-full items-center justify-center text-sm text-[var(--text-faint)]">
  Redirecting to Studio…
</div>
