<script lang="ts">
  /**
   * Tabbed inspector. Phase 1.4 = Raw view; Phase 2 adds Args
   * (schema-driven) + Examples tabs. Verify tab lands in Phase 4.
   */
  import type { VisualNode, VisualPlaybook } from '../api';
  import StepInspectorArgsTab from './StepInspectorArgsTab.svelte';
  import StepInspectorExamplesTab from './StepInspectorExamplesTab.svelte';
  import StepInspectorBranchesTab from './StepInspectorBranchesTab.svelte';
  import StepInspectorVerifyTab from './StepInspectorVerifyTab.svelte';
  import StepDraftModal from './StepDraftModal.svelte';
  import { visualStore } from '../visualEditStore.svelte';

  type Props = {
    node: VisualNode | null;
    playbook: VisualPlaybook | null;
    playbookIdx: number;
    onDelete?: (nodeId: string) => void;
  };
  let { node, playbook, playbookIdx, onDelete }: Props = $props();

  function renameNode(e: Event) {
    if (!node) return;
    const v = (e.currentTarget as HTMLInputElement).value;
    visualStore.patchNode(playbookIdx, node.id, { name: v });
  }
  function setComment(e: Event) {
    if (!node) return;
    const v = (e.currentTarget as HTMLTextAreaElement).value;
    visualStore.patchNode(playbookIdx, node.id, { comment: v || null });
  }
  function deleteNode() {
    if (!node) return;
    if (!confirm(`Delete step '${node.name}' (${node.id})? This also drops every edge touching it.`)) return;
    const id = node.id;
    visualStore.removeNode(playbookIdx, id);
    onDelete?.(id);
  }

  type Tab = 'args' | 'examples' | 'branches' | 'verify' | 'raw';
  let activeTab: Tab = $state('args');

  // Reset to the most useful default tab whenever the user picks a
  // different node. Decision → Branches; terminal → Raw; everything
  // else → Args.
  $effect(() => {
    if (node) activeTab = defaultTab;
  });

  // Tab visibility is driven by node family/type. Decision/terminal/etc.
  // don't have schema-driven args or operation examples, so we hide
  // those tabs entirely to keep the inspector focused.
  // Args tab is irrelevant for decision (use Branches), terminal
  // (no args), and trigger steps where the only field is the trigger
  // record context. Keep it everywhere else.
  let showArgs = $derived(
    node ? node.family !== 'terminal' && node.type !== 'decision' : false
  );
  // Examples tab is shown for any step type that has corpus-mined
  // skeletons available — connector_op + record_crud use the live
  // operation/Jinja examples; everything else falls back to the new
  // /api/ref/step-examples/<type> clusters with deterministic English
  // summaries. The set below mirrors STEP_TYPE_TO_CORPUS in
  // web/backend/step_examples.py.
  const STEP_TYPES_WITH_EXAMPLES = new Set([
    'decision', 'manual_input', 'set_variable', 'find_record',
    'create_record', 'insert_record', 'update_record', 'delete_record',
    'ingest_bulk_feed', 'delay', 'code_snippet', 'workflow_reference',
    'start_on_create', 'start_on_update', 'start',
    'manual_action', 'api_call'
  ]);
  let showExamples = $derived(node
    ? node.family === 'connector_op' || node.family === 'record_crud'
      || STEP_TYPES_WITH_EXAMPLES.has(node.type)
    : false);
  let showBranches = $derived(node?.type === 'decision' || node?.type === 'manual_input');
  let showVerify = $derived(node ? node.family !== 'terminal' : false);

  // Decision and trigger nodes' "args" are tiny — fall back to Branches
  // (decision) or Raw (trigger) as the default tab so the user lands on
  // something useful instead of a one-line freeform JSON view.
  let defaultTab = $derived<Tab>(
    node?.type === 'decision' ? 'branches'
      : node?.family === 'terminal' ? 'raw'
      : 'args'
  );

  let TABS = $derived<{ key: Tab; label: string }[]>([
    ...(showArgs ? [{ key: 'args' as Tab, label: 'Args' }] : []),
    ...(showExamples ? [{ key: 'examples' as Tab, label: 'Examples' }] : []),
    ...(showBranches ? [{ key: 'branches' as Tab, label: 'Branches' }] : []),
    ...(showVerify ? [{ key: 'verify' as Tab, label: 'Verify' }] : []),
    { key: 'raw', label: 'Raw' }
  ]);

  // AI step drafter — same set the backend supports (mirrors STEP_INTROS
  // in `web/backend/step_drafter.py`). Surfaces a "✨ Describe" button
  // beside the step name when available.
  const DRAFTABLE_TYPES = new Set([
    'decision', 'manual_input', 'find_record',
    'create_record', 'update_record',
    'set_variable', 'delay', 'workflow_reference', 'code_snippet',
    'raise_exception', 'terminate', 'assert',
    'start_on_create', 'start_on_update', 'start',
    'manual_action', 'api_call'
  ]);
  let draftOpen = $state(false);
  let canDraft = $derived(node ? DRAFTABLE_TYPES.has(node.type) : false);

  /** Pull the active module name from the node's args — only relevant
   * for trigger / record_crud step types where the drafter wants the
   * field schema. Returns null otherwise. */
  function activeModule(): string | null {
    if (!node) return null;
    const a = (node.arguments ?? {}) as Record<string, unknown>;
    if (node.family === 'trigger') {
      const r = a.resource as string | undefined;
      return r ? r.split('?', 1)[0] : null;
    }
    if (node.family === 'record_crud') {
      const m = a.module as string | undefined;
      if (m) return m.split('?', 1)[0];
      const c = a.collection as string | undefined;
      if (c) return c.replace(/^\/api\/(?:3|ingest-feeds)\//, '').split('?', 1)[0];
    }
    return null;
  }

  function applyDraft(next: Record<string, unknown>) {
    if (!node) return;
    visualStore.setArgs(playbookIdx, node.id, next);
    draftOpen = false;
  }
</script>

<aside class="flex h-full w-96 flex-col border-l border-[var(--border-soft)] bg-[var(--bg-canvas)]">
  {#if !node || !playbook}
    <div class="flex flex-1 items-center justify-center px-4 text-center text-sm text-[var(--text-faint)]">
      Click a node to inspect
    </div>
  {:else}
    <header class="border-b border-[var(--border-soft)] px-4 py-2">
      <div class="flex items-center gap-2">
        <input
          type="text"
          aria-label="Step name"
          value={node.name}
          oninput={renameNode}
          class="flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold text-[var(--text-default)] hover:border-[var(--border-soft)] focus:border-[var(--brand)] focus:outline-none"
        />
        {#if canDraft}
          <button
            type="button"
            aria-label="Describe step"
            title="Describe what you want — AI drafts the args"
            class="rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-default)] hover:bg-[var(--bg-canvas)]"
            onclick={() => (draftOpen = true)}
          >✨ Describe</button>
        {/if}
        <button
          type="button"
          aria-label="Delete step"
          title="Delete step"
          class="text-[10px] font-medium text-rose-600 hover:text-rose-700"
          onclick={deleteNode}
        >Delete</button>
      </div>
      <div class="text-[10px] text-[var(--text-faint)] truncate" title="{node.family} · {node.type} · {node.id}">
        {node.family} · {node.type} · <span class="font-mono">{node.id}</span>
      </div>
    </header>

    <nav class="flex border-b border-[var(--border-soft)] text-xs">
      {#each TABS as t}
        <button
          type="button"
          class="flex-1 px-3 py-2 font-medium transition-colors {activeTab === t.key
            ? 'border-b-2 border-[var(--brand)] text-[var(--text-default)]'
            : 'text-[var(--text-muted)] hover:text-[var(--text-default)]'}"
          onclick={() => (activeTab = t.key)}
        >{t.label}</button>
      {/each}
    </nav>

    <div class="flex-1 overflow-auto px-4 py-3 text-sm">
      {#if activeTab === 'args'}
        <StepInspectorArgsTab {node} {playbook} {playbookIdx} />
      {:else if activeTab === 'examples'}
        <StepInspectorExamplesTab {node} {playbook} {playbookIdx} />
      {:else if activeTab === 'branches'}
        <StepInspectorBranchesTab {node} {playbook} {playbookIdx} />
      {:else if activeTab === 'verify'}
        <StepInspectorVerifyTab {node} />
      {:else}
        <section class="mb-3">
          <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Comment</div>
          <textarea
            aria-label="Step comment"
            class="mt-1 block w-full resize-y rounded border border-[var(--border-soft)] bg-[var(--bg-elev)] px-2 py-1 text-xs"
            rows="2"
            value={node.comment ?? ''}
            placeholder="(no comment)"
            oninput={setComment}
          ></textarea>
        </section>
        {#if node.for_each}
          <section class="mb-3">
            <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">For each</div>
            <pre class="mt-1 max-h-40 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.for_each, null, 2)}</pre>
          </section>
        {/if}
        <section>
          <div class="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Arguments (raw)</div>
          {#if Object.keys(node.arguments ?? {}).length === 0}
            <p class="mt-1 italic text-[var(--text-faint)]">no arguments</p>
          {:else}
            <pre class="mt-1 overflow-auto rounded bg-[var(--bg-elev)] p-2 text-xs">{JSON.stringify(node.arguments, null, 2)}</pre>
          {/if}
        </section>
      {/if}
    </div>
  {/if}
</aside>

{#if draftOpen && node}
  <StepDraftModal
    {node}
    module={activeModule()}
    onApply={applyDraft}
    onClose={() => (draftOpen = false)}
  />
{/if}
