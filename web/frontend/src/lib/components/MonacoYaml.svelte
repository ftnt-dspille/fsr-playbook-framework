<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { Marker } from '$lib/api';
  import { ensureYamlSupport } from '$lib/monacoYamlSupport';
  import { enhanceJinjaEditor } from '$lib/jinja/enhanceJinjaEditor';
  import JinjaVarPicker from './JinjaVarPicker.svelte';
  import JinjaToolbar from './JinjaToolbar.svelte';

  let {
    value = '',
    onInput,
    markers = [] as Marker[],
    readOnly = false,
    onEditor
  }: {
    value: string;
    onInput: (v: string) => void;
    markers?: Marker[];
    readOnly?: boolean;
    /** Optional: parent receives the Monaco editor instance for
     * programmatic edits (e.g. the Fix-warnings panel uses
     * `editor.executeEdits` so each apply lands in the undo stack). */
    onEditor?: (editor: any, monaco: any) => void;
  } = $props();

  let host: HTMLDivElement;
  // editor / monaco / model are $state so the effects below re-run after
  // onMount finishes — without this, the value-sync effect captures
  // `editor === undefined` on its first run, never tracks `value`, and
  // never fires on subsequent prop changes.
  let editor = $state<any>(null);
  let monacoRef = $state<any>(null);
  let modelRef = $state<any>(null);
  let internalUpdate = false;

  onMount(async () => {
    const monaco = await import('monaco-editor');
    monacoRef = monaco;
    editor = monaco.editor.create(host, {
      value,
      language: 'yaml',
      theme: 'vs-dark',
      automaticLayout: true,
      readOnly,
      fontSize: 15,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      tabSize: 2,
      fixedOverflowWidgets: true
    });
    modelRef = editor.getModel();
    ensureYamlSupport(monaco);
    enhanceJinjaEditor(editor, monaco);
    editor.onDidChangeModelContent(() => {
      if (internalUpdate) return;
      onInput(editor.getValue());
    });
    applyMarkers();
    onEditor?.(editor, monaco);
  });

  onDestroy(() => {
    editor?.dispose();
  });

  // Push parent-driven value changes into the editor without echoing back.
  // Read `value` UNCONDITIONALLY so it is always a tracked dep (the early
  // returns below mustn't be allowed to short-circuit dep collection).
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

  $effect(() => {
    void markers;
    applyMarkers();
  });

  function applyMarkers() {
    if (!monacoRef || !modelRef) return;
    const sev = monacoRef.MarkerSeverity;
    const ms = markers.map((m) => ({
      startLineNumber: m.line,
      startColumn: m.col,
      endLineNumber: m.line,
      endColumn: m.col + 200,
      severity:
        m.severity === 'error' ? sev.Error : m.severity === 'warning' ? sev.Warning : sev.Info,
      message: m.suggestion ? `${m.message}\n→ ${m.suggestion}` : m.message,
      source: m.code
    }));
    monacoRef.editor.setModelMarkers(modelRef, 'fsrpb', ms);
  }
</script>

<div class="relative h-full w-full">
  <div bind:this={host} class="h-full w-full"></div>
  {#if editor && monacoRef && !readOnly}
    <div class="pointer-events-none absolute right-2 top-2 z-10 flex gap-2">
      <div class="pointer-events-auto">
        <JinjaVarPicker {editor} monaco={monacoRef} />
      </div>
      <div class="pointer-events-auto">
        <JinjaToolbar {editor} monaco={monacoRef} />
      </div>
    </div>
  {/if}
</div>
