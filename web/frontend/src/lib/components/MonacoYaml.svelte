<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import type { Marker } from '$lib/api';
  import { registerYamlCompletions } from '$lib/yamlCompletions';

  let {
    value = '',
    onInput,
    markers = [] as Marker[],
    readOnly = false
  }: {
    value: string;
    onInput: (v: string) => void;
    markers?: Marker[];
    readOnly?: boolean;
  } = $props();

  let host: HTMLDivElement;
  // editor / monaco / model are $state so the effects below re-run after
  // onMount finishes — without this, the value-sync effect captures
  // `editor === undefined` on its first run, never tracks `value`, and
  // never fires on subsequent prop changes.
  let editor = $state<any>(null);
  let monacoRef = $state<any>(null);
  let modelRef = $state<any>(null);
  let completionDisposer: { dispose: () => void } | null = null;
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
      tabSize: 2
    });
    modelRef = editor.getModel();
    completionDisposer = registerYamlCompletions(monaco);
    editor.onDidChangeModelContent(() => {
      if (internalUpdate) return;
      onInput(editor.getValue());
    });
    applyMarkers();
  });

  onDestroy(() => {
    completionDisposer?.dispose();
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

<div bind:this={host} class="h-full w-full"></div>
