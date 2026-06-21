<script lang="ts" module>
  /**
   * Module-level Promise cache so simultaneous mounts of multiple
   * <ConnectorIcon name="jira" /> instances share one fetch instead of
   * fanning out. Keyed by connector name; size variant just picks
   * which field of the resolved record to render.
   */
  import { callMcpTool } from '../api';

  type IconRecord = { icon_small?: string | null; icon_large?: string | null };
  const inflight = new Map<string, Promise<IconRecord | null>>();

  export function fetchConnectorIcon(name: string): Promise<IconRecord | null> {
    if (!name) return Promise.resolve(null);
    let p = inflight.get(name);
    if (p) return p;
    p = callMcpTool<IconRecord & { ok?: boolean }>('get_connector_icon', { connector: name })
      .then((r) => (r.ok ? (r.result ?? null) : null))
      .catch(() => null);
    inflight.set(name, p);
    return p;
  }
</script>

<script lang="ts">
  /**
   * Renders a connector's PNG/JPEG icon. The MCP tool returns ready-to-
   * use `data:image/...;base64,...` strings, so the data URI just slots
   * straight into <img src>. Falls back to a colored initial badge when
   * we have no image (no live FSR, unknown connector, or fetch error).
   */
  type Props = { name: string; size?: 'sm' | 'lg'; class?: string };
  let { name, size = 'sm', class: extraClass = '' }: Props = $props();

  let dataUri = $state<string | null>(null);
  let loaded = $state(false);

  $effect(() => {
    loaded = false;
    dataUri = null;
    if (!name) return;
    let cancelled = false;
    fetchConnectorIcon(name).then((rec) => {
      if (cancelled) return;
      const candidate = size === 'lg'
        ? (rec?.icon_large ?? rec?.icon_small)
        : (rec?.icon_small ?? rec?.icon_large);
      dataUri = candidate ?? null;
      loaded = true;
    });
    return () => { cancelled = true; };
  });

  let dim = $derived(size === 'lg' ? 64 : 18);
  let initial = $derived(name ? name[0]!.toUpperCase() : '?');
</script>

{#if dataUri}
  <img
    src={dataUri}
    alt={name}
    width={dim}
    height={dim}
    class="fsrpb-connector-icon {extraClass}"
    style="width: {dim}px; height: {dim}px;"
  />
{:else}
  <span
    class="fsrpb-connector-icon-fallback {extraClass}"
    style="width: {dim}px; height: {dim}px; font-size: {Math.round(dim * 0.5)}px;"
    aria-label={name}
    title={name}
  >{initial}</span>
{/if}

<style>
  .fsrpb-connector-icon {
    display: inline-block;
    border-radius: 4px;
    object-fit: contain;
    background: white;
    flex-shrink: 0;
  }
  .fsrpb-connector-icon-fallback {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    background: #e5e7eb;
    color: #374151;
    font-weight: 600;
    flex-shrink: 0;
  }
</style>
