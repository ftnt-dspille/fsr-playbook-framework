<script lang="ts">
  /**
   * Custom xyflow node template for a playbook step.
   *
   * Collapses the 43 FSR step types into seven visual families
   * (driven by `node.family` from the backend). Color/icon scheme is
   * intentionally distinct so the canvas can be skimmed at a glance.
   */
  import { Handle, Position, type NodeProps } from '@xyflow/svelte';
  import type { VisualNode } from '../api';

  let props: NodeProps = $props();
  let node = $derived(props.data.node as VisualNode);
  let verification = $derived(props.data.verification as { status: string } | null);

  const FAMILY_STYLE: Record<VisualNode['family'], { bg: string; border: string; label: string }> = {
    trigger:        { bg: '#fef3c7', border: '#d97706', label: 'Trigger' },
    connector_op:   { bg: '#dbeafe', border: '#2563eb', label: 'Connector' },
    decision:       { bg: '#ede9fe', border: '#7c3aed', label: 'Decision' },
    record_crud:    { bg: '#dcfce7', border: '#16a34a', label: 'Record' },
    utility:        { bg: '#f3f4f6', border: '#6b7280', label: 'Utility' },
    manual_input:   { bg: '#fef9c3', border: '#ca8a04', label: 'Manual Input' },
    workflow_ref:   { bg: '#fae8ff', border: '#a21caf', label: 'Workflow Ref' },
    terminal:       { bg: '#fee2e2', border: '#b91c1c', label: 'Terminal' }
  };

  let style = $derived(FAMILY_STYLE[node.family] ?? FAMILY_STYLE.utility);

  // Pull a couple of leading args to render in the body so the user
  // doesn't have to open the inspector to see what the step does.
  let summary = $derived(buildSummary(node));

  function buildSummary(n: VisualNode): string {
    if (n.family === 'connector_op') {
      const c = n.arguments?.connector as string | undefined;
      const op = (n.arguments?.operation as string | undefined) ?? n.type;
      return `${c ?? '?'} · ${op}`;
    }
    if (n.family === 'decision') {
      const conds = (n.arguments?.conditions as unknown[]) ?? [];
      return `${conds.length} branch${conds.length === 1 ? '' : 'es'}`;
    }
    if (n.family === 'record_crud') {
      const m = (n.arguments?.module as string | undefined) ?? (n.arguments?.collection as string | undefined);
      return m ? `module: ${m}` : '';
    }
    if (n.family === 'utility' && n.type === 'set_variable') {
      const al = n.arguments?.arg_list as { name?: string }[] | undefined;
      const names = al?.map((a) => a.name).filter(Boolean) ?? [];
      return names.length ? names.slice(0, 3).join(', ') + (names.length > 3 ? '…' : '') : '';
    }
    return '';
  }

  const VERIF_DOT: Record<string, string> = {
    tested_pass: '#16a34a',
    tested_fail: '#dc2626',
    seen: '#9ca3af'
  };
</script>

<div
  class="rounded-lg border-2 px-3 py-2 shadow-sm transition-shadow hover:shadow-md"
  style="background: {style.bg}; border-color: {style.border}; min-width: 200px; max-width: 240px;"
>
  <Handle type="target" position={Position.Top} />
  <div class="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wide" style="color: {style.border}">
    <span>{style.label}</span>
    {#if verification}
      <span
        class="inline-block h-2 w-2 rounded-full"
        title="verification: {verification.status}"
        style="background: {VERIF_DOT[verification.status] ?? '#9ca3af'}"
        aria-label="verification {verification.status}"
      ></span>
    {/if}
  </div>
  <div class="mt-1 truncate text-sm font-medium text-gray-900">{node.name}</div>
  {#if summary}
    <div class="mt-0.5 truncate text-xs text-gray-600">{summary}</div>
  {/if}
  <Handle type="source" position={Position.Bottom} />
</div>
