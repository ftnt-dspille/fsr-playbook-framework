<script lang="ts">
  /**
   * Read-only diagnostic banners that surface compile-time and
   * runtime gotchas at edit-time, before the user clicks Save.
   *
   * Two checks today; both stem from real failures the round-trip
   * probe surfaced (see `python/probes/probe_round_trip.py`):
   *
   *   1. Multi-trigger detected — FSR allows exactly one trigger per
   *      playbook. The compiler rejects this, but only at save time;
   *      surfacing it here catches it the moment the user drops the
   *      second trigger on the canvas.
   *
   *   2. Trigger playbook is inactive — `is_active: false` ships
   *      cleanly to FSR but the trigger never fires (the IR default is
   *      False, easy to miss). Catching it here saves the user from
   *      "I pushed it, why didn't it fire?" debugging.
   *
   * Pure computation; no MCP calls. Safe to mount above the canvas.
   */
  import type { VisualPlaybook, VisualNode } from '../api';

  type Props = { playbook: VisualPlaybook | null };
  let { playbook }: Props = $props();

  let triggers = $derived<VisualNode[]>(
    playbook ? playbook.nodes.filter((n) => n.family === 'trigger') : []
  );

  let multiTrigger = $derived(triggers.length > 1);
  // Inactive guard only fires when the playbook actually has a
  // trigger — manual collections without a trigger don't need to be
  // "active" in FSR's sense and would generate noise otherwise.
  let inactiveTriggerPlaybook = $derived(
    !!playbook && triggers.length > 0 && playbook.is_active === false
  );
</script>

{#if playbook && (multiTrigger || inactiveTriggerPlaybook)}
  <div class="space-y-1 px-3 py-1.5">
    {#if multiTrigger}
      <div
        role="alert"
        class="rounded border border-rose-300 bg-rose-50 px-2 py-1 text-[11px] dark:bg-rose-950/30"
      >
        <span class="font-semibold text-rose-700 dark:text-rose-400">
          Multiple triggers ({triggers.length})
        </span>
        <span class="text-rose-700 dark:text-rose-400">
          — FSR allows exactly one trigger per playbook. The compiler
          will reject this on save. Delete one of:
        </span>
        <span class="font-mono">
          {triggers.map((t) => t.name || t.id).join(', ')}
        </span>
      </div>
    {/if}
    {#if inactiveTriggerPlaybook}
      <div
        role="status"
        class="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] dark:bg-amber-950/30"
      >
        <span class="font-semibold text-amber-700 dark:text-amber-400">
          Playbook is inactive
        </span>
        <span class="text-amber-800 dark:text-amber-300">
          — the trigger will not fire on push. Add
          <code class="font-mono">is_active: true</code>
          under <code class="font-mono">{playbook.name}</code> in YAML
          (or the playbook header) to enable.
        </span>
      </div>
    {/if}
  </div>
{/if}
