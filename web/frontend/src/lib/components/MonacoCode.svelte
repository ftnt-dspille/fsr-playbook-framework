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
  import { ensureYamlSupport } from '$lib/monacoYamlSupport';
  import { enhanceJinjaEditor } from '$lib/jinja/enhanceJinjaEditor';
  import JinjaToolbar from './JinjaToolbar.svelte';

  let {
    value = '',
    language = 'python',
    onInput,
    readOnly = false,
    placeholder = '',
    height = '14rem',
    compact = false,
    showJinjaToolbar = false,
    onEditor,
    onFocus,
    onBlur
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
    /** Hide line numbers + the entire left gutter. Use for inline value
     * editors (set_variable rows, condition fields) where Monaco's
     * default gutter dominates a 1-line field. */
    compact?: boolean;
    /** Show the Jinja toolbar (filter palette + snippets + templates)
     * overlaid on this editor. Only relevant for yaml/jinja languages.
     * Default off so the toolbar doesn't clutter Python / JSON cells. */
    showJinjaToolbar?: boolean;
    /** Optional: parent receives the Monaco editor + namespace once
     * the editor is mounted. Used by the Jinja test modal so it can
     * setModelMarkers on render errors (mirroring the widget). */
    onEditor?: (editor: any, monaco: any) => void;
    /** Fired when the embedded editor gains focus. Used by inspector
     *  fields to claim themselves as the variable pane's insert target.
     *  No-op when omitted. */
    onFocus?: () => void;
    /** Fired when the embedded editor loses focus. */
    onBlur?: () => void;
  } = $props();

  let host: HTMLDivElement;
  let editor = $state<any>(null);
  let monacoRef = $state<any>(null);
  let internalUpdate = false;

  onMount(async () => {
    const monaco = await import('monaco-editor');
    monacoRef = monaco;
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
      lineNumbers: compact ? 'off' : 'on',
      // 3 chars handles up to line 999 — wide enough for any realistic
      // editor in this app and avoids the 5-char default's wasted gutter.
      lineNumbersMinChars: compact ? 0 : 3,
      lineDecorationsWidth: compact ? 0 : 4,
      // Drop the glyph margin entirely — we don't use breakpoint /
      // debug glyphs, and it adds ~28 px of empty left padding that
      // crowds short editors.
      glyphMargin: false,
      folding: false,
      wordWrap: 'on',
      // Render hover popovers (error tooltips, signature help, etc.)
      // at the document root so they aren't clipped by parent
      // `overflow: hidden` containers — e.g. the JinjaTestModal's
      // pane wrappers, which were chopping the "View Problem" popover.
      fixedOverflowWidgets: true
    });
    // When this slim wrapper hosts YAML or Jinja, register the shared
    // language providers so inline value editors (set_variable rows,
    // condition fields, jinja expression fields) get the same support
    // as the main YAML buffer. ensureYamlSupport is idempotent.
    if (language === 'yaml' || language === 'jinja') {
      ensureYamlSupport(monaco);
      enhanceJinjaEditor(editor, monaco);
    }
    onEditor?.(editor, monaco);
    editor.onDidChangeModelContent(() => {
      if (internalUpdate) return;
      onInput(editor.getValue());
    });
    // Forward Monaco's editor-text focus events. The DOM-level focus
    // event on `host` fires too early/late for nested widgets, so we
    // use Monaco's own listeners which fire when the actual textarea
    // gains/loses focus inside the editor.
    if (onFocus) editor.onDidFocusEditorText?.(() => onFocus());
    if (onBlur) editor.onDidBlurEditorText?.(() => onBlur());
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
    <div class="pointer-events-none absolute {compact ? 'left-3' : 'left-12'} top-2 font-mono text-[12px] italic text-[var(--text-faint)]">
      {placeholder}
    </div>
  {/if}
  {#if showJinjaToolbar && editor && monacoRef && (language === 'yaml' || language === 'jinja')}
    <div class="absolute right-2 top-2 z-10">
      <JinjaToolbar {editor} monaco={monacoRef} />
    </div>
  {/if}
</div>
