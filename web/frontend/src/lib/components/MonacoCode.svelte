<script lang="ts">
  /**
   * Slim Monaco wrapper for arbitrary languages — used by code_snippet
   * (Python / Jinja-Python) and any future inspector field that needs
   * proper syntax highlighting + indentation. Mirrors `MonacoYaml`'s
   * lifecycle (init in onMount, dispose on unmount, parent→editor sync
   * via $effect with the internalUpdate guard) but without the
   * YAML-specific completion/hover registration.
   *
   * Default language is `python`; pass `language="json"` etc. to opt
   * into other modes Monaco ships out of the box.
   */
  import { onMount, onDestroy } from 'svelte';

  let {
    value = '',
    language = 'python',
    onInput,
    readOnly = false,
    placeholder = '',
    height = '14rem'
  }: {
    value: string;
    language?: string;
    onInput: (v: string) => void;
    readOnly?: boolean;
    /** Shown in a one-line ghost overlay when the editor has no
     * content. Monaco doesn't expose a placeholder API, so we fade
     * a static element behind the editor when value is empty. */
    placeholder?: string;
    /** CSS height for the editor host. The inspector lays this in a
     * variable-width sidebar so we let the parent decide vertically. */
    height?: string;
  } = $props();

  let host: HTMLDivElement;
  let editor = $state<any>(null);
  let internalUpdate = false;

  onMount(async () => {
    const monaco = await import('monaco-editor');
    editor = monaco.editor.create(host, {
      value,
      language,
      theme: 'vs-dark',
      automaticLayout: true,
      readOnly,
      fontSize: 13,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      tabSize: 4,
      lineNumbers: 'on',
      folding: false,
      wordWrap: 'on'
    });
    editor.onDidChangeModelContent(() => {
      if (internalUpdate) return;
      onInput(editor.getValue());
    });
  });

  onDestroy(() => { editor?.dispose(); });

  // Parent-driven value sync. Reads `value` unconditionally so it
  // remains a tracked dep even when the early-returns trigger.
  $effect(() => {
    const next = value;
    if (!editor) return;
    if (next === editor.getValue()) return;
    internalUpdate = true;
    try {
      editor.setValue(next);
    } finally {
      internalUpdate = false;
    }
  });
</script>

<div class="relative" style:height>
  <div bind:this={host} class="h-full w-full rounded border border-[var(--border-soft)]"></div>
  {#if placeholder && !value}
    <div class="pointer-events-none absolute left-12 top-2 font-mono text-[12px] italic text-[var(--text-faint)]">
      {placeholder}
    </div>
  {/if}
</div>
