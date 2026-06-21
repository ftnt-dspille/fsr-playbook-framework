<script lang="ts">
  /**
   * Retired: the run-log surface lives in the DiagnosticsDrawer's
   * Deploy tab now (visible inline during Push & Run, no tab switch
   * required). This route survives only so existing bookmarks redirect
   * cleanly to Studio.
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
